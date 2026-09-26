"""The routes the dashboard actually needs.

Without these there is no way to answer the two questions a principal opens the app with:
"what is the link I give my students?" and "who has finished?"
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    Staff,
    current_staff,
    require_admin,
    require_reader,
    require_scanner,
    require_staff,
    require_teacher_read_scope,
    school_in_scope,
    teacher_assignments,
    teacher_can_read,
    teacher_subject_codes,
)
from app.api.academics import _subject_label
from app.api.schemas import StudentCreateIn, StudentUpdateIn
from app.curriculum import subject_groups
from app.db import get_session
from app.models import (
    TEACHER_ASSIGNMENT_TYPES,
    Assessment,
    BookChunk,
    DataQualityFlag,
    GridSheetRow,
    ItemResponse,
    MarkEvent,
    ProfileResult,
    ProposedMark,
    Question,
    ScaleScore,
    ScanDocument,
    School,
    Section,
    StaffKey,
    StudentProfile,
    StudentReport,
    StudentSession,
    TeacherAssignment,
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
    # A teacher's own paper-authoring/marks/scanning rights turn on holding at least one
    # *subject* assignment -- a class-only teacher stays read-only, same rule as
    # teacher_can_enter_marks. Computed once and reused for both flags: they are granted
    # or refused together, since both routes live behind exactly the same subject check.
    teacher_has_subject = staff.is_teacher and (bool(teacher_subject_codes(staff, db)) or staff.exam_cell)
    out = {
        "school_id": school.id,
        "name": school.name,
        "board": school.board,
        "state": school.state,
        "training_consent": school.training_consent,
        "role": staff.role,
        #: An admin key is not tied to a school, so the dashboard has to offer a choice of
        #: them. A principal's key names one and the question does not arise.
        "scope": "all_schools" if staff.is_admin and staff.home is None else "one_school",
        #: Set only for a teacher key. The frontend used to infer "exam cell" from
        #: assignments.length === 0 plus scan/enter rights, a condition that can never
        #: actually hold -- those rights themselves only ever came from holding a subject
        #: assignment. This is the real, operator-set fact instead of that inference.
        "exam_cell": staff.is_teacher and staff.exam_cell,
        "can": {
            "read_results": not staff.is_teacher,
            # Scanning and marks entry are open to any staff. A principal produces marks
            # as well as reading them: a deliberate choice, not an oversight.
            "scan_papers": (not staff.is_teacher) or teacher_has_subject,
            "enter_marks": (not staff.is_teacher) or teacher_has_subject,
            # The roster is now open to a principal too (add/edit/remove a student in
            # their own school) -- the same widening require_scanner already made for
            # scanning and marks. The Q-matrix and the credentials still stay with the
            # admin: those act across a school's whole setup, not one student's record.
            "manage_roster": not staff.is_teacher,
            "manage_schools": staff.is_admin,
        },
    }
    # A teacher's response carries the same top-level keys principal/admin have always
    # had (byte-identical for those two roles) plus one more: which sections/subjects
    # this key may touch, which is what the frontend uses to pick the teacher shell and
    # render only the classes/subjects this key actually holds.
    if staff.is_teacher:
        rows = teacher_assignments(staff, db)
        section_ids = {a.section_id for a in rows}
        sections = {
            s.id: s for s in db.scalars(select(Section).where(Section.id.in_(section_ids)))
        } if section_ids else {}
        out["assignments"] = [
            {
                "type": a.type,
                "section_id": a.section_id,
                "section_label": (
                    f"Class {sections[a.section_id].grade}-{sections[a.section_id].name}"
                    if a.section_id in sections else None
                ),
                "subject_code": a.subject_code,
                "subject_label": _subject_label(a.subject_code) if a.subject_code else None,
            }
            for a in rows
        ]
    return out


@router.get("/staff")
def list_staff(
    school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> list[dict]:
    """Who else can act on this school -- read-only.

    Issuing or revoking a key is still operator-only (app.api.platform, behind
    X-Platform-Key): a principal must never mint their own replacement credential or
    another school's. Seeing who already holds one for their own school is a different
    act, and today there was no way to do even that -- a principal had to ask the operator
    rather than check for themselves. Never carries api_key, same as every other listing
    of a key in this codebase.
    """
    keys = list(
        db.scalars(
            select(StaffKey)
            .where(StaffKey.school_id == school.id)
            .order_by(StaffKey.revoked_at.is_not(None), StaffKey.created_at)
        )
    )
    return [
        {
            "id": k.id,
            "role": k.role,
            "label": k.label,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
        }
        for k in keys
    ]


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


def _roster_payload(db: Session, school: School, section_id: str) -> dict:
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


@router.get("/sections/{section_id}/students")
def roster(
    section_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    return _roster_payload(db, school, section_id)


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
    # StudentSession: born the moment this student ever signed in with a shared report's
    # PIN (app.api.student), which is the ordinary path once a report has been shared --
    # so most students worth deleting have one, and its FK has no DB-level cascade.
    for model in (TestSession, MarkEvent, StudentReport, ProposedMark, DataQualityFlag, StudentSession):
        db.execute(model.__table__.delete().where(model.student_id == student_id))
    for document in db.scalars(
        select(ScanDocument).where(ScanDocument.student_id == student_id)
    ):
        db.delete(document)
    # A resolved grid-sheet row is about the sheet, not solely this student -- nulling the
    # match (back to "unmatched", the same state before it was ever resolved) rather than
    # deleting the row keeps the sheet's other students' rows intact.
    db.execute(
        GridSheetRow.__table__.update()
        .where(GridSheetRow.student_id == student_id)
        .values(student_id=None, status="unmatched")
    )
    db.delete(student)
    db.commit()


def _cohort_payload(db: Session, school: School, section_id: str) -> dict:
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


@router.get("/cohort/{section_id}")
def cohort(
    section_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    return _cohort_payload(db, school, section_id)


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
    for group in subject_groups():
        books = []
        group_chapters = group_board_units = group_chunks = group_embedded = 0
        for curriculum in group.members:
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
            books.append({
                "subject_code": curriculum.subject_code,
                "label": curriculum.subject_label,
                "grade": curriculum.grade,
                "chapters": len(curriculum.chapters),
                "board_units": len(curriculum.units),
                #: a book with no embedded content cannot map a question, and a screen
                #: that offers it anyway is offering a dead end
                "book_loaded": embedded > 0,
                "chunks": chunks,
                "chunks_embedded": embedded,
            })
            group_chapters += len(curriculum.chapters)
            group_board_units += len(curriculum.units)
            group_chunks += chunks
            group_embedded += embedded
        out.append({
            "group_code": group.group_code,
            "group_label": group.group_label,
            #: back-compat for a single-book group (every subject but English/Hindi): the
            #: same fields a book itself carries, so an existing caller reading these
            #: top-level fields on a one-book subject keeps working unchanged
            "subject_code": group.group_code,
            "label": group.group_label,
            "grade": group.members[0].grade,
            "chapters": group_chapters,
            "board_units": group_board_units,
            "book_loaded": group_embedded > 0,
            "chunks": group_chunks,
            "chunks_embedded": group_embedded,
            "books": books,
        })
    return {"subjects": out}


# ---------------------------------------------------------------------------------
# Teacher: scoped reads (any signed-in teacher key, filtered to their own assignments)
# ---------------------------------------------------------------------------------

def _teacher_home(staff: Staff) -> School:
    """A teacher key is school-scoped exactly like a principal key -- see Staff's own
    docstring. Only routes that have already checked ``staff.is_teacher`` call this."""
    assert staff.home is not None, "a teacher key always names its school"
    return staff.home


@router.get("/teacher/sections/{section_id}/students")
def teacher_roster(
    section_id: str,
    staff: Staff = Depends(current_staff),
    db: Session = Depends(get_session),
) -> dict:
    """The same roster a principal sees for one class -- but only for a section this
    teacher key holds a class or subject assignment on. Anyone else's key is refused
    with 404, the same as a section outside their own school would be."""
    if not staff.is_teacher:
        raise HTTPException(403, "this route is for teacher keys; use /admin/sections/{id}/students")
    require_teacher_read_scope(staff, db, section_id)
    return _roster_payload(db, _teacher_home(staff), section_id)


@router.get("/teacher/papers")
def teacher_papers(
    staff: Staff = Depends(current_staff), db: Session = Depends(get_session)
) -> dict:
    """Every paper this teacher key may author -- one whose subject_code is one they
    hold a subject assignment for, whatever section that assignment names, or every
    paper in the school for the exam cell, which holds that right for every subject
    without needing an assignment row per one. A class-only, non-exam-cell teacher (no
    subject assignment at all) gets an empty list, the same as they get no
    paper-authoring route to act on one anyway.

    Reuses marks.assessment_summaries so this list can never show a different "stage" for
    a paper than the principal's own /assessments listing does.
    """
    if not staff.is_teacher:
        raise HTTPException(403, "this route is for teacher keys; use GET /assessments")
    assert staff.home is not None
    from app.api.marks import assessment_summaries

    query = select(Assessment).where(Assessment.school_id == staff.home.id)
    if not staff.exam_cell:
        subjects = teacher_subject_codes(staff, db)
        if not subjects:
            return {"assessments": []}
        query = query.where(Assessment.subject_code.in_(subjects))
    assessments = list(db.scalars(query.order_by(Assessment.created_at.desc())))
    return {"assessments": assessment_summaries(db, assessments)}


@router.get("/teacher/cohort/{section_id}")
def teacher_cohort(
    section_id: str,
    staff: Staff = Depends(current_staff),
    db: Session = Depends(get_session),
) -> dict:
    if not staff.is_teacher:
        raise HTTPException(403, "this route is for teacher keys; use /admin/cohort/{id}")
    require_teacher_read_scope(staff, db, section_id)
    return _cohort_payload(db, _teacher_home(staff), section_id)


@router.get("/teacher/sections")
def teacher_sections(
    staff: Staff = Depends(current_staff), db: Session = Depends(get_session)
) -> dict:
    """Every section this teacher key may open at all, with what it may do there --
    the menu the teacher shell renders instead of guessing from the assignment rows
    itself. The exam cell gets every section in the school, marked read/enter-everywhere,
    without needing an assignment row per section."""
    if not staff.is_teacher:
        raise HTTPException(403, "this route is for teacher keys")
    assert staff.home is not None
    if staff.exam_cell:
        all_sections = list(db.scalars(select(Section).where(Section.school_id == staff.home.id)))
        all_subject_codes = [c.subject_code for g in subject_groups() for c in g.members]
        return {
            "sections": [
                {
                    "section_id": s.id,
                    "can_read_all_subjects": True,
                    "subjects": all_subject_codes,
                    "label": f"Class {s.grade}-{s.name}",
                    "student_path": f"/t/{s.id}",
                }
                for s in all_sections
            ]
        }
    rows = teacher_assignments(staff, db)
    by_section: dict[str, dict] = {}
    for a in rows:
        entry = by_section.setdefault(
            a.section_id, {"section_id": a.section_id, "can_read_all_subjects": False, "subjects": []}
        )
        if a.type == "class":
            entry["can_read_all_subjects"] = True
        elif a.subject_code:
            entry["subjects"].append(a.subject_code)
    sections = {
        s.id: s for s in db.scalars(select(Section).where(Section.id.in_(by_section.keys())))
    } if by_section else {}
    out = []
    for section_id, entry in by_section.items():
        section = sections.get(section_id)
        out.append({
            **entry,
            "label": f"Class {section.grade}-{section.name}" if section else None,
            "student_path": f"/t/{section_id}" if section else None,
        })
    return {"sections": out}


def _teacher_report_scope_ok(staff: Staff, db: Session, student: StudentProfile) -> bool:
    """Whether this staff key may act on this student's reports.

    Only a true cross-school admin key (``role == "admin"`` naming no school) reaches any
    student -- that is what ``home is None`` means for admin, exactly as
    ``school_in_scope`` treats it. The school's own legacy ``api_key`` is also
    ``role == "admin"`` but names one school (``home`` is set), so it is bound to it here
    the same as a principal; without this it would silently reach every other school's
    students too.
    """
    if staff.is_admin and staff.home is None:
        return True
    if staff.home is None or student.school_id != staff.home.id:
        return False
    if staff.manages_school:
        return True
    return teacher_can_read(staff, db, student.section_id)


def _hash_pin(pin: str, student_id: str) -> str:
    """Salted by student_id so the same four digits never collide across students in the
    hash column -- the PIN itself is never stored, same rule as every credential here."""
    return hashlib.sha256(f"{pin}:{student_id}".encode()).hexdigest()


def _issued_report_view(record: StudentReport) -> dict:
    return {
        "report_id": record.id,
        "assessment_id": record.assessment_id,
        "student_id": record.student_id,
        "issued_by": record.issued_by,
        "issued_at": record.created_at.isoformat() if record.created_at else None,
        "earned": float(record.earned),
        "available": float(record.available),
        "assessment_title": record.payload.get("assessment_title"),
        "shared": record.shared_at is not None and record.share_revoked_at is None,
        "shared_at": record.shared_at.isoformat() if record.shared_at else None,
        "shared_by": record.shared_by,
    }


@router.get("/teacher/students/{student_id}/reports")
def teacher_student_reports(
    student_id: str,
    staff: Staff = Depends(current_staff),
    db: Session = Depends(get_session),
) -> dict:
    """Every report issued for this student -- the list "Share" is chosen from. A
    principal/admin reaches every student in their school; a teacher only one their
    class or subject assignment actually covers."""
    student = db.get(StudentProfile, student_id)
    if student is None or not _teacher_report_scope_ok(staff, db, student):
        raise HTTPException(404, "no such student")
    records = db.scalars(
        select(StudentReport)
        .where(StudentReport.student_id == student_id, StudentReport.school_id == student.school_id)
        .order_by(StudentReport.created_at.desc())
    ).all()
    return {"reports": [_issued_report_view(r) for r in records]}


class ShareReportIn(BaseModel):
    by: str = Field(default="", max_length=120)


@router.post("/teacher/reports/{report_id}/share", status_code=201)
def share_report_with_student(
    report_id: str,
    body: ShareReportIn,
    staff: Staff = Depends(current_staff),
    db: Session = Depends(get_session),
) -> dict:
    """Issue a fresh PIN for this report and mark it shared.

    Re-sharing an already-shared report is allowed and expected -- a lost slip of paper
    is common, and issuing a new PIN simply replaces the old one; the old PIN stops
    working the instant this returns, same "one live secret" rule as reissuing a staff
    key. Shown once, same as every other credential this deployment issues.
    """
    record = db.get(StudentReport, report_id)
    if record is None:
        raise HTTPException(404, "no such report")
    student = db.get(StudentProfile, record.student_id)
    if student is None or not _teacher_report_scope_ok(staff, db, student):
        raise HTTPException(404, "no such report")

    pin = f"{secrets.randbelow(1_000_000):06d}"
    record.share_pin_hash = _hash_pin(pin, record.student_id)
    record.shared_at = datetime.now(UTC)
    record.shared_by = body.by.strip() or "teacher"
    record.share_revoked_at = None
    db.commit()
    db.refresh(record)

    view = _issued_report_view(record)
    view["pin"] = pin
    view["class_code"] = student.section_id
    view["roll_no"] = student.roll_no
    view["pin_notice"] = (
        "Shown once. Give the PIN, the class code above and the roll number to the "
        "student or their parent -- there is no route that reads the PIN back, only "
        "share again to issue a new one."
    )
    return view


@router.post("/teacher/reports/{report_id}/unshare")
def unshare_report(
    report_id: str,
    staff: Staff = Depends(current_staff),
    db: Session = Depends(get_session),
) -> dict:
    """Take a report back. The PIN already handed out stops working immediately, and any
    student session that was opened by way of it keeps existing but this report drops
    out of what it can read (checked fresh on every read, not cached into the session)."""
    record = db.get(StudentReport, report_id)
    if record is None:
        raise HTTPException(404, "no such report")
    student = db.get(StudentProfile, record.student_id)
    if student is None or not _teacher_report_scope_ok(staff, db, student):
        raise HTTPException(404, "no such report")
    if record.shared_at is not None and record.share_revoked_at is None:
        record.share_revoked_at = datetime.now(UTC)
        db.commit()
        db.refresh(record)
    return _issued_report_view(record)


# ---------------------------------------------------------------------------------
# Teacher key issuance and assignment management -- principal-scoped (a principal
# manages the teachers of their own school; issuing an admin or principal key is still
# operator-only, in app.api.platform).
# ---------------------------------------------------------------------------------

class TeacherAssignmentIn(BaseModel):
    type: str = Field(...)
    section_id: str
    subject_code: str | None = None

    def _validate(self, db: Session, school: School) -> None:
        if self.type not in TEACHER_ASSIGNMENT_TYPES:
            raise HTTPException(422, f"type must be one of {', '.join(TEACHER_ASSIGNMENT_TYPES)}")
        section = db.get(Section, self.section_id)
        if section is None or section.school_id != school.id:
            raise HTTPException(404, "no such class in this school")
        if self.type == "subject" and not self.subject_code:
            raise HTTPException(422, "a subject assignment needs subject_code")
        if self.type == "class" and self.subject_code:
            raise HTTPException(422, "a class assignment covers every subject; leave subject_code unset")


class TeacherKeyIn(BaseModel):
    label: str = Field(default="", max_length=120)
    assignments: list[TeacherAssignmentIn] = Field(default_factory=list)


def _assignment_view(a: TeacherAssignment, sections: dict[str, Section]) -> dict:
    section = sections.get(a.section_id)
    return {
        "id": a.id,
        "type": a.type,
        "section_id": a.section_id,
        "section_label": f"Class {section.grade}-{section.name}" if section else None,
        "subject_code": a.subject_code,
    }


def _teacher_view(db: Session, key: StaffKey) -> dict:
    rows = list(
        db.scalars(select(TeacherAssignment).where(TeacherAssignment.staff_key_id == key.id))
    )
    section_ids = {a.section_id for a in rows}
    sections = {
        s.id: s for s in db.scalars(select(Section).where(Section.id.in_(section_ids)))
    } if section_ids else {}
    return {
        "id": key.id,
        "role": key.role,
        "label": key.label,
        # A principal already has full authority over their own school (see
        # Staff.manages_school); they issue and revoke these keys, so seeing the live
        # value back is not a wider grant, only the same authority surfaced.
        "api_key": key.api_key,
        "created_at": key.created_at.isoformat() if key.created_at else None,
        "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
        "assignments": [_assignment_view(a, sections) for a in rows],
    }


@router.get("/teachers")
def list_teachers(
    school: School = Depends(require_admin), db: Session = Depends(get_session)
) -> list[dict]:
    """Every teacher key issued for this school, with their assignments and live key.

    ``require_admin`` already scopes ``school`` to the caller's own -- this can never
    surface a teacher key belonging to a different school.
    """
    keys = db.scalars(
        select(StaffKey)
        .where(StaffKey.school_id == school.id, StaffKey.role == "teacher")
        .order_by(StaffKey.revoked_at.is_not(None), StaffKey.created_at)
    ).all()
    return [_teacher_view(db, k) for k in keys]


@router.post("/teachers", status_code=201)
def create_teacher(
    body: TeacherKeyIn,
    school: School = Depends(require_admin), db: Session = Depends(get_session),
) -> dict:
    """Issue a teacher key for this school, with an initial set of assignments.

    Same "shown once" pattern as every other key this deployment issues: the raw key
    comes back in this response and nowhere else.
    """
    for spec in body.assignments:
        spec._validate(db, school)

    key = StaffKey(
        school_id=school.id, api_key=secrets.token_urlsafe(24),
        role="teacher", label=body.label.strip(),
    )
    db.add(key)
    db.flush()
    for spec in body.assignments:
        db.add(TeacherAssignment(
            staff_key_id=key.id, type=spec.type,
            section_id=spec.section_id, subject_code=spec.subject_code,
        ))
    db.commit()
    db.refresh(key)
    view = _teacher_view(db, key)
    view["api_key"] = key.api_key
    view["api_key_notice"] = (
        "Give it to the teacher named now. It's also visible from Manage Teachers "
        "later if you need to look it up again."
    )
    return view


@router.post("/teachers/{key_id}/assignments", status_code=201)
def add_teacher_assignment(
    key_id: str, body: TeacherAssignmentIn,
    school: School = Depends(require_admin), db: Session = Depends(get_session),
) -> dict:
    key = db.get(StaffKey, key_id)
    if key is None or key.school_id != school.id or key.role != "teacher":
        raise HTTPException(404, "no such teacher key")
    body._validate(db, school)
    existing = db.scalar(
        select(TeacherAssignment).where(
            TeacherAssignment.staff_key_id == key.id,
            TeacherAssignment.type == body.type,
            TeacherAssignment.section_id == body.section_id,
            TeacherAssignment.subject_code == body.subject_code,
        )
    )
    if existing is None:
        db.add(TeacherAssignment(
            staff_key_id=key.id, type=body.type,
            section_id=body.section_id, subject_code=body.subject_code,
        ))
        db.commit()
        db.refresh(key)
    return _teacher_view(db, key)


@router.delete("/teachers/{key_id}/assignments/{assignment_id}", status_code=204)
def remove_teacher_assignment(
    key_id: str, assignment_id: str,
    school: School = Depends(require_admin), db: Session = Depends(get_session),
) -> None:
    key = db.get(StaffKey, key_id)
    if key is None or key.school_id != school.id or key.role != "teacher":
        raise HTTPException(404, "no such teacher key")
    row = db.get(TeacherAssignment, assignment_id)
    if row is None or row.staff_key_id != key.id:
        raise HTTPException(404, "no such assignment")
    db.delete(row)
    db.commit()


@router.post("/teachers/{key_id}/revoke")
def revoke_teacher(
    key_id: str,
    school: School = Depends(require_admin), db: Session = Depends(get_session),
) -> dict:
    """Stop a teacher key working. The row (and its assignments) stay -- who held access
    to which class, and until when, is the first question asked after anything goes
    wrong, same as every other key revocation in this codebase."""
    key = db.get(StaffKey, key_id)
    if key is None or key.school_id != school.id or key.role != "teacher":
        raise HTTPException(404, "no such teacher key")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        db.commit()
    return _teacher_view(db, key)


class TeacherLabelIn(BaseModel):
    label: str = Field(..., max_length=120)


@router.patch("/teachers/{key_id}")
def rename_teacher(
    key_id: str, body: TeacherLabelIn,
    school: School = Depends(require_admin), db: Session = Depends(get_session),
) -> dict:
    """Fix a teacher's name without touching the key or their assignments -- the only
    thing a typo in ``label`` should cost."""
    key = db.get(StaffKey, key_id)
    if key is None or key.school_id != school.id or key.role != "teacher":
        raise HTTPException(404, "no such teacher key")
    label = body.label.strip()
    if not label:
        raise HTTPException(422, "label cannot be empty")
    key.label = label
    db.commit()
    return _teacher_view(db, key)


@router.post("/teachers/{key_id}/reissue")
def reissue_teacher_key(
    key_id: str,
    school: School = Depends(require_admin), db: Session = Depends(get_session),
) -> dict:
    """Replace a teacher's key with a fresh one, keeping their assignments and row --
    for a key that was lost or a person who never received theirs.

    The old key stops working the instant the new one is written, the same way a
    revoke does; unlike revoke, this key is not dead, it has a new secret. A revoked
    key cannot be reissued -- it stays dead, on purpose, and a school that wants that
    person back issues them a new key instead, a deliberate act rather than one route
    silently reviving a credential someone chose to kill.
    """
    key = db.get(StaffKey, key_id)
    if key is None or key.school_id != school.id or key.role != "teacher":
        raise HTTPException(404, "no such teacher key")
    if key.revoked_at is not None:
        raise HTTPException(409, "this key was revoked; issue a new teacher instead")
    key.api_key = secrets.token_urlsafe(24)
    db.commit()
    db.refresh(key)
    view = _teacher_view(db, key)
    view["api_key"] = key.api_key
    view["api_key_notice"] = (
        "Shown once. The old key stopped working the moment this one was issued -- "
        "give this to the teacher named and store it somewhere safe."
    )
    return view
