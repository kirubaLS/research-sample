"""Read a Hindi NCERT book with Gemini, because Tesseract needs a system binary this
deployment's Render plan cannot install.

The real files (Kshitij, Kritika, Sparsh, Sanchayan) embed a pre-Unicode font
(Walkman-Chanakya) with no ``ToUnicode`` CMap -- see app.ingest.hindi_ocr for the full
explanation of why the PDF's own text layer cannot be trusted at all. That module reads
the rendered page with Tesseract, a system binary Render's free-tier Python runtime
cannot install (only its Docker runtime can, and this deployment runs the Python one).
Gemini reads the PDF directly over the API instead -- no system dependency.

One call per PAGE, not one call per file: a whole 15-20 page chapter sent as a single
inline PDF was the shape of every "Gemini OCR failed after 3 attempts" -- the request
itself is large, and asking one call to transcribe that many pages in one response gives
Gemini far more places to time out, get rate-limited mid-generation, or simply run long
than a single page ever does. Splitting page-by-page (image, not PDF, per call -- see
app.ingest.hindi_ocr for the same page-image approach with Tesseract) means a page that
fails retries independently of the twenty around it, and the total work per call is small
enough that a failure is actually the exception's fault, not the request's size.
"""

from __future__ import annotations

import base64
import time

import httpx
import pymupdf

ENDPOINT_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

#: A synchronous vision call on a full chapter PDF genuinely takes tens of seconds, and a
#: managed platform's outbound network has its own occasional connect/read failures having
#: nothing to do with the request itself -- "Could not reach the API" on a request that
#: reached this code was one of those, not a bad payload, and a single unretried attempt
#: turned it into a hard failure instead of a slow success. Same shape as
#: app.ingest.jina.JinaEmbedder's own retry loop. Retried per page now, not per file, so
#: one bad page never spends all three attempts on work the other pages already finished.
MAX_RETRIES = 3

#: Matches app.ingest.hindi_ocr.OCR_DPI: dense Devanagari conjuncts need the resolution: a
#: lower DPI reads as plausible-looking wrong text rather than failing loudly, which is a
#: worse failure than this being slow.
RENDER_DPI = 300

#: One page, not "this PDF": asked to "read this book," a model tends to summarise once
#: the page runs long, and a whole-file version of this prompt was the wording in place
#: when a full chapter was still sent as a single call.
PAGE_PROMPT = (
    "Transcribe the Hindi (Devanagari) text of this page image exactly as printed, in "
    "reading order. Output ONLY the transcribed text -- no summary, no translation, no "
    "commentary, no markdown formatting. If the page has no readable text, output nothing."
)


def _gemini_call(
    parts: list[dict], *, api_key: str, model: str, timeout: float, max_retries: int,
) -> str:
    """One generateContent call, retried the way app.ingest.jina.JinaEmbedder retries its
    own provider calls: a transport failure (the platform's network, not this request) and
    a 429 or 5xx (the provider's fault, not the payload's). A 4xx other than 429 is the
    payload's fault and is never worth retrying.
    """
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.0},  # deterministic transcription
    }

    last: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = httpx.post(
                ENDPOINT_TEMPLATE.format(model=model),
                params={"key": api_key}, json=payload, timeout=timeout,
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"Gemini returned {response.status_code}",
                    request=response.request, response=response,
                )
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates") or []
            if not candidates:
                block_reason = (data.get("promptFeedback") or {}).get("blockReason")
                raise RuntimeError(
                    "Gemini returned no candidates"
                    f"{f' (blocked: {block_reason})' if block_reason else ''}"
                )
            found = candidates[0].get("content", {}).get("parts") or []
            return "".join(p.get("text", "") for p in found)
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last = exc
            if attempt < max_retries - 1:
                time.sleep(2**attempt)

    raise RuntimeError(f"Gemini OCR failed after {max_retries} attempts") from last


def gemini_read_text(
    pdf_bytes: bytes, *, api_key: str, model: str = "gemini-3.6-flash", timeout: float = 60.0,
    max_retries: int = MAX_RETRIES,
) -> str:
    """The book's real Unicode text, transcribed one page at a time and joined the way
    every other read_text-like function in this codebase joins pages (a blank line), so a
    pattern written against that convention does not have to know this text came from
    Gemini rather than PyMuPDF or Tesseract.

    Raises for a non-2xx response rather than returning something that looks like text but
    is an error message -- a silently wrong transcription is worse than a loud failure
    here, the same reasoning every other ingest guard in this codebase follows.
    """
    if not api_key:
        raise ValueError(
            "no Gemini API key. Set YAADHUM_GEMINI_API_KEY -- without it a Hindi book's "
            "text layer cannot be read at all, since it decodes as mojibake and Tesseract "
            "needs a system binary this deployment cannot install."
        )

    pages: list[str] = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            png_bytes = page.get_pixmap(dpi=RENDER_DPI).tobytes("png")
            parts = [
                {"inline_data": {"mime_type": "image/png",
                                  "data": base64.b64encode(png_bytes).decode("ascii")}},
                {"text": PAGE_PROMPT},
            ]
            pages.append(_gemini_call(
                parts, api_key=api_key, model=model, timeout=timeout, max_retries=max_retries,
            ))
    return "\n\n".join(pages)
