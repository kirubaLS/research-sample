"""Tenancy and roster. Identity lives here and nowhere else."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
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

    sections: Mapped[list[Section]] = relationship(back_populates="school")


#: Ordered from least to most authority. A route that says "principal or above" is
#: written once, here, rather than as a set literal repeated at every call site.
STAFF_ROLES = ("principal", "admin")


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

    school: Mapped[School | None] = relationship()


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

    section: Mapped[Section] = relationship(back_populates="students")
