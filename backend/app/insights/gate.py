"""Part C3: the paper-check gate. A GATE, not a filter — blocked claims are
recorded (C8), not silently dropped."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .model import Question, CompetencyTier, Complexity, Dependency
from .flags import QuestionFlags
from . import constants as C


class ClaimType(str, Enum):
    TIER_GAP = "TIER_GAP"
    COMPLEXITY_GAP = "COMPLEXITY_GAP"
    INTEGRATION_GAP = "INTEGRATION_GAP"
    VARIANT_WEAKNESS = "VARIANT_WEAKNESS"
    DIFFUSE_SIGNAL = "DIFFUSE_SIGNAL"


@dataclass
class BlockedClaim:
    claim_type: ClaimType
    analytical_scope: str
    domain: str | None
    blocked_at: str
    reason: str
    detail: str
    attribution: str = "Property of the paper, not of the students."
    remedy: str = ""
    report_language: str = ""


@dataclass
class DomainStats:
    domain: str
    questions: list[Question]

    def by_tier(self, tier: CompetencyTier) -> list[Question]:
        return [q for q in self.questions if q.competency_tier == tier]

    def recall(self) -> list[Question]:
        return self.by_tier(CompetencyTier.RECALL)

    def nonrecall(self) -> list[Question]:
        return [q for q in self.questions if q.competency_tier != CompetencyTier.RECALL]

    def by_complexity(self, group: str) -> list[Question]:
        if group == "L1":
            return [q for q in self.questions if q.complexity == Complexity.L1]
        return [q for q in self.questions if q.complexity in (Complexity.L2, Complexity.L3)]

    def by_dependency(self, group: str) -> list[Question]:
        if group == "D2":
            return [q for q in self.questions if q.dependency == Dependency.D2]
        return [q for q in self.questions if q.dependency in (Dependency.D0, Dependency.D1)]


def domain_questions(questions: list[Question], flags: dict[str, QuestionFlags],
                      domain: str, *, exclude_entirely: bool = True) -> list[Question]:
    out = []
    for q in questions:
        if q.domain != domain:
            continue
        if exclude_entirely and flags[q.question_id].excluded_entirely:
            continue
        out.append(q)
    return out


def distinct_variants(questions: list[Question], flags: dict[str, QuestionFlags]) -> set[str]:
    """variant_unknown questions do not count toward coverage (C2)."""
    return {
        q.concept_variant for q in questions
        if not flags[q.question_id].variant_unknown
    }


def max_question_share_of_group(questions: list[Question]) -> float:
    total = sum(q.max_marks for q in questions)
    if total == 0:
        return 0.0
    return max((q.max_marks for q in questions), default=0) / total


def largest_variant_share(questions: list[Question], flags: dict[str, QuestionFlags]) -> float:
    known = [q for q in questions if not flags[q.question_id].variant_unknown]
    if not known:
        return 0.0
    from collections import Counter
    counts = Counter(q.concept_variant for q in known)
    return max(counts.values()) / len(known)


def clean_partial_credit_questions(questions: list[Question], flags: dict[str, QuestionFlags]) -> list[Question]:
    """partial credit AND NOT variant_unknown."""
    out = []
    for q in questions:
        f = flags[q.question_id]
        if f.excluded_entirely:
            continue
        if f.marker_dependent and not f.variant_unknown:
            out.append(q)
    return out


def chapter_balance_check(all_questions: list[Question], flags: dict[str, QuestionFlags]) -> tuple[bool, str]:
    """Part E1: for each chapter, its share of paper marks vs its share of the
    recall pool vs its share of the non-recall pool must each be within
    CHAPTER_BALANCE_BAND_PP points."""
    usable = [q for q in all_questions if not flags[q.question_id].excluded_entirely]
    total_marks = sum(q.max_marks for q in usable)
    recall = [q for q in usable if q.competency_tier == CompetencyTier.RECALL]
    nonrecall = [q for q in usable if q.competency_tier != CompetencyTier.RECALL]
    recall_marks = sum(q.max_marks for q in recall)
    nonrecall_marks = sum(q.max_marks for q in nonrecall)
    if total_marks == 0 or recall_marks == 0 or nonrecall_marks == 0:
        return False, "Insufficient marks to compute chapter balance."

    domains = sorted({q.domain for q in usable})
    problems = []
    for d in domains:
        paper_share = sum(q.max_marks for q in usable if q.domain == d) / total_marks
        recall_share = sum(q.max_marks for q in recall if q.domain == d) / recall_marks
        nonrecall_share = sum(q.max_marks for q in nonrecall if q.domain == d) / nonrecall_marks
        if abs(paper_share - recall_share) * 100 > C.CHAPTER_BALANCE_BAND_PP:
            problems.append(d)
        elif abs(paper_share - nonrecall_share) * 100 > C.CHAPTER_BALANCE_BAND_PP:
            problems.append(d)
    if problems:
        return False, f"Chapter balance fails for: {', '.join(problems)}."
    return True, "Chapter balance holds within {}pp for every chapter.".format(
        C.CHAPTER_BALANCE_BAND_PP
    )
