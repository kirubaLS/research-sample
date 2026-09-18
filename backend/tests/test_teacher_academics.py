"""The teacher-scoped Overview/Test drill-down: same computations as the principal's
own app.api.academics, narrowed to exactly what a class or subject assignment covers --
never wider, no matter what a query string asks for."""

from __future__ import annotations

import uuid

import pytest


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@pytest.fixture
def teacher_scope_paper(client, school):
    """One Maths paper, two students (on_track and requires_review), plus a Science
    paper for the same two students -- enough to prove a subject-assigned teacher sees
    Maths and nothing of the Science paper, while a class-assigned teacher sees both."""
    tag = uuid.uuid4().hex[:8]
    h = _auth(school)
    math_aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.MATH", "title": f"Teacher Scope Maths {tag}", "total_marks": 10},
    ).json()["assessment_id"]
    client.post(
        f"/assessments/{math_aid}/questions", headers=h, json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 10, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"ts-{tag}-1",
             "chapter": "X.MATH.SAV", "curriculum_section": "12.1"},
        ]},
    )
    sci_aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.SCI", "title": f"Teacher Scope Science {tag}", "total_marks": 10},
    ).json()["assessment_id"]
    client.post(
        f"/assessments/{sci_aid}/questions", headers=h, json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 10, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"ts-sci-{tag}-1",
             "chapter": "X.MATH.SAV", "curriculum_section": "12.1"},
        ]},
    )

    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    strong = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"], name=f"Strong {tag}", roll_no=f"{tag}-1",
    )
    weak = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"], name=f"Weak {tag}", roll_no=f"{tag}-2",
    )
    db.add_all([strong, weak])
    db.commit()
    ids = {"strong": strong.id, "weak": weak.id}
    db.close()

    for aid in (math_aid, sci_aid):
        for key, mark in (("strong", 9), ("weak", 2)):
            client.patch(
                f"/assessments/{aid}/answers/{ids[key]}/reading/A/1//",
                headers=h, json={"marks": mark, "state": "awarded", "by": "test"},
            )
            client.post(f"/assessments/{aid}/answers/{ids[key]}/reading/confirm", headers=h, json={"by": "test"})

    return {"math_aid": math_aid, "sci_aid": sci_aid, "strong_id": ids["strong"], "weak_id": ids["weak"]}


def _subject_teacher(client, school, subject_code):
    created = client.post(
        "/admin/teachers", headers=_auth(school),
        json={"label": f"{subject_code} teacher", "assignments": [
            {"type": "subject", "section_id": school["section_id"], "subject_code": subject_code},
        ]},
    ).json()
    return {"X-API-Key": created["api_key"]}


def _class_teacher(client, school):
    created = client.post(
        "/admin/teachers", headers=_auth(school),
        json={"label": "Class teacher", "assignments": [
            {"type": "class", "section_id": school["section_id"]},
        ]},
    ).json()
    return {"X-API-Key": created["api_key"]}


def test_subject_teacher_overview_only_covers_their_own_subject(client, school, teacher_scope_paper):
    h = _subject_teacher(client, school, "X.MATH")
    r = client.get("/admin/teacher/academics", headers=h)
    assert r.status_code == 200, r.text
    classes = r.json()["classes"]
    assert len(classes) == 1
    assert classes[0]["subject_code"] == "X.MATH"
    # >= rather than == : `school`'s section is a session-scoped fixture shared by
    # every test file, so this count also includes every other test's own students in
    # the same section -- this fixture's own strong/weak pair is checked precisely via
    # the per-student view instead, in the tests below.
    assert classes[0]["status_counts"]["on_track"] >= 1
    assert classes[0]["status_counts"]["requires_review"] >= 1


def test_class_teacher_overview_covers_every_subject(client, school, teacher_scope_paper):
    h = _class_teacher(client, school)
    r = client.get("/admin/teacher/academics", headers=h)
    assert r.status_code == 200, r.text
    classes = r.json()["classes"]
    assert len(classes) == 1
    assert classes[0]["subject_code"] is None
    # Maths + Science combined -- >= 2 rather than == 2: `school`'s section is a
    # session-scoped fixture shared by every test file, so other tests' own papers on
    # this same section legitimately add to this class-assignment's (unscoped) count.
    assert classes[0]["test_count"] >= 2


def test_subject_teacher_class_students_cannot_be_widened_to_another_subject(
    client, school, teacher_scope_paper,
):
    h = _subject_teacher(client, school, "X.MATH")
    # asking for X.SCI explicitly must not widen a subject-scoped teacher's own read --
    # refused the same way every other out-of-scope read in this codebase is (404, not
    # a silent substitution), so a probe cannot tell "wrong subject" from "no such
    # section" either.
    mismatched = client.get(
        f"/admin/teacher/academics/{school['section_id']}/students",
        params={"subject_code": "X.SCI"}, headers=h,
    )
    assert mismatched.status_code == 404

    own_subject = client.get(
        f"/admin/teacher/academics/{school['section_id']}/students",
        params={"subject_code": "X.MATH"}, headers=h,
    )
    assert own_subject.status_code == 200, own_subject.text
    assert own_subject.json()["subject_code"] == "X.MATH"

    # omitting subject_code altogether still runs as the one subject this key holds
    no_filter = client.get(f"/admin/teacher/academics/{school['section_id']}/students", headers=h)
    assert no_filter.status_code == 200, no_filter.text
    assert no_filter.json()["subject_code"] == "X.MATH"


def test_teacher_class_students_refuses_a_section_not_held(client, school, teacher_scope_paper):
    from app.db import SessionLocal
    from app.models import Section

    db = SessionLocal()
    other_section = Section(school_id=school["school_id"], grade=11, name="Z")
    db.add(other_section)
    db.commit()
    other_section_id = other_section.id
    db.close()

    h = _subject_teacher(client, school, "X.MATH")
    r = client.get(f"/admin/teacher/academics/{other_section_id}/students", headers=h)
    assert r.status_code == 404


def test_subject_teacher_tests_list_excludes_the_other_subjects_paper(client, school, teacher_scope_paper):
    h = _subject_teacher(client, school, "X.MATH")
    r = client.get("/admin/teacher/academics/tests", headers=h)
    assert r.status_code == 200, r.text
    ids = {t["assessment_id"] for t in r.json()["tests"]}
    assert teacher_scope_paper["math_aid"] in ids
    assert teacher_scope_paper["sci_aid"] not in ids


def test_subject_teacher_cannot_read_the_other_subjects_test_summary(client, school, teacher_scope_paper):
    h = _subject_teacher(client, school, "X.MATH")
    r = client.get(f"/admin/teacher/academics/tests/{teacher_scope_paper['sci_aid']}", headers=h)
    assert r.status_code == 404

    ok = client.get(f"/admin/teacher/academics/tests/{teacher_scope_paper['math_aid']}", headers=h)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status_counts"]["on_track"] == 1
    assert ok.json()["status_counts"]["requires_review"] == 1


def test_a_principal_key_is_refused_the_teacher_scoped_routes(client, school, teacher_scope_paper):
    r = client.get("/admin/teacher/academics", headers=_auth(school))
    assert r.status_code == 403
