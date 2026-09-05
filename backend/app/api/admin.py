"""The routes the dashboard actually needs.

Without these there is no way to answer the two questions a principal opens the app with:
"what is the link I give my students?" and "who has finished?"
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    Staff,
    current_staff,
    require_reader,
    require_scanner,
    require_staff,
    school_in_scope,
)
from app.api.schemas import StudentCreateIn, StudentUpdateIn
from app.curriculum import CURRICULA
from app.db import get_session
from app.models import (
    Assessment,
    BookChunk,
    DataQualityFlag,
    ItemResponse,
    MarkEvent,
    ProfileResult,
    ProposedMark,
    Question,
    ScaleScore,
    ScanDocument,
    School,
    Section,
    StudentProfile,
    StudentReport,
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
            # Scanning and marks entry are open to any staff. A principal produces marks
            # as well as reading them: a deliberate choice, not an oversight.
            "scan_papers": True,
            "enter_marks": True,
            # The roster is now open to a principal too (add/edit/remove a student in
            # their own school) -- the same widening require_scanner already made for
            # scanning and marks. The Q-matrix and the credentials still stay with the
            # admin: those act across a school's whole setup, not one student's record.
            "manage_roster": True,
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


@router.get("/dashboard")
def dashboard(
    school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> dict:
    """Everything the landing screen shows, in one request.

    Every figure here is a count of rows that exist. There is no target, no projection and
    no "progress" that is not simply marks entered over questions on the paper -- a
    dashboard that estimates is a dashboard somebody eventually acts on.
    """
    assessments = list(db.scalars(
        select(Assessment).where(Assessment.school_id == school.id)
        .order_by(Assessment.created_at.desc())
    ))
    ids = [a.id for a in assessments]

    def counted(query) -> dict[str, int]:
        return dict(db.execute(query).all()) if ids else {}

    questions = counted(
        select(Question.assessment_id, func.count())
        .where(Question.assessment_id.in_(ids)).group_by(Question.assessment_id)
    )
    mapped = counted(
        select(Question.assessment_id, func.count())
        .where(Question.assessment_id.in_(ids), Question.chapter_id.is_not(None))
        .group_by(Question.assessment_id)
    )
    marked_students = counted(
        select(MarkEvent.assessment_id, func.count(func.distinct(MarkEvent.student_id)))
        .where(MarkEvent.assessment_id.in_(ids)).group_by(MarkEvent.assessment_id)
    )
    papers_scanned = counted(
        select(ScanDocument.assessment_id, func.count())
        .where(ScanDocument.assessment_id.in_(ids), ScanDocument.kind == "question_paper")
        .group_by(ScanDocument.assessment_id)
    )

    students = list(db.scalars(
        select(StudentProfile).where(StudentProfile.school_id == school.id)
    ))
    student_ids = [s.id for s in students]

    scripts = list(db.scalars(
        select(ScanDocument)
        .where(ScanDocument.school_id == school.id, ScanDocument.kind == "answer_sheet")
        .order_by(ScanDocument.created_at.desc())
    ))
    scripts_by_student: dict[str, int] = {}
    for d in scripts:
        if d.student_id:
            scripts_by_student[d.student_id] = scripts_by_student.get(d.student_id, 0) + 1

    marks_by_student = dict(db.execute(
        select(MarkEvent.student_id, func.count(func.distinct(MarkEvent.assessment_id)))
        .where(MarkEvent.student_id.in_(student_ids)).group_by(MarkEvent.student_id)
    ).all()) if student_ids else {}

    reports_by_student = dict(db.execute(
        select(StudentReport.student_id, func.count())
        .where(StudentReport.school_id == school.id).group_by(StudentReport.student_id)
    ).all())

    titles = {a.id: a.title for a in assessments}
    names = {s.id: (s.name, s.roll_no) for s in students}

    #: One ratio, and it is the one that decides whether a report can be written at all:
    #: a question with no chapter contributes to no finding.
    questions_total = sum(questions.values())
    questions_mapped = sum(mapped.values())

    return {
        "school": {"id": school.id, "name": school.name, "state": school.state},
        "counts": {
            "students": len(students),
            "classes": db.scalar(
                select(func.count()).select_from(Section).where(Section.school_id == school.id)
            ),
            "papers": len(assessments),
            "papers_read": sum(1 for a in assessments if questions.get(a.id, 0) > 0),
            "question_papers_stored": sum(papers_scanned.values()),
            "scripts_stored": len(scripts),
            "reports_issued": sum(reports_by_student.values()),
            "questions_total": questions_total,
            "questions_mapped": questions_mapped,
        },
        "papers": [
            {
                "id": a.id,
                "title": a.title,
                "subject_code": a.subject_code,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "questions": questions.get(a.id, 0),
                "mapped": mapped.get(a.id, 0),
                "students_marked": marked_students.get(a.id, 0),
                "paper_stored": papers_scanned.get(a.id, 0) > 0,
                "stage": (
                    "mapped" if mapped.get(a.id) else
                    "read" if questions.get(a.id) else
                    "scanned" if papers_scanned.get(a.id) else "empty"
                ),
            }
            for a in assessments[:6]
        ],
        "students": [
            {
                "student_id": s.id,
                "name": s.name,
                "roll_no": s.roll_no,
                "papers_marked": marks_by_student.get(s.id, 0),
                "scripts": scripts_by_student.get(s.id, 0),
                "reports": reports_by_student.get(s.id, 0),
            }
            for s in sorted(students, key=lambda s: (-marks_by_student.get(s.id, 0), s.roll_no))[:6]
        ],
        "recent_scripts": [
            {
                "document_id": d.id,
                "student_id": d.student_id,
                "student": names.get(d.student_id or "", ("unknown", ""))[0],
                "roll_no": names.get(d.student_id or "", ("", ""))[1],
                "assessment_title": titles.get(d.assessment_id),
                "page_count": d.page_count,
                "stored_at": d.created_at.isoformat() if d.created_at else None,
                "first_page": f"/documents/{d.id}/pages/0" if d.page_count else None,
            }
            for d in scripts[:5]
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


def _student_in_scope(db: Session, school: School, student_id: str) -> StudentProfile:
    student = db.get(StudentProfile, student_id)
    if student is None or student.school_id != school.id:
        raise HTTPException(404, "not found")
    return student


@router.post("/sections/{section_id}/students", status_code=201)
def create_student(
    section_id: str, body: StudentCreateIn,
    school: School = Depends(require_scanner), db: Session = Depends(get_session),
) -> dict:
    """Add a student to the roster by hand.

    A principal reaches this the same way they already reach scanning and marks
    (require_scanner) -- see the roster's own widened scope. self-registration
    (app.api.interest) is still the normal path for a student who has the class link;
    this is for the one who does not sit the interest test first, or whose name a
    principal is correcting before a paper is scanned.
    """
    section = db.get(Section, section_id)
    if section is None or section.school_id != school.id:
        raise HTTPException(404, "not found")

    existing = db.scalar(
        select(StudentProfile).where(
            StudentProfile.section_id == section_id, StudentProfile.roll_no == body.roll_no,
        )
    )
    if existing is not None:
        raise HTTPException(
            409, f"roll number {body.roll_no!r} is already in this class -- {existing.name}",
        )

    student = StudentProfile(
        school_id=school.id, section_id=section_id, name=body.name, roll_no=body.roll_no,
        age=body.age, gender=body.gender, dob=body.dob,
    )
    db.add(student)
    db.commit()
    return {"student_id": student.id, "name": student.name, "roll_no": student.roll_no}


@router.patch("/students/{student_id}")
def edit_student(
    student_id: str, body: StudentUpdateIn,
    school: School = Depends(require_scanner), db: Session = Depends(get_session),
) -> dict:
    student = _student_in_scope(db, school, student_id)

    if body.roll_no is not None and body.roll_no != student.roll_no:
        clash = db.scalar(
            select(StudentProfile).where(
                StudentProfile.section_id == student.section_id,
                StudentProfile.roll_no == body.roll_no,
            )
        )
        if clash is not None:
            raise HTTPException(
                409, f"roll number {body.roll_no!r} is already in this class -- {clash.name}",
            )

    changed = []
    for field_name in ("name", "roll_no", "age", "gender", "dob"):
        value = getattr(body, field_name)
        if value is None:
            continue
        setattr(student, field_name, value)
        changed.append(field_name)
    db.commit()
    return {"student_id": student.id, "changed": changed}


@router.delete("/students/{student_id}", status_code=204)
def delete_student(
    student_id: str,
    school: School = Depends(require_scanner), db: Session = Depends(get_session),
) -> None:
    """Remove a student and every record that names them.

    Hard delete, like every other removal in this API -- there is no soft-delete column to
    honour instead. A principal reaches this the same way they reach the rest of the
    roster now; unlike delete_assessment (admin-only: a whole paper's worth of everyone
    else's marks), the blast radius here is scoped to one student's own record, which a
    principal is already trusted to enter and correct.
    """
    student = _student_in_scope(db, school, student_id)

    session_ids = list(
        db.scalars(select(TestSession.id).where(TestSession.student_id == student_id))
    )
    if session_ids:
        db.execute(ItemResponse.__table__.delete().where(ItemResponse.session_id.in_(session_ids)))
        db.execute(ScaleScore.__table__.delete().where(ScaleScore.session_id.in_(session_ids)))
        db.execute(ProfileResult.__table__.delete().where(ProfileResult.session_id.in_(session_ids)))
    for model in (TestSession, MarkEvent, StudentReport, ProposedMark, DataQualityFlag):
        db.execute(model.__table__.delete().where(model.student_id == student_id))
    for document in db.scalars(
        select(ScanDocument).where(ScanDocument.student_id == student_id)
    ):
        db.delete(document)
    db.delete(student)
    db.commit()


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


@router.get("/subjects")
def list_subjects(
    _staff: Staff = Depends(current_staff), db: Session = Depends(get_session)
) -> dict:
    """The subjects this deployment carries, and how far each one is loaded.

    The screens used to name Mathematics and Science in their own code, so a third subject
    could be added here and stay invisible to everybody using the app. The curriculum is
    the authority for what exists; this route is how a screen asks it.

    Any signed-in member of staff, and deliberately not scoped to a school: which subjects
    a deployment carries is the same answer for everybody, and demanding a school here shut
    the operator console out of its own book screen.
    """
    out = []
    for curriculum in CURRICULA.values():
        chunks = db.scalar(
            select(func.count(BookChunk.id)).where(
                BookChunk.subject_code == curriculum.subject_code
            )
        ) or 0
        embedded = db.scalar(
            select(func.count(BookChunk.id)).where(
                BookChunk.subject_code == curriculum.subject_code,
                BookChunk.embedding.isnot(None),
            )
        ) or 0
        out.append({
            "subject_code": curriculum.subject_code,
            "label": curriculum.subject_label,
            "grade": curriculum.grade,
            "chapters": len(curriculum.chapters),
            "board_units": len(curriculum.units),
            #: a subject with no embedded book cannot map a question, and a screen that
            #: offers it anyway is offering a dead end
            "book_loaded": embedded > 0,
            "chunks": chunks,
            "chunks_embedded": embedded,
        })
    return {"subjects": out}
