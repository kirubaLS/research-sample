"""app.ingest.tamil_ocr: reading a single Tamil page whose font subset has a broken
ToUnicode CMap -- see app.ingest.tamil_text's module docstring for the defect, and
app.ingest.hindi_ocr for the same defect class in a different language.

Gated on the same capability check the module itself uses -- Tesseract's Tamil language
data ('tam') is a system package, not guaranteed to be present in every environment these
tests run in, and skipping honestly beats a false pass or a hard failure.
"""

from __future__ import annotations

import pytest

from app.ingest.tamil_ocr import ocr_available, ocr_read_page, ocr_read_text

needs_ocr = pytest.mark.skipif(not ocr_available(), reason="tesseract-ocr-tam is not installed here")


def test_ocr_available_reports_a_bool_without_raising():
    assert isinstance(ocr_available(), bool)


@needs_ocr
def test_a_rendered_page_comes_back_as_real_text(tmp_path):
    """Not a Tamil-specific claim -- checks the plumbing (render, shell out to tesseract,
    read its output file back) works at all, independent of OCR quality on any particular
    language or font. Uses English/'eng' the same way test_hindi_ocr's smoke test does,
    since the point is the plumbing, not transcription accuracy."""
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
def test_ocr_read_page_reads_one_already_open_page(tmp_path):
    """The unit app.ingest.tamil_text actually calls: a single pymupdf.Page, not a whole
    file -- only the pages tamil_text_is_corrupted flags should ever pay OCR's cost."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=200)
    page.insert_text((60, 60), "Hello Page")
    try:
        text = ocr_read_page(page, lang="eng")
    finally:
        doc.close()
    assert "Hello" in text and "Page" in text
