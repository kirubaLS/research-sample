"""E9: primary/secondary resolution for overlapping insights on the same subject."""
from __future__ import annotations

from .insight import (
    InsightObject, InsightType, AnalyticalScope, Band, Contributing, MarksAtStake,
)

_BAND_ORDER = {Band.HIGH: 3, Band.MEDIUM: 2, Band.LOW: 1, Band.NONE: 0}
_SCOPE_ORDER = {AnalyticalScope.PAPER: 3, AnalyticalScope.CHAPTER: 2,
                AnalyticalScope.SKILL: 2, AnalyticalScope.VARIANT: 1}

# E6 and E8 are exempt from resolution entirely (K5.1): they answer "where a
# student stands", not "what pattern their answers show", and are printed
# alongside domain findings rather than in competition with them.
_EXEMPT_TYPES = {InsightType.SELF_COMPARISON, InsightType.GAP_TO_REFERENCE}


def _mult_value(obj: InsightObject) -> float:
    m = obj.priority.multiplier
    return m if isinstance(m, (int, float)) else 0.0


def _rank_key(obj: InsightObject):
    return (
        _BAND_ORDER[obj.confidence.observation],
        _BAND_ORDER[obj.confidence.attribution],
        obj.coverage.distinct_variants,
        _mult_value(obj),
        _SCOPE_ORDER.get(obj.analytical_scope, 0),
    )


def _shares_evidence(a: InsightObject, b: InsightObject) -> bool:
    return bool(set(a.evidence.supporting) & set(b.evidence.supporting))


def _subordinate_sentence(obj: InsightObject) -> str:
    # Reuses the same structural facts, but does NOT reuse the F5 headline
    # string as a sub-clause (K5.4) — it is its own contributing summary line.
    gt = obj.evidence.group_totals
    if obj.insight_type == InsightType.VARIANT_WEAKNESS and gt:
        pass
    n = len(obj.evidence.supporting)
    scope = obj.domain or "this scope"
    lost = obj.marks_at_stake.lost if isinstance(obj.marks_at_stake.lost, int) else 0
    avail = obj.marks_at_stake.available if isinstance(obj.marks_at_stake.available, int) else 0
    variant_txt = f" involving '{obj.variant}'" if obj.variant else ""
    return (
        f"Within {scope}, {obj.insight_type.value.replace('_', ' ').title()} also "
        f"appears{variant_txt} ({n} questions, {lost} of {avail} marks not scored)."
    )


def resolve(objects: list[InsightObject]) -> list[InsightObject]:
    """Groups objects by subject_id, resolves overlapping evidence within a
    subject into one headline + subordinates written into
    evidence.contributing, and returns the flat list of HEADLINE objects
    (subordinates are dropped from the top-level list but recorded)."""
    by_subject: dict[str, list[InsightObject]] = {}
    for obj in objects:
        by_subject.setdefault(obj.subject_id, []).append(obj)

    headlines: list[InsightObject] = []

    for subject_id, subj_objs in by_subject.items():
        exempt = [o for o in subj_objs if o.insight_type in _EXEMPT_TYPES]
        rankable = [o for o in subj_objs if o.insight_type not in _EXEMPT_TYPES]

        # DIFFUSE_SIGNAL never takes primary (E7.7).
        rankable.sort(key=lambda o: (
            o.insight_type == InsightType.DIFFUSE_SIGNAL,  # False sorts first
            [-x for x in _rank_key(o)],
        ))

        used = [False] * len(rankable)
        for i, obj in enumerate(rankable):
            if used[i]:
                continue
            used[i] = True
            for j in range(i + 1, len(rankable)):
                if used[j]:
                    continue
                other = rankable[j]
                if _shares_evidence(obj, other):
                    used[j] = True
                    obj.evidence.contributing.append(
                        Contributing(other.insight_type, _subordinate_sentence(other),
                                     list(other.evidence.supporting))
                    )
                    other.marks_at_stake = MarksAtStake(
                        other.marks_at_stake.lost, other.marks_at_stake.available,
                        other.marks_at_stake.basis, aggregable=False,
                    )
            headlines.append(obj)

        headlines.extend(exempt)

    return headlines
