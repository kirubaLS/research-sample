"""Read a Hindi NCERT book with Gemini, because Tesseract needs a system binary this
deployment's Render plan cannot install.

The real files (Kshitij, Kritika, Sparsh, Sanchayan) embed a pre-Unicode font
(Walkman-Chanakya) with no ``ToUnicode`` CMap -- see app.ingest.hindi_ocr for the full
explanation of why the PDF's own text layer cannot be trusted at all. That module reads
the rendered page with Tesseract, a system binary Render's free-tier Python runtime
cannot install (only its Docker runtime can, and this deployment runs the Python one).
Gemini reads the PDF directly over the API instead -- no system dependency, one HTTP call
per file rather than one per page.

Sent as ``inline_data``, not the Files API: these prelims and chapter files are a few MB,
comfortably under the 20MB inline limit, and Files API storage/lifecycle is machinery this
does not need for a file used once and discarded.
"""

from __future__ import annotations

import base64

import httpx

ENDPOINT_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

#: Transcribe, not describe or translate: a model asked to "read this book" tends to
#: summarise once the page runs long. Page-break markers keep the join honest -- so a
#: pattern written against the page-joining convention every other read_text-like
#: function in this codebase uses (a blank line between pages) does not have to know this
#: text came from Gemini rather than PyMuPDF or Tesseract.
PROMPT = (
    "Transcribe the Hindi (Devanagari) text of this PDF exactly as printed, page by page, "
    "in reading order. Output ONLY the transcribed text -- no summary, no translation, no "
    "commentary, no markdown formatting. Between each page's text, output a line "
    "containing only: ===PAGE BREAK==="
)


def gemini_read_text(
    pdf_bytes: bytes, *, api_key: str, model: str = "gemini-2.5-flash", timeout: float = 180.0,
) -> str:
    """The book's real Unicode text, transcribed page by page.

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

    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "application/pdf",
                                  "data": base64.b64encode(pdf_bytes).decode("ascii")}},
                {"text": PROMPT},
            ],
        }],
        # deterministic transcription, not creative writing
        "generationConfig": {"temperature": 0.0},
    }
    response = httpx.post(
        ENDPOINT_TEMPLATE.format(model=model),
        params={"key": api_key}, json=payload, timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        block_reason = (data.get("promptFeedback") or {}).get("blockReason")
        raise RuntimeError(
            f"Gemini returned no candidates{f' (blocked: {block_reason})' if block_reason else ''}"
        )
    parts = candidates[0].get("content", {}).get("parts") or []
    transcript = "".join(p.get("text", "") for p in parts)
    return transcript.replace("===PAGE BREAK===", "\n\n")
