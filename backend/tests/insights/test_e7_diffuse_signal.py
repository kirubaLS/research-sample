"""E7 Diffuse Signal: the seven-probability-questions flagship case from E7.1,
plus the split-confidence assertion from K2 (observation HIGH-capped-MEDIUM by
E7.4 when D2 is absent, attribution NONE)."""
from app.insights.flags import compute_flags
from app.insights.rules import diffuse_signal_student
from app.insights.insight import Band, InsightType
from app.insights.model import Paper, CompetencyTier, Complexity, Dependency
from .fixtures import q, student


def _probability_paper() -> Paper:
    variants = ["Single-trial A", "Single-trial B", "Compound-trial A",
                "Compound-trial B", "Complement rule", "Single-trial C", "Compound-trial C"]
    complexities = [Complexity.L1] * 4 + [Complexity.L2] * 3
    questions = []
    for i, (v, cx) in enumerate(zip(variants, complexities)):
        questions.append(q(f"P{i}", "Probability", v, CompetencyTier.APPLICATION,
                            cx, Dependency.D0, 3))  # partial-credit, D0/D1 only
    return Paper(paper_id="PROB", subject="Maths", questions=questions)


def test_e7_fires_on_uniform_partial_loss_and_splits_confidence():
    paper = _probability_paper()
    # rest of the paper: high score, so domain is well below the student's own average
    rest = []
    for i in range(6):
        rest.append(q(f"X{i}", "Other Chapter", f"v{i}", CompetencyTier.APPLICATION,
                       Complexity.L1, Dependency.D0, 2))
    paper.questions = paper.questions + rest
    flags = compute_flags(paper.questions)

    # student loses 1 of 3 on every Probability question (uniform ~33% loss
    # each), full marks elsewhere.
    marks_map = {qq.question_id: 2 for qq in paper.questions if qq.domain == "Probability"}
    marks_map.update({r.question_id: 2 for r in rest})
    stu = student("S1", "10A", marks_map)

    class_students = [stu]
    for i in range(10):
        cs_marks = dict(marks_map)
        # most of the class does NOT show the uniform pattern (full marks in Probability)
        for pq in paper.questions:
            if pq.domain == "Probability":
                cs_marks[pq.question_id] = pq.max_marks
        class_students.append(student(f"C{i}", "10A", cs_marks))

    obj = diffuse_signal_student(paper, flags, stu, "Probability", class_students)
    assert obj is not None
    assert obj.insight_type == InsightType.DIFFUSE_SIGNAL
    # Split confidence: observation capped at MEDIUM (D2 absent -> E7.4),
    # attribution NONE.
    assert obj.confidence.observation == Band.MEDIUM
    assert obj.confidence.attribution == Band.NONE
    assert "convention_loss" in obj.alternative_explanations.declared
    assert obj.action.value == "TEACHER_REVIEW"


def test_e7_observation_sorts_above_medium_below_high():
    """D2: ordering sorts on observation first, so a Diffuse Signal (MEDIUM
    observation here, given D2 absent) sits with MEDIUM findings and below a
    fully-attributed HIGH one, and E7.7 keeps it from taking a headline."""
    from app.insights.assembly import order_findings
    from app.insights.insight import (
        InsightObject, SubjectScope, AnalyticalScope, Evidence, Coverage,
        CoverageStatus, Confidence, Priority, MarksAtStake, AlternativeExplanations,
        CheckOutcome, CheckResult, Action, ReportLanguage,
    )

    def make(itype, obs, attr, domain):
        return InsightObject(
            insight_type=itype, subject_scope=SubjectScope.STUDENT,
            analytical_scope=AnalyticalScope.CHAPTER, domain=domain, subject_id="S1",
            evidence=Evidence(supporting=[f"{domain}-Q1"]),
            coverage=Coverage(3, ["v1", "v2", "v3"], 3, CoverageStatus.PASS),
            confidence=Confidence(obs, attr, "reason"),
            priority=Priority("NOT_CALIBRATED", "reason"),
            marks_at_stake=MarksAtStake(1, 2, "basis", True),
            alternative_explanations=AlternativeExplanations(
                declared=["anomalous_question", "confound", "marker_variation"],
                results={k: CheckOutcome(CheckResult.RULED_OUT, "r") for k in
                         ["anomalous_question", "confound", "marker_variation"]},
            ),
            action=Action.NONE, report_language=ReportLanguage("t", "p", "s"),
        )

    high_full = make(InsightType.COMPLEXITY_GAP, Band.HIGH, Band.HIGH, "A")
    diffuse = make(InsightType.DIFFUSE_SIGNAL, Band.HIGH, Band.NONE, "B")
    medium = make(InsightType.TIER_GAP, Band.MEDIUM, Band.MEDIUM, "C")

    ordered = order_findings([medium, diffuse, high_full])
    assert ordered[0] is high_full
    assert ordered[1] is diffuse   # HIGH observation, NONE attribution: below full HIGH
    assert ordered[2] is medium    # below diffuse since MEDIUM < HIGH observation
