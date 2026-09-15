"""app.ingest.hindi_ocr: reading a book whose text layer cannot be trusted at all.

The real Hindi NCERT books (Kshitij, Kritika, Sparsh, Sanchayan) embed a pre-Unicode font
with no ToUnicode CMap, so their PDF text layer decodes as mojibake regardless of which
extraction method reads it -- a font-encoding problem, not a layout one, and the only fix
is reading the rendered page image instead of the text layer at all.

Gated on the same capability check the module itself uses: Tesseract and its Hindi
language data are a system package, present in the Docker image these tests run in but
not guaranteed everywhere, and skipping honestly beats a false pass or a hard failure.
"""

from __future__ import annotations

import pytest

from app.ingest.hindi_ocr import ocr_available, ocr_read_text

needs_ocr = pytest.mark.skipif(not ocr_available(), reason="tesseract-ocr-hin is not installed here")


def test_ocr_available_reports_a_bool_without_raising():
    assert isinstance(ocr_available(), bool)


@needs_ocr
def test_a_rendered_page_comes_back_as_real_text(tmp_path):
    """Not a Hindi-specific claim -- this checks the plumbing (render, shell out to
    tesseract, read its output file back) works at all, independent of OCR quality on any
    particular language or font."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=200)
    page.insert_text((60, 60), "Hello World")
    path = tmp_path / "smoke.pdf"
    doc.save(path)
    doc.close()

    text = ocr_read_text(path, lang="eng")
    assert "Hello" in text and "World" in text


@needs_ocr
def test_pages_are_joined_the_same_way_read_text_joins_them(tmp_path):
    """A pattern written against book.read_text's page-joining convention should not have
    to know whether the text underneath it came from the PDF's own layer or from OCR."""
    import pymupdf

    doc = pymupdf.open()
    for word in ("First", "Second"):
        page = doc.new_page(width=595, height=200)
        page.insert_text((60, 60), word)
    path = tmp_path / "two-pages.pdf"
    doc.save(path)
    doc.close()

    text = ocr_read_text(path, lang="eng")
    assert "First" in text
    assert "Second" in text
    assert text.index("First") < text.index("Second")
