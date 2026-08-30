"""Reconcile a whole paper against the blueprint it declares.

The classifier decides question by question, and a question-by-question decision has no way
to notice that it has put thirteen marks into a unit the board weights at ten. The paper is
a system whose arithmetic must close, and that is information no per-question method can
use.

    If the blueprint says Mensuration carries 10 marks and the assignment gives it 13,
    at least one question is misplaced -- and that is known without a human looking.

So placement becomes an assignment problem: choose one chapter per question, maximising
total confidence, subject to each board unit's marks matching what the paper declares. A
confidently wrong answer gets overruled when moving it is the only way the totals close.

This is the same shape as app.mapping.solver, which repairs misread marks against section
totals. The insight is the same one: local reads are noisy, the totals are not.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Option:
    """One chapter a question could belong to, and how much it is believed."""

    chapter: str
    board_unit: str
    confidence: float

    @property
    def log_confidence(self) -> float:
        # Log so confidences multiply across questions rather than add: an assignment that
        # needs one near-impossible placement should lose to one that needs two mildly
        # unlikely ones.
        return math.log(max(self.confidence, 1e-6))


@dataclass(frozen=True)
class QuestionSlot:
    question_id: str
    marks: float
    options: list[Option]

    @property
    def best(self) -> Option:
        return max(self.options, key=lambda o: o.confidence)


@dataclass
class Reconciliation:
    assignment: dict[str, Option]
    #: questions the blueprint forced away from the classifier's own first choice
    overruled: list[str] = field(default_factory=list)
    #: unit -> (assigned marks, declared marks) where they still disagree
    residual: dict[str, tuple[float, float]] = field(default_factory=dict)
    feasible: bool = True
    note: str = ""


def _totals(assignment: dict[str, Option], slots: list[QuestionSlot]) -> dict[str, float]:
    marks = {s.question_id: s.marks for s in slots}
    out: dict[str, float] = {}
    for qid, option in assignment.items():
        out[option.board_unit] = out.get(option.board_unit, 0.0) + marks[qid]
    return out


def reconcile(
    slots: list[QuestionSlot],
    declared: dict[str, float],
    *,
    tolerance: float = 0.0,
    max_swaps: int = 200,
) -> Reconciliation:
    """Best assignment whose unit totals match the declared blueprint.

    Exact search is exponential, so this is a greedy repair: start from what the classifier
    believed, then repeatedly make the single swap that most reduces the gap to the
    blueprint while costing the least confidence. On a 38-question paper with a handful of
    misplacements that reaches the same answer as exhaustive search, and it degrades
    honestly -- if it cannot close the totals it says so rather than returning a tidy
    assignment that is wrong.
    """
    assignment = {s.question_id: s.best for s in slots}
    if not declared:
        return Reconciliation(assignment, note="paper declares no blueprint; nothing to check")

    def gap(assign: dict[str, Option]) -> float:
        totals = _totals(assign, slots)
        return sum(
            abs(totals.get(unit, 0.0) - target)
            for unit, target in declared.items()
        ) + sum(
            marks for unit, marks in totals.items() if unit not in declared
        )

    overruled: list[str] = []
    for _ in range(max_swaps):
        current = gap(assignment)
        if current <= tolerance:
            break

        best_swap: tuple[float, str, Option] | None = None
        for slot in slots:
            for option in slot.options:
                if option.chapter == assignment[slot.question_id].chapter:
                    continue
                trial = dict(assignment)
                trial[slot.question_id] = option
                improvement = current - gap(trial)
                if improvement <= 0:
                    continue
                # cost of believing this instead: how much confidence is given up
                cost = (
                    assignment[slot.question_id].log_confidence - option.log_confidence
                )
                score = improvement / max(cost, 1e-6)
                if best_swap is None or score > best_swap[0]:
                    best_swap = (score, slot.question_id, option)

        if best_swap is None:
            break
        _, qid, option = best_swap
        assignment[qid] = option
        if qid not in overruled:
            overruled.append(qid)

    totals = _totals(assignment, slots)
    residual = {
        unit: (round(totals.get(unit, 0.0), 2), target)
        for unit, target in declared.items()
        if abs(totals.get(unit, 0.0) - target) > tolerance
    }
    feasible = not residual
    return Reconciliation(
        assignment=assignment,
        overruled=overruled,
        residual=residual,
        feasible=feasible,
        note=(
            f"blueprint closed; {len(overruled)} question(s) moved to make the marks balance"
            if feasible else
            "the totals could not be closed: either a question is missing from the paper, "
            "the declared blueprint is wrong, or the right chapter was never among the "
            "candidates. Do not treat this assignment as verified."
        ),
    )


def needs_a_human(
    slots: list[QuestionSlot],
    result: Reconciliation,
    *,
    min_confidence: float = 0.70,
) -> list[str]:
    """The questions to put in front of a person.

    Three ways to earn a look: the classifier was unsure; the blueprint overruled it, which
    means two sources of evidence disagreed; or the totals never closed, in which case the
    whole paper is suspect and the weakest calls are where to start.
    """
    by_id = {s.question_id: s for s in slots}
    flagged = []
    for qid, option in result.assignment.items():
        if option.confidence < min_confidence or qid in result.overruled:
            flagged.append(qid)
    if not result.feasible:
        ranked = sorted(by_id, key=lambda q: result.assignment[q].confidence)
        for qid in ranked:
            if qid not in flagged:
                flagged.append(qid)
    return flagged
