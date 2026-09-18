"""Removing a student from the roster -- a principal's own action, not a teacher's (see
delete_student's docstring). Every real student worth removing has usually signed in at
least once (a StudentSession, born from logging in with a shared report's PIN) or been
resolved on a grid sheet (GridSheetRow.student_id) -- neither carried a DB-level cascade,
so deleting exactly the students most worth deleting failed outright with a foreign key
violation Postgres enforces unconditionally, the same class of bug test_assessment_crud.py
already caught once for deleting a paper."""

from __future__ import annotations

from contextlib import contextmanager

import pytest


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@contextmanager
def _foreign_keys_enforced():
    from sqlalchemy import event

    from app.db import engine

    def _enable(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    if engine.dialect.name != "sqlite":
        yield
        return
    event.listen(engine, "connect", _enable)
    engine.dispose()
    try:
        yield
    finally:
        event.remove(engine, "connect", _enable)
        engine.dispose()


@pytest.fixture
def student(school):
    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    s = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name="Delete Me", roll_no="del-1",
    )
    db.add(s)
    db.commit()
    student_id = s.id
    db.close()
    return student_id


def test_deleting_a_student_who_has_signed_in_with_a_shared_reports_pin_works(
    client, school, student,
):
    from datetime import UTC, datetime, timedelta

    from app.db import SessionLocal
    from app.models import StudentProfile, StudentSession

    db = SessionLocal()
    db.add(StudentSession(
        student_id=student, school_id=school["school_id"], token="tok-" + student,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    ))
    db.commit()
    db.close()

    with _foreign_keys_enforced():
        r = client.delete(f"/admin/students/{student}", headers=_auth(school))
    assert r.status_code == 204, r.text

    db = SessionLocal()
    assert db.get(StudentProfile, student) is None
    from sqlalchemy import select

    assert not list(db.scalars(select(StudentSession).where(StudentSession.student_id == student)))
    db.close()


def test_deleting_a_student_resolved_on_a_grid_sheet_works_and_keeps_the_sheet(
    client, school, student,
):
    """The grid sheet row itself survives -- other students' rows on the same sheet must
    not be lost -- but the deleted student is no longer named on it."""
    from app.db import SessionLocal
    from app.models import Assessment, GridSheetRow, ScanDocument, StudentProfile

    db = SessionLocal()
    assessment = Assessment(
        school_id=school["school_id"], subject_code="X.MATH", title="Grid Test", total_marks=10,
    )
    db.add(assessment)
    db.flush()
    document = ScanDocument(
        school_id=school["school_id"], assessment_id=assessment.id, kind="mark_grid",
        sha256="deadbeef", page_count=1,
    )
    db.add(document)
    db.flush()
    row = GridSheetRow(
        school_id=school["school_id"], assessment_id=assessment.id,
        section_id=school["section_id"], document_id=document.id,
        roll_no="del-1", status="clean", cells=[], student_id=student,
    )
    db.add(row)
    db.commit()
    row_id = row.id
    db.close()

    with _foreign_keys_enforced():
        r = client.delete(f"/admin/students/{student}", headers=_auth(school))
    assert r.status_code == 204, r.text

    db = SessionLocal()
    assert db.get(StudentProfile, student) is None
    kept = db.get(GridSheetRow, row_id)
    assert kept is not None
    assert kept.student_id is None
    assert kept.status == "unmatched"
    db.close()
