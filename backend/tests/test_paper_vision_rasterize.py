"""rasterize_pdf feeds a scanned paper's pages to the vision model -- see paper_vision.py's
own docstring for why oversized, uncompressed pages are what turned into production's
"RequestTooLargeError: Error code: 413": a 300dpi PNG scan of even a modest paper routinely
exceeded Anthropic's 32MB request cap. These tests are the guardrail against that shape of
regression coming back.
"""

from __future__ import annotations

import pymupdf

from app.extraction.paper_vision import _VISION_LONG_EDGE_PX, rasterize_pdf


def _pdf_with_pages(count: int, *, width: float = 595, height: float = 842) -> bytes:
    doc = pymupdf.open()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8))
    pixmap.clear_with(180)
    for _ in range(count):
        page = doc.new_page(width=width, height=height)
        page.insert_image(pymupdf.Rect(0, 0, width, height), pixmap=pixmap)
    data = doc.tobytes()
    doc.close()
    return data


def test_pages_come_back_as_jpeg_not_png(tmp_path):
    """PNG's lossless compression does badly on photographic noise -- a scan or a phone
    photo of paper is exactly that -- and was the single biggest contributor to the
    oversized request that 413'd in production."""
    path = tmp_path / "scan.pdf"
    path.write_bytes(_pdf_with_pages(1))

    pages = rasterize_pdf(path)

    assert len(pages) == 1
    data, content_type = pages[0]
    assert content_type == "image/jpeg"
    assert data[:2] == b"\xff\xd8"  # a JPEG file's own magic bytes


def test_a_page_is_never_rendered_larger_than_what_the_model_actually_uses(tmp_path):
    """Anthropic downscales anything past ~1568px on the long edge before the model ever
    sees it -- rendering bigger than that buys nothing but bytes, which is exactly what
    caused the request to exceed Anthropic's own 32MB size cap for a normal paper."""
    path = tmp_path / "scan.pdf"
    path.write_bytes(_pdf_with_pages(1))

    (data, _), = rasterize_pdf(path)
    pixmap = pymupdf.Pixmap(data)
    assert max(pixmap.width, pixmap.height) <= _VISION_LONG_EDGE_PX + 1  # rounding


def test_a_multi_page_paper_stays_comfortably_under_anthropics_request_cap(tmp_path):
    """The actual regression: a paper with a realistic page count (CBSE Class X papers
    run up to ~20 pages) used to produce a base64 payload well past Anthropic's 32MB
    request-size limit at 300dpi PNG. Sized and compressed as they are here, even a long
    paper stays well inside it."""
    path = tmp_path / "scan.pdf"
    path.write_bytes(_pdf_with_pages(20))

    pages = rasterize_pdf(path)

    total_bytes = sum(len(data) for data, _ in pages)
    assert total_bytes < 10 * 1024 * 1024  # nowhere near the 32MB cap, even before base64
