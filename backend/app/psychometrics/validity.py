"""Response-validity screening.

Roughly 5-8% of Class X sessions fail one of these checks. Catching them is what separates
a test from a form: an invalid session must never produce a recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from app.psychometrics.instrument import reverse_pairs

LONG_STRING_LIMIT = 8
MIN_MEDIAN_SECONDS = 1.5
INCONSISTENCY_LIMIT = 3.0


@dataclass
class Response:
    item_id: str
    value: int
    seconds: float | None = None


@dataclass
class ValidityReport:
    status: str                       # 'valid' | 'suspect' | 'invalid'
    longest_run: int = 0
    median_seconds: float | None = None
    inconsistency: float = 0.0
    completeness: float = 1.0
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "longest_run": self.longest_run,
            "median_seconds": self.median_seconds,
            "inconsistency": self.inconsistency,
            "completeness": self.completeness,
            "reasons": self.reasons,
        }


def longest_identical_run(values: list[int]) -> int:
    best = run = 0
    prev = None
    for v in values:
        run = run + 1 if v == prev else 1
        prev = v
        best = max(best, run)
    return best


def inconsistency_index(by_item: dict[str, int]) -> float:
    """Mean absolute difference across the reverse-keyed pairs.

    The pairs are ordinary-looking items, not a visible 'attention check' — teenagers spot
    those instantly.
    """
    diffs = [
        abs(by_item[a] - by_item[b])
        for a, b in reverse_pairs()
        if a in by_item and b in by_item
    ]
    return sum(diffs) / len(diffs) if diffs else 0.0


def screen(responses: list[Response], expected_items: int) -> ValidityReport:
    values = [r.value for r in responses]
    by_item = {r.item_id: r.value for r in responses}
    times = [r.seconds for r in responses if r.seconds is not None]

    rep = ValidityReport(status="valid")
    rep.longest_run = longest_identical_run(values)
    rep.median_seconds = median(times) if times else None
    rep.inconsistency = inconsistency_index(by_item)
    rep.completeness = len(responses) / expected_items if expected_items else 0.0

    if rep.completeness < 1.0:
        rep.status = "invalid"
        rep.reasons.append(f"incomplete: {len(responses)}/{expected_items} answered")
        return rep

    if rep.longest_run > LONG_STRING_LIMIT:
        rep.reasons.append(f"straight-lining: {rep.longest_run} identical answers in a row")
    if rep.median_seconds is not None and rep.median_seconds < MIN_MEDIAN_SECONDS:
        rep.reasons.append(f"median item time {rep.median_seconds:.1f}s below {MIN_MEDIAN_SECONDS}s")
    if rep.inconsistency > INCONSISTENCY_LIMIT:
        rep.reasons.append(f"reverse-pair inconsistency {rep.inconsistency:.1f}")

    if len(rep.reasons) >= 2:
        rep.status = "invalid"
    elif rep.reasons:
        rep.status = "suspect"
    return rep
