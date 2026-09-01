"""The routes the dashboard actually needs.

Without these there is no way to answer the two questions a principal opens the app with:
"what is the link I give my students?" and "who has finished?"
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Staff, require_reader, require_staff, school_in_scope
from app.db import get_session
from app.models import (
    Assessment,
    MarkEvent,
    ProfileResult,
    School,
    Section,
    StudentProfile,
    TestSession,
)

router = APIRouter(prefix="/admin", tags=["dashboard"])


@router.get("/me")
def whoami(
    staff: Staff = Depends(require_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> dict:
    """Validates a key, names the school it is acting on, and says what it may do.

    The permissions come from the server rather than being inferred in the browser from
    the role name. A screen that hides a button it guessed at is one release away from
    hiding the wrong one; this way the dashboard and the API cannot disagree.
    """
    school = school_in_scope(staff, x_school_id, db)
    return {
        "school_id": school.id,
        "name": school.name,
        "board": school.board,
        "state": school.state,
        "training_consent": school.training_consent,
        "role": staff.role,
        #: An admin key is not tied to a school, so the dashboard has to offer a choice of
        #: them. A principal's key names one and the question does not arise.
        "scope": "all_schools" if staff.is_admin and staff.home is None else "one_school",
        "can": {
            "read_results": True,
            "scan_papers": staff.is_admin,
            "enter_marks": staff.is_admin,
            "manage_roster": staff.is_admin,
            "manage_schools": staff.is_admin,
        },
    }


@router.get("/overview")
def overview(
    school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> dict:
    """Everything the landing dashboard shows: classes, their student link, and progress."""
    sections = list(
        db.scalars(select(Section).where(Section.school_id == school.id).order_by(Section.name))
    )

    out = []
    for section in sections:
        students = list(
            db.scalars(select(StudentProfile).where(StudentProfile.section_id == section.id))
        )
        ids = [s.id for s in students]
        completed = 0
        flagged = 0
        if ids:
            rows = list(
                db.scalars(select(TestSession).where(TestSession.student_id.in_(ids)))
            )
            latest: dict[str, TestSession] = {}
            for row in rows:
                prev = latest.get(row.student_id)
                if prev is None or (row.created_at or 0) > (prev.created_at or 0):
                    latest[row.student_id] = row
            completed = sum(1 for r in latest.values() if r.completed_at is not None)
            flagged = sum(1 for r in latest.values() if r.validity in ("suspect", "invalid"))

        out.append(
            {
                "section_id": section.id,
                "label": f"Class {section.grade}-{section.name}",
                "grade": section.grade,
                "name": section.name,
                #: the link a teacher hands out — this is the answer to "where is the
                #: student link?", and it exists nowhere else in the system
                "student_path": f"/t/{section.id}",
                "students": len(students),
                "completed": completed,
                "flagged": flagged,
            }
        )

    assessments = list(
        db.scalars(
            select(Assessment)
            .where(Assessment.school_id == school.id)
            .order_by(Assessment.created_at.desc())
        )
    )
    return {
        "school": {"id": school.id, "name": school.name, "state": school.state},
        "sections": out,
        "totals": {
            "students": sum(s["students"] for s in out),
            "completed": sum(s["completed"] for s in out),
            "flagged": sum(s["flagged"] for s in out),
        },
        "assessments": [
            {
                "id": a.id,
                "title": a.title,
                "paper_code": a.paper_code,
                "subject_code": a.subject_code,
                "status": a.status,
                "total_marks": float(a.total_marks) if a.total_marks is not None else None,
                "frozen": a.qmatrix_frozen_at is not None,
            }
            for a in assessments
        ],
    }


@router.get("/sections/{section_id}/students")
def roster(
    section_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """The roster, each row carrying enough state to decide what to do next."""
    section = db.get(Section, section_id)
    if section is None or section.school_id != school.id:
        raise HTTPException(404, "not found")

    students = list(
        db.scalars(
            select(StudentProfile)
            .where(StudentProfile.section_id == section_id)
            .order_by(StudentProfile.roll_no)
        )
    )

    sessions: dict[str, TestSession] = {}
    results: dict[str, ProfileResult] = {}
    if students:
        ids = [s.id for s in students]
        for row in db.scalars(select(TestSession).where(TestSession.student_id.in_(ids))):
            prev = sessions.get(row.student_id)
            if prev is None or (row.created_at or 0) > (prev.created_at or 0):
                sessions[row.student_id] = row
        session_ids = [s.id for s in sessions.values()]
        if session_ids:
            for res in db.scalars(
                select(ProfileResult).where(ProfileResult.session_id.in_(session_ids))
            ):
                results[res.session_id] = res

    # How many papers each student has marks on. The roster carried only the interest
    # test, so a class that had sat a written test looked untouched -- and the marks are
    # the half a principal opens the roster to see.
    papers: dict[str, int] = {}
    if students:
        for student_id, count in db.execute(
            select(MarkEvent.student_id, func.count(func.distinct(MarkEvent.assessment_id)))
            .where(MarkEvent.student_id.in_([s.id for s in students]))
            .group_by(MarkEvent.student_id)
        ).all():
            papers[student_id] = count

    rows = []
    for student in students:
        session = sessions.get(student.id)
        result = results.get(session.id) if session else None
        if session is None:
            status = "not_started"
        elif session.completed_at is None:
            status = "in_progress"
        else:
            status = "complete"
        rows.append(
            {
                "student_id": student.id,
                "name": student.name,
                "roll_no": student.roll_no,
                "status": status,
                "papers_marked": papers.get(student.id, 0),
                "validity": session.validity if session else None,
                "holland_code": result.holland_code if result else None,
                "withheld": bool(result.recommendation_withheld) if result else None,
                "top_stream": (
                    max(result.stream_fit, key=result.stream_fit.get)
                    if result and result.stream_fit and not result.recommendation_withheld
                    else None
                ),
            }
        )

    return {
        "section": {
            "id": section.id,
            "label": f"Class {section.grade}-{section.name}",
            "student_path": f"/t/{section.id}",
        },
        "students": rows,
    }


@router.get("/cohort/{section_id}")
def cohort(
    section_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """Class-level interest distribution — the view that helps plan section sizes."""
    section = db.get(Section, section_id)
    if section is None or section.school_id != school.id:
        raise HTTPException(404, "not found")

    students = list(
        db.scalars(select(StudentProfile.id).where(StudentProfile.section_id == section_id))
    )
    if not students:
        return {"holland": {}, "streams": {}, "counted": 0, "withheld": 0}

    session_rows = list(db.scalars(select(TestSession).where(TestSession.student_id.in_(students))))
    latest: dict[str, TestSession] = {}
    for row in session_rows:
        prev = latest.get(row.student_id)
        if prev is None or (row.created_at or 0) > (prev.created_at or 0):
            latest[row.student_id] = row

    holland: dict[str, int] = {}
    streams: dict[str, int] = {}
    counted = 0
    withheld = 0
    for session in latest.values():
        result = db.scalar(select(ProfileResult).where(ProfileResult.session_id == session.id))
        if result is None:
            continue
        if result.recommendation_withheld:
            withheld += 1
            continue
        counted += 1
        if result.holland_code:
            holland[result.holland_code[0]] = holland.get(result.holland_code[0], 0) + 1
        if result.stream_fit:
            top = max(result.stream_fit, key=result.stream_fit.get)
            streams[top] = streams.get(top, 0) + 1

    return {"holland": holland, "streams": streams, "counted": counted, "withheld": withheld}
