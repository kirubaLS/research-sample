"""Read a Tamil book PAGE by OCR, for the pages whose font subset has a broken
``ToUnicode`` CMap -- see app.ingest.tamil_text's module docstring for the full
explanation, and app.ingest.hindi_ocr for the same class of defect in a different
language (there, every page of the book; here, only some chapters' pages).

Unlike Hindi, most of a Tamil book's pages extract cleanly through the PDF's own text
layer (app.ingest.tamil_text.tamil_read_text, after its glyph-repeat fix) -- there is no
whole-book ``hindi_read_text``-style dispatcher here, because most pages should never pay
OCR's cost at all. This module exists only to re-read the specific pages
app.ingest.tamil_text.tamil_text_is_corrupted flags, one page at a time, which is why its
entry point takes an already-open ``pymupdf.Page`` rather than a whole file.

Same CLI-Tesseract approach as app.ingest.hindi_ocr, for the same reason: PyMuPDF's own
``get_textpage_ocr()`` shells out to Tesseract too but with less control over page
segmentation, and invoking the binary directly is the version already proven (on Hindi)
to keep words from breaking apart mid-conjunct.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf

#: Same reasoning as app.ingest.hindi_ocr.OCR_DPI: dense book type set in Tamil
#: consonant-vowel-sign clusters needs the extra resolution over a mark sheet's few
#: handwritten digits to come back legible at all. Tamil has no reason to need a
#: different value from Hindi here -- the resolution requirement comes from the type
#: being small and dense, not from which script it is set in.
OCR_DPI = 300
#: Tesseract's Tamil traineddata, distinct from Hindi's 'hin' -- installed separately
#: (tesseract-ocr-tam on Debian/Ubuntu) and checked for by name in ocr_available().
OCR_LANG = "tam"
#: PSM 6 ("assume a single uniform block of text"), the same choice app.ingest.hindi_ocr
#: settled on for Hindi rather than the default PSM 3 ("fully automatic"). Not re-derived
#: from a Tamil-specific failure the way Hindi's was (no real corrupted Tamil page has
#: been run through both PSMs to compare) -- but the underlying reasoning carries over
#: unchanged: these are the same shape of pages, dense running prose in a single column,
#: which is exactly the layout PSM 6 targets and PSM 3's layout-guessing has no need to
#: get right here. Worth revisiting against a real flagged Tamil page once one exists to
#: compare against, the same way Hindi's own choice was pinned down.
OCR_PSM = "6"
#: Same reasoning and same value as app.ingest.hindi_ocr.OCR_PAGE_TIMEOUT_SECONDS: this
#: runs inside a background ingest job, not a blocking request, so correctness (letting a
#: slow instance actually finish) matters more than a tight bound.
OCR_PAGE_TIMEOUT_SECONDS = 600


def ocr_available() -> bool:
    """Whether Tamil text recognition can run here -- mirrors
    app.ingest.hindi_ocr.ocr_available() exactly, checked against 'tam' rather than 'hin'.
    A capability, not an assumption: Tesseract's Tamil language data is a system package a
    deployment either has installed or does not, and the difference has to reach the
    person uploading (as a clear error -- see tamil_text._extract_tamil_page_text) rather
    than surfacing as silently-wrong text.
    """
    if shutil.which("tesseract") is None:
        return False
    try:
        langs = subprocess.run(
            ["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return OCR_LANG in langs.splitlines()


def ocr_read_page(
    page: "pymupdf.Page", *, dpi: int = OCR_DPI, lang: str = OCR_LANG,
) -> str:
    """One already-open page's text, recognised from its rendered image -- the unit
    app.ingest.tamil_text actually needs, since only some pages of a Tamil chapter are
    corrupted and OCR-ing the rest would be pure waste (see that module's docstring).
    """
    # Grayscale, not the default RGB -- same memory reasoning as app.ingest.hindi_ocr's
    # own ocr_read_text: a third of the pixel memory for the same resolution and the same
    # text, which matters on a constrained free-tier instance.
    pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    with tempfile.TemporaryDirectory() as tmp:
        image_path = Path(tmp) / "page.png"
        pixmap.save(image_path)
        pixmap = None
        out_prefix = Path(tmp) / "out"
        result = subprocess.run(
            ["tesseract", str(image_path), str(out_prefix), "-l", lang, "--psm", OCR_PSM],
            capture_output=True, text=True, timeout=OCR_PAGE_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"tesseract failed on page {page.number + 1}: {result.stderr.strip()}"
            )
        return (out_prefix.with_suffix(".txt")).read_text(encoding="utf-8")


def ocr_read_text(source: str | bytes, *, dpi: int = OCR_DPI, lang: str = OCR_LANG) -> str:
    """Every page of a whole file, OCR'd unconditionally -- provided for parity with
    app.ingest.hindi_ocr.ocr_read_text (e.g. for testing this backend directly, or a
    future book whose corruption is not confined to a few pages), but NOT what
    app.ingest.tamil_text.tamil_read_text calls day to day -- that calls ocr_read_page
    per flagged page instead, to avoid paying OCR's cost on chapters that extract cleanly.
    """
    pages: list[str] = []
    opened = pymupdf.open(stream=source, filetype="pdf") if isinstance(source, bytes) else pymupdf.open(source)
    with opened as doc:
        for page in doc:
            pages.append(ocr_read_page(page, dpi=dpi, lang=lang))
    return "\n\n".join(pages)
