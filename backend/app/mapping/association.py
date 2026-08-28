"""Binding a mark to the question it belongs to.

The mark can be anywhere — left margin, right margin, above the answer, inside the
margin. A fixed region-of-interest does not survive contact with a real script, so this
is solved as a *constrained assignment problem*.

Two passes, and the second one is what a competitor on a generic OCR API will not have:

  pass 1  build a cost matrix and solve it optimally with the Hungarian algorithm
  pass 2  fit the teacher's own layout convention from the confident bindings, rebuild the
          matrix with that convention as a prior, and solve again

A teacher is highly consistent within a script. The bindings that were coin-flips in
pass 1 are then decided by the teacher's own habit.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

PENALTY = 6.0
BIG = 1e6


@dataclass(frozen=True)
class Anchor:
    """A question serial number written by the student — CBSE requires them to write it."""

    address: str
    page: int
    x: float
    y: float
    block_top: float | None = None   # answer-block extent, from the student ink layer
    block_bottom: float | None = None
    max_marks: float = 1.0
    step: float = 1.0


@dataclass(frozen=True)
class MarkCandidate:
    """A red numeral found in the teacher ink layer."""

    candidate_id: str
    page: int
    x: float
    y: float
    value: float | None = None
    confidence: float = 1.0


@dataclass
class Convention:
    """The teacher's fitted habit for this script."""

    dx: float = 0.0
    dy: float = 0.0
    side: str = "unknown"     # 'left' | 'right' | 'unknown'
    dist_sd: float = 120.0
    fitted_from: int = 0

    @property
    def is_fitted(self) -> bool:
        return self.fitted_from >= 3


@dataclass
class Binding:
    anchor: Anchor
    mark: MarkCandidate | None
    cost: float
    margin: float = 0.0   # cost gap to the runner-up; large => confident

    @property
    def confident(self) -> bool:
        return self.mark is not None and self.margin >= 1.0


@dataclass
class AssociationResult:
    bindings: list[Binding] = field(default_factory=list)
    convention: Convention = field(default_factory=Convention)
    unassigned_marks: list[MarkCandidate] = field(default_factory=list)

    @property
    def confident_bindings(self) -> list[Binding]:
        return [b for b in self.bindings if b.confident]


def _legal_values(max_marks: float, step: float) -> list[float]:
    n = int(round(max_marks / step))
    return [round(i * step, 2) for i in range(n + 1)]


def _pair_cost(
    mark: MarkCandidate,
    anchor: Anchor,
    convention: Convention,
    weights: dict[str, float],
) -> float:
    if mark.page != anchor.page:
        return BIG

    dy = mark.y - anchor.y
    dx = mark.x - anchor.x

    cost = weights["w1"] * abs(dy) / 100.0

    # answer-block containment: does the mark fall inside this question's answer region?
    if anchor.block_top is not None and anchor.block_bottom is not None:
        if not (anchor.block_top - 20 <= mark.y <= anchor.block_bottom + 20):
            cost += weights["w2"] * PENALTY
    elif dy < -30:  # a mark above its own anchor is unusual
        cost += weights["w2"] * PENALTY * 0.5

    # side consistency against the fitted convention
    if convention.is_fitted:
        side = "right" if dx >= 0 else "left"
        if side != convention.side:
            cost += weights["w3"] * PENALTY
        cost += weights["w3"] * abs(dy - convention.dy) / max(convention.dist_sd, 1.0)

    # value plausibility: a 7 next to a 3-mark question is unlikely
    if mark.value is not None:
        if mark.value > anchor.max_marks + 1e-9:
            cost += weights["w5"] * PENALTY * 2
        elif mark.value not in _legal_values(anchor.max_marks, anchor.step):
            cost += weights["w5"] * PENALTY

    # a low-confidence read should bind less eagerly
    cost += weights["w6"] * (1.0 - min(max(mark.confidence, 0.0), 1.0))
    return cost


def _solve_once(
    marks: list[MarkCandidate],
    anchors: list[Anchor],
    convention: Convention,
    weights: dict[str, float],
) -> tuple[list[Binding], list[MarkCandidate]]:
    if not marks or not anchors:
        return [Binding(a, None, BIG) for a in anchors], list(marks)

    cost = np.full((len(marks), len(anchors)), BIG, dtype=float)
    for i, m in enumerate(marks):
        for j, a in enumerate(anchors):
            cost[i, j] = _pair_cost(m, a, convention, weights)

    rows, cols = linear_sum_assignment(cost)
    assigned: dict[int, tuple[int, float]] = {}
    for r, c in zip(rows, cols, strict=False):
        if cost[r, c] >= BIG:
            continue
        assigned[c] = (r, float(cost[r, c]))

    bindings: list[Binding] = []
    for j, anchor in enumerate(anchors):
        if j not in assigned:
            bindings.append(Binding(anchor, None, BIG))
            continue
        i, c = assigned[j]
        column = np.sort(cost[:, j])
        runner_up = float(column[1]) if len(column) > 1 else BIG
        bindings.append(Binding(anchor, marks[i], c, margin=max(runner_up - c, 0.0)))

    used = {i for i, _ in assigned.values()}
    unassigned = [m for i, m in enumerate(marks) if i not in used]
    return bindings, unassigned


def fit_convention(bindings: list[Binding]) -> Convention:
    """Learn the teacher's habit from the bindings that were not close calls."""
    confident = [b for b in bindings if b.confident and b.mark is not None]
    if len(confident) < 3:
        return Convention()

    dxs = [b.mark.x - b.anchor.x for b in confident]          # type: ignore[union-attr]
    dys = [b.mark.y - b.anchor.y for b in confident]          # type: ignore[union-attr]
    right = sum(1 for d in dxs if d >= 0)
    side = "right" if right * 2 >= len(dxs) else "left"
    sd = statistics.pstdev(dys) if len(dys) > 1 else 120.0
    return Convention(
        dx=statistics.median(dxs),
        dy=statistics.median(dys),
        side=side,
        dist_sd=max(sd, 20.0),
        fitted_from=len(confident),
    )


DEFAULT_WEIGHTS = {"w1": 1.0, "w2": 1.0, "w3": 1.0, "w5": 1.0, "w6": 0.5}


def associate(
    marks: list[MarkCandidate],
    anchors: list[Anchor],
    *,
    weights: dict[str, float] | None = None,
    refit: bool = True,
) -> AssociationResult:
    """Two-pass association. Returns bindings plus the convention that was fitted."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}

    bindings, unassigned = _solve_once(marks, anchors, Convention(), w)
    convention = fit_convention(bindings) if refit else Convention()

    if convention.is_fitted:
        bindings, unassigned = _solve_once(marks, anchors, convention, w)

    return AssociationResult(bindings=bindings, convention=convention, unassigned_marks=unassigned)


def bindings_to_distributions(
    result: AssociationResult,
    *,
    floor: float = 0.02,
) -> dict[str, dict[float, float]]:
    """Turn bindings into per-question distributions for the constraint solver.

    An unbound anchor gets a flat distribution over its legal values — the solver may still
    recover it from the totals.
    """
    out: dict[str, dict[float, float]] = {}
    for b in result.bindings:
        legal = _legal_values(b.anchor.max_marks, b.anchor.step)
        if b.mark is None or b.mark.value is None:
            out[b.anchor.address] = {v: 1.0 / len(legal) for v in legal}
            continue
        conf = min(max(b.mark.confidence, floor), 1.0 - floor)
        spread = (1.0 - conf) / max(len(legal) - 1, 1)
        dist = {v: spread for v in legal}
        if b.mark.value in dist:
            dist[b.mark.value] = conf
        else:  # an illegal read — keep it flat, let the solver decide
            dist = {v: 1.0 / len(legal) for v in legal}
        out[b.anchor.address] = dist
    return out


def confusable_prior(value: float, legal: list[float], confidence: float) -> dict[float, float]:
    """Handwritten digit confusion prior. 1 and 3 are the classic pair on an Indian script."""
    confusions = {1.0: [3.0, 7.0], 3.0: [1.0, 8.0], 5.0: [6.0], 6.0: [5.0, 0.0], 0.0: [6.0]}
    dist = {v: 0.0 for v in legal}
    if value in dist:
        dist[value] = confidence
    rest = 1.0 - confidence
    near = [v for v in confusions.get(value, []) if v in dist]
    for v in near:
        dist[v] = rest * 0.6 / len(near)
    others = [v for v in legal if v != value and v not in near]
    for v in others:
        dist[v] = rest * 0.4 / max(len(others), 1)
    total = sum(dist.values()) or 1.0
    return {k: v / total for k, v in dist.items() if v > 0 or math.isclose(k, value)}
