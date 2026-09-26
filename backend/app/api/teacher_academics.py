"""The same Overview -> class -> test drill-down principals get in app.api.academics,
scoped to one teacher's own class/subject assignments -- a class assignment reads every
subject for that section; a subject assignment reads only that one subject, and can
never be widened by a query parameter.

Reuses every computation in app.api.academics unchanged (resolved_rows, the status
bands, the chapter/tier findings machinery) -- this module only adds the scope check and
narrows which sections/subjects a call is allowed to ask about.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.academics import (
    STATUS_LABELS,
    TaggedRow,
    _class_students_rows,
    _csv_response,
    _status_for,
    _student_overview,
    _student_rows,
    _subject_breakdown,
    _subject_label,
    _subject_rows,
    _test_rows,
    resolved_rows,
    tests_with_movement,
)
from app.api.deps import Staff, current_staff, teacher_assignments, teacher_can_read
from app.db import get_session
from app.models import Section, StudentProfile

router = APIRouter(prefix="/admin/teacher/academics", tags=["academics"])


def _require_teacher(staff: Staff) -> None:
    if not staff.is_teacher:
        raise HTTPException(403, "this route is for teacher keys")


def _teacher_scope(staff: Staff, db: Session) -> list[tuple[str, str | None]]:
    """Every (section_id, subject_code) this teacher key may read -- subject_code is
    None for a class assignment (every subject in that section), or the one subject a
    subject assignment names. A teacher holding both a class and a subject assignment
    on the same section gets the wider (class) read for it, not both rows separately."""
    by_section: dict[str, str | None] = {}
    for a in teacher_assignments(staff, db):
        if a.type == "class":
            by_section[a.section_id] = None
        elif a.section_id not in by_section:
            by_section[a.section_id] = a.subject_code
    return list(by_section.items())


def _assert_in_scope(scope: list[tuple[str, str | None]], section_id: str, subject_code: str | None) -> str | None:
    """Refuses a request outside what this key actually holds, and returns the subject
    this call must actually run as -- a subject-scoped teacher can never widen their own
    read by naming a different (or no) subject in the query string."""
    for sec, subj in scope:
        if sec != section_id:
            continue
        if subj is None:
            return subject_code  # class assignment: whatever the caller asked for
        if subject_code is not None and subject_code != subj:
            raise HTTPException(404, "not found")
        return subj
    raise HTTPException(404, "not found")


@router.get("")
def teacher_academics_overview(
    staff: Staff = Depends(current_staff), db: Session = Depends(get_session)
) -> dict:
    """Every class/subject this teacher key holds, the same status split a principal's
    Overview shows -- narrowed to one subject's marks where the teacher only holds a
    subject assignment there."""
    _require_teacher(staff)
    assert staff.home is not None, "a teacher key always names its school"
    school = staff.home
    scope = _teacher_scope(staff, db)
    sections = {
        s.id: s for s in db.scalars(select(Section).where(Section.id.in_([s for s, _ in scope])))
    } if scope else {}

    out = []
    for section_id, subject_code in scope:
        section = sections.get(section_id)
        if section is None:
            continue
        students = list(
            db.scalars(select(StudentProfile).where(StudentProfile.section_id == section_id))
        )
        student_ids = [s.id for s in students]
        tagged = resolved_rows(db, school, student_ids=student_ids, subject_code=subject_code)
        by_student: dict[str, list[TaggedRow]] = {}
        for t in tagged:
            by_student.setdefault(t.row.student_id, []).append(t)

        counts = {k: 0 for k in STATUS_LABELS}
        earned_sum = available_sum = 0.0
        assessment_ids: set[str] = set()
        for student in students:
            entries = by_student.get(student.id, [])
            earned = sum(t.row.earned for t in entries if t.row.counts)
            available = sum(t.row.max_marks for t in entries if t.row.counts)
            counts[_status_for(earned, available)] += 1
            earned_sum += earned
            available_sum += available
            assessment_ids |= {t.assessment_id for t in entries}

        out.append({
            "section_id": section.id,
            "label": f"Class {section.grade}-{section.name}",
            "subject_code": subject_code,
            "subject_label": _subject_label(subject_code) if subject_code else "All subjects",
            "student_count": len(students),
            "status_counts": counts,
            "avg_score_pct": round(earned_sum / available_sum * 100, 1) if available_sum else None,
            # Real average marks earned / average marks possible, per student, behind
            # that percentage -- for an "avg 14 / 17" style display. Derived from the
            # same earned/available sums avg_score_pct is computed from, never a guess;
            # None (not a fabricated 0) when nobody in this class has a resolved mark.
            "avg_marks_earned": round(earned_sum / len(students), 1) if available_sum and students else None,
            "avg_marks_available": round(available_sum / len(students), 1) if available_sum and students else None,
            "test_count": len(assessment_ids),
        })
    out.sort(key=lambda e: (e["label"], e["subject_label"]))
    return {"classes": out}


@router.get("/{section_id}/students.csv")
def teacher_class_students_csv(
    section_id: str, subject_code: str | None = None, assessment_id: str | None = None, status: str | None = None,
    staff: Staff = Depends(current_staff), db: Session = Depends(get_session),
) -> Response:
    """Same rows as the bare route below, as a CSV -- registered first so FastAPI
    matches the ``.csv`` suffix before the bare ``{section_id}`` path param would
    swallow it (the convention every ``.xlsx``/``.pdf`` sibling in academics.py follows)."""
    body = teacher_class_students(section_id, subject_code, assessment_id, status, staff, db)
    header, rows = _class_students_rows(body["students"])
    return _csv_response(header, rows, f"{body['section']['label']}-students.csv")


@router.get("/{section_id}/students")
def teacher_class_students(
    section_id: str, subject_code: str | None = None, assessment_id: str | None = None, status: str | None = None,
    staff: Staff = Depends(current_staff), db: Session = Depends(get_session),
) -> dict:
    """The same per-student status/avg-score list a principal's class page shows,
    refused with 404 unless this teacher key holds a class or subject assignment on
    this exact section -- and, for a subject assignment, always run as that one
    subject regardless of what the query string asks for. ``assessment_id``, like the
    principal's own route, narrows to one test and unlocks each row's real
    previous_score_pct/delta_pct against the immediately preceding same-subject test --
    left out (both null) when no test is named."""
    _require_teacher(staff)
    assert staff.home is not None
    scope = _teacher_scope(staff, db)
    effective_subject = _assert_in_scope(scope, section_id, subject_code)
    if status is not None and status not in STATUS_LABELS:
        raise HTTPException(422, f"status must be one of {', '.join(STATUS_LABELS)}")

    from app.api.academics import _class_students, _get_section, _previous_test

    section = _get_section(db, staff.home, section_id)
    student_ids = list(
        db.scalars(select(StudentProfile.id).where(StudentProfile.section_id == section_id))
    )
    previous = _previous_test(db, staff.home, assessment_id, student_ids) if assessment_id else None
    students = _class_students(
        db, staff.home, section, subject_code=effective_subject, assessment_id=assessment_id, status=status,
    )
    return {
        "section": {"id": section.id, "label": f"Class {section.grade}-{section.name}"},
        "subject_code": effective_subject,
        "previous_test": {"assessment_id": previous.id, "title": previous.title} if previous else None,
        "students": students,
    }


@router.get("/tests")
def teacher_academics_tests(
    staff: Staff = Depends(current_staff), db: Session = Depends(get_session)
) -> dict:
    """Every paper with a resolved mark inside this teacher's own scope -- a subject
    teacher never sees a paper from a subject they were not assigned, even for a
    section they otherwise hold."""
    _require_teacher(staff)
    assert staff.home is not None
    school = staff.home
    scope = _teacher_scope(staff, db)

    tagged: list[TaggedRow] = []
    for section_id, subject_code in scope:
        student_ids = list(
            db.scalars(select(StudentProfile.id).where(StudentProfile.section_id == section_id))
        )
        if not student_ids:
            continue
        tagged.extend(resolved_rows(db, school, student_ids=student_ids, subject_code=subject_code))

    return {"tests": tests_with_movement(db, tagged)}


@router.get("/tests/{assessment_id}.csv")
def teacher_test_summary_csv(
    assessment_id: str, staff: Staff = Depends(current_staff), db: Session = Depends(get_session),
) -> Response:
    """Same ordering rule as the students.csv sibling above -- must be registered
    before the bare ``/tests/{assessment_id}`` route."""
    body = teacher_test_summary(assessment_id, staff, db)
    header, rows = _test_rows(body)
    return _csv_response(header, rows, f"{body['assessment']['title']}-results.csv")


@router.get("/tests/{assessment_id}")
def teacher_test_summary(
    assessment_id: str, staff: Staff = Depends(current_staff), db: Session = Depends(get_session)
) -> dict:
    """One test's student-by-student summary, restricted to students in a section this
    teacher holds and (for a subject assignment) to that one subject's own marks."""
    _require_teacher(staff)
    assert staff.home is not None
    school = staff.home
    scope = _teacher_scope(staff, db)

    from app.models import Assessment

    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != school.id:
        raise HTTPException(404, "no such test")

    # Only the (section, subject) pairs this teacher holds that could even see this
    # assessment's own subject -- a class assignment (subject_code None) always
    # qualifies; a subject assignment only if it names this exact subject.
    eligible_sections = [
        sec for sec, subj in scope if subj is None or subj == assessment.subject_code
    ]
    if not eligible_sections:
        raise HTTPException(404, "no such test")
    student_ids = list(
        db.scalars(select(StudentProfile.id).where(StudentProfile.section_id.in_(eligible_sections)))
    )
    if not student_ids:
        raise HTTPException(404, "no such test")

    from app.analysis.diagnostics import MarkRow

    tagged = resolved_rows(db, school, student_ids=student_ids, assessment_id=assessment_id)
    by_student: dict[str, list[MarkRow]] = {}
    for t in tagged:
        by_student.setdefault(t.row.student_id, []).append(t.row)
    if not by_student:
        raise HTTPException(404, "no such test")

    students = {
        s.id: s for s in db.scalars(select(StudentProfile).where(StudentProfile.id.in_(list(by_student))))
    }
    counts = {k: 0 for k in STATUS_LABELS}
    rows = []
    for student_id, marks in by_student.items():
        student = students.get(student_id)
        earned = sum(r.earned for r in marks if r.counts)
        available = sum(r.max_marks for r in marks if r.counts)
        status_band = _status_for(earned, available)
        counts[status_band] += 1
        rows.append({
            "student_id": student_id,
            "name": student.name if student else student_id,
            "roll_no": student.roll_no if student else "",
            "earned": earned, "available": available,
            "avg_score_pct": round(earned / available * 100, 1) if available else None,
            "status": status_band,
        })
    rows.sort(key=lambda r: r["roll_no"])

    return {
        "assessment": {
            "id": assessment.id, "title": assessment.title,
            "subject_code": assessment.subject_code, "subject_label": _subject_label(assessment.subject_code),
        },
        "status_counts": counts,
        "students": rows,
    }


def _get_scoped_student(db: Session, staff: Staff, student_id: str) -> StudentProfile:
    student = db.get(StudentProfile, student_id)
    if student is None or staff.home is None or student.school_id != staff.home.id:
        raise HTTPException(404, "not found")
    return student


def _allowed_subjects_for(
    scope: list[tuple[str, str | None]], section_id: str,
) -> tuple[bool, set[str] | None]:
    """(found, allowed) for one section: found is False if this key holds nothing on
    this section at all (404 territory); allowed is None for a class assignment (every
    subject), or the set of subject codes a subject assignment (or several) names."""
    found = False
    allowed: set[str] | None = set()
    for sec, subj in scope:
        if sec != section_id:
            continue
        found = True
        if subj is None:
            return True, None
        assert allowed is not None
        allowed.add(subj)
    return found, allowed


@router.get("/students/{student_id}.csv")
def teacher_student_academics_csv(
    student_id: str, subject_code: str | None = None,
    staff: Staff = Depends(current_staff), db: Session = Depends(get_session),
) -> Response:
    """Registered before the bare `/students/{student_id}` route below, same ordering
    rule as every other .csv sibling in this file."""
    overview = teacher_student_academics(student_id, subject_code, staff, db)
    header, rows = _student_rows(overview)
    return _csv_response(header, rows, f"{overview['student']['name']}-overview.csv")


@router.get("/students/{student_id}")
def teacher_student_academics(
    student_id: str, subject_code: str | None = None,
    staff: Staff = Depends(current_staff), db: Session = Depends(get_session),
) -> dict:
    """The same cross-subject student overview a principal's student page shows --
    reuses _student_overview unchanged, restricted to exactly the subjects this
    teacher's own assignments on the student's section cover (a class assignment sees
    every subject; a subject assignment sees only its own, including in the "overall"
    tiles, never just the table)."""
    _require_teacher(staff)
    assert staff.home is not None
    student = _get_scoped_student(db, staff, student_id)
    scope = _teacher_scope(staff, db)
    found, allowed = _allowed_subjects_for(scope, student.section_id)
    if not found:
        raise HTTPException(404, "not found")
    return _student_overview(db, staff.home, student, subject_code=subject_code, allowed_subjects=allowed)


@router.get("/students/{student_id}/subjects/{subject_code}.csv")
def teacher_student_subject_csv(
    student_id: str, subject_code: str,
    staff: Staff = Depends(current_staff), db: Session = Depends(get_session),
) -> Response:
    """Registered before the bare `/subjects/{subject_code}` route below, same
    ordering rule as every other .csv sibling in this file."""
    detail = teacher_student_subject_breakdown(student_id, subject_code, staff, db)
    header, rows = _subject_rows(detail)
    return _csv_response(header, rows, f"{detail['student']['name']}-{subject_code}.csv")


@router.get("/students/{student_id}/subjects/{subject_code}")
def teacher_student_subject_breakdown(
    student_id: str, subject_code: str,
    staff: Staff = Depends(current_staff), db: Session = Depends(get_session),
) -> dict:
    """The same chapter/tier drill-down a principal's student-subject page shows,
    reusing _subject_breakdown unchanged -- refused with 404 unless this teacher key
    holds a class or subject assignment on the student's own section covering this
    subject (never widened by the subject_code in the URL itself)."""
    _require_teacher(staff)
    assert staff.home is not None
    student = _get_scoped_student(db, staff, student_id)
    if not teacher_can_read(staff, db, student.section_id, subject_code):
        raise HTTPException(404, "not found")
    return _subject_breakdown(db, staff.home, student, subject_code)


@router.get("/students/{student_id}/boardx")
def teacher_student_boardx(
    student_id: str, assessment_id: str,
    staff: Staff = Depends(current_staff), db: Session = Depends(get_session),
) -> dict:
    """The BoardX v2 one-pager for a student in this teacher's own scope.
    GET /reports/student/{id}/boardx explicitly refuses a teacher key (see its own
    docstring/require_reader) since that surface has no section/subject filter -- this
    is the teacher-scoped sibling: same compose_boardx_report computation, gated to
    exactly the section+subject this key holds instead of a school-wide read."""
    _require_teacher(staff)
    assert staff.home is not None
    from app.analysis.boardx_report import compose_boardx_report
    from app.api.reports import _rows
    from app.models import Assessment

    student = _get_scoped_student(db, staff, student_id)
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != staff.home.id:
        raise HTTPException(404, "not found")
    if not teacher_can_read(staff, db, student.section_id, assessment.subject_code):
        raise HTTPException(404, "not found")
    rows = [r for r in _rows(db, assessment) if r.student_id == student_id]
    if not rows:
        raise HTTPException(404, "no marks for this student")
    return compose_boardx_report(db, assessment, student, rows)
