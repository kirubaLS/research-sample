"""Shared helpers used across rules: marks_at_stake arithmetic (D5),
remediation lookup, board-urgency lookup (D6/J1)."""
from __future__ import annotations

from typing import Optional

from .model import Question, StudentPaper, CompetencyTier, RemediationTable, BoardUrgencyTable
from .insight import MarksAtStake, Priority, RemediationRef, SENTINEL_NC
from . import constants as C


def marks_at_stake_for(
    questions: list[Question],
    student: StudentPaper,
    basis: str,
    *,
    aggregable: bool = True,
) -> MarksAtStake:
    """D5: lost/available over supporting questions. Absent (null) marks are
    EXCLUDED from both lost and available — never treated as zero."""
    lost = 0
    available = 0
    excluded_absent = 0
    for q in questions:
        obtained = student.marks_obtained(q.question_id)
        if obtained is None:
            excluded_absent += 1
            continue
        lost += (q.max_marks - obtained)
        available += q.max_marks
    full_basis = basis
    if excluded_absent:
        full_basis += f" Excludes {excluded_absent} question(s) not attempted (absent)."
    return MarksAtStake(lost=lost, available=available, basis=full_basis, aggregable=aggregable)


def remediation_action(
    table: RemediationTable, domain_or_skill: str, tier: CompetencyTier
) -> tuple[RemediationRef | str, bool]:
    """Returns (action, resolved_ok). If the lookup key does not resolve to a
    row, action is TEACHER_REVIEW-ish string but resolved_ok=False so G1.7
    rejects the object (per spec: 'do not build around it')."""
    row = table.get(domain_or_skill, tier)
    if row is None:
        return RemediationRef(domain_or_skill=domain_or_skill, tier=tier.value), False
    return RemediationRef(domain_or_skill=domain_or_skill, tier=tier.value), True


def priority_for(board_urgency: BoardUrgencyTable, concept_family: Optional[str],
                  *, scope_not_applicable: bool = False,
                  na_reason: str = "") -> Priority:
    """D6: priority.multiplier lookup. NEVER default to 1.0 for an uncalibrated
    family — NOT_CALIBRATED is the safe default."""
    if scope_not_applicable:
        return Priority(multiplier="NOT_APPLICABLE", reason=na_reason or
                         "No single concept family key applies at this scope.")
    if concept_family is None:
        return Priority(multiplier="NOT_APPLICABLE", reason="No concept family key applies.")
    row = board_urgency.get(concept_family)
    if row is None:
        return Priority(
            multiplier=SENTINEL_NC,
            reason=(
                f"Board urgency table not yet populated for concept family "
                f"'{concept_family}'. Sorted last within its band, not demoted "
                "across bands."
            ),
        )
    mult = C.BOARD_URGENCY_MULTIPLIER_BY_APPEARANCES.get(row.appearances_last_4_years, 1.0)
    mult = max(mult, C.BOARD_URGENCY_FLOOR)
    return Priority(
        multiplier=mult,
        reason=(
            f"'{concept_family}' appeared in {row.appearances_last_4_years} of the "
            f"last 4 years ({row.frequency_band})."
        ),
    )


def pct(part: int, whole: int) -> float:
    return 0.0 if whole == 0 else 100.0 * part / whole


def group_pct_scored(questions: list[Question], student: StudentPaper) -> float:
    """Percentage of available marks scored across a group, for one student.
    Absent questions excluded from both numerator and denominator."""
    obtained_total = 0
    available_total = 0
    for q in questions:
        m = student.marks_obtained(q.question_id)
        if m is None:
            continue
        obtained_total += m
        available_total += q.max_marks
    return pct(obtained_total, available_total)
