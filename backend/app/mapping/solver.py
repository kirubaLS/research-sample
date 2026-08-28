"""The constraint solver — the arithmetic oracle.

Given, for each question, a probability distribution over its *legal* mark values, and
the totals the teacher wrote (grand, per section, per page), choose the assignment that

    maximise    sum_q  log p_q(m_q)
    subject to  sum of marks in each constrained group == that group's written total
                0 <= m_q <= max_marks(q), on the legal step lattice

This is why a handwritten 1 misread as a 3 gets repaired: per-crop the recogniser may
prefer 3, but the arithmetic is ground truth. It is also why system accuracy is far higher
than component accuracy.

Constraints form a *laminar family* in practice (a page total sits inside a section total
sits inside the paper total), so the exact solution is a max-plus convolution over the
constraint tree — polynomial, exact, and a few milliseconds for a real paper.

If nothing clears the likelihood floor the script is FLAGGED, never guessed: a missing
page, an unmarked question or the teacher's own addition error all surface here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

NEG_INF = float("-inf")


@dataclass(frozen=True)
class QuestionDist:
    """Distribution over the legal mark values of one question."""

    question_id: str
    max_marks: float
    step: float
    probs: dict[float, float]  # value -> probability (need not be normalised)

    def legal_values(self) -> list[float]:
        n = int(round(self.max_marks / self.step))
        return [round(i * self.step, 2) for i in range(n + 1)]


@dataclass(frozen=True)
class Constraint:
    """``indices`` must sum to ``total``. ``name`` appears in the failure message."""

    name: str
    indices: frozenset[int]
    total: float


@dataclass
class SolveResult:
    feasible: bool
    assignment: dict[str, float] = field(default_factory=dict)
    loglik: float = NEG_INF
    mean_logp: float = NEG_INF
    failed_constraint: str | None = None
    detail: str = ""


def _units(value: float, step: float) -> int:
    return int(round(value / step))


def _is_laminar(constraints: list[Constraint]) -> bool:
    for i, a in enumerate(constraints):
        for b in constraints[i + 1 :]:
            if a.indices & b.indices and not (a.indices <= b.indices or b.indices <= a.indices):
                return False
    return True


class _Node:
    __slots__ = ("constraint", "children", "leaves")

    def __init__(self, constraint: Constraint | None):
        self.constraint = constraint
        self.children: list[_Node] = []
        self.leaves: list[int] = []


def _build_tree(constraints: list[Constraint], all_indices: set[int]) -> _Node:
    """Nest constraints by containment; unconstrained questions hang off the root."""
    ordered = sorted(constraints, key=lambda c: (-len(c.indices), c.name))
    root = _Node(None)
    nodes = [(_Node(c), c) for c in ordered]

    for node, c in nodes:
        parent = root
        for other_node, other_c in nodes:
            if other_c is c:
                continue
            if c.indices < other_c.indices:
                if parent.constraint is None or other_c.indices < parent.constraint.indices:
                    parent = other_node
        parent.children.append(node)

    def assign_leaves(node: _Node, owned: set[int]) -> None:
        child_cover: set[int] = set()
        for ch in node.children:
            assert ch.constraint is not None
            child_cover |= ch.constraint.indices
        node.leaves = sorted(owned - child_cover)
        for ch in node.children:
            assert ch.constraint is not None
            assign_leaves(ch, set(ch.constraint.indices))

    assign_leaves(root, set(all_indices))
    return root


def _leaf_profile(dist: QuestionDist, step: float) -> dict[int, tuple[float, float]]:
    """units -> (best log-prob, chosen value)."""
    out: dict[int, tuple[float, float]] = {}
    for v in dist.legal_values():
        p = dist.probs.get(v, 0.0)
        lp = math.log(p) if p > 0 else NEG_INF
        if lp == NEG_INF:
            continue
        out[_units(v, step)] = (lp, v)
    return out


def _convolve(
    a: dict[int, tuple[float, list]],
    b: dict[int, tuple[float, list]],
    cap: int,
) -> dict[int, tuple[float, list]]:
    """Max-plus convolution with backpointers."""
    out: dict[int, tuple[float, list]] = {}
    for ua, (la, sa) in a.items():
        for ub, (lb, sb) in b.items():
            u = ua + ub
            if u > cap:
                continue
            lv = la + lb
            prev = out.get(u)
            if prev is None or lv > prev[0]:
                out[u] = (lv, [sa, sb])
    return out


def solve(
    dists: list[QuestionDist],
    constraints: list[Constraint],
    *,
    likelihood_floor: float = -2.5,
) -> SolveResult:
    """Exact constrained MAP assignment.

    ``likelihood_floor`` is the minimum *mean* log-probability per question. Below it the
    reconciliation is not believable and the script is flagged instead of accepted.
    """
    if not dists:
        return SolveResult(feasible=True, assignment={}, loglik=0.0, mean_logp=0.0)

    step = min(d.step for d in dists)
    for d in dists:
        if abs(round(d.step / step) - d.step / step) > 1e-9:
            return SolveResult(False, detail="incompatible mark steps")

    if not _is_laminar(constraints):
        return SolveResult(False, detail="overlapping non-nested constraints")

    all_idx = set(range(len(dists)))
    for c in constraints:
        if not c.indices <= all_idx:
            return SolveResult(False, failed_constraint=c.name, detail="unknown question index")

    root = _build_tree(constraints, all_idx)
    cap = sum(_units(d.max_marks, step) for d in dists)

    def solve_node(node: _Node) -> dict[int, tuple[float, list]]:
        profile: dict[int, tuple[float, list]] = {0: (0.0, [])}
        for idx in node.leaves:
            leaf = {u: (lp, ("leaf", idx, v)) for u, (lp, v) in _leaf_profile(dists[idx], step).items()}
            if not leaf:
                return {}
            profile = _convolve(profile, leaf, cap)
        for ch in node.children:
            sub = solve_node(ch)
            if not sub:
                return {}
            profile = _convolve(profile, sub, cap)

        if node.constraint is not None:
            want = _units(node.constraint.total, step)
            hit = profile.get(want)
            if hit is None:
                raise _Infeasible(node.constraint.name, node.constraint.total)
            profile = {want: hit}
        return profile

    try:
        profile = solve_node(root)
    except _Infeasible as exc:
        return SolveResult(
            False,
            failed_constraint=exc.name,
            detail=f"no assignment sums to {exc.total} for constraint '{exc.name}'",
        )

    if not profile:
        return SolveResult(False, detail="no legal assignment")

    best_units = max(profile, key=lambda u: profile[u][0])
    loglik, tree = profile[best_units]

    assignment: dict[str, float] = {}

    def walk(node) -> None:
        if isinstance(node, tuple) and node and node[0] == "leaf":
            _, idx, value = node
            assignment[dists[idx].question_id] = value
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(tree)
    mean = loglik / len(dists) if dists else 0.0
    if mean < likelihood_floor:
        return SolveResult(
            False,
            assignment=assignment,
            loglik=loglik,
            mean_logp=mean,
            detail=f"mean log-probability {mean:.2f} below floor {likelihood_floor}",
        )
    return SolveResult(True, assignment, loglik, mean)


class _Infeasible(Exception):
    def __init__(self, name: str, total: float):
        super().__init__(name)
        self.name = name
        self.total = total
