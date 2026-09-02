"""Place a paper's questions, and let a person settle the ones that need settling.

Placement is a proposal. The routes here are what turn a proposal into a fact: a paper is
tagged once, reviewed once, and then correct for every student who sat it and every re-run
of the analysis. That is where full accuracy comes from -- not from a model that is never
wrong, but from one that is never confidently wrong and hands the rest over.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.books import clean_sections
from app.api.deps import require_admin, require_reader, require_scanner
from app.classify.pipeline import place_paper
from app.mapping.family import Choice, choose_family
from app.config import get_settings
from app.db import get_session
from app.ingest.probe import LexicalIndex, SemanticIndex
from app.models import (
    Assessment,
    BookChunk,
    ConceptFamilyProposal,
    Question,
    QuestionPlacement,
    QuestionTier,
    School,
    TaxonomyNode,
)
from app.models.assessment import TIERS, tier_code

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


@router.post("/{assessment_id}/place")
def place(
    assessment_id: str,
    # The same permission as reading a paper and mapping it: this is a step of that flow,
    # and an admin-only step in the middle of it is a wall a principal cannot get past.
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """Run retrieval, the judge and the constraints over every question in the paper."""
    settings = get_settings()
    a = _assessment(db, school, assessment_id)

    questions = db.scalars(
        select(Question).where(Question.assessment_id == a.id).order_by(Question.address)
    ).all()
    stems = [(q.id, q.stem_text or "", float(q.max_marks)) for q in questions if q.stem_text]
    if not stems:
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
    from app.classify.anthropic_judge import AnthropicJudge

    chunks = db.scalars(
        select(BookChunk).where(BookChunk.subject_code == a.subject_code)
    ).all()
    if not chunks:
        raise HTTPException(409, f"no book loaded for {a.subject_code}")

    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
    by_label = {n.label: n for n in nodes.values() if n.kind == "chapter"}
    unit_by_chapter = _chapter_to_unit(db, nodes)

    indexes: list = [LexicalIndex(chunks)]
    if settings.jina_api_key and any(c.embedding for c in chunks):
        from app.ingest.jina import JinaEmbedder

        indexes.append(SemanticIndex(chunks, JinaEmbedder(
            settings.jina_api_key, model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )))

    # The sections the book ingest actually extracted, so an invented "12.9" is caught
    # rather than stored. Without this the section is unverifiable and gets dropped -- an
    # unverified value must never read as a verified one.
    known_sections: dict[str, set[str]] = {}
    for node in nodes.values():
        if node.kind != "subtopic":
            continue
        parent = nodes.get(node.parent_id)
        if parent is None or parent.kind != "chapter":
            continue
        # codes look like X.MATH.SAV.S12_2 -- the section number is the tail
        tail = node.code.rsplit(".", 1)[-1]
        if tail.startswith("S") and "_" in tail:
            known_sections.setdefault(parent.label, set()).add(tail[1:].replace("_", "."))

    judge = AnthropicJudge(
        settings.anthropic_api_key,
        model=settings.model_classifier,
        known_sections=known_sections or None,
        effort=settings.model_effort,
    )

    scope = None
    if a.syllabus_scope:
        scope = {nodes[n.id].label for n in by_label.values() if n.code in a.syllabus_scope}

    result = place_paper(
        stems, indexes, judge,
        chapter_of=lambda nid: nodes[nid].label if nid in nodes else None,
        unit_of=lambda label: unit_by_chapter.get(label),
        section_of=lambda ref: None,
        declared=(a.declared or {}).get("board_units"),
        scope=scope,
    )

    # Which families each chapter has, and which sections each of those draws on. Read
    # from the book's own record, so a judgement lands in the same family the mapping step
    # would have chosen for the same section -- one rule, in app.mapping.family.
    families: dict[str, list[TaxonomyNode]] = {}
    for node in nodes.values():
        if node.kind == "concept_family" and node.parent_id:
            families.setdefault(node.parent_id, []).append(node)
    sections_of = {
        row.code: set(clean_sections(row.from_sections))
        for row in db.scalars(select(ConceptFamilyProposal).where(
            ConceptFamilyProposal.subject_code == a.subject_code
        ))
    }

    settled, unsettled, refused = 0, 0, []
    for placed in result.questions:
        chapter = by_label.get(placed.chapter)
        unit_id = _unit_node_id(db, nodes, placed.board_unit)
        question = db.get(Question, placed.question_id)

        # The judge reads the passages retrieval found and can tell a question ABOUT a
        # theorem from the theorem, which is the whole reason it exists. Its answer used to
        # be written only as a placement, while every report prefers what the question
        # itself carries -- so the correction was recorded and then ignored. It settles the
        # question now, exactly as a teacher's correction does, and the mapping step's
        # attempt stays in the placement history.
        choice = Choice(None)
        if question is not None and chapter is not None:
            choice = choose_family(
                families.get(chapter.id, []), sections_of,
                placed.curriculum_section, chapter.label,
            )
            if choice.family is not None:
                question.chapter_id = chapter.id
                question.curriculum_section = placed.curriculum_section
                question.concept_family_id = choice.family.id
                if unit_id:
                    question.board_unit_id = unit_id
                settled += 1
                if choice.unsettled:
                    unsettled += 1
            else:
                # The chapter changed to one whose families cannot place this question.
                # Leaving the old family in place would file the marks under a chapter the
                # judge has just said is the wrong one.
                refused.append(placed.question_id)
            if placed.skill_required:
                question.skill_required = placed.skill_required

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
                or choice.unsettled is not None
                or choice.blocked is not None
            ),
            reasoning=" ".join(filter(None, [
                placed.reasoning, choice.unsettled, choice.blocked,
            ])),
            evidence=placed.evidence,
            candidates=[placed.chapter],
        ))
        # The tier belongs on its own append-only row too. Reports read it from there, so
        # writing it only onto the placement meant the judge decided the cognitive tier of
        # every question and no report ever saw one.
        db.add(QuestionTier(
            question_id=placed.question_id,
            tier=tier_code(placed.tier),
            confidence=placed.confidence,
            source="ensemble",
            model_version=settings.model_classifier,
            rationale=placed.reasoning,
        ))
    db.commit()

    return {
        "assessment_id": a.id,
        "placed": len(result.questions),
        #: questions whose chapter, topic and sub-topic the judge settled on the question
        #: itself, which is what every report reads
        "labelled": settled,
        #: settled, but more than one family had an equal claim on the section
        "unsettled_family": unsettled,
        #: the judge moved the question to a chapter whose families cannot place it, so
        #: the old family was left rather than filed under a chapter it was just told is
        #: the wrong one
        "family_refused": len(refused),
        "tiers": sum(1 for q in result.questions if tier_code(q.tier)),
        "settled": result.settled,
        "needs_review": result.reviewed_count,
        "blueprint_feasible": result.feasible,
        "note": result.note,
        # Confirming a scope is one glance; confirming thirty-eight placements is an
        # afternoon. Getting the scope right constrains every question, so it is the thing
        # worth putting in front of a person first.
        # How often the knowledge base had to correct the model. A rising number is the
        # signal that the next paper cannot be trusted to it unattended.
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


def _chapter_to_unit(db: Session, nodes: dict) -> dict[str, str]:
    from app.models import ChapterBoardUnit

    out: dict[str, str] = {}
    for row in db.scalars(select(ChapterBoardUnit)):
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
    school: School = Depends(require_reader),
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

    pending = [
        {
            "question_id": qid,
            "address": questions[qid].address,
            "question_no": questions[qid].question_no,
            "marks": float(questions[qid].max_marks),
            "stem": (questions[qid].stem_text or "")[:400],
            "proposed_chapter": nodes[p.chapter_id].label if p.chapter_id in nodes else None,
            "curriculum_section": p.curriculum_section,
            "tier": p.tier,
            "confidence": p.confidence,
            "source": p.source,
            "reasoning": p.reasoning,
            "evidence": p.evidence or [],
        }
        for qid, p in sorted(latest.items(), key=lambda kv: kv[1].confidence or 0.0)
        if p.needs_review
    ]
    return {
        "assessment_id": a.id,
        "total_placed": len(latest),
        "pending": len(pending),
        "questions": pending,
        "chapters": sorted(n.label for n in nodes.values() if n.kind == "chapter"),
    }


@router.post("/{assessment_id}/review/{question_id}")
def confirm(
    assessment_id: str,
    question_id: str,
    body: ConfirmIn,
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    """A person settles one question. Recorded as a new placement, never an edit.

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

    if body.tier and tier_code(body.tier) is None:
        raise HTTPException(
            422,
            f"{body.tier!r} is not a tier. Use one of: " + "; ".join(TIERS),
        )
    db.add(QuestionPlacement(
        question_id=question_id,
        chapter_id=chapter.id,
        curriculum_section=body.curriculum_section,
        tier=body.tier,
        confidence=1.0,
        source="human",
        needs_review=False,
        reviewed_by=body.reviewed_by,
        reasoning=f"confirmed by {body.reviewed_by}",
    ))
    # the question itself carries the settled answer, which is what analysis reads
    question.chapter_id = chapter.id
    if body.curriculum_section:
        question.curriculum_section = body.curriculum_section
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
