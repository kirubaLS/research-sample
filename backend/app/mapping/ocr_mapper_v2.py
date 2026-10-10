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

from app.api import prompt_lab as pl
from app.llm import output_config
from app.mapping import prompt_taxonomy as pt
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

VERIFY_RULES = """You are the second reader of a CBSE Class X Social Science question mapper. For each row you are given the question, the first reader's answer ("first_answer"), and candidate sections with the matching sentences from the textbook.

Decide which section TEACHES the concept the question tests, using the section text. Confirm the first answer when the text supports it; change it only when the text shows it is wrong or a neighbouring section teaches the concept better.
- Map to the section where the concept is explained, not where a keyword merely appears.
- Choose the most specific section that teaches it. A parent covers the text before its first sub-topic: use the parent when the answer is in that opening text or the question spans the section.
- MCQ: the concept of the correct answer and stem; ignore distractors. Assertion-Reason: the Assertion's topic is primary. Matching questions: tag every pair, first as primary. Case-based: use the passage.
- Add a secondary only if a student must use that section to answer.
- Use ONLY IDs from the TAXONOMY. A section letter fixes the subject.
- confidence is YOUR certainty. syllabus_status describes the textbook.
Answer every row by its "row" number with considered, chapter_id, topic_id, secondary_topic_ids, confidence, syllabus_status and reason."""


def _candidate(ix: sr.SectionIndex, taxonomy: pt.Taxonomy, hit: sr.Hit, full: bool = False) -> dict:
    topic = taxonomy.topic(hit.topic_id)
    text = ix.text.get(hit.topic_id, "")
    return {"id": hit.topic_id, "title": topic.title if topic else "",
            "matches": hit.snippet if not full else (hit.snippet or text[:600])[:700]}


def _call(client, model: str, system_rules: str, subjects: set[str] | None, rows: list[dict], settings):
    extra = {"output_config": cfg} if (cfg := output_config(model, settings.model_effort)) else {}
    system = [
        {"type": "text", "text": system_rules},
        {"type": "text", "text": "## TAXONOMY\n" + pt.render(subjects=subjects), "cache_control": {"type": "ephemeral"}},
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


def map_rows_v2(client, settings, rows: list[dict], taxonomy: pt.Taxonomy | None = None):
    """Map ``rows`` (``{"row", "text", "section"?}``).

    Returns ``(answers by row, usage by model, calls, errors, meta by row)``."""
    taxonomy = taxonomy or pt.build()
    ix = sr.index()
    cheap, strong = settings.model_high_volume, settings.model_high_stakes
    usage: dict[str, dict] = defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0})
    errors: list[str] = []
    calls = 0
    subject_of = {r["row"]: pt.SECTION_SUBJECT.get((r.get("section") or "").strip().upper()) for r in rows}

    # 1. find: the sections whose own text talks about each question
    hits = {r["row"]: ix.search(r["text"], subject_of[r["row"]], CANDIDATES) for r in rows}
    with_candidates = [
        {**r, "candidates": [_candidate(ix, taxonomy, h) for h in hits[r["row"]]]} for r in rows]
    by_row = {r["row"]: r for r in with_candidates}

    def run(model, rules, chunk, subjects, label):
        nonlocal calls
        try:
            mapped, u = _call(client, model, rules, subjects, chunk, settings)
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
            for m in run(cheap, pl.RULES + CANDIDATE_RULES, chunk, {subject} if subject else None,
                         f"rows {chunk[0]['row']}-{chunk[-1]['row']}"):
                answers.setdefault(m.row, m)
    again = [
        {**by_row[r], "note": "Your previous answer used IDs that are not in the TAXONOMY: "
         + ", ".join(pl.invalid_ids(taxonomy, a)) + ". Choose again, copying IDs exactly."}
        for r, a in answers.items() if r in by_row and pl.invalid_ids(taxonomy, a)
    ]
    for subject in {subject_of[r["row"]] for r in again}:
        members = [r for r in again if subject_of[r["row"]] == subject]
        for m in run(cheap, pl.RULES + CANDIDATE_RULES, members, {subject} if subject else None, "retry"):
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
            for m in run(strong, VERIFY_RULES, chunk, {subject} if subject else None,
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
