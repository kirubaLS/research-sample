"""G1: an incomplete Insight Object is rejected."""
import pytest
from app.insights.insight import (
    InsightObject, InsightType, SubjectScope, AnalyticalScope, Evidence,
    Coverage, CoverageStatus, Confidence, Band, Priority, MarksAtStake,
    AlternativeExplanations, CheckOutcome, CheckResult, Action, ReportLanguage,
    validate, ValidationError,
)


def _complete_object() -> InsightObject:
    return InsightObject(
        insight_type=InsightType.COMPLEXITY_GAP,
        subject_scope=SubjectScope.STUDENT,
        analytical_scope=AnalyticalScope.CHAPTER,
        domain="Statistics", subject_id="S1",
        evidence=Evidence(supporting=["Q1", "Q2"]),
        coverage=Coverage(3, ["v1", "v2", "v3"], 3, CoverageStatus.PASS),
        confidence=Confidence(Band.HIGH, Band.HIGH, "High. Both groups clear the minimum."),
        priority=Priority("NOT_CALIBRATED", "No board data yet."),
        marks_at_stake=MarksAtStake(2, 5, "Multi-step questions.", True),
        alternative_explanations=AlternativeExplanations(
            declared=["anomalous_question", "confound", "marker_variation"],
            results={
                "anomalous_question": CheckOutcome(CheckResult.RULED_OUT, "removal test ok"),
                "confound": CheckOutcome(CheckResult.RULED_OUT, "not dominated by one variant"),
                "marker_variation": CheckOutcome(CheckResult.RULED_OUT, "mostly marker-independent"),
            },
        ),
        action=Action.NONE,
        report_language=ReportLanguage("teacher text", "parent text", "student text"),
    )


def test_complete_object_validates():
    obj = _complete_object()
    validate(obj)  # should not raise


def test_missing_confidence_reason_is_rejected():
    obj = _complete_object()
    obj.confidence.reason = ""
    with pytest.raises(ValidationError):
        validate(obj)


def test_declared_check_without_result_is_rejected():
    obj = _complete_object()
    obj.alternative_explanations.declared.append("extra_check")
    with pytest.raises(ValidationError):
        validate(obj)


def test_untestable_check_requires_confidence_cap_recorded():
    obj = _complete_object()
    obj.alternative_explanations.results["marker_variation"] = CheckOutcome(
        CheckResult.UNTESTABLE, "cannot be run on this data"
    )
    # confidence.reason does not mention it being untestable / could not be run
    with pytest.raises(ValidationError):
        validate(obj)


def test_paper_scope_with_action_other_than_none_is_rejected():
    obj = _complete_object()
    obj.analytical_scope = AnalyticalScope.PAPER
    obj.action = Action.TEACHER_REVIEW
    with pytest.raises(ValidationError):
        validate(obj)


def test_remediation_ref_that_does_not_resolve_is_rejected():
    from app.insights.insight import RemediationRef
    obj = _complete_object()
    obj.action = RemediationRef("Statistics", "APPLICATION")
    with pytest.raises(ValidationError):
        validate(obj, remediation_lookup_ok=False)
