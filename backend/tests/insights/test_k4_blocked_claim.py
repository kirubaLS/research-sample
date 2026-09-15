"""K4: a blocked claim (Maths, Surface Areas and Volumes — 1 recall question,
minimum 5) renders into Part 3 output with no confidence, priority, marks or
action."""
from app.insights.gate import BlockedClaim, ClaimType
from app.insights.assembly import render_blocked_claim
from app.insights.model import Question, DomainType, CompetencyTier, Complexity, Dependency
from app.insights.flags import compute_flags
from app.insights.rules import tier_gap_student
from .fixtures import q, student
from app.insights.model import Paper


def test_k4_surface_areas_tier_gap_is_blocked():
    questions = [
        q("Q1", "Surface Areas and Volumes", "v1", CompetencyTier.RECALL,
          Complexity.L1, Dependency.D0, 1),
    ]
    for i in range(14):
        questions.append(q(f"Q{i+2}", "Surface Areas and Volumes", f"v{i%4}",
                            CompetencyTier.APPLICATION, Complexity.L2, Dependency.D0, 2))
    paper = Paper(paper_id="MATHS", subject="Maths", questions=questions)
    flags = compute_flags(questions)
    stu = student("S1", "10A", {qq.question_id: 1 for qq in questions})

    assert tier_gap_student(paper, flags, stu) is None

    bc = BlockedClaim(
        claim_type=ClaimType.TIER_GAP,
        analytical_scope="CHAPTER",
        domain="Surface Areas and Volumes",
        blocked_at="STAGE 3",
        reason="recall_count = 1, minimum 5",
        detail="31 marks and 15 question numbers, of which one (Q1, 1 mark) is "
               "recall tier. There is no recall baseline in this chapter.",
        remedy="H7. Four existing 1-mark items rewritten at recall tier raises "
               "the count from 1 to 5 at identical weightage.",
        report_language=(
            "This paper contained 1 recall-tier question in Surface Areas and "
            "Volumes. No comparison between recall and application in this "
            "chapter can be drawn from it."
        ),
    )

    rendered = render_blocked_claim(bc)
    assert "1 recall-tier question" in rendered

    # A blocked claim carries no confidence, priority, marks or action —
    # structurally, BlockedClaim has no such fields at all.
    fields = {f for f in bc.__dataclass_fields__}
    assert "confidence" not in fields
    assert "priority" not in fields
    assert "marks_at_stake" not in fields
    assert "action" not in fields
