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

from app.classify.gate import chapter_gate
from app.classify.judge import TIERS, Classification, Evidence
from app.classify.reconcile import (
    Option,
    QuestionSlot,
    Reconciliation,
    needs_a_human,
    reconcile,
)
from app.classify.scope import InferredScope, Vote, infer_scope
from app.ingest.probe import full_chapter_evidence, locate, retrieval_query_text, search_all

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
    #: True when the judge could not be asked at all (an API refusal, a rate limit, a
    #: reply the SDK rejected). Not a judgment: the question's earlier placement stands.
    judge_failed: bool = False
    #: placed in a chapter outside the scope declared for it (cross_scope_fallback, or
    #: nothing in scope retrieved at all) -- always also needs_review
    cross_scope: bool = False
    #: the scope named exactly one chapter, so the chapter judge was not asked
    #: (skip_single_chapter_judge); the tier then comes from the topic judge
    chapter_judge_skipped: bool = False
    #: ...because a person already confirmed a near-identical question in this school
    #: (app.classify.memory); the confirmed section and tier ride on the placement and the
    #: topic judge is not asked either. Always also chapter_judge_skipped.
    memory_reused: bool = False
    #: ...because both retrievers agreed with a clear lead (Tier 0, app.classify.gate), not
    #: because the paper declared the chapter. Always also chapter_judge_skipped.
    chapter_gated: bool = False
    #: the chapter judge's own confidence, and how many chapters it chose among -- None
    #: and 0 when it was not asked (skipped, failed, nothing retrieved)
    judge_confidence: float | None = None
    chapters_shown: int = 0


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


@dataclass(frozen=True)
class PassOptions:
    """Behaviour switches for one classification pass. All off reproduces the original
    pass exactly. Settings decide them (app.api.placement); this module never reads
    settings, so it stays testable without them."""

    #: chapter label -> the book (subject code) it belongs to. With ``balanced`` on and a
    #: question whose scope spans several books, the judge is shown each book's best
    #: retrieval candidate, not only the global top chapters (balanced_group_candidates).
    book_of: dict[str, str] | None = None
    balanced: bool = False
    #: ask the judge whether no in-scope chapter can answer, and if so re-ask over the
    #: whole group; such a placement is cross_scope (cross_scope_fallback)
    cross_scope: bool = False
    #: a question whose declared scope is exactly one chapter is not sent to the chapter
    #: judge (skip_single_chapter_judge)
    skip_single_chapter: bool = False
    #: the paper-wide ``scope`` passed to the pass was declared (teacher, syllabus), not
    #: inferred -- only a declared single-chapter scope may skip the judge
    scope_declared: bool = False
    #: (chapter label, section) -> the section cut to the subject's depth
    #: (topic_depth_cap): the judge sees one passage per major topic, labelled with it
    section_cap: Callable[[str | None, str | None], str | None] | None = None
    #: Tier 0 (app.classify.gate): evaluate whether retrieval alone is sure of the chapter.
    #: ``gate_log`` is filled with question id -> the gate's decision, and later the
    #: chapter judge's answer for it, so a shadow run can be scored. Without
    #: ``gate_enforce`` the judge is still asked about every question.
    gate: bool = False
    gate_enforce: bool = False
    gate_min_margin: float = 0.3
    #: a cross-encoder (app.ingest.rerank.JinaReranker) as the gate's third reader: it must
    #: not prefer another chapter among the verdict's own passages
    gate_reranker: object | None = None
    gate_log: dict | None = None
    #: what teachers have already confirmed (app.classify.memory). Giving a memory alone
    #: only OBSERVES: each question's closest confirmed neighbour is written to
    #: ``memory_log`` next to the judge's answer. ``memory_reuse`` then lets a question
    #: that is, to within a few words, one already confirmed in the same school take that
    #: placement without either judge; ``memory_demos`` shows the judge that many similar
    #: confirmed questions as worked examples.
    memory: object | None = None
    memory_reuse: bool = False
    memory_min_similarity: float = 0.9
    memory_demos: int = 0
    memory_demo_min_similarity: float = 0.4
    memory_log: dict | None = None
    #: Several questions per chapter-judge call (classify_many): saves the per-call overhead
    #: and the reasoning preamble, not the passages. A question the grouped answer misses is
    #: asked alone. Needs a live judge that offers classify_many; ignored otherwise.
    group_size: int = 1
    #: Re-ask a low-confidence answer with the passages in a different order and take the
    #: majority chapter. A thinking model offers no sampling temperature, so reordering is
    #: the perturbation: an answer that flips when only the order changed was not an answer.
    #: Live judge only -- every re-ask in a batched judge would wait a whole batch.
    recheck: bool = False
    recheck_below: float = 0.8
    recheck_n: int = 2
    recheck_log: dict | None = None


#: passages each other book contributes when candidates are balanced across books
BALANCED_PASSAGES_PER_BOOK = 2


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
    options: PassOptions | None = None,
    asked: dict[str, tuple[float, int]] | None = None,
) -> tuple[list[QuestionSlot], dict[str, Classification], set[str], set[str], set[str]]:
    """One classification pass over every question. Returns the slots, the judgments,
    the ids of the questions the judge could not be asked about at all, the ids placed
    outside their declared scope, and the ids whose chapter judge was skipped.

    ``scope_of(question_id)``, when given, narrows one question to its own set of chapter
    names -- a Social Science paper's Section B is Geography by board convention, so a
    Geography question is never offered a Manufacturing Industries chapter from the
    same group's other book. Combined with the paper-wide ``scope`` by intersection;
    the question's own scope wins outright when the two do not overlap, because it is
    the more certain fact of the two.

    ``asked``, when given, is filled with question id -> (the chapter judge's own
    confidence, how many chapters it chose among) for every question the judge actually
    answered -- what review_flag_rule's confidence condition reads.
    """
    options = options or PassOptions()
    slots: list[QuestionSlot] = []
    judged: dict[str, Classification] = {}
    failed: set[str] = set()
    crossed: set[str] = set()
    skipped: set[str] = set()
    pool = _full_pool(indexes)
    total = len(questions)
    prepared: list[tuple] = []
    every_label = set(options.book_of or {})
    #: questions whose scope was DECLARED (their own section title, or a declared
    #: paper-wide scope) -- only these can be placed cross-scope; an inferred scope is a
    #: guess about the paper, and leaving it is not leaving a declaration
    declared: set[str] = set()

    def books_in(labels: set[str] | None) -> dict[str, set[str]]:
        """book -> its chapter labels, within ``labels`` (all of them when None)."""
        out: dict[str, set[str]] = {}
        for label, book in (options.book_of or {}).items():
            if labels is None or label in labels:
                out.setdefault(book, set()).add(label)
        return out

    def build_evidence(verdict, query: str, extra: list | None = None) -> list[Evidence]:
        # The structural fix: once a chapter is identified for this question, the judge
        # is shown one representative passage from EVERY real section of that chapter --
        # not locate()'s scored top-K, which is a guess at what is worth showing and can
        # (and, on a real paper, did) rank the actually-correct section below any fixed
        # cutoff. verdict.node_id was already chosen respecting scope (locate() filters
        # its ranked lists by scope before ever picking a winner), so pulling everything
        # this chapter has from `pool` -- which is not itself scope-filtered -- cannot
        # leak an out-of-scope chapter's content: it only ever fetches content belonging
        # to the exact node_id locate() already vetted.
        cap = options.section_cap
        key = None
        if cap is not None and verdict.node_id:
            label = chapter_of(verdict.node_id)

            def key(section, _label=label):
                return cap(_label, section)
        own_evidence = (
            full_chapter_evidence(verdict.node_id, pool, query, section_key=key)
            if verdict.node_id else []
        )
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
        shown_chapters = {c.node_id for c in candidates}
        for c in extra or []:
            if c.node_id not in shown_chapters or c.chunk_id not in {x.chunk_id for x in candidates}:
                candidates.append(c)
        budget = _adaptive_passage_chars(passage_chars, len(candidates))

        def shown_section(c) -> str:
            section = section_of(c.reference) or (c.section or "")
            if cap is not None and section:
                section = cap(chapter_of(c.node_id), section) or section
            return section

        return [
            Evidence(
                chapter=chapter_of(c.node_id) or "?",
                reference=c.reference,
                section=shown_section(c),
                text=c.text[:budget],
            )
            for c in candidates
        ]

    def retrieve(query: str, q_scope: set[str] | None):
        """(verdict, evidence, out_of_scope) for one question."""
        books = books_in(q_scope) if options.balanced else {}
        ranked = None
        if len(books) > 1:
            # one search serves the scoped verdict and every per-book verdict below
            ranked = search_all(query, indexes, EVIDENCE_DEPTH * 3 * len(books))
        verdict = locate(
            query, indexes, depth=EVIDENCE_DEPTH, scope=q_scope, chapter_of=chapter_of,
            evidence_passages=evidence_passages, evidence_chapters=evidence_chapters,
            ranked=ranked,
        )
        # Retrieval applies the scope itself, so a question with nothing in scope comes
        # back empty. Retry without it rather than lose the question: one missing from the
        # report is worse than one visibly in the wrong place.
        out_of_scope = q_scope is not None and not verdict.evidence
        if out_of_scope:
            verdict = locate(
                query, indexes, depth=EVIDENCE_DEPTH,
                evidence_passages=evidence_passages, evidence_chapters=evidence_chapters,
                ranked=ranked,
            )
        extra: list = []
        if len(books) > 1 and not out_of_scope:
            # Balanced: every book in scope puts its own best chapter in front of the
            # judge, so a weak lexical match in one book is never crowded out by three
            # strong ones from another.
            for _book, labels in sorted(books.items()):
                best = locate(
                    query, indexes, depth=EVIDENCE_DEPTH, scope=labels,
                    chapter_of=chapter_of, evidence_passages=BALANCED_PASSAGES_PER_BOOK,
                    evidence_chapters=1, ranked=ranked,
                )
                extra.extend(best.evidence[:BALANCED_PASSAGES_PER_BOOK])
        return verdict, build_evidence(verdict, query, extra), out_of_scope

    # Phase 1: retrieval and evidence for every question, no model call yet.
    for done, (question_id, stem, marks) in enumerate(questions, start=1):
        own_scope = scope_of(question_id) if scope_of is not None else None
        q_scope = scope
        if own_scope:
            q_scope = (scope & own_scope or own_scope) if scope is not None else own_scope
        if own_scope or (options.scope_declared and scope):
            declared.add(question_id)

        if options.skip_single_chapter:
            single = None
            if own_scope and len(own_scope) == 1:
                single = next(iter(own_scope))
            elif not own_scope and options.scope_declared and scope and len(scope) == 1:
                single = next(iter(scope))
            if single is not None and (not every_label or single in every_label or unit_of(single)):
                # The paper names exactly one chapter for this question: nothing for the
                # chapter judge to decide. The topic judge reads it next, and names the
                # tier (see app.api.placement).
                judged[question_id] = Classification(
                    chapter=single, curriculum_section=None, tier=None, skill_required="",
                    reasoning=(
                        f"the paper's declared scope for this question is one chapter, "
                        f"{single}, so the chapter judge was not asked"
                    ),
                    evidence=[], confidence=1.0, alternative_chapter=None,
                )
                skipped.add(question_id)
                slots.append(QuestionSlot(question_id, marks, [
                    Option(single, unit_of(single) or "?", 1.0),
                ]))
                if on_progress is not None:
                    on_progress(done, total)
                continue

        # Retrieval only -- the judge below still reads the real, untouched stem.
        query = retrieval_query_text(stem)
        verdict, evidence, out_of_scope = retrieve(query, q_scope)
        if not evidence:
            if on_progress is not None:
                on_progress(done, total)
            continue
        if options.memory is not None:
            recall = options.memory.recall(stem, exclude=question_id)
            hit = recall.reusable(options.memory_min_similarity)
            reusable = (
                hit is not None and not out_of_scope
                and (not every_label or hit.entry.chapter in every_label or unit_of(hit.entry.chapter))
                and (q_scope is None or hit.entry.chapter in q_scope)
            )
            reused = bool(reusable and options.memory_reuse)
            if options.memory_log is not None:
                options.memory_log[question_id] = {
                    "similarity": recall.best.similarity if recall.best else 0.0,
                    "chapter": hit.entry.chapter if hit is not None else recall.vote,
                    "reusable": bool(reusable), "reused": reused,
                }
            if reused:
                tier = hit.entry.tier if hit.entry.tier in TIERS else None
                judged[question_id] = Classification(
                    chapter=hit.entry.chapter, curriculum_section=hit.entry.section, tier=tier,
                    skill_required="",
                    reasoning=(
                        f"a teacher already placed a near-identical question "
                        f"({hit.similarity:.0%} alike) in {hit.entry.chapter}"
                        + (f", section {hit.entry.section}" if hit.entry.section else "")
                        + ", so neither judge was asked"
                    ),
                    evidence=[], confidence=0.97, alternative_chapter=None,
                )
                skipped.add(question_id)
                slots.append(QuestionSlot(question_id, marks, [
                    Option(hit.entry.chapter, unit_of(hit.entry.chapter) or "?", 0.97),
                ]))
                if on_progress is not None:
                    on_progress(done, total)
                continue
        if options.gate and not out_of_scope:
            def reranked(_verdict=verdict, _stem=stem):
                # the chapter whose passage the reranker scores highest; None when only one
                # chapter was shown (nothing to disagree about) or the call failed -- a
                # reranker outage must never place or refuse a question by itself
                chapters = {c.node_id for c in _verdict.evidence}
                if len(chapters) < 2:
                    return None
                try:
                    scores = options.gate_reranker.scores(
                        retrieval_query_text(_stem), [c.text for c in _verdict.evidence],
                    )
                except Exception:  # noqa: BLE001
                    return None
                best = max(range(len(scores)), key=scores.__getitem__)
                return chapter_of(_verdict.evidence[best].node_id)

            gate = chapter_gate(
                verdict, chapter_of(verdict.node_id), min_relative_margin=options.gate_min_margin,
                reranked=reranked if options.gate_reranker is not None else None,
                remembered=(
                    (lambda r=recall: r.vote if r.unanimous else None)
                    if options.memory is not None else None
                ),
            )
            enforced = options.gate_enforce and gate.passed
            if options.gate_log is not None:
                options.gate_log[question_id] = {
                    "passed": gate.passed, "chapter": gate.chapter,
                    "relative_margin": round(gate.relative_margin, 3),
                    "reason": gate.reason, "enforced": enforced,
                    "retrievers_agreed": bool(verdict.agreed),
                }
            if enforced:
                # Retrieval's two readers agree and lead clearly: nothing for the chapter
                # judge to decide. Placed like a declared single chapter, so the topic
                # judge reads it next and names the tier.
                judged[question_id] = Classification(
                    chapter=gate.chapter, curriculum_section=None, tier=None,
                    skill_required="",
                    reasoning=(
                        f"both retrievers placed this in {gate.chapter} with a "
                        f"{gate.relative_margin:.0%} lead, so the chapter judge was not asked"
                    ),
                    evidence=[], confidence=min(0.9, 0.5 + gate.relative_margin / 2),
                    alternative_chapter=None,
                )
                skipped.add(question_id)
                slots.append(QuestionSlot(question_id, marks, [
                    Option(gate.chapter, unit_of(gate.chapter) or "?", judged[question_id].confidence),
                ]))
                if on_progress is not None:
                    on_progress(done, total)
                continue
        prepared.append((done, question_id, stem, marks, evidence, verdict, q_scope, out_of_scope))

    def scoped_call(item) -> bool:
        """Ask for ScopedClassification: a question confined to a declared scope whose
        retrieval did find something in it."""
        return (
            options.cross_scope and item[1] in declared and item[6] is not None
            and not item[7]
        )

    def demos_for(item) -> list:
        if options.memory is None or not options.memory_demos:
            return []
        shown = options.memory.demonstrations(
            item[2], options.memory_demos, min_similarity=options.memory_demo_min_similarity,
            exclude=item[1],
        )
        if shown and options.memory_log is not None and item[1] in options.memory_log:
            options.memory_log[item[1]]["demos"] = len(shown)
        return shown

    def classify(item):
        # worked examples only when there are some, so a judge that predates them is
        # called exactly as before
        extra = {}
        shown = demos_for(item)
        if shown:
            extra["examples"] = shown
        if scoped_call(item):
            return judge.classify(item[2], item[4], scoped=True, **extra)
        return judge.classify(item[2], item[4], **extra)

    # Phase 2: the judge. A batched judge (see app.llm_batch) is asked every question at
    # once, from one thread each, so the whole paper becomes one batch; a live judge is
    # asked one at a time as before. Either way each answer is handled below in paper
    # order, and one question's failure never sinks the rest.
    calls: dict[str, object] = {}
    if (
        options.group_size > 1 and hasattr(judge, "classify_many")
        and not getattr(judge, "batched", False)
    ):
        eligible = [it for it in prepared if not scoped_call(it)]
        for start in range(0, len(eligible), options.group_size):
            group = eligible[start:start + options.group_size]
            try:
                answers = judge.classify_many([
                    {"question": it[2], "evidence": it[4], "examples": demos_for(it)}
                    for it in group
                ])
            except Exception:  # noqa: BLE001 -- every question in the group is asked alone
                continue
            for it, answer in zip(group, answers, strict=True):
                if not isinstance(answer, Exception):
                    calls[it[1]] = answer
    if getattr(judge, "batched", False) and len(prepared) > 1:
        from concurrent.futures import ThreadPoolExecutor

        def ask(item):
            try:
                return classify(item)
            except Exception as exc:  # noqa: BLE001
                return exc

        with ThreadPoolExecutor(max_workers=min(64, len(prepared))) as pool_:
            for item, outcome in zip(prepared, pool_.map(ask, prepared), strict=True):
                calls[item[1]] = outcome

    for item in prepared:
        done, question_id, stem, marks, evidence, verdict, q_scope, out_of_scope = item
        try:
            call = calls.get(question_id)
            if call is None:
                call = classify(item)
            elif isinstance(call, Exception):
                raise call
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
            failed.add(question_id)
            slots.append(QuestionSlot(question_id, marks, [Option(None, None, 0.0)]))
            if on_progress is not None:
                on_progress(done, total)
            continue

        crossing = options.cross_scope and out_of_scope and question_id in declared
        judged_on = evidence           # the passages the answer kept was given
        if scoped_call(item) and getattr(call, "no_in_scope_chapter", False):
            # The judge says no chapter in the declared scope can answer this question.
            # One more read over the whole group (the indexes hold only this paper's own
            # subject group) -- and if it lands outside the scope, the placement says so.
            query = retrieval_query_text(stem)
            wide = locate(
                query, indexes, depth=EVIDENCE_DEPTH,
                evidence_passages=evidence_passages, evidence_chapters=evidence_chapters,
            )
            wide_evidence = build_evidence(wide, query)
            try:
                second = judge.classify(stem, wide_evidence) if wide_evidence else None
            except Exception:  # noqa: BLE001 -- the in-scope answer stands, flagged
                second = None
            if second is not None and second.chapter is not None and second.chapter not in q_scope:
                call = second.model_copy(update={
                    "reasoning": (
                        "no chapter in the declared scope can answer this question, so it "
                        "was placed outside it and needs a person to confirm. "
                        + second.reasoning
                    )[:600],
                })
                verdict, crossing = wide, True
                q_scope = None
                judged_on = wide_evidence
            elif second is not None and second.chapter in (q_scope or set()):
                call = second
                judged_on = wide_evidence

        if (
            options.recheck and not getattr(judge, "batched", False)
            and call.chapter is not None and not out_of_scope and not crossing
            and call.confidence < options.recheck_below
            and len({e.chapter for e in judged_on}) > 1
        ):
            call = _recheck(call, stem, judged_on, judge, options, question_id)

        if crossing:
            crossed.add(question_id)
        if options.memory_log is not None and question_id in options.memory_log:
            options.memory_log[question_id]["judge_chapter"] = call.chapter
        if options.gate_log is not None and question_id in options.gate_log:
            options.gate_log[question_id]["judge_chapter"] = call.chapter
        if asked is not None:
            asked[question_id] = (call.confidence, len({e.chapter for e in judged_on}))

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
            options_ = [Option(None, None, confidence)]
        else:
            options_ = [Option(call.chapter, unit_of(call.chapter) or "?", confidence)]
            seen = {call.chapter}
            for node, _ in verdict.runners_up:
                name = chapter_of(node)
                if q_scope is not None and not out_of_scope and name not in q_scope:
                    continue
                if name and name not in seen:
                    seen.add(name)
                    options_.append(
                        Option(name, unit_of(name) or "?", max(0.05, call.confidence * 0.4))
                    )
            if call.alternative_chapter and call.alternative_chapter not in seen:
                if q_scope is None or out_of_scope or call.alternative_chapter in q_scope:
                    options_.append(
                        Option(
                            call.alternative_chapter,
                            unit_of(call.alternative_chapter) or "?",
                            call.confidence * 0.8,
                        )
                    )

        slots.append(QuestionSlot(question_id, marks, options_))
        if on_progress is not None:
            on_progress(done, total)

    return slots, judged, failed, crossed, skipped


def _reordered(evidence: list[Evidence], k: int) -> list[Evidence]:
    """The passages in a different order: reversed for the first re-ask, then rotated."""
    if k == 0:
        return list(reversed(evidence))
    shift = max(1, len(evidence) // 2) * k
    return evidence[shift % len(evidence):] + evidence[: shift % len(evidence)]


def _recheck(call: Classification, stem: str, evidence: list[Evidence], judge,
             options: PassOptions, question_id: str) -> Classification:
    """Self-consistency by perturbation, for one low-confidence answer.

    The chapter judge is asked again ``recheck_n`` times with the passages reordered. The
    majority chapter stands; an answer nobody repeats is capped below the review threshold so
    a person looks at it, and one that every re-ask repeats is left exactly as it was. A
    re-ask that fails is no vote.
    """
    votes = [call.chapter]
    answers = {call.chapter: call}
    for k in range(options.recheck_n):
        try:
            again = judge.classify(stem, _reordered(evidence, k))
        except Exception:  # noqa: BLE001
            continue
        votes.append(again.chapter)
        answers.setdefault(again.chapter, again)
    tally: dict = {}
    for v in votes:
        tally[v] = tally.get(v, 0) + 1
    top, count = max(tally.items(), key=lambda kv: (kv[1], kv[0] == call.chapter))
    changed = top != call.chapter
    if len(votes) == 1:
        result = call                       # no re-ask answered: nothing learnt
    elif count >= 2 and len(tally) == 1:
        result = call                       # unanimous
    elif count >= 2:
        result = answers[top] if changed else call
    else:
        result = call.model_copy(update={"confidence": min(call.confidence, 0.4)})
    if options.recheck_log is not None:
        options.recheck_log[question_id] = {
            "votes": votes, "changed": changed, "unstable": len(tally) > 1,
        }
    return result


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
    options: PassOptions | None = None,
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

    import dataclasses

    options = options or PassOptions()
    first_options = dataclasses.replace(options, scope_declared=scope is not None)
    asked: dict[str, tuple[float, int]] = {}
    slots, judged, failed, crossed, skipped = _pass(
        questions, indexes, judge, chapter_of, unit_of, section_of, scope,
        evidence_passages, evidence_chapters, passage_chars, on_progress, scope_of,
        first_options, asked,
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
            asked = {}
            slots, judged, failed, crossed, skipped = _pass(
                questions, indexes, judge, chapter_of, unit_of, section_of,
                inferred.chapters, evidence_passages, evidence_chapters, passage_chars,
                on_progress, scope_of,
                # an inferred scope is not a declaration: only a question's own declared
                # scope may skip the judge or make a placement cross-scope
                dataclasses.replace(options, scope_declared=False),
                asked,
            )
            scope_source = "inferred"

    gated = {
        qid for qid, entry in (options.gate_log or {}).items() if entry.get("enforced")
    } & skipped

    memorised = {
        qid for qid, entry in (options.memory_log or {}).items() if entry.get("reused")
    } & skipped

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
            judge_failed=slot.question_id in failed,
            cross_scope=slot.question_id in crossed,
            chapter_judge_skipped=slot.question_id in skipped,
            chapter_gated=slot.question_id in gated,
            memory_reused=slot.question_id in memorised,
            judge_confidence=asked.get(slot.question_id, (None, 0))[0],
            chapters_shown=asked.get(slot.question_id, (None, 0))[1],
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


def reclassify_without_scope(
    question_id: str,
    stem: str,
    marks: float,
    indexes: list,
    judge,
    *,
    chapter_of,
    unit_of,
    section_of,
    evidence_passages: int = EVIDENCE_DEPTH,
    evidence_chapters: int = 1,
    passage_chars: int = DEFAULT_PASSAGE_CHARS,
) -> PlacedQuestion | None:
    """One question read by the chapter judge over every chapter ``indexes`` hold (the
    paper's own subject group), with no declared scope. Used when a question was confined
    to a single chapter, its chapter judge skipped, and the topic judge then found that no
    section of that chapter can answer it (cross_scope_fallback). None when nothing was
    retrieved or the judge could not be asked."""
    asked: dict[str, tuple[float, int]] = {}
    slots, judged, failed, _, _ = _pass(
        [(question_id, stem, marks)], indexes, judge, chapter_of, unit_of, section_of,
        None, evidence_passages, evidence_chapters, passage_chars, asked=asked,
    )
    if not slots or question_id in failed:
        return None
    call = judged[question_id]
    option = slots[0].options[0]
    return PlacedQuestion(
        question_id=question_id, marks=marks, chapter=call.chapter,
        board_unit=option.board_unit if call.chapter is not None else None,
        curriculum_section=call.curriculum_section, tier=call.tier,
        skill_required=call.skill_required, confidence=call.confidence,
        reasoning=call.reasoning, evidence=list(call.evidence),
        judge_confidence=asked.get(question_id, (None, 0))[0],
        chapters_shown=asked.get(question_id, (None, 0))[1],
    )
