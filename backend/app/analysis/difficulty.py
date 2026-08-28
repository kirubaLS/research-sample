"""Difficulty -- derived from observed performance, never tagged by a person.

The schema is explicit that difficulty is not a field. It is computed from real attempts,
and not reported until a question has volume across more than one school. Until then it is
*absent*, not estimated: a provisional difficulty is the number everyone quotes.

A consequence worth stating rather than discovering: during a single-school pilot,
difficulty is unavailable for every question by definition. `unavailable_reason` says so
in words, so a report can print the reason instead of a blank.
"""

from __future__ import annotations

from dataclasses import dataclass

#: below this many scored attempts, the proportion is noise
MIN_ATTEMPTS = 30
#: one school's difficulty is that school's teaching, not the question's demand
MIN_SCHOOLS = 2


@dataclass(frozen=True)
class Attempt:
    school_id: str
    awarded: float
    max_marks: float


@dataclass(frozen=True)
class Difficulty:
    question_id: str
    available: bool
    #: mean proportion of marks earned; None whenever available is False
    facility: float | None = None
    attempts: int = 0
    schools: int = 0
    unavailable_reason: str | None = None


def compute(question_id: str, attempts: list[Attempt]) -> Difficulty:
    scored = [a for a in attempts if a.max_marks > 0]
    schools = {a.school_id for a in scored}

    if len(scored) < MIN_ATTEMPTS:
        return Difficulty(
            question_id, False, attempts=len(scored), schools=len(schools),
            unavailable_reason=(
                f"needs {MIN_ATTEMPTS} scored attempts, has {len(scored)}"
            ),
        )
    if len(schools) < MIN_SCHOOLS:
        return Difficulty(
            question_id, False, attempts=len(scored), schools=len(schools),
            unavailable_reason=(
                "seen in only one school -- a single school's result measures its teaching "
                "as much as the question, so difficulty is withheld until a second school "
                "has used this question"
            ),
        )

    facility = sum(a.awarded / a.max_marks for a in scored) / len(scored)
    return Difficulty(question_id, True, facility=facility,
                      attempts=len(scored), schools=len(schools))
