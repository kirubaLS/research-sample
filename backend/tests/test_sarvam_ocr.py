"""app.ingest.sarvam_ocr: the page-batching that keeps a job under Sarvam's own 10-page
limit, and the failure modes around a job's async lifecycle.

No real API calls -- these test the parts that don't need one: splitting a book into
batches, and how a job's terminal states and missing output are turned into errors.
"""

from __future__ import annotations

import pytest

from app.ingest.sarvam_ocr import (
    MAX_PAGES_PER_JOB,
    _split_into_batches,
    sarvam_read_text,
)


def _pdf_with_pages(n: int) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for _ in range(n):
        doc.new_page(width=100, height=100)
    data = doc.tobytes()
    doc.close()
    return data


def test_a_book_under_the_page_limit_is_a_single_batch():
    batches = _split_into_batches(_pdf_with_pages(5), MAX_PAGES_PER_JOB)
    assert len(batches) == 1


def test_a_book_over_the_page_limit_is_split_at_the_limit():
    """23 pages, a 10-page limit: 10 + 10 + 3, not one oversized job Sarvam would 400 on."""
    import pymupdf

    batches = _split_into_batches(_pdf_with_pages(23), MAX_PAGES_PER_JOB)
    page_counts = []
    for batch in batches:
        with pymupdf.open(stream=batch, filetype="pdf") as doc:
            page_counts.append(doc.page_count)
    assert page_counts == [10, 10, 3]


def test_no_api_key_is_a_named_failure_not_a_silent_one():
    with pytest.raises(ValueError, match="Sarvam API key"):
        sarvam_read_text(_pdf_with_pages(1), api_key="")
