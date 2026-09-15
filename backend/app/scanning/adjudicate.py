"""L7 -- Adjudication: what is accepted, what a person sees, and what becomes training.

Three outcomes and no fourth. A mark is accepted, or it is queued for a person with the
crop that produced it, or the whole script is flagged. Anything that cannot be routed to
one of the three is the case this layer exists to prevent: a number that reached a report
without anyone, machine or human, having stood behind it.

Confidence is calibrated against the solver's own margin rather than the recogniser's
self-report. A recogniser's confidence says how sure it is about a crop; the margin says
how much better the accepted assignment was than the next feasible one, which is the
quantity that actually predicts whether the answer is right.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Route = Literal["accepted", "review", "flagged"]


@dataclass(frozen=True)
class MarkFact:
    """One mark, and everything needed to defend it."""

    address: str
    value: float
    confidence: float
    route: Route
    reason: str | None = None
    #: the crop a reviewer is shown; an identifier, never the pixels themselves
    crop_id: str | None = None


@dataclass
class Adjudication:
    facts: list[MarkFact] = field(default_factory=list)
    flagged: bool = False
    flag_reason: str | None = None

    @property
    def accepted(self) -> list[MarkFact]:
        return [f for f in self.facts if f.route == "accepted"]

    @property
    def queued(self) -> list[MarkFact]:
        return [f for f in self.facts if f.route == "review"]

    @property
    def review_load(self) -> int:
        return len(self.queued)


def adjudicate(
    marks: dict[str, float],
    confidence: dict[str, float],
    *,
    threshold: float,
    feasible: bool,
    infeasible_reason: str | None = None,
    crops: dict[str, str] | None = None,
) -> Adjudication:
    """Route every mark. An infeasible script flags whole, and queues nothing.

    Queueing the individual marks of a script whose totals do not add up would send a
    reviewer to check twenty digits when the real fault is a missing page or the teacher's
    own arithmetic. The script is the unit of that failure, so the script is what is
    flagged.
    """
    if not feasible:
        return Adjudication(
            facts=[
                MarkFact(address, value, 0.0, "flagged", infeasible_reason, (crops or {}).get(address))
                for address, value in sorted(marks.items())
            ],
            flagged=True,
            flag_reason=infeasible_reason or "the marks could not be reconciled with the totals",
        )

    facts: list[MarkFact] = []
    for address, value in sorted(marks.items()):
        conf = confidence.get(address, 0.0)
        accepted = conf >= threshold
        facts.append(MarkFact(
            address=address,
            value=value,
            confidence=conf,
            route="accepted" if accepted else "review",
            reason=None if accepted else f"confidence {conf:.2f} is below {threshold:.2f}",
            crop_id=(crops or {}).get(address),
        ))
    return Adjudication(facts=facts)
