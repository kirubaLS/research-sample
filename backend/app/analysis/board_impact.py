"""Board Impact -- a join and a formula, computed at analysis time and stored nowhere.

    Board Impact = (marks lost in this board unit, this test
                    / marks available in this board unit, this test) x board weight

Two details the formula assumes, which the code has to guarantee:

* "marks available ... this test" is per-test, not per-syllabus, and must respect choice
  groups and NOT_OFFERED. A question the student was never offered is not a mark they
  could have earned, and counting it turns a choice into a penalty.
* every question carries a board unit, or the denominator is a subset pretending to be a
  whole. Hence Question.board_unit_id is not null.
"""

from __future__ import annotations

from dataclasses import dataclass

#: a mark state meaning the student was never offered this question -- an unchosen
#: alternative in a choice group, or a section their paper did not include
NOT_OFFERED = "NOT_OFFERED"


@dataclass(frozen=True)
class QuestionMarks:
    question_id: str
    board_unit_id: str
    max_marks: float
    awarded: float | None       # None when not offered
    state: str = "MARKED"


@dataclass(frozen=True)
class UnitImpact:
    board_unit_id: str
    marks_available: float
    marks_lost: float
    board_weight_pct: float
    impact: float
    #: the share of this unit's marks that were lost, before the board weight is applied
    loss_fraction: float


def compute(
    marks: list[QuestionMarks],
    board_weights: dict[str, float],
) -> list[UnitImpact]:
    """Board impact per unit, highest impact first.

    A unit with no marks available in this test is omitted entirely rather than reported
    as zero impact: nothing was tested, so nothing is known, and a zero would read as
    "no problem here".
    """
    available: dict[str, float] = {}
    lost: dict[str, float] = {}

    for m in marks:
        if m.state == NOT_OFFERED or m.awarded is None:
            continue
        available[m.board_unit_id] = available.get(m.board_unit_id, 0.0) + m.max_marks
        lost[m.board_unit_id] = lost.get(m.board_unit_id, 0.0) + (m.max_marks - m.awarded)

    out: list[UnitImpact] = []
    for unit_id, unit_available in available.items():
        if unit_available <= 0:
            continue
        unit_lost = lost.get(unit_id, 0.0)
        fraction = unit_lost / unit_available
        weight = board_weights.get(unit_id, 0.0)
        out.append(
            UnitImpact(
                board_unit_id=unit_id,
                marks_available=unit_available,
                marks_lost=unit_lost,
                board_weight_pct=weight,
                impact=fraction * weight,
                loss_fraction=fraction,
            )
        )

    return sorted(out, key=lambda u: u.impact, reverse=True)
