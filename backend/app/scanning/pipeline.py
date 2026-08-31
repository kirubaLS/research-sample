"""L2 to L7 in order, on one script.

L0 and L1 sit outside: capture happens in the browser and restoration on the page image,
and both are per-page concerns. From ink separation onward the script is the unit, because
association fits the teacher's convention across pages and reconciliation needs the
totals from all of them at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.mapping.association import (
    Anchor,
    AssociationResult,
    MarkCandidate,
    associate,
    bindings_to_distributions,
)
from app.mapping.solver import Constraint, QuestionDist, SolveResult, solve
from app.scanning.adjudicate import Adjudication, adjudicate
from app.scanning.recognise import MarkRecognizer, clamp
from app.vision.ink import InkLayers, separate
from app.vision.localise import find_mark_candidates, find_total_candidates


@dataclass
class ScriptResult:
    """Everything the seven layers produced, and where it came from."""

    anchors: list[Anchor] = field(default_factory=list)
    candidates: list[MarkCandidate] = field(default_factory=list)
    association: AssociationResult | None = None
    solution: SolveResult | None = None
    adjudication: Adjudication | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.adjudication and not self.adjudication.flagged)


def _legal(anchor: Anchor) -> list[float]:
    n = int(round(anchor.max_marks / anchor.step))
    return [round(i * anchor.step, 2) for i in range(n + 1)]


def read_script(
    pages_rgb: list[np.ndarray],
    anchors: list[Anchor],
    recognizer: MarkRecognizer,
    *,
    constraints: list[Constraint] | None = None,
    crops: dict[str, object] | None = None,
    threshold: float = 0.97,
    ink_profile=None,
) -> ScriptResult:
    """Run L2 -> L7.

    ``anchors`` come from L3 against the frozen Q-matrix and are passed in rather than
    found here, because reading a question label is recognition and belongs to L4 -- and an
    anchor asserted before anything read it is a question number nobody has seen.
    """
    out = ScriptResult(anchors=list(anchors))

    # --- L2: ink separation, then L3: localisation, page by page ---
    for page_number, rgb in enumerate(pages_rgb, start=1):
        layers: InkLayers = separate(rgb, ink_profile)
        out.candidates.extend(find_mark_candidates(layers.teacher, page_number))
        totals = find_total_candidates(layers.teacher, page_number)
        if totals:
            out.notes.append(f"page {page_number}: {len(totals)} total candidate(s)")
        if layers.removed_rules:
            out.notes.append(
                f"page {page_number}: {layers.removed_rules} ruled line(s) removed before blob detection"
            )

    if not out.candidates:
        out.notes.append("no mark candidates were found in the teacher's ink")

    # --- L4: recognition, as a distribution over the legal values of the bound question ---
    # Recognition needs to know which question a crop belongs to, and association needs the
    # recognised values to bind well. The order here is: a cheap first association on
    # position alone, recognise against the values that binding makes legal, then let L5
    # re-solve with the values in hand.
    rough = associate(out.candidates, out.anchors, refit=False)
    legal_for: dict[str, list[float]] = {}
    for binding in rough.bindings:
        if binding.mark is None:
            continue
        legal_for[binding.mark.candidate_id] = _legal(binding.anchor)

    read: list[MarkCandidate] = []
    for candidate in out.candidates:
        legal = legal_for.get(candidate.candidate_id)
        if not legal:
            # Unbound at this stage: no question, so no legal set, so nothing to read
            # against. Carried forward unread rather than dropped -- L5 may still bind it.
            read.append(candidate)
            continue
        crop = (crops or {}).get(candidate.candidate_id)
        distribution = clamp(recognizer.predict(crop, legal), legal)
        best = max(distribution, key=lambda v: distribution[v])
        total = sum(distribution.values()) or 1.0
        read.append(
            MarkCandidate(
                candidate_id=candidate.candidate_id, page=candidate.page,
                x=candidate.x, y=candidate.y,
                value=best, confidence=distribution[best] / total,
            )
        )
    out.candidates = read

    # --- L5: association, now with values, which the cost matrix uses for plausibility ---
    out.association = associate(out.candidates, out.anchors)
    distributions = bindings_to_distributions(out.association)

    # --- L6: reconciliation against the totals ---
    dists = [
        QuestionDist(
            question_id=anchor.address, max_marks=anchor.max_marks, step=anchor.step,
            probs=distributions.get(anchor.address) or {v: 1.0 for v in _legal(anchor)},
        )
        for anchor in out.anchors
    ]
    out.solution = solve(dists, constraints or [])

    # --- L7: adjudication ---
    confidence = {
        binding.anchor.address: (binding.mark.confidence if binding.mark else 0.0)
        for binding in out.association.bindings
    }
    out.adjudication = adjudicate(
        out.solution.assignment,
        confidence,
        threshold=threshold,
        feasible=out.solution.feasible,
        infeasible_reason=out.solution.detail or out.solution.failed_constraint,
        crops={c: c for c in confidence},
    )
    return out
