"""The prompt mapper: map questions to chapter and topic with ONE cheap model call per batch.

An experiment beside the real pipeline, not a replacement for it. The real pipeline reads the
book's text (retrieval, then a judge that reads the chapter); this asks a small model
(Haiku) to choose from the book's complete list of chapters and topics, written out in the
prompt with hints about what each contains (``app.mapping.prompt_taxonomy``). The two can be
run on the same questions and compared, which is the point: it answers "does a closed list
cover the topics better than retrieval does?" with numbers.

Why the list is built from the book map and not typed: a hand-written list drifts. Topics go
missing (each crop, the soil types, the consumer-court sections) and topics the book does not
have get added, and either way a question is forced onto the wrong thing. Built from the same
reference files the rest of the system reads, every section and sub-section is a choice.

**It writes nothing and touches nothing existing.** Own routes, own module, own session that
is never committed; the only things it reads from the database are a paper's questions and
their saved mapping, for comparison. Behind the operator key.
"""

# ruff: noqa: E501 -- RULES is prose for a model, not wrapped to code width
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from app.api.deps import require_platform_admin
from app.config import get_settings
from app.db import SessionLocal
from app.llm import estimate_usd, output_config
from app.mapping import prompt_taxonomy as pt
from app.models import Assessment, Question, TaxonomyNode
from app.ratelimit import FixedWindowLimiter, client_key

router = APIRouter(
    prefix="/platform/prompt-lab", tags=["prompt-lab"],
    dependencies=[Depends(require_platform_admin)],
)

_limiter = FixedWindowLimiter(limit=40, window_seconds=3600)
#: questions per model call: small enough that the answer stays short and careful
BATCH = 20
#: questions per run
MAX_ROWS = 80

RULES = """You are an expert CBSE Class X Social Science curriculum mapper. You map exam questions to the exact chapter and topic of the NCERT 2026-27 textbooks where the tested concept is TAUGHT.

## Mapping rules
1. Map to the section where the concept is explained, not where a keyword merely appears. Example: a question on the Rowlatt Act maps to the Rowlatt Act section, not to a later section that mentions it.
2. Choose the MOST SPECIFIC topic that teaches the concept: a sub-section over its parent section when one fits. Use the parent only when the question spans the whole section.
3. MCQ: map the concept tested by the correct answer and the stem. Ignore distractor options.
4. Assertion-Reason: map the topic of the Assertion as primary. If the Reason comes from a different section, list that section as secondary.
5. Case-based: use the passage context. A sub-question is mapped on its own words and its passage.
6. Map questions: map each item to the chapter where that place is taught. Items can come from different chapters.
7. Chronology or multi-concept questions: give one primary topic and list all other topics as secondary.
8. Alternative (OR) questions: map the first alternative; list the other's topic as secondary.
9. Use ONLY the IDs in the TAXONOMY below. Never invent, merge or renumber an ID. The words in square brackets after a topic are hints about what it contains.
10. A "section" letter on a question fixes its subject: A = History (H chapters), B = Geography (G), C = Political Science (P), D = Economics (E). When one is given, choose only from that subject.
11. syllabus_status: "in_syllabus" when a topic teaches the concept; "partial" when it is only touched on indirectly; "not_found" when no topic does (then topic_id and chapter_id may be null).
12. confidence: "high" when one topic clearly teaches it, "medium" when two could, "low" when you are guessing.
13. reason: one short sentence naming the concept and why that topic teaches it.

Answer for every row, by its "row" number, with chapter_id, topic_id, secondary_topic_ids, confidence, syllabus_status and reason."""


class QuestionIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)
    section: str | None = Field(default=None, max_length=2)
    question_id: str | None = None


class RunIn(BaseModel):
    questions: list[QuestionIn] = Field(default_factory=list)
    #: map every question of a stored paper instead (read only), and compare with its saved mapping
    assessment_id: str | None = None


class _Row(BaseModel):
    row: int
    chapter_id: str | None = None
    topic_id: str | None = None
    secondary_topic_ids: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    syllabus_status: Literal["in_syllabus", "partial", "not_found"]
    reason: str = ""


class _Out(BaseModel):
    mappings: list[_Row]


def _client(settings):
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _system(subjects: set[str] | None = None) -> list[dict]:
    """The rules, then the taxonomy as a cached block: identical bytes on every call, so the
    second batch of a paper reads it back at a tenth of the price."""
    return [
        {"type": "text", "text": RULES},
        {"type": "text", "text": "## TAXONOMY\n" + pt.render(subjects=subjects),
         "cache_control": {"type": "ephemeral"}},
    ]


def map_batch(client, model: str, rows: list[dict], settings) -> tuple[list[_Row], dict]:
    """One call for up to BATCH rows ``{"row", "text", "section"?}``. Returns the answers and
    the usage."""
    extra = {"output_config": cfg} if (cfg := output_config(model, settings.model_effort)) else {}
    response = client.messages.parse(
        model=model, max_tokens=8000, system=_system(),
        messages=[{"role": "user", "content": "Map the following questions.\n\n<questions>\n"
                   + json.dumps(rows, ensure_ascii=False) + "\n</questions>"}],
        output_format=_Out, **extra,
    )
    usage = getattr(response, "usage", None)
    return response.parsed_output.mappings, {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }


def resolve(taxonomy: pt.Taxonomy, row: _Row | None, section: str | None) -> dict:
    """An answer, checked against the taxonomy and translated to the real chapter and section.

    The model may only choose from the list, but it is checked anyway: an ID not in the list is
    reported as invalid and the row is flagged, never trusted."""
    if row is None:
        return {"chapter": None, "topic": None, "secondary": [], "confidence": "low",
                "syllabus_status": "not_found", "reason": "the model gave no answer for this row",
                "needs_review": True, "problems": ["no answer"]}
    problems: list[str] = []
    topic = taxonomy.topic(row.topic_id)
    if row.topic_id and topic is None:
        problems.append(f"unknown topic id {row.topic_id}")
    chapter = taxonomy.chapter(row.chapter_id)
    if row.chapter_id and chapter is None:
        problems.append(f"unknown chapter id {row.chapter_id}")
    if topic is not None:
        owner = taxonomy.chapter(topic.chapter_id)
        if chapter is not None and owner is not None and owner.id != chapter.id:
            problems.append(
                f"topic {topic.id} is in {owner.id}, not {chapter.id}; the topic's chapter was used")
        chapter = owner or chapter
    subject = pt.SECTION_SUBJECT.get((section or "").strip().upper())
    if subject and chapter is not None and chapter.subject != subject:
        problems.append(f"section {section.strip().upper()} is {subject}, the answer is in {chapter.subject}")
    secondary = []
    for tid in row.secondary_topic_ids:
        t = taxonomy.topic(tid)
        c = taxonomy.chapter(t.chapter_id) if t else None
        if t is None or c is None:
            problems.append(f"unknown secondary id {tid}")
            continue
        if topic is not None and t.id == topic.id:
            continue
        secondary.append({"id": t.id, "title": t.title, "chapter": c.title, "number": t.number})
    needs_review = bool(problems) or row.confidence == "low" or row.syllabus_status != "in_syllabus"
    return {
        "chapter": None if chapter is None else {
            "id": chapter.id, "code": chapter.code, "title": chapter.title},
        "topic": None if topic is None or chapter is None else {
            "id": topic.id, "number": topic.number, "title": topic.title,
            "major_number": pt.major_topic(chapter, topic),
            "major_title": _major_title(taxonomy, chapter, pt.major_topic(chapter, topic)),
        },
        "secondary": secondary, "confidence": row.confidence,
        "syllabus_status": row.syllabus_status, "reason": (row.reason or "")[:300],
        "needs_review": needs_review, "problems": problems,
    }


def _major_title(taxonomy: pt.Taxonomy, chapter: pt.Chapter, number: str | None) -> str | None:
    if number is None:
        return None
    t = taxonomy.topic(f"{chapter.id}.{number}")
    return t.title if t else None


def _stored_for(db, taxonomy, qids: list[str]) -> dict[str, dict]:
    """Each stored question's saved chapter and section, to compare with. Read only."""
    if not qids:
        return {}
    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
    out = {}
    for q in db.scalars(select(Question).where(Question.id.in_(qids))):
        node = nodes.get(q.chapter_id) if q.chapter_id else None
        chapter = next((c for c in taxonomy.chapters if node and c.code == node.code), None)
        major = pt.major_topic(chapter, taxonomy.topic(f"{chapter.id}.{q.curriculum_section}")) \
            if chapter and q.curriculum_section else None
        out[q.id] = {
            "chapter_code": node.code if node else None, "chapter": node.label if node else None,
            "section": q.curriculum_section, "major_section": major or q.curriculum_section,
        }
    return out


def compare(result: dict, stored: dict | None) -> dict | None:
    if not stored or not stored.get("chapter_code"):
        return None
    chapter_ok = bool(result["chapter"]) and result["chapter"]["code"] == stored["chapter_code"]
    mapped = (result["topic"] or {}).get("major_number")
    topic_ok = chapter_ok and mapped is not None and mapped == stored["major_section"]
    return {"chapter": stored["chapter"], "section": stored["section"],
            "chapter_agrees": chapter_ok, "topic_agrees": topic_ok}


@router.get("/taxonomy")
def taxonomy_overview(full: bool = False) -> dict:
    """What the model is shown: how many chapters and topics, and (``full``) the text itself."""
    taxonomy = pt.build()
    rendered = pt.render(taxonomy)
    return {
        "subjects": [s for s, _ in pt.SUBJECTS], "chapters": len(taxonomy.chapters),
        "topics": taxonomy.topic_count, "approx_tokens": len(rendered) // 4,
        "model": get_settings().model_high_volume,
        "text": rendered if full else None,
    }


@router.get("/papers")
def papers(school_id: str) -> dict:
    """A school's papers with a Social Science subject, to load into the mapper. Read only."""
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Assessment, func.count(Question.id))
            .join(Question, Question.assessment_id == Assessment.id, isouter=True)
            .where(Assessment.school_id == school_id)
            .group_by(Assessment.id).order_by(Assessment.created_at.desc()).limit(60)
        ).all()
        return {"papers": [
            {"assessment_id": a.id, "title": a.title, "subject_code": a.subject_code, "questions": n}
            for a, n in rows if n and (a.subject_code or "").startswith("X.SST")
            or (n and (a.subject_code or "") in {s for s, _ in pt.SUBJECTS})
        ]}
    finally:
        db.rollback()
        db.close()


@router.post("/run")
def run(body: RunIn, request: Request) -> dict:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(status.HTTP_409_CONFLICT, "no YAADHUM_ANTHROPIC_API_KEY: the mapper needs it")
    _limiter.check(client_key(request))
    taxonomy = pt.build()
    db = SessionLocal()
    try:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(text("SET TRANSACTION READ ONLY"))
        questions = list(body.questions)
        if body.assessment_id:
            stored = db.scalars(
                select(Question).where(Question.assessment_id == body.assessment_id)
                .order_by(Question.address)).all()
            if not stored:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "no questions on that paper")
            questions = [QuestionIn(text=q.stem_text, section=q.section, question_id=q.id)
                         for q in stored if (q.stem_text or "").strip()]
        if not questions:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "no questions to map")
        if len(questions) > MAX_ROWS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"at most {MAX_ROWS} questions per run")

        model = settings.model_high_volume
        client = _client(settings)
        answers: dict[int, _Row] = {}
        usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}
        calls = 0
        errors: list[str] = []
        for start in range(0, len(questions), BATCH):
            chunk = [
                {"row": start + i, "text": q.text.strip(),
                 **({"section": q.section.strip().upper()} if q.section and q.section.strip() else {})}
                for i, q in enumerate(questions[start:start + BATCH])
            ]
            try:
                mapped, u = map_batch(client, model, chunk, settings)
            except Exception as exc:  # noqa: BLE001 -- one batch failing must not lose the others
                errors.append(
                    f"rows {start}-{start + len(chunk) - 1}: {type(exc).__name__}: {str(exc)[:200]}")
                continue
            calls += 1
            for k in usage:
                usage[k] += u[k]
            for m in mapped:
                answers.setdefault(m.row, m)

        saved = _stored_for(db, taxonomy, [q.question_id for q in questions if q.question_id])
        results = []
        for i, q in enumerate(questions):
            r = resolve(taxonomy, answers.get(i), q.section)
            results.append({
                "row": i, "text": q.text, "section": q.section, "question_id": q.question_id,
                **r, "stored": compare(r, saved.get(q.question_id or "")),
            })
        compared = [r for r in results if r["stored"]]
        usd = estimate_usd(
            model, usage["input_tokens"], usage["output_tokens"], usage["cache_read_tokens"],
            cache_write_tokens=usage["cache_write_tokens"],
        )
        return {
            "model": model, "calls": calls, "errors": errors, "results": results,
            "summary": {
                "questions": len(results),
                "mapped": sum(1 for r in results if r["topic"]),
                "in_syllabus": sum(1 for r in results if r["syllabus_status"] == "in_syllabus"),
                "needs_review": sum(1 for r in results if r["needs_review"]),
                "high": sum(1 for r in results if r["confidence"] == "high"),
                "compared": len(compared),
                "chapter_agrees": sum(1 for r in compared if r["stored"]["chapter_agrees"]),
                "topic_agrees": sum(1 for r in compared if r["stored"]["topic_agrees"]),
            },
            "spend": {**usage, "estimated_usd": round(usd, 4)},
            "taxonomy": {"chapters": len(taxonomy.chapters), "topics": taxonomy.topic_count},
            "wrote_nothing": True,
        }
    finally:
        db.rollback()
        db.close()
