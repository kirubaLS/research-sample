"""Read a Hindi NCERT book by OCR, because its text layer cannot be trusted at all.

The real files (Kshitij, Kritika, Sparsh, Sanchayan) embed a pre-Unicode font --
Walkman-Chanakya -- with no ``ToUnicode`` CMap. Every glyph is drawn from a WinAnsi code
point chosen to *look like* Devanagari in that one font; nothing in the PDF says what
Unicode character it actually is. ``page.get_text()`` (what ``book.read_text`` uses for
every other subject) returns that raw code point back as if it were real text, which
decodes as mojibake regardless of which PyMuPDF call reads it -- this is not the layout
problem every other subject's fix addressed, it is a font-encoding problem no amount of
regex on the existing text layer can solve.

Reading the *rendered page image* sidesteps the encoding entirely: OCR reads the ink, not
the font's internal numbering, so it comes back as real Unicode Devanagari. Tried two
ways before settling on the CLI: PyMuPDF's own ``get_textpage_ocr()`` also shells out to
Tesseract, but its default page segmentation broke words apart mid-conjunct on these
files ("पाठ्यसामग्रीकापुनर्सयोजन" with no spaces at all) where invoking the ``tesseract``
binary directly on a rendered pixmap did not.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf

#: 300, not marksheet.py's 200: a mark sheet's OCR target is a few handwritten digits:
#: this one is dense book type set in Devanagari conjuncts, which needs the extra
#: resolution to come back legible at all.
OCR_DPI = 300
OCR_LANG = "hin"
#: Tesseract's default page segmentation (PSM 3, "fully automatic") reads the running
#: prose of a chapter fine but dropped the leading serial number on a contents-page entry
#: in the real Kritika file half the time -- '1.' in front of the first chapter's title
#: rendered as a bare '.' with the digit missing entirely, while every later entry ('2.',
#: '3.') kept its number. PSM 6 ("assume a single uniform block of text") recovered two
#: of the three numbers that PSM 3 dropped on the same page; the remaining one -- always
#: the first entry, never a later one -- is recovered separately, see
#: app.ingest.book._recover_hindi_first_chapter_number.
OCR_PSM = "6"
#: Render's shared/free-tier CPU took over 120s on a single dense page -- real, not a
#: hang, confirmed by the same page finishing on a second try. This runs inside a
#: background job (see IngestJob), not a blocking HTTP request, so there is no reason to
#: keep this tight: correctness matters more than speed for an admin-only, occasional
#: upload. 10 minutes is generous even for a slow instance; a page that still has not
#: finished by then really has hung.
OCR_PAGE_TIMEOUT_SECONDS = 600


def ocr_available() -> bool:
    """Whether Hindi text recognition can run here.

    A capability, not an assumption -- same reasoning as app.extraction.marksheet's own
    ocr_available(): Tesseract, and specifically its Hindi language data, is a system
    package that a deployment either has or does not, and the difference has to reach the
    person uploading rather than surfacing as silently empty text.
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


def ocr_read_text(source: str | Path | bytes, *, dpi: int = OCR_DPI, lang: str = OCR_LANG) -> str:
    """Every page's text, recognised from its rendered image.

    Pages are joined by a blank line, the same separator plain ``read_text`` uses, so a
    pattern written against one page's contents does not have to know it came from OCR.

    ``source`` is a path or the file's bytes directly -- the bytes form is what
    app.ingest.hindi_text uses, matching app.ingest.gemini_ocr.gemini_read_text's own
    bytes-in signature so the two OCR backends are interchangeable behind one call.
    """
    pages: list[str] = []
    opened = pymupdf.open(stream=source, filetype="pdf") if isinstance(source, bytes) else pymupdf.open(source)
    with opened as doc:
        for page in doc:
            # Grayscale, not the default RGB: a third of the pixel memory for exactly the
            # same resolution and the same text -- Tesseract reads ink, not colour, and a
            # Render free-tier instance ("exceeds memory limit", the whole process killed
            # mid-job) does not have RGB's headroom to spare rendering one dense page at
            # 300 DPI. One page at a time and each pixmap freed before the next page's
            # is even created, so peak memory is one page's worth, not the whole book's.
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
                        f"tesseract failed on page {page.number + 1} of {source}: "
                        f"{result.stderr.strip()}"
                    )
                pages.append((out_prefix.with_suffix(".txt")).read_text(encoding="utf-8"))
    return "\n\n".join(pages)
