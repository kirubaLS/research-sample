"""Exam days: scheduling one before any paper exists, attaching real papers to it, and
the section x subject grid computed from the marks those papers actually carry."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest


def _auth(school):
    return {"X-API-Key": school["api_key"]}


def _paper(client, school, subject, title, marks_by_student, *, exam_id=None):
    """A one-question, 10-mark paper with the given marks awarded per student id."""
    tag = uuid.uuid4().hex[:8]
    h = _auth(school)
    body = {"subject_code": subject, "title": title, "total_marks": 10}
    if exam_id:
        body["exam_id"] = exam_id
    r = client.post("/assessments", headers=h, json=body)
    assert r.status_code == 200, r.text
    aid = r.json()["assessment_id"]
    r = client.post(f"/assessments/{aid}/questions", headers=h, json={"questions": [
        {"section": "A", "question_no": "1", "max_marks": 10, "board_unit": "X.MATH.U.MENSURATION",
         "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"ex-{tag}",
         "chapter": "X.MATH.SAV", "curriculum_section": "13.1"},
    ]})
    assert r.status_code == 200, r.text
    for sid, mark in marks_by_student.items():
        client.patch(
            f"/assessments/{aid}/answers/{sid}/reading/A/1//",
            headers=h, json={"marks": mark, "state": "awarded", "by": "test"},
        )
        client.post(f"/assessments/{aid}/answers/{sid}/reading/confirm", headers=h, json={"by": "test"})
    return aid


@pytest.fixture
def students(school):
    from app.db import SessionLocal
    from app.models import StudentProfile

    tag = uuid.uuid4().hex[:8]
    db = SessionLocal()
    a = StudentProfile(school_id=school["school_id"], section_id=school["section_id"], name=f"A {tag}", roll_no=f"{tag}-1")
    b = StudentProfile(school_id=school["school_id"], section_id=school["section_id"], name=f"B {tag}", roll_no=f"{tag}-2")
    db.add_all([a, b])
    db.commit()
    ids = [a.id, b.id]
    db.close()
    return ids


def _find(items, key, value):
    return next((i for i in items if i[key] == value), None)


def test_a_scheduled_exam_with_no_paper_is_upcoming(client, school):
    when = date.today() + timedelta(days=6)
    r = client.post("/admin/exams", headers=_auth(school), json={"name": "Quarterly Exam", "scheduled_date": when.isoformat()})
    assert r.status_code == 200, r.text
    exam_id = r.json()["id"]

    body = client.get("/admin/exams", headers=_auth(school)).json()
    up = _find(body["upcoming"], "id", exam_id)
    assert up is not None
    assert up["name"] == "Quarterly Exam"
    assert up["scheduled_date"] == when.isoformat()
    assert up["status"] == "Scheduled"
    assert up["days_away"] == 6
    assert _find(body["conducted"], "id", exam_id) is None


def test_a_past_exam_with_no_marks_awaits_marks_rather_than_being_upcoming(client, school):
    when = date.today() - timedelta(days=3)
    exam_id = client.post("/admin/exams", headers=_auth(school), json={"name": "Missed", "scheduled_date": when.isoformat()}).json()["id"]
    body = client.get("/admin/exams", headers=_auth(school)).json()
    assert _find(body["upcoming"], "id", exam_id) is None
    assert _find(body["awaiting_marks"], "id", exam_id)["status"] == "Awaiting marks"


def test_create_exam_rejects_a_blank_name(client, school):
    r = client.post("/admin/exams", headers=_auth(school), json={"name": "   ", "scheduled_date": "2026-10-01"})
    assert r.status_code == 422


def test_papers_attached_to_an_exam_roll_up_into_a_section_by_subject_grid(client, school, students):
    h = _auth(school)
    exam_id = client.post("/admin/exams", headers=h, json={
        "name": "Unit Test 2", "scheduled_date": (date.today() - timedelta(days=1)).isoformat(),
    }).json()["id"]
    a, b = students
    # Maths created already inside the exam; Science created standalone then attached
    math = _paper(client, school, "X.MATH", "UT2 Maths", {a: 9, b: 7}, exam_id=exam_id)
    sci = _paper(client, school, "X.SCI", "UT2 Science", {a: 5, b: 3})
    r = client.post(f"/admin/exams/{exam_id}/papers", headers=h, json={"assessment_id": sci})
    assert r.status_code == 200, r.text
    assert r.json()["paper_count"] == 2

    body = client.get("/admin/exams", headers=h).json()
    assert _find(body["upcoming"], "id", exam_id) is None
    exam = _find(body["conducted"], "id", exam_id)
    assert exam["kind"] == "exam" and exam["name"] == "Unit Test 2"
    cells = {c["subject_code"]: c for c in exam["grid"] if c["section_id"] == school["section_id"]}
    assert cells["X.MATH"]["avg_score_pct"] == 80.0   # 16/20
    assert cells["X.SCI"]["avg_score_pct"] == 40.0    # 8/20
    assert cells["X.MATH"]["assessment_ids"] == [math]
    assert exam["school_avg_pct"] == 60.0             # 24/40, not a mean of means
    # attached papers no longer show as standalone entries
    assert _find(body["conducted"], "id", sci) is None
    # the school fixture is shared across tests, so other tests' marks may hold an even
    # weaker subject -- but nothing weaker than this exam's own Science can be skipped
    assert body["weakest_subject"]["avg_score_pct"] <= 40.0


def test_vs_last_compares_against_the_previous_conducted_exam(client, school, students):
    h = _auth(school)
    a, b = students
    first = client.post("/admin/exams", headers=h, json={"name": "UT1", "scheduled_date": "2026-07-01"}).json()["id"]
    second = client.post("/admin/exams", headers=h, json={"name": "UT2", "scheduled_date": "2026-08-14"}).json()["id"]
    _paper(client, school, "X.MATH", "UT1 Maths", {a: 5, b: 5}, exam_id=first)
    _paper(client, school, "X.MATH", "UT2 Maths", {a: 8, b: 6}, exam_id=second)
    body = client.get("/admin/exams", headers=h).json()
    latest = _find(body["conducted"], "id", second)
    assert latest["previous"]["id"] == first
    assert latest["delta_pct"] == 20.0
    assert _find(body["conducted"], "id", first)["delta_pct"] is None


def test_standalone_papers_still_appear_and_existing_endpoints_are_unchanged(client, school, students):
    h = _auth(school)
    a, _ = students
    aid = _paper(client, school, "X.MATH", "Standalone", {a: 6})
    body = client.get("/admin/exams", headers=h).json()
    entry = _find(body["conducted"], "id", aid)
    assert entry["kind"] == "paper" and entry["name"] == "Standalone" and entry["school_avg_pct"] == 60.0
    tests = client.get("/admin/academics/tests", headers=h).json()["tests"]
    assert _find(tests, "assessment_id", aid)["avg_score_pct"] == 60.0


def test_attach_refuses_an_unknown_exam_or_paper(client, school):
    h = _auth(school)
    r = client.post("/admin/exams/nope/papers", headers=h, json={"assessment_id": "x"})
    assert r.status_code == 404
    exam_id = client.post("/admin/exams", headers=h, json={"name": "X", "scheduled_date": "2026-12-01"}).json()["id"]
    r = client.post(f"/admin/exams/{exam_id}/papers", headers=h, json={"assessment_id": "missing"})
    assert r.status_code == 404
    r = client.post("/assessments", headers=h, json={"subject_code": "X.MATH", "title": "t", "exam_id": "missing"})
    assert r.status_code == 404
