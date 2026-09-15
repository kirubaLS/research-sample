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


#: A read must be this confident in its best value before the value is asserted at all.
#: Below it the crop is not read as anything -- not as the best guess, not as a fallback.
MIN_CONFIDENCE = 0.55
#: And it must beat the runner-up by this much. A 0.50/0.48 split between 1 and 3 is not a
#: reading of a 1; it is a coin toss wearing a probability.
MIN_MARGIN = 0.15


def abstains(
    distribution: dict[float, float],
    *,
    min_confidence: float = MIN_CONFIDENCE,
    min_margin: float = MIN_MARGIN,
) -> bool:
    """Whether this read is too weak to assert a value.

    This is the whole of "never hallucinate", and it is a refusal rather than a fallback.
    A recogniser asked for a digit will always name one -- that is what the question
    forces -- so the guard cannot live inside the model. It lives here, where a weak read
    becomes no read.

    An abstention is not a loss. The candidate carries no value into L5, L6 sees a flat
    distribution over the legal values, and the teacher's totals may still determine the
    mark exactly. Where they cannot, L7 shows a person the crop. Both are outcomes; a
    guessed digit is not.
    """
    if not distribution:
        return True
    total = sum(distribution.values())
    if total <= 0:
        return True
    ranked = sorted((p / total for p in distribution.values()), reverse=True)
    if ranked[0] < min_confidence:
        return True
    runner_up = ranked[1] if len(ranked) > 1 else 0.0
    return (ranked[0] - runner_up) < min_margin


class Ensemble:
    """Several recognisers on one crop; agreement is the condition for asserting anything.

    Two independent reads that agree are far better evidence than one read that is
    confident, because the failure modes of a single model are systematic -- it will be
    confidently wrong about the same badly-formed 1 every time it sees it, and repeating
    the question will not help.

    Disagreement produces a deliberately flat distribution rather than an average. An
    average of 3-at-0.8 and 1-at-0.8 is a distribution that looks moderately sure of
    something, which is the one thing this must never manufacture.
    """

    def __init__(self, *recognizers: MarkRecognizer, require_agreement: bool = True):
        if not recognizers:
            raise ValueError("an ensemble needs at least one recogniser")
        self.recognizers = recognizers
        self.require_agreement = require_agreement

    def predict(self, crop: object, legal_values: list[float]) -> dict[float, float]:
        reads = [clamp(r.predict(crop, legal_values), legal_values) for r in self.recognizers]
        bests = [max(d, key=lambda v: d[v]) for d in reads if d]
        if not bests:
            return flat(legal_values)
        if self.require_agreement and len(set(bests)) > 1:
            return flat(legal_values)

        combined = {v: 0.0 for v in legal_values}
        for read in reads:
            total = sum(read.values()) or 1.0
            for value, weight in read.items():
                combined[value] += weight / total
        return {v: p for v, p in combined.items() if p > 0} or flat(legal_values)


def clamp(distribution: dict[float, float], legal_values: list[float]) -> dict[float, float]:
    """Keep only legal values, and fall back to flat if nothing legal survives.

    A recogniser asked for a mark out of 3 can still answer 5. Passing that through would
    put an impossible value into the assignment; dropping it silently would leave the
    question with no distribution at all. Neither is acceptable, so an answer with no legal
    mass becomes an honest 'no information'.
    """
    kept = {v: p for v, p in distribution.items() if v in set(legal_values) and p > 0}
    return kept or flat(legal_values)
