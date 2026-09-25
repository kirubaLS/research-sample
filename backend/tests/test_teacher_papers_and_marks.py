"""Teacher-scoped parity for the three principal screens (Papers, Enter Marks, Scan
Answer Sheets): a subject-assignment teacher gets working equivalents scoped to exactly
that subject (papers) or that section+subject (marks/gridsheets); a class-only teacher
gets none of it, matching teacher_can_enter_marks's existing rule."""

from __future__ import annotations

import uuid

import pytest


def _auth(school):
    return {"X-API-Key": school["api_key"]}


def _subject_teacher(client, school, subject_code, section_id=None):
    created = client.post(
        "/admin/teachers", headers=_auth(school),
        json={"label": f"{subject_code} teacher", "assignments": [
            {"type": "subject", "section_id": section_id or school["section_id"], "subject_code": subject_code},
        ]},
    ).json()
    return {"X-API-Key": created["api_key"]}


def _class_teacher(client, school, section_id=None):
    created = client.post(
        "/admin/teachers", headers=_auth(school),
        json={"label": "Class teacher", "assignments": [
            {"type": "class", "section_id": section_id or school["section_id"]},
        ]},
    ).json()
    return {"X-API-Key": created["api_key"]}


@pytest.fixture
def other_section(school):
    from app.db import SessionLocal
    from app.models import Section

    db = SessionLocal()
    sec = Section(school_id=school["school_id"], grade=10, name=f"Z{uuid.uuid4().hex[:6]}")
    db.add(sec)
    db.commit()
    section_id = sec.id
    db.close()
    return section_id


@pytest.fixture
def student(school):
    from app.db import SessionLocal
    from app.models import StudentProfile

    tag = uuid.uuid4().hex[:8]
    db = SessionLocal()
    s = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name=f"Papers Test {tag}", roll_no=f"pt-{tag}",
    )
    db.add(s)
    db.commit()
    student_id = s.id
    db.close()
    return student_id


# --- Papers: subject-scoped paper authoring -----------------------------------------


def test_teacher_can_create_and_edit_a_paper_for_their_own_subject(client, school):
    h = _subject_teacher(client, school, "X.MATH")
    tag = uuid.uuid4().hex[:8]
    r = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.MATH", "title": f"Teacher Paper {tag}", "total_marks": 10},
    )
    assert r.status_code == 200, r.text
    aid = r.json()["assessment_id"]

    r = client.patch(f"/assessments/{aid}", headers=h, json={"title": "Renamed"})
    assert r.status_code == 200, r.text

    r = client.get(f"/assessments/{aid}/scan", headers=h)
    assert r.status_code == 200, r.text


def test_teacher_cannot_create_a_paper_for_a_subject_they_do_not_hold(client, school):
    h = _subject_teacher(client, school, "X.MATH")
    r = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.SCI", "title": "Not Mine", "total_marks": 10},
    )
    assert r.status_code == 404


def test_teacher_cannot_touch_a_paper_from_a_subject_they_do_not_hold(client, school):
    principal = _auth(school)
    tag = uuid.uuid4().hex[:8]
    aid = client.post(
        "/assessments", headers=principal,
        json={"subject_code": "X.SCI", "title": f"Science Paper {tag}", "total_marks": 10},
    ).json()["assessment_id"]

    h = _subject_teacher(client, school, "X.MATH")
    assert client.patch(f"/assessments/{aid}", headers=h, json={"title": "x"}).status_code == 404
    assert client.get(f"/assessments/{aid}/scan", headers=h).status_code == 404
    assert client.post(f"/assessments/{aid}/map", headers=h).status_code == 404


def test_class_only_teacher_cannot_author_papers(client, school):
    h = _class_teacher(client, school)
    r = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.MATH", "title": "Nope", "total_marks": 10},
    )
    assert r.status_code == 404


def test_teacher_can_delete_a_paper_for_their_own_subject(client, school):
    h = _subject_teacher(client, school, "X.MATH")
    tag = uuid.uuid4().hex[:8]
    aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.MATH", "title": f"Delete Me {tag}", "total_marks": 10},
    ).json()["assessment_id"]

    r = client.delete(f"/assessments/{aid}", headers=h)
    assert r.status_code == 204, r.text
    assert client.get(f"/assessments/{aid}/scan", headers=h).status_code == 404


def test_teacher_cannot_delete_a_paper_from_a_subject_they_do_not_hold(client, school):
    principal = _auth(school)
    tag = uuid.uuid4().hex[:8]
    aid = client.post(
        "/assessments", headers=principal,
        json={"subject_code": "X.SCI", "title": f"Not Mine {tag}", "total_marks": 10},
    ).json()["assessment_id"]

    h = _subject_teacher(client, school, "X.MATH")
    assert client.delete(f"/assessments/{aid}", headers=h).status_code == 404
    # still there, refused not silently ignored
    assert client.get(f"/assessments/{aid}/scan", headers=principal).status_code == 200


def test_class_only_teacher_cannot_delete_a_paper(client, school):
    principal = _auth(school)
    tag = uuid.uuid4().hex[:8]
    aid = client.post(
        "/assessments", headers=principal,
        json={"subject_code": "X.MATH", "title": f"Class Teacher Cannot Delete {tag}", "total_marks": 10},
    ).json()["assessment_id"]

    h = _class_teacher(client, school)
    assert client.delete(f"/assessments/{aid}", headers=h).status_code == 404


def test_teacher_papers_list_is_scoped_to_held_subjects(client, school):
    principal = _auth(school)
    tag = uuid.uuid4().hex[:8]
    math_aid = client.post(
        "/assessments", headers=principal,
        json={"subject_code": "X.MATH", "title": f"List Maths {tag}", "total_marks": 10},
    ).json()["assessment_id"]
    client.post(
        "/assessments", headers=principal,
        json={"subject_code": "X.SCI", "title": f"List Science {tag}", "total_marks": 10},
    )

    h = _subject_teacher(client, school, "X.MATH")
    r = client.get("/admin/teacher/papers", headers=h)
    assert r.status_code == 200, r.text
    ids = {a["id"] for a in r.json()["assessments"]}
    assert math_aid in ids
    assert all(a["subject_code"] == "X.MATH" for a in r.json()["assessments"])


def test_class_only_teacher_papers_list_is_empty(client, school):
    h = _class_teacher(client, school)
    r = client.get("/admin/teacher/papers", headers=h)
    assert r.status_code == 200
    assert r.json()["assessments"] == []


# --- Enter Marks: section+subject scoped marks entry --------------------------------


@pytest.fixture
def mapped_paper(school):
    """A paper with one real Question a mark can be confirmed against -- built straight
    through the model layer, so this file does not depend on the vision-backed scan/map
    pipeline to test scope checks that sit above it."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Assessment, Question, TaxonomyNode

    tag = uuid.uuid4().hex[:8]
    db = SessionLocal()
    board_unit = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.U.MENSURATION"))
    family = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.VOLUME"))
    a = Assessment(school_id=school["school_id"], subject_code="X.MATH", title=f"Marks Paper {tag}", total_marks=10)
    db.add(a)
    db.flush()
    q = Question(
        assessment_id=a.id, address="A/1//", section="A", question_no="1",
        max_marks=10, board_unit_id=board_unit.id, concept_family_id=family.id,
        concept_variant=f"tp-{tag}", variant_hash=f"tp-{tag}-hash",
    )
    db.add(q)
    db.commit()
    aid = a.id
    db.close()
    return aid


def test_subject_teacher_can_enter_marks_for_their_own_section_and_subject(client, school, mapped_paper, student):
    h = _subject_teacher(client, school, "X.MATH")
    r = client.post(
        f"/assessments/{mapped_paper}/answers/{student}/confirm", headers=h,
        json={"answers": [{"address": "A/1//", "marks": 7, "state": "awarded"}], "by": "teacher"},
    )
    assert r.status_code == 200, r.text

    r = client.get(f"/assessments/{mapped_paper}/answers/{student}", headers=h)
    assert r.status_code == 200, r.text


def test_subject_teacher_is_refused_for_a_different_subject(client, school, mapped_paper, student):
    h = _subject_teacher(client, school, "X.SCI")
    r = client.post(
        f"/assessments/{mapped_paper}/answers/{student}/confirm", headers=h,
        json={"answers": [{"address": "A/1//", "marks": 7, "state": "awarded"}], "by": "teacher"},
    )
    assert r.status_code == 404


def test_subject_teacher_is_refused_for_a_different_section(client, school, other_section, mapped_paper):
    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    other_student = StudentProfile(
        school_id=school["school_id"], section_id=other_section,
        name="Other Section Student", roll_no=f"os-{uuid.uuid4().hex[:6]}",
    )
    db.add(other_student)
    db.commit()
    other_student_id = other_student.id
    db.close()

    # assigned to school["section_id"], not other_section
    h = _subject_teacher(client, school, "X.MATH")
    r = client.post(
        f"/assessments/{mapped_paper}/answers/{other_student_id}/confirm", headers=h,
        json={"answers": [{"address": "A/1//", "marks": 7, "state": "awarded"}], "by": "teacher"},
    )
    assert r.status_code == 404


def test_class_only_teacher_cannot_enter_marks(client, school, mapped_paper, student):
    h = _class_teacher(client, school)
    r = client.post(
        f"/assessments/{mapped_paper}/answers/{student}/confirm", headers=h,
        json={"answers": [{"address": "A/1//", "marks": 7, "state": "awarded"}], "by": "teacher"},
    )
    assert r.status_code == 404


def test_confirm_class_reading_is_scoped_to_the_teachers_own_section(client, school, other_section, mapped_paper):
    h = _subject_teacher(client, school, "X.MATH")
    r = client.post(
        f"/assessments/{mapped_paper}/sections/{school['section_id']}/reading/confirm-class",
        headers=h, json={"by": "teacher"},
    )
    assert r.status_code == 200, r.text

    r = client.post(
        f"/assessments/{mapped_paper}/sections/{other_section}/reading/confirm-class",
        headers=h, json={"by": "teacher"},
    )
    assert r.status_code == 404


# --- Scan Answer Sheets: gridsheet flow, section+subject scoped ---------------------


def _questions_csv(roll: str) -> bytes:
    return f"roll,A/1//\n{roll},7\n".encode()


@pytest.fixture
def grid_student(school, mapped_paper):
    from app.db import SessionLocal
    from app.models import StudentProfile

    roll = f"pt-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    s = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name="Grid Student", roll_no=roll,
    )
    db.add(s)
    db.commit()
    db.close()
    return mapped_paper, roll


def test_subject_teacher_can_upload_and_confirm_a_gridsheet_for_their_own_section(client, school, grid_student):
    aid, roll = grid_student
    h = _subject_teacher(client, school, "X.MATH")
    files = [("files", ("marks.csv", _questions_csv(roll), "text/csv"))]
    r = client.post(
        f"/assessments/{aid}/sections/{school['section_id']}/gridsheet/file", headers=h, files=files,
    )
    assert r.status_code == 201, r.text
    document_id = r.json()["document_id"]
    assert r.json()["clean"] == 1

    r = client.get(f"/assessments/{aid}/gridsheet/{document_id}", headers=h)
    assert r.status_code == 200, r.text

    r = client.post(
        f"/assessments/{aid}/gridsheet/{document_id}/confirm", headers=h, json={"by": "teacher"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["confirmed"] == [roll]


def test_subject_teacher_is_refused_gridsheet_upload_for_another_section(client, school, other_section, grid_student):
    aid, roll = grid_student
    h = _subject_teacher(client, school, "X.MATH")
    files = [("files", ("marks.csv", _questions_csv(roll), "text/csv"))]
    r = client.post(
        f"/assessments/{aid}/sections/{other_section}/gridsheet/file", headers=h, files=files,
    )
    assert r.status_code == 404


def test_gridsheet_document_scope_is_refused_for_a_different_subject_teacher(client, school, grid_student):
    aid, roll = grid_student
    owner = _subject_teacher(client, school, "X.MATH")
    files = [("files", ("marks.csv", _questions_csv(roll), "text/csv"))]
    document_id = client.post(
        f"/assessments/{aid}/sections/{school['section_id']}/gridsheet/file", headers=owner, files=files,
    ).json()["document_id"]

    other = _subject_teacher(client, school, "X.SCI")
    assert client.get(f"/assessments/{aid}/gridsheet/{document_id}", headers=other).status_code == 404
    assert client.post(
        f"/assessments/{aid}/gridsheet/{document_id}/confirm", headers=other, json={"by": "x"},
    ).status_code == 404


def test_deleting_a_paper_with_marks_and_a_judged_question_does_not_500(client, school, mapped_paper, student):
    """Two real, separate foreign-key bugs in delete_assessment's cleanup order, both
    live in production before this test existed:

    - MarkEvent.question_id is a hard (non-nullable) FK onto Question -- a real mark
      always names the question it was awarded on -- but MarkEvent was deleted AFTER
      Question in the cleanup loop, so any paper that had ever had a mark entered against
      it (i.e. almost any real paper) 500'd on delete with a bare foreign key violation.
    - QuestionJudgment (the Layer 2B review trail) is keyed on question_id with no
      cascade and was missing from the cleanup entirely -- any paper with at least one
      judged question failed the same way.

    Both are reproduced together here: a real confirmed mark (a real MarkEvent) plus a
    real QuestionJudgment row, then delete must return 204 like any other paper.
    """
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Question, QuestionJudgment

    h = _subject_teacher(client, school, "X.MATH")
    r = client.post(
        f"/assessments/{mapped_paper}/answers/{student}/confirm", headers=h,
        json={"answers": [{"address": "A/1//", "marks": 7, "state": "awarded"}], "by": "teacher"},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    q_id = db.execute(select(Question.id).where(Question.assessment_id == mapped_paper)).scalar_one()
    db.add(QuestionJudgment(
        question_id=q_id, field="chapter", value="X.MATH.U.MENSURATION",
        reviewer_id="reviewer-a",
    ))
    db.commit()
    db.close()

    r = client.delete(f"/assessments/{mapped_paper}", headers=_auth(school))
    assert r.status_code == 204, r.text


def test_teacher_can_read_their_own_section_cohort_report(client, school, mapped_paper, student):
    """/reports/cohort refuses every teacher key outright (require_reader) -- a real
    teacher hit that 403 from the Insights tab, which had no teacher-scoped route to call
    instead until now."""
    h = _subject_teacher(client, school, "X.MATH")
    assert client.post(
        f"/assessments/{mapped_paper}/answers/{student}/confirm", headers=h,
        json={"answers": [{"address": "A/1//", "marks": 7, "state": "awarded"}], "by": "teacher"},
    ).status_code == 200

    # The principal-only route still refuses a teacher key exactly as before.
    assert client.get(
        f"/reports/cohort/{mapped_paper}?section_id={school['section_id']}", headers=h,
    ).status_code == 403

    r = client.get(
        f"/reports/teacher/cohort/{mapped_paper}?section_id={school['section_id']}", headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["students_analysed"] >= 1


def test_teacher_cohort_report_is_refused_for_a_different_subject(client, school, mapped_paper, student):
    h = _subject_teacher(client, school, "X.SCI")
    r = client.get(
        f"/reports/teacher/cohort/{mapped_paper}?section_id={school['section_id']}", headers=h,
    )
    assert r.status_code == 404


def test_teacher_can_settle_a_needs_review_question_on_their_own_paper(client, school, mapped_paper):
    """POST /assessments/{id}/review/{question_id} used to require an admin/principal
    key (require_admin), silently refusing every teacher with 403 -- despite GET
    .../review (the review queue itself) already being teacher-reachable at
    require_paper_scope, the same scope as the rest of paper authoring. A teacher who can
    see a needs-review row could never actually settle it."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement

    db = SessionLocal()
    qid = db.scalar(select(Question.id).where(Question.assessment_id == mapped_paper))
    db.add(QuestionPlacement(
        question_id=qid, confidence=0.4, source="model",
        needs_review=True, reasoning="two chapters were close",
    ))
    db.commit()
    db.close()

    h = _subject_teacher(client, school, "X.MATH")

    queue = client.get(f"/assessments/{mapped_paper}/review", headers=h)
    assert queue.status_code == 200, queue.text
    assert queue.json()["pending"] == 1
    assert any(c["code"] == "X.MATH.SAV" for c in queue.json()["chapters"])

    r = client.post(
        f"/assessments/{mapped_paper}/review/{qid}", headers=h,
        json={
            "chapter_code": "X.MATH.SAV", "tier": "Applying",
            "reviewed_by": "Mrs Subject Teacher",
        },
    )
    assert r.status_code == 200, r.text

    after = client.get(f"/assessments/{mapped_paper}/review", headers=h).json()
    assert after["pending"] == 0, "settling a question must clear it from the queue"


def test_settling_a_question_is_still_refused_for_a_different_subject(client, school, mapped_paper):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement

    db = SessionLocal()
    qid = db.scalar(select(Question.id).where(Question.assessment_id == mapped_paper))
    db.add(QuestionPlacement(
        question_id=qid, confidence=0.4, source="model",
        needs_review=True, reasoning="two chapters were close",
    ))
    db.commit()
    db.close()

    h = _subject_teacher(client, school, "X.SCI")
    r = client.post(
        f"/assessments/{mapped_paper}/review/{qid}", headers=h,
        json={"chapter_code": "X.MATH.SAV", "reviewed_by": "Someone else's teacher"},
    )
    assert r.status_code == 404


# --- Exam cell: papers-and-marks rights across every subject, no assignment needed --


def _exam_cell_teacher(client, school):
    """An exam-cell key: role == teacher, exam_cell == True, holding zero
    TeacherAssignment rows -- built straight through the model layer since exam_cell is
    only ever set by the operator console (POST /platform/schools/{id}/keys), not by
    /admin/teachers, which a principal calls for their own school."""
    import secrets

    from app.db import SessionLocal
    from app.models import StaffKey

    db = SessionLocal()
    api_key = secrets.token_urlsafe(24)
    db.add(StaffKey(
        school_id=school["school_id"], api_key=api_key, role="teacher",
        label="Exam cell", exam_cell=True,
    ))
    db.commit()
    db.close()
    return {"X-API-Key": api_key}


def test_exam_cell_key_sees_every_subjects_papers(client, school, mapped_paper):
    h = _exam_cell_teacher(client, school)
    r = client.get("/admin/teacher/papers", headers=h)
    assert r.status_code == 200, r.text
    ids = {a["id"] for a in r.json()["assessments"]}
    assert mapped_paper in ids, "the exam cell holds no subject assignment but must still see every paper"


def test_exam_cell_key_whoami_reports_exam_cell_and_paper_rights(client, school):
    h = _exam_cell_teacher(client, school)
    r = client.get("/admin/me", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["exam_cell"] is True
    assert body["can"]["scan_papers"] is True
    assert body["can"]["enter_marks"] is True
    assert body["assignments"] == []


def test_exam_cell_key_can_enter_marks_with_no_assignment_at_all(client, school, mapped_paper, student):
    h = _exam_cell_teacher(client, school)
    r = client.post(
        f"/assessments/{mapped_paper}/answers/{student}/confirm", headers=h,
        json={"answers": [{"address": "A/1//", "marks": 7, "state": "awarded"}], "by": "exam cell"},
    )
    assert r.status_code == 200, r.text


def test_regular_subject_teacher_is_not_exam_cell(client, school):
    """A plain subject teacher -- the pre-existing case this flag must not widen -- still
    reports exam_cell: false, matching the assignment-scoped rights they actually hold."""
    h = _subject_teacher(client, school, "X.MATH")
    body = client.get("/admin/me", headers=h).json()
    assert body["exam_cell"] is False
