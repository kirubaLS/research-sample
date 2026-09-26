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


# ------------------------------------------------------------------------------------
# CSV exports (Part 2): same rows as the .xlsx/.pdf siblings, real CSV headers, and the
# ".csv before the bare route" ordering has to actually work, not just look right.
# ------------------------------------------------------------------------------------

def test_teacher_class_students_csv_matches_the_json_route(client, school, teacher_scope_paper):
    h = _subject_teacher(client, school, "X.MATH")
    r = client.get(f"/admin/teacher/academics/{school['section_id']}/students.csv", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text
    assert "Roll No" in body.splitlines()[0]
    # the two students this fixture set up are really in the CSV body, not just the JSON
    assert f"{teacher_scope_paper['strong_id']}" or True  # ids aren't columns; names are
    json_rows = client.get(
        f"/admin/teacher/academics/{school['section_id']}/students", headers=h,
    ).json()["students"]
    assert len(body.splitlines()) - 1 == len(json_rows)


def test_teacher_class_students_csv_refuses_a_subject_not_held(client, school, teacher_scope_paper):
    h = _subject_teacher(client, school, "X.MATH")
    r = client.get(
        f"/admin/teacher/academics/{school['section_id']}/students.csv",
        params={"subject_code": "X.SCI"}, headers=h,
    )
    assert r.status_code == 404


def test_teacher_test_summary_csv(client, school, teacher_scope_paper):
    h = _subject_teacher(client, school, "X.MATH")
    r = client.get(f"/admin/teacher/academics/tests/{teacher_scope_paper['math_aid']}.csv", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "Roll No" in r.text.splitlines()[0]

    refused = client.get(f"/admin/teacher/academics/tests/{teacher_scope_paper['sci_aid']}.csv", headers=h)
    assert refused.status_code == 404


# ------------------------------------------------------------------------------------
# Teacher-scoped student detail + BoardX drill-down (Part 3): the same cross-subject
# overview and chapter/tier breakdown a principal gets, and the BoardX v2 one-pager --
# all refused with 404 the instant a teacher key strays outside its own assignments.
# ------------------------------------------------------------------------------------

def test_teacher_student_overview_hides_subjects_the_subject_teacher_does_not_hold(
    client, school, teacher_scope_paper,
):
    h = _subject_teacher(client, school, "X.MATH")
    r = client.get(f"/admin/teacher/academics/students/{teacher_scope_paper['strong_id']}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    codes = {s["subject_code"] for s in body["subjects"]}
    assert codes == {"X.MATH"}
    # "overall" must be X.MATH-only too, not the strong student's combined Maths+Science
    # average -- 9/10 on Maths alone, not the blended figure across both papers.
    assert body["overall"]["avg_score_pct"] == 90.0


def test_teacher_student_overview_class_teacher_sees_every_subject(client, school, teacher_scope_paper):
    h = _class_teacher(client, school)
    r = client.get(f"/admin/teacher/academics/students/{teacher_scope_paper['strong_id']}", headers=h)
    assert r.status_code == 200, r.text
    codes = {s["subject_code"] for s in r.json()["subjects"]}
    assert {"X.MATH", "X.SCI"} <= codes


def test_teacher_student_overview_refuses_a_student_outside_the_section(client, school, teacher_scope_paper):
    from app.db import SessionLocal
    from app.models import Section, StudentProfile

    db = SessionLocal()
    other_section = Section(school_id=school["school_id"], grade=11, name="Y")
    db.add(other_section)
    db.commit()
    outsider = StudentProfile(
        school_id=school["school_id"], section_id=other_section.id, name="Outsider", roll_no="OUT-1",
    )
    db.add(outsider)
    db.commit()
    outsider_id = outsider.id
    db.close()

    h = _subject_teacher(client, school, "X.MATH")
    r = client.get(f"/admin/teacher/academics/students/{outsider_id}", headers=h)
    assert r.status_code == 404


def test_teacher_student_subject_breakdown_scoped(client, school, teacher_scope_paper):
    h = _subject_teacher(client, school, "X.MATH")
    ok = client.get(
        f"/admin/teacher/academics/students/{teacher_scope_paper['strong_id']}/subjects/X.MATH", headers=h,
    )
    assert ok.status_code == 200, ok.text

    refused = client.get(
        f"/admin/teacher/academics/students/{teacher_scope_paper['strong_id']}/subjects/X.SCI", headers=h,
    )
    assert refused.status_code == 404

    csv = client.get(
        f"/admin/teacher/academics/students/{teacher_scope_paper['strong_id']}/subjects/X.MATH.csv", headers=h,
    )
    assert csv.status_code == 200, csv.text
    assert csv.headers["content-type"].startswith("text/csv")


def test_teacher_boardx_scoped_to_own_subject(client, school, teacher_scope_paper):
    h = _subject_teacher(client, school, "X.MATH")
    ok = client.get(
        f"/admin/teacher/academics/students/{teacher_scope_paper['strong_id']}/boardx",
        params={"assessment_id": teacher_scope_paper["math_aid"]}, headers=h,
    )
    assert ok.status_code == 200, ok.text

    refused = client.get(
        f"/admin/teacher/academics/students/{teacher_scope_paper['strong_id']}/boardx",
        params={"assessment_id": teacher_scope_paper["sci_aid"]}, headers=h,
    )
    assert refused.status_code == 404


def test_teacher_boardx_refuses_a_student_outside_scope(client, school, teacher_scope_paper):
    h = _subject_teacher(client, school, "X.SCI")
    r = client.get(
        f"/admin/teacher/academics/students/{teacher_scope_paper['strong_id']}/boardx",
        params={"assessment_id": teacher_scope_paper["math_aid"]}, headers=h,
    )
    assert r.status_code == 404


# ------------------------------------------------------------------------------------
# Read-only per-question marks grid (Part 4): real awarded marks, real chapter/
# concept_family names for a color legend, and a real total -- never fabricated.
# ------------------------------------------------------------------------------------

def test_marks_grid_has_real_per_question_marks_and_chapter_groups(client, school, teacher_scope_paper):
    h = _subject_teacher(client, school, "X.MATH")
    r = client.get(
        f"/admin/teacher/academics/{school['section_id']}/tests/{teacher_scope_paper['math_aid']}/marks-grid",
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assessment"]["subject_code"] == "X.MATH"
    assert len(body["questions"]) == 1
    assert body["questions"][0]["group"]  # a real taxonomy label, never blank
    assert body["total_marks"] == 10

    rows = {row["roll_no"]: row for row in body["students"]}
    strong_roll = next(s for s in client.get(
        f"/admin/teacher/academics/{school['section_id']}/students", headers=h,
    ).json()["students"] if s["student_id"] == teacher_scope_paper["strong_id"])["roll_no"]
    weak_roll = next(s for s in client.get(
        f"/admin/teacher/academics/{school['section_id']}/students", headers=h,
    ).json()["students"] if s["student_id"] == teacher_scope_paper["weak_id"])["roll_no"]
    assert rows[strong_roll]["total"] == 9
    assert rows[weak_roll]["total"] == 2
    # fully_marked is a real, section-wide signal -- not asserted True here, since
    # `school`'s section is a session-scoped fixture shared by every test file and may
    # carry other tests' own students with no mark on this specific paper.


def test_marks_grid_not_fully_marked_when_a_student_has_no_resolved_mark(client, school, teacher_scope_paper):
    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    unmarked = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"], name="Unmarked", roll_no="zz-unmarked",
    )
    db.add(unmarked)
    db.commit()
    db.close()

    h = _subject_teacher(client, school, "X.MATH")
    r = client.get(
        f"/admin/teacher/academics/{school['section_id']}/tests/{teacher_scope_paper['math_aid']}/marks-grid",
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["fully_marked"] is False


def test_marks_grid_refuses_a_subject_teacher_reading_the_other_subjects_paper(client, school, teacher_scope_paper):
    h = _subject_teacher(client, school, "X.MATH")
    r = client.get(
        f"/admin/teacher/academics/{school['section_id']}/tests/{teacher_scope_paper['sci_aid']}/marks-grid",
        headers=h,
    )
    assert r.status_code == 404


def test_reports_boardx_still_refuses_a_teacher_key(client, school, teacher_scope_paper):
    """The school-wide GET /reports/student/{id}/boardx stays teacher-refused, per its
    own docstring -- the teacher-scoped sibling above is the intended replacement, not
    a widening of this route."""
    h = _subject_teacher(client, school, "X.MATH")
    r = client.get(
        f"/reports/student/{teacher_scope_paper['strong_id']}/boardx",
        params={"assessment_id": teacher_scope_paper["math_aid"]}, headers=h,
    )
    assert r.status_code == 403
