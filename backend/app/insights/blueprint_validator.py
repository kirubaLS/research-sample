"""Part H: Blueprint Validator (paper authoring). Independent of the rules
engine — runs BEFORE a paper ships, to check it against the diagnosability
thresholds the rules engine will apply later."""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import Question, Complexity, Dependency, CompetencyTier
from . import constants as C

# H3: minimum questions per chapter at a given recall ratio r, derived as
# max(5/r, 5/(1-r)), per the table in H3.
_MIN_QUESTIONS_TABLE = {
    0.50: 10,
    0.40: 13,
    0.33: 15,
    0.25: 20,
}


def min_questions_for_ratio(r: float) -> int:
    import math
    return max(math.ceil(C.MIN_QUESTIONS_PER_GROUP / r),
               math.ceil(C.MIN_QUESTIONS_PER_GROUP / (1 - r)))


@dataclass
class ChapterChecklistResult:
    domain: str
    diagnosable: bool
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def check_chapter(
    domain: str, questions: list[Question], recall_ratio: float,
) -> ChapterChecklistResult:
    """H4 per-chapter checklist, items 1-8."""
    failures: list[str] = []
    n = len(questions)

    # 1. minimum questions for the ratio
    min_q = min_questions_for_ratio(recall_ratio)
    if n < min_q:
        failures.append(f"H4.1: {n} questions, needs at least {min_q} at r={recall_ratio:.0%}")

    # 2. tier ratio applied uniformly is checked at paper level, not here.

    # 3. at least 5 L1 and at least 5 L2+L3
    l1 = [q for q in questions if q.complexity == Complexity.L1]
    multi = [q for q in questions if q.complexity in (Complexity.L2, Complexity.L3)]
    if len(l1) < C.MIN_QUESTIONS_PER_GROUP:
        failures.append(f"H4.3: only {len(l1)} L1 questions, needs {C.MIN_QUESTIONS_PER_GROUP}")
    if len(multi) < C.MIN_QUESTIONS_PER_GROUP:
        failures.append(f"H4.3: only {len(multi)} L2+L3 questions, needs {C.MIN_QUESTIONS_PER_GROUP}")

    # 4. at least 3 distinct variants per tier
    for tier in (CompetencyTier.RECALL, CompetencyTier.APPLICATION, CompetencyTier.ANALYSIS):
        tq = [q for q in questions if q.competency_tier == tier]
        if not tq:
            continue
        variants = {q.concept_variant for q in tq if not q.has_internal_choice}
        if len(variants) < C.MIN_DISTINCT_VARIANTS and len(tq) >= C.MIN_QUESTIONS_PER_GROUP:
            failures.append(f"H4.4: {tier.value} has only {len(variants)} distinct variants")

    # 5. no more than 2 questions with internal choice
    choice_n = sum(1 for q in questions if q.has_internal_choice)
    if choice_n > 2:
        failures.append(f"H4.5: {choice_n} questions carry internal choice, max 2")

    # 6. no single question worth more than 15% of its tier's marks
    for tier in (CompetencyTier.RECALL, CompetencyTier.APPLICATION, CompetencyTier.ANALYSIS):
        tq = [q for q in questions if q.competency_tier == tier]
        total = sum(q.max_marks for q in tq)
        if total == 0:
            continue
        biggest = max(q.max_marks for q in tq)
        if biggest / total > C.MAX_QUESTION_SHARE_OF_TIER:
            failures.append(
                f"H4.6: a {tier.value} question is {biggest / total:.0%} of that "
                f"tier's marks, over {C.MAX_QUESTION_SHARE_OF_TIER:.0%}"
            )

    notes = []
    # 7. Diffuse Signal capacity
    clean_partial = [q for q in questions if q.max_marks > 1 and not q.is_binary
                      and not q.has_internal_choice and not q.is_open_list]
    choice_partial = [q for q in questions if q.max_marks > 1 and not q.is_binary
                       and q.has_internal_choice]
    if len(clean_partial) < C.MIN_PARTIAL_CREDIT_Q:
        notes.append(f"H4.7: only {len(clean_partial)} clean partial-credit questions, "
                     f"Diffuse Signal needs {C.MIN_PARTIAL_CREDIT_Q}")
    if len(choice_partial) > 1:
        notes.append(f"H4.7: {len(choice_partial)} partial-credit questions carry "
                     "internal choice, Diffuse Signal wants at most 1")

    # 8. Integration Gap capacity
    d2 = [q for q in questions if q.dependency == Dependency.D2]
    d2_not_l3 = [q for q in d2 if q.complexity != Complexity.L3]
    if len(d2) < C.MIN_QUESTIONS_PER_GROUP:
        notes.append(f"H4.8: only {len(d2)} D2 questions, Integration Gap needs "
                     f"{C.MIN_QUESTIONS_PER_GROUP}")
    if len(d2_not_l3) < C.MIN_D2_NOT_L3:
        notes.append(f"H4.8: only {len(d2_not_l3)} D2-not-L3 questions, needs "
                     f"{C.MIN_D2_NOT_L3}")

    return ChapterChecklistResult(domain, diagnosable=(len(failures) == 0),
                                   failures=failures, notes=notes)


def uniform_ratio_check(questions_by_chapter: dict[str, list[Question]]) -> list[str]:
    """H1/H4.2: the recall ratio must be applied uniformly across chapters."""
    problems = []
    ratios = {}
    for domain, qs in questions_by_chapter.items():
        total = sum(q.max_marks for q in qs)
        recall = sum(q.max_marks for q in qs if q.competency_tier == CompetencyTier.RECALL)
        ratios[domain] = 0.0 if total == 0 else recall / total
    if not ratios:
        return problems
    values = list(ratios.values())
    spread = max(values) - min(values)
    if spread > 0.10:  # more than 10pp drift between chapters is not "uniform"
        detail = ", ".join(f"{d} {r:.0%}" for d, r in ratios.items())
        problems.append(f"H1: recall ratio is not uniform across chapters ({detail})")
    return problems


@dataclass
class BlueprintReport:
    chapters: list[ChapterChecklistResult]
    ratio_problems: list[str]
    diagnosable_chapters: list[str]
    non_diagnostic_chapters: list[str]
    coverage_statement: str


def validate_paper(questions: list[Question], recall_ratio: float) -> BlueprintReport:
    by_chapter: dict[str, list[Question]] = {}
    for q in questions:
        by_chapter.setdefault(q.domain, []).append(q)

    chapters = [check_chapter(d, qs, recall_ratio) for d, qs in by_chapter.items()]
    ratio_problems = uniform_ratio_check(by_chapter)

    diagnosable = [c.domain for c in chapters if c.diagnosable]
    non_diagnostic = [c.domain for c in chapters if not c.diagnosable]

    if non_diagnostic:
        statement = (
            f"This paper was designed to diagnose {', '.join(diagnosable)} at tier "
            f"level. {', '.join(non_diagnostic)} was covered for syllabus "
            "completeness. No tier-level conclusion is drawn for it."
        )
    else:
        statement = f"This paper diagnoses all {len(diagnosable)} chapters at tier level."

    return BlueprintReport(chapters, ratio_problems, diagnosable, non_diagnostic, statement)
