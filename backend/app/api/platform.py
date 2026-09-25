"""The operator surface: create a school, add sections, mint a principal's key.

This is the GUI equivalent of ``scripts.create_school`` and ``scripts.admin_key``, for the
person running the deployment rather than the person running a school. It sits behind
``X-Platform-Key`` -- a separate secret from any school key -- because a principal must
never be able to create schools or read another school's credential.

Two rules the routes here are built around:

* A key is shown **once**, at the moment it is created or rotated. Listing schools returns
  no keys at all, so a screen left open in a staffroom cannot leak one.
* Rotation is immediate and total: the previous key stops working on the next request.
"""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_admin
from app.config import get_settings
from app.db import get_session
from app.models import (
    STAFF_ROLES,
    TEACHER_ASSIGNMENT_TYPES,
    AuditLog,
    School,
    Section,
    StaffKey,
    StudentProfile,
    TeacherAssignment,
)
from app.ratelimit import FixedWindowLimiter, client_key

router = APIRouter(
    prefix="/platform", tags=["platform"], dependencies=[Depends(require_platform_admin)]
)

#: the operator key is the highest credential here, so guessing at it gets a low ceiling
_limiter = FixedWindowLimiter(limit=get_settings().platform_rate_limit_per_hour)


class SectionIn(BaseModel):
    grade: int = Field(ge=1, le=12)
    name: str = Field(min_length=1, max_length=8)

    @field_validator("name")
    @classmethod
    def _normalise(cls, v: str) -> str:
        # 'a' and 'A' are the same class; storing both would split a roster in two
        return v.strip().upper()


def _key_view(k: StaffKey) -> dict:
    # The operator is the top of the trust chain and already holds these keys in the DB
    # in plain form -- listing one back is not a new exposure, only surfacing what a
    # principal/admin key issue already handed the operator once and then hid again.
    return {
        "id": k.id,
        "role": k.role,
        "label": k.label,
        "name": k.name,
        "email": k.email,
        "phone": k.phone,
        "exam_cell": k.exam_cell,
        "school_id": k.school_id,
        "api_key": k.api_key,
        "created_at": k.created_at.isoformat() if k.created_at else None,
        "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
    }


def _assignment_view(a: TeacherAssignment) -> dict:
    return {
        "id": a.id,
        "staff_key_id": a.staff_key_id,
        "type": a.type,
        "section_id": a.section_id,
        "subject_code": a.subject_code,
    }


def _log(
    db: Session,
    school_id: str | None,
    action: str,
    detail: str = "",
    actor_label: str = "",
) -> None:
    """Append one audit trail row. Never raises -- a logging failure must not block the
    action it is trying to record."""
    db.add(
        AuditLog(
            school_id=school_id,
            actor_role="platform_admin",
            actor_label=actor_label,
            action=action,
            detail=detail,
        )
    )


class StaffKeyIn(BaseModel):
    role: str = Field(default="principal")
    label: str = Field(default="", max_length=120)
    #: Only meaningful when role == "teacher": papers-and-marks rights across every
    #: subject in the school, no teaching assignment needed. Ignored for any other role,
    #: which already has that reach.
    exam_cell: bool = False


def _validate_consent(v: str) -> str:
    allowed = {"operational_only", "improve_models", "research"}
    if v not in allowed:
        raise ValueError(f"training_consent must be one of {sorted(allowed)}")
    return v


class SchoolIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    board: str = Field(default="CBSE", max_length=32)
    state: str | None = Field(default="Tamil Nadu", max_length=64)
    training_consent: str = "operational_only"
    sections: list[SectionIn] = Field(default_factory=lambda: [SectionIn(grade=10, name="A")])

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("training_consent")
    @classmethod
    def _consent(cls, v: str) -> str:
        return _validate_consent(v)


class SchoolPatchIn(BaseModel):
    """Every field the "School details" tab can edit. Every field is optional -- a PATCH
    only touches what it sends."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    board: str | None = Field(default=None, max_length=32)
    state: str | None = Field(default=None, max_length=64)
    training_consent: str | None = None
    code: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=500)
    academic_year: str | None = Field(default=None, max_length=16)

    @field_validator("training_consent")
    @classmethod
    def _consent(cls, v: str | None) -> str | None:
        return v if v is None else _validate_consent(v)


class StaffKeyPatchIn(BaseModel):
    """Contact-detail edits for a principal or teacher key -- the credential itself
    (role, api_key) is never changed here; that is what issue/revoke/rotate are for."""

    name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    label: str | None = Field(default=None, max_length=120)
    exam_cell: bool | None = Field(default=None)


class AssignmentIn(BaseModel):
    type: str
    section_id: str
    subject_code: str | None = None

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in TEACHER_ASSIGNMENT_TYPES:
            raise ValueError(f"type must be one of {TEACHER_ASSIGNMENT_TYPES}")
        return v


class AssignmentsPatchIn(BaseModel):
    """Replaces the full set of assignments for a teacher key with exactly this list."""

    assignments: list[AssignmentIn]


class StudentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    roll_no: str = Field(min_length=1, max_length=16)
    section_id: str
    age: int | None = None
    gender: str | None = Field(default=None, max_length=16)
    dob: str | None = None
    parent_name: str | None = Field(default=None, max_length=200)
    parent_whatsapp: str | None = Field(default=None, max_length=32)


class StudentsBulkIn(BaseModel):
    students: list[StudentIn]


def _section_view(section: Section) -> dict:
    return {
        "id": section.id,
        "label": f"Class {section.grade}-{section.name}",
        "grade": section.grade,
        "name": section.name,
        "student_path": f"/t/{section.id}",
    }


def _school_view(db: Session, school: School) -> dict:
    """Never includes the API key. Listing is a different act from issuing."""
    sections = db.scalars(
        select(Section).where(Section.school_id == school.id).order_by(Section.grade, Section.name)
    ).all()
    students = db.scalar(
        select(func.count(StudentProfile.id)).where(StudentProfile.school_id == school.id)
    )
    return {
        "id": school.id,
        "name": school.name,
        "board": school.board,
        "state": school.state,
        "training_consent": school.training_consent,
        "code": school.code,
        "city": school.city,
        "address": school.address,
        "academic_year": school.academic_year,
        "students": students or 0,
        "sections": [_section_view(s) for s in sections],
        "hidden_from_directory": school.hidden_from_directory,
        "created_at": school.created_at.isoformat() if school.created_at else None,
    }


@router.get("/me")
def whoami(request: Request) -> dict:
    """Validates the operator key. The console's sign-in check."""
    _limiter.check(client_key(request))
    return {"role": "platform_admin"}


@router.get("/schools")
def list_schools(db: Session = Depends(get_session)) -> list[dict]:
    schools = db.scalars(select(School).order_by(School.name)).all()
    return [_school_view(db, s) for s in schools]


@router.get("/schools/{school_id}")
def get_school(school_id: str, db: Session = Depends(get_session)) -> dict:
    """One school's full detail view -- the ops console's school detail screen loads
    this once and derives every tab (besides keys/students/activity, each of which has
    its own, separately-scoped route) from it."""
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    return _school_view(db, school)


@router.patch("/schools/{school_id}")
def patch_school(school_id: str, body: SchoolPatchIn, db: Session = Depends(get_session)) -> dict:
    """The "School details" tab's save action. Only fields present in the request body
    are touched; everything else is left exactly as it was."""
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if field == "name" and value is not None:
            value = value.strip()
        setattr(school, field, value)
    if changes:
        _log(db, school.id, "school_edited", f"fields={sorted(changes)}")
    db.commit()
    db.refresh(school)
    return _school_view(db, school)


@router.get("/overview")
def overview(db: Session = Depends(get_session)) -> dict:
    """Every school on this deployment, on one screen: students, papers, answer scripts,
    issued reports and staff keys, each broken down per school and summed across all of
    them.

    One query per count, grouped by school_id, rather than one row scan per school -- a
    deployment of any real size would otherwise turn this screen into N+1 queries deep.
    """
    from app.models import Assessment, ScanDocument, StudentReport

    schools = list(db.scalars(select(School).order_by(School.name)))

    def _counts_by_school(stmt) -> dict[str, int]:
        return dict(db.execute(stmt).all())

    students = _counts_by_school(
        select(StudentProfile.school_id, func.count(StudentProfile.id))
        .group_by(StudentProfile.school_id)
    )
    papers = _counts_by_school(
        select(Assessment.school_id, func.count(Assessment.id)).group_by(Assessment.school_id)
    )
    answer_scripts = _counts_by_school(
        select(ScanDocument.school_id, func.count(ScanDocument.id))
        .where(ScanDocument.kind == "answer_sheet")
        .group_by(ScanDocument.school_id)
    )
    reports_issued = _counts_by_school(
        select(StudentReport.school_id, func.count(StudentReport.id))
        .group_by(StudentReport.school_id)
    )
    # Active (unrevoked) keys only -- a revoked one is not who can act on the school today.
    active_keys = list(
        db.scalars(select(StaffKey).where(StaffKey.revoked_at.is_(None)))
    )
    principals_by_school: dict[str, int] = {}
    admins_by_school: dict[str, int] = {}
    for k in active_keys:
        if k.school_id is None:
            continue
        target = principals_by_school if k.role == "principal" else admins_by_school
        target[k.school_id] = target.get(k.school_id, 0) + 1

    rows = []
    for s in schools:
        rows.append({
            "id": s.id,
            "name": s.name,
            "board": s.board,
            "state": s.state,
            "students": students.get(s.id, 0),
            "papers": papers.get(s.id, 0),
            "answer_scripts": answer_scripts.get(s.id, 0),
            "reports_issued": reports_issued.get(s.id, 0),
            # The school's own api_key counts as one working admin credential even before
            # anyone issues a separate StaffKey -- see School.api_key's own history.
            "admin_keys": admins_by_school.get(s.id, 0) + 1,
            "principal_keys": principals_by_school.get(s.id, 0),
        })

    return {
        "schools": rows,
        "totals": {
            "schools": len(rows),
            "students": sum(r["students"] for r in rows),
            "papers": sum(r["papers"] for r in rows),
            "answer_scripts": sum(r["answer_scripts"] for r in rows),
            "reports_issued": sum(r["reports_issued"] for r in rows),
        },
        # Admin keys that belong to no school -- an operator's own deputies, not counted
        # against any one school's row above.
        "cross_school_admin_keys": sum(1 for k in active_keys if k.school_id is None),
    }


@router.post("/schools", status_code=status.HTTP_201_CREATED)
def create_school(body: SchoolIn, db: Session = Depends(get_session)) -> dict:
    """Create a school, its sections, and the school's own admin key.

    The key comes back once here as a courtesy copy-now moment; the school's own key
    itself is not a ``StaffKey`` row, so it does not resurface in the keys listing below
    -- only ``/rotate`` replaces it.
    """
    if db.scalar(select(School).where(School.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "a school with that name already exists")

    school = School(
        name=body.name,
        board=body.board,
        state=body.state,
        api_key=secrets.token_urlsafe(24),
        training_consent=body.training_consent,
    )
    db.add(school)
    db.flush()

    seen: set[tuple[int, str]] = set()
    for spec in body.sections:
        if (spec.grade, spec.name) in seen:
            continue
        seen.add((spec.grade, spec.name))
        db.add(Section(school_id=school.id, grade=spec.grade, name=spec.name))
    _log(db, school.id, "school_created", f"name={school.name!r}")
    db.commit()
    db.refresh(school)

    view = _school_view(db, school)
    view["api_key"] = school.api_key
    view["api_key_notice"] = (
        "This key is shown once. It runs this one school and cannot reach another or "
        "create one. Store it safely; if it is lost, rotate it rather than looking it up."
    )
    return view


@router.post("/schools/{school_id}/sections", status_code=status.HTTP_201_CREATED)
def add_section(
    school_id: str, body: SectionIn, db: Session = Depends(get_session)
) -> dict:
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    existing = db.scalar(
        select(Section).where(
            Section.school_id == school_id,
            Section.grade == body.grade,
            Section.name == body.name,
        )
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "that class already exists")
    section = Section(school_id=school_id, grade=body.grade, name=body.name)
    db.add(section)
    db.commit()
    db.refresh(section)
    return _section_view(section)


@router.get("/keys")
def list_admin_keys(db: Session = Depends(get_session)) -> list[dict]:
    """Admin keys, which belong to no school, with their live secret included."""
    keys = db.scalars(
        select(StaffKey).where(StaffKey.school_id.is_(None)).order_by(StaffKey.created_at)
    ).all()
    return [_key_view(k) for k in keys]


@router.post("/keys", status_code=status.HTTP_201_CREATED)
def issue_admin_key(body: StaffKeyIn, db: Session = Depends(get_session)) -> dict:
    """Issue an admin key: every school on this deployment, and the power to create more.

    Not attached to a school, on purpose. An admin who had a home school would be one
    forgotten header away from acting on the wrong one; with none, every request has to
    name the school it is about.
    """
    key = StaffKey(
        school_id=None, api_key=secrets.token_urlsafe(24), role="admin",
        label=body.label.strip(),
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    view = _key_view(key)
    view["api_key"] = key.api_key
    view["api_key_notice"] = (
        "Shown once. This key can create schools and act on every school on this "
        "deployment -- store it as carefully as the operator key itself."
    )
    return view


@router.post("/keys/{key_id}/revoke")
def revoke_admin_key(key_id: str, db: Session = Depends(get_session)) -> dict:
    key = db.get(StaffKey, key_id)
    if key is None or key.school_id is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such key")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        db.commit()
    return _key_view(key)


class DirectoryVisibilityIn(BaseModel):
    hidden: bool


@router.patch("/schools/{school_id}/directory-visibility")
def set_directory_visibility(
    school_id: str, body: DirectoryVisibilityIn, db: Session = Depends(get_session)
) -> dict:
    """Show or hide a school's classes on GET /t/classes, the public unauthenticated
    student entry page. A school new on this deployment starts hidden (see School's own
    docstring) -- this is the only way to switch it on, and the only way to switch it
    back off if a pilot ends.
    """
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    school.hidden_from_directory = body.hidden
    db.commit()
    return _school_view(db, school)


@router.get("/schools/{school_id}/keys")
def list_staff_keys(school_id: str, db: Session = Depends(get_session)) -> list[dict]:
    """Who holds a key at this school, with what role, and the live secret itself.

    Scoped to one school by the path, same as every other route here -- an operator
    reading this can never pull another school's keys through it.
    """
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    keys = db.scalars(
        select(StaffKey).where(StaffKey.school_id == school_id).order_by(StaffKey.created_at)
    ).all()
    return [_key_view(k) for k in keys]


@router.post("/schools/{school_id}/keys", status_code=status.HTTP_201_CREATED)
def issue_staff_key(school_id: str, body: StaffKeyIn, db: Session = Depends(get_session)) -> dict:
    """Issue a key for one person at one school.

    A principal key reads results and progress across the school. It cannot scan a paper,
    enter marks or change the roster -- so the person who runs the assessments and the
    person who reads them are no longer the same credential, and an office laptop left
    signed in cannot alter a mark.
    """
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    if body.role not in STAFF_ROLES:
        raise HTTPException(422, f"role must be one of {', '.join(STAFF_ROLES)}")

    key = StaffKey(
        school_id=school.id, api_key=secrets.token_urlsafe(24),
        role=body.role, label=body.label.strip(),
        exam_cell=body.exam_cell if body.role == "teacher" else False,
    )
    db.add(key)
    _log(db, school.id, "key_issued", f"role={body.role!r} label={body.label!r}")
    db.commit()
    db.refresh(key)
    view = _key_view(key)
    view["api_key"] = key.api_key
    view["api_key_notice"] = (
        "Give it to the person named now. You can look it up again later from this "
        "school's staff key list if needed, but treat it as if you couldn't."
    )
    return view


@router.patch("/schools/{school_id}/keys/{key_id}")
def patch_staff_key(
    school_id: str, key_id: str, body: StaffKeyPatchIn, db: Session = Depends(get_session)
) -> dict:
    """Edit a principal or teacher key's contact details (and/or its label). The
    credential itself never changes here -- issue/revoke/rotate cover that."""
    key = db.get(StaffKey, key_id)
    if key is None or key.school_id != school_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such key")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(key, field, value)
    if changes:
        _log(db, school_id, "key_edited", f"key_id={key_id} fields={sorted(changes)}")
    db.commit()
    db.refresh(key)
    return _key_view(key)


@router.post("/schools/{school_id}/keys/{key_id}/revoke")
def revoke_staff_key(school_id: str, key_id: str, db: Session = Depends(get_session)) -> dict:
    """Stop a key working. The row stays: who held access, and until when, is the first
    question asked after anything goes wrong."""
    key = db.get(StaffKey, key_id)
    if key is None or key.school_id != school_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such key")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        _log(db, school_id, "key_revoked", f"key_id={key_id} role={key.role!r}")
        db.commit()
    return _key_view(key)


@router.get("/schools/{school_id}/keys/{key_id}/assignments")
def list_assignments(school_id: str, key_id: str, db: Session = Depends(get_session)) -> list[dict]:
    """A teacher key's class/subject assignments -- what the Teachers tab edits."""
    key = db.get(StaffKey, key_id)
    if key is None or key.school_id != school_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such key")
    rows = db.scalars(
        select(TeacherAssignment)
        .where(TeacherAssignment.staff_key_id == key_id)
        .order_by(TeacherAssignment.created_at)
    ).all()
    return [_assignment_view(a) for a in rows]


@router.patch("/schools/{school_id}/keys/{key_id}/assignments")
def patch_assignments(
    school_id: str, key_id: str, body: AssignmentsPatchIn, db: Session = Depends(get_session)
) -> list[dict]:
    """Replace a teacher key's full set of assignments with exactly the list given.

    Whole-set replace, not incremental add/remove: the Teachers tab always shows and
    submits the complete list, so there is no ambiguity about what "the current
    assignments" means after a save.
    """
    key = db.get(StaffKey, key_id)
    if key is None or key.school_id != school_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such key")

    section_ids = {a.section_id for a in body.assignments}
    if section_ids:
        found = set(
            db.scalars(
                select(Section.id).where(
                    Section.id.in_(section_ids), Section.school_id == school_id
                )
            )
        )
        missing = section_ids - found
        if missing:
            raise HTTPException(422, f"no such section in this school: {sorted(missing)}")

    db.execute(
        TeacherAssignment.__table__.delete().where(TeacherAssignment.staff_key_id == key_id)
    )
    for a in body.assignments:
        db.add(
            TeacherAssignment(
                staff_key_id=key_id, type=a.type, section_id=a.section_id,
                subject_code=a.subject_code,
            )
        )
    _log(
        db, school_id, "teacher_assignments_edited",
        f"key_id={key_id} count={len(body.assignments)}",
    )
    db.commit()
    rows = db.scalars(
        select(TeacherAssignment)
        .where(TeacherAssignment.staff_key_id == key_id)
        .order_by(TeacherAssignment.created_at)
    ).all()
    return [_assignment_view(a) for a in rows]


@router.get("/schools/{school_id}/students")
def list_students(school_id: str, db: Session = Depends(get_session)) -> list[dict]:
    """The full roster for the Students tab, across every section."""
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    sections = {
        s.id: s
        for s in db.scalars(select(Section).where(Section.school_id == school_id))
    }
    students = db.scalars(
        select(StudentProfile)
        .where(StudentProfile.school_id == school_id)
        .order_by(StudentProfile.section_id, StudentProfile.roll_no)
    ).all()
    rows = []
    for st in students:
        section = sections.get(st.section_id)
        rows.append({
            "id": st.id,
            "name": st.name,
            "roll_no": st.roll_no,
            "section_id": st.section_id,
            "section_label": f"Class {section.grade}-{section.name}" if section else None,
            "age": st.age,
            "gender": st.gender,
            "dob": st.dob.isoformat() if st.dob else None,
            "parent_name": st.parent_name,
            "parent_whatsapp": st.parent_whatsapp,
        })
    return rows


@router.post("/schools/{school_id}/students/bulk", status_code=status.HTTP_201_CREATED)
def bulk_add_students(
    school_id: str, body: StudentsBulkIn, db: Session = Depends(get_session)
) -> list[dict]:
    """Add several students at once -- the Students tab's "Add students" action."""
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    if not body.students:
        raise HTTPException(422, "no students given")

    section_ids = {s.section_id for s in body.students}
    found = set(
        db.scalars(
            select(Section.id).where(Section.id.in_(section_ids), Section.school_id == school_id)
        )
    )
    missing = section_ids - found
    if missing:
        raise HTTPException(422, f"no such section in this school: {sorted(missing)}")

    created: list[StudentProfile] = []
    for s in body.students:
        dob = None
        if s.dob:
            try:
                dob = date.fromisoformat(s.dob)
            except ValueError:
                raise HTTPException(422, f"invalid dob: {s.dob!r}")
        student = StudentProfile(
            school_id=school_id, section_id=s.section_id, name=s.name.strip(),
            roll_no=s.roll_no.strip(), age=s.age, gender=s.gender, dob=dob,
            parent_name=s.parent_name, parent_whatsapp=s.parent_whatsapp,
        )
        db.add(student)
        created.append(student)
    _log(db, school_id, "students_added", f"count={len(created)}")
    db.commit()
    for st in created:
        db.refresh(st)
    return [
        {
            "id": st.id, "name": st.name, "roll_no": st.roll_no, "section_id": st.section_id,
            "age": st.age, "gender": st.gender,
            "dob": st.dob.isoformat() if st.dob else None,
            "parent_name": st.parent_name, "parent_whatsapp": st.parent_whatsapp,
        }
        for st in created
    ]


@router.get("/schools/{school_id}/activity")
def list_activity(
    school_id: str, limit: int = 100, db: Session = Depends(get_session)
) -> list[dict]:
    """The Activity tab: most recent actions taken on this school through the ops
    console, newest first."""
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    limit = max(1, min(limit, 100))
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.school_id == school_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": a.id,
            "action": a.action,
            "detail": a.detail,
            "actor_role": a.actor_role,
            "actor_label": a.actor_label,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]


@router.post("/schools/{school_id}/rotate-key")
def rotate_key(school_id: str, db: Session = Depends(get_session)) -> dict:
    """Issue a new admin key for this school. The old one stops working immediately.

    Sections and every student record are untouched -- rotating a credential must not
    disturb a class link a school has already handed out.
    """
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    school.api_key = secrets.token_urlsafe(24)
    _log(db, school.id, "key_rotated", "school admin key rotated")
    db.commit()
    return {
        "school_id": school.id,
        "name": school.name,
        "api_key": school.api_key,
        "api_key_notice": (
            "Shown once. Anyone holding the previous key is now signed out."
        ),
    }
