"""The same Overview -> class -> test drill-down principals get in app.api.academics,
scoped to one teacher's own class/subject assignments -- a class assignment reads every
subject for that section; a subject assignment reads only that one subject, and can
never be widened by a query parameter.

Reuses every computation in app.api.academics unchanged (resolved_rows, the status
bands, the chapter/tier findings machinery) -- this module only adds the scope check and
narrows which sections/subjects a call is allowed to ask about.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.academics import (
    STATUS_LABELS,
    TaggedRow,
    _status_for,
    _subject_label,
    resolved_rows,
)
from app.api.deps import Staff, current_staff, teacher_assignments
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
            "test_count": len(assessment_ids),
        })
    out.sort(key=lambda e: (e["label"], e["subject_label"]))
    return {"classes": out}


@router.get("/{section_id}/students")
def teacher_class_students(
    section_id: str, subject_code: str | None = None, status: str | None = None,
    staff: Staff = Depends(current_staff), db: Session = Depends(get_session),
) -> dict:
    """The same per-student status/avg-score list a principal's class page shows,
    refused with 404 unless this teacher key holds a class or subject assignment on
    this exact section -- and, for a subject assignment, always run as that one
    subject regardless of what the query string asks for."""
    _require_teacher(staff)
    assert staff.home is not None
    scope = _teacher_scope(staff, db)
    effective_subject = _assert_in_scope(scope, section_id, subject_code)
    if status is not None and status not in STATUS_LABELS:
        raise HTTPException(422, f"status must be one of {', '.join(STATUS_LABELS)}")

    from app.api.academics import _class_students, _get_section

    section = _get_section(db, staff.home, section_id)
    students = _class_students(
        db, staff.home, section, subject_code=effective_subject, assessment_id=None, status=status,
    )
    return {
        "section": {"id": section.id, "label": f"Class {section.grade}-{section.name}"},
        "subject_code": effective_subject,
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

    by_assessment: dict[str, dict] = {}
    for section_id, subject_code in scope:
        student_ids = list(
            db.scalars(select(StudentProfile.id).where(StudentProfile.section_id == section_id))
        )
        if not student_ids:
            continue
        tagged = resolved_rows(db, school, student_ids=student_ids, subject_code=subject_code)
        for t in tagged:
            entry = by_assessment.setdefault(t.assessment_id, {
                "assessment_id": t.assessment_id, "title": t.assessment_title,
                "subject_code": t.subject_code, "label": _subject_label(t.subject_code),
                "students": set(),
            })
            entry["students"].add(t.row.student_id)

    out = [
        {**{k: v for k, v in e.items() if k != "students"}, "students_marked": len(e["students"])}
        for e in by_assessment.values()
    ]
    out.sort(key=lambda e: e["title"])
    return {"tests": out}


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
