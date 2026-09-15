from app.insights.flags import compute_flags
from app.insights.rules import complexity_gap_student, variant_weakness_student
from app.insights.resolution import resolve
from app.insights.insight import InsightType
from .fixtures import statistics_paper


def test_k5_overlap_one_headline_one_subordinate():
    paper, questions, stu = statistics_paper()
    flags = compute_flags(questions)

    complexity = complexity_gap_student(paper, flags, stu, "Statistics")
    assert complexity is not None

    # Variant Weakness on "Two missing frequencies" (Q35 and two others),
    # sharing Q35 with the Complexity Gap's multi-step group.
    variant = variant_weakness_student(paper, flags, stu, "Statistics",
                                        "Two missing frequencies")
    # Our fixture only has 2 "Two missing frequencies" questions (below n=3
    # gate); build a synthetic sibling object sharing evidence with
    # `complexity` to exercise E9 directly regardless of E5's own gate.
    from app.insights.insight import (
        InsightObject, SubjectScope, AnalyticalScope, Evidence, Coverage,
        CoverageStatus, Confidence, Band, Priority, MarksAtStake,
        AlternativeExplanations, CheckOutcome, CheckResult, Action,
        ReportLanguage,
    )
    synthetic_variant_weakness = InsightObject(
        insight_type=InsightType.VARIANT_WEAKNESS,
        subject_scope=SubjectScope.STUDENT,
        analytical_scope=AnalyticalScope.VARIANT,
        domain="Statistics", subject_id="S1", variant="Two missing frequencies",
        evidence=Evidence(supporting=["Q35", "Q12", "Q15"]),  # shares Q35
        coverage=Coverage(1, ["Two missing frequencies"], 0, CoverageStatus.NOT_APPLICABLE),
        confidence=Confidence(complexity.confidence.observation,
                               complexity.confidence.attribution, "Medium, n=3."),
        priority=Priority("NOT_CALIBRATED", "no data"),
        marks_at_stake=MarksAtStake(3, 10, "Two missing frequencies questions.", True),
        alternative_explanations=AlternativeExplanations(
            declared=["anomalous_question", "confound", "marker_variation"],
            results={
                "anomalous_question": CheckOutcome(CheckResult.RULED_OUT, "n/a"),
                "confound": CheckOutcome(CheckResult.RULED_OUT, "n/a"),
                "marker_variation": CheckOutcome(CheckResult.NOT_RULED_OUT, "n/a"),
            },
        ),
        action=Action.NONE,
        report_language=ReportLanguage("teacher string", "parent string", "student string"),
    )

    headlines = resolve([complexity, synthetic_variant_weakness])

    # Exactly one heading for this student in Statistics.
    stat_headlines = [h for h in headlines if h.domain == "Statistics"
                       and h.subject_id == "S1"]
    assert len(stat_headlines) == 1
    headline = stat_headlines[0]
    assert headline.insight_type == InsightType.COMPLEXITY_GAP  # wider coverage wins

    # The subordinate carries no heading, no action/priority position; it is
    # recorded in evidence.contributing.
    assert len(headline.evidence.contributing) == 1
    contrib = headline.evidence.contributing[0]
    assert contrib.insight_type == InsightType.VARIANT_WEAKNESS
    assert "Q35" in contrib.supporting

    # Subordinate's own aggregable flips to false.
    assert synthetic_variant_weakness.marks_at_stake.aggregable is False

    # Q35 counted exactly once toward any marks total (aggregable=true set).
    aggregable_objs = [o for o in headlines if o.marks_at_stake.aggregable]
    q35_owners = [o for o in aggregable_objs if "Q35" in o.evidence.supporting]
    assert len(q35_owners) == 1
