"""The one place that decides how a Hindi book's real text gets read.

Three backends exist for the same problem (see app.ingest.hindi_ocr for why the PDF's own
text layer is unusable at all): Sarvam Vision 1.5, over the network, an OCR model trained
specifically on Indic scripts; Tesseract, local and free but a system binary Render's
free-tier Python runtime cannot install; Gemini, over the network too, general-purpose
rather than Indic-specialised, subject to that network's own reliability and Google's
pricing.

Sarvam is tried first when configured -- it exists specifically to be the accuracy option,
which is worth the network dependency it carries. Tesseract is next: local, free, no
network round trip to fail, and nothing about its output depends on a remote model's
prompt-following on any given call. A deployment gets it for free by running the Docker
image (see Dockerfile) instead of the native Python runtime; Render's free tier supports
both, so a second Docker-based service dedicated to Hindi ingest, pointed at the same
database as the main API, gets Tesseract without moving the main deployment off its own
free Python runtime. Gemini is the last resort, for a deployment with neither of the other
two -- still correct, just carrying the network's own failure modes with no Indic
specialisation to offset them.
"""

from __future__ import annotations

from app.ingest.gemini_ocr import gemini_read_text
from app.ingest.hindi_ocr import ocr_available, ocr_read_text
from app.ingest.sarvam_ocr import sarvam_read_text


def hindi_read_text(
    pdf_bytes: bytes, *, gemini_api_key: str | None, gemini_model: str,
    sarvam_api_key: str | None = None, sarvam_language: str = "hi-IN",
) -> str:
    """The book's real Unicode text, by whichever backend this deployment can actually run.

    Raises ValueError (mirroring gemini_read_text's/sarvam_read_text's own guards) when
    none is available -- an operator setup gap, not something to fall through silently on.
    """
    if sarvam_api_key:
        return sarvam_read_text(pdf_bytes, api_key=sarvam_api_key, language=sarvam_language)
    if ocr_available():
        return ocr_read_text(pdf_bytes)
    if not gemini_api_key:
        raise ValueError(
            "no Sarvam API key (YAADHUM_SARVAM_API_KEY), Tesseract is not installed here "
            "(this deployment is likely on Render's native Python runtime, not the Docker "
            "one), and no Gemini API key is configured (YAADHUM_GEMINI_API_KEY) either -- "
            "a Hindi book's text layer cannot be read at all without one of the three."
        )
    return gemini_read_text(pdf_bytes, api_key=gemini_api_key, model=gemini_model)
