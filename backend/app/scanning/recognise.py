"""L4 -- Recognition: what is written in this crop, as a distribution.

A distribution, never a value. L6 repairs a misread by re-weighting the alternatives
against the teacher's own totals, and it can only do that if the alternatives survive this
far. Returning the argmax here would be discarding the evidence that makes the pipeline
work, and would look like a simplification.

The recogniser is behind a Protocol for the same reason the classifier's judge is: the
constraint layers above must be exercisable, and testable, without a model.
"""

from __future__ import annotations

from typing import Protocol

#: Below this the crop is not a digit at all -- a stray dot, a comma, part of a diagram.
#: Reported rather than silently spread across the legal values.
ILLEGIBLE = "illegible"


class MarkRecognizer(Protocol):
    def predict(self, crop: object, legal_values: list[float]) -> dict[float, float]:
        """A probability over exactly ``legal_values``. Need not be normalised."""
        ...


def flat(legal_values: list[float]) -> dict[float, float]:
    """What an unreadable crop is worth: nothing said, everything still possible.

    Used where a crop could not be read at all. It is deliberately not a refusal -- L6 may
    still recover the value from the totals alone, which is the whole reason the totals are
    collected.
    """
    if not legal_values:
        return {}
    share = 1.0 / len(legal_values)
    return {v: share for v in legal_values}


def clamp(distribution: dict[float, float], legal_values: list[float]) -> dict[float, float]:
    """Keep only legal values, and fall back to flat if nothing legal survives.

    A recogniser asked for a mark out of 3 can still answer 5. Passing that through would
    put an impossible value into the assignment; dropping it silently would leave the
    question with no distribution at all. Neither is acceptable, so an answer with no legal
    mass becomes an honest 'no information'.
    """
    kept = {v: p for v, p in distribution.items() if v in set(legal_values) and p > 0}
    return kept or flat(legal_values)
