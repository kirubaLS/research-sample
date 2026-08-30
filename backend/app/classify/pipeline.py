"""Retrieve, judge, reconcile -- the whole placement path for a paper.

Three stages, each catching what the one before cannot:

1. **Retrieve** (hybrid lexical + semantic). Narrows fourteen chapters to a handful of
   candidate passages. Cannot decide between them.
2. **Judge** (a model reading those passages). Separates a question about a theorem from
   the theorem, which distance cannot. Decides one question at a time, so it cannot notice
   that the paper's marks no longer add up.
3. **Reconcile** (the declared blueprint). Sees the whole paper at once and overrules a
   confident placement when the arithmetic says it must be wrong.

What is left after all three is genuinely ambiguous, and goes to a person -- once per
paper, not once per student.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.classify.judge import Classification, Evidence
from app.classify.reconcile import (
    Option,
    QuestionSlot,
    Reconciliation,
    needs_a_human,
    reconcile,
)
from app.ingest.probe import locate

#: candidate passages shown to the judge. Enough to cover the right chapter and a rival,
#: few enough that the prompt stays about this question.
EVIDENCE_DEPTH = 8


@dataclass
class PlacedQuestion:
    question_id: str
    marks: float
    chapter: str
    board_unit: str
    curriculum_section: str | None
    tier: str
    skill_required: str
    confidence: float
    reasoning: str
    evidence: list[str] = field(default_factory=list)
    #: True when the blueprint moved it away from the judge's own first choice
    overruled: bool = False
    needs_review: bool = False


@dataclass
class PaperPlacement:
    questions: list[PlacedQuestion]
    feasible: bool
    note: str
    residual: dict[str, tuple[float, float]]
    reviewed_count: int

    @property
    def settled(self) -> int:
        return sum(1 for q in self.questions if not q.needs_review)


def place_paper(
    questions: list[tuple[str, str, float]],
    indexes: list,
    judge,
    *,
    chapter_of,
    unit_of,
    section_of,
    declared: dict[str, float] | None = None,
    scope: set[str] | None = None,
) -> PaperPlacement:
    """Place every question in a paper.

    ``questions``  (question_id, stem, marks)
    ``chapter_of`` node id -> chapter name; ``unit_of`` chapter name -> board unit code;
    ``section_of`` chunk reference -> NCERT section number. Passed in rather than looked up
    so this stays testable without a database.

    ``scope`` is the chapters the test declares it covers. Most papers are daily or cyclic
    tests with no published weightage, and this is the strongest constraint they have: a
    question placed outside the scope is provably wrong, so out-of-scope passages are
    dropped before the judge ever sees them and the candidate set shrinks from fourteen
    chapters to a handful. None means the paper declared nothing -- which is different from
    declaring the whole syllabus, and must stay different, because a report has to be able
    to say which it was working from.
    """
    slots: list[QuestionSlot] = []
    judged: dict[str, Classification] = {}

    for question_id, stem, marks in questions:
        verdict = locate(stem, indexes, depth=EVIDENCE_DEPTH, scope=scope, chapter_of=chapter_of)
        evidence = [
            Evidence(
                chapter=chapter_of(c.node_id) or "?",
                reference=c.reference,
                section=section_of(c.reference) or "",
                text=c.text if hasattr(c, "text") else "",
            )
            for c in verdict.evidence
        ]
        # Out-of-scope chapters are removed, not down-weighted: the teacher said this test
        # covers chapters 1 to 5, so chapter 9 is not a weaker answer, it is a wrong one.
        if scope is not None:
            evidence = [e for e in evidence if e.chapter in scope]
        if not evidence:
            continue

        call = judge.classify(stem, evidence)
        judged[question_id] = call

        # the judge's answer, plus the rivals retrieval offered, so the blueprint has
        # somewhere to move a question TO
        options = [Option(call.chapter, unit_of(call.chapter) or "?", call.confidence)]
        seen = {call.chapter}
        for node, _ in verdict.runners_up:
            name = chapter_of(node)
            if scope is not None and name not in scope:
                continue
            if name and name not in seen:
                seen.add(name)
                # a rival retrieval ranked but the judge passed over is possible, not
                # likely: enough to be movable, not enough to win on its own
                options.append(Option(name, unit_of(name) or "?", max(0.05, call.confidence * 0.4)))
        if call.alternative_chapter and call.alternative_chapter not in seen:
            options.append(
                Option(
                    call.alternative_chapter,
                    unit_of(call.alternative_chapter) or "?",
                    call.confidence * 0.8,
                )
            )

        slots.append(QuestionSlot(question_id, marks, options))

    result: Reconciliation = reconcile(slots, declared or {})
    flagged = set(needs_a_human(slots, result))

    placed = [
        PlacedQuestion(
            question_id=slot.question_id,
            marks=slot.marks,
            chapter=result.assignment[slot.question_id].chapter,
            board_unit=result.assignment[slot.question_id].board_unit,
            curriculum_section=judged[slot.question_id].curriculum_section,
            tier=judged[slot.question_id].tier,
            skill_required=judged[slot.question_id].skill_required,
            confidence=result.assignment[slot.question_id].confidence,
            reasoning=judged[slot.question_id].reasoning,
            evidence=judged[slot.question_id].evidence,
            overruled=slot.question_id in result.overruled,
            needs_review=slot.question_id in flagged,
        )
        for slot in slots
    ]

    return PaperPlacement(
        questions=placed,
        feasible=result.feasible,
        note=result.note,
        residual=result.residual,
        reviewed_count=len(flagged),
    )
