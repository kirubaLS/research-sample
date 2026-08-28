"""Use case 1 — the RIASEC interest inventory."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin


class TestSession(Base, PkMixin, TimestampMixin):
    __tablename__ = "test_session"

    school_id: Mapped[str] = mapped_column(ForeignKey("school.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("student_profile.id"), index=True)
    instrument_version: Mapped[str] = mapped_column(String(32), default="riasec-36-v1")
    locale: Mapped[str] = mapped_column(String(8), default="en")
    item_order: Mapped[list | None] = mapped_column(JSON, nullable=True)  # fixed seed, auditable
    started_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validity: Mapped[str] = mapped_column(String(16), default="pending")  # valid|suspect|invalid
    validity_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ItemResponse(Base, PkMixin):
    """shown_at and answered_at are the entire validity layer. They cannot be added later."""

    __tablename__ = "item_response"

    session_id: Mapped[str] = mapped_column(ForeignKey("test_session.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(16), index=True)
    value: Mapped[int] = mapped_column(Integer)  # 1..5 Likert
    shown_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScaleScore(Base, PkMixin):
    __tablename__ = "scale_score"

    session_id: Mapped[str] = mapped_column(ForeignKey("test_session.id"), index=True)
    scale: Mapped[str] = mapped_column(String(1))  # R I A S E C
    raw: Mapped[float] = mapped_column(Float)
    centered: Mapped[float] = mapped_column(Float)
    percentile: Mapped[float] = mapped_column(Float)
    ci_low: Mapped[float] = mapped_column(Float)
    ci_high: Mapped[float] = mapped_column(Float)


class ProfileResult(Base, PkMixin, TimestampMixin):
    __tablename__ = "profile_result"

    session_id: Mapped[str] = mapped_column(ForeignKey("test_session.id"), index=True, unique=True)
    holland_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    differentiation: Mapped[float | None] = mapped_column(Float, nullable=True)
    consistency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stream_fit: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommendation_withheld: Mapped[bool] = mapped_column(Boolean, default=False)
    withheld_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
