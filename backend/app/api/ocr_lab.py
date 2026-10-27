"""The OCR mapper: read a question paper the way the teacher dashboard does, then map it.

An admin-console tool, beside the real pipeline and not part of it. It runs the SAME reading
steps a teacher's upload runs -- the same upload merger (``pages_to_pdf``), the same text-layer
reader (``extract_paper``), the same "is the text read trustworthy" test, and for a scan the
same vision reader (``rasterize_pdf`` + ``read_paper_vision``, with the same cheap-model cascade
and structure capture when those settings are on) -- by importing them, never copying or
changing them. The questions it reads are then mapped to chapter and topic with the prompt
mapper (``app.api.prompt_lab``, Haiku, from the book's complete topic list).

**It stores nothing in the database and changes no code.** The reading can take minutes, so it
runs as a background job like the teacher flow's, but the job lives in a temporary directory,
not a table: ``<tmp>/yaadhum-ocr-lab/<id>/state.json``, readable by every server process, and
deleted after a few hours. The uploaded pages are deleted the moment the read finishes. No
assessment, scanned question, question, placement, job row or file in the document store is
created; it never opens a database session of its own (the operator-key check, which every
admin route has, is the only database read).

Behind the operator key. Rate limited, and bounded in size and pages, because a read is paid.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

from app.api.deps import require_platform_admin
from app.api.upload import pages_to_pdf
from app.config import get_settings
from app.extraction.paper import context_addresses, extract_paper
from app.llm import estimate_usd
from app.mapping import ocr_mapper_v2
from app.ratelimit import FixedWindowLimiter, client_key

router = APIRouter(
    prefix="/platform/ocr-lab", tags=["ocr-lab"], dependencies=[Depends(require_platform_admin)],
)

_limiter = FixedWindowLimiter(limit=20, window_seconds=3600)
#: pages per paper: a read is paid per page, and no real paper is longer
MAX_PAGES = 30
#: what a read of one page costs on the vision model, for the estimate only. The vision reader
#: does not report tokens, so this is the measured-by-assumption figure from the cost
#: analysis (about 4.7K input, 2.5K output on Opus), not a bill.
EST_TOKENS_PER_PAGE = (4700, 2500)
JOB_TTL_SECONDS = 3 * 3600
_ID = re.compile(r"^[0-9a-f]{32}$")


def _root() -> Path:
    root = Path(tempfile.gettempdir()) / "yaadhum-ocr-lab"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _job_dir(job_id: str) -> Path:
    if not _ID.match(job_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such job")
    return _root() / job_id


def _write(job_id: str, **state) -> dict:
    """Merge ``state`` into the job's state file. Atomic, so a poll never reads half a file;
    shared across server processes because it is a file, not memory."""
    d = _job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "state.json"
    current = json.loads(path.read_text()) if path.exists() else {}
    current.update(state)
    current["job_id"] = job_id
    tmp = d / f"state.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(current))
    os.replace(tmp, path)
    return current


def _sweep() -> None:
    """Delete jobs older than the TTL, uploads and all."""
    cutoff = time.time() - JOB_TTL_SECONDS
    for d in _root().iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            continue


def _row(q) -> dict:
    return {
        "address": q.address, "section": q.section, "question_no": q.question_no,
        "sub_part": q.sub_part, "choice_alt": q.choice_alt,
        "marks": None if q.max_marks is None else float(q.max_marks), "text": q.stem_text,
        "page": q.logical_page, "is_context": bool(q.is_context),
        "attempt_required": q.attempt_required,
    }


def _mapping_text(q, passage_of: dict) -> str:
    """The sub-question together with the passage it is about, as the classify step hands its
    judge, so a case-based question is mapped on what the student read."""
    text = q.stem_text or ""
    passage = passage_of.get((q.section, q.question_no)) if q.sub_part else None
    if passage and passage not in text:
        return f"{passage}\n\nQUESTION ON THE PASSAGE ABOVE:\n{text}"
    return text


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def start(
    request: Request, background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    subject_code: str = Form("X.SST"),
    map_topics: bool = Form(True),
    prompt: str = Form(""),
) -> dict:
    settings = get_settings()
    _check_prompt(prompt)
    if map_topics and not settings.anthropic_api_key:
        raise HTTPException(status.HTTP_409_CONFLICT, "no YAADHUM_ANTHROPIC_API_KEY: mapping needs it")
    _limiter.check(client_key(request))
    _sweep()

    # the SAME merger the teacher upload uses: any number of PDFs and photographs, in the
    # order given, as one document
    path = await pages_to_pdf(files)
    try:
        extract = extract_paper(path, subject_code=subject_code)
        raw = path.read_bytes()
    finally:
        path.unlink(missing_ok=True)
    if extract.page_count > MAX_PAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"{extract.page_count} pages; at most {MAX_PAGES} per read")

    # the SAME decision the teacher flow makes: a scan, or a text read that does not add up
    from app.api.marks import _text_route_is_confident

    unreliable = extract.route == "text" and not _text_route_is_confident(extract)
    needs_vision = extract.route == "vision" or unreliable

    job_id = uuid.uuid4().hex
    _write(job_id, status="queued", created=time.time(), pages=extract.page_count,
           route="vision" if needs_vision else "text", phase="queued", done=0, total=extract.page_count,
           note=("the fast read of this paper looked unreliable, so it is being re-read with the "
                 "vision model" if unreliable else None))
    if needs_vision:
        (_job_dir(job_id) / "paper.pdf").write_bytes(raw)
    background_tasks.add_task(_run, job_id, extract if not needs_vision else None, needs_vision,
                              subject_code, map_topics, prompt)
    return {"job_id": job_id, "route": "vision" if needs_vision else "text", "pages": extract.page_count}


#: pasted questions per run, and characters per question: a map is paid per question
MAX_PASTED = 100
MAX_PASTED_CHARS = 4000
_NUMBERED = re.compile(r"^\s*(?:Q(?:uestion)?\.?\s*)?\d{1,3}\s*[.)]\s+\S", re.IGNORECASE)


def split_pasted(text: str) -> list[str]:
    """The questions in pasted text: split at each numbered line ("1." / "Q2)"), else at blank
    lines, else the whole text as one question."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    starts = [i for i, ln in enumerate(lines) if _NUMBERED.match(ln)]
    if len(starts) >= 2:
        bounds = starts + [len(lines)]
        parts = ["\n".join(lines[a:b]) for a, b in zip(bounds, bounds[1:], strict=False)]
        lead = "\n".join(lines[:starts[0]]).strip()
        if lead:                                  # text before the first number belongs with it
            parts[0] = lead + "\n" + parts[0]
    else:
        parts = re.split(r"\n\s*\n", "\n".join(lines))
    return [p.strip() for p in parts if p.strip()]


#: a trial prompt: the built-in Science one is about 96 KB
MAX_PROMPT_CHARS = 200_000


def _check_prompt(prompt: str) -> None:
    if len(prompt or "") > MAX_PROMPT_CHARS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"the prompt is over {MAX_PROMPT_CHARS} characters")


@router.get("/prompt")
def built_in_prompt(subject_code: str = "X.SST") -> dict:
    """The prompt the mapper uses for a subject, to start a trial prompt from."""
    profile = ocr_mapper_v2.profile_for(subject_code)
    return {"subject": profile.name, "prompt": profile.rules, "self_contained": profile.self_contained}


class PasteBody(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    subject_code: str = "X.SST"
    prompt: str = Field("", max_length=MAX_PROMPT_CHARS)


@router.post("/paste", status_code=status.HTTP_202_ACCEPTED)
def paste(body: PasteBody, request: Request, background_tasks: BackgroundTasks) -> dict:
    """Map questions that were typed or pasted instead of read from a paper: the same mapping
    step and result as an upload, without the reading."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(status.HTTP_409_CONFLICT, "no YAADHUM_ANTHROPIC_API_KEY: mapping needs it")
    _check_prompt(body.prompt)
    texts = split_pasted(body.text)
    if not texts:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "no question found in the pasted text")
    if len(texts) > MAX_PASTED:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"{len(texts)} questions; at most {MAX_PASTED} per run")
    _limiter.check(client_key(request))
    _sweep()
    job_id = uuid.uuid4().hex
    _write(job_id, status="mapping", created=time.time(), pages=0, route="paste", phase="mapping topics",
           done=0, total=len(texts))
    background_tasks.add_task(_run_paste, job_id, texts, body.subject_code, body.prompt)
    return {"job_id": job_id, "questions": len(texts)}


def _run_paste(job_id: str, texts: list[str], subject_code: str, prompt: str = "") -> None:
    """The background job for pasted questions. Never raises: a failure is written to the state."""
    try:
        questions = [
            SimpleNamespace(
                address=f"P:{i + 1}", section="", question_no=str(i + 1), sub_part=None, choice_alt=None,
                max_marks=None, stem_text=t[:MAX_PASTED_CHARS], logical_page=1, is_context=False,
                attempt_required=None)
            for i, t in enumerate(texts)
        ]
        result = {
            "ocr": {"route": "paste", "model": None, "estimated_usd": 0.0, "cascade": None},
            "checks": {"declared_total": None, "read_total": 0, "total_matches": None, "declared_count": None,
                       "read_count": len(questions), "declared_sections": {}, "section_titles": {},
                       "problems": []},
            "questions": [_row(q) for q in questions], "mapping": None,
        }
        _write(job_id, result=result)
        result["mapping"] = _map(questions, set(), {}, get_settings(), subject_code, prompt)
        _write(job_id, result=result, status="done", phase="done")
    except Exception as exc:  # noqa: BLE001 -- the job's state is the only place it can be seen
        _write(job_id, status="failed", error=f"{type(exc).__name__}: {str(exc)[:400]}")


@router.get("/jobs/{job_id}")
def poll(job_id: str) -> dict:
    path = _job_dir(job_id) / "state.json"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such job (it may have expired)")
    state = json.loads(path.read_text())
    if state["status"] in {"queued", "reading", "mapping"} and time.time() - state["created"] > 20 * 60:
        state = _write(
            job_id, status="failed", error="the read never finished; the server may have restarted")
    return state


def _run(job_id: str, text_extract, needs_vision: bool, subject_code: str, map_topics: bool,
         prompt: str = "") -> None:
    """The background job. Never raises: any failure is written to the job's state."""
    settings = get_settings()
    paper = _job_dir(job_id) / "paper.pdf"
    try:
        ocr: dict = {"route": "text", "model": None, "estimated_usd": 0.0, "cascade": None}
        if needs_vision:
            _write(job_id, status="reading", phase="reading pages", done=0)
            extract, ocr = _read_with_vision(job_id, paper, settings)
        else:
            extract = text_extract
        paper.unlink(missing_ok=True)          # the pages are not kept

        questions = extract.questions
        context = context_addresses(questions)
        passage_of = {
            (q.section, q.question_no): (q.stem_text or "").strip()
            for q in questions if q.address in context and (q.stem_text or "").strip()
        }
        rows = [_row(q) for q in questions]
        read_total = float(extract.total_marks)
        checks = {
            "declared_total": extract.declared_total,
            "read_total": round(read_total, 2),
            "total_matches": None if extract.declared_total is None
            else abs(read_total - float(extract.declared_total)) < 0.01,
            "declared_count": extract.declared_count,
            "read_count": len({
                q.question_no for q in questions if q.address not in context and not q.is_context}),
            "declared_sections": extract.declared_sections,
            "section_titles": extract.section_titles,
            "problems": list(extract.problems),
        }
        result = {"ocr": ocr, "checks": checks, "questions": rows, "mapping": None}
        _write(job_id, result=result, phase="read", done=extract.page_count)

        if map_topics:
            _write(job_id, status="mapping", phase="mapping topics")
            result["mapping"] = _map(questions, context, passage_of, settings, subject_code, prompt)
            _write(job_id, result=result)
        _write(job_id, status="done", phase="done")
    except Exception as exc:  # noqa: BLE001 -- the job's state is the only place it can be seen
        paper.unlink(missing_ok=True)
        _write(job_id, status="failed", error=f"{type(exc).__name__}: {str(exc)[:400]}")


def _read_with_vision(job_id: str, paper: Path, settings):
    """The teacher flow's vision read, step for step: rasterize, then the vision reader, with the
    same cheap-model cascade and structure capture when those settings are on."""
    from app.extraction.paper import PaperExtract
    from app.extraction.paper_vision import rasterize_pdf, read_paper_vision

    pages = rasterize_pdf(paper)
    structure = {"capture_structure": True} if settings.paper_capture_structure else {}

    def progress(done, total):
        _write(job_id, done=done, total=total)

    def read(pages_, *, model, on_progress, **extra):
        return read_paper_vision(
            pages_, api_key=settings.anthropic_api_key, model=model,
            page_concurrency=settings.vision_page_concurrency, on_progress=on_progress, **extra)

    cascade = None
    if settings.vision_cheap_model:
        from app.extraction.vision_cascade import read_with_cascade

        reading, cascade = read_with_cascade(
            pages, cheap=settings.vision_cheap_model, strong=settings.model_high_stakes,
            read=read, on_progress=progress, **structure)
    else:
        reading = read(pages, model=settings.model_high_stakes, on_progress=progress, **structure)
    if reading.refused:
        raise RuntimeError(reading.refused)
    extract = PaperExtract(
        route="vision", page_count=len(pages), questions=reading.questions,
        declared_sections=reading.declared_sections, declared_count=reading.declared_count,
        declared_total=reading.declared_total, problems=reading.problems,
        section_titles=dict(getattr(reading, "section_titles", None) or {}),
        syllabus_lines=list(getattr(reading, "syllabus_lines", None) or []),
    )
    pt_in, pt_out = EST_TOKENS_PER_PAGE
    strong_pages = len(pages) if cascade is None else cascade["strong_pages"]
    cheap_pages = 0 if cascade is None else cascade["cheap_pages"]
    usd = strong_pages * estimate_usd(settings.model_high_stakes, pt_in, pt_out)
    if cascade and cheap_pages:
        usd += cheap_pages * estimate_usd(settings.vision_cheap_model, pt_in, pt_out)
    return extract, {
        "route": "vision", "model": settings.model_high_stakes, "pages": len(pages),
        "estimated_usd": round(usd, 3), "estimate_note": "an estimate: the reader does not report tokens",
        "cascade": cascade,
    }


def _looks_cut_off(text: str) -> bool:
    """A stem that stops on a lone letter or a bare list marker ("IV. E"): the read lost its end."""
    t = text.rstrip()
    # "III, IV, I": the last item of a list of roman numerals or options is not a lost word
    lone_letter = re.search(r"(^|\s)[A-Za-z]$", t) and not re.search(r",\s*[A-Za-z]$", t)
    return bool(
        lone_letter
        or re.search(r"(^|\s)([IVXivx]+|[A-Da-d])[.)]$", t)
        or re.search(r"\([a-dA-D]\)$", t)
    )


def _map(questions, context: set, passage_of: dict, settings, subject_code: str = "X.SST",
         prompt: str = "", dedupe: bool = True, strict_flags: bool = True,
         tier: bool = False) -> dict:
    """Map every real question (not a shared passage) with the prompt mapper."""
    from app.api import prompt_lab

    base = ocr_mapper_v2.profile_for(subject_code)
    profile = ocr_mapper_v2.with_prompt(base, prompt)
    taxonomy = profile.taxonomy()
    model = settings.model_high_volume
    client = prompt_lab._client(settings)
    real = [q for q in questions if q.address not in context and not getattr(q, "is_context", False)]
    # The reader sometimes returns the same question twice (one copy without its statements or
    # options). Map the fuller one; the other would only overwrite it under the same address.
    fullest: dict[tuple, object] = {}
    for q in real if dedupe else []:
        k = (q.section, q.question_no, q.sub_part, q.choice_alt)
        if k not in fullest or len(q.stem_text or "") > len(fullest[k].stem_text or ""):
            fullest[k] = q
    if dedupe:
        real = [q for q in real if fullest[(q.section, q.question_no, q.sub_part, q.choice_alt)] is q]
    rows = [
        {"row": i, "text": _mapping_text(q, passage_of).strip()[:4000],
         **({"section": q.section.strip().upper()} if q.section and q.section.strip() else {})}
        for i, q in enumerate(real)
    ]
    # the book's own text finds candidate sections, a cheap model chooses among them, and a strong
    # model rereads the doubtful answers (app.mapping.ocr_mapper_v2)
    answers, usage_by_model, calls, errors, meta = ocr_mapper_v2.map_rows_v2(
        client, settings, rows, taxonomy, profile, tier=tier)
    results = {
        q.address: profile.resolve(taxonomy, answers.get(i), q.section) for i, q in enumerate(real)
    }
    for i, q in enumerate(real):
        r = results[q.address]
        r["tier"] = getattr(answers.get(i), "cognitive_tier", None)
        m = meta.get(i, {})
        r["book_check"] = {
            "candidates": m.get("candidates", []), "supported_by_book": m.get("supported_by_book"),
            "first_pass": m.get("first_pass"), "second_reader": bool(m.get("verified")),
            "second_reader_changed": bool(m.get("changed")),
        }
        if m.get("changed") and m.get("second_reader_confidence") != "high":
            r["problems"].append("the two readers disagreed and the second is not sure")
            r["needs_review"] = True
        elif (strict_flags and m.get("candidates") and not m.get("supported_by_book")
              and not m.get("verified")):
            r["problems"].append("the textbook text does not clearly point to this topic")
            r["needs_review"] = True
    for q in real if strict_flags else []:
        if _looks_cut_off(q.stem_text or ""):
            r = results[q.address]
            r["problems"].append("the question text looks cut off; check the scan")
            r["needs_review"] = True
    usage = {k: sum(u[k] for u in usage_by_model.values())
             for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")}
    usd = sum(estimate_usd(m, u["input_tokens"], u["output_tokens"], u["cache_read_tokens"],
                           cache_write_tokens=u["cache_write_tokens"]) for m, u in usage_by_model.items())
    mapped_n = sum(1 for r in results.values() if r["topic"])
    return {
        "subject": profile.name, "custom_prompt": profile is not base, "model": model,
        "second_reader_model": settings.model_high_stakes,
        "calls": calls, "errors": errors, "by_address": results,
        "summary": {
            "questions": len(real), "mapped": mapped_n,
            "needs_review": sum(1 for r in results.values() if r["needs_review"]),
            "high": sum(1 for r in results.values() if r["confidence"] == "high"),
        },
        "spend": {**usage, "estimated_usd": round(usd, 4)},
    }
