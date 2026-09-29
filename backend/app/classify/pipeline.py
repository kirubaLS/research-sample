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

from collections.abc import Callable
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
from app.ingest.probe import full_chapter_evidence, locate, retrieval_query_text

#: how deep retrieval searches before the chapters are voted on. Not the number of
#: passages the reader is shown -- that is a setting, because it is the price of the call.
EVIDENCE_DEPTH = 8

#: Default per-passage character budget (mirrors app.config.classifier_passage_chars),
#: used only when a caller does not pass its own -- pipeline.py stays testable without
#: reading settings, the same reason evidence_passages/evidence_chapters are parameters
#: rather than lookups.
DEFAULT_PASSAGE_CHARS = 1200

#: Above this many passages, trim each one more aggressively rather than let the prompt
#: grow without bound. A chapter with a handful of sections keeps the full budget; a
#: chapter with two or three dozen (the largest seen in this book's own book_map data,
#: e.g. Minerals and Energy Resources) would otherwise multiply passage_chars by 30+.
_PASSAGE_TAPER_AT = 10
_MIN_PASSAGE_CHARS = 300


def _adaptive_passage_chars(base: int, n_passages: int) -> int:
    """Shrink the per-passage character budget as the evidence list grows.

    Keeps the total evidence text roughly bounded (~10x the base budget) once a chapter's
    real section count pushes the passage list past the point a fixed top-K used to cap
    it at, instead of letting every extra section add a full passage's worth of tokens.
    """
    if n_passages <= _PASSAGE_TAPER_AT:
        return base
    return max(_MIN_PASSAGE_CHARS, (base * _PASSAGE_TAPER_AT) // n_passages)


def _full_pool(indexes: list) -> list:
    """Every content chunk any retriever holds, deduplicated by chunk id.

    Locate()'s scored top-K is a guess at what is worth showing the judge; a chapter's
    full set of real sections is not a guess, it is a fact about the book, independent of
    how any one question happened to score against it. Every index already stores the
    same content_chunks()-filtered pool it was built from (LexicalIndex keeps all of it;
    SemanticIndex only what has an embedding), so the union is the fullest pool available
    without a second database read.
    """
    seen: dict[str, object] = {}
    for index in indexes:
        for c in getattr(index, "chunks", []):
            seen.setdefault(c.id, c)
    return list(seen.values())


@dataclass
class PlacedQuestion:
    question_id: str
    marks: float
    #: Null for a skill-anchored question the judge confidently placed outside any
    #: chapter -- see judge.Classification.chapter. board_unit is null exactly when this
    #: is, for the same reason.
    chapter: str | None
    board_unit: str | None
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
    passage_chars: int = DEFAULT_PASSAGE_CHARS,
    on_progress: Callable[[int, int], None] | None = None,
    scope_of: Callable[[str], set[str] | None] | None = None,
) -> tuple[list[QuestionSlot], dict[str, Classification]]:
    """One classification pass over every question.

    ``scope_of(question_id)``, when given, narrows one question to its own set of chapter
    names -- a Social Science paper's Section B is Geography by board convention, so a
    Geography question is never offered a Manufacturing Industries chapter from the
    same group's other book. Combined with the paper-wide ``scope`` by intersection;
    the question's own scope wins outright when the two do not overlap, because it is
    the more certain fact of the two.
    """
    slots: list[QuestionSlot] = []
    judged: dict[str, Classification] = {}
    pool = _full_pool(indexes)
    total = len(questions)

    for done, (question_id, stem, marks) in enumerate(questions, start=1):
        own_scope = scope_of(question_id) if scope_of is not None else None
        q_scope = scope
        if own_scope:
            q_scope = (scope & own_scope or own_scope) if scope is not None else own_scope
        # Retrieval only -- the judge below still reads the real, untouched stem.
        query = retrieval_query_text(stem)
        verdict = locate(
            query, indexes, depth=EVIDENCE_DEPTH, scope=q_scope, chapter_of=chapter_of,
            evidence_passages=evidence_passages, evidence_chapters=evidence_chapters,
        )
        # Retrieval applies the scope itself, so a question with nothing in scope comes
        # back empty. Retry without it rather than lose the question: one missing from the
        # report is worse than one visibly in the wrong place.
        out_of_scope = q_scope is not None and not verdict.evidence
        if out_of_scope:
            verdict = locate(
                query, indexes, depth=EVIDENCE_DEPTH,
                evidence_passages=evidence_passages, evidence_chapters=evidence_chapters,
            )
        # The structural fix: once a chapter is identified for this question, the judge
        # is shown one representative passage from EVERY real section of that chapter --
        # not locate()'s scored top-K, which is a guess at what is worth showing and can
        # (and, on a real paper, did) rank the actually-correct section below any fixed
        # cutoff. verdict.node_id was already chosen respecting scope (locate() filters
        # its ranked lists by scope before ever picking a winner), so pulling everything
        # this chapter has from `pool` -- which is not itself scope-filtered -- cannot
        # leak an out-of-scope chapter's content: it only ever fetches content belonging
        # to the exact node_id locate() already vetted.
        own_evidence = full_chapter_evidence(verdict.node_id, pool, query) if verdict.node_id else []
        if not own_evidence:
            # No section-tagged content for this chapter (e.g. a book imported without
            # section numbers) -- fall back to whatever locate() itself found, rather
            # than showing the judge nothing about the chapter it voted for.
            own_evidence = [c for c in verdict.evidence if c.node_id == verdict.node_id]
        # Rival chapters' own passages are kept too: the judge still needs to see a real
        # competing chapter to tell a question ABOUT a theorem from the theorem, which
        # scoring alone cannot do (see judge.py's docstring). Only the WINNING chapter's
        # evidence is replaced with full section coverage -- chapter selection itself is
        # untouched, this is section-level disambiguation within it.
        rival_evidence = [c for c in verdict.evidence if c.node_id != verdict.node_id]
        candidates = own_evidence + rival_evidence
        budget = _adaptive_passage_chars(passage_chars, len(candidates))
        evidence = [
            Evidence(
                chapter=chapter_of(c.node_id) or "?",
                reference=c.reference,
                section=section_of(c.reference) or (c.section or ""),
                text=c.text[:budget],
            )
            for c in candidates
        ]
        if not evidence:
            if on_progress is not None:
                on_progress(done, total)
            continue

        try:
            call = judge.classify(stem, evidence)
        except Exception as exc:  # noqa: BLE001 -- one bad question must not sink the paper
            # The judge can fail for reasons that have nothing to do with whether this
            # question has a real chapter: the model's own reply can violate a field
            # constraint (a ValidationError raised inside the SDK's own .parse()), a rate
            # limit, a network hiccup, malformed JSON. None of those are evidence about
            # where the question belongs, so this is treated exactly like out_of_scope --
            # confidence forced to 0, no chapter guessed, and it surfaces for a person --
            # rather than being allowed to abort every other question in the paper.
            judged[question_id] = Classification(
                chapter=None,
                curriculum_section=None,
                tier=None,
                skill_required="",
                reasoning=(
                    "the reading model's answer for this question was invalid "
                    f"({exc}) -- needs a person."
                ),
                evidence=[],
                confidence=0.0,
                alternative_chapter=None,
            )
            slots.append(QuestionSlot(question_id, marks, [Option(None, None, 0.0)]))
            if on_progress is not None:
                on_progress(done, total)
            continue

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

        if call.chapter is None:
            # Skill-anchored: the judge said this question has no chapter to point at, and
            # the only honest option set is the one that says so. Giving it real-chapter
            # runners-up as fallbacks would let reconcile()'s marks arithmetic swap it into
            # a chapter it does not belong to -- exactly the force-fit this whole design
            # exists to prevent, just moved from the judge to the solver.
            options = [Option(None, None, confidence)]
        else:
            options = [Option(call.chapter, unit_of(call.chapter) or "?", confidence)]
            seen = {call.chapter}
            for node, _ in verdict.runners_up:
                name = chapter_of(node)
                if q_scope is not None and not out_of_scope and name not in q_scope:
                    continue
                if name and name not in seen:
                    seen.add(name)
                    options.append(
                        Option(name, unit_of(name) or "?", max(0.05, call.confidence * 0.4))
                    )
            if call.alternative_chapter and call.alternative_chapter not in seen:
                if q_scope is None or out_of_scope or call.alternative_chapter in q_scope:
                    options.append(
                        Option(
                            call.alternative_chapter,
                            unit_of(call.alternative_chapter) or "?",
                            call.confidence * 0.8,
                        )
                    )

        slots.append(QuestionSlot(question_id, marks, options))
        if on_progress is not None:
            on_progress(done, total)

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
    passage_chars: int = DEFAULT_PASSAGE_CHARS,
    on_progress: Callable[[int, int], None] | None = None,
    scope_of: Callable[[str], set[str] | None] | None = None,
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

    ``on_progress(done, total)``, when given, is called after each question in
    ``questions`` is classified against the CURRENT pass (see _pass) -- ``done`` counts
    within that pass, not across both, so a paper whose scope gets inferred and runs a
    second pass reports progress that restarts from 1 partway through the job. That is
    the honest shape of the work: the second pass genuinely re-classifies every question.
    """
    inferred: InferredScope | None = None
    scope_source = "declared" if scope is not None else "none"

    slots, judged = _pass(
        questions, indexes, judge, chapter_of, unit_of, section_of, scope,
        evidence_passages, evidence_chapters, passage_chars, on_progress, scope_of,
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
            # A skill-anchored question voted for no chapter and says nothing about which
            # chapters this paper covers -- it is not evidence to aggregate, and Vote.chapter
            # is not nullable because every real vote names one.
            if judged[slot.question_id].chapter is not None
        ])
        # Only act on a scope that explains most of the paper. A narrow scope that leaves a
        # third of the marks outside it would delete real content on the second pass, and a
        # deleted question is worse than a misplaced one -- it vanishes from the report
        # instead of being wrong in it.
        if inferred.confident:
            slots, judged = _pass(
                questions, indexes, judge, chapter_of, unit_of, section_of,
                inferred.chapters, evidence_passages, evidence_chapters, passage_chars,
                on_progress, scope_of,
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
