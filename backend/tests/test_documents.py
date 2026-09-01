"""The paper, the script and the report are kept, and joined to each other.

A mark on a report is a claim about a piece of paper. Storing only what was read off it
left every later question -- "is that really what question 14 said?", "show me his answer
sheet" -- unanswerable, which is the same as asking a parent to take our word for it.
"""

from __future__ import annotations

import io

import pytest
from sqlalchemy import select


def _auth(school):
    return {"X-API-Key": school["api_key"]}


PAGE = b"\xff\xd8\xff\xe0fake-jpeg-bytes-for-one-page"


@pytest.fixture
def student(school):
    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    existing = db.scalar(
        select(StudentProfile).where(
            StudentProfile.section_id == school["section_id"],
            StudentProfile.roll_no == "091",
        )
    )
    if existing is None:
        existing = StudentProfile(
            school_id=school["school_id"], section_id=school["section_id"],
            name="Document test student", roll_no="091",
        )
        db.add(existing)
        db.commit()
    sid = existing.id
    db.close()
    return sid


@pytest.fixture
def assessment(client, school):
    return client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Documents test", "total_marks": 8},
    ).json()["assessment_id"]


def _upload(client, school, assessment, student, pages):
    return client.post(
        f"/assessments/{assessment}/answers/{student}/pages",
        headers=_auth(school),
        files=[("files", (f"p{i}.jpg", io.BytesIO(p), "image/jpeg")) for i, p in enumerate(pages)],
    )


def test_an_answer_script_is_stored_page_by_page_and_read_back(
    client, school, assessment, student
):
    out = _upload(client, school, assessment, student, [PAGE, PAGE + b"2", PAGE + b"3"])
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["page_count"] == 3
    assert [p["index"] for p in body["pages"]] == [0, 1, 2]

    # Each page addressable on its own, so a viewer can page through a script rather than
    # pulling the whole thing.
    second = client.get(body["pages"][1]["url"], headers=_auth(school))
    assert second.status_code == 200
    assert second.content == PAGE + b"2"
    assert second.headers["content-type"].startswith("image/jpeg")


def test_a_rescan_supersedes_the_script_rather_than_sitting_beside_it(
    client, school, assessment, student
):
    """Two versions of one script with no way to tell which the marks came from is worse
    than either."""
    first = _upload(client, school, assessment, student, [PAGE]).json()
    second = _upload(client, school, assessment, student, [PAGE + b"new", PAGE + b"x"]).json()

    assert first["document_id"] != second["document_id"]
    listed = client.get(
        f"/assessments/{assessment}/documents?student_id={student}", headers=_auth(school)
    ).json()["documents"]
    assert len(listed) == 1 and listed[0]["document_id"] == second["document_id"]
    assert client.get(first["pages"][0]["url"], headers=_auth(school)).status_code == 404


def test_a_script_is_reachable_from_the_student_not_only_from_the_paper(
    client, school, assessment, student
):
    """The principal opens a student, not an assessment."""
    _upload(client, school, assessment, student, [PAGE])
    body = client.get(f"/students/{student}/documents", headers=_auth(school)).json()
    assert body["documents"]
    assert body["documents"][0]["assessment_title"] == "Documents test"


def test_another_schools_page_is_not_readable_with_a_leaked_page_url(
    client, school, assessment, student
):
    """Tenancy is checked on the document, so a page id on its own opens nothing."""
    from app.db import SessionLocal
    from app.models import School

    url = _upload(client, school, assessment, student, [PAGE]).json()["pages"][0]["url"]

    db = SessionLocal()
    other = db.scalar(select(School).where(School.name == "Other School"))
    if other is None:
        other = School(name="Other School", api_key="other-school-key", state="Tamil Nadu")
        db.add(other)
        db.commit()
    db.close()

    assert client.get(url, headers={"X-API-Key": "other-school-key"}).status_code == 404


def test_a_principal_can_read_a_script_but_not_upload_one(client, school, assessment, student):
    from app.db import SessionLocal
    from app.models import StaffKey

    db = SessionLocal()
    if db.scalar(select(StaffKey).where(StaffKey.api_key == "principal-doc-key")) is None:
        db.add(StaffKey(school_id=school["school_id"], api_key="principal-doc-key",
                        role="principal", label="Principal"))
        db.commit()
    db.close()
    head = {"X-API-Key": "principal-doc-key"}

    url = _upload(client, school, assessment, student, [PAGE]).json()["pages"][0]["url"]
    assert client.get(url, headers=head).status_code == 200
    assert client.get(f"/students/{student}/documents", headers=head).status_code == 200
    assert _upload(client, school, assessment, student, [PAGE]).status_code == 200

    refused = client.post(
        f"/assessments/{assessment}/answers/{student}/pages", headers=head,
        files=[("files", ("p.jpg", io.BytesIO(PAGE), "image/jpeg"))],
    )
    assert refused.status_code == 403


def test_an_empty_page_is_refused_rather_than_stored(client, school, assessment, student):
    out = client.post(
        f"/assessments/{assessment}/answers/{student}/pages", headers=_auth(school),
        files=[("files", ("blank.jpg", io.BytesIO(b""), "image/jpeg"))],
    )
    assert out.status_code == 422


def test_pages_are_written_to_the_object_store_not_into_the_database(
    client, school, assessment, student
):
    """A term of scripts is gigabytes. Keeping them as columns puts them in every backup,
    every restore and every replica of a database that is otherwise the size of the marks."""
    from app.db import SessionLocal
    from app.models import ScanPage

    body = _upload(client, school, assessment, student, [PAGE, PAGE + b"2"]).json()

    db = SessionLocal()
    rows = db.scalars(
        select(ScanPage).where(ScanPage.document_id == body["document_id"])
    ).all()
    stored = [(r.content, r.storage_key, r.sha256) for r in rows]
    db.close()

    assert len(stored) == 2
    for content, key, sha in stored:
        assert content is None, "the bytes must not be in the row"
        assert key and sha, "the row has to say where the bytes are, and what they were"

    # and it still reads back byte for byte
    assert client.get(body["pages"][0]["url"], headers=_auth(school)).content == PAGE


def test_a_page_written_before_the_move_is_still_readable(
    client, school, assessment, student
):
    """Rewriting a school's stored scripts to relocate them is a worse risk than reading
    two places, so a row from before the object store keeps working untouched."""
    from app.db import SessionLocal
    from app.models import ScanPage

    body = _upload(client, school, assessment, student, [PAGE]).json()

    db = SessionLocal()
    page = db.scalar(select(ScanPage).where(ScanPage.document_id == body["document_id"]))
    page.content = b"\xff\xd8older-page-kept-in-the-database"
    page.storage_key = None
    page.storage_uri = None
    db.commit()
    db.close()

    out = client.get(body["pages"][0]["url"], headers=_auth(school))
    assert out.status_code == 200
    assert out.content == b"\xff\xd8older-page-kept-in-the-database"


def test_superseding_a_script_does_not_leave_its_pages_in_the_store(
    client, school, assessment, student
):
    from app.storage import get_object_store

    first = _upload(client, school, assessment, student, [PAGE]).json()

    from app.db import SessionLocal
    from app.models import ScanPage

    db = SessionLocal()
    key = db.scalar(
        select(ScanPage.storage_key).where(ScanPage.document_id == first["document_id"])
    )
    db.close()
    assert get_object_store().exists(key)

    _upload(client, school, assessment, student, [PAGE + b"new"])
    assert not get_object_store().exists(key), "the superseded page is not left behind"


def test_a_page_whose_image_has_gone_says_so_rather_than_failing(
    client, school, assessment, student
):
    """On a host without durable storage the images do not survive a restart. A 500 would
    send somebody hunting a bug in the reader instead of reading the sentence."""
    from app.db import SessionLocal
    from app.models import ScanPage
    from app.storage import get_object_store

    body = _upload(client, school, assessment, student, [PAGE]).json()

    db = SessionLocal()
    key = db.scalar(
        select(ScanPage.storage_key).where(ScanPage.document_id == body["document_id"])
    )
    db.close()
    get_object_store().delete(key)

    out = client.get(body["pages"][0]["url"], headers=_auth(school))
    assert out.status_code == 410
    assert "no longer in storage" in out.json()["detail"]
    # and the marks are still there, which is the part that matters
    assert client.get(f"/students/{student}/documents", headers=_auth(school)).status_code == 200


def test_pages_can_be_kept_in_the_database_when_that_is_the_only_durable_thing(
    client, school, assessment, student
):
    """A free host has no disk and no bucket, and Postgres is the one thing that survives
    a restart. The bytes go in the row, and everything else behaves identically."""
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import ScanPage

    settings = get_settings()
    before = settings.storage_backend
    settings.storage_backend = "database"
    try:
        body = _upload(client, school, assessment, student, [PAGE, PAGE + b"2"]).json()

        db = SessionLocal()
        rows = db.scalars(
            select(ScanPage).where(ScanPage.document_id == body["document_id"])
        ).all()
        stored = [(r.content, r.storage_key, r.sha256) for r in rows]
        db.close()

        assert len(stored) == 2
        for content, key, sha in stored:
            assert content, "the bytes have to be in the row"
            assert key is None, "nothing was written to an object store"
            assert sha, "and the row still records what the bytes were"

        # served back byte for byte, from the same URL as any other page
        assert client.get(body["pages"][1]["url"], headers=_auth(school)).content == PAGE + b"2"
    finally:
        settings.storage_backend = before


def test_superseding_a_database_stored_script_removes_its_rows(
    client, school, assessment, student
):
    """Without an object store there is nothing to orphan, but the old rows still have to
    go: two versions of one script with no way to tell which the marks came from is the
    thing being prevented, and it has nothing to do with where the bytes live."""
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import ScanPage

    settings = get_settings()
    before = settings.storage_backend
    settings.storage_backend = "database"
    try:
        first = _upload(client, school, assessment, student, [PAGE]).json()
        _upload(client, school, assessment, student, [PAGE + b"new"])

        db = SessionLocal()
        left = db.scalars(
            select(ScanPage).where(ScanPage.document_id == first["document_id"])
        ).all()
        db.close()
        assert left == []
    finally:
        settings.storage_backend = before
