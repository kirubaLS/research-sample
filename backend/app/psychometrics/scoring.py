"""RIASEC scoring.

Two steps that cheap career tools skip, and both matter:

  * ipsative centering — without subtracting the person's own mean, a student who likes
    everything scores high on all six types and gets a meaningless "you could do anything".
  * the differentiation gate — when the profile is genuinely flat there is no preference to
    report, and the correct output is NO recommendation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.psychometrics.instrument import HEXAGON, SCALES, item_index, stream_matrix

#: below this, the profile is too flat to call
DIFFERENTIATION_FLOOR = 0.60
#: two streams closer than this are reported together, not ranked
STREAM_MARGIN = 0.05


@dataclass
class ScaleResult:
    scale: str
    raw: float
    centered: float
    percentile: float
    ci_low: float
    ci_high: float


@dataclass
class ProfileOutcome:
    scales: list[ScaleResult]
    holland_code: str | None
    differentiation: float
    consistency: int
    stream_fit: dict[str, float]
    top_streams: list[str]
    recommendation_withheld: bool = False
    withheld_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "scales": [
                {
                    "scale": s.scale, "raw": s.raw, "centered": round(s.centered, 3),
                    "percentile": round(s.percentile, 1),
                    "ci": [round(s.ci_low, 1), round(s.ci_high, 1)],
                }
                for s in self.scales
            ],
            "holland_code": self.holland_code,
            "differentiation": round(self.differentiation, 3),
            "consistency": self.consistency,
            "stream_fit": {k: round(v, 3) for k, v in self.stream_fit.items()},
            "top_streams": self.top_streams,
            "recommendation_withheld": self.recommendation_withheld,
            "withheld_reason": self.withheld_reason,
            "notes": self.notes,
        }


def raw_scores(by_item: dict[str, int]) -> dict[str, float]:
    idx = item_index()
    out = {s: 0.0 for s in SCALES}
    for item_id, value in by_item.items():
        it = idx.get(item_id)
        if it:
            out[it.scale] += value
    return out


def ipsative_centre(raw: dict[str, float]) -> dict[str, float]:
    """Subtract the person's own mean. Removes elevation and acquiescence bias."""
    mean = sum(raw.values()) / len(raw)
    return {s: v - mean for s, v in raw.items()}


def empirical_bayes_percentile(
    centered: dict[str, float],
    cohort: dict[str, list[float]] | None = None,
    *,
    prior_weight: float = 8.0,
) -> dict[str, tuple[float, float, float]]:
    """Percentile against the cohort, shrunk toward the prior while n is small.

    Cold start uses a theoretical normal; as a school accumulates sessions the empirical
    distribution takes over. Returns scale -> (percentile, ci_low, ci_high).
    """
    out: dict[str, tuple[float, float, float]] = {}
    for scale, value in centered.items():
        sample = (cohort or {}).get(scale, [])
        n = len(sample)
        if n >= 2:
            mu = sum(sample) / n
            var = sum((x - mu) ** 2 for x in sample) / max(n - 1, 1)
            sd = math.sqrt(var) if var > 0 else 1.0
        else:
            mu, sd = 0.0, 4.0                      # theoretical prior for a 6-item scale
        shrink = n / (n + prior_weight)
        mu = shrink * mu + (1 - shrink) * 0.0
        sd = shrink * sd + (1 - shrink) * 4.0

        z = (value - mu) / (sd or 1.0)
        pct = 100 * 0.5 * (1 + math.erf(z / math.sqrt(2)))
        # width reflects how little we know: wide while n is small
        half = 30.0 / math.sqrt(n + 1)
        out[scale] = (pct, max(0.0, pct - half), min(100.0, pct + half))
    return out


def hexagon_consistency(code: str) -> int:
    """3 = adjacent on Holland's hexagon, 2 = alternate, 1 = opposite."""
    if len(code) < 2:
        return 0
    i, j = HEXAGON.index(code[0]), HEXAGON.index(code[1])
    d = min((i - j) % 6, (j - i) % 6)
    return {0: 3, 1: 3, 2: 2, 3: 1}.get(d, 1)


def score(
    by_item: dict[str, int],
    *,
    cohort: dict[str, list[float]] | None = None,
    differentiation_floor: float = DIFFERENTIATION_FLOOR,
) -> ProfileOutcome:
    raw = raw_scores(by_item)
    centered = ipsative_centre(raw)
    pct = empirical_bayes_percentile(centered, cohort)

    scales = [
        ScaleResult(s, raw[s], centered[s], pct[s][0], pct[s][1], pct[s][2]) for s in SCALES
    ]

    ranked = sorted(SCALES, key=lambda s: centered[s], reverse=True)
    code = "".join(ranked[:3])

    spread = max(centered.values()) - min(centered.values())
    n_items_per_scale = 6
    # normalise differentiation by the maximum possible spread on this instrument
    differentiation = spread / (4 * n_items_per_scale)
    consistency = hexagon_consistency(code)

    W = stream_matrix()
    z = {s: centered[s] / (4 * n_items_per_scale) for s in SCALES}
    fit = {stream: sum(w.get(s, 0.0) * z[s] for s in SCALES) for stream, w in W.items()}
    lo = min(fit.values())
    hi = max(fit.values())
    rng = (hi - lo) or 1.0
    fit = {k: (v - lo) / rng for k, v in fit.items()}

    ordered = sorted(fit.items(), key=lambda kv: kv[1], reverse=True)
    top = [ordered[0][0]]
    if len(ordered) > 1 and (ordered[0][1] - ordered[1][1]) < STREAM_MARGIN:
        top.append(ordered[1][0])

    outcome = ProfileOutcome(
        scales=scales, holland_code=code, differentiation=differentiation,
        consistency=consistency, stream_fit=fit, top_streams=top,
    )

    if differentiation < differentiation_floor:
        outcome.recommendation_withheld = True
        outcome.holland_code = None
        outcome.top_streams = []
        outcome.withheld_reason = (
            "The profile is undifferentiated: this student's interests are close to equal "
            "across all six types, so no stream can be indicated from this test. "
            "Recommend a counselling conversation and a retest."
        )
    if len(top) > 1 and not outcome.recommendation_withheld:
        outcome.notes.append("Two streams are equally indicated; present both, do not rank them.")
    return outcome
