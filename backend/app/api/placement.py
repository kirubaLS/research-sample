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

from app.api.deps import require_admin, require_paper_scope
from app.config import get_settings
from app.curriculum import group_subjects
from app.db import get_session
from app.mapping.auto_resolve import record_family_section
from app.mapping.topic_node import (
    assert_topic_matches_section,
    set_question_topic,
    topic_headings,
)
from app.models import (
    Assessment,
    BookChunk,
    ConceptFamilyProposal,
    PlacementJob,
    Question,
    QuestionPlacement,
    QuestionTier,
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


def _run_placement_job(job_id: str) -> None:
    """The classify step. The chapter and topic of every question are decided by the OCR
    mapper's pipeline in the map step (app.mapping.teacher_map), so this step has nothing left
    to decide: it records that on the job so the screens that follow a Classify job still
    complete. Never raises."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        job = db.get(PlacementJob, job_id)
        if job is None:
            return
        _finish_placement_job(
            job_id, status_value="succeeded", result={
                "assessment_id": job.assessment_id, "placed": 0, "pipeline": "ocr_mapper",
                "note": "chapter and topic were decided by the OCR mapper's pipeline in the map step",
            },
        )
    finally:
        db.close()


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
    # topic_depth_cap: a person's section is cut to the subject's depth like any other
    from app.curriculum.depth import collapse_section

    fine_section = resolved_section
    resolved_section = collapse_section(None, resolved_section, chapter_code=chapter.code)
    db.add(QuestionPlacement(
        question_id=question_id,
        chapter_id=chapter.id,
        curriculum_section=resolved_section,
        curriculum_section_fine=(
            fine_section if fine_section and fine_section != resolved_section else None
        ),
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
        headings = topic_headings(chapter_chunks, chapter, subtopics)
        if resolved_section not in headings:
            from app.curriculum.book_map import heading_label, unit_by_number

            unit = unit_by_number(chapter.code).get(resolved_section)
            if unit is not None:
                headings[resolved_section] = heading_label(resolved_section, unit.title)
        set_question_topic(
            db, question.id, chapter, resolved_section,
            headings.get(resolved_section) or resolved_section,
            source="human", confidence=1.0,
        )
        assert_topic_matches_section(db, [question.id])
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
