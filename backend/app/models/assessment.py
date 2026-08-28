"""Assessment, its pages, and the frozen Q-matrix.

Every structural property of a paper is *discovered* and recorded, never hardcoded per
subject: imposition (1-up / 2-up / 4-up), rotation, languages and section count all vary
across the eight real CBSE 2026 papers we measured.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

#: CBSE cognitive tiers, in the board's own words. One field, one name -- the UI
#: abbreviates ("AP"), storage does not.
TIERS = ("Remembering & Understanding", "Applying", "Analysing, Evaluating & Creating")
#: legacy short codes, accepted on the way in so older data and the tier engine keep working
TIER_ALIASES = {
    "R&U": "Remembering & Understanding",
    "AP": "Applying",
    "AEC": "Analysing, Evaluating & Creating",
}
#: target mark share of a board paper, used only as a tie-break on declared blueprints
CBSE_TIER_TARGET = {
    "Remembering & Understanding": 0.54,
    "Applying": 0.24,
    "Analysing, Evaluating & Creating": 0.22,
}

#: Complexity does not map onto pure literary interpretation. A third state keeps the
#: analysis honest rather than coercing single/multi-step -- the same reasoning as
#: NOT_OFFERED in the marks engine.
COMPLEXITY_VALUES = ("SINGLE_STEP", "MULTI_STEP", "NOT_APPLICABLE")
DEPENDENCY_VALUES = ("SINGLE_CONCEPT", "MULTI_CONCEPT")
#: the judgment fields of Layer 2B, each requiring two agreeing reviewers before shipping
JUDGMENT_FIELDS = ("skill_required", "complexity", "dependency_level")


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
    __table_args__ = (
        UniqueConstraint("assessment_id", "address", name="uq_question_address"),
        # The conditional-Chapter rule, enforced rather than trusted. A half-filled pair --
        # chapter without section, or section without chapter -- is the force-fitting the
        # rule forbids, and is far cheaper to reject here than to find in a report later.
        CheckConstraint(
            "(chapter_id IS NULL) = (curriculum_section IS NULL)",
            name="ck_question_chapter_pairing",
        ),
    )

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

    # --- Layer 1: curriculum intelligence ---
    #: The only field the board-weight lookup ever reads. Not null: a null here silently
    #: removes the question from board-impact reporting rather than failing loudly.
    board_unit_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_node.id"), index=True)
    #: Conditional. A skill-anchored question (unseen passage, invented sentence) has no
    #: chapter to point at, and inventing one is the failure the rule exists to prevent.
    chapter_id: Mapped[str | None] = mapped_column(
        ForeignKey("taxonomy_node.id"), nullable=True, index=True
    )
    curriculum_section: Mapped[str | None] = mapped_column(String(32), nullable=True)  # '12.2'
    curriculum_section_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Provenance for the section number. The schema requires it checked against the current
    #: textbook, so an unverified number must be visibly unverified, not indistinguishable
    #: from a checked one.
    verified_against: Mapped[str | None] = mapped_column(String(120), nullable=True)
    verified_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

    #: Held constant across cycles: the axis every trend report groups by, and the reason
    #: a diagnosis still works when chapter_id is null.
    concept_family_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_node.id"), index=True)
    #: Must CHANGE across cycles. Same family, different question -- otherwise a rising
    #: score measures familiarity and reads as learning. Enforced by app.taxonomy.variants.
    concept_variant: Mapped[str] = mapped_column(String(200))
    variant_hash: Mapped[str] = mapped_column(String(64), index=True)

    # --- Layer 2B: learning demand (judgment; see QuestionJudgment for the review gate) ---
    skill_required: Mapped[str | None] = mapped_column(String(200), nullable=True)
    complexity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dependency_level: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Difficulty is deliberately absent and must stay absent. It is derived from observed
    # performance across more than one school (app.analysis.difficulty), never tagged.


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


class QuestionJudgment(Base, PkMixin, TimestampMixin):
    """Layer 2B review trail. Append-only; more than one row per field is the normal case.

    The schema requires two reviewers and disagreements resolved *before the question
    ships*, so agreement is a gate rather than a statistic -- see app.taxonomy.judgment.
    """

    __tablename__ = "question_judgment"

    question_id: Mapped[str] = mapped_column(ForeignKey("question.id"), index=True)
    field: Mapped[str] = mapped_column(String(24), index=True)  # see JUDGMENT_FIELDS
    value: Mapped[str] = mapped_column(String(200))
    reviewer_id: Mapped[str] = mapped_column(String(64), index=True)
    #: set when a third judgment settles a disagreement rather than being an independent read
    is_resolution: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)


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
