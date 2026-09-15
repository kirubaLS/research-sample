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
from app.classify.scope import InferredScope, Vote, infer_scope
from app.ingest.probe import locate

#: how deep retrieval searches before the chapters are voted on. Not the number of
#: passages the reader is shown -- that is a setting, because it is the price of the call.
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
    #: what the paper turned out to be about, when nobody declared it
    scope: InferredScope | None = None
    scope_source: str = "none"        # 'declared' | 'inferred' | 'none'

    @property
    def settled(self) -> int:
        return sum(1 for q in self.questions if not q.needs_review)


def _pass(
    questions: list[tuple[str, str, float]],
    indexes: list,
    judge,
    chapter_of,
    unit_of,
    section_of,
    scope: set[str] | None,
    evidence_passages: int,
    evidence_chapters: int,
) -> tuple[list[QuestionSlot], dict[str, Classification]]:
    """One classification pass over every question."""
    slots: list[QuestionSlot] = []
    judged: dict[str, Classification] = {}

    for question_id, stem, marks in questions:
        verdict = locate(
            stem, indexes, depth=EVIDENCE_DEPTH, scope=scope, chapter_of=chapter_of,
            evidence_passages=evidence_passages, evidence_chapters=evidence_chapters,
        )
        # Retrieval applies the scope itself, so a question with nothing in scope comes
        # back empty. Retry without it rather than lose the question: one missing from the
        # report is worse than one visibly in the wrong place.
        out_of_scope = scope is not None and not verdict.evidence
        if out_of_scope:
            verdict = locate(
                stem, indexes, depth=EVIDENCE_DEPTH,
                evidence_passages=evidence_passages, evidence_chapters=evidence_chapters,
            )
        evidence = [
            Evidence(
                chapter=chapter_of(c.node_id) or "?",
                reference=c.reference,
                section=section_of(c.reference) or "",
                text=c.text,
            )
            for c in verdict.evidence
        ]
        if not evidence:
            continue

        call = judge.classify(stem, evidence)

        # a question whose evidence all fell outside the scope cannot be trusted to the
        # confidence the judge gave it, whatever that was
        confidence = 0.0 if out_of_scope else call.confidence
        judged[question_id] = (
            call.model_copy(update={
                "confidence": 0.0,
                "reasoning": (
                    "nothing retrieved for this question is in the paper's scope, so it "
                    "needs a person: either the scope is too narrow, or this question is "
                    "not from this paper. " + call.reasoning
                ),
            })
            if out_of_scope else call
        )

        options = [Option(call.chapter, unit_of(call.chapter) or "?", confidence)]
        seen = {call.chapter}
        for node, _ in verdict.runners_up:
            name = chapter_of(node)
            if scope is not None and not out_of_scope and name not in scope:
                continue
            if name and name not in seen:
                seen.add(name)
                options.append(
                    Option(name, unit_of(name) or "?", max(0.05, call.confidence * 0.4))
                )
        if call.alternative_chapter and call.alternative_chapter not in seen:
            if scope is None or out_of_scope or call.alternative_chapter in scope:
                options.append(
                    Option(
                        call.alternative_chapter,
                        unit_of(call.alternative_chapter) or "?",
                        call.confidence * 0.8,
                    )
                )

        slots.append(QuestionSlot(question_id, marks, options))

    return slots, judged


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
    infer_scope_when_undeclared: bool = True,
    evidence_passages: int = EVIDENCE_DEPTH,
    evidence_chapters: int = 1,
) -> PaperPlacement:
    """Place every question in a paper.

    ``questions``  (question_id, stem, marks)
    ``chapter_of`` node id -> chapter name; ``unit_of`` chapter name -> board unit code;
    ``section_of`` chunk reference -> NCERT section number. Passed in rather than looked up
    so this stays testable without a database.

    ``scope`` is what the paper declares it covers. When nothing is declared, a first pass
    classifies freely and the scope is inferred from where the questions actually fell --
    an easier problem than any single placement, because a chapter twelve questions agree
    on is nearly certain while one question alone in a chapter is more likely an error.
    A second pass then runs with the outliers ruled out.
    """
    inferred: InferredScope | None = None
    scope_source = "declared" if scope is not None else "none"

    slots, judged = _pass(
        questions, indexes, judge, chapter_of, unit_of, section_of, scope,
        evidence_passages, evidence_chapters,
    )

    if scope is None and infer_scope_when_undeclared and slots:
        inferred = infer_scope([
            Vote(
                question_id=slot.question_id,
                chapter=judged[slot.question_id].chapter,
                marks=slot.marks,
                confidence=judged[slot.question_id].confidence,
            )
            for slot in slots
        ])
        # Only act on a scope that explains most of the paper. A narrow scope that leaves a
        # third of the marks outside it would delete real content on the second pass, and a
        # deleted question is worse than a misplaced one -- it vanishes from the report
        # instead of being wrong in it.
        if inferred.confident:
            slots, judged = _pass(
                questions, indexes, judge, chapter_of, unit_of, section_of,
                inferred.chapters, evidence_passages, evidence_chapters,
            )
            scope_source = "inferred"

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
        scope=inferred,
        scope_source=scope_source,
    )
