"""The one place that decides how a Hindi book's real text gets read.

Two backends exist for the same problem (see app.ingest.hindi_ocr for why the PDF's own
text layer is unusable at all): Tesseract, local and free but a system binary Render's
free-tier Python runtime cannot install; Gemini, over the network, no system dependency,
but subject to that network's own reliability and Google's pricing.

Tesseract is preferred whenever it is actually available -- accuracy and reliability both
favour it here: it reads the rendered page directly with no network round trip to fail,
and nothing about its output depends on a remote model's prompt-following on any given
call. A deployment gets this for free by running the Docker image (see Dockerfile) instead
of the native Python runtime; Render's free tier supports both, so a second Docker-based
service dedicated to Hindi ingest, pointed at the same database as the main API, gets
Tesseract's accuracy without moving the main deployment off its own free Python runtime.
Gemini is the fallback for a deployment that has not done that -- still correct, just
carrying the network's own failure modes on top.
"""

from __future__ import annotations

from app.ingest.gemini_ocr import gemini_read_text
from app.ingest.hindi_ocr import ocr_available, ocr_read_text


def hindi_read_text(
    pdf_bytes: bytes, *, gemini_api_key: str | None, gemini_model: str,
) -> str:
    """The book's real Unicode text, by whichever backend this deployment can actually run.

    Raises ValueError (mirroring gemini_read_text's own guard) when neither is available --
    an operator setup gap, not something to fall through silently on.
    """
    if ocr_available():
        return ocr_read_text(pdf_bytes)
    if not gemini_api_key:
        raise ValueError(
            "Tesseract is not installed here (this deployment is likely on Render's "
            "native Python runtime, not the Docker one) and no Gemini API key is "
            "configured (YAADHUM_GEMINI_API_KEY) either -- a Hindi book's text layer "
            "cannot be read at all without one of the two."
        )
    return gemini_read_text(pdf_bytes, api_key=gemini_api_key, model=gemini_model)
