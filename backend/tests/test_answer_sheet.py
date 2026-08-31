"""Entering and confirming one student's marks against a paper already mapped."""

from __future__ import annotations

import io

import pymupdf
import pytest
from sqlalchemy import select

MARK_X = 595 * 0.87


def _auth(school):
    return {"X-API-Key": school["api_key"]}


PAPER = [
    (60, 60, "This question paper contains 2 questions."),
    (60, 90, "SECTION A"),
    (60, 125, "1. Find the mean of the grouped data by the"),
    (60, 139, "step-deviation method, assumed mean 200."), (MARK_X, 125, "3"),
    (60, 180, "2. Prove that the tangent at any point of a"),
    (60, 194, "circle is perpendicular to the radius."), (MARK_X, 180, "5"),
]


@pytest.fixture
def mapped_paper(client, school, book):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text in PAPER:
        page.insert_text((x, y), text, fontsize=10)
    data = doc.tobytes()
    doc.close()

    created = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Answer sheet test", "total_marks": 8},
    )
    aid = created.json()["assessment_id"]
    client.post(
        f"/assessments/{aid}/scan", headers=_auth(school),
        files=[("files", ("p.pdf", io.BytesIO(data), "application/pdf"))],
    )
    client.post(f"/assessments/{aid}/scan/confirm", headers=_auth(school), json={})
    client.post(f"/assessments/{aid}/map", headers=_auth(school))
    return aid


@pytest.fixture
def student(school):
    """This suite seeds its own student. Reading one another suite happens to have created
    makes the result depend on collection order, which is not a property anyone chose."""
    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    existing = db.scalar(
        select(StudentProfile).where(
            StudentProfile.section_id == school["section_id"],
            StudentProfile.roll_no == "047",
        )
    )
    if existing is None:
        existing = StudentProfile(
            school_id=school["school_id"], section_id=school["section_id"],
            name="Answer sheet student", roll_no="047",
        )
        db.add(existing)
        db.commit()
    sid = existing.id
    db.close()
    return sid


def test_the_sheet_is_driven_by_the_paper_not_by_the_marks(client, school, mapped_paper, student):
    """A question with no mark yet is exactly what the person entering them is looking
    for. A screen built from the marks shows a complete-looking list missing the gaps."""
    body = client.get(
        f"/assessments/{mapped_paper}/answers/{student}", headers=_auth(school)
    ).json()
    assert body["questions"], "the paper's questions must appear before any mark exists"
    assert body["entered"] == 0
    assert body["remaining"] == len(body["questions"])
    assert all(q["marks"] is None for q in body["questions"])
    # Each row carries what the mark will mean, from the book.
    assert any(q["concept_family"] for q in body["questions"])


def test_confirming_writes_marks_and_reports_what_is_still_missing(
    client, school, mapped_paper, student
):
    sheet = client.get(
        f"/assessments/{mapped_paper}/answers/{student}", headers=_auth(school)
    ).json()
    first = sheet["questions"][0]

    out = client.post(
        f"/assessments/{mapped_paper}/answers/{student}/confirm",
        headers=_auth(school),
        json={"answers": [{"address": first["address"], "marks": 1}], "by": "Mrs Rani"},
    )
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["written"] == 1 and body["rejected"] == []
    assert body["scored"] == 1.0
    # Said rather than assumed: a total over a partial sheet reads exactly like a low score.
    assert body["complete"] is (body["remaining"] == 0)
    if len(sheet["questions"]) > 1:
        assert body["complete"] is False


def test_a_mark_above_what_the_question_is_worth_is_refused_not_clamped(
    client, school, mapped_paper, student
):
    """Clamping turns a typo into a plausible number nobody would question again."""
    sheet = client.get(
        f"/assessments/{mapped_paper}/answers/{student}", headers=_auth(school)
    ).json()
    q = sheet["questions"][0]

    out = client.post(
        f"/assessments/{mapped_paper}/answers/{student}/confirm",
        headers=_auth(school),
        json={"answers": [{"address": q["address"], "marks": q["max_marks"] + 5}]},
    ).json()
    assert out["written"] == 0
    assert "more than the" in out["rejected"][0]["reason"]


def test_the_unattempted_half_of_a_choice_is_recorded_as_not_offered(
    client, school, mapped_paper, student
):
    sheet = client.get(
        f"/assessments/{mapped_paper}/answers/{student}", headers=_auth(school)
    ).json()
    q = sheet["questions"][0]
    client.post(
        f"/assessments/{mapped_paper}/answers/{student}/confirm",
        headers=_auth(school),
        json={"answers": [{"address": q["address"], "state": "not_offered"}]},
    )
    after = client.get(
        f"/assessments/{mapped_paper}/answers/{student}", headers=_auth(school)
    ).json()
    row = next(r for r in after["questions"] if r["address"] == q["address"])
    assert row["state"] == "not_offered"
    assert row["marks"] is None


def test_a_teachers_confirmation_supersedes_an_automatic_reading(
    client, school, mapped_paper, student
):
    """teacher outranks page_ocr, so a correction always wins -- and the earlier reading
    stays in the log, because how a mark was arrived at is part of defending it."""
    from app.db import SessionLocal
    from app.models import MarkEvent, Question

    sheet = client.get(
        f"/assessments/{mapped_paper}/answers/{student}", headers=_auth(school)
    ).json()
    q = sheet["questions"][0]

    db = SessionLocal()
    question = db.scalar(
        select(Question).where(
            Question.assessment_id == mapped_paper, Question.address == q["address"]
        )
    )
    db.add(MarkEvent(
        assessment_id=mapped_paper, student_id=student, question_id=question.id,
        state="awarded", marks=3, source="page_ocr", confidence=0.6,
    ))
    db.commit()
    db.close()

    scanned = client.get(
        f"/assessments/{mapped_paper}/answers/{student}", headers=_auth(school)
    ).json()
    assert next(r for r in scanned["questions"] if r["address"] == q["address"])["source"] == "page_ocr"

    client.post(
        f"/assessments/{mapped_paper}/answers/{student}/confirm",
        headers=_auth(school), json={"answers": [{"address": q["address"], "marks": 1}]},
    )
    after = client.get(
        f"/assessments/{mapped_paper}/answers/{student}", headers=_auth(school)
    ).json()
    row = next(r for r in after["questions"] if r["address"] == q["address"])
    assert row["marks"] == 1.0 and row["source"] == "teacher"

    db = SessionLocal()
    kept = db.scalars(
        select(MarkEvent).where(
            MarkEvent.question_id == question.id, MarkEvent.student_id == student
        )
    ).all()
    db.close()
    assert any(e.source == "page_ocr" for e in kept), "the earlier reading must survive"


def test_a_sheet_for_an_unmapped_paper_says_what_to_do(client, school, student):
    created = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Never scanned", "total_marks": 5},
    )
    aid = created.json()["assessment_id"]

    out = client.get(f"/assessments/{aid}/answers/{student}", headers=_auth(school))
    assert out.status_code == 422
    assert "no mapped questions" in out.json()["detail"]


def test_the_paper_list_says_which_papers_can_take_an_answer_sheet(
    client, school, mapped_paper
):
    """A teacher picking a paper to enter marks against should not have to discover at the
    point of entry that it was never mapped."""
    created = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Not scanned yet", "total_marks": 5},
    ).json()["assessment_id"]

    rows = client.get("/assessments", headers=_auth(school)).json()["assessments"]
    by_id = {r["id"]: r for r in rows}

    assert by_id[mapped_paper]["stage"] == "mapped"
    assert by_id[mapped_paper]["questions"] > 0
    assert by_id[mapped_paper]["ready_for_answer_sheets"] is True

    assert by_id[created]["stage"] == "empty"
    assert by_id[created]["ready_for_answer_sheets"] is False
