"""Part C2: derived flags, computed at load, before any rule runs."""
from __future__ import annotations

from .model import Question


def marker_dependent(q: Question) -> bool:
    return q.max_marks > 1 and not q.is_binary


def variant_unknown(q: Question) -> bool:
    return q.has_internal_choice or q.is_open_list


def tier_unknown(q: Question) -> bool:
    if not q.has_internal_choice or not q.choice_branches:
        return False
    tiers = {b.competency_tier for b in q.choice_branches}
    return len(tiers) > 1


def excluded_entirely(q: Question) -> bool:
    return q.is_holistic or tier_unknown(q)


class QuestionFlags:
    """Bundle of the derived flags for one question, computed once at load."""

    __slots__ = ("question_id", "marker_dependent", "variant_unknown",
                 "tier_unknown", "excluded_entirely")

    def __init__(self, q: Question) -> None:
        self.question_id = q.question_id
        self.marker_dependent = marker_dependent(q)
        self.variant_unknown = variant_unknown(q)
        self.tier_unknown = tier_unknown(q)
        self.excluded_entirely = excluded_entirely(q)


def compute_flags(questions: list[Question]) -> dict[str, QuestionFlags]:
    return {q.question_id: QuestionFlags(q) for q in questions}
