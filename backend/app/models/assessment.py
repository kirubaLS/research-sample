"""Assessment, its pages, and the frozen Q-matrix.

Every structural property of a paper is *discovered* and recorded, never hardcoded per
subject: imposition (1-up / 2-up / 4-up), rotation, languages and section count all vary
across the eight real CBSE 2026 papers we measured.
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

#: CBSE cognitive tiers
TIERS = ("R&U", "AP", "AEC")
#: target mark share of a board paper, used only as a tie-break on declared blueprints
CBSE_TIER_TARGET = {"R&U": 0.54, "AP": 0.24, "AEC": 0.22}


class Assessment(Base, PkMixin, TimestampMixin):
    __tablename__ = "assessment"

    school_id: Mapped[str] = mapped_column(ForeignKey("school.id"), index=True)
    subject_code: Mapped[str] = mapped_column(String(32))
    curriculum_version: Mapped[str] = mapped_column(String(32), default="CBSE-2026-27")
    title: Mapped[str] = mapped_column(String(200))
    paper_code: Mapped[str | None] = mapped_column(String(32), nullable=True)  # '30(B)', '2/7/3'
    total_marks: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)

    # --- discovered at ingest (app.vision, app.extraction) ---
    source_sha256: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    pdf_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    logical_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imposition: Mapped[int] = mapped_column(Integer, default=1)      # 1, 2 or 4-up
    rotation: Mapped[int] = mapped_column(Integer, default=0)        # 0/90/180/270
    languages: Mapped[list | None] = mapped_column(JSON, nullable=True)
    route: Mapped[str] = mapped_column(String(16), default="vision")  # 'vision' | 'text'

    # --- what the paper itself declares (app.extraction.instructions) ---
    declared: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(24), default="ingested", index=True)
    qmatrix_frozen_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    qmatrix_version: Mapped[int] = mapped_column(Integer, default=0)


class LogicalPage(Base, PkMixin):
    """One real A4 page of the paper, after de-imposition and language de-duplication."""

    __tablename__ = "logical_page"
    __table_args__ = (UniqueConstraint("assessment_id", "index", name="uq_logical_page"),)

    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessment.id"), index=True)
    index: Mapped[int] = mapped_column(Integer)          # printed 'Page N of M'
    source_pdf_page: Mapped[int] = mapped_column(Integer)
    tile_bbox: Mapped[list | None] = mapped_column(JSON, nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="en")
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=True)
    image_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Question(Base, PkMixin, TimestampMixin):
    """One row per *address*, not per question number.

    Marks are written per sub-part, so the atomic unit is
    ``section / question_no / sub_part / choice_alt`` — see app.extraction.address.
    """

    __tablename__ = "question"
    __table_args__ = (UniqueConstraint("assessment_id", "address", name="uq_question_address"),)

    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessment.id"), index=True)
    address: Mapped[str] = mapped_column(String(40), index=True)   # 'C/27//b'
    section: Mapped[str | None] = mapped_column(String(8), nullable=True)
    question_no: Mapped[str] = mapped_column(String(12))
    sub_part: Mapped[str | None] = mapped_column(String(12), nullable=True)
    choice_alt: Mapped[str | None] = mapped_column(String(4), nullable=True)
    choice_group_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    max_marks: Mapped[float] = mapped_column(Numeric(5, 2))
    mark_step: Mapped[float] = mapped_column(Numeric(3, 2), default=1.0)
    question_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    stem_text: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    stem_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    logical_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[list | None] = mapped_column(JSON, nullable=True)


class QuestionSkill(Base, PkMixin):
    """The Q-matrix. Multi-skill rows are allowed and are what make the diagnosis work."""

    __tablename__ = "question_skill"
    __table_args__ = (UniqueConstraint("question_id", "node_id", name="uq_question_skill"),)

    question_id: Mapped[str] = mapped_column(ForeignKey("question.id"), index=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_node.id"), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(24), default="model")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class QuestionTier(Base, PkMixin, TimestampMixin):
    """Append-only tier decisions. Never mutated; precedence resolves the current value."""

    __tablename__ = "question_tier"

    question_id: Mapped[str] = mapped_column(ForeignKey("question.id"), index=True)
    tier: Mapped[str | None] = mapped_column(String(8), nullable=True)  # None => abstained
    action_class: Mapped[str | None] = mapped_column(String(24), nullable=True)
    familiarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    familiarity_bucket: Mapped[str | None] = mapped_column(String(1), nullable=True)
    signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # the four signal vectors
    conformal_set: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(24), default="ensemble")  # ensemble|human|library
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class DataQualityFlag(Base, PkMixin, TimestampMixin):
    __tablename__ = "data_quality_flag"

    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessment.id"), index=True)
    student_id: Mapped[str | None] = mapped_column(ForeignKey("student_profile.id"), nullable=True)
    rule: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="blocking")
    detail: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)


class AnalysisRun(Base, PkMixin, TimestampMixin):
    """Every derived row is tagged with a run so a report regenerates bit-identically."""

    __tablename__ = "analysis_run"

    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessment.id"), index=True)
    code_version: Mapped[str] = mapped_column(String(40))
    taxonomy_version: Mapped[str] = mapped_column(String(32))
    model_versions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
