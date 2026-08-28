"""Append-only mark events.

Three states, not two: a numeric award, ABSENT (student not present), and NOT_OFFERED
(the unattempted half of an internal-choice pair). Scoring NOT_OFFERED as zero would
mark every student weak in whichever topic they chose to avoid.
"""

from __future__ import annotations

from sqlalchemy import JSON, Float, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

#: precedence when several sources disagree — resolved at projection time, never by UPDATE
SOURCE_PRECEDENCE = ("page_ocr", "cover_ocr", "csv", "teacher")

MARK_STATES = ("awarded", "absent", "not_offered")


class MarkEvent(Base, PkMixin, TimestampMixin):
    __tablename__ = "mark_event"

    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessment.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("student_profile.id"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("question.id"), index=True)

    state: Mapped[str] = mapped_column(String(16), default="awarded")
    marks: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    source: Mapped[str] = mapped_column(String(16), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: {'page_id':..., 'bbox':[...], 'crop_uri':..., 'row_ref': 'sheet1!C14'}
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    superseded: Mapped[bool] = mapped_column(default=False)
