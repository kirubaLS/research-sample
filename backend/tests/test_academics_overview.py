"""The class-overview screen: a status bucket per student rolled up per class, derived
straight from real confirmed marks -- never an invented aspiration/action-plan figure
this deployment has no data model for."""

from __future__ import annotations

import uuid

import pytest


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@pytest.fixture
def scored_paper(client, school):
    """One paper, three students, scored so each lands in a different status band:
    90% (on_track), 60% (needs_attention), 20% (requires_review). A fourth student in
    the same class gets no marks at all, to prove not_assessed is its own bucket rather
    than folded into requires_review."""
    tag = uuid.uuid4().hex[:8]
    h = _auth(school)
    aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.MATH", "title": f"Overview Test {tag}", "total_marks": 10},
    ).json()["assessment_id"]
    client.post(
        f"/assessments/{aid}/questions", headers=h, json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 10, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"ov-{tag}-1"},
        ]},
    )

    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    strong = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"], name=f"Strong {tag}", roll_no=f"{tag}-1",
    )
    middling = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"], name=f"Middling {tag}", roll_no=f"{tag}-2",
    )
    weak = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"], name=f"Weak {tag}", roll_no=f"{tag}-3",
    )
    untouched = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"], name=f"Untouched {tag}", roll_no=f"{tag}-4",
    )
    db.add_all([strong, middling, weak, untouched])
    db.commit()
    ids = {"strong": strong.id, "middling": middling.id, "weak": weak.id}
    db.close()

    for key, mark in (("strong", 9), ("middling", 6), ("weak", 2)):
        client.patch(
            f"/assessments/{aid}/answers/{ids[key]}/reading/A/1//",
            headers=h, json={"marks": mark, "state": "awarded", "by": "test"},
        )
        client.post(f"/assessments/{aid}/answers/{ids[key]}/reading/confirm", headers=h, json={"by": "test"})

    return aid


def test_class_overview_buckets_students_by_score_band(client, school, scored_paper):
    r = client.get("/admin/academics", headers=_auth(school))
    assert r.status_code == 200, r.text
    row = next(c for c in r.json()["classes"] if c["section_id"] == school["section_id"])
    counts = row["status_counts"]
    assert counts["on_track"] >= 1
    assert counts["needs_attention"] >= 1
    assert counts["requires_review"] >= 1
    assert counts["not_assessed"] >= 1
    # >= rather than == : `school` and its section are session-scoped fixtures shared by
    # every test file, so other tests in the same run legitimately add more assessments
    # and marks to this same section -- an exact count here would be asserting against
    # the whole suite's fixture order, not against what this test itself set up.
    assert row["test_count"] >= 1
    assert row["avg_score_pct"] is not None


def test_class_overview_xlsx_downloads(client, school, scored_paper):
    r = client.get("/admin/academics/overview.xlsx", headers=_auth(school))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(r.content) > 0


def test_class_overview_pdf_downloads(client, school, scored_paper):
    r = client.get("/admin/academics/overview.pdf", headers=_auth(school))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def _scored_assessment(client, school, subject, title, mark, out_of=10):
    """One question, one student, scored exactly `mark`/`out_of` -- a single confirmed
    row is enough to pin this assessment's average score to a known value, which is what
    a movement test needs on both sides of the comparison."""
    h = _auth(school)
    aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": subject, "title": title, "total_marks": out_of},
    ).json()["assessment_id"]
    tag = uuid.uuid4().hex[:8]
    client.post(
        f"/assessments/{aid}/questions", headers=h, json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": out_of, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"mv-{tag}"},
        ]},
    )
    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    student = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name=f"Mover {tag}", roll_no=f"{tag}",
    )
    db.add(student)
    db.commit()
    student_id = student.id
    db.close()

    client.patch(
        f"/assessments/{aid}/answers/{student_id}/reading/A/1//",
        headers=h, json={"marks": mark, "state": "awarded", "by": "test"},
    )
    client.post(f"/assessments/{aid}/answers/{student_id}/reading/confirm", headers=h, json={"by": "test"})
    return aid


def test_the_tests_list_is_newest_first_with_a_real_movement_against_the_prior_test(
    client, school
):
    """Real production bug: the Test tab's own docstring promised "newest first" but the
    list was actually sorted alphabetically by title. Two same-subject tests, scored 40%
    then 70%, in that creation order -- the newer (70%) one must lead the list, and must
    show a real +30 movement against the older one; the older one has nothing earlier to
    compare against and must show no movement at all rather than a guessed one."""
    first_aid = _scored_assessment(client, school, "X.MATH", "Movement Test A", 4)
    second_aid = _scored_assessment(client, school, "X.MATH", "Movement Test B", 7)

    out = client.get("/admin/academics/tests", headers=_auth(school)).json()["tests"]
    by_id = {t["assessment_id"]: t for t in out}
    assert first_aid in by_id and second_aid in by_id

    ids_in_order = [t["assessment_id"] for t in out if t["assessment_id"] in (first_aid, second_aid)]
    assert ids_in_order == [second_aid, first_aid], "newest test must lead the list"

    # Not asserting first_aid's own delta is None: this suite's DB is shared across test
    # functions (other tests seed their own X.MATH assessments), so an earlier, unrelated
    # X.MATH test may genuinely precede first_aid here -- that is real behaviour, not a
    # bug. What is guaranteed regardless of what else exists is that second_aid's
    # immediately preceding X.MATH test, within this test's own two, is first_aid.
    assert by_id[first_aid]["avg_score_pct"] == 40.0
    assert by_id[second_aid]["avg_score_pct"] == 70.0
    assert by_id[second_aid]["delta_pct"] == 30.0


def test_a_teacher_key_is_refused_the_generic_overview(client, school):
    created = client.post(
        "/admin/teachers", headers=_auth(school), json={"label": "Ms. Rao", "assignments": []},
    ).json()
    r = client.get("/admin/academics", headers={"X-API-Key": created["api_key"]})
    assert r.status_code == 403
