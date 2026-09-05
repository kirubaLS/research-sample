"""Renaming and deleting a paper, and deleting a stored answer script."""

from __future__ import annotations

import pytest


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@pytest.fixture
def assessment(client, school):
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Scan test", "total_marks": 8},
    )
    assert r.status_code == 200
    return r.json()["assessment_id"]


def test_a_paper_can_be_renamed_before_its_scan_is_confirmed(client, school, assessment):
    r = client.patch(
        f"/assessments/{assessment}", headers=_auth(school),
        json={"title": "Cycle Test II", "paper_code": "30(C)"},
    )
    assert r.status_code == 200, r.text
    assert set(r.json()["changed"]) == {"title", "paper_code"}

    listed = client.get("/assessments", headers=_auth(school))
    row = next(a for a in listed.json()["assessments"] if a["id"] == assessment)
    assert row["title"] == "Cycle Test II"
    assert row["paper_code"] == "30(C)"


def test_renaming_is_refused_once_the_scan_is_confirmed(client, school, assessment):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Assessment

    db = SessionLocal()
    a = db.get(Assessment, assessment)
    a.scan_confirmed_at = "2026-01-01T00:00:00"
    db.commit()
    db.close()

    r = client.patch(f"/assessments/{assessment}", headers=_auth(school), json={"title": "x"})
    assert r.status_code == 409


def test_deleting_a_paper_removes_it(client, school, assessment):
    r = client.delete(f"/assessments/{assessment}", headers=_auth(school))
    assert r.status_code == 204, r.text

    listed = client.get("/assessments", headers=_auth(school))
    assert all(a["id"] != assessment for a in listed.json()["assessments"])

    again = client.delete(f"/assessments/{assessment}", headers=_auth(school))
    assert again.status_code == 404


def test_deleting_a_paper_that_has_been_scanned_and_mapped_leaves_nothing_behind(
    client, school,
):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import (
        Assessment,
        BookChunk,
        ChapterBoardUnit,
        Question,
        ScannedQuestion,
        TaxonomyNode,
    )

    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "To be deleted", "total_marks": 3},
    )
    assessment_id = r.json()["assessment_id"]

    db = SessionLocal()
    db.add(ScannedQuestion(
        assessment_id=assessment_id, address="1", question_no="1", max_marks=3,
        stem_text="Find the mean.", logical_page=1,
    ))
    chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.STATS"))
    unit = db.scalar(
        select(ChapterBoardUnit).where(ChapterBoardUnit.chapter_id == chapter.id)
    )
    family = TaxonomyNode(
        kind="concept_family", code="X.MATH.CF.TEST_DELETE_CASCADE", label="test",
        parent_id=chapter.id, path="X.MATH.CF.TEST_DELETE_CASCADE",
        curriculum_version=chapter.curriculum_version,
    )
    db.add(family)
    db.flush()
    db.add(Question(
        assessment_id=assessment_id, address="1", question_no="1", max_marks=3,
        stem_text="Find the mean.", stem_hash="h", chapter_id=chapter.id,
        board_unit_id=unit.board_unit_id, concept_family_id=family.id,
        concept_variant="Find the mean.", variant_hash="v", curriculum_section="13.1",
    ))
    db.commit()
    db.close()

    r = client.delete(f"/assessments/{assessment_id}", headers=_auth(school))
    assert r.status_code == 204, r.text

    db = SessionLocal()
    assert db.get(Assessment, assessment_id) is None
    assert not list(db.scalars(
        select(ScannedQuestion).where(ScannedQuestion.assessment_id == assessment_id)
    ))
    assert not list(db.scalars(
        select(Question).where(Question.assessment_id == assessment_id)
    ))
    db.close()


def test_deleting_a_document_removes_it_from_the_assessment(client, school, assessment):
    import pymupdf

    from app.db import SessionLocal
    from app.models import StudentProfile

    def _one_page() -> bytes:
        doc = pymupdf.open()
        page = doc.new_page(width=200, height=200)
        page.insert_text((20, 20), "a page")
        data = doc.tobytes()
        doc.close()
        return data

    db = SessionLocal()
    student = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name="Test Student", roll_no="99",
    )
    db.add(student)
    db.commit()
    student_id = student.id
    db.close()

    r = client.post(
        f"/assessments/{assessment}/answers/{student_id}/pages",
        headers=_auth(school),
        files={"files": ("page1.pdf", _one_page(), "application/pdf")},
    )
    assert r.status_code == 200, r.text
    document_id = r.json()["document_id"]

    d = client.delete(f"/documents/{document_id}", headers=_auth(school))
    assert d.status_code == 204, d.text

    listed = client.get(f"/assessments/{assessment}/documents", headers=_auth(school))
    assert all(doc["document_id"] != document_id for doc in listed.json()["documents"])
