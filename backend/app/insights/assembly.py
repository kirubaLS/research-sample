"""Part G: report assembly — ordering (G2), shape statement (G3), priority
watch list (G4), overflow (G5), marks summary block (G6)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .insight import InsightObject, InsightType, AnalyticalScope, Band, SENTINEL_NC
from .gate import BlockedClaim
from . import constants as C
from . import strings as S

_BAND_ORDER = {Band.HIGH: 3, Band.MEDIUM: 2, Band.LOW: 1, Band.NONE: 0}


def _mult_value(obj: InsightObject) -> float:
    m = obj.priority.multiplier
    return m if isinstance(m, (int, float)) else -1.0  # NOT_CALIBRATED sorts last


def _marks_value(obj: InsightObject) -> int:
    v = obj.marks_at_stake.lost
    return v if isinstance(v, int) else 0


def order_findings(objects: list[InsightObject]) -> list[InsightObject]:
    """Part 2 ordering: observation band, then attribution band, then priority
    desc, then marks_at_stake desc, then coverage desc.
    Priority never moves an insight across a confidence band — the sort is
    lexicographic and band dominates, which this key structurally guarantees."""
    findings = [o for o in objects
                if o.analytical_scope != AnalyticalScope.PAPER]
    findings.sort(key=lambda o: (
        -_BAND_ORDER[o.confidence.observation],
        -_BAND_ORDER[o.confidence.attribution],
        -_mult_value(o),
        -_marks_value(o),
        -o.coverage.distinct_variants,
    ))
    return findings


def split_by_band(findings: list[InsightObject]) -> dict[Band, list[InsightObject]]:
    out: dict[Band, list[InsightObject]] = {Band.HIGH: [], Band.MEDIUM: [], Band.LOW: []}
    for o in findings:
        out.setdefault(o.confidence.observation, []).append(o)
    return out


def overflow_lines(findings_by_band: dict[Band, list[InsightObject]]) -> list[str]:
    lines = []
    for band, items in findings_by_band.items():
        if len(items) > C.MAX_INSIGHTS_PER_BAND:
            overflow_n = len(items) - C.MAX_INSIGHTS_PER_BAND
            lines.append(S.render("OVERFLOW", n=overflow_n, band=band.value.title()))
    return lines


def priority_watch_list(objects: list[InsightObject]) -> str | None:
    """G4: concept families with multiplier >= 1.5 where an insight fired
    below HIGH observation."""
    families = []
    for o in objects:
        mult = o.priority.multiplier
        if isinstance(mult, (int, float)) and mult >= C.PRIORITY_WATCH_MULTIPLIER_THRESHOLD:
            if _BAND_ORDER[o.confidence.observation] < _BAND_ORDER[Band.HIGH]:
                if o.domain and o.domain not in families:
                    families.append(o.domain)
    if not families:
        return None
    return S.render("PRIORITY_WATCH", families=", ".join(families))


def shape_statement(register: str, recall_n: int, nonrecall_n: int, chapters_n: int,
                     student: str = "the student") -> str:
    key = {"TEACHER": "SHAPE_TEACHER", "PARENT": "SHAPE_PARENT",
           "STUDENT": "SHAPE_STUDENT"}[register]
    kwargs = dict(r=recall_n, n=nonrecall_n, c=chapters_n)
    if register != "TEACHER":
        kwargs["student"] = student
    return S.render(key, **kwargs)


def marks_summary(register: str, objects: list[InsightObject]) -> str:
    """G6: sums aggregable=true objects only."""
    total_lost = 0
    total_available = 0
    for o in objects:
        if o.marks_at_stake.aggregable and isinstance(o.marks_at_stake.lost, int):
            total_lost += o.marks_at_stake.lost
            total_available += o.marks_at_stake.available
    key = "MARKS_SUMMARY_TEACHER" if register == "TEACHER" else "MARKS_SUMMARY_PARENT"
    return S.render(key, total_lost=total_lost, total_available=total_available)


def render_blocked_claim(bc: BlockedClaim) -> str:
    return bc.report_language or (
        f"blocked_claim: {bc.claim_type.value} at {bc.blocked_at} — {bc.reason}"
    )


@dataclass
class AssembledReport:
    part1_shape: str
    part1_marks_summary: str | None
    part2_findings: list[InsightObject]
    part2_overflow_notes: list[str]
    part3_blocked_claims: list[BlockedClaim]
    part3_priority_watch: str | None
    part2_exempt: list[InsightObject] = field(default_factory=list)  # E6/E8, printed alongside


def assemble(
    register: str,
    all_objects: list[InsightObject],
    blocked_claims: list[BlockedClaim],
    recall_n: int, nonrecall_n: int, chapters_n: int,
    student_name: str = "the student",
) -> AssembledReport:
    findings = order_findings(all_objects)
    by_band = split_by_band(findings)
    overflow = overflow_lines(by_band)

    shape = shape_statement(register, recall_n, nonrecall_n, chapters_n, student_name)
    ms = marks_summary(register, all_objects) if register in ("TEACHER", "PARENT") else None

    watch = priority_watch_list(all_objects)

    exempt = [o for o in all_objects if o.insight_type in
              (InsightType.SELF_COMPARISON, InsightType.GAP_TO_REFERENCE)
              and o not in findings]

    return AssembledReport(
        part1_shape=shape,
        part1_marks_summary=ms,
        part2_findings=findings,
        part2_overflow_notes=overflow,
        part3_blocked_claims=blocked_claims,
        part3_priority_watch=watch,
        part2_exempt=exempt,
    )
