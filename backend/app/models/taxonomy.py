"""Curriculum knowledge graph: the asset with the longest half-life.

Versioned as an SCD-2 tree. Nothing here is ever hard-deleted; a syllabus revision
adds a node version so historical reports stay reproducible.
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

NODE_KINDS = ("board", "subject", "grade", "chapter", "subtopic", "skill", "qtype", "tier")


class TaxonomyNode(Base, PkMixin, TimestampMixin):
    __tablename__ = "taxonomy_node"
    __table_args__ = (UniqueConstraint("curriculum_version", "code", name="uq_taxonomy_code"),)

    kind: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(80), index=True)  # 'X.MATH.REAL.IRRATIONAL'
    label: Mapped[str] = mapped_column(String(200))
    label_i18n: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {'ta': ..., 'hi': ...}
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("taxonomy_node.id"), nullable=True)
    path: Mapped[str] = mapped_column(String(500), index=True)  # materialised ltree-style path
    curriculum_version: Mapped[str] = mapped_column(String(32), default="CBSE-2026-27", index=True)
    valid_from: Mapped[str | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[str | None] = mapped_column(Date, nullable=True)


class TaxonomyAlias(Base, PkMixin):
    """'SA&V', 'Ch 13', 'Surface Areas & Volumes' all resolve to one node."""

    __tablename__ = "taxonomy_alias"

    node_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_node.id"), index=True)
    alias: Mapped[str] = mapped_column(String(200), index=True)
    locale: Mapped[str] = mapped_column(String(8), default="en")


class Prerequisite(Base, PkMixin):
    """Directed edge: `node` requires `requires`. Remediation walks down these."""

    __tablename__ = "prerequisite"
    __table_args__ = (UniqueConstraint("node_id", "requires_id", name="uq_prereq"),)

    node_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_node.id"), index=True)
    requires_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_node.id"), index=True)
    strength: Mapped[float] = mapped_column(Float, default=1.0)


class ChapterWeight(Base, PkMixin):
    """Board weights are data, with a citation. A principal will challenge these."""

    __tablename__ = "chapter_weight"
    __table_args__ = (
        UniqueConstraint("curriculum_version", "chapter_id", name="uq_chapter_weight"),
    )

    curriculum_version: Mapped[str] = mapped_column(String(32), index=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_node.id"), index=True)
    weight_pct: Mapped[float] = mapped_column(Numeric(5, 2))
    source_doc_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class CanonicalProcedure(Base, PkMixin, TimestampMixin):
    """The taught-verbatim set (Bucket T).

    NCERT labels its theorems and worked examples, so this table is extracted from the
    book rather than hand-typed. Membership turns the familiarity signal from fuzzy
    retrieval into an exact lookup — see app.taxonomy.tier.
    """

    __tablename__ = "canonical_procedure"

    curriculum_version: Mapped[str] = mapped_column(String(32), index=True)
    subject_code: Mapped[str] = mapped_column(String(32), index=True)
    chapter_id: Mapped[str | None] = mapped_column(ForeignKey("taxonomy_node.id"), nullable=True)
    subtopic_id: Mapped[str | None] = mapped_column(ForeignKey("taxonomy_node.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))          # 'Irrationality of root 5'
    reference: Mapped[str | None] = mapped_column(String(80), nullable=True)  # 'Theorem 1.3'
    canonical_stem: Mapped[str] = mapped_column(String(1000))
    stem_hash: Mapped[str] = mapped_column(String(64), index=True)
    taught_verbatim: Mapped[bool] = mapped_column(Boolean, default=True)  # True => Bucket T
    aliases: Mapped[list | None] = mapped_column(JSON, nullable=True)


class BookChunk(Base, PkMixin):
    """Textbook content, split into the two familiarity buckets.

    bucket 'T' = taught as content (theorems, worked/solved examples in the chapter body)
    bucket 'E' = exercise practice (end-of-chapter exercises, past papers)
    """

    __tablename__ = "book_chunk"

    curriculum_version: Mapped[str] = mapped_column(String(32), index=True)
    subject_code: Mapped[str] = mapped_column(String(32), index=True)
    node_id: Mapped[str | None] = mapped_column(ForeignKey("taxonomy_node.id"), nullable=True)
    bucket: Mapped[str] = mapped_column(String(1), index=True)  # 'T' | 'E'
    reference: Mapped[str | None] = mapped_column(String(80), nullable=True)  # 'Ex 1.2 Q1'
    text: Mapped[str] = mapped_column(String(4000))
    normalised: Mapped[str] = mapped_column(String(4000))
    stem_hash: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)  # pgvector in production
