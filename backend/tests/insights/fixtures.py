"""Shared fixtures for the K-series acceptance tests."""
from __future__ import annotations

from app.insights.model import (
    Question, DomainType, CompetencyTier, Complexity, Dependency, StudentPaper,
    StudentResponse, Paper, RemediationTable, RemediationRow, BoardUrgencyTable,
    BoardUrgencyRow,
)


def q(qid, domain, variant, tier, cx, dep, marks, *, domain_type=DomainType.CHAPTER,
      concept_family=None, is_binary=False, has_choice=False):
    return Question(
        question_id=qid, domain=domain, domain_type=domain_type,
        board_unit="unit", concept_family=concept_family or f"{domain}:{variant}",
        concept_variant=variant, competency_tier=tier, complexity=cx,
        dependency=dep, max_marks=marks, is_binary=is_binary,
        has_internal_choice=has_choice,
    )


def student(student_id, class_id, marks: dict[str, int | None]) -> StudentPaper:
    resp = {qid: StudentResponse(student_id, qid, m) for qid, m in marks.items()}
    return StudentPaper(student_id=student_id, class_id=class_id, responses=resp)


def statistics_paper() -> tuple[Paper, list[Question]]:
    """K1 fixture: Statistics chapter, complexity-gap-shaped evidence.
    7 single-step (8 marks total), 10 multi-step (25 marks total), 9 distinct
    multi-step variants, largest variant share 20% (2 of 10)."""
    l1 = [
        q("Q10", "Statistics", "Mean, direct method", CompetencyTier.APPLICATION,
          Complexity.L1, Dependency.D0, 1, concept_family="Central tendency, mean"),
        q("Q11", "Statistics", "Median, ungrouped", CompetencyTier.APPLICATION,
          Complexity.L1, Dependency.D0, 1, concept_family="Central tendency, median"),
        q("Q13", "Statistics", "Mode, ungrouped", CompetencyTier.RECALL,
          Complexity.L1, Dependency.D0, 1, concept_family="Central tendency, mode"),
        q("Q14", "Statistics", "Class mark recall", CompetencyTier.RECALL,
          Complexity.L1, Dependency.D0, 1, concept_family="Grouped data structure"),
        q("Q22b", "Statistics", "Mean, missing frequency", CompetencyTier.APPLICATION,
          Complexity.L1, Dependency.D0, 1, concept_family="Central tendency, mean"),
        q("Q37i", "Statistics", "Median formula recall", CompetencyTier.RECALL,
          Complexity.L1, Dependency.D0, 1, concept_family="Central tendency, median"),
        q("Q37ii", "Statistics", "Modal class identification", CompetencyTier.RECALL,
          Complexity.L1, Dependency.D0, 2, concept_family="Central tendency, mode"),
    ]
    multi_variants = [
        "Mean, assumed mean method", "Median, grouped, cf table",
        "Mode, grouped formula", "Two missing frequencies", "Two missing frequencies",
        "Combined mean, two groups", "Ogive construction", "Mean-median-mode relation",
        "Grouped data, class width change", "Cumulative frequency, more-than type",
    ]
    l2 = []
    marks_seq = [2, 3, 3, 3, 3, 2, 3, 2, 2, 2]  # sums to 25
    ids = ["Q12", "Q15", "Q19", "Q22a", "Q23", "Q28", "Q29", "Q34", "Q35", "Q37iii"]
    for qid, variant, mk in zip(ids, multi_variants, marks_seq):
        l2.append(q(qid, "Statistics", variant, CompetencyTier.APPLICATION,
                     Complexity.L2, Dependency.D1, mk,
                     concept_family="Central tendency, mean"))

    questions = l1 + l2

    remediation = RemediationTable([
        RemediationRow("Statistics", CompetencyTier.APPLICATION, ["NCERT 14.2"]),
        RemediationRow("English Grammar", CompetencyTier.APPLICATION, ["NCERT Grammar App"]),
    ])
    board = BoardUrgencyTable()  # deliberately empty (J3)
    paper = Paper(paper_id="MATHS-2026", subject="Mathematics", questions=questions,
                  board_urgency=board, remediation=remediation)

    # Student scores: ~87.5% single-step (7/8), ~60% multi-step (15/25).
    marks_map = {
        "Q10": 1, "Q11": 1, "Q13": 1, "Q14": 1, "Q22b": 1, "Q37i": 1, "Q37ii": 1,  # 7/8
        "Q12": 1, "Q15": 2, "Q19": 1, "Q22a": 2, "Q23": 2, "Q28": 1, "Q29": 2,
        "Q34": 1, "Q35": 1, "Q37iii": 1,  # sums to 14 of 25 (~56%)
    }
    stu = student("S1", "10A", marks_map)
    return paper, questions, stu


def english_grammar_paper() -> tuple[Paper, StudentPaper]:
    """K3 Grammar fixture."""
    rows = [
        ("G1", "Present perfect vs simple past", CompetencyTier.APPLICATION, Complexity.L1, Dependency.D0),
        ("G2", "Collective noun subject", CompetencyTier.APPLICATION, Complexity.L1, Dependency.D1),
        ("G3", "Quantifier with uncountable noun", CompetencyTier.APPLICATION, Complexity.L1, Dependency.D0),
        ("G4", "Obligation vs deduction", CompetencyTier.APPLICATION, Complexity.L1, Dependency.D0),
        ("G5", "Statement to reported, tense shift", CompetencyTier.APPLICATION, Complexity.L2, Dependency.D1),
        ("G6", "Question to reported", CompetencyTier.APPLICATION, Complexity.L2, Dependency.D1),
        ("G7", "Active to passive, past tense", CompetencyTier.APPLICATION, Complexity.L2, Dependency.D1),
        ("G8", "Relative clause joining", CompetencyTier.APPLICATION, Complexity.L2, Dependency.D1),
        ("G9", "Name the tense used", CompetencyTier.RECALL, Complexity.L1, Dependency.D0),
        ("G10", "Article choice, rule recall", CompetencyTier.RECALL, Complexity.L1, Dependency.D0),
        ("G11", "Error identification, mixed systems", CompetencyTier.APPLICATION, Complexity.L2, Dependency.D2),
        ("G12", "Omission, mixed systems", CompetencyTier.APPLICATION, Complexity.L2, Dependency.D2),
    ]
    questions = [
        q(qid, "English Grammar", variant, tier, cx, dep, 1,
          domain_type=DomainType.SKILL, is_binary=True,
          concept_family=f"English Grammar:{variant}")
        for qid, variant, tier, cx, dep in rows
    ]
    remediation = RemediationTable([
        RemediationRow("English Grammar", CompetencyTier.APPLICATION, ["NCERT Grammar App"]),
    ])
    paper = Paper(paper_id="ENG-2026", subject="English", questions=questions,
                  remediation=remediation)
    # illustrative 83% single-step (5/6), 33% multi-step (2/6)
    marks_map = {
        "G1": 1, "G2": 1, "G3": 1, "G4": 1, "G9": 0, "G10": 1,       # 5/6
        "G5": 1, "G6": 0, "G7": 0, "G8": 0, "G11": 1, "G12": 0,      # 2/6
    }
    stu = student("S1", "10A", marks_map)
    return paper, stu


def english_reading_paper() -> Paper:
    rows = [
        ("R1", "Fact stated in passage", CompetencyTier.RECALL, Complexity.L1, Dependency.D0, 1),
        ("R2", "Figure quoted in passage", CompetencyTier.RECALL, Complexity.L1, Dependency.D0, 1),
        ("R3", "Synonym for a marked word", CompetencyTier.RECALL, Complexity.L1, Dependency.D0, 1),
        # Spec's summary line states "L1 4 . L2 6" for this section (K3); R4 is
        # placed at L2 here to match that stated total, per the explicit gate
        # assertions in K3 (Complexity Gap BLOCKED, L1 4, min 5).
        ("R4", "Shade of meaning or antonym", CompetencyTier.APPLICATION, Complexity.L2, Dependency.D1, 1),
        ("R5", "Implied reason", CompetencyTier.ANALYSIS, Complexity.L2, Dependency.D1, 1),
        ("R6", "Implied consequence, two-part", CompetencyTier.ANALYSIS, Complexity.L2, Dependency.D2, 2),
        ("R7", "Best title for the passage", CompetencyTier.ANALYSIS, Complexity.L2, Dependency.D2, 1),
        ("R8", "Writer's attitude", CompetencyTier.ANALYSIS, Complexity.L2, Dependency.D1, 1),
        ("R9", "Function of a paragraph", CompetencyTier.APPLICATION, Complexity.L2, Dependency.D1, 1),
        ("R10", "True or false with justification", CompetencyTier.RECALL, Complexity.L1, Dependency.D0, 1),
    ]
    questions = [
        q(qid, "English Reading", variant, tier, cx, dep, mk,
          domain_type=DomainType.SKILL, is_binary=(mk == 1),
          concept_family=f"English Reading:{variant}")
        for qid, variant, tier, cx, dep, mk in rows
    ]
    return Paper(paper_id="ENG-READ-2026", subject="English", questions=questions)
