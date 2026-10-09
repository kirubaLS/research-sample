"""Read the first page of an uploaded question paper and say what it is.

A teacher drops a paper in before any test exists. This returns what the paper's own heading
says -- subject, class, the test's name, its date, what it is worth -- so the screen can make
the exam card itself. It stores nothing and changes nothing: the card, the paper and the full
read (confirm, map, classify) are the existing endpoints, called by the page afterwards.

One cheap call on one page. When the first page has a text layer its text is sent instead of
an image, which is cheaper and exact.
"""

from __future__ import annotations

import base64
import json
import re

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.api.deps import Staff, require_staff
from app.api.upload import pages_to_pdf
from app.config import get_settings
from app.llm import estimate_usd
from app.ratelimit import FixedWindowLimiter, client_key

router = APIRouter(prefix="/paper-intake", tags=["paper-intake"])

_limiter = FixedWindowLimiter(limit=60, window_seconds=3600)
MAX_FILES = 25

PROMPT = """This is the first page of a school question paper. Read only its heading, not the questions.
Reply with one JSON object and nothing else:
{"subject": string|null, "class": string|null, "title": string|null, "date": string|null,
 "total_marks": number|null, "duration": string|null}
- subject: the subject exactly as printed (e.g. "Mathematics", "Social Science", "Hindi").
- class: the class/standard as printed (e.g. "X", "10").
- title: the name of the test or exam as printed (e.g. "Unit Test 1", "Half Yearly Examination"). Not the school's name.
- date: the exam date as YYYY-MM-DD if one is printed, else null.
- total_marks: the maximum marks printed (e.g. "Max. Marks: 80" gives 80), else null.
- duration: as printed (e.g. "3 hours"), else null.
Use null for anything not printed. Never guess."""


def _first_page(pdf_path) -> tuple[str, bytes | None]:
    """The first page's text layer, and its image only when the text layer is too thin to use."""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        page = doc[0]
        text = (page.get_text() or "").strip()
        if len(text) >= 80:
            return text[:4000], None
        long_edge_in = max(page.rect.width, page.rect.height) / 72
        dpi = max(100, min(200, 1568 / long_edge_in))
        return "", page.get_pixmap(dpi=round(dpi)).tobytes("jpg", jpg_quality=85)


def _clean(raw: dict) -> dict:
    def text(v, limit=120):
        return v.strip()[:limit] if isinstance(v, str) and v.strip() else None

    marks = raw.get("total_marks")
    if isinstance(marks, str):
        m = re.search(r"\d+(?:\.\d+)?", marks)
        marks = float(m.group()) if m else None
    if not isinstance(marks, (int, float)) or isinstance(marks, bool) or not (0 < marks <= 1000):
        marks = None
    date = text(raw.get("date"), 10)
    if date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        date = None
    return {
        "subject": text(raw.get("subject")), "class": text(raw.get("class"), 20), "title": text(raw.get("title")),
        "date": date, "total_marks": marks, "duration": text(raw.get("duration"), 40),
    }


def _ask(settings, text: str, image: bytes | None) -> tuple[dict, str, float]:
    import anthropic

    model = settings.vision_cheap_model or settings.model_high_volume
    content: list[dict] = []
    if image is not None:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.b64encode(image).decode()}})
    else:
        content.append({"type": "text", "text": f"The page's text:\n\n{text}"})
    content.append({"type": "text", "text": PROMPT})
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(model=model, max_tokens=400, messages=[{"role": "user", "content": content}])
    out = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    match = re.search(r"\{.*\}", out, re.S)
    parsed = json.loads(match.group()) if match else {}
    usd = estimate_usd(model, resp.usage.input_tokens, resp.usage.output_tokens)
    return parsed if isinstance(parsed, dict) else {}, model, round(usd, 5)


@router.post("/detect")
async def detect(
    request: Request,
    files: list[UploadFile] = File(...),
    _staff: Staff = Depends(require_staff),
) -> dict:
    """What the paper's heading says. Fields it does not print come back null."""
    _limiter.check(client_key(request))
    if not files or len(files) > MAX_FILES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"send 1 to {MAX_FILES} files")
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {"detected": _clean({}), "model": None, "estimated_usd": 0.0,
                "note": "No model key is configured, so the heading could not be read."}
    path = await pages_to_pdf(files)
    try:
        text, image = _first_page(path)
    except Exception as exc:  # an unreadable file is a fact about the file
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "that file could not be opened") from exc
    finally:
        path.unlink(missing_ok=True)
    try:
        raw, model, usd = _ask(settings, text, image)
    except Exception:
        return {"detected": _clean({}), "model": None, "estimated_usd": 0.0,
                "note": "The heading could not be read this time."}
    return {"detected": _clean(raw), "model": model, "estimated_usd": usd, "note": None}
