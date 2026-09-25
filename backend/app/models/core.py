"""Tenancy and roster. Identity lives here and nowhere else."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PkMixin, TimestampMixin


class School(Base, PkMixin, TimestampMixin):
    __tablename__ = "school"

    name: Mapped[str] = mapped_column(String(200))
    board: Mapped[str] = mapped_column(String(32), default="CBSE")
    state: Mapped[str | None] = mapped_column(String(64), default="Tamil Nadu")
    api_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # per-school fitted HSV centroids for teacher/student ink (app.vision.ink)
    ink_profile: Mapped[dict | None] = mapped_column(nullable=True, type_=None, use_existing_column=True) \
        if False else mapped_column(String(2000), nullable=True)
    training_consent: Mapped[str] = mapped_column(String(32), default="operational_only")
    #: Whether GET /t/classes -- the public, unauthenticated student entry page -- lists
    #: this school's sections. Defaults true (hidden) at the ORM level: a school made by
    #: the operator must not become visible in the public directory just by existing, it
    #: has to be switched on deliberately (app.api.platform's visibility toggle). The
    #: migration that adds this column backfills already-live schools to false (visible)
    #: instead -- see that migration's own docstring for why.
    hidden_from_directory: Mapped[bool] = mapped_column(Boolean, default=True)

    #: Operator-facing "school details" fields. None of these are used anywhere in the
    #: student/teacher-facing flows -- they exist purely so the ops console has somewhere
    #: to record a school's official code, city, postal address and the academic year the
    #: pilot is running against.
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    academic_year: Mapped[str | None] = mapped_column(String(16), nullable=True)

    sections: Mapped[list[Section]] = relationship(back_populates="school")


#: Ordered from least to most authority. A route that says "principal or above" is
#: written once, here, rather than as a set literal repeated at every call site.
#: "teacher" sits below "principal": a teacher's authority is not a smaller version of a
#: principal's, it is scoped by TeacherAssignment rather than by school alone (see that
#: model's docstring), so no route may treat "principal or above" as covering a teacher.
STAFF_ROLES = ("teacher", "principal", "admin")

#: A class assignment covers every subject taught to that section (read access, plus the
#: reading of marks); a subject assignment covers one subject across whichever sections
#: it names, and is the only kind that grants marks-entry rights (see
#: app.api.deps.teacher_can_enter_marks). The two are not layered -- holding a class
#: assignment for a section does not grant subject-assignment rights there too.
TEACHER_ASSIGNMENT_TYPES = ("class", "subject")


class StaffKey(Base, PkMixin, TimestampMixin):
    """A credential belonging to one person, carrying one role.

    ``school_id`` is what separates the two roles, and it is the whole design:

    * a **principal** key names a school, and can only ever see that school -- the id is
      not a default the request may override but the only school the key can resolve to;
    * an **admin** key names none, because an admin creates schools and works across all
      of them. They say which school they are acting on per request.

    So a principal cannot be given another school's data by any header, parameter or
    mistake, because there is no code path that reads a school from the request for them.

    The school's own ``api_key`` predates this table and still works, as an admin bound to
    that one school -- no deployment loses access by this arriving.

    Revoking sets ``revoked_at`` rather than deleting: who held access, and until when, is
    the first question asked after anything goes wrong.
    """

    __tablename__ = "staff_key"

    school_id: Mapped[str | None] = mapped_column(
        ForeignKey("school.id"), index=True, nullable=True
    )
    api_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(16), default="principal")
    label: Mapped[str] = mapped_column(String(120), default="")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Contact details for the person holding this key -- shown on the ops console's
    #: Principal/Teacher tabs. Optional: a key minted before these existed, or one issued
    #: without contact details on hand, simply carries nulls until someone edits it in.
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Set on every successful X-API-Key authentication (see app.api.deps.current_staff).
    #: Lets the ops console show "last active" rather than only "issued on".
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    school: Mapped[School | None] = relationship()
    assignments: Mapped[list[TeacherAssignment]] = relationship(
        back_populates="staff_key", cascade="all, delete-orphan",
    )


class TeacherAssignment(Base, PkMixin, TimestampMixin):
    """One class or subject a teacher key is allowed to touch.

    A teacher key can carry many of these rows -- one per class or subject they hold. Two
    shapes, named by ``type``:

    * ``"class"`` -- ``section_id`` set, ``subject_code`` null. Read access to every
      subject's marks and roster for that one section. Does *not* grant marks-entry: a
      class teacher is, by default, read-only outside their own subject (spec §10.2).
    * ``"subject"`` -- both set. Read *and* marks-entry rights for that one subject, in
      that one section. A teacher who both class-teaches 10-A and subject-teaches Maths
      there holds two rows, not one row with both fields set.

    Nothing here names a school directly: the school is whichever one the assignment's
    ``staff_key`` belongs to (a teacher key is school-scoped exactly like a principal
    key), so a row can never point at a section outside the key's own school by mistake
    -- there is no field here that could disagree with it.
    """

    __tablename__ = "teacher_assignment"

    staff_key_id: Mapped[str] = mapped_column(ForeignKey("staff_key.id"), index=True)
    type: Mapped[str] = mapped_column(String(16))
    section_id: Mapped[str] = mapped_column(ForeignKey("section.id"), index=True)
    subject_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    staff_key: Mapped[StaffKey] = relationship(back_populates="assignments")
    section: Mapped[Section] = relationship()


class Section(Base, PkMixin, TimestampMixin):
    __tablename__ = "section"
    __table_args__ = (UniqueConstraint("school_id", "grade", "name", name="uq_section"),)

    school_id: Mapped[str] = mapped_column(ForeignKey("school.id"), index=True)
    grade: Mapped[int] = mapped_column(Integer, default=10)
    name: Mapped[str] = mapped_column(String(8), default="A")

    school: Mapped[School] = relationship(back_populates="sections")
    students: Mapped[list[StudentProfile]] = relationship(back_populates="section")


class StudentProfile(Base, PkMixin, TimestampMixin):
    """Restricted schema. Analytics joins on id only, never on name."""

    __tablename__ = "student_profile"
    __table_args__ = (UniqueConstraint("section_id", "roll_no", name="uq_roll"),)

    school_id: Mapped[str] = mapped_column(ForeignKey("school.id"), index=True)
    section_id: Mapped[str] = mapped_column(ForeignKey("section.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    roll_no: Mapped[str] = mapped_column(String(16))
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dob: Mapped[str | None] = mapped_column(Date, nullable=True)
    consent_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parent_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parent_whatsapp: Mapped[str | None] = mapped_column(String(32), nullable=True)

    section: Mapped[Section] = relationship(back_populates="students")


class StudentSession(Base, PkMixin, TimestampMixin):
    """A signed-in student's own session, born from logging in with a report's PIN.

    Deliberately not a StaffKey: this never carries a role, never opens a staff route,
    and grants nothing on its own -- every read it makes still has to find a
    ``StudentReport`` row for this exact ``student_id`` with ``shared_at`` set and
    ``share_revoked_at`` null. Revoking or re-sharing a report cannot be undone by an
    old session token; it is checked against the report row fresh on every read, not
    baked into the token at login.

    Random and short-lived on purpose: a PIN is low-entropy by design (a parent reads
    it off a slip of paper), so what carries it afterwards has to be a real secret with
    its own expiry, not the PIN itself asked for again on every request.
    """

    __tablename__ = "student_session"

    student_id: Mapped[str] = mapped_column(ForeignKey("student_profile.id"), index=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("school.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    student: Mapped[StudentProfile] = relationship()


class AuditLog(Base, PkMixin, TimestampMixin):
    """A record of who-did-what on the ops console, per school.

    Written only by app.api.platform, one row per state-changing call: a school created
    or edited, a key issued/revoked/rotated or edited, students added, or a teacher's
    assignments changed. Never edited or deleted afterwards -- the whole point is an
    honest trail, so a route that writes one must never also let it be rewritten.
    """

    __tablename__ = "audit_log"

    school_id: Mapped[str | None] = mapped_column(ForeignKey("school.id"), index=True, nullable=True)
    actor_role: Mapped[str] = mapped_column(String(32), default="platform_admin")
    actor_label: Mapped[str] = mapped_column(String(200), default="")
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(String(2000), nullable=True)
