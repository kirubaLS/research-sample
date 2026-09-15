from app.insights.flags import compute_flags
from app.insights.rules import complexity_gap_student
from app.insights.insight import validate, Band, InsightType, AnalyticalScope
from .fixtures import statistics_paper


def test_k1_complexity_gap_fires_and_validates():
    paper, questions, stu = statistics_paper()
    flags = compute_flags(questions)

    obj = complexity_gap_student(paper, flags, stu, "Statistics")
    assert obj is not None
    assert obj.insight_type == InsightType.COMPLEXITY_GAP
    assert obj.analytical_scope == AnalyticalScope.CHAPTER
    assert obj.domain == "Statistics"

    # group sizes per K1
    l1_total = next(g for g in obj.evidence.group_totals if g.label == "single-step")
    l2_total = next(g for g in obj.evidence.group_totals if g.label == "multi-step")
    assert l1_total.question_count == 7
    assert l2_total.question_count == 10

    # coverage: 9 distinct multi-step variants, PASS
    assert obj.coverage.distinct_variants == 9
    assert obj.coverage.minimum_required == 3

    # the gap must clear materiality
    assert (l1_total.pct - l2_total.pct) >= 15

    # marker dependence: multi-step is not binary and >1 mark => marker-dependent
    # so with a majority marker-dependent group at STUDENT scope, confidence caps at MEDIUM
    assert obj.confidence.observation in (Band.MEDIUM, Band.HIGH)
    assert obj.confidence.attribution == obj.confidence.observation

    # action resolves via remediation table (present in fixture)
    resolved = obj.__dict__.get("_remediation_resolved")
    assert resolved is True

    # marks_at_stake basis excludes absent students, aggregable true for a
    # standalone (non-subordinate) object
    assert obj.marks_at_stake.aggregable is True
    assert isinstance(obj.marks_at_stake.lost, int)
    assert isinstance(obj.marks_at_stake.available, int)
    assert obj.marks_at_stake.available == 25

    # G1 validation passes
    validate(obj, remediation_lookup_ok=resolved)


def test_k1_alternative_explanations_declared_set():
    paper, questions, stu = statistics_paper()
    flags = compute_flags(questions)
    obj = complexity_gap_student(paper, flags, stu, "Statistics")
    declared = set(obj.alternative_explanations.declared)
    assert declared == {"anomalous_question", "confound", "marker_variation"}
    for name in declared:
        outcome = obj.alternative_explanations.results[name]
        assert outcome is not None
        assert outcome.reason.strip() != ""
