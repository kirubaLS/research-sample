# ruff: noqa: F811 -- fixtures imported from test_teacher_papers_and_marks
"""teacher_any_subject_uploads: with one common teacher key and one common dashboard, any
teacher may upload and enter marks for any section and subject of their own school -- and
never of another school. The default (off) keeps the assignment rule; its tests live in
test_teacher_papers_and_marks.py."""

from __future__ import annotations

import uuid

import pytest

from app.config import get_settings
from tests.test_teacher_papers_and_marks import (  # noqa: F401 -- fixtures
    _class_teacher,
    _questions_csv,
    _subject_teacher,
    grid_student,
    mapped_paper,
    other_section,
    student,
)

CONFIRM = {"answers": [{"address": "A/1//", "marks": 7, "state": "awarded"}], "by": "teacher"}


@pytest.fixture
def open_scope(monkeypatch):
    monkeypatch.setattr(get_settings(), "teacher_any_subject_uploads", True)


def _student_in(school, section_id):
    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    s = StudentProfile(school_id=school["school_id"], section_id=section_id,
                       name="Open Scope", roll_no=f"os-{uuid.uuid4().hex[:6]}")
    db.add(s)
    db.commit()
    sid = s.id
    db.close()
    return sid


def test_the_setting_defaults_off():
    assert get_settings().teacher_any_subject_uploads is False


def test_off_a_teacher_of_another_subject_is_still_refused(client, school, mapped_paper, student):
    h = _subject_teacher(client, school, "X.SCI")
    r = client.post(f"/assessments/{mapped_paper}/answers/{student}/confirm", headers=h, json=CONFIRM)
    assert r.status_code == 404


def test_a_teacher_of_another_subject_can_enter_marks(client, school, open_scope, mapped_paper, student):
    h = _subject_teacher(client, school, "X.SCI")
    r = client.post(f"/assessments/{mapped_paper}/answers/{student}/confirm", headers=h, json=CONFIRM)
    assert r.status_code == 200, r.text
    assert client.get(f"/assessments/{mapped_paper}/answers/{student}", headers=h).status_code == 200


def test_a_class_only_teacher_can_enter_marks(client, school, open_scope, mapped_paper, student):
    h = _class_teacher(client, school)
    r = client.post(f"/assessments/{mapped_paper}/answers/{student}/confirm", headers=h, json=CONFIRM)
    assert r.status_code == 200, r.text


def test_a_teacher_can_enter_marks_for_another_section_of_their_school(
    client, school, open_scope, other_section, mapped_paper,
):
    h = _subject_teacher(client, school, "X.MATH")
    other = _student_in(school, other_section)
    r = client.post(f"/assessments/{mapped_paper}/answers/{other}/confirm", headers=h, json=CONFIRM)
    assert r.status_code == 200, r.text


def test_whoami_says_a_class_only_teacher_may_enter_marks(client, school, open_scope):
    h = _class_teacher(client, school)
    assert client.get("/admin/me", headers=h).json()["can"]["enter_marks"] is True


def test_whoami_off_keeps_a_class_only_teacher_read_only(client, school):
    h = _class_teacher(client, school)
    assert client.get("/admin/me", headers=h).json()["can"]["enter_marks"] is False


def test_any_teacher_can_upload_and_confirm_an_answer_grid_for_any_section_and_subject(
    client, school, open_scope, other_section, grid_student,
):
    aid, roll = grid_student
    h = _subject_teacher(client, school, "X.SCI")                 # not the paper's subject
    files = [("files", ("marks.csv", _questions_csv(roll), "text/csv"))]
    r = client.post(
        f"/assessments/{aid}/sections/{school['section_id']}/gridsheet/file", headers=h, files=files,
    )
    assert r.status_code == 201, r.text
    document_id = r.json()["document_id"]
    other = _class_teacher(client, school)                        # a different teacher entirely
    assert client.get(f"/assessments/{aid}/gridsheet/{document_id}", headers=other).status_code == 200
    r = client.post(f"/assessments/{aid}/gridsheet/{document_id}/confirm", headers=other,
                    json={"by": "teacher"})
    assert r.status_code == 200, r.text
    # another section of the same school is open too (the roll simply is not on it)
    r = client.post(f"/assessments/{aid}/sections/{other_section}/gridsheet/file", headers=h, files=files)
    assert r.status_code != 404


def test_another_schools_section_is_never_reachable(client, school, open_scope, grid_student):
    from app.db import SessionLocal
    from app.models import School, Section

    aid, roll = grid_student
    db = SessionLocal()
    rival = School(name="Rival School", api_key=f"rival-{uuid.uuid4().hex}", state="Tamil Nadu",
                   training_consent="training_permitted", hidden_from_directory=False)
    db.add(rival)
    db.flush()
    foreign = Section(school_id=rival.id, grade=10, name="Q")
    db.add(foreign)
    db.commit()
    foreign_id = foreign.id
    db.close()
    h = _class_teacher(client, school)
    files = [("files", ("marks.csv", _questions_csv(roll), "text/csv"))]
    r = client.post(f"/assessments/{aid}/sections/{foreign_id}/gridsheet/file", headers=h, files=files)
    assert r.status_code == 404
    missing = f"/assessments/{aid}/sections/{uuid.uuid4()}/gridsheet/file"
    assert client.post(missing, headers=h, files=files).status_code == 404


def test_a_common_key_is_offered_every_section_and_may_read_any_roster_of_its_school(
    client, school, open_scope, other_section,
):
    h = _class_teacher(client, school)
    ids = {s["section_id"] for s in client.get("/admin/teacher/sections", headers=h).json()["sections"]}
    assert {school["section_id"], other_section} <= ids
    assert client.get(f"/admin/teacher/sections/{other_section}/students", headers=h).status_code == 200


def test_off_a_class_teacher_still_sees_only_their_own_sections(client, school, other_section):
    h = _class_teacher(client, school)
    ids = {s["section_id"] for s in client.get("/admin/teacher/sections", headers=h).json()["sections"]}
    assert other_section not in ids
    assert client.get(f"/admin/teacher/sections/{other_section}/students", headers=h).status_code == 404


def test_another_schools_roster_is_never_readable(client, school, open_scope):
    from app.db import SessionLocal
    from app.models import School, Section

    db = SessionLocal()
    rival = School(name="Rival Roster School", api_key=f"rr-{uuid.uuid4().hex}", state="Tamil Nadu",
                   training_consent="training_permitted", hidden_from_directory=False)
    db.add(rival)
    db.flush()
    foreign = Section(school_id=rival.id, grade=10, name="R")
    db.add(foreign)
    db.commit()
    foreign_id = foreign.id
    db.close()
    h = _class_teacher(client, school)
    assert client.get(f"/admin/teacher/sections/{foreign_id}/students", headers=h).status_code == 404
