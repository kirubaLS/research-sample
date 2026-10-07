"""The question lab: put ONE question through the mapping pipeline and see every step.

An operator types a question (or loads one already stored), picks a subject, and gets back
what the pipeline would decide -- chapter, topic, tier, concept family -- together with the
evidence for each decision: the retrieval ranking, whether the Tier 0 gate would have
passed, the nearest questions a school's teachers already confirmed, the trained
classifier's vote, and, in ``full`` mode, what the chapter and topic judges said and what
the calls cost.

**It writes nothing.** No question, placement, topic, family, job or cost row is created or
changed, on any path: the route opens its own session, never commits, rolls back in a
``finally``, and on Postgres starts the transaction READ ONLY, so a bug here would fail
loudly instead of changing data. Nothing it does can affect any paper, school or student.

Two modes, because they differ in price and the operator should choose:

* ``retrieval`` (free): book retrieval, the retrieval-only topic, and the signals. No
  Anthropic call. One tiny Jina query when the book has embeddings.
* ``full`` (costs money): additionally runs the live chapter judge and topic judge exactly
  as the classify job configures them, and reports calls, tokens and an estimated cost.
  Rate limited.

Behind the operator key, like the rest of ``/platform``.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from app.api.books import clean_sections
from app.api.deps import require_platform_admin
from app.api.placement import _chapter_to_unit, _chapters_in_subjects
from app.classify.bayes import CONFIRMED_WEIGHT, NaiveBayesChapters
from app.classify.gate import chapter_gate
from app.classify.memory import load_confirmed
from app.classify.pipeline import EVIDENCE_DEPTH
from app.config import get_settings
from app.curriculum import group_subjects
from app.db import SessionLocal
from app.ingest.probe import (
    LexicalIndex,
    SemanticIndex,
    content_chunks,
    locate,
    retrieval_query_text,
)
from app.llm import estimate_usd
from app.mapping.family import choose_family
from app.mapping.topic_node import major_view, topic_headings
from app.models import (
    Assessment,
    BookChunk,
    ConceptFamilyProposal,
    Question,
    QuestionPlacement,
    QuestionSkill,
    TaxonomyNode,
)
from app.ratelimit import FixedWindowLimiter, client_key

router = APIRouter(
    prefix="/platform/question-lab", tags=["question-lab"],
    dependencies=[Depends(require_platform_admin)],
)

#: ``full`` mode spends real money; a runaway loop in a browser tab must hit a ceiling
_full_limiter = FixedWindowLimiter(limit=60, window_seconds=3600)

#: Social Science sections are fixed by board convention (A History, B Geography, ...)
SST_SECTION_SUBJECT = {"A": "X.HIST", "B": "X.GEO", "C": "X.POL", "D": "X.ECO"}


class LabIn(BaseModel):
    subject_code: str = Field(min_length=1, max_length=32)
    stem: str = Field(min_length=3, max_length=4000)
    marks: float = Field(default=1.0, ge=0, le=100)
    mode: Literal["retrieval", "full"] = "retrieval"
    #: the paper section letter; narrows a Social Science question to its subject
    section: str | None = Field(default=None, max_length=8)
    #: whose confirmed questions to recall; also scopes the stored-question comparison
    school_id: str | None = None
    #: a stored question to compare the lab's answer against (read only)
    question_id: str | None = None


def _label(nodes: dict, node_id: str | None) -> str | None:
    node = nodes.get(node_id) if node_id else None
    return node.label if node is not None else None


def _snippet(text_: str | None, n: int = 220) -> str:
    return " ".join((text_ or "").split())[:n]


@router.get("/find")
def find_stored_questions(q: str, school_id: str | None = None, limit: int = 15) -> dict:
    """Stored questions whose text contains ``q`` -- to load one into the lab. Read only."""
    needle = q.strip()
    if len(needle) < 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "type at least 3 characters")
    like = "%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    db = SessionLocal()
    try:
        stmt = (
            select(Question, Assessment)
            .join(Assessment, Assessment.id == Question.assessment_id)
            .where(Question.stem_text.ilike(like, escape="\\"))
            .order_by(Question.created_at.desc())
            .limit(max(1, min(limit, 30)))
        )
        if school_id:
            stmt = stmt.where(Assessment.school_id == school_id)
        nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
        return {"questions": [
            {
                "question_id": qu.id, "assessment": a.title, "subject_code": a.subject_code,
                "school_id": a.school_id, "address": qu.address, "section": qu.section,
                "marks": float(qu.max_marks), "stem": qu.stem_text,
                "chapter": _label(nodes, qu.chapter_id), "topic_section": qu.curriculum_section,
            }
            for qu, a in db.execute(stmt)
        ]}
    finally:
        db.rollback()
        db.close()


@router.post("/run")
def run_question(body: LabIn, request: Request) -> dict:
    settings = get_settings()
    if body.mode == "full":
        if not settings.anthropic_api_key:
            raise HTTPException(status.HTTP_409_CONFLICT, "no YAADHUM_ANTHROPIC_API_KEY: full mode needs it")
        _full_limiter.check(client_key(request))
    db = SessionLocal()
    try:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(text("SET TRANSACTION READ ONLY"))
        return analyse(db, settings, body)
    finally:
        db.rollback()          # nothing is ever committed from here
        db.close()


def _settings_for(settings, subject_code: str):
    """The settings this subject's paper would really run with. Where the deployment gates
    new mapping behaviour per subject (``mapping_v2_subjects``), a subject outside the list
    reads every such flag as off, and the lab must show that, not what a flag would do if it
    applied. Absent that gating, the settings are returned unchanged."""
    try:
        from app.mapping.subject_scope import applies, for_subject
    except ImportError:
        return settings, True
    return for_subject(settings, subject_code), applies(subject_code, settings)


def analyse(db, settings, body: LabIn) -> dict:  # noqa: PLR0915 -- one linear walk through the steps
    """The whole lab, against an open session. Never writes; see the module docstring."""
    settings, v2_subject = _settings_for(settings, body.subject_code)
    codes = group_subjects(body.subject_code)
    chunks = db.scalars(select(BookChunk).where(BookChunk.subject_code.in_(codes))).all()
    if not chunks:
        raise HTTPException(status.HTTP_409_CONFLICT, f"no book loaded for {body.subject_code}")

    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
    chapter_ids = _chapters_in_subjects(nodes, codes)
    by_label = {n.label: n for n in nodes.values() if n.kind == "chapter" and n.id in chapter_ids}
    unit_by_chapter = _chapter_to_unit(db, nodes, chapter_ids)

    def chapter_of(nid):
        return nodes[nid].label if nid in nodes else None

    # --- the same retrieval the pipeline builds ---------------------------------------------
    retrieval_chunks = content_chunks(chunks)
    context_of = None
    if settings.retrieval_contextual_prefix:
        from app.ingest.context import chunk_context

        def context_of(c):
            return chunk_context(c, chapter_of)

    indexes: list = [LexicalIndex(retrieval_chunks, context_of)]
    embedder = None
    if settings.jina_api_key and any(c.embedding for c in retrieval_chunks):
        from app.ingest.jina import JinaEmbedder

        embedder = JinaEmbedder(
            settings.jina_api_key, model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        indexes.append(SemanticIndex(retrieval_chunks, embedder))

    # a Social Science section letter fixes the subject, as map and classify both do
    scope: set[str] | None = None
    scope_note = None
    subject = SST_SECTION_SUBJECT.get((body.section or "").strip().upper())
    if subject and subject in codes:
        scope = {n.label for n in by_label.values()
                 if n.id in _chapters_in_subjects(nodes, [subject])} or None
        scope_note = f"section {body.section.strip().upper()} → {subject}"

    query = retrieval_query_text(body.stem)
    evidence_chapters = min(
        settings.classifier_evidence_chapters * len(codes), 3 * settings.classifier_evidence_chapters,
    )
    verdict = locate(
        query, indexes, depth=EVIDENCE_DEPTH, scope=scope, chapter_of=chapter_of,
        evidence_passages=settings.classifier_evidence_passages,
        evidence_chapters=evidence_chapters,
    )
    if scope is not None and not verdict.evidence:
        verdict = locate(
            query, indexes, depth=EVIDENCE_DEPTH,
            evidence_passages=settings.classifier_evidence_passages,
            evidence_chapters=evidence_chapters,
        )
        scope_note = (scope_note or "") + " (nothing retrieved in scope; searched everything)"
    retrieved_label = chapter_of(verdict.node_id)
    retrieved_node = by_label.get(retrieved_label) if retrieved_label else None

    retrieval = {
        "chapter": retrieved_label,
        "score": round(verdict.score, 4),
        "margin": round(verdict.margin, 4),
        "retrievers_agreed": bool(verdict.agreed),
        "retrievers": ["lexical"] + (["semantic"] if embedder else []),
        "section": verdict.section,
        "ranking": [{"chapter": chapter_of(n), "score": s} for n, s in verdict.runners_up],
        "scope": scope_note,
        "evidence": [
            {"chapter": chapter_of(c.node_id), "reference": c.reference, "section": c.section,
             "text": _snippet(c.text)}
            for c in verdict.evidence[:6]
        ],
    }

    # --- the signals the cost levers read -----------------------------------------------------
    gate = chapter_gate(verdict, retrieved_label, min_relative_margin=settings.chapter_gate_min_margin)
    gate_reason = gate.reason or None
    if len(indexes) == 1 and gate_reason == "the retrievers disagree":
        gate_reason = (
            "only one retriever is available (this book has no embeddings); "
            "the gate needs two to agree"
        )
    signals: dict = {
        "gate": {"would_pass": gate.passed, "relative_margin": round(gate.relative_margin, 3),
                 "reason": gate_reason, "min_margin": settings.chapter_gate_min_margin},
        "memory": None,
    }
    memory = None
    if body.school_id:
        memory = load_confirmed(db, school_id=body.school_id, subject_codes=codes)
        recall = memory.recall(body.stem, exclude=body.question_id)
        hit = recall.reusable(settings.memory_min_similarity)
        signals["memory"] = {
            "remembered_questions": len(memory),
            "nearest": [
                {"similarity": h.similarity, "chapter": h.entry.chapter, "section": h.entry.section,
                 "stem": _snippet(h.entry.stem, 160)} for h in recall.hits[:3]
            ],
            "vote": recall.vote, "unanimous": recall.unanimous,
            "would_reuse": hit is not None,
            "min_similarity": settings.memory_min_similarity,
        }
    bayes = NaiveBayesChapters().fit(
        [(chapter_of(c.node_id), c.text or "", 1) for c in retrieval_chunks if c.node_id in nodes]
        + ([(e.chapter, e.stem, CONFIRMED_WEIGHT) for e in memory.entries] if memory else [])
    )
    voted, posterior = bayes.predict(query, allowed=scope)
    signals["classifier"] = {"chapter": voted, "confidence": round(posterior, 3)}

    # --- the retrieval-only answer ------------------------------------------------------------
    from app.classify.topic import (
        TopicJudge,
        capped,
        choose_topic,
        topic_lexical_index,
    )
    from app.curriculum.depth import collapse_section, is_capped

    headings_of = {n.id: topic_headings(chunks, n, nodes) for n in by_label.values()}
    topic_index = topic_lexical_index(retrieval_chunks)

    def decide_topic(chapter_node, judge, fallback_section=None):
        pick = choose_topic(
            body.stem, chapter_node.id, chapter_node.label, retrieval_chunks,
            headings_of.get(chapter_node.id, {}), judge,
            fallback_section=fallback_section, embedder=embedder,
            evidence_passages=settings.classifier_evidence_passages,
            passage_chars=settings.classifier_passage_chars,
            lexical_index=topic_index, card_mode=settings.topic_card_mode,
            adaptive_reads=settings.topic_adaptive_reads,
            **({"major": view} if (view := major_view(chapter_node)) is not None else {}),
        )
        if is_capped(chapter_node.code):
            pick = capped(
                pick, lambda sec: collapse_section(None, sec, chapter_code=chapter_node.code),
                headings_of.get(chapter_node.id, {}),
            )
        return pick

    final_chapter_node = retrieved_node
    final = {
        "source": "retrieval", "tier": None, "skill_required": None,
        "confidence": round(verdict.score, 4), "needs_review": not (verdict.agreed and gate.passed),
        "reasoning": f"retrieval only: margin {verdict.margin:.3f}, " + (
            "one retriever (lexical; this book has no embeddings), so no second opinion"
            if len(indexes) == 1 else
            "both retrievers agree" if verdict.agreed else "the retrievers disagree"),
    }
    spend = {"calls": 0, "models": [], "input_tokens": 0, "output_tokens": 0,
             "cache_read_tokens": 0, "cache_write_tokens": 0, "estimated_usd": 0.0,
             "estimated_usd_topic_batched": 0.0}
    topic_judge = None
    pick = None

    if body.mode == "full" and retrieval["evidence"]:
        from app.classify.anthropic_judge import AnthropicJudge
        from app.classify.pipeline import PassOptions, place_paper

        known_sections: dict[str, set[str]] = {}
        for c in chunks:
            if c.section_number and c.node_id in chapter_ids and c.node_id in nodes:
                known_sections.setdefault(nodes[c.node_id].label, set()).add(c.section_number)
        code_of_label = {n.label: n.code for n in by_label.values()}

        def cap_for(label, section):
            code = code_of_label.get(label or "")
            if code is None or not is_capped(code):
                return section
            return collapse_section(None, section, chapter_code=code)

        if any(is_capped(code) for code in code_of_label.values()):
            known_sections = {lb: {cap_for(lb, s) for s in secs} for lb, secs in known_sections.items()}
        judge = AnthropicJudge(
            settings.anthropic_api_key, model=settings.model_classifier,
            known_sections=known_sections or None, effort=settings.model_effort,
            passage_chars=settings.classifier_passage_chars, batched=False,
            **({"section_mapper": cap_for} if settings.topic_depth_cap else {}),
            **({"cite_by_number": True} if settings.cite_passages_by_number else {}),
        )
        placement = place_paper(
            [("lab", body.stem, body.marks)], indexes, judge, chapter_of=chapter_of,
            unit_of=lambda label: unit_by_chapter.get(label), section_of=lambda ref: None,
            evidence_passages=settings.classifier_evidence_passages,
            evidence_chapters=evidence_chapters, passage_chars=settings.classifier_passage_chars,
            scope=scope, infer_scope_when_undeclared=False,
            options=PassOptions(section_cap=cap_for if settings.topic_depth_cap else None),
        )
        placed = placement.questions[0] if placement.questions else None
        if placed is not None and placed.chapter is not None and by_label.get(placed.chapter):
            final_chapter_node = by_label[placed.chapter]
            topic_judge = TopicJudge(
                settings.anthropic_api_key, settings.model_classifier, effort=settings.model_effort,
                passage_chars=settings.classifier_passage_chars, batched=False,
                **({"major_only": True} if settings.topic_major_only_document else {}),
            )
            pick = decide_topic(final_chapter_node, topic_judge, placed.curriculum_section)
            final.update({
                "source": "judges", "tier": placed.tier, "skill_required": placed.skill_required,
                "confidence": placed.confidence, "needs_review": placed.needs_review,
                "reasoning": placed.reasoning,
            })
        elif placed is not None:
            final_chapter_node = None
            final.update({"source": "judges", "tier": placed.tier,
                          "skill_required": placed.skill_required, "confidence": placed.confidence,
                          "needs_review": placed.needs_review, "reasoning": placed.reasoning})
        for j in (judge, topic_judge):
            if j is None:
                continue
            spend["calls"] += j.calls
            spend["input_tokens"] += j.input_tokens
            spend["output_tokens"] += j.output_tokens
            spend["cache_read_tokens"] += j.cache_read_tokens
            spend["cache_write_tokens"] += j.cache_write_tokens
            live = estimate_usd(
                settings.model_classifier, j.input_tokens, j.output_tokens, j.cache_read_tokens,
                cache_write_tokens=j.cache_write_tokens,
            )
            spend["estimated_usd"] += live
            spend["estimated_usd_topic_batched"] += live * (0.5 if j is topic_judge else 1.0)
        spend["models"] = [settings.model_classifier]
        spend["estimated_usd"] = round(spend["estimated_usd"], 4)
        spend["estimated_usd_topic_batched"] = round(spend["estimated_usd_topic_batched"], 4)
    elif retrieved_node is not None:
        pick = decide_topic(retrieved_node, None)

    topic = None
    if pick is not None:
        topic = {
            "section": pick.section, "heading": pick.heading, "source": pick.source,
            "agreed": pick.agreed, "verified": pick.verified,
            "retrieval_section": pick.retrieval_section, "rationale": pick.rationale,
            "secondaries": [{"section": s, "heading": h} for s, h in pick.secondaries],
        }
        if final["tier"] is None and getattr(pick, "tier", None):
            final["tier"] = pick.tier

    # --- the concept family the chapter and section would be filed under -------------------
    family = None
    if final_chapter_node is not None and pick is not None:
        try:
            families = [n for n in nodes.values()
                        if n.kind == "concept_family" and n.parent_id == final_chapter_node.id]
            sections_of = {
                row.code: set(clean_sections(row.from_sections))
                for row in db.scalars(select(ConceptFamilyProposal).where(
                    ConceptFamilyProposal.subject_code.in_(codes)))
            }
            choice = choose_family(
                families, sections_of, pick.section, final_chapter_node.label,
                prefer_label=pick.heading,
            )
            family = {
                "label": choice.family.label if choice.family else None,
                "unsettled": choice.unsettled, "blocked": choice.blocked,
            }
        except Exception:  # noqa: BLE001 -- the family is a courtesy; the rest still stands
            family = None

    final.update({
        "chapter": final_chapter_node.label if final_chapter_node else None,
        "chapter_code": final_chapter_node.code if final_chapter_node else None,
        "board_unit": unit_by_chapter.get(final_chapter_node.label) if final_chapter_node else None,
        "topic": topic, "family": family,
    })

    return {
        "mode": body.mode, "subject_code": body.subject_code, "books": codes,
        #: whether this subject runs the newer mapping logic (mapping_v2_subjects); when it
        #: does not, the lab ran with every gated flag off, as classify does
        "v2_subject": v2_subject,
        "chapters_in_book": len(by_label), "chunks": len(chunks),
        "final": final, "retrieval": retrieval, "signals": signals,
        "spend": spend,
        "stored": _stored(db, nodes, body.question_id),
        "wrote_nothing": True,
    }


def _stored(db, nodes, question_id: str | None) -> dict | None:
    """What the database already holds for a stored question, to compare against."""
    if not question_id:
        return None
    q = db.get(Question, question_id)
    if q is None:
        return None
    placement = db.scalars(
        select(QuestionPlacement).where(QuestionPlacement.question_id == q.id)
        .order_by(QuestionPlacement.created_at.desc()).limit(1)
    ).first()
    skills = db.scalars(select(QuestionSkill).where(QuestionSkill.question_id == q.id)).all()
    return {
        "question_id": q.id, "address": q.address, "stem": q.stem_text,
        "chapter": _label(nodes, q.chapter_id), "section": q.curriculum_section,
        "topics": [{"label": _label(nodes, s.node_id), "source": s.source} for s in skills],
        "placement": None if placement is None else {
            "source": placement.source, "needs_review": placement.needs_review,
            "review_reason": placement.review_reason, "tier": placement.tier,
            "chapter": _label(nodes, placement.chapter_id),
            "section": placement.curriculum_section,
            "created_at": placement.created_at.isoformat() if placement.created_at else None,
        },
    }

