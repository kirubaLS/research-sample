"""Curriculum knowledge graph: the asset with the longest half-life.

Versioned as an SCD-2 tree. Nothing here is ever hard-deleted; a syllabus revision
adds a node version so historical reports stay reproducible.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

#: 'board_unit' is a SIBLING of chapter under subject, never a parent of it. CBSE's
#: weightage unit may combine several chapters, or exist where no chapter does (English's
#: Reading section), so it cannot sit in the chapter hierarchy without distorting it.
#: 'concept_family' is the stable axis every trend report groups by.
NODE_KINDS = (
    "board", "subject", "grade", "board_unit", "chapter", "subtopic",
    "concept_family", "skill", "qtype", "tier",
)


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
    """Directed edge: `node` requires `requires`.

    Deferred in V1: the table exists and may be populated, but nothing in the reporting
    path reads it. Prerequisite Concept is a placeholder in the schema, and a remediation
    chain built on unvalidated edges would be confidently wrong about what to reteach.
    """

    __tablename__ = "prerequisite"
    __table_args__ = (UniqueConstraint("node_id", "requires_id", name="uq_prereq"),)

    node_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_node.id"), index=True)
    requires_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_node.id"), index=True)
    strength: Mapped[float] = mapped_column(Float, default=1.0)


class BoardUnitWeight(Base, PkMixin):
    """Board weights are data, with a citation. A principal will challenge these.

    Keyed on the board unit, never the chapter. CBSE publishes weightage per unit, and a
    unit may span several chapters or none at all -- keying this on chapter computed board
    impact against a scale the board does not use.
    """

    __tablename__ = "board_unit_weight"
    __table_args__ = (
        UniqueConstraint("curriculum_version", "board_unit_id", name="uq_board_unit_weight"),
    )

    curriculum_version: Mapped[str] = mapped_column(String(32), index=True)
    board_unit_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_node.id"), index=True)
    weight_pct: Mapped[float] = mapped_column(Numeric(5, 2))
    source_doc_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ChapterBoardUnit(Base, PkMixin):
    """Which board unit a chapter's marks count towards.

    An explicit mapping rather than a walk up the tree. The real case that decides this:
    History map marks belong to Geography's board unit because the tested chapter does not
    carry them. Inference from the hierarchy gets exactly that wrong.
    """

    __tablename__ = "chapter_board_unit"
    __table_args__ = (
        UniqueConstraint("curriculum_version", "chapter_id", name="uq_chapter_board_unit"),
    )

    curriculum_version: Mapped[str] = mapped_column(String(32), index=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_node.id"), index=True)
    board_unit_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_node.id"), index=True)


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
    canonical_stem: Mapped[str] = mapped_column(Text)
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
    #: '12.2' -- which section of the chapter this passage came from. The ingest works it
    #: out and used to discard it, which left every chunk filed under its chapter and the
    #: section unknowable, so no question could be given a topic.
    section_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: unbounded: a real exercise runs to 8500 characters of frequency tables, and a
    #: truncated one is a silently corrupted familiarity signal rather than a short row
    text: Mapped[str] = mapped_column(Text)
    normalised: Mapped[str] = mapped_column(Text)
    stem_hash: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)  # pgvector in production


class ConceptFamilyProposal(Base, PkMixin, TimestampMixin):
    """A proposed concept family, kept whether or not it is ever applied.

    Stored rather than returned and forgotten, for three reasons that all come up later:

    * **The run is expensive to repeat and cheap to keep.** Reading both books costs about
      a dollar; storing the answer costs nothing. The route refuses to run twice for a
      subject unless asked to, and this table is how it knows.
    * **A family that was applied has to stay explicable.** Eighteen months from now,
      "why is Step-deviation method a row on this report?" is answerable only if the
      passages the model cited are still here next to the label it chose.
    * **A family that was NOT applied is evidence too.** The proposals a person rejected
      are how we find out whether the model's reading is worth paying for at all.

    Never a taxonomy node on its own. Applying a proposal creates the node, and that
    remains a separate, deliberate act: renaming a family after a class has been tested
    breaks every trend that references it.
    """

    __tablename__ = "concept_family_proposal"
    __table_args__ = (
        UniqueConstraint(
            "curriculum_version", "subject_code", "run_id", "code",
            name="uq_family_proposal",
        ),
    )

    curriculum_version: Mapped[str] = mapped_column(String(32), index=True)
    subject_code: Mapped[str] = mapped_column(String(32), index=True)
    #: one id per pass over a subject, so a re-run is comparable with the one before it
    #: rather than merged into it
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    #: 'sections' -- the headings, free and blind to a heading that drills two procedures;
    #: 'llm' -- a model reading the chapter's own passages
    source: Mapped[str] = mapped_column(String(16), default="llm", index=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    code: Mapped[str] = mapped_column(String(80), index=True)
    label: Mapped[str] = mapped_column(String(200))
    chapter_id: Mapped[str | None] = mapped_column(
        ForeignKey("taxonomy_node.id"), nullable=True, index=True
    )
    #: the model's own words on why this is one thing a student can fail
    rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    #: chunk references, every one of them verified to be a passage actually shown
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)
    #: section numbers it draws on, e.g. ['14.1']
    from_sections: Mapped[list | None] = mapped_column(JSON, nullable=True)
    #: set when the proposal has been turned into a taxonomy node
    applied_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class BookSource(Base, PkMixin, TimestampMixin):
    """What was uploaded for a subject, and what the contents page says to expect.

    The contents page is the oracle the whole ingest depends on, so it is uploaded first
    and its table of contents stored here. Every later chapter upload is checked against
    it: a chapter that disagrees is rejected rather than loaded, exactly as the CLI does.

    Also carries the provenance the schema asks for -- the edition string and a per-file
    sha256 -- so `verified_against` is a recorded fact rather than a claim.
    """

    __tablename__ = "book_source"
    __table_args__ = (
        UniqueConstraint("curriculum_version", "subject_code", name="uq_book_source"),
    )

    curriculum_version: Mapped[str] = mapped_column(String(32), index=True)
    subject_code: Mapped[str] = mapped_column(String(32), index=True)
    edition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: {chapter_number: [{"number": "1.1", "title": "Introduction"}, ...]}
    expected_sections: Mapped[dict] = mapped_column(JSON)
    #: {chapter_number: "Light -- Reflection and Refraction"}. All the Science contents
    #: page publishes: it stops at chapter titles where the Maths one lists every section.
    #: A chapter still gets checked against it -- that the file uploaded as 9 is the
    #: chapter the book calls 9 -- but a chapter verified only this far must stay marked
    #: unverified at section level rather than passing as fully checked.
    expected_chapters: Mapped[dict] = mapped_column(JSON, default=dict)
    #: {"01-real-numbers.pdf": {"sha256": ..., "chunks": 16, "loaded_at": ...}}
    files: Mapped[dict] = mapped_column(JSON, default=dict)
