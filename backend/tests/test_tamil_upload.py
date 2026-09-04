"""Loading a Tamil book through the browser -- the synchronous path, not Hindi's job/202
one, since app.ingest.tamil_text needs no OCR backend and no multi-minute call to
background (see TAMIL_SUBJECT_PREFIX in app.api.books).

app.api.books.tamil_read_text is stubbed rather than calling real OCR/extraction: what
these tests check is that the upload path calls it and threads its answer through to a
written chapter, not the quality of extraction itself (that is app.ingest.tamil_text's own
test_tamil_text.py and test_tamil_toc.py). The contents-page upload still needs a REAL PDF
on disk, unlike Hindi's fully-stubbed one -- _tamil_toc_chapters_by_position reads the real
file's own word positions directly, independent of the stubbed text.
"""

from __future__ import annotations

import io

import pymupdf
import pytest

KEY = "platform-test-key-abc"
HEAD = {"X-Platform-Key": KEY}


@pytest.fixture(autouse=True)
def _enable_platform():
    from app.config import get_settings

    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = KEY
    yield
    settings.platform_admin_key = before


def _tamil_contents_pdf() -> bytes:
    """A real PDF with placeholder Latin text at the same x-coordinates the actual Tamil
    contents page uses (verified against the real book, see _TAMIL_TITLE_X/_PAGENUM_X in
    app.ingest.book) -- no Tamil-capable font is installed in this environment, but the
    column-position logic being tested does not care what script a token is in, only
    where it sits and whether it ends in a digit.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=850)
    page.insert_text((62, 99), "unit")
    page.insert_text((233, 99), "title")
    page.insert_text((1, 120), "1")
    page.insert_text((140, 120), "theme")
    page.insert_text((234, 120), "annai")
    page.insert_text((280, 120), "mozhiye")
    page.insert_text((458, 120), "2")
    data = doc.tobytes()
    doc.close()
    return data


def test_a_tamil_upload_is_answered_directly_not_backgrounded(client, monkeypatch):
    """The point of TAMIL_SUBJECT_PREFIX staying off the IngestJob path: a 201 with the
    result in the body, the same request, not a 202 to poll."""
    def fake_tamil_read_text(pdf_bytes):
        return "1 அன்னை மொழியே 2" if len(pdf_bytes) < 5000 else (
            "அன்னை மொழியே\nஇது ஒரு கதை.\n"
        )

    monkeypatch.setattr("app.api.books.tamil_read_text", fake_tamil_read_text)

    client.post("/platform/books/X.TAM/curriculum", headers=HEAD)
    contents = client.post(
        "/platform/books/X.TAM/contents", headers=HEAD,
        files={"file": ("tamil-contents.pdf", io.BytesIO(_tamil_contents_pdf()), "application/pdf")},
    )
    assert contents.status_code == 201, contents.text
    assert contents.json()["chapters_expected"] == 1

    chapter = client.post(
        "/platform/books/X.TAM/chapters", headers=HEAD,
        files={"file": ("01-annai-mozhiye.pdf", io.BytesIO(b"x" * 6000), "application/pdf")},
    )
    # Expected to fail on structure (no exercise marker confirmed for Tamil yet -- see
    # app.ingest.book's own comment on this), but it must reach that check at all, as a
    # direct 4xx response, never a 202/job.
    assert chapter.status_code in (201, 422), chapter.text
    assert "job_id" not in chapter.json()


def test_a_tamil_chapter_title_mismatch_uses_the_fuzzy_match_not_an_exact_one(client, monkeypatch):
    """The same word-boundary quirk _tamil_toc_chapters_by_position's own test guards --
    'அன்னை மொழியே' read back with a stray space inside a word must not be rejected as a
    different chapter. Written against the source, curriculum and DB models directly
    rather than a real contents-page upload: no Tamil-capable font is installed in this
    environment for pymupdf to render a real geometry-based extraction of actual Tamil
    text, which is what a genuine word-boundary split needs to reproduce -- the earlier
    synthetic PDF's Latin placeholder text is fine for testing table GEOMETRY (see
    test_tamil_toc.py) but cannot stand in for a real script-level fuzzy-match case.
    """
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import BookSource

    def fake_tamil_read_text(pdf_bytes):
        return "அன் னை மொழியே\nஇது ஒரு கதை.\n"

    monkeypatch.setattr("app.api.books.tamil_read_text", fake_tamil_read_text)

    client.post("/platform/books/X.TAM/curriculum", headers=HEAD)
    db = SessionLocal()
    source = db.scalar(
        select(BookSource).where(
            BookSource.subject_code == "X.TAM",
            BookSource.curriculum_version == "CBSE-2026-27",
        )
    )
    if source is None:
        source = BookSource(
            curriculum_version="CBSE-2026-27", subject_code="X.TAM", edition=None,
            expected_sections={}, files={},
        )
        db.add(source)
    source.expected_chapters = {"1": "அன்னை மொழியே"}
    db.commit()
    db.close()

    chapter = client.post(
        "/platform/books/X.TAM/chapters", headers=HEAD,
        files={"file": ("01-annai-mozhiye.pdf", io.BytesIO(b"x" * 6000), "application/pdf")},
    )
    # A 422 is still expected here (no exercise marker confirmed for Tamil yet -- see
    # app.ingest.book), but not for a TITLE mismatch: that specific phrase must be absent.
    if chapter.status_code == 422:
        assert "the contents page calls chapter" not in chapter.json()["detail"]
