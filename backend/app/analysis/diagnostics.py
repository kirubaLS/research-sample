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
from dataclasses import dataclass, field

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
    #: Everything a teacher needs to check this one mark by hand: the question as it was
    #: read off the paper, where it was placed, and what that placement rested on. Carried
    #: rather than recomputed, so a finding and its proof can never disagree.
    proof: dict | None = None

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
    #: The questions this number is made of, in paper order. Never empty for a finding the
    #: report shows: a line nobody can check is not a finding, it is an assertion.
    evidence: tuple[dict, ...] = ()

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "scope": self.scope, "key": self.key,
            "earned": self.earned, "available": self.available,
            "questions": self.questions,
            "rate": None if self.rate is None else round(self.rate, 4),
            "ci": None if self.ci is None else [round(self.ci[0], 4), round(self.ci[1], 4)],
            "sufficient": self.sufficient, "message": self.message,
            "evidence": list(self.evidence),
        }


@dataclass
class _Bucket:
    earned: float = 0.0
    available: float = 0.0
    rows: list[MarkRow] = field(default_factory=list)

    @property
    def questions(self) -> int:
        return len(self.rows)


def _aggregate(rows: list[MarkRow], keyfn) -> dict[str, _Bucket]:
    """Keeps the contributing rows, not just their totals.

    The rows were being summed and discarded, which is why no figure in the report could
    be traced back to the questions it came from. They cost nothing to carry.
    """
    acc: dict[str, _Bucket] = defaultdict(_Bucket)
    for r in rows:
        if not r.counts:
            continue
        for key in keyfn(r):
            if key is None:
                continue
            b = acc[key]
            b.earned += r.earned
            b.available += r.max_marks
            b.rows.append(r)
    return dict(acc)


def _evidence(rows: list[MarkRow]) -> tuple[dict, ...]:
    """One entry per contributing question, in paper order.

    Marks are restated here from the same MarkRow the total was computed from, so the
    proof reconciles to the finding by construction rather than by a second lookup that
    could drift.
    """
    out = []
    for r in sorted(rows, key=lambda r: r.address):
        entry = {
            "address": r.address,
            "earned": r.earned,
            "max_marks": r.max_marks,
            "lost": r.max_marks - r.earned,
            "state": r.state,
            "tier": r.tier,
            "chapter": r.chapter,
            "board_unit": r.board_unit,
            "concept_family": r.concept_family,
        }
        entry.update(r.proof or {})
        out.append(entry)
    return tuple(out)


def summarise(
    rows: list[MarkRow],
    *,
    scope: str,
    keyfn,
    kind: str,
) -> list[Finding]:
    s = get_settings()
    out: list[Finding] = []
    for key, b in sorted(_aggregate(rows, keyfn).items()):
        earned, available, n = b.earned, b.available, b.questions
        proof = _evidence(b.rows)
        sufficient = available >= s.evidence_floor_marks and n >= s.evidence_floor_questions
        if not sufficient:
            out.append(
                Finding(
                    kind, scope, key, earned, available, n, None, None, False,
                    f"Insufficient evidence in this paper: only {available:g} mark(s) "
                    f"across {n} question(s).",
                    evidence=proof,
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
                evidence=proof,
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
        b = agg.get(unit)
        earned, available, n = (b.earned, b.available, b.questions) if b else (0.0, 0.0, 0)
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
                "evidence": list(_evidence(b.rows)) if b else [],
            }
        )

    total = sum(i["indicator"] for i in indicators) or 1.0
    for i in indicators:
        i["share"] = round(i["indicator"] / total, 4)
    indicators.sort(key=lambda i: i["indicator"], reverse=True)

    gaps = [
        CoverageGap(
            unit, weight,
            # The code is not repeated into the sentence: the row already names the unit,
            # and a reader should never be shown a taxonomy code where a name belongs.
            # The weight is shown beside the unit's name by whatever displays this, so
            # repeating it here printed the same percentage twice in one sentence.
            "No marks in this paper, so the test says nothing about it either way.",
        )
        for unit, weight in board_weights.items()
        if unit not in agg or agg[unit].available <= 0
    ]
    return indicators, gaps


#: At or above this rate a topic is a strength, not a place to work. One constant, used
#: by both selectors, because the same report calling one topic both would be incoherent.
STRENGTH_FLOOR = 0.8


def select_findings(
    findings: list[Finding],
    board_weights: dict[str, float],
    cap: int = 5,
    floor: float = STRENGTH_FLOOR,
) -> list[Finding]:
    """Rank by board weight x evidence strength x actionability, then cap.

    A report with fourteen findings changes no behaviour.

    Anything at or above ``floor`` is dropped before ranking. Ranking alone put a topic
    scored 94% under "where to work next" whenever the paper had fewer than five topics --
    the list was never wrong about the number, it was wrong about what the number meant.
    """
    def rank(f: Finding) -> float:
        if not f.sufficient or f.rate is None:
            return -1.0
        weight = board_weights.get(f.key.split("|")[0], 5.0) / 100.0
        evidence = min(f.available / 6.0, 1.0)
        actionability = 1.0 - f.rate
        return weight * evidence * actionability

    ranked = sorted(
        (f for f in findings if f.sufficient and (f.rate is None or f.rate < floor)),
        key=rank,
        reverse=True,
    )
    return ranked[:cap]


def select_strengths(
    findings: list[Finding], cap: int = 5, floor: float = STRENGTH_FLOOR
) -> list[Finding]:
    """The other half of the diagnosis, computed from the same numbers.

    A report that lists only losses tells a boy nothing about what he already has, and a
    teacher cannot tell "weak everywhere" from "weak in one place". Same evidence floor as
    the losses: a strength claimed on one 2-mark question is not a strength.

    Qualifying is on the observed rate, ranking is on the *lower* end of the Wilson
    interval. Both matter and they do different jobs. Qualifying on the interval instead
    would admit almost nothing at the sizes this product sees -- 11 of 12 marks has a lower
    bound near 0.65 -- so a boy who got nearly everything right would be told he has no
    strengths, which is false. Ranking on the interval is what stops 4/4 on one question
    from outranking 11/12.
    """
    def rank(f: Finding) -> float:
        assert f.ci is not None
        return f.ci[0]

    strong = [
        f for f in findings
        if f.sufficient and f.rate is not None and f.ci is not None and f.rate >= floor
    ]
    return sorted(strong, key=rank, reverse=True)[:cap]
