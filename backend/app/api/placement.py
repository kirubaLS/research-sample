"""Place a paper's questions, and let a person settle the ones that need settling.

Placement is a proposal. The routes here are what turn a proposal into a fact: a paper is
tagged once, reviewed once, and then correct for every student who sat it and every re-run
of the analysis. That is where full accuracy comes from -- not from a model that is never
wrong, but from one that is never confidently wrong and hands the rest over.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.books import clean_sections
from app.api.deps import require_admin, require_paper_scope, require_reader, require_scanner
from app.classify.pipeline import place_paper
from app.curriculum import group_subjects
from app.mapping.auto_resolve import record_family_section, resolve_blocked_family
from app.mapping.family import Choice, choose_family
from app.llm import estimate_usd
from app.mapping.topic_node import section_headings, set_question_topic
from app.config import get_settings
from app.db import get_session
from app.ingest.probe import LexicalIndex, SemanticIndex, content_chunks
from app.models import (
    Assessment,
    BookChunk,
    ConceptFamilyProposal,
    PlacementJob,
    Question,
    QuestionPlacement,
    QuestionTier,
    ScannedQuestion,
    School,
    TaxonomyNode,
)
from app.models.assessment import TIER_ALIASES, TIERS, tier_code

router = APIRouter(prefix="/assessments", tags=["placement"])


class ScopeIn(BaseModel):
    """What this paper covers. One field, and it is the constraint daily tests run on."""

    chapters: list[str] = Field(
        min_length=1,
        description="Chapter codes, e.g. ['X.MATH.REAL', 'X.MATH.POLY']",
    )


class ConfirmIn(BaseModel):
    chapter_code: str
    curriculum_section: str | None = None
    #: which concept family (topic within the chapter) this question actually belongs
    #: to -- see review_queue's own `candidate_families` for what a chapter offers.
    #: Optional because plenty of reviews are only ever about the chapter or the tier;
    #: required to actually fix a question `choose_family` left blocked or misfiled,
    #: which chapter_code alone cannot touch (see confirm()'s own docstring).
    family_code: str | None = None
    tier: str | None = None
    reviewed_by: str = Field(max_length=64)


def _assessment(db: Session, school: School, assessment_id: str) -> Assessment:
    a = db.get(Assessment, assessment_id)
    if a is None or a.school_id != school.id:
        raise HTTPException(404, "not found")
    return a


@router.put("/{assessment_id}/scope")
def set_scope(
    assessment_id: str,
    body: ScopeIn,
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    """Declare which chapters this test covers.

    Most papers are daily or cyclic tests with no published weightage, and this is the
    strongest constraint they have. Setting it before placement is worth far more than
    correcting placements afterwards.
    """
    a = _assessment(db, school, assessment_id)
    known = {
        n.code
        for n in db.scalars(
            select(TaxonomyNode).where(
                TaxonomyNode.kind == "chapter", TaxonomyNode.code.in_(body.chapters)
            )
        )
    }
    unknown = sorted(set(body.chapters) - known)
    if unknown:
        raise HTTPException(422, f"not chapters in the taxonomy: {unknown}")

    a.syllabus_scope = sorted(known)
    db.commit()
    return {"assessment_id": a.id, "scope": a.syllabus_scope, "chapters": len(known)}


def _finish_placement_job(
    job_id: str, *, status_value: str, result: dict | None = None,
    error_status: int | None = None, error_detail: str | None = None,
) -> None:
    """Write a job's outcome in its own short-lived session -- see _run_placement_job's
    docstring for why a session is never held open across the classifier calls
    themselves."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        job = db.get(PlacementJob, job_id)
        if job is None:
            return
        job.status = status_value
        job.result = result
        job.error_status = error_status
        job.error_detail = error_detail
        job.finished_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def _report_placement_progress(job_id: str, done: int, total: int) -> None:
    """Commit one question's worth of real progress -- called from inside place_paper's
    (really _pass's) sequential per-question loop, after each judge.classify() call
    returns. A short-lived session of its own, opened and closed just for this write, the
    same discipline _run_placement_job's own docstring gives for the read and write
    phases either side of the classifier calls -- this fires *during* those calls,
    potentially forty times, not just once after them.

    Never raises: a failure writing progress is not a failure of the classification
    itself, and must not abort a run that is otherwise succeeding just because one
    progress commit could not land.
    """
    from app.db import SessionLocal

    try:
        db = SessionLocal()
        try:
            job = db.get(PlacementJob, job_id)
            if job is not None:
                job.progress_done = done
                job.progress_total = total
                db.commit()
        finally:
            db.close()
    except Exception:  # noqa: BLE001 -- a progress write must never sink the real run
        pass


def _run_placement_job(job_id: str) -> None:  # noqa: PLR0915 -- one linear run, not worth splitting
    """The slow part of placement, run after the request that queued it has already
    returned.

    Two short-lived sessions, never one held open across the classifier calls: the same
    lesson GridSheetJob's own docstring gives -- a session kept open while ~40 sequential
    Anthropic calls run sits idle-in-transaction for however long that takes, and Postgres
    enforces its own idle-in-transaction timeout regardless of what this process is doing.
    Unlike a grid sheet's clean split, placement needs the database again afterwards (to
    write every QuestionPlacement and QuestionTier row), so this is three phases, not two:
    read what the classifier needs, close the session, call it, then a fresh session to
    write what it decided.

    Never raises: every failure is caught and written to the job row, because that row is
    the only place left a failure can be seen once the request that would have shown it
    has already returned.
    """
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        job = db.get(PlacementJob, job_id)
        if job is None:
            return
        a = db.get(Assessment, job.assessment_id)
        if a is None:
            _finish_placement_job(
                job_id, status_value="failed", error_status=404,
                error_detail="the paper this job belonged to was removed",
            )
            return
        settings = get_settings()

        questions = db.scalars(
            select(Question).where(Question.assessment_id == a.id).order_by(Question.address)
        ).all()
        # A sub-question of a source-based question ("State one way public libraries
        # widened access") is unplaceable on its own words -- the passage it is about was
        # scanned as a separate context row and never became a Question. Hand the judge
        # (and retrieval) the passage together with the sub-question, exactly as the
        # student had them on the page. The stored stem is untouched.
        from app.extraction.paper import context_addresses

        staged = db.scalars(
            select(ScannedQuestion).where(ScannedQuestion.assessment_id == a.id)
        ).all()
        context_rows = context_addresses(staged)
        passage_of: dict[tuple[str | None, str], str] = {
            (r.section, r.question_no): r.stem_text.strip()
            for r in staged if r.address in context_rows and (r.stem_text or "").strip()
        }

        def judge_text(q: Question) -> str:
            text = q.stem_text or ""
            passage = passage_of.get((q.section, q.question_no)) if q.sub_part else None
            if passage and passage not in text:
                return f"{passage}\n\nQUESTION ON THE PASSAGE ABOVE:\n{text}"
            return text

        stems = [(q.id, judge_text(q), float(q.max_marks)) for q in questions if q.stem_text]
        stem_by_id = {qid: text for qid, text, _ in stems}
        if not stems:
            _finish_placement_job(
                job_id, status_value="failed", error_status=409,
                error_detail=(
                    "no question text to work from. Placement reads the stems; add them "
                    "with the questions, or run the paper through recognition first."
                ),
            )
            return
        if not settings.anthropic_api_key:
            _finish_placement_job(
                job_id, status_value="failed", error_status=409,
                error_detail=(
                    "no classifier key configured. Set YAADHUM_ANTHROPIC_API_KEY. "
                    "Retrieval alone cannot tell a question about a theorem from the "
                    "theorem, so placement without it would need reviewing question by "
                    "question."
                ),
            )
            return

        book_subject_codes = group_subjects(a.subject_code)
        chunks = db.scalars(
            select(BookChunk).where(BookChunk.subject_code.in_(book_subject_codes))
        ).all()
        if not chunks:
            _finish_placement_job(
                job_id, status_value="failed", error_status=409,
                error_detail=f"no book loaded for {a.subject_code}",
            )
            return

        nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
        chapter_ids = _chapters_in_subjects(nodes, book_subject_codes)
        by_label = {
            n.label: n for n in nodes.values()
            if n.kind == "chapter" and n.id in chapter_ids
        }
        unit_by_chapter = _chapter_to_unit(db, nodes, chapter_ids)

        # Exercise-bucket chunks (bucket='E') carry no section_number (see
        # import_book_map.py) and only share surface vocabulary with a question, not
        # what it's actually about -- left in the pool that decides chapter/section, an
        # exercise chunk can beat the real teaching-text passage and produce a topicless
        # placement. A bare pie-chart-legend fragment fails the same way (see
        # content_chunks). Excluded from retrieval only; `chunks` itself (used for
        # known_sections below) is untouched.
        retrieval_chunks = content_chunks(chunks)
        indexes: list = [LexicalIndex(retrieval_chunks)]
        if settings.jina_api_key and any(c.embedding for c in retrieval_chunks):
            from app.ingest.jina import JinaEmbedder

            indexes.append(SemanticIndex(retrieval_chunks, JinaEmbedder(
                settings.jina_api_key, model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
            )))

        # The sections the book ingest actually extracted, so an invented "12.9" is
        # caught rather than stored. Without this the section is unverifiable and gets
        # dropped -- an unverified value must never read as a verified one.
        known_sections: dict[str, set[str]] = {}
        for node in nodes.values():
            if node.kind != "subtopic":
                continue
            parent = nodes.get(node.parent_id)
            if parent is None or parent.kind != "chapter" or parent.id not in chapter_ids:
                continue
            # codes look like X.MATH.SAV.S12_2 -- the section number is the tail
            tail = node.code.rsplit(".", 1)[-1]
            if tail.startswith("S") and "_" in tail:
                known_sections.setdefault(parent.label, set()).add(tail[1:].replace("_", "."))
        # The book_map import (app.scripts.import_book_map) never creates "subtopic"
        # nodes -- it writes section numbers straight onto BookChunk.section_number
        # instead. Without this, every chapter imported that way (X.HIST/GEO/POL/ECO)
        # has an empty known_sections entry, so ground() strips a genuinely correct
        # curriculum_section from every question in those subjects, unconditionally.
        for c in chunks:
            if not c.section_number or c.node_id not in chapter_ids:
                continue
            chapter_node = nodes.get(c.node_id)
            if chapter_node is not None:
                known_sections.setdefault(chapter_node.label, set()).add(c.section_number)

        from app.classify.anthropic_judge import AnthropicJudge

        batch_options = {
            "linger": settings.batch_linger_seconds, "poll": settings.batch_poll_seconds,
            "max_wait": settings.batch_max_wait_seconds,
        }
        judge = AnthropicJudge(
            settings.anthropic_api_key,
            model=settings.model_classifier,
            known_sections=known_sections or None,
            effort=settings.model_effort,
            passage_chars=settings.classifier_passage_chars,
            batched=settings.batch_classify and settings.batch_chapter_judge,
            batch_options=batch_options,
        )

        scope = None
        if a.syllabus_scope:
            scope = {nodes[n.id].label for n in by_label.values() if n.code in a.syllabus_scope}

        # A Social Science paper's sections are fixed by board convention (A History,
        # B Geography, C Political Science, D Economics -- see marks._SST_SECTION_SUBJECT),
        # so a Section B question is never offered a Political Science chapter, however
        # well one of its passages happens to match. The same narrowing map_paper already
        # applies; classify used to search the whole group and could land a Geography
        # question in Manufacturing Industries.
        from app.api.marks import _SST_SECTION_SUBJECT
        from app.curriculum import CURRICULA

        subject_curriculum = CURRICULA.get(a.subject_code)
        group_code = subject_curriculum.group_code if subject_curriculum else a.subject_code
        own_scope: dict[str, set[str]] = {}
        if group_code == "X.SST":
            labels_of_subject = {
                code: {nodes[i].label for i in _chapters_in_subjects(nodes, [code])}
                for code in book_subject_codes
            }
            for q in questions:
                subject = _SST_SECTION_SUBJECT.get((q.section or "").strip().upper())
                if subject and labels_of_subject.get(subject):
                    own_scope[q.id] = labels_of_subject[subject]

        # The closed set the topic judge chooses from, per chapter: every section the
        # book has for it, with its heading.
        headings_of = {
            node.id: section_headings(chunks, node, nodes) for node in by_label.values()
        }
        embedder = None
        if settings.jina_api_key and any(c.embedding for c in retrieval_chunks):
            from app.ingest.jina import JinaEmbedder

            embedder = JinaEmbedder(
                settings.jina_api_key, model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
            )
        from app.classify.topic import TopicJudge, choose_topic

        try:
            topic_judge = TopicJudge(
                settings.anthropic_api_key, settings.model_classifier,
                effort=settings.model_effort, passage_chars=settings.classifier_passage_chars,
                batched=settings.batch_classify, batch_options=batch_options,
            )
        except Exception:  # noqa: BLE001 -- retrieval within the chapter still decides
            topic_judge = None

        families: dict[str, list[TaxonomyNode]] = {}
        for node in nodes.values():
            if node.kind == "concept_family" and node.parent_id:
                families.setdefault(node.parent_id, []).append(node)
        sections_of = {
            row.code: set(clean_sections(row.from_sections))
            for row in db.scalars(select(ConceptFamilyProposal).where(
                ConceptFamilyProposal.subject_code.in_(book_subject_codes)
            ))
        }
        declared = (a.declared or {}).get("board_units")
        paper_kind, subject_code, assessment_id = a.paper_kind, a.subject_code, a.id
    finally:
        db.close()  # released BEFORE the slow classifier calls below, not held across it

    _report_placement_progress(job_id, 0, len(stems))

    # A group paper's retrieval pool is every book in the group at once (X.SST's four
    # books together), not one -- so the fixed per-book candidate count starves a question
    # whose true chapter is a weak lexical/semantic match (a short factual stem like "An
    # oil field located in Gujarat" barely resembles its own chapter's prose) of ever being
    # shown to the judge at all among just the setting's default handful of chapters, once
    # that handful is being chosen from every chapter of every book in the group combined.
    # Widened in proportion to how many books are actually in play, capped so a large group
    # does not multiply the token cost unboundedly.
    evidence_chapters = min(
        settings.classifier_evidence_chapters * len(book_subject_codes),
        3 * settings.classifier_evidence_chapters,
    )

    try:
        result = place_paper(
            stems, indexes, judge,
            # What the reader is shown, and so what the run costs. Both from settings.
            evidence_passages=settings.classifier_evidence_passages,
            evidence_chapters=evidence_chapters,
            passage_chars=settings.classifier_passage_chars,
            chapter_of=lambda nid: nodes[nid].label if nid in nodes else None,
            unit_of=lambda label: unit_by_chapter.get(label),
            section_of=lambda ref: None,
            declared=declared,
            scope=scope,
            on_progress=lambda done, total: _report_placement_progress(job_id, done, total),
            scope_of=own_scope.get,
        )
    except Exception as exc:  # noqa: BLE001 -- see docstring: this must never escape
        _finish_placement_job(
            job_id, status_value="failed", error_status=502,
            error_detail=f"classification failed ({type(exc).__name__}: {exc})",
        )
        return

    # The judge could not be asked for ANY question: not a judgment about the paper but
    # an outage (an API refusal, exhausted credit, a dead network), and writing it as
    # seventy "no chapter" placements would erase every chapter the map step found.
    # The job fails instead, naming the cause, and the paper stays as mapped.
    if result.questions and all(q.judge_failed for q in result.questions):
        _finish_placement_job(
            job_id, status_value="failed", error_status=502,
            error_detail=(
                "the reading model could not be asked for any question, so nothing was "
                f"changed: {result.questions[0].reasoning}"
            ),
        )
        return

    # The topic, decided once the chapter is final (the blueprint may have moved it),
    # from the closed set of that chapter's own sections. Still outside any database
    # session: this is one more model call per question.
    topic_picks: dict[str, object] = {}
    from app.classify.topic import topic_lexical_index

    # built once: a tokenisation of the whole book, which every question used to repeat
    topic_index = topic_lexical_index(retrieval_chunks)

    def pick_topic(placed):
        chapter_node = by_label.get(placed.chapter)
        return choose_topic(
            stem_by_id.get(placed.question_id, ""), chapter_node.id, chapter_node.label,
            retrieval_chunks, headings_of.get(chapter_node.id, {}), topic_judge,
            fallback_section=placed.curriculum_section,
            embedder=embedder,
            evidence_passages=settings.classifier_evidence_passages,
            passage_chars=settings.classifier_passage_chars,
            lexical_index=topic_index,
        )

    to_pick = [
        placed for placed in result.questions
        if placed.chapter is not None and by_label.get(placed.chapter) is not None
    ]
    if getattr(topic_judge, "batched", False) and len(to_pick) > 1:
        # One thread per question so every question's read joins the same batch, and
        # the chapter's reads, confirms and checks become one batch per round rather
        # than one live call each -- see app.llm_batch.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(64, len(to_pick))) as pool:
            for placed, pick in zip(to_pick, pool.map(pick_topic, to_pick), strict=True):
                topic_picks[placed.question_id] = pick
    else:
        for placed in to_pick:
            topic_picks[placed.question_id] = pick_topic(placed)

    db = SessionLocal()
    try:
        settled, unsettled, refused = 0, 0, []
        for placed in result.questions:
            chapter = by_label.get(placed.chapter) if placed.chapter is not None else None
            unit_id = _unit_node_id(db, nodes, placed.board_unit) if placed.board_unit else None
            question = db.get(Question, placed.question_id)

            # The judge reads the passages retrieval found and can tell a question ABOUT
            # a theorem from the theorem, which is the whole reason it exists. Its answer
            # used to be written only as a placement, while every report prefers what the
            # question itself carries -- so the correction was recorded and then ignored.
            # It settles the question now, exactly as a teacher's correction does, and the
            # mapping step's attempt stays in the placement history.
            choice = Choice(None)
            auto_resolved: str | None = None
            pick = topic_picks.get(placed.question_id)
            if pick is not None and pick.section is not None:
                import dataclasses

                placed = dataclasses.replace(placed, curriculum_section=pick.section)
            if question is not None and placed.judge_failed:
                # The judge could not be asked for this one question. That is not a
                # finding about the question, so what the map step decided -- chapter,
                # section, topic, family -- stays exactly as it is; only a placement row
                # records the failure, flagged, so a person can re-run or settle it.
                import dataclasses

                kept = nodes.get(question.chapter_id) if question.chapter_id else None
                chapter = kept
                placed = dataclasses.replace(
                    placed, chapter=kept.label if kept else None,
                    curriculum_section=question.curriculum_section,
                    needs_review=True,
                )
            elif question is not None and placed.chapter is None:
                # Skill-anchored: the judge confidently said this question has no chapter,
                # and the question record should say the same rather than keep whatever
                # placeholder chapter it was seeded with. concept_family_id and
                # board_unit_id are left as they are -- Question requires both non-null
                # (see the model's own comments), and a skill-anchored question genuinely
                # has neither a family nor a board unit to report against, so there is
                # nothing here that would improve on the placeholder.
                question.chapter_id = None
                question.curriculum_section = None
                if placed.skill_required:
                    question.skill_required = placed.skill_required
                settled += 1
            elif question is not None and chapter is not None:
                choice = choose_family(
                    families.get(chapter.id, []), sections_of,
                    placed.curriculum_section, chapter.label,
                    prefer_label=pick.heading if pick is not None else None,
                )
                if choice.family is None and choice.blocked is not None:
                    # The mapping step already tries this same auto-resolve (see
                    # marks.py's map_paper) -- classify re-derives choose_family from
                    # scratch here, against the judge's OWN curriculum_section, which is
                    # frequently None even for a question mapping placed cleanly (the
                    # judge is not asked to name a section the way retrieval's own
                    # locate() is). Without this, a chapter with several families read as
                    # newly "blocked" on every single classify run for any subject where
                    # section detection is unreliable, silently overwriting a perfectly
                    # good mapping-time placement with a confusing "settle it in review"
                    # message and needs_review=True -- observed in production across an
                    # entire paper's worth of otherwise cleanly-placed questions.
                    resolution = resolve_blocked_family(
                        db,
                        api_key=settings.anthropic_api_key,
                        model=settings.model_classifier,
                        effort=settings.model_effort,
                        subject_codes=book_subject_codes,
                        section=placed.curriculum_section,
                        stem_text=question.stem_text,
                        chapter=chapter,
                        candidates=families.get(chapter.id, []),
                        jina_api_key=settings.jina_api_key,
                        embedding_model=settings.embedding_model,
                        embedding_dimensions=settings.embedding_dimensions,
                    )
                    if resolution is not None:
                        choice = Choice(resolution.family)
                        auto_resolved = f"[{resolution.grounded_in}] {resolution.rationale}"
                        # The section auto_resolve itself found (the exact section's own
                        # text, or whichever real passage the chapter-wide search actually
                        # quoted) -- not the judge's, which is exactly what was missing.
                        import dataclasses

                        placed = dataclasses.replace(
                            placed,
                            curriculum_section=placed.curriculum_section or resolution.book_section,
                        )
                if choice.family is not None:
                    question.concept_family_id = choice.family.id
                    # Question's own check constraint (ck_question_chapter_pairing) is
                    # chapter_id and curriculum_section together or neither -- a chapter
                    # with no section to pair it with is filed under nothing rather than
                    # half the pair the constraint forbids. concept_family_id above still
                    # gets recorded either way: it carries no such pairing rule, and a
                    # question's family is exactly the fact this whole path exists to fix.
                    if placed.curriculum_section is not None:
                        question.chapter_id = chapter.id
                        question.curriculum_section = placed.curriculum_section
                        if unit_id:
                            question.board_unit_id = unit_id
                        # The Topic column reads QuestionSkill, so the section decided
                        # here has to be written there too, or the column keeps showing
                        # the retrieval-time guess from map forever.
                        heading = (
                            pick.heading if pick is not None and pick.section == placed.curriculum_section
                            else None
                        ) or headings_of.get(chapter.id, {}).get(placed.curriculum_section)
                        set_question_topic(
                            db, question.id, chapter, placed.curriculum_section,
                            heading or placed.curriculum_section,
                            source="classify", confidence=placed.confidence,
                            secondaries=(
                                pick.secondaries
                                if pick is not None and pick.section == placed.curriculum_section
                                else ()
                            ),
                        )
                    settled += 1
                    if choice.unsettled:
                        unsettled += 1
                else:
                    # The chapter changed to one whose families cannot place this
                    # question. Leaving the old family in place would file the marks
                    # under a chapter the judge has just said is the wrong one.
                    refused.append(placed.question_id)
                if placed.skill_required:
                    question.skill_required = placed.skill_required

            # Both rows carry a hard FK onto question.id -- a question deleted (the paper
            # itself removed) between this job's slow classifier call and this write
            # would otherwise still get a placement/tier row inserted for it here,
            # landing in the exact window a concurrent delete_assessment's own cleanup
            # already swept, and failing that delete outright with a foreign key
            # violation on whichever table it reaches next. Skipped rather than raised:
            # a question that no longer exists has nothing left to record a judgment
            # about.
            if question is None:
                continue

            db.add(QuestionPlacement(
                question_id=placed.question_id,
                chapter_id=chapter.id if chapter else None,
                board_unit_id=unit_id,
                curriculum_section=placed.curriculum_section,
                tier=placed.tier,
                skill_required=placed.skill_required,
                confidence=placed.confidence,
                source="blueprint" if placed.overruled else "model",
                needs_review=(
                    placed.needs_review
                    or (pick is not None and pick.section is not None and not pick.agreed)
                    or choice.unsettled is not None
                    or choice.blocked is not None
                    # a family auto-resolved from a section the topic judge settled is
                    # not a doubt about the topic; only an unsettled section still is
                    or (auto_resolved is not None and not (pick is not None and pick.agreed))
                ),
                reasoning=" ".join(filter(None, [
                    placed.reasoning,
                    (
                        f"Topic {pick.section} ({pick.heading}): {pick.rationale}"
                        if pick is not None and pick.section is not None else None
                    ),
                    choice.unsettled, choice.blocked,
                    f"Auto-resolved: {auto_resolved}" if auto_resolved else None,
                ])),
                evidence=placed.evidence,
                candidates=[placed.chapter] if placed.chapter is not None else [],
            ))
            # The tier belongs on its own append-only row too. Reports read it from
            # there, so writing it only onto the placement meant the judge decided the
            # cognitive tier of every question and no report ever saw one.
            db.add(QuestionTier(
                question_id=placed.question_id,
                tier=tier_code(placed.tier),
                confidence=placed.confidence,
                source="ensemble",
                model_version=settings.model_classifier,
                rationale=placed.reasoning,
            ))
        db.commit()

        # The judge may have moved questions between families, and on a board paper that
        # is a change to the evidence the frequency table rests on.
        frequency = None
        if paper_kind == "board" and settled:
            from app.curriculum.board_frequency import recompute as recompute_frequency
            from app.curriculum.board_frequency import stream_of

            a = db.get(Assessment, assessment_id)
            frequency = recompute_frequency(db, subject_code, stream=stream_of(a))

        response = {
            "assessment_id": assessment_id,
            "placed": len(result.questions),
            "board_frequency": frequency,
            #: questions whose chapter, topic and sub-topic the judge settled on the
            #: question itself, which is what every report reads
            "labelled": settled,
            #: settled, but more than one family had an equal claim on the section
            "unsettled_family": unsettled,
            #: the judge moved the question to a chapter whose families cannot place it,
            #: so the old family was left rather than filed under a chapter it was just
            #: told is the wrong one
            "family_refused": len(refused),
            "tiers": sum(1 for q in result.questions if tier_code(q.tier)),
            #: What this run actually cost, in tokens, read back off the responses. Not
            #: an estimate: every figure anybody has quoted for a paper so far was
            #: arithmetic on a guess about the prompt, and the two differed by more than
            #: double.
            "spend": {
                "model": settings.model_classifier,
                "effort": settings.model_effort,
                "calls": getattr(judge, "calls", 0) + getattr(topic_judge, "calls", 0),
                "input_tokens": (
                    getattr(judge, "input_tokens", 0) + getattr(topic_judge, "input_tokens", 0)
                ),
                "output_tokens": (
                    getattr(judge, "output_tokens", 0) + getattr(topic_judge, "output_tokens", 0)
                ),
                #: chapter text served from the prompt cache rather than paid for again
                "cache_read_tokens": (
                    getattr(judge, "cache_read_tokens", 0)
                    + getattr(topic_judge, "cache_read_tokens", 0)
                ),
                "passages_shown": settings.classifier_evidence_passages,
                "chapters_shown": evidence_chapters,
                "batched": settings.batch_classify,
                #: from the token counts above and the model's list price -- an estimate
                #: of the bill, not the bill; each judge at the rate it actually ran at
                "estimated_usd": round(
                    estimate_usd(
                        settings.model_classifier,
                        getattr(judge, "input_tokens", 0), getattr(judge, "output_tokens", 0),
                        getattr(judge, "cache_read_tokens", 0),
                        batched=bool(getattr(judge, "batched", False)),
                    )
                    + estimate_usd(
                        settings.model_classifier,
                        getattr(topic_judge, "input_tokens", 0), getattr(topic_judge, "output_tokens", 0),
                        getattr(topic_judge, "cache_read_tokens", 0),
                        batched=bool(getattr(topic_judge, "batched", False)),
                    ),
                    4,
                ),
            },
            "settled": result.settled,
            "needs_review": result.reviewed_count,
            "blueprint_feasible": result.feasible,
            "note": result.note,
            # How often the knowledge base had to correct the model. A rising number is
            # the signal that the next paper cannot be trusted to it unattended.
            "grounding_violations": [
                {"question": q, "problems": v} for q, v in getattr(judge, "violations", [])
            ],
            "scope_source": result.scope_source,
            "scope": {
                "chapters": sorted(result.scope.chapters),
                "rejected": result.scope.rejected,
                "tally": result.scope.tally,
                "confident": result.scope.confident,
                "note": result.scope.note,
            } if result.scope else None,
        }
    except Exception as exc:  # noqa: BLE001 -- see docstring: this must never escape
        _finish_placement_job(
            job_id, status_value="failed", error_status=500,
            error_detail=f"{type(exc).__name__}: {exc}",
        )
        return
    finally:
        db.close()

    _finish_placement_job(job_id, status_value="succeeded", result=response)


@router.post("/{assessment_id}/place", status_code=status.HTTP_202_ACCEPTED)
def place(
    assessment_id: str,
    background_tasks: BackgroundTasks,
    # The same permission as reading a paper and mapping it: this is a step of that flow,
    # and an admin-only step in the middle of it is a wall a principal cannot get past.
    # A teacher reaches it too, subject-scoped like every other paper-authoring step.
    school: School = Depends(require_paper_scope),
    db: Session = Depends(get_session),
) -> JSONResponse:
    """Queue retrieval, the judge and the constraints over every question in the paper.

    A classifier call per question -- around forty for an ordinary paper -- is a request
    this cannot answer synchronously (see PlacementJob's docstring), so this only queues
    the work and returns a job id; poll GET .../place/jobs/{job_id} for the result this
    endpoint used to return directly. The quick checks below (question text exists, a
    classifier key is configured, a book is loaded) still run inline: each is a fast,
    local read, and failing them here means the person who clicked Classify learns why in
    the same second, rather than after a job that was doomed from the start.
    """
    settings = get_settings()
    a = _assessment(db, school, assessment_id)

    has_stems = db.scalar(
        select(Question.id).where(
            Question.assessment_id == a.id, Question.stem_text.is_not(None)
        ).limit(1)
    )
    if not has_stems:
        raise HTTPException(
            409,
            "no question text to work from. Placement reads the stems; add them with the "
            "questions, or run the paper through recognition first.",
        )
    if not settings.anthropic_api_key:
        raise HTTPException(
            409,
            "no classifier key configured. Set YAADHUM_ANTHROPIC_API_KEY. Retrieval alone "
            "cannot tell a question about a theorem from the theorem, so placement without "
            "it would need reviewing question by question.",
        )
    has_book = db.scalar(
        select(BookChunk.id)
        .where(BookChunk.subject_code.in_(group_subjects(a.subject_code)))
        .limit(1)
    )
    if not has_book:
        raise HTTPException(409, f"no book loaded for {a.subject_code}")

    # One classify job per paper at a time -- see marks.running_job for why.
    from app.api.marks import running_job

    running = running_job(db, a.id, "place")
    if running is not None:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "job_id": running.id, "status": "pending", "already_running": True,
                "next": f"Poll GET /assessments/{a.id}/place/jobs/{running.id} for the result.",
            },
        )
    job = PlacementJob(school_id=school.id, assessment_id=a.id)
    db.add(job)
    db.commit()
    background_tasks.add_task(_run_placement_job, job.id)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "job_id": job.id, "status": "pending",
            "next": f"Poll GET /assessments/{a.id}/place/jobs/{job.id} for the result.",
        },
    )


@router.get("/{assessment_id}/place/jobs/{job_id}")
def get_placement_job(
    assessment_id: str,
    job_id: str,
    school: School = Depends(require_paper_scope),
    db: Session = Depends(get_session),
) -> dict:
    """Poll for the result of a queued placement run -- see place() and PlacementJob. A
    failed job carries the same status code and detail a synchronous run would have
    raised, not a bare 'failed'."""
    job = db.get(PlacementJob, job_id)
    if job is None or job.assessment_id != assessment_id or job.school_id != school.id:
        raise HTTPException(404, f"no job {job_id!r} for this paper")
    if job.status == "failed":
        raise HTTPException(job.error_status or 500, job.error_detail or "the job failed")
    if job.status != "succeeded":
        return {
            "job_id": job.id, "status": job.status,
            "progress_done": job.progress_done, "progress_total": job.progress_total,
        }
    return {
        "job_id": job.id, "status": "succeeded",
        "progress_done": job.progress_done, "progress_total": job.progress_total,
        **(job.result or {}),
    }


def _chapters_in_subjects(nodes: dict, subject_codes: list[str]) -> set[str]:
    """Every chapter node whose parent chain reaches a subject node in ``subject_codes``.

    Two different books can share an identical chapter label (e.g. "Introduction"), so a
    placement run must only ever consider chapters that actually belong to the assessment's
    own subject/group -- the same parent-chain walk `_chapter_to_unit` already uses to
    resolve a chapter's board unit.
    """
    subject_ids = {
        n.id for n in nodes.values() if n.kind == "subject" and n.code in subject_codes
    }
    out: set[str] = set()
    for node in nodes.values():
        if node.kind != "chapter":
            continue
        seen: set[str] = set()
        current = node
        while current is not None and current.id not in seen:
            if current.id in subject_ids:
                out.add(node.id)
                break
            seen.add(current.id)
            current = nodes.get(current.parent_id)
    return out


def _chapter_to_unit(db: Session, nodes: dict, chapter_ids: set[str] | None = None) -> dict[str, str]:
    from app.models import ChapterBoardUnit

    out: dict[str, str] = {}
    for row in db.scalars(select(ChapterBoardUnit)):
        if chapter_ids is not None and row.chapter_id not in chapter_ids:
            continue
        chapter = nodes.get(row.chapter_id)
        unit = nodes.get(row.board_unit_id)
        if chapter and unit:
            out[chapter.label] = unit.code
    return out


def _unit_node_id(db: Session, nodes: dict, unit_code: str) -> str | None:
    for node in nodes.values():
        if node.kind == "board_unit" and node.code == unit_code:
            return node.id
    return None


@router.get("/{assessment_id}/review")
def review_queue(
    assessment_id: str,
    school: School = Depends(require_paper_scope),
    db: Session = Depends(get_session),
) -> dict:
    """The questions a person still has to settle, with what the machine had to go on."""
    a = _assessment(db, school, assessment_id)
    questions = {
        q.id: q
        for q in db.scalars(select(Question).where(Question.assessment_id == a.id))
    }
    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}

    latest: dict[str, QuestionPlacement] = {}
    for placement in db.scalars(
        select(QuestionPlacement)
        .where(QuestionPlacement.question_id.in_(questions))
        .order_by(QuestionPlacement.created_at)
    ):
        latest[placement.question_id] = placement

    # Every concept family (topic within a chapter) grouped by its chapter, so a review
    # row can offer the same candidates choose_family() itself picks between -- without
    # this a reviewer confirming the CHAPTER had no way to also fix the FAMILY, which is
    # exactly the failure mode a chapter with several families and no usable section
    # collapses into (see app.mapping.family.choose_family's own docstring).
    families_by_chapter: dict[str, list[dict]] = {}
    for n in nodes.values():
        if n.kind == "concept_family" and n.parent_id:
            families_by_chapter.setdefault(n.parent_id, []).append({"code": n.code, "label": n.label})
    for fams in families_by_chapter.values():
        fams.sort(key=lambda f: f["label"])

    pending = [
        {
            "question_id": qid,
            "address": questions[qid].address,
            "question_no": questions[qid].question_no,
            "marks": float(questions[qid].max_marks),
            "stem": (questions[qid].stem_text or "")[:400],
            "proposed_chapter": nodes[p.chapter_id].label if p.chapter_id in nodes else None,
            "proposed_chapter_code": nodes[p.chapter_id].code if p.chapter_id in nodes else None,
            "proposed_family": (
                nodes[questions[qid].concept_family_id].label
                if questions[qid].concept_family_id in nodes else None
            ),
            "proposed_family_code": (
                nodes[questions[qid].concept_family_id].code
                if questions[qid].concept_family_id in nodes else None
            ),
            "candidate_families": families_by_chapter.get(p.chapter_id, []) if p.chapter_id else [],
            "curriculum_section": p.curriculum_section,
            "tier": p.tier,
            "tier_label": TIER_ALIASES.get(p.tier or ""),
            "confidence": p.confidence,
            "source": p.source,
            "reasoning": p.reasoning,
            "evidence": p.evidence or [],
        }
        for qid, p in sorted(latest.items(), key=lambda kv: kv[1].confidence or 0.0)
        if p.needs_review
    ]
    # Scoped to this paper's own subject group -- the unfiltered set of every chapter in
    # the whole taxonomy used to be offered here, which meant a Hindi paper's review
    # screen could "settle" a question onto a Science chapter with nothing to catch it.
    chapter_ids = _chapters_in_subjects(nodes, group_subjects(a.subject_code))
    chapters = sorted(
        ({"code": n.code, "label": n.label} for n in nodes.values() if n.id in chapter_ids),
        key=lambda c: c["label"],
    )
    return {
        "assessment_id": a.id,
        "total_placed": len(latest),
        "pending": len(pending),
        "questions": pending,
        "chapters": chapters,
    }


@router.post("/{assessment_id}/review/{question_id}")
def confirm(
    assessment_id: str,
    question_id: str,
    body: ConfirmIn,
    school: School = Depends(require_paper_scope),
    db: Session = Depends(get_session),
) -> dict:
    """A person settles one question. Recorded as a new placement, never an edit.

    Same scope as the rest of paper authoring (scan/edit/confirm/map): a teacher settling
    a needs-review row on their own paper is not a different privilege than mapping it in
    the first place, and review_queue (just above) already read at this same scope --
    this used to be admin-only, silently refusing every teacher with 403 despite the
    review screen itself being reachable to them.

    The machine's attempt stays in the history: how often a teacher overrules it is the
    only honest measure of whether it is good enough to trust on the next paper.
    """
    a = _assessment(db, school, assessment_id)
    question = db.get(Question, question_id)
    if question is None or question.assessment_id != a.id:
        raise HTTPException(404, "not found")

    chapter = db.scalar(
        select(TaxonomyNode).where(
            TaxonomyNode.kind == "chapter", TaxonomyNode.code == body.chapter_code
        )
    )
    if chapter is None:
        raise HTTPException(422, f"no chapter with code {body.chapter_code!r}")

    # Settling the CHAPTER used to be the only thing this endpoint could fix. That left
    # exactly the failure mode choose_family()'s own docstring describes -- a chapter with
    # several concept families and no section to disambiguate them -- with no human lever
    # at all: a reviewer could confirm the chapter (already right, in that case) and the
    # question's family stayed whatever it was blocked on, forever. family_code closes
    # that gap: it must be one of the chapter's own families, same guardrail choose_family
    # itself applies, never a family from some other chapter.
    family = None
    if body.family_code is not None:
        family = db.scalar(
            select(TaxonomyNode).where(
                TaxonomyNode.kind == "concept_family", TaxonomyNode.code == body.family_code
            )
        )
        if family is None or family.parent_id != chapter.id:
            raise HTTPException(
                422,
                f"{body.family_code!r} is not a concept family of {chapter.label!r}",
            )

    if body.tier and tier_code(body.tier) is None:
        raise HTTPException(
            422,
            f"{body.tier!r} is not a tier. Use one of: " + "; ".join(TIERS),
        )
    # A reviewer who names a chapter but no section (the common case: they know which
    # chapter this belongs in, not which NCERT section number) keeps whatever section was
    # already on the question, rather than the pairing this uses on the Question itself
    # (chapter_id and curriculum_section together or neither -- see
    # ck_question_chapter_pairing) going half-filled and crashing with a bare
    # IntegrityError, which is what happened here before this line existed.
    resolved_section = body.curriculum_section or question.curriculum_section
    db.add(QuestionPlacement(
        question_id=question_id,
        chapter_id=chapter.id,
        curriculum_section=resolved_section,
        tier=body.tier,
        confidence=1.0,
        source="human",
        needs_review=False,
        reviewed_by=body.reviewed_by,
        reasoning=(
            f"confirmed by {body.reviewed_by}"
            + (f"; family settled to {family.label}" if family is not None else "")
        ),
    ))
    # the question itself carries the settled answer, which is what analysis reads
    if resolved_section:
        question.chapter_id = chapter.id
        question.curriculum_section = resolved_section
        # ...and so does the Topic column, which reads QuestionSkill rather than the
        # section: a settled section that left the old topic showing was settled nowhere
        # a teacher could see.
        chapter_chunks = db.scalars(
            select(BookChunk).where(BookChunk.node_id == chapter.id)
        ).all()
        subtopics = {
            n.id: n for n in db.scalars(
                select(TaxonomyNode).where(TaxonomyNode.parent_id == chapter.id)
            )
        }
        headings = section_headings(chapter_chunks, chapter, subtopics)
        set_question_topic(
            db, question.id, chapter, resolved_section,
            headings.get(resolved_section) or resolved_section,
            source="human", confidence=1.0,
        )
    if family is not None:
        question.concept_family_id = family.id
        if resolved_section:
            # Feed the correction back into the knowledge base itself, exactly as an
            # automated resolution already does (see record_family_section's own
            # docstring) -- a human settling this once is what stops the SAME chapter
            # blocking every future paper's worth of this same section, rather than only
            # fixing the one question in front of them.
            subject_codes = group_subjects(a.subject_code)
            proposals = list(db.scalars(
                select(ConceptFamilyProposal).where(
                    ConceptFamilyProposal.subject_code.in_(subject_codes),
                    ConceptFamilyProposal.code == family.code,
                )
            ))
            record_family_section(
                db, winner=family, chapter=chapter, section=resolved_section,
                subject_codes=subject_codes, proposals=proposals,
                model="human", source="human_review",
                rationale=f"settled by {body.reviewed_by} during paper review",
            )
    if body.tier:
        # A person's tier outranks the machine's, and both stay: how often a teacher
        # overrules it is the only honest measure of whether it can be trusted.
        db.add(QuestionTier(
            question_id=question_id, tier=tier_code(body.tier), confidence=1.0,
            source="human", rationale=f"settled by {body.reviewed_by}",
        ))
    db.commit()

    # Placements are append-only, so the question just corrected still has its original
    # needs_review row. What is outstanding is the questions whose LATEST placement needs
    # review -- counting every row ever written would never reach zero.
    latest: dict[str, QuestionPlacement] = {}
    for row in db.scalars(
        select(QuestionPlacement)
        .join(Question, Question.id == QuestionPlacement.question_id)
        .where(Question.assessment_id == a.id)
        .order_by(QuestionPlacement.created_at)
    ):
        latest[row.question_id] = row
    remaining = sum(1 for row in latest.values() if row.needs_review)

    return {"question_id": question_id, "chapter": chapter.label, "remaining": remaining}
