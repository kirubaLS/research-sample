"""Request-scoped dependencies. Tenancy is resolved once and applied to every query."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import (
    Assessment,
    GridSheetJob,
    GridSheetRow,
    School,
    ScanDocument,
    StaffKey,
    StudentProfile,
    TeacherAssignment,
)


@dataclass(frozen=True)
class Staff:
    """Who is asking, and with what authority.

    ``home`` is the school the key itself names. A principal has one and it is the only
    school they can ever reach. An admin has none, because an admin works across schools
    and says which one per request. A teacher also has one, exactly like a principal --
    what makes a teacher's authority narrower is not the school but ``staff_key_id``,
    which is looked up against TeacherAssignment by the helpers below.
    """

    role: str
    home: School | None
    staff_key_id: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_teacher(self) -> bool:
        return self.role == "teacher"

    @property
    def manages_school(self) -> bool:
        """Full authority over one school's roster, credentials and marks engine.

        A principal has this now, same as an admin -- the "admin" role exists at all
        only for the cross-school, no-home case (the operator's own deputies, resolved
        with ``home=None``), not as a second, stronger per-school role a principal has
        to be handed instead of just being one. ``is_admin`` stays narrower (used by
        ``school_in_scope`` to decide whether a request has to name its school) because
        a principal's key still always names exactly one school via ``home`` and must
        never gain the "which school?" cross-school behavior an admin key has.
        """
        return self.role in ("admin", "principal")


def teacher_assignments(staff: Staff, db: Session) -> list[TeacherAssignment]:
    """Every row naming what this teacher key may touch. Empty for any other role."""
    if not staff.is_teacher or staff.staff_key_id is None:
        return []
    return list(
        db.scalars(
            select(TeacherAssignment).where(TeacherAssignment.staff_key_id == staff.staff_key_id)
        )
    )


def teacher_can_read(staff: Staff, db: Session, section_id: str, subject_code: str | None = None) -> bool:
    """Read access to a section's roster/marks: a class assignment for it (any subject),
    or, when ``subject_code`` is given, a subject assignment naming both."""
    for a in teacher_assignments(staff, db):
        if a.section_id != section_id:
            continue
        if a.type == "class":
            return True
        # A subject assignment always covers reading the section it names; when the
        # caller also names a subject (e.g. deciding whether to show one subject's
        # marks), it must additionally match. With no subject_code given -- "may this
        # teacher open this section at all" -- holding any subject assignment there is
        # enough.
        if a.type == "subject" and (subject_code is None or a.subject_code == subject_code):
            return True
    return False


def teacher_can_enter_marks(staff: Staff, db: Session, section_id: str, subject_code: str) -> bool:
    """Marks-entry rights: only a subject assignment naming this exact section and
    subject. A class assignment is read-only outside the class teacher's own subject
    (spec §10.2's default) -- it never reaches this far."""
    return any(
        a.type == "subject" and a.section_id == section_id and a.subject_code == subject_code
        for a in teacher_assignments(staff, db)
    )


def require_teacher_read_scope(
    staff: Staff, db: Session, section_id: str, subject_code: str | None = None
) -> None:
    if staff.is_teacher and not teacher_can_read(staff, db, section_id, subject_code):
        # 404, not 403: a teacher must not learn that a section/subject they don't hold
        # exists at all, matching this file's convention for every other scope check.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")


def require_teacher_marks_scope(
    staff: Staff, db: Session, section_id: str, subject_code: str
) -> None:
    if staff.is_teacher and not teacher_can_enter_marks(staff, db, section_id, subject_code):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")


def current_staff(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_session),
) -> Staff:
    """Resolve a key to a role, and to the school it names if it names one.

    A school's own ``api_key`` predates per-person keys and still works, as an admin bound
    to that one school, so no deployment loses access.
    """
    school = db.scalar(select(School).where(School.api_key == x_api_key))
    if school is not None:
        return Staff(role="admin", home=school)

    # The operator key used to also open this side, as an admin belonging to no school --
    # deliberately removed. It reads as a convenience ("scan a paper without minting a
    # second credential") but it means the one secret that can create every school on the
    # deployment also signs in on the same form a teacher or principal uses, which is
    # confusing at best and is exactly the "why does the operator key unlock /admin"
    # question that got this removed. The operator key now opens only require_platform_admin
    # (/platform and nothing else) -- if the person running the deployment wants to act
    # inside a school, they issue themselves an admin key for it, the same as anyone else.

    staff = db.scalar(select(StaffKey).where(StaffKey.api_key == x_api_key))
    # A revoked key is treated exactly like one that never existed: answering differently
    # would tell whoever kept it that it was once real.
    if staff is None or staff.revoked_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    from datetime import UTC, datetime as _datetime

    staff.last_used_at = _datetime.now(UTC)
    db.commit()
    return Staff(role=staff.role, home=staff.school, staff_key_id=staff.id)


def school_in_scope(staff: Staff, requested: str | None, db: Session) -> School:
    """Which school this request is about.

    For anyone who is not an admin the answer comes from their key and nothing else. The
    requested id is not consulted, not compared and not reported on -- there is simply no
    path by which a principal's request reads a school from the request, which is a
    stronger guarantee than checking that it matches.
    """
    if not staff.is_admin:
        assert staff.home is not None, "a non-admin key always names its school"
        return staff.home

    if requested:
        school = db.get(School, requested)
        if school is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
        return school
    if staff.home is not None:
        return staff.home
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "this key works across schools, so the request has to say which one. Send the "
        "school id in the X-School-Id header.",
    )


def require_staff(
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> Staff:
    """Any signed-in member of staff. Read-only surfaces use this."""
    school_in_scope(staff, x_school_id, db)      # rejects an admin who named no school
    return staff


def require_scanner(
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> School:
    """Reading a paper, storing a script, entering marks: any signed-in member of staff.

    A principal does this as well as an admin. It is a deliberate widening of what a
    principal may do -- they can now produce marks, not only read them -- so the earlier
    property that a signed-in dashboard could not alter a mark no longer holds. Every mark
    still records who confirmed it, which is what a disputed figure is actually checked
    against.

    What stays admin-only is the roster and the school itself: who the students are, and
    which credentials exist.

    A teacher key never reaches this generic surface -- it has no notion of section or
    subject, and every one of these routes touches a whole school's roster/marks engine.
    Teachers act through their own scoped routes instead (see admin.py's
    ``/admin/teacher/...`` surface and gridsheets.py's per-section, per-subject checks).
    """
    if staff.is_teacher:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "a teacher key acts through its own scoped routes, not this one",
        )
    return school_in_scope(staff, x_school_id, db)


def require_scanner_or_teacher(
    assessment_id: str,
    section_id: str,
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> School:
    """Reading a class mark-entry sheet for one section of one paper.

    Everyone require_scanner already allowed keeps working exactly as before. A teacher
    key is additionally let through here -- and only here, and only as far as
    TeacherAssignment says -- because this is the one gridsheet route shaped around a
    single section and a single assessment (hence a single subject), which is precisely
    what a subject assignment is scoped to. A class assignment does not reach this: spec
    §10.2 makes a class teacher read-only outside their own subject by default.
    """
    if not staff.is_teacher:
        return school_in_scope(staff, x_school_id, db)
    assert staff.home is not None, "a teacher key always names its school"
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != staff.home.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    require_teacher_marks_scope(staff, db, section_id, assessment.subject_code)
    return staff.home


def teacher_subject_codes(staff: Staff, db: Session) -> set[str]:
    """Every subject a teacher key may author a paper for. A class assignment names no
    subject and grants nothing here -- paper-authoring, like marks entry, is a subject
    right (spec §10.2's default)."""
    return {
        a.subject_code
        for a in teacher_assignments(staff, db)
        if a.type == "subject" and a.subject_code
    }


def require_paper_scope(
    assessment_id: str,
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> School:
    """Authoring one paper: create-questions-aside, this covers scan/edit/confirm/map and
    reading the same. An Assessment is not section-scoped -- it is shared by every section
    that sits it -- so a subject assignment on *any* section is enough; unlike marks entry
    there is no single section to check against. A class-only teacher never reaches this,
    the same as they never reach marks entry.
    """
    if not staff.is_teacher:
        return school_in_scope(staff, x_school_id, db)
    assert staff.home is not None, "a teacher key always names its school"
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != staff.home.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    if assessment.subject_code not in teacher_subject_codes(staff, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return staff.home


def require_marks_scope_for_student(
    assessment_id: str,
    student_id: str,
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> School:
    """Entering/reading one student's marks for one paper -- the per-student sibling of
    require_scanner_or_teacher, which is shaped around a whole section instead. Scoped by
    the student's own section and the paper's subject, exactly the same
    teacher_can_enter_marks check, just reached from a student id instead of a section id.
    """
    if not staff.is_teacher:
        return school_in_scope(staff, x_school_id, db)
    assert staff.home is not None
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != staff.home.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    student = db.get(StudentProfile, student_id)
    if student is None or student.school_id != staff.home.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    require_teacher_marks_scope(staff, db, student.section_id, assessment.subject_code)
    return staff.home


def require_documents_list_scope(
    assessment_id: str,
    student_id: str | None = None,
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> School:
    """Listing a paper's stored documents. With no student_id this is the paper's own
    question-paper upload (Papers screen) -- subject scope. With one, it is that
    student's own answer-sheet upload (Enter Marks screen) -- that student's
    section+subject scope. Matches the same two screens' own request shapes; a teacher
    can never widen this by adding or dropping the query param, since which branch runs
    is decided here, not by what the caller claims to want.
    """
    if not staff.is_teacher:
        return school_in_scope(staff, x_school_id, db)
    if student_id:
        return require_marks_scope_for_student(assessment_id, student_id, staff, x_school_id, db)
    return require_paper_scope(assessment_id, staff, x_school_id, db)


def require_document_scope(
    document_id: str,
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> School:
    """Confirming or deleting one stored document, reached only by its own id. Which
    scope rule applies is decided from the document's own ``kind`` -- a question paper is
    subject-scoped, an answer sheet is that one student's section+subject, a mark grid is
    its section+subject -- never from anything the caller sends, so a teacher cannot claim
    a document is one kind to dodge the other kind's check.
    """
    if not staff.is_teacher:
        return school_in_scope(staff, x_school_id, db)
    assert staff.home is not None
    document = db.get(ScanDocument, document_id)
    if document is None or document.school_id != staff.home.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    assessment = db.get(Assessment, document.assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    if document.kind == "question_paper":
        if assessment.subject_code not in teacher_subject_codes(staff, db):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    elif document.kind == "answer_sheet":
        student = db.get(StudentProfile, document.student_id) if document.student_id else None
        if student is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        require_teacher_marks_scope(staff, db, student.section_id, assessment.subject_code)
    elif document.kind == "mark_grid":
        row = db.scalar(select(GridSheetRow).where(GridSheetRow.document_id == document.id))
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        require_teacher_marks_scope(staff, db, row.section_id, assessment.subject_code)
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return staff.home


def require_gridsheet_job_scope(
    assessment_id: str,
    job_id: str,
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> School:
    """Polling a grid-sheet read job -- the job itself carries the section it was read
    for, the same section upload_gridsheet/upload_single_script already checked."""
    if not staff.is_teacher:
        return school_in_scope(staff, x_school_id, db)
    assert staff.home is not None
    job = db.get(GridSheetJob, job_id)
    if job is None or job.assessment_id != assessment_id or job.school_id != staff.home.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    require_teacher_marks_scope(staff, db, job.section_id, assessment.subject_code)
    return staff.home


def require_gridsheet_document_scope(
    assessment_id: str,
    document_id: str,
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> School:
    """Reviewing, resolving a row on, or confirming a grid-sheet document -- the document
    has no section column of its own, but every row it produced does, and a document is
    always read for exactly one section."""
    if not staff.is_teacher:
        return school_in_scope(staff, x_school_id, db)
    assert staff.home is not None
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != staff.home.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    row = db.scalar(select(GridSheetRow).where(GridSheetRow.document_id == document_id))
    if row is None or row.assessment_id != assessment_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    require_teacher_marks_scope(staff, db, row.section_id, assessment.subject_code)
    return staff.home


def require_admin_staff(staff: Staff = Depends(current_staff)) -> Staff:
    """Anything that changes a school's data, and the whole marks engine.

    A principal has full authority over their own school -- the roster, marks entry,
    Manage Teachers, everything -- same as an admin key. A teacher is refused with 403
    rather than 404: unlike a wrong key, they are genuinely signed in, and telling them
    the surface exists but is not theirs is the honest answer.
    """
    if not staff.manages_school:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "this needs a principal or admin key. A teacher key acts through its own "
            "scoped routes instead.",
        )
    return staff


def current_school(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_session),
) -> School:
    school = db.scalar(select(School).where(School.api_key == x_api_key))
    if school is None:
        # 404 rather than 403: a wrong key must not confirm that a school exists
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return school


def require_admin(
    staff: Staff = Depends(require_admin_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> School:
    """The school an admin request is acting on. Students never reach these routes."""
    return school_in_scope(staff, x_school_id, db)


def require_reader(
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> School:
    """The school a read is about -- an admin's chosen one, or a principal's only one.

    A teacher key is refused here too, for the same reason as require_scanner: this
    surface has no section/subject filter, and a teacher must never see a subject or
    section outside their own TeacherAssignment rows, including in a list. Their reads
    go through admin.py's teacher-scoped roster/cohort routes instead.
    """
    if staff.is_teacher:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "a teacher key acts through its own scoped routes, not this one",
        )
    return school_in_scope(staff, x_school_id, db)


def require_platform_admin(
    x_platform_key: str | None = Header(default=None, alias="X-Platform-Key"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_session),
) -> None:
    """Creating schools, loading books, issuing keys.

    Two credentials open this, and only two:

    * the operator key, ``YAADHUM_PLATFORM_ADMIN_KEY``, which bootstraps a deployment and
      is the only way to issue the first admin key;
    * an **admin** staff key that names no school, because an admin creates schools and
      works across them -- that is the whole point of the role.

    A principal key never opens it, and neither does a school's own key, which is an admin
    bound to one school: it can run that school, not create another. So one leaked school
    credential still cannot reach a second school's data.

    Unset ``platform_admin_key`` disables the operator key entirely rather than falling
    back to something weaker -- a deployment that forgot to configure it must fail closed.
    An admin staff key still works, because it was issued deliberately.
    """
    from app.config import get_settings

    expected = get_settings().platform_admin_key
    # constant time: a byte-by-byte comparison leaks the key one character at a time
    if expected and x_platform_key and secrets.compare_digest(x_platform_key, expected):
        return

    if x_api_key:
        staff = db.scalar(select(StaffKey).where(StaffKey.api_key == x_api_key))
        if staff and staff.revoked_at is None and staff.role == "admin" and staff.school_id is None:
            return

    # 404 for every failure, so a probe cannot tell a wrong key from a disabled console
    raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
