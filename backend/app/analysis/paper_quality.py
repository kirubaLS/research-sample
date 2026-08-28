"""Is the paper well built, and does it match the board?

Two independent questions. The second is the finding a principal has never been shown
before, and it is why the CBSE blueprint prior must never be applied to a school's own
paper: the deviation IS the finding.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

CBSE_TIER_TARGET = {"R&U": 0.54, "AP": 0.24, "AEC": 0.22}


@dataclass
class ItemStat:
    address: str
    max_marks: float
    difficulty: float          # p-value: mean score rate. High = easy.
    discrimination: float      # point-biserial with the rest-of-test score
    n: int
    flag: str | None = None


def item_analysis(
    scores: dict[str, dict[str, float]],
    max_marks: dict[str, float],
) -> list[ItemStat]:
    """``scores[student][address] = earned``. Classic item analysis."""
    addresses = sorted(max_marks)
    students = sorted(scores)
    if not students:
        return []

    totals = {s: sum(scores[s].get(a, 0.0) for a in addresses) for s in students}
    out: list[ItemStat] = []

    for a in addresses:
        vals = [scores[s].get(a, 0.0) for s in students]
        mm = max_marks[a] or 1.0
        rates = [v / mm for v in vals]
        p = sum(rates) / len(rates)

        rest = [totals[s] - scores[s].get(a, 0.0) for s in students]
        disc = _pearson(rates, rest)

        flag = None
        if disc is not None and disc < 0:
            flag = "negative_discrimination"      # likely a mis-key or a marking error
        elif disc is not None and disc < 0.2:
            flag = "low_discrimination"
        elif p >= 0.98 or p <= 0.02:
            flag = "no_variance"
        out.append(ItemStat(a, mm, round(p, 4), round(disc or 0.0, 4), len(students), flag))
    return out


def _pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=False))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x))
    dy = math.sqrt(sum((b - my) ** 2 for b in y))
    return num / (dx * dy) if dx > 0 and dy > 0 else None


def cronbach_alpha(scores: dict[str, dict[str, float]], addresses: list[str]) -> float | None:
    students = sorted(scores)
    k = len(addresses)
    if k < 2 or len(students) < 3:
        return None
    per_item_var = []
    for a in addresses:
        vals = [scores[s].get(a, 0.0) for s in students]
        m = sum(vals) / len(vals)
        per_item_var.append(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))
    totals = [sum(scores[s].get(a, 0.0) for a in addresses) for s in students]
    mt = sum(totals) / len(totals)
    total_var = sum((t - mt) ** 2 for t in totals) / (len(totals) - 1)
    if total_var <= 0:
        return None
    return (k / (k - 1)) * (1 - sum(per_item_var) / total_var)


@dataclass
class AlignmentReport:
    observed: dict[str, float]
    target: dict[str, float]
    chi_square: float
    alignment_score: float          # 0..1, 1 = perfect match
    verdict: str

    def as_dict(self) -> dict:
        return {
            "observed": {k: round(v, 4) for k, v in self.observed.items()},
            "target": self.target,
            "chi_square": round(self.chi_square, 3),
            "alignment_score": round(self.alignment_score, 3),
            "verdict": self.verdict,
        }


def typology_alignment(
    marks_by_tier: dict[str, float],
    target: dict[str, float] | None = None,
) -> AlignmentReport:
    """Observed tier mark-share vs the CBSE target, as chi-square plus a 0-1 score.

    This is reported, never corrected. A school paper that is recall-heavy is not an error
    in our extraction; it is the most valuable line in the report.
    """
    tgt = target or CBSE_TIER_TARGET
    total = sum(marks_by_tier.values()) or 1.0
    observed = {t: marks_by_tier.get(t, 0.0) / total for t in tgt}

    chi = 0.0
    for t, share in tgt.items():
        exp = share * total
        obs = marks_by_tier.get(t, 0.0)
        if exp > 0:
            chi += (obs - exp) ** 2 / exp

    tvd = 0.5 * sum(abs(observed[t] - tgt[t]) for t in tgt)   # total variation distance
    alignment = max(0.0, 1.0 - tvd / 0.5)

    worst = max(tgt, key=lambda t: observed[t] - tgt[t])
    under = min(tgt, key=lambda t: observed[t] - tgt[t])
    if alignment >= 0.85:
        verdict = "Paper is well aligned to the expected board distribution."
    else:
        verdict = (
            f"Paper is {worst}-heavy relative to the expected board distribution: "
            f"{observed[worst]:.0%} {worst} against a {tgt[worst]:.0%} target; "
            f"{under} under-represented at {observed[under]:.0%} against {tgt[under]:.0%}."
        )
    return AlignmentReport(observed, tgt, chi, alignment, verdict)


def chapter_coverage(
    marks_by_chapter: dict[str, float],
    board_weights: dict[str, float],
) -> dict:
    total = sum(marks_by_chapter.values()) or 1.0
    observed = {c: marks_by_chapter.get(c, 0.0) / total for c in board_weights}
    missing = [c for c, w in board_weights.items() if marks_by_chapter.get(c, 0.0) <= 0]
    tvd = 0.5 * sum(abs(observed[c] - board_weights[c] / 100.0) for c in board_weights)
    return {
        "observed_share": {k: round(v, 4) for k, v in observed.items()},
        "coverage_gaps": missing,
        "alignment_score": round(max(0.0, 1.0 - tvd / 0.5), 3),
    }
