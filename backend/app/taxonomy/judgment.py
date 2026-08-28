"""Layer 2B review gate: two reviewers, disagreements resolved before a question ships.

The schema treats 2A as mechanical and 2B as judgment. Judgment fields get a process, not
a confidence score: a question is shippable only when every 2B field carries two
independent agreeing reads, or a recorded resolution.

Cohen's kappa is reported per field, per reviewer pair, and is a diagnostic about the
*field* rather than the reviewers. A field that cannot reach agreement is badly defined --
which the schema already suspects of Complexity against literary interpretation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

#: Layer 2B fields. Kept here rather than imported from models so this module stays
#: usable on plain data in a notebook or a review script.
JUDGMENT_FIELDS = ("skill_required", "complexity", "dependency_level")

COMPLEXITY_VALUES = ("SINGLE_STEP", "MULTI_STEP", "NOT_APPLICABLE")
DEPENDENCY_VALUES = ("SINGLE_CONCEPT", "MULTI_CONCEPT")


@dataclass(frozen=True)
class Judgment:
    field: str
    value: str
    reviewer_id: str
    #: kappa pairs reviewers per question, so it is required for agreement reporting.
    #: The ship gate works on one question at a time and does not read it.
    question_id: str = ""
    is_resolution: bool = False


@dataclass
class FieldStatus:
    field: str
    state: str          # AGREED | RESOLVED | DISPUTED | AWAITING_SECOND | MISSING
    value: str | None
    reason: str


@dataclass
class Gate:
    shippable: bool
    fields: dict[str, FieldStatus] = field(default_factory=dict)

    def blockers(self) -> list[str]:
        return [s.reason for s in self.fields.values() if s.state not in ("AGREED", "RESOLVED")]


def _status(name: str, judgments: list[Judgment]) -> FieldStatus:
    if not judgments:
        return FieldStatus(name, "MISSING", None, f"{name}: no judgment recorded")

    # A resolution is deliberate and final -- it is how a disagreement is closed.
    resolutions = [j for j in judgments if j.is_resolution]
    if resolutions:
        return FieldStatus(
            name, "RESOLVED", resolutions[-1].value, f"{name}: resolved"
        )

    independent = [j for j in judgments if not j.is_resolution]
    # two reads from ONE reviewer is one opinion twice, not agreement
    by_reviewer = {j.reviewer_id: j.value for j in independent}
    if len(by_reviewer) < 2:
        return FieldStatus(
            name, "AWAITING_SECOND", None,
            f"{name}: only one reviewer has judged it; a second independent read is required",
        )

    values = set(by_reviewer.values())
    if len(values) == 1:
        return FieldStatus(name, "AGREED", values.pop(), f"{name}: agreed")
    return FieldStatus(
        name, "DISPUTED", None,
        f"{name}: reviewers disagree ({', '.join(sorted(values))}); "
        f"record a resolution before this question ships",
    )


def gate(judgments: list[Judgment], required: tuple[str, ...] = JUDGMENT_FIELDS) -> Gate:
    """Can this question ship? Every required 2B field must be agreed or resolved."""
    grouped: dict[str, list[Judgment]] = defaultdict(list)
    for j in judgments:
        grouped[j.field].append(j)

    statuses = {name: _status(name, grouped.get(name, [])) for name in required}
    return Gate(
        shippable=all(s.state in ("AGREED", "RESOLVED") for s in statuses.values()),
        fields=statuses,
    )


def cohens_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Agreement between two reviewers, corrected for agreement by chance.

    Returns None when it is undefined rather than a misleading number: with fewer than two
    items, or when both reviewers used exactly one label for everything (perfect expected
    agreement, so the correction divides by zero). A field that always gets the same answer
    tells you nothing about whether reviewers can tell its values apart.
    """
    n = len(pairs)
    if n < 2:
        return None

    observed = sum(1 for a, b in pairs if a == b) / n

    labels = {label for pair in pairs for label in pair}
    expected = sum(
        (sum(1 for a, _ in pairs if a == label) / n)
        * (sum(1 for _, b in pairs if b == label) / n)
        for label in labels
    )
    if expected >= 1.0:
        return None
    return (observed - expected) / (1 - expected)


def field_agreement(judgments: list[Judgment]) -> dict[str, float | None]:
    """Kappa per field across every reviewer pair that judged the same questions.

    Read it as a statement about the field: a persistently low value means the definition
    is ambiguous, not that a reviewer is careless.
    """
    return {
        name: cohens_kappa(_paired(name, judgments))
        for name in JUDGMENT_FIELDS
    }


def _paired(name: str, judgments: list[Judgment]) -> list[tuple[str, str]]:
    """Every (reviewer A, reviewer B) value pair for one field, one pair per question."""
    by_question: dict[str, dict[str, str]] = defaultdict(dict)
    for j in judgments:
        if j.field == name and not j.is_resolution:
            by_question[j.question_id][j.reviewer_id] = j.value

    out: list[tuple[str, str]] = []
    for reviewers in by_question.values():
        ordered = [reviewers[r] for r in sorted(reviewers)]
        if len(ordered) >= 2:
            out.append((ordered[0], ordered[1]))
    return out
