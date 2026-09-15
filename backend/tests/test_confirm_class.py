"""Confirming a whole class's readings in one call -- the per-student-file counterpart to
gridsheets.py's confirm_gridsheet, for a class whose marks arrived as separate files
rather than one class photo. Only ever moves what is clean; a student still carrying a
problem is named and skipped, never guessed through.
"""

from __future__ import annotations

import io

import pytest
from sqlalchemy import select


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@pytest.fixture
def paper(client, school):
    aid = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Confirm class test", "total_marks": 5},
    ).json()["assessment_id"]
    out = client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 2, "board_unit": "X.MATH.U.STATSPROB",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"cc-{aid}-1"},
        ]},
    )
    assert out.status_code == 200, out.text
    return aid


@pytest.fixture
def two_students(client, school):
    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    ids = {}
    for roll, name in (("501", "Confirm Class A"), ("502", "Confirm Class B")):
        existing = db.scalar(
            select(StudentProfile).where(
                StudentProfile.section_id == school["section_id"], StudentProfile.roll_no == roll
            )
        )
        if existing is None:
            existing = StudentProfile(
                school_id=school["school_id"], section_id=school["section_id"],
                name=name, roll_no=roll,
            )
            db.add(existing)
            db.commit()
        ids[roll] = existing.id
    db.close()
    return ids


def _read(client, school, paper, student_id, data):
    return client.post(
        f"/assessments/{paper}/answers/{student_id}/read", headers=_auth(school),
        files=[("files", ("marks.csv", io.BytesIO(data), "text/csv"))],
    )


def test_confirm_class_moves_the_clean_student_and_skips_the_blocked_one(
    client, school, paper, two_students
):
    clean_id = two_students["501"]
    blocked_id = two_students["502"]

    ok = _read(client, school, paper, clean_id, b"Question,Marks\nQ1,1.5\n")
    assert ok.status_code == 201, ok.text
    # 5 is more than this question's max_marks of 2 -- stays blocked until edited.
    bad = _read(client, school, paper, blocked_id, b"Question,Marks\nQ1,5\n")
    assert bad.status_code == 201, bad.text

    out = client.post(
        f"/assessments/{paper}/sections/{school['section_id']}/reading/confirm-class",
        headers=_auth(school), json={"by": "Mrs Rani"},
    )
    assert out.status_code == 200, out.text
    body = out.json()
    assert [c["student_id"] for c in body["confirmed"]] == [clean_id]
    assert [s["student_id"] for s in body["skipped"]] == [blocked_id]

    from app.db import SessionLocal
    from app.models import MarkEvent, ProposedMark

    db = SessionLocal()
    clean_events = db.scalars(select(MarkEvent).where(MarkEvent.student_id == clean_id)).all()
    blocked_events = db.scalars(select(MarkEvent).where(MarkEvent.student_id == blocked_id)).all()
    blocked_still_proposed = db.scalars(
        select(ProposedMark).where(ProposedMark.student_id == blocked_id)
    ).all()
    db.close()
    assert len(clean_events) == 1
    assert blocked_events == []
    assert len(blocked_still_proposed) == 1, "a blocked row must not be silently dropped either"


def test_confirm_class_requires_a_name(client, school, paper, two_students):
    out = client.post(
        f"/assessments/{paper}/sections/{school['section_id']}/reading/confirm-class",
        headers=_auth(school), json={"by": ""},
    )
    assert out.status_code == 422, out.text
