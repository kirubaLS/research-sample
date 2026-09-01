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
