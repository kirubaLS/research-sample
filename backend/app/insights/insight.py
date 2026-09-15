"""Part D: the Insight Object, plus the G1 validation gate."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union

SENTINEL_NA = "NOT_APPLICABLE"
SENTINEL_NC = "NOT_CALIBRATED"
SENTINEL_NOT_ISSUED = "NOT_ISSUED"


class InsightType(str, Enum):
    TIER_GAP = "TIER_GAP"
    REVERSE_TIER_GAP = "REVERSE_TIER_GAP"
    COMPLEXITY_GAP = "COMPLEXITY_GAP"
    INTEGRATION_GAP = "INTEGRATION_GAP"
    VARIANT_WEAKNESS = "VARIANT_WEAKNESS"
    SELF_COMPARISON = "SELF_COMPARISON"
    DIFFUSE_SIGNAL = "DIFFUSE_SIGNAL"
    GAP_TO_REFERENCE = "GAP_TO_REFERENCE"


class SubjectScope(str, Enum):
    STUDENT = "STUDENT"
    CLASS = "CLASS"
    SCHOOL = "SCHOOL"


class AnalyticalScope(str, Enum):
    PAPER = "PAPER"
    CHAPTER = "CHAPTER"
    VARIANT = "VARIANT"
    SKILL = "SKILL"


class Band(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class CheckResult(str, Enum):
    RULED_OUT = "RULED_OUT"
    NOT_RULED_OUT = "NOT_RULED_OUT"
    UNTESTABLE = "UNTESTABLE"


class Action(str, Enum):
    NONE = "NONE"
    TEACHER_REVIEW = "TEACHER_REVIEW"
    PAPER_REVIEW = "PAPER_REVIEW"
    REMEDIATION = "REMEDIATION_REF"


class CoverageStatus(str, Enum):
    PASS = "PASS"
    NARROWED = "NARROWED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class GroupTotal:
    label: str
    question_count: int
    marks: int
    pct: Optional[float] = None
    note: str = ""


@dataclass
class Contributing:
    """Summary line for a subordinate insight (E9), living in evidence.contributing."""
    insight_type: InsightType
    sentence: str
    supporting: list[str] = field(default_factory=list)


@dataclass
class Evidence:
    supporting: list[str] = field(default_factory=list)
    group_totals: list[GroupTotal] = field(default_factory=list)
    excluded: list[tuple[str, str]] = field(default_factory=list)
    contributing: list[Contributing] = field(default_factory=list)


@dataclass
class Coverage:
    distinct_variants: int
    variants: list[str]
    minimum_required: int
    status: CoverageStatus
    note: str = ""


@dataclass
class Confidence:
    observation: Band
    attribution: Band
    reason: str  # required, always populated


@dataclass
class Priority:
    # float | NOT_APPLICABLE | NOT_CALIBRATED
    multiplier: Union[float, str]
    reason: str


@dataclass
class MarksAtStake:
    # int | NOT_APPLICABLE for lost/available when the rule has no marks basis (E2)
    lost: Union[int, str]
    available: Union[int, str]
    basis: str
    aggregable: bool


@dataclass
class CheckOutcome:
    result: CheckResult
    reason: str


@dataclass
class AlternativeExplanations:
    declared: list[str]
    results: dict[str, CheckOutcome] = field(default_factory=dict)


@dataclass
class RemediationRef:
    domain_or_skill: str
    tier: str


@dataclass
class ReportLanguage:
    teacher: str
    parent: Union[str, str]     # string or NOT_ISSUED
    student: Union[str, str]    # string or NOT_ISSUED


@dataclass
class InsightObject:
    insight_type: InsightType
    subject_scope: SubjectScope
    analytical_scope: AnalyticalScope
    domain: Optional[str]        # chapter/skill name, or None at PAPER scope
    subject_id: str              # student_id, class_id, or school/grade id

    evidence: Evidence
    coverage: Coverage
    confidence: Confidence
    priority: Priority
    marks_at_stake: MarksAtStake
    alternative_explanations: AlternativeExplanations
    action: Union[Action, RemediationRef, str]
    report_language: ReportLanguage

    # bookkeeping used by E9/E10/E12/G2, not part of D1's core fields
    variant: Optional[str] = None
    aggregable_override_reason: str = ""


class ValidationError(Exception):
    pass


def _action_is_paper_incompatible(obj: InsightObject) -> bool:
    """G1 rule 6: PAPER scope => action NONE, except E8 (chapter localisations
    carry their own references)."""
    if obj.analytical_scope != AnalyticalScope.PAPER:
        return False
    if obj.insight_type == InsightType.GAP_TO_REFERENCE:
        return False
    return not (obj.action == Action.NONE or obj.action == "NONE")


def validate(obj: InsightObject, remediation_lookup_ok: Optional[bool] = None) -> None:
    """G1 validation gate. Raises ValidationError with the failing rule number
    if the object is incomplete or inconsistent. `remediation_lookup_ok`
    lets callers assert G1.7 (a remediation_ref must resolve to a real row);
    when the action is a RemediationRef this must be passed and True."""

    # 1. Every field populated (sentinels are legal values, not empty fields).
    required = [
        obj.insight_type, obj.subject_scope, obj.analytical_scope,
        obj.evidence, obj.coverage, obj.confidence, obj.priority,
        obj.marks_at_stake, obj.alternative_explanations, obj.action,
        obj.report_language,
    ]
    if any(v is None for v in required):
        raise ValidationError("G1.1: a required field is missing")
    if obj.confidence.reason.strip() == "":
        raise ValidationError("G1.1: confidence.reason must be populated")
    if obj.priority.reason.strip() == "":
        raise ValidationError("G1.1: priority.reason must be populated")

    # 3. Every declared check has a result and reason; UNTESTABLE implies a cap
    #    recorded in confidence.reason.
    declared = obj.alternative_explanations.declared
    results = obj.alternative_explanations.results
    if set(declared) != set(results.keys()):
        raise ValidationError(
            "G1.3: declared checks and results must match exactly"
        )
    for name in declared:
        outcome = results[name]
        if not outcome.reason.strip():
            raise ValidationError(f"G1.3: check '{name}' has no reason")
        if outcome.result == CheckResult.UNTESTABLE:
            if "untestable" not in obj.confidence.reason.lower() and \
               "could not be run" not in obj.confidence.reason.lower():
                raise ValidationError(
                    f"G1.3: check '{name}' is UNTESTABLE but confidence.reason "
                    "does not record the corresponding cap"
                )

    # 6. PAPER scope => action NONE except E8.
    if _action_is_paper_incompatible(obj):
        raise ValidationError("G1.6: PAPER scope insight must carry action NONE")

    # 7. remediation_ref must resolve.
    if isinstance(obj.action, RemediationRef):
        if remediation_lookup_ok is False:
            raise ValidationError(
                "G1.7: remediation_ref did not resolve to an actual row"
            )

    # register NOT_ISSUED values are accepted as-is (F4 / G1.1).
    for reg_value in (obj.report_language.teacher, obj.report_language.parent,
                      obj.report_language.student):
        if reg_value is None:
            raise ValidationError("G1.1: a report_language register is unset")


def enforce_no_shared_aggregable_question(objects: list[InsightObject]) -> None:
    """G1.8: if marks_at_stake.aggregable is true, no other emitted object
    shares a supporting question with this one."""
    seen: dict[str, InsightObject] = {}
    for obj in objects:
        if not obj.marks_at_stake.aggregable:
            continue
        for qid in obj.evidence.supporting:
            if qid in seen and seen[qid] is not obj:
                raise ValidationError(
                    f"G1.8: question {qid} is shared by two aggregable=true objects"
                )
            seen[qid] = obj
