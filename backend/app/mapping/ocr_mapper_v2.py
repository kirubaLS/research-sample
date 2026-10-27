"""The OCR mapper's topic step, with the book's own text in front of the model.

Three stages, for any paper:

1. **Find.** Each question is matched against the printed text of every section of its subject's
   book (``section_retrieval``), and the few sections whose text talks about what was asked are
   attached to the question, with the matching sentences.
2. **Choose.** A cheap model picks the topic from the closed list, reading those passages rather
   than guessing from titles. An answer with an ID outside the list is asked again once.
3. **Check.** The answers most likely to be wrong are read again by the strong model, which sees
   the section texts side by side: anything the first pass was unsure of, anything it chose that
   the book text does not support, and anything the book text points elsewhere for. Where the two
   disagree the question is flagged for a person.

Nothing here writes anywhere. It imports the prompt mapper's schema and helpers and changes none
of them.
"""

# ruff: noqa: E501 -- the rules are prose for a model, not wrapped to code width
from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import BaseModel, Field

from app.api import prompt_lab as pl
from app.llm import output_config
from app.mapping import english_taxonomy as et
from app.mapping import math_taxonomy as mt
from app.mapping import prompt_taxonomy as pt
from app.mapping import science_taxonomy as st
from app.mapping import section_retrieval as sr

CANDIDATES = 6
#: how many top book matches count as "the book text supports this answer"
SUPPORT_TOP = 3
#: strong-model rechecks per run: the doubtful minority, not every row
MAX_VERIFY = 30
VERIFY_BATCH = 8

CANDIDATE_RULES = """

## Candidate sections
Each row carries "candidates": the sections whose own printed text best matches the question, best first, each with the sentences that match it. They come from the textbook itself, so treat them as evidence.
- Prefer a candidate whose text actually answers the question. A title that looks right is not enough: read the matching sentences.
- The right section is usually among the candidates. If none fits, choose any ID from the TAXONOMY.
- Where two candidates are a parent and its sub-topic: choose the sub-topic when the matching sentences come from its own text, and the parent when they come from the parent's opening text or the question spans the whole section (rule 2).
- Fill "considered" with the candidate IDs you weighed."""

def verify_rules(exam: str, subject_line: str) -> str:
    return f"""You are the second reader of a CBSE Class X {exam} question mapper. For each row you are given the question, the first reader's answer ("first_answer"), and candidate sections with the matching sentences from the textbook.

Decide which section TEACHES the concept the question tests, using the section text. Confirm the first answer when the text supports it; change it only when the text shows it is wrong or a neighbouring section teaches the concept better.
- Map to the section where the concept is explained, not where a keyword merely appears.
- Choose the most specific section that teaches it. A parent covers the text before its first sub-topic: use the parent when the answer is in that opening text or the question spans the section.
- MCQ: the concept of the correct answer and stem; ignore distractors. Assertion-Reason: the Assertion's topic is primary. Matching questions: tag every pair, first as primary. Case-based: use the passage. Numericals: the concept or formula the working uses.
- Add a secondary only if a student must use that section to answer.
- Use ONLY IDs from the TAXONOMY. {subject_line}
- confidence is YOUR certainty. syllabus_status describes the textbook.
Answer every row by its "row" number with considered, chapter_id, topic_id, secondary_topic_ids, confidence, syllabus_status and reason."""


VERIFY_RULES = verify_rules("Social Science", "A section letter fixes the subject.")

SCIENCE_PROMPT = st.prompt_text()


class _ScienceRow(BaseModel):
    """One Science answer, fields in the order the Science prompt asks for them."""

    row: int
    question_kind: Literal["mcq", "mcq_matching", "assertion_reason", "numerical", "diagram", "equation",
                           "short_answer", "long_answer", "case_subpart", "stem"] = "short_answer"
    tested_concept: str = ""
    considered: list[str] = Field(default_factory=list, max_length=8)
    chapter_id: str | None = None
    topic_id: str | None = None
    secondary_topic_ids: list[str] = Field(default_factory=list)
    evidence_quote: str = ""
    evidence_source: Literal["candidate", "key_terms", "none"] = "none"
    candidate_miss: bool = False
    confidence: Literal["high", "medium", "low"]
    syllabus_status: Literal["in_syllabus", "partial", "not_found"]
    out_of_book_note: str = ""
    needs_review: bool = False
    reason: str = ""


class _ScienceOut(BaseModel):
    mappings: list[_ScienceRow]


TIERS = ("Remembering & Understanding", "Applying", "Analysing, Evaluating & Creating")


def _tier_block() -> str:
    from app.classify.judge import TIER_GUIDE

    return (
        "## Competency tier (asked of every row)\n"
        "Besides the fields above, set `cognitive_tier` on every row to exactly one of: "
        + "; ".join(f'"{t}"' for t in TIERS) + ". Choose it from what the student has to DO, not from the "
        "chapter. Use null only when the question text is too short to tell.\n" + TIER_GUIDE
    )


class _TieredRow(pl._Row):
    """The Social, Mathematics and English answer, plus the competency tier."""

    cognitive_tier: Literal["Remembering & Understanding", "Applying", "Analysing, Evaluating & Creating"] | None = None


class _TieredOut(BaseModel):
    mappings: list[_TieredRow]


class _TieredScienceRow(_ScienceRow):
    cognitive_tier: Literal["Remembering & Understanding", "Applying", "Analysing, Evaluating & Creating"] | None = None


class _TieredScienceOut(BaseModel):
    mappings: list[_TieredScienceRow]


def tiered(output: type) -> type:
    """``output`` with a competency tier on every row."""
    return _TieredScienceOut if output is _ScienceOut else _TieredOut


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _science_resolve(taxonomy: pt.Taxonomy, row, section=None) -> dict:
    """``_list_resolve`` plus the Science prompt's extra fields. An evidence quote that is not in
    the chosen section's text or key terms is a problem: the model must quote, not recall."""
    out = _list_resolve(taxonomy, row, section)
    if row is None:
        return out
    for k in ("question_kind", "tested_concept", "evidence_quote", "evidence_source", "candidate_miss",
              "out_of_book_note"):
        out[k] = getattr(row, k, None)
    quote = _norm(getattr(row, "evidence_quote", ""))
    if quote and out["topic"] is not None and getattr(row, "evidence_source", "none") != "none":
        if quote not in _norm(sr.science_index().text.get(out["topic"]["id"], "")):
            out["problems"].append("the evidence quote is not in the chosen section's text or key terms")
            out["needs_review"] = True
    if getattr(row, "needs_review", False):
        out["needs_review"] = True
    return out


def _list_resolve(taxonomy: pt.Taxonomy, row, section=None) -> dict:
    """An answer, checked against a school-supplied list (Science, Mathematics): unknown IDs
    reported, the topic's own chapter used when the two disagree. (``prompt_lab.resolve`` is the
    Social Science version.)"""
    if row is None:
        return {"chapter": None, "topic": None, "secondary": [], "considered": [], "confidence": "low",
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
            problems.append(f"topic {topic.id} is in {owner.id}, not {chapter.id}; the topic's chapter was used")
        chapter = owner or chapter
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
    major = major_title = None
    if topic is not None and topic.number:
        major = ".".join(topic.number.split(".")[:2])
        major_topic = taxonomy.topic(f"{topic.chapter_id}.{major}")
        major_title = major_topic.title if major_topic else None
    return {
        "chapter": None if chapter is None else {"id": chapter.id, "code": chapter.code, "title": chapter.title},
        "topic": None if topic is None or chapter is None else {
            "id": topic.id, "number": topic.number, "title": topic.title,
            "major_number": major, "major_title": major_title},
        "considered": [tid for tid in row.considered if taxonomy.topic(tid) is not None][:8],
        "secondary": secondary, "confidence": row.confidence, "syllabus_status": row.syllabus_status,
        "reason": (row.reason or "")[:300],
        #: the whole sentence, for a reader that looks in it for the topics it names
        "reason_full": row.reason or "",
        "needs_review": bool(problems) or row.confidence == "low" or row.syllabus_status != "in_syllabus",
        "problems": problems,
    }


@dataclass(frozen=True)
class Profile:
    """What differs between the subjects the mapper knows: the list, the book text, the rules."""

    name: str
    taxonomy: Callable[[], pt.Taxonomy]
    index: Callable[[], sr.SectionIndex]
    rules: str
    verify: str
    #: a Social Science question's section letter fixes its subject; a Science one's does not
    subject_of_section: Callable[[str | None], str | None]
    resolve: Callable
    #: True when the paper's section letter says only the question type, so it is not sent
    ignore_section: bool = False
    #: the prompt already carries the topic list and the candidate-section rules (Mathematics)
    self_contained: bool = False
    #: the structured answer the model fills, and the name its question text goes under
    output: type = pl._Out
    question_key: str = "text"
    #: False when the book text cannot say where a question comes from (English: unseen passages,
    #: grammar and writing have no section). The candidates are then not sent to the first reader
    #: or used to decide which answers the second reader rechecks.
    use_retrieval: bool = True


SOCIAL = Profile(
    "social", pt.build, sr.index, pl.RULES, VERIFY_RULES,
    lambda section: pt.SECTION_SUBJECT.get((section or "").strip().upper()),
    lambda taxonomy, row, section: pl.resolve(taxonomy, row, section),
)
SCIENCE = Profile(
    "science", st.build, sr.science_index, SCIENCE_PROMPT,
    verify_rules("Science", "Ignore a section letter: it names the question type, not the subject.")
    + "\n\n# The prompt the first reader followed\nApply the same taxonomy, mapping rules and decision rules.\n\n"
    + SCIENCE_PROMPT,
    lambda section: None,
    lambda taxonomy, row, section: _science_resolve(taxonomy, row, section),
    ignore_section=True,
    self_contained=True,
    output=_ScienceOut,
    question_key="question",
)
MATH_PROMPT = mt.prompt_text()
MATHS = Profile(
    "maths", mt.build, sr.math_index, MATH_PROMPT,
    verify_rules("Mathematics", "Ignore a section letter: it names the question type, not the chapter.")
    + "\n\n# The prompt the first reader followed\nApply the same taxonomy, mapping rules and decision rules.\n\n"
    + MATH_PROMPT,
    lambda section: None,
    lambda taxonomy, row, section: _list_resolve(taxonomy, row, section),
    ignore_section=True,
    self_contained=True,
)


def with_prompt(profile: Profile, prompt: str | None) -> Profile:
    """The same profile reading ``prompt`` instead of its built-in one (a trial from the admin
    console; nothing is saved). The topic list the answers are checked against does not change,
    so a trial prompt must keep using the list's IDs."""
    prompt = (prompt or "").strip()
    if not prompt or prompt == profile.rules.strip():
        return profile
    # a self-contained profile's second-reader prompt carries the first reader's prompt verbatim
    verify = profile.verify.replace(profile.rules, prompt) if profile.self_contained else profile.verify
    return replace(profile, rules=prompt, verify=verify)


ENGLISH_PROMPT = et.prompt_text()
ENGLISH = Profile(
    "english", et.build, sr.english_index, ENGLISH_PROMPT,
    verify_rules("English Language and Literature", "Ignore a section letter: it names the question type, not the text.")
    + "\n\n# The prompt the first reader followed\nApply the same taxonomy, mapping rules and decision rules.\n\n"
    + ENGLISH_PROMPT,
    lambda section: None,
    lambda taxonomy, row, section: _list_resolve(taxonomy, row, section),
    ignore_section=True,
    self_contained=True,
    use_retrieval=False,
)


def profile_for(subject_code: str | None) -> Profile:
    code = (subject_code or "").upper()
    if code.startswith("X.SCI"):
        return SCIENCE
    if code.startswith("X.MATH"):
        return MATHS
    if code.startswith("X.ENG"):
        return ENGLISH
    return SOCIAL


def _candidate(ix: sr.SectionIndex, taxonomy: pt.Taxonomy, hit: sr.Hit, full: bool = False) -> dict:
    topic = taxonomy.topic(hit.topic_id)
    text = ix.text.get(hit.topic_id, "")
    return {"id": hit.topic_id, "title": topic.title if topic else "",
            "matches": hit.snippet if not full else (hit.snippet or text[:600])[:700]}


def _call(client, model: str, system_rules: str, taxonomy: pt.Taxonomy, subjects: set[str] | None,
          rows: list[dict], settings, self_contained: bool = False, output=pl._Out,
          extra_rules: str | None = None):
    extra = {"output_config": cfg} if (cfg := output_config(model, settings.model_effort)) else {}
    if self_contained:
        # the prompt carries its own topic list: one cached block, sent as written
        system = [{"type": "text", "text": system_rules, "cache_control": {"type": "ephemeral"}}]
    else:
        system = [
            {"type": "text", "text": system_rules},
            {"type": "text", "text": "## TAXONOMY\n" + pt.render(taxonomy, subjects),
             "cache_control": {"type": "ephemeral"}},
        ]
    if extra_rules:
        # the same words on every call, so they are cached with the prompt
        system = [*system, {"type": "text", "text": extra_rules, "cache_control": {"type": "ephemeral"}}]
    response = client.messages.parse(
        model=model, max_tokens=8000, system=system,
        messages=[{"role": "user", "content": "Map the following questions.\n\n<questions>\n"
                   + json.dumps(rows, ensure_ascii=False) + "\n</questions>"}],
        output_format=output, **extra,
    )
    usage = getattr(response, "usage", None)
    return response.parsed_output.mappings, {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }


def _family(a: str | None, b: str | None) -> bool:
    return bool(a and b and (a == b or a.startswith(b + ".") or b.startswith(a + ".")))


def map_rows_v2(client, settings, rows: list[dict], taxonomy: pt.Taxonomy | None = None,
                profile: Profile = SOCIAL, tier: bool = False):
    """Map ``rows`` (``{"row", "text", "section"?}``).

    Returns ``(answers by row, usage by model, calls, errors, meta by row)``."""
    taxonomy = taxonomy or profile.taxonomy()
    ix = profile.index()
    cheap, strong = settings.model_high_volume, settings.model_high_stakes
    usage: dict[str, dict] = defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0})
    errors: list[str] = []
    calls = 0
    subject_of = {r["row"]: profile.subject_of_section(r.get("section")) for r in rows}

    # 1. find: the sections whose own text talks about each question
    hits = {r["row"]: ix.search(r["text"], subject_of[r["row"]], CANDIDATES) for r in rows}
    with_candidates = [
        {**{("question" if k == "text" and profile.question_key == "question" else k): v
            for k, v in r.items() if not (k == "section" and profile.ignore_section)},
         **({"candidates": [_candidate(ix, taxonomy, h) for h in hits[r["row"]]]} if profile.use_retrieval else {})}
        for r in rows]
    by_row = {r["row"]: r for r in with_candidates}
    text_of = {r["row"]: r["text"] for r in rows}

    out_cls = tiered(profile.output) if tier else profile.output
    tier_rules = _tier_block() if tier else None

    def run(model, rules, chunk, subjects, label):
        nonlocal calls
        try:
            mapped, u = _call(client, model, rules, taxonomy, subjects, chunk, settings, profile.self_contained,
                              out_cls, tier_rules)
        except Exception as exc:  # noqa: BLE001 -- one batch failing must not lose the others
            errors.append(f"{label}: {type(exc).__name__}: {str(exc)[:200]}")
            return []
        calls += 1
        for k in u:
            usage[model][k] += u[k]
        return mapped

    # 2. choose
    first_pass_rules = profile.rules if profile.self_contained else profile.rules + CANDIDATE_RULES
    answers: dict[int, object] = {}
    groups: dict[str | None, list[dict]] = {}
    for r in with_candidates:
        groups.setdefault(subject_of[r["row"]], []).append(r)
    for subject, members in groups.items():
        for start in range(0, len(members), pl.BATCH):
            chunk = members[start:start + pl.BATCH]
            for m in run(cheap, first_pass_rules, chunk, {subject} if subject else None,
                         f"rows {chunk[0]['row']}-{chunk[-1]['row']}"):
                answers.setdefault(m.row, m)
    again = [
        {**by_row[r], "note": "Your previous answer used IDs that are not in the TAXONOMY: "
         + ", ".join(pl.invalid_ids(taxonomy, a)) + ". Choose again, copying IDs exactly."}
        for r, a in answers.items() if r in by_row and pl.invalid_ids(taxonomy, a)
    ]
    for subject in {subject_of[r["row"]] for r in again}:
        members = [r for r in again if subject_of[r["row"]] == subject]
        for m in run(cheap, first_pass_rules, members, {subject} if subject else None, "retry"):
            old = answers.get(m.row)
            if old is None or len(pl.invalid_ids(taxonomy, m)) < len(pl.invalid_ids(taxonomy, old)):
                answers[m.row] = m

    # 3. check: the doubtful minority, by the strong model, with the section texts
    meta: dict[int, dict] = {}
    doubtful: list[tuple[int, int]] = []
    for r in rows:
        i = r["row"]
        a = answers.get(i)
        ids = [h.topic_id for h in hits[i]]
        chosen = a.topic_id if a else None
        in_top = chosen in ids[:SUPPORT_TOP]
        in_any = chosen in ids
        meta[i] = {"candidates": ids[:CANDIDATES] if profile.use_retrieval else [], "supported_by_book": in_top if profile.use_retrieval else None,
                   "first_pass": chosen, "verified": False, "changed": False}
        if a is None:
            continue
        if not profile.use_retrieval:       # the book text cannot vouch for or against this answer
            if a.confidence != "high" or a.syllabus_status != "in_syllabus":
                doubtful.append((3, i))
            continue
        chosen_score = next((h.score for h in hits[i] if h.topic_id == chosen), 0.0)
        top = hits[i][0] if hits[i] else None
        book_points_elsewhere = bool(
            top and not _family(top.topic_id, chosen) and top.score >= 1.25 * max(chosen_score, 0.01))
        priority = (0 if not in_any else 1 if book_points_elsewhere else 2 if not in_top else 3
                    if (a.confidence != "high" or a.syllabus_status != "in_syllabus") else 9)
        if priority < 9:
            doubtful.append((priority, i))
    doubtful = [i for _, i in sorted(doubtful)][:MAX_VERIFY]
    for subject in {subject_of[i] for i in doubtful}:
        members_ids = [i for i in doubtful if subject_of[i] == subject]
        for start in range(0, len(members_ids), VERIFY_BATCH):
            chunk_ids = members_ids[start:start + VERIFY_BATCH]
            chunk = []
            for i in chunk_ids:
                a = answers[i]
                cands = [_candidate(ix, taxonomy, h, full=True) for h in hits[i][:5]]
                if a.topic_id and a.topic_id not in {c["id"] for c in cands}:
                    qterms = set(sr.tokens(text_of[i]))
                    t = taxonomy.topic(a.topic_id)
                    cands.append({"id": a.topic_id, "title": t.title if t else "",
                                  "matches": ix.snippet(a.topic_id, qterms, 700)})
                chunk.append({**{k: v for k, v in by_row[i].items() if k != "candidates"},
                              "first_answer": {"topic_id": a.topic_id, "secondary_topic_ids": a.secondary_topic_ids,
                                               "confidence": a.confidence, "reason": a.reason},
                              "candidates": cands})
            for m in run(strong, profile.verify, chunk, {subject} if subject else None,
                         f"check rows {chunk_ids[0]}-{chunk_ids[-1]}"):
                first = answers.get(m.row)
                if first is None or m.row not in chunk_ids or pl.invalid_ids(taxonomy, m):
                    continue
                meta[m.row]["verified"] = True
                if tier and getattr(m, "cognitive_tier", None) is None:
                    m.cognitive_tier = getattr(first, "cognitive_tier", None)
                if m.topic_id != first.topic_id:
                    meta[m.row]["changed"] = True
                    meta[m.row]["second_reader_confidence"] = m.confidence
                answers[m.row] = m
    return answers, dict(usage), calls, errors, meta
