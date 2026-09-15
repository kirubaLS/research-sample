"""
Part B data model for the rules engine, as pure dataclasses. No DB models, no
storage, no API. This module is self-contained.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums (spec vocabulary, deliberately NOT the same as the existing
# app.models.assessment enums — see task brief).
# ---------------------------------------------------------------------------

class DomainType(str, Enum):
    CHAPTER = "CHAPTER"
    SKILL = "SKILL"


class CompetencyTier(str, Enum):
    RECALL = "RECALL"
    APPLICATION = "APPLICATION"
    ANALYSIS = "ANALYSIS"


class Complexity(str, Enum):
    L1 = "L1"   # single-step
    L2 = "L2"   # multi-step
    L3 = "L3"   # integrated


class Dependency(str, Enum):
    D0 = "D0"   # independent
    D1 = "D1"   # prerequisite
    D2 = "D2"   # cross-concept


# ---------------------------------------------------------------------------
# B1: per-question
# ---------------------------------------------------------------------------

@dataclass
class ChoiceBranch:
    branch: str                       # 'a' or 'b'
    concept_variant: str
    competency_tier: CompetencyTier
    complexity: Complexity
    dependency: Dependency


@dataclass
class Question:
    question_id: str
    domain: str
    domain_type: DomainType
    board_unit: str
    concept_family: str
    concept_variant: str
    competency_tier: CompetencyTier
    complexity: Complexity
    dependency: Dependency
    max_marks: int                    # required on every row
    has_internal_choice: bool = False
    choice_branches: list[ChoiceBranch] = field(default_factory=list)
    is_open_list: bool = False
    is_holistic: bool = False
    is_binary: bool = False

    def __post_init__(self) -> None:
        if self.max_marks is None:
            raise ValueError(f"{self.question_id}: max_marks is required on every row")


# ---------------------------------------------------------------------------
# B2: per student, per question
# ---------------------------------------------------------------------------

@dataclass
class StudentResponse:
    student_id: str
    question_id: str
    # None means absent. NOT the same as 0. Must never be treated as zero.
    marks_obtained: Optional[int]
    branch_attempted: Optional[str] = None   # 'a' | 'b' | None (not currently captured)
    subpart_marks: Optional[list[int]] = None  # not currently captured

    @property
    def is_absent(self) -> bool:
        return self.marks_obtained is None


# ---------------------------------------------------------------------------
# B3: reference tables, joined at analysis time (lookups, not fields)
# ---------------------------------------------------------------------------

@dataclass
class BoardUrgencyRow:
    concept_family: str
    appearances_last_4_years: int      # 0..4
    frequency_band: str                # e.g. "Very high", "High", ...
    choice_only: bool = False


class BoardUrgencyTable:
    """Keyed by concept_family. Deliberately NOT seeded with defaults (M9/J3):
    an absent row is the correct, expected steady state until Part J counting
    is done."""

    def __init__(self, rows: Optional[dict[str, BoardUrgencyRow]] = None) -> None:
        self._rows: dict[str, BoardUrgencyRow] = dict(rows or {})

    def get(self, concept_family: str) -> Optional[BoardUrgencyRow]:
        return self._rows.get(concept_family)

    def put(self, row: BoardUrgencyRow) -> None:
        self._rows[row.concept_family] = row


@dataclass
class RemediationRow:
    # Key changed per B3/M1: first position accepts a chapter OR a skill label.
    domain_or_skill: str
    competency_tier: CompetencyTier
    ncert_references: list[str] = field(default_factory=list)


class RemediationTable:
    """Keyed by (domain_or_skill, competency_tier)."""

    def __init__(self, rows: Optional[list[RemediationRow]] = None) -> None:
        self._rows: dict[tuple[str, CompetencyTier], RemediationRow] = {}
        for r in rows or []:
            self._rows[(r.domain_or_skill, r.competency_tier)] = r

    def get(self, domain_or_skill: str, tier: CompetencyTier) -> Optional[RemediationRow]:
        return self._rows.get((domain_or_skill, tier))

    def put(self, row: RemediationRow) -> None:
        self._rows[(row.domain_or_skill, row.competency_tier)] = row


# ---------------------------------------------------------------------------
# B4: class / cohort structure
# ---------------------------------------------------------------------------

@dataclass
class ClassCohort:
    class_id: str
    grade: str
    # student_ids of everyone who sat (marks_obtained != null on the totals used)
    students_who_sat: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Paper: the aggregate the engine actually operates over
# ---------------------------------------------------------------------------

@dataclass
class Paper:
    paper_id: str
    subject: str
    questions: list[Question]
    board_urgency: BoardUrgencyTable = field(default_factory=BoardUrgencyTable)
    remediation: RemediationTable = field(default_factory=RemediationTable)

    def question_by_id(self, question_id: str) -> Question:
        for q in self.questions:
            if q.question_id == question_id:
                return q
        raise KeyError(question_id)

    def domains(self) -> list[str]:
        seen: list[str] = []
        for q in self.questions:
            if q.domain not in seen:
                seen.append(q.domain)
        return seen


@dataclass
class StudentPaper:
    """One student's responses to one Paper, within one class."""
    student_id: str
    class_id: str
    responses: dict[str, StudentResponse]   # question_id -> response

    def response_for(self, question_id: str) -> Optional[StudentResponse]:
        return self.responses.get(question_id)

    def marks_obtained(self, question_id: str) -> Optional[int]:
        r = self.responses.get(question_id)
        return None if r is None else r.marks_obtained
