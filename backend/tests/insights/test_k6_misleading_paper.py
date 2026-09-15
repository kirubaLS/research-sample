"""K6: a 90% recall paper on which a student scores well must never produce a
strength claim. Structural defence: no rule's fire condition is 'scored
well', and F3 rejects strength words even if one were emitted by mistake."""
from app.insights.flags import compute_flags
from app.insights.rules import tier_gap_student, complexity_gap_student
from app.insights.model import Paper, CompetencyTier, Complexity, Dependency
from app.insights.strings import check_boundaries, _STRENGTH_WORDS
from .fixtures import q, student


def _ninety_ten_paper() -> Paper:
    questions = []
    for i in range(18):
        questions.append(q(f"R{i}", "Chapter A", f"recall-v{i % 4}",
                            CompetencyTier.RECALL, Complexity.L1, Dependency.D0, 1))
    for i in range(2):
        questions.append(q(f"A{i}", "Chapter A", f"app-v{i}",
                            CompetencyTier.APPLICATION, Complexity.L2, Dependency.D0, 5))
    return Paper(paper_id="90-10", subject="Maths", questions=questions)


def test_k6_no_strength_claim_on_high_scoring_student():
    paper = _ninety_ten_paper()
    flags = compute_flags(paper.questions)
    marks = {f"R{i}": 1 for i in range(18)}
    marks.update({"A0": 5, "A1": 5})
    stu = student("S1", "10A", marks)

    # Second defence: nonrecall_count (2) fails the 5-question minimum, so
    # Tier Gap never reaches evaluation.
    assert tier_gap_student(paper, flags, stu) is None
    assert complexity_gap_student(paper, flags, stu, "Chapter A") is None


def test_k6_no_rule_module_contains_a_strength_word():
    """Static sweep of every frozen string in the table: none contains a
    strength word (F3), independent of any particular fixture."""
    from app.insights import strings as S
    for key, template in S.STRINGS.items():
        failures = check_boundaries(template, key=key)
        strength_failures = [f for f in failures if f.startswith("F3 strength")]
        assert not strength_failures, f"{key}: {strength_failures}"
