"""Tenancy and roster. Identity lives here and nowhere else."""

from __future__ import annotations

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
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
