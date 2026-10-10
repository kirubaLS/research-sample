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
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from app.api import prompt_lab as pl
from app.llm import output_config
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

SCIENCE_RULES = """You are an expert CBSE Class X Science curriculum mapper. You map exam questions to the exact chapter and topic of the NCERT 2026-27 Science textbook where the tested concept is TAUGHT.

## The taxonomy
The TAXONOMY below is a CLOSED list of the Chemistry (C), Biology (B), Physics (P) and Environment (ENV) chapters. Its numbers (C2.10, P3.6.1, ...) are this list's own and differ from the numbers printed in the textbook, so never use a number from your memory of the book. Copy every ID exactly as it is written below. Never invent, merge, shorten or renumber an ID. Nothing deeper than the listed levels exists.
The words in square brackets after a topic are key terms from that section's own text. Use them to tell neighbouring topics apart.

## Mapping rules
1. Map to the section where the concept is explained, not where a keyword merely appears.
2. Choose the MOST SPECIFIC section that teaches the concept. A parent ID (for example C1.4) covers the text before its first sub-topic (C1.4.1). If the answer is in that opening text, or the question spans the whole section, use the parent; otherwise use the sub-topic.
3. Before you choose, compare the neighbours: sibling and parent topics and similar topics in other chapters. Put the IDs you compared in "considered". Some concepts are taught in two chapters, for example corrosion (C1.6.1 and C3.7) and the reaction of acids with metals (C2.3 and C3.2.3). Choose the one whose framing matches the question, and add the other as a secondary only if the question needs both.
4. MCQ: map the concept tested by the correct answer and the stem. Ignore distractor options.
5. Assertion-Reason: map the topic of the Assertion as primary. Add the Reason's topic as secondary only if it comes from a different section and a student must know it to answer.
6. Numerical problems: map the concept or formula the working uses (the mirror formula, Ohm's law, the lens formula), not the setting of the story.
7. Diagram and ray-diagram questions: map the topic that teaches that diagram or construction. Chemical-equation questions: balancing is C1.3, naming a type of reaction is C1.4.x, writing an equation for a particular reaction goes to the topic about that reaction.
8. Practical and experiment-based questions: map the concept the experiment demonstrates.
9. Case-based and source-based questions: use the passage. A sub-question is mapped on its own words and its passage.
10. Secondary topics: add one only if a student must use content from that section to answer. A shared keyword is not enough.
11. Alternatives (OR): if (a) and (b) arrive as separate rows, map each row on its own and do not add the other alternative's topic. If both are inside one row, map the first as primary and list the other's topic as secondary.
12. The section letter of a Science question (A, B, C, ...) only says the question type, never the subject: ignore it and choose the chapter from the question itself.
13. syllabus_status describes the TEXTBOOK, not you: "in_syllabus" when a topic teaches the concept; "partial" when the textbook only touches it in passing; "not_found" when no topic covers it (then topic_id and chapter_id may be null).
14. confidence describes YOUR certainty only: "high" when one topic clearly teaches it, "medium" when two could, "low" when you are guessing.
15. reason: one short sentence naming the concept and why that topic teaches it.

## Before you answer
For every row check: each ID exists exactly in the TAXONOMY; chapter_id is the chapter that topic_id belongs to; no secondary equals the primary; every secondary passes rule 10.

Answer for every row, by its "row" number, with considered, chapter_id, topic_id, secondary_topic_ids, confidence, syllabus_status and reason."""


MATH_RULES = """You are an expert CBSE Class X Mathematics curriculum mapper. You map exam questions to the exact chapter and topic of the NCERT 2026-27 Mathematics textbook that teaches the method, theorem or formula the question needs.

## The taxonomy
The TAXONOMY below is a CLOSED list of the Mathematics chapters (M1 to M14) and their sections. Its numbers (M3.2.1, M8.2.3, ...) are this list's own and differ from the numbers printed in the textbook, so never use a number from your memory of the book. Copy every ID exactly as it is written below. Never invent, merge, shorten or renumber an ID. Nothing deeper than the listed levels exists.
The words in square brackets after a topic are its key terms: formulas, results and the words an exam question on it uses. Use them to tell neighbouring topics apart.

## Mapping rules
1. Map to the topic whose method, theorem or formula the question needs to be solved, not to the setting of the story. A word problem about ages or a boat in a stream belongs where its equations are solved; a problem about a tower belongs to heights and distances.
2. Choose the MOST SPECIFIC section that teaches it. A parent ID (for example M3.2) covers the text before its first sub-topic (M3.2.1). Use the parent when the question spans the section or does not name a method; use the sub-topic when the question names or clearly needs it (for example "by the substitution method").
3. Before you choose, compare the neighbours and put the IDs you compared in "considered". Close pairs: zeroes of a polynomial from a graph (M2.1) versus the sum and product of zeroes (M2.2); solving a quadratic by factorisation (M4.1) versus the discriminant and the quadratic formula (M4.2); the nth term of an AP (M5.1) versus the sum of n terms (M5.2); the distance formula (M7.1) versus the section formula (M7.2); the basic proportionality theorem (M6.2) versus the similarity criteria (M6.3); tangent perpendicular to the radius (M10.1) versus equal tangents from an external point (M10.2); surface area of a combination of solids (M12.1) versus volume (M12.2).
4. MCQ: map the concept tested by the correct answer and the stem. Ignore distractor options.
5. Assertion-Reason: map the topic of the Assertion as primary. Add the Reason's topic as secondary only if it comes from a different section and a student must know it to answer.
6. Proofs ("prove that", "show that"): map to the theorem or result being proved or used (for example M1.2 for proving a number irrational, M8.3 for proving a trigonometric identity, M10.2 for proving that tangents are equal).
7. Case-study and source-based questions: use the passage. A sub-question is mapped on its own words and its passage.
8. A question that combines two topics: one primary (the one the main step needs) and the other as secondary, only if a student must use it. A shared word is not enough.
9. Alternatives (OR): if (a) and (b) arrive as separate rows, map each row on its own and do not add the other alternative's topic. If both are inside one row, map the first as primary and list the other's topic as secondary.
10. The section letter of a Mathematics question (A, B, C, ...) only says the question type and its marks, never the chapter: ignore it.
11. syllabus_status describes the TEXTBOOK, not you: "in_syllabus" when a topic teaches the method; "partial" when the textbook only touches it in passing; "not_found" when no topic covers it (then topic_id and chapter_id may be null).
12. confidence describes YOUR certainty only: "high" when one topic clearly teaches it, "medium" when two could, "low" when you are guessing.
13. reason: one short sentence naming the method or result and why that topic teaches it.

## Before you answer
For every row check: each ID exists exactly in the TAXONOMY; chapter_id is the chapter that topic_id belongs to; no secondary equals the primary; every secondary passes rule 8.

Answer for every row, by its "row" number, with considered, chapter_id, topic_id, secondary_topic_ids, confidence, syllabus_status and reason."""


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
    if topic is not None:
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


SOCIAL = Profile(
    "social", pt.build, sr.index, pl.RULES, VERIFY_RULES,
    lambda section: pt.SECTION_SUBJECT.get((section or "").strip().upper()),
    lambda taxonomy, row, section: pl.resolve(taxonomy, row, section),
)
SCIENCE = Profile(
    "science", st.build, sr.science_index, SCIENCE_RULES,
    verify_rules("Science", "Ignore a section letter: it names the question type, not the subject."),
    lambda section: None,
    lambda taxonomy, row, section: _list_resolve(taxonomy, row, section),
    ignore_section=True,
)
MATHS = Profile(
    "maths", mt.build, sr.math_index, MATH_RULES,
    verify_rules("Mathematics", "Ignore a section letter: it names the question type, not the chapter."),
    lambda section: None,
    lambda taxonomy, row, section: _list_resolve(taxonomy, row, section),
    ignore_section=True,
)


def profile_for(subject_code: str | None) -> Profile:
    code = (subject_code or "").upper()
    if code.startswith("X.SCI"):
        return SCIENCE
    if code.startswith("X.MATH"):
        return MATHS
    return SOCIAL


def _candidate(ix: sr.SectionIndex, taxonomy: pt.Taxonomy, hit: sr.Hit, full: bool = False) -> dict:
    topic = taxonomy.topic(hit.topic_id)
    text = ix.text.get(hit.topic_id, "")
    return {"id": hit.topic_id, "title": topic.title if topic else "",
            "matches": hit.snippet if not full else (hit.snippet or text[:600])[:700]}


def _call(client, model: str, system_rules: str, taxonomy: pt.Taxonomy, subjects: set[str] | None,
          rows: list[dict], settings):
    extra = {"output_config": cfg} if (cfg := output_config(model, settings.model_effort)) else {}
    system = [
        {"type": "text", "text": system_rules},
        {"type": "text", "text": "## TAXONOMY\n" + pt.render(taxonomy, subjects),
         "cache_control": {"type": "ephemeral"}},
    ]
    response = client.messages.parse(
        model=model, max_tokens=8000, system=system,
        messages=[{"role": "user", "content": "Map the following questions.\n\n<questions>\n"
                   + json.dumps(rows, ensure_ascii=False) + "\n</questions>"}],
        output_format=pl._Out, **extra,
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
                profile: Profile = SOCIAL):
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
        {**({k: v for k, v in r.items() if k != "section"} if profile.ignore_section else r),
         "candidates": [_candidate(ix, taxonomy, h) for h in hits[r["row"]]]} for r in rows]
    by_row = {r["row"]: r for r in with_candidates}

    def run(model, rules, chunk, subjects, label):
        nonlocal calls
        try:
            mapped, u = _call(client, model, rules, taxonomy, subjects, chunk, settings)
        except Exception as exc:  # noqa: BLE001 -- one batch failing must not lose the others
            errors.append(f"{label}: {type(exc).__name__}: {str(exc)[:200]}")
            return []
        calls += 1
        for k in u:
            usage[model][k] += u[k]
        return mapped

    # 2. choose
    answers: dict[int, pl._Row] = {}
    groups: dict[str | None, list[dict]] = {}
    for r in with_candidates:
        groups.setdefault(subject_of[r["row"]], []).append(r)
    for subject, members in groups.items():
        for start in range(0, len(members), pl.BATCH):
            chunk = members[start:start + pl.BATCH]
            for m in run(cheap, profile.rules + CANDIDATE_RULES, chunk, {subject} if subject else None,
                         f"rows {chunk[0]['row']}-{chunk[-1]['row']}"):
                answers.setdefault(m.row, m)
    again = [
        {**by_row[r], "note": "Your previous answer used IDs that are not in the TAXONOMY: "
         + ", ".join(pl.invalid_ids(taxonomy, a)) + ". Choose again, copying IDs exactly."}
        for r, a in answers.items() if r in by_row and pl.invalid_ids(taxonomy, a)
    ]
    for subject in {subject_of[r["row"]] for r in again}:
        members = [r for r in again if subject_of[r["row"]] == subject]
        for m in run(cheap, profile.rules + CANDIDATE_RULES, members, {subject} if subject else None, "retry"):
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
        meta[i] = {"candidates": ids[:CANDIDATES], "supported_by_book": in_top, "first_pass": chosen,
                   "verified": False, "changed": False}
        if a is None:
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
                    qterms = set(sr.tokens(by_row[i]["text"]))
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
                if m.topic_id != first.topic_id:
                    meta[m.row]["changed"] = True
                    meta[m.row]["second_reader_confidence"] = m.confidence
                answers[m.row] = m
    return answers, dict(usage), calls, errors, meta
