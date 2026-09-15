from app.insights.flags import compute_flags
from app.insights.rules import (
    complexity_gap_student, tier_gap_student, integration_gap_student,
    variant_weakness_student,
)
from app.insights.insight import validate, Band
from .fixtures import english_grammar_paper, english_reading_paper, student


def test_k3_grammar_gates():
    paper, stu = english_grammar_paper()
    flags = compute_flags(paper.questions)

    # Tier Gap: BLOCKED, recall 2 < 5
    assert tier_gap_student(paper, flags, stu) is None

    # Integration Gap: BLOCKED, D2 count 2 < 5
    assert integration_gap_student(paper, flags, stu, "English Grammar",
                                    domain_type_skill=True) is None

    # Variant Weakness: BLOCKED, no variant carries 3 items
    for variant in {q.concept_variant for q in paper.questions}:
        assert variant_weakness_student(paper, flags, stu, "English Grammar",
                                         variant, domain_type_skill=True) is None

    # Complexity Gap: PERMITTED, fires HIGH/HIGH
    obj = complexity_gap_student(paper, flags, stu, "English Grammar",
                                  domain_type_skill=True)
    assert obj is not None
    assert obj.confidence.observation == Band.HIGH
    assert obj.confidence.attribution == Band.HIGH
    assert obj.coverage.distinct_variants == 6

    resolved = obj.__dict__.get("_remediation_resolved")
    validate(obj, remediation_lookup_ok=resolved)


def test_k3_reading_gates():
    paper = english_reading_paper()
    flags = compute_flags(paper.questions)
    stu = student("S1", "10A", {q.question_id: 1 for q in paper.questions})

    # Tier Gap: BLOCKED, recall 4 < 5
    assert tier_gap_student(paper, flags, stu) is None

    # Complexity Gap: BLOCKED, L1 count 4 < 5
    assert complexity_gap_student(paper, flags, stu, "English Reading",
                                   domain_type_skill=True) is None

    # Integration Gap: BLOCKED, D2 count 2 < 5
    assert integration_gap_student(paper, flags, stu, "English Reading",
                                    domain_type_skill=True) is None

    # Variant Weakness: BLOCKED — Literal retrieval has 3 items but all at L1
    # (fails the "not all questions at same complexity" gate)
    assert variant_weakness_student(paper, flags, stu, "English Reading",
                                     "Fact stated in passage",
                                     domain_type_skill=True) is None
