"""A page's bytes now live in the object store (app/storage.py), addressed by
ScanPage.storage_key, instead of in this database -- the move that lets a 30-day S3
lifecycle rule expire the raw scan while the ScannedQuestion/Mark rows it produced stay in
Postgres forever (see app/models/documents.py's own docstring). These tests are the
regression guard for that wiring: a page written today is served back correctly, an old
row that still only carries `content` keeps working with no backfill, and a page whose
object has genuinely expired fails as a clear 410 rather than a crash.
"""

from __future__ import annotations

import io

import pymupdf
import pytest
from sqlalchemy import select

from app.config import get_settings

MARK_X = 595 * 0.87

PAPER = [[
    (60, 60, "This question paper contains 1 questions."),
    (60, 90, "SECTION A"),
    (60, 120, "1. Find the mean of the grouped data."),
    (MARK_X, 120, "3"),
]]


def _paper_bytes() -> bytes:
    doc = pymupdf.open()
    for lines in PAPER:
        page = doc.new_page(width=595, height=842)
        for x, y, text in lines:
            page.insert_text((x, y), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@pytest.fixture
def assessment(client, school):
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Storage test", "total_marks": 8},
    )
    assert r.status_code == 200
    return r.json()["assessment_id"]


def _scan_document_id(assessment: str) -> str:
    from app.db import SessionLocal
    from app.models import ScanDocument

    db = SessionLocal()
    try:
        doc = db.scalar(
            select(ScanDocument).where(
                ScanDocument.assessment_id == assessment, ScanDocument.kind == "question_paper",
            )
        )
        assert doc is not None
        return doc.id
    finally:
        db.close()


def test_a_freshly_scanned_page_is_written_through_the_object_store_and_served_back(
    client, school, assessment,
):
    original = _paper_bytes()
    r = client.post(
        f"/assessments/{assessment}/scan", headers=_auth(school),
        files=[("files", ("paper.pdf", io.BytesIO(original), "application/pdf"))],
    )
    assert r.status_code == 201, r.text
    document_id = _scan_document_id(assessment)

    from app.db import SessionLocal
    from app.models import ScanPage

    db = SessionLocal()
    try:
        page = db.scalar(select(ScanPage).where(ScanPage.document_id == document_id, ScanPage.index == 0))
        assert page is not None
        assert page.storage_key, "a freshly written page should carry a storage_key"
        assert page.content is None, "a freshly written page should not duplicate bytes in Postgres"
    finally:
        db.close()

    served = client.get(f"/documents/{document_id}/pages/0", headers=_auth(school))
    assert served.status_code == 200, served.text
    assert served.content == original


def test_a_legacy_row_with_only_content_still_serves_with_no_backfill(client, school, assessment):
    """A row written before storage_key existed keeps working -- read_page_bytes falls
    back to `content` rather than requiring every old row to be migrated to S3 first."""
    original = _paper_bytes()
    r = client.post(
        f"/assessments/{assessment}/scan", headers=_auth(school),
        files=[("files", ("paper.pdf", io.BytesIO(original), "application/pdf"))],
    )
    assert r.status_code == 201, r.text
    document_id = _scan_document_id(assessment)

    from app.db import SessionLocal
    from app.models import ScanPage

    db = SessionLocal()
    try:
        page = db.scalar(select(ScanPage).where(ScanPage.document_id == document_id, ScanPage.index == 0))
        # Simulate a pre-migration row: bytes in `content`, no storage_key.
        page.content = original
        page.storage_key = None
        db.commit()
    finally:
        db.close()

    served = client.get(f"/documents/{document_id}/pages/0", headers=_auth(school))
    assert served.status_code == 200, served.text
    assert served.content == original


def test_a_page_whose_object_has_expired_is_a_clear_410_not_a_crash(client, school, assessment):
    """The expected shape once a 30-day S3 lifecycle rule has actually run: the row still
    exists (it names an object that is gone), and that has to read as "this image expired
    on schedule", not as an unhandled error."""
    r = client.post(
        f"/assessments/{assessment}/scan", headers=_auth(school),
        files=[("files", ("paper.pdf", io.BytesIO(_paper_bytes()), "application/pdf"))],
    )
    assert r.status_code == 201, r.text
    document_id = _scan_document_id(assessment)

    from app.db import SessionLocal
    from app.models import ScanPage
    from app.storage import get_object_store

    db = SessionLocal()
    try:
        page = db.scalar(select(ScanPage).where(ScanPage.document_id == document_id, ScanPage.index == 0))
        get_object_store().delete(page.storage_key)  # stand in for the lifecycle rule
    finally:
        db.close()

    served = client.get(f"/documents/{document_id}/pages/0", headers=_auth(school))
    assert served.status_code == 410, served.text
    assert "auto-deleted" in served.text
