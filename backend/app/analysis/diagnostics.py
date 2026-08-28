"""Deterministic diagnosis. No model appears anywhere in this module.

Teachers check these numbers by hand, so they must reconcile to the mark sheet exactly.

Three disciplines that keep the output honest at n=40:
  * every rate carries its denominator and a Wilson interval
  * NOT_OFFERED is excluded from denominators — the unattempted half of a choice pair is
    absence of evidence, not evidence of weakness
  * an evidence floor: under 2 marks or 2 questions we report 'insufficient evidence in
    this paper', never a percentage
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from app.config import get_settings

Z = 1.959963984540054  # 95%


def wilson_interval(successes: float, trials: float, z: float = Z) -> tuple[float, float]:
    """Wilson score interval — behaves sensibly at the tiny denominators this product has."""
    if trials <= 0:
        return (0.0, 1.0)
    p = successes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = (z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


@dataclass
class MarkRow:
    """One resolved mark for one student on one question address."""

    student_id: str
    address: str
    earned: float
    max_marks: float
    state: str = "awarded"        # awarded | absent | not_offered
    skills: tuple[str, ...] = ()
    tier: str | None = None
    chapter: str | None = None          # null for a skill-anchored question -- by design
    board_unit: str | None = None       # what board weighting is computed against
    concept_family: str | None = None   # the axis that survives a null chapter

    @property
    def counts(self) -> bool:
        return self.state == "awarded"


@dataclass
class Finding:
    kind: str
    scope: str
    key: str
    earned: float
    available: float
    questions: int
    rate: float | None
    ci: tuple[float, float] | None
    sufficient: bool
    message: str

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "scope": self.scope, "key": self.key,
            "earned": self.earned, "available": self.available,
            "questions": self.questions,
            "rate": None if self.rate is None else round(self.rate, 4),
            "ci": None if self.ci is None else [round(self.ci[0], 4), round(self.ci[1], 4)],
            "sufficient": self.sufficient, "message": self.message,
        }


def _aggregate(rows: list[MarkRow], keyfn) -> dict[str, tuple[float, float, int]]:
    acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0])
    for r in rows:
        if not r.counts:
            continue
        for key in keyfn(r):
            if key is None:
                continue
            acc[key][0] += r.earned
            acc[key][1] += r.max_marks
            acc[key][2] += 1
    return {k: (v[0], v[1], int(v[2])) for k, v in acc.items()}


def summarise(
    rows: list[MarkRow],
    *,
    scope: str,
    keyfn,
    kind: str,
) -> list[Finding]:
    s = get_settings()
    out: list[Finding] = []
    for key, (earned, available, n) in sorted(_aggregate(rows, keyfn).items()):
        sufficient = available >= s.evidence_floor_marks and n >= s.evidence_floor_questions
        if not sufficient:
            out.append(
                Finding(
                    kind, scope, key, earned, available, n, None, None, False,
                    f"Insufficient evidence in this paper: only {available:g} mark(s) "
                    f"across {n} question(s).",
                )
            )
            continue
        rate = earned / available if available else 0.0
        ci = wilson_interval(earned, available)
        lost = available - earned
        out.append(
            Finding(
                kind, scope, key, earned, available, n, rate, ci, True,
                f"Scored {earned:g} of {available:g} ({rate:.0%}); lost {lost:g}.",
            )
        )
    return out


def by_chapter(rows: list[MarkRow]) -> list[Finding]:
    """Optional rollup. A skill-anchored question has no chapter and is excluded here."""
    return summarise(
        [r for r in rows if r.chapter is not None],
        scope="chapter", kind="loss", keyfn=lambda r: (r.chapter,),
    )


def by_concept_family(rows: list[MarkRow]) -> list[Finding]:
    """The primary axis.

    Chapter is conditional -- Reading and Grammar questions have none -- so keying the
    diagnosis on it silently dropped every skill-anchored question from the report.
    Concept Family is present on every question and is held constant across cycles, which
    is also what makes a trend across tests comparable.
    """
    return summarise(rows, scope="concept_family", kind="loss",
                     keyfn=lambda r: (r.concept_family,))


def by_skill(rows: list[MarkRow]) -> list[Finding]:
    return summarise(rows, scope="subtopic", kind="loss", keyfn=lambda r: r.skills)


def by_tier(rows: list[MarkRow]) -> list[Finding]:
    return summarise(rows, scope="tier", kind="loss", keyfn=lambda r: (r.tier,))


def skill_by_tier(rows: list[MarkRow]) -> list[Finding]:
    """The cross-tab that *is* the diagnosis.

    High R&U with low AP on the same sub-topic is the "knows the formula, cannot apply it"
    signature — and it is only detectable when the paper contains both tiers for that
    sub-topic. Where it does not, we say so instead of asserting a diagnosis the paper
    cannot support.
    """
    return summarise(
        rows,
        scope="subtopic_x_tier",
        kind="crosstab",
        keyfn=lambda r: tuple(f"{sk}|{r.tier}" for sk in r.skills if r.tier),
    )


@dataclass
class CoverageGap:
    board_unit: str
    board_weight: float
    message: str


def board_weighted_indicator(
    rows: list[MarkRow],
    board_weights: dict[str, float],
) -> tuple[list[dict], list[CoverageGap]]:
    """(marks lost in board unit / marks available in board unit) x board weight.

    Reported with a credible interval, and normalised as a share of total indicator mass so
    "where do I spend the next two weeks" has a defensible answer. A unit with board
    weight but zero marks in this paper is a *coverage gap*, never a zero.

    Keyed on the board unit, not the chapter: CBSE publishes weightage per unit, and a
    unit may span several chapters or exist where none does.
    """
    agg = _aggregate(rows, lambda r: (r.board_unit,))
    indicators: list[dict] = []
    for unit, weight in board_weights.items():
        earned, available, n = agg.get(unit, (0.0, 0.0, 0))
        if available <= 0:
            continue
        loss_rate = (available - earned) / available
        lo, hi = wilson_interval(available - earned, available)
        indicators.append(
            {
                "board_unit": unit, "board_weight": weight,
                "loss_rate": round(loss_rate, 4),
                "indicator": round(loss_rate * weight, 4),
                "indicator_ci": [round(lo * weight, 4), round(hi * weight, 4)],
                "marks_available": available, "questions": n,
            }
        )

    total = sum(i["indicator"] for i in indicators) or 1.0
    for i in indicators:
        i["share"] = round(i["indicator"] / total, 4)
    indicators.sort(key=lambda i: i["indicator"], reverse=True)

    gaps = [
        CoverageGap(
            unit, weight,
            f"This paper carries no marks for {unit}, which is {weight:.0f}% of the board "
            f"weighting. The test gives you no information about it.",
        )
        for unit, weight in board_weights.items()
        if agg.get(unit, (0.0, 0.0, 0))[1] <= 0
    ]
    return indicators, gaps


def select_findings(findings: list[Finding], board_weights: dict[str, float], cap: int = 5) -> list[Finding]:
    """Rank by board weight x evidence strength x actionability, then cap.

    A report with fourteen findings changes no behaviour.
    """
    def rank(f: Finding) -> float:
        if not f.sufficient or f.rate is None:
            return -1.0
        weight = board_weights.get(f.key.split("|")[0], 5.0) / 100.0
        evidence = min(f.available / 6.0, 1.0)
        actionability = 1.0 - f.rate
        return weight * evidence * actionability

    ranked = sorted((f for f in findings if f.sufficient), key=rank, reverse=True)
    return ranked[:cap]
