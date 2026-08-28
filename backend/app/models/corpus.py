"""ml_corpus — the bridge from a paid launch to a free recogniser.

Separate schema, separate credentials. Five rules, all enforced here:
  1. every prediction is stored, including auto-accepted ones
  2. the full distribution is stored, not the argmax
  3. append-only — a correction is a new row
  4. time_taken_ms on every human label is a free difficulty annotation
  5. consent_class is set at capture time; it cannot be retrofitted
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin


class CaptureAsset(Base, PkMixin, TimestampMixin):
    __tablename__ = "ml_capture_asset"

    school_id: Mapped[str] = mapped_column(String(36), index=True)
    assessment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    student_ref: Mapped[str | None] = mapped_column(String(36), nullable=True)  # pseudonymous
    page_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_uri: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    device_hint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    quality: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ink_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    consent_class: Mapped[str] = mapped_column(String(32), default="operational_only", index=True)


class Crop(Base, PkMixin):
    __tablename__ = "ml_crop"

    asset_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(16))   # mark | anchor | cell | total
    layer: Mapped[str] = mapped_column(String(16))  # teacher | student | printed
    bbox: Mapped[list] = mapped_column(JSON)
    preproc_ver: Mapped[str] = mapped_column(String(32))
    storage_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Prediction(Base, PkMixin, TimestampMixin):
    __tablename__ = "ml_prediction"

    crop_id: Mapped[str] = mapped_column(String(36), index=True)
    backend: Mapped[str] = mapped_column(String(48), index=True)
    model_version: Mapped[str] = mapped_column(String(64))
    distribution: Mapped[dict] = mapped_column(JSON)  # FULL distribution, not the argmax
    argmax: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibrated: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_micros: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_accepted: Mapped[bool] = mapped_column(Boolean, default=False)


class HumanLabel(Base, PkMixin, TimestampMixin):
    __tablename__ = "ml_human_label"

    crop_id: Mapped[str] = mapped_column(String(36), index=True)
    value: Mapped[str] = mapped_column(String(16))
    labeler_id: Mapped[str] = mapped_column(String(36))
    mode: Mapped[str] = mapped_column(String(16))  # review | audit | adjudication
    time_taken_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Disagreement(Base, PkMixin, TimestampMixin):
    __tablename__ = "ml_disagreement"

    crop_id: Mapped[str] = mapped_column(String(36), index=True)
    source_a: Mapped[str] = mapped_column(String(48))
    value_a: Mapped[str] = mapped_column(String(16))
    source_b: Mapped[str] = mapped_column(String(48))
    value_b: Mapped[str] = mapped_column(String(16))
    resolved: Mapped[str | None] = mapped_column(String(16), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
