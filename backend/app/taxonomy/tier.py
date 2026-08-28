"""Deciding R&U / AP / AEC.

Tier is a judgement about cognitive demand, not a fact printed on the page, so it is never
one model asked once. Four independent signals, fused and calibrated, with an abstain
option:

  1  structural prior   question type, marks, section position — free and deterministic
  2  action class       from the verb lexicon (never a tier, only an action)
  3  familiarity        against the book's two buckets — the signal that fixes the trap
  4  model judgement    constrained to the three tiers, self-consistency k=5

Signals 2 and 3 compose through a table, because Bloom level = action x familiarity:

                        T_VERBATIM   PRACTISED   ADAPTED   NOVEL
  RECALL / EXPLAIN         R&U          R&U        R&U      R&U
  EXECUTE / PROVE          R&U   <--    AP         AP       AEC
  APPLY_IN_CONTEXT         AP           AP         AP       AEC
  ANALYSE/EVAL/CREATE      AP           AEC        AEC      AEC

T_VERBATIM means the chapter *body* showed the answer (a named theorem or worked example):
reproduction. PRACTISED means the same task appeared as an *exercise*: the student carried
the procedure out themselves, which is Applying. That distinction is what separates
"Prove that root 5 is irrational" (Theorem 1.3, so R&U) from "Prove that 3 + 2 root 5 is
irrational" (Exercise 1.2, so AP).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.assessment import TIER_ALIASES
from app.taxonomy.familiarity import FamiliarityResult
from app.taxonomy.lexicon import primary_action

#: the derivation engine works in short codes; storage uses the board's own words, so
#: reconcile_with_blueprint maps across via TIER_ALIASES on the way out
TIERS = ("R&U", "AP", "AEC")

FAMILIARITY_LEVELS = ("T_VERBATIM", "PRACTISED", "ADAPTED", "NOVEL")

#: action x familiarity -> tier
ACTION_FAMILIARITY_TABLE: dict[str, dict[str, str]] = {
    "RECALL":                 {"T_VERBATIM": "R&U", "PRACTISED": "R&U", "ADAPTED": "R&U", "NOVEL": "R&U"},
    "EXPLAIN":                {"T_VERBATIM": "R&U", "PRACTISED": "R&U", "ADAPTED": "R&U", "NOVEL": "AEC"},
    "EXECUTE":                {"T_VERBATIM": "R&U", "PRACTISED": "AP",  "ADAPTED": "AP",  "NOVEL": "AEC"},
    "PROVE":                  {"T_VERBATIM": "R&U", "PRACTISED": "AP",  "ADAPTED": "AP",  "NOVEL": "AEC"},
    "APPLY_IN_CONTEXT":       {"T_VERBATIM": "AP",  "PRACTISED": "AP",  "ADAPTED": "AP",  "NOVEL": "AEC"},
    "ANALYSE_EVALUATE_CREATE":{"T_VERBATIM": "AP",  "PRACTISED": "AEC", "ADAPTED": "AEC", "NOVEL": "AEC"},
}

#: question type -> prior over tiers. Measured shape of CBSE papers, used as a prior only.
TYPE_PRIOR: dict[str, dict[str, float]] = {
    "MCQ":            {"R&U": 0.72, "AP": 0.22, "AEC": 0.06},
    "ASSERTION_REASON": {"R&U": 0.25, "AP": 0.30, "AEC": 0.45},
    "MATCH":          {"R&U": 0.80, "AP": 0.15, "AEC": 0.05},
    "VSA":            {"R&U": 0.55, "AP": 0.35, "AEC": 0.10},
    "SA":             {"R&U": 0.30, "AP": 0.50, "AEC": 0.20},
    "LA":             {"R&U": 0.15, "AP": 0.40, "AEC": 0.45},
    "CBQ":            {"R&U": 0.15, "AP": 0.45, "AEC": 0.40},
    "MAP":            {"R&U": 0.55, "AP": 0.35, "AEC": 0.10},
}
MARKS_PRIOR = {
    1: {"R&U": 0.70, "AP": 0.24, "AEC": 0.06},
    2: {"R&U": 0.50, "AP": 0.38, "AEC": 0.12},
    3: {"R&U": 0.30, "AP": 0.48, "AEC": 0.22},
    4: {"R&U": 0.18, "AP": 0.45, "AEC": 0.37},
    5: {"R&U": 0.15, "AP": 0.40, "AEC": 0.45},
}

COLD_START_WEIGHTS = {"model": 0.45, "action": 0.25, "familiarity": 0.20, "structural": 0.10}


def familiarity_level(fam: FamiliarityResult) -> str:
    """Collapse (bucket, band) into the table's column."""
    if fam.bucket is None:
        return "NOVEL"
    if fam.band == "verbatim":
        return "T_VERBATIM" if fam.bucket == "T" else "PRACTISED"
    if fam.band == "adapted":
        return "ADAPTED"
    return "NOVEL"


def structural_prior(question_type: str | None, max_marks: float) -> dict[str, float]:
    """Signal 1. Blend the type prior with the marks prior; neither alone decides."""
    by_type = TYPE_PRIOR.get((question_type or "").upper())
    by_marks = MARKS_PRIOR.get(int(round(max_marks)), {"R&U": 0.34, "AP": 0.33, "AEC": 0.33})
    if by_type is None:
        return dict(by_marks)
    return {t: 0.6 * by_type[t] + 0.4 * by_marks.get(t, 0.0) for t in TIERS}


def _onehot(tier: str | None, mass: float = 0.85) -> dict[str, float]:
    if tier is None:
        return {t: 1 / 3 for t in TIERS}
    rest = (1.0 - mass) / (len(TIERS) - 1)
    return {t: (mass if t == tier else rest) for t in TIERS}


def _normalise(d: dict[str, float]) -> dict[str, float]:
    total = sum(d.values()) or 1.0
    return {k: v / total for k, v in d.items()}


@dataclass
class TierSignals:
    structural: dict[str, float]
    action: dict[str, float]
    familiarity: dict[str, float]
    model: dict[str, float]
    action_class: str | None = None
    fam_level: str | None = None
    fam_detail: FamiliarityResult | None = None

    def as_dict(self) -> dict:
        return {
            "structural": self.structural,
            "action": self.action,
            "familiarity": self.familiarity,
            "model": self.model,
            "action_class": self.action_class,
            "familiarity_level": self.fam_level,
            "familiarity_score": self.fam_detail.score if self.fam_detail else None,
            "familiarity_bucket": self.fam_detail.bucket if self.fam_detail else None,
            "familiarity_ref": self.fam_detail.match_ref if self.fam_detail else None,
        }


@dataclass
class TierDecision:
    tier: str | None                 # None => abstained, goes to a human
    fused: dict[str, float]
    conformal_set: list[str]
    confidence: float
    signals: TierSignals
    mode: str = "cold_start"
    rationale: str = ""
    overridden: bool = False

    @property
    def abstained(self) -> bool:
        return self.tier is None


def classify_tier(
    stem: str,
    *,
    question_type: str | None,
    max_marks: float,
    familiarity: FamiliarityResult,
    model_votes: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
    conformal_threshold: float = 0.62,
    school_override: str | None = None,
) -> TierDecision:
    """Fuse the four signals and decide, or abstain.

    ``conformal_threshold`` is calibrated on a held-out adjudicated set so the returned SET
    contains the truth with probability >= 1 - alpha. Any tier whose fused mass is within
    reach of the leader stays in the set; a set of size > 1 means a human decides.
    """
    w = {**COLD_START_WEIGHTS, **(weights or {})}

    action = primary_action(stem)
    level = familiarity_level(familiarity)

    table_tier = ACTION_FAMILIARITY_TABLE.get(action or "", {}).get(level)
    sig = TierSignals(
        structural=_normalise(structural_prior(question_type, max_marks)),
        action=_onehot(table_tier, mass=0.80),
        familiarity=_onehot(table_tier, mass=0.75) if action else {t: 1 / 3 for t in TIERS},
        model=_normalise(model_votes or {t: 1 / 3 for t in TIERS}),
        action_class=action,
        fam_level=level,
        fam_detail=familiarity,
    )

    fused = {
        t: w["structural"] * sig.structural[t]
        + w["action"] * sig.action[t]
        + w["familiarity"] * sig.familiarity[t]
        + w["model"] * sig.model[t]
        for t in TIERS
    }
    fused = _normalise(fused)

    ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    leader, lead_mass = ranked[0]
    conformal = [t for t, m in ranked if m >= lead_mass * conformal_threshold]

    if school_override:
        return TierDecision(
            school_override, fused, [school_override], 1.0, sig,
            mode="school_override", overridden=True,
            rationale="tier fixed by this school's taxonomy override",
        )

    tier = leader if len(conformal) == 1 else None
    rationale = (
        f"action={action or 'none'} x familiarity={level}"
        f"{f' ({familiarity.match_ref}, F={familiarity.score:.2f})' if familiarity.match_ref else ''}"
        f" -> table says {table_tier or 'n/a'}; fused leader {leader} at {lead_mass:.2f}"
    )
    return TierDecision(tier, fused, conformal, lead_mass, sig, rationale=rationale)


# --------------------------------------------------------------------------------------
# Paper-level tie-breaker
# --------------------------------------------------------------------------------------

CBSE_TIER_TARGET = {"R&U": 0.54, "AP": 0.24, "AEC": 0.22}


@dataclass
class BlueprintAdjustment:
    applied: bool
    moved: list[tuple[str, str]] = field(default_factory=list)  # (question_id, tier)
    reason: str = ""


def apply_blueprint_tiebreak(
    decisions: dict[str, TierDecision],
    marks: dict[str, float],
    *,
    declares_blueprint: bool,
    target: dict[str, float] | None = None,
) -> BlueprintAdjustment:
    """Nudge ONLY the abstained items toward a declared blueprint.

    Board papers declare 54 / 24 / 22, so for those it is legitimate to break ties toward
    the target. A *school unit test* must never be adjusted: a paper deviating from the
    target is not an error to correct, it is the most valuable line in the paper-quality
    report. Applying the prior there would erase the finding.
    """
    if not declares_blueprint:
        return BlueprintAdjustment(
            False,
            reason="paper declares no blueprint; deviation is a finding, not an error",
        )

    tgt = target or CBSE_TIER_TARGET
    total = sum(marks.values()) or 1.0
    confident_mass = {t: 0.0 for t in TIERS}
    for qid, d in decisions.items():
        if d.tier is not None:
            confident_mass[d.tier] += marks.get(qid, 0.0)

    moved: list[tuple[str, str]] = []
    abstained = [qid for qid, d in decisions.items() if d.tier is None]
    # greedily assign each abstained item to whichever of its candidate tiers is furthest
    # below target — a one-pass Sinkhorn-style nudge, never touching confident items
    for qid in sorted(abstained, key=lambda q: -marks.get(q, 0.0)):
        d = decisions[qid]
        candidates = d.conformal_set or list(TIERS)
        deficits = {
            t: tgt.get(t, 0.0) - (confident_mass[t] / total)
            for t in candidates
        }
        pick = max(deficits, key=lambda t: deficits[t])
        confident_mass[pick] += marks.get(qid, 0.0)
        moved.append((qid, pick))

    return BlueprintAdjustment(True, moved, "abstained items nudged toward declared blueprint")


@dataclass(frozen=True)
class TierReconciliation:
    """What the paper says, what the derivation says, and where they part company."""

    question_id: str
    tier: str | None                # the value to store
    source: str                     # 'blueprint' | 'derived' | 'abstained'
    derived: str | None
    declared: str | None
    disagreement: bool


def reconcile_with_blueprint(
    decisions: dict[str, TierDecision],
    declared_tiers: dict[str, str],
) -> list[TierReconciliation]:
    """The blueprint wins where the paper states a tier per question.

    Competency Tier is assessment metadata, not a judgment: it is CBSE's own label,
    checked against the blueprint, and the paper is the primary source. So where a tier is
    declared it *is* the answer, and the derivation becomes a cross-check whose real value
    is the disagreement it surfaces -- either the derivation is wrong, or the paper has
    mislabelled a question, and both are worth knowing.

    Where nothing is declared, the derivation does its actual job and may still abstain.
    """
    out: list[TierReconciliation] = []
    for question_id, decision in decisions.items():
        declared = declared_tiers.get(question_id)
        declared = TIER_ALIASES.get(declared, declared) if declared else None
        derived = TIER_ALIASES.get(decision.tier, decision.tier) if decision.tier else None

        if declared is not None:
            out.append(
                TierReconciliation(
                    question_id, declared, "blueprint", derived, declared,
                    disagreement=derived is not None and derived != declared,
                )
            )
        else:
            out.append(
                TierReconciliation(
                    question_id, derived, "derived" if derived else "abstained",
                    derived, None, disagreement=False,
                )
            )
    return out


def disagreements(reconciliations: list[TierReconciliation]) -> list[TierReconciliation]:
    """Worth a flag on the paper: the derivation and the blueprint read a question differently."""
    return [r for r in reconciliations if r.disagreement]
