"""Which section of an already-decided chapter a question tests: the topic.

Chapter placement is a search problem across a whole book; topic placement is not. Once
the chapter is known, the topic is one of a small, closed, fully enumerable set -- the
chapter's own section headings, which the book ingest recorded on every chunk. So the
topic is decided the way a closed set should be: the judge is shown EVERY section of the
chapter by number and heading, plus the passages that best match the question, and must
answer with one of those numbers. Retrieval votes separately, on the same chapter's own
chunks, and the two either agree or they do not. Disagreement is the review flag -- a
signal about this one question, rather than a property of the chapter's family data
that flags most of a paper regardless of whether anything is wrong.

Before this existed the topic was chosen by retrieval alone at map time and never revised:
the judge named the right section in its reasoning and the Topic column showed the
retrieval guess. On a Political Science chapter whose every section says "party" and
"election", retrieval alone was close to a coin toss.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.classify.pipeline import _adaptive_passage_chars
from app.ingest.probe import (
    Candidate,
    LexicalIndex,
    SemanticIndex,
    full_chapter_evidence,
    locate,
    retrieval_query_text,
)
from app.llm import output_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TopicPick:
    """The section chosen for a question within its chapter, and how it was chosen."""

    section: str | None
    heading: str | None
    #: "judge" when the model chose from the closed list, "retrieval" when the model
    #: abstained or could not be asked and the chapter's own best-matching passages
    #: decided, "none" when the chapter has no section-tagged text at all
    source: str
    #: the judge and retrieval named the same section (or one is the other's parent)
    agreed: bool
    retrieval_section: str | None
    rationale: str


class _TopicChoice(BaseModel):
    section: str = Field(
        description="exactly one section number from the list offered, e.g. '1.2', or "
        "the literal 'none' when the question fits no listed section"
    )
    rationale: str = Field(max_length=400, description="one sentence a teacher can check")
    #: verbatim words copied from ONE of the passages shown -- the sentence that holds the
    #: fact the question tests. Checked as a real substring of the passages before the
    #: answer is trusted, and the section that sentence sits in is the section: a fact's
    #: location in the book outranks whichever heading sounds most like the question.
    quote: str = Field(
        default="",
        description="exact words copied from the one passage that contains what the "
        "question tests; empty only if no passage shown contains it",
    )


_SYSTEM = """You place one CBSE Class X exam question under the ONE section of its NCERT
textbook chapter that it tests. The chapter has already been decided; do not question it.

You are given every section of that chapter, numbered, with the book's own heading for
each, and passages from the book. Answer with exactly one section number copied from the
list. Judge what the question ASKS, not which words it shares with a passage: a question
about the functions of political parties belongs under the section whose heading names
functions, even if a later section on reform mentions functions in passing.

Rules:
- The section is where the FACT the question tests is written, not the heading that
  sounds most like the question. A question about the Index of Prohibited Books belongs
  to the section whose text mentions the Index, even if another section's heading is
  "the Fear of Print". Copy that sentence into `quote`, verbatim, from the passage shown.
- Prefer the most specific section that is genuinely about the question. A sub-section
  (2.2) beats its parent (2) when the question is about that sub-section's subject; the
  parent is right only when the question spans its children or is about the parent's
  own introductory text.
- A sub-question of a passage-based (source-based) question is about the passage's
  subject: place it where the book discusses what the passage discusses.
- A map-skill or one-line locate-and-label item belongs to the section that teaches the
  thing being located (a coal mine goes under the coal section, not the chapter intro).
- Answer 'none' only when the question fits no listed section at all. A confident wrong
  section is filed as fact and misleads every report grouped by topic, but so is a
  needless 'none': it hands the choice back to word-overlap search."""


def _prompt(
    stem: str, chapter_label: str, headings: dict[str, str],
    passages: list[Candidate], passage_chars: int,
) -> str:
    lines = [
        f"CHAPTER: {chapter_label}",
        "",
        "QUESTION",
        stem.strip()[:3000],
        "",
        "SECTIONS OF THIS CHAPTER (answer with exactly one number)",
    ]
    for number, heading in headings.items():
        lines.append(f"- {number}  {heading}" if heading and heading != number else f"- {number}")
    lines.append("")
    lines.append("PASSAGES FROM THE BOOK")
    for i, c in enumerate(passages, 1):
        where = f" (section {c.section})" if c.section else ""
        lines.append(f"\n[{i}] {c.reference}{where}\n{c.text[:passage_chars]}")
    return "\n".join(lines)


def normalise_section(answer: str, headings: dict[str, str]) -> str | None:
    """The section number the model meant, or None. Tolerates '1.2 Functions', 'section
    1.2' and '1.2.' -- but never a number the chapter does not have."""
    text = (answer or "").strip().strip(".").lower()
    if not text or text == "none":
        return None
    if text.startswith("section"):
        text = text[len("section"):].strip()
    head = text.split()[0].rstrip(".") if text.split() else text
    if head in headings:
        return head
    for number, heading in headings.items():
        if heading and text == heading.strip().lower():
            return number
    return None


class TopicJudge:
    """One structured call per question, answering from a closed list."""

    def __init__(
        self, api_key: str, model: str, *, effort: str | None = None,
        passage_chars: int = 1200,
    ) -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.output_config = output_config(model, effort)
        self.passage_chars = passage_chars
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def pick(
        self, stem: str, chapter_label: str, headings: dict[str, str],
        passages: list[Candidate],
    ) -> _TopicChoice:
        extra = {"output_config": self.output_config} if self.output_config else {}
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=8000,
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": _prompt(stem, chapter_label, headings, passages, self.passage_chars),
            }],
            output_format=_TopicChoice,
            **extra,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.input_tokens += getattr(usage, "input_tokens", 0) or 0
            self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.calls += 1
        return response.parsed_output


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def quoted_sections(quote: str, passages: list[Candidate]) -> list[str]:
    """The sections of the passages that actually contain ``quote``, in the order the
    passages were shown. Empty when the quote is not in any of them -- a paraphrase, or
    an invention, and either way not evidence."""
    q = _normalise(quote)
    if len(q) < 12:
        return []
    out: list[str] = []
    for c in passages:
        if c.section and q in _normalise(c.text) and c.section not in out:
            out.append(c.section)
    return out


_LINK_WORDS = {"of", "the", "and", "for", "in", "on", "to", "de", "&"}
_TERM_RE = re.compile(
    r"(?<![\w'])((?:[A-Z][\w'’-]+)(?:\s+(?:(?:of|the|and|for|in|on|to|de|&)\s+)?[A-Z][\w'’-]+)+)"
)
_YEAR_RE = re.compile(r"\b(1[4-9]\d\d|20\d\d)\b")
#: a single capitalised word counts only mid-sentence (after a list marker, a dash, a
#: comma), never as a sentence opener, and never one of the exam's own stock words
_SINGLE_RE = re.compile(r"(?<=[)\-–—,;] )([A-Z][a-z][\w'’-]{3,})")
_STOCK_WORDS = {
    "assertion", "reason", "options", "option", "column", "match", "choose", "explain",
    "which", "state", "read", "both", "only", "section", "question", "suggest", "analyse",
    "justify", "examine", "mention", "name", "describe", "write", "given", "answer",
    "following", "correct", "statement", "statements", "true", "false", "arrange", "person",
}
_QUOTED_RE = re.compile(r"[‘'\"“]([^’'\"”]{6,80})[’'\"”]")


def distinctive_terms(stem: str) -> list[str]:
    """Names, titles and years the question itself uses: multi-word capitalised phrases
    ("Index of Prohibited Books", "Vernacular Press Act"), quoted titles, four-digit
    years. Single capitalised words are left out -- too many are just sentence starts."""
    out: list[str] = []
    for m in _TERM_RE.finditer(stem):
        term = re.sub(r"^(The|A|An)\s+", "", m.group(1).strip())
        words = [w for w in term.split() if w.lower() not in _LINK_WORDS]
        if len(words) >= 2 and term not in out:
            out.append(term)
        elif len(words) == 1 and words[0].lower() not in _STOCK_WORDS and words[0] not in out:
            out.append(words[0])
    for m in _SINGLE_RE.finditer(stem):
        word = m.group(1)
        if word.lower() not in _STOCK_WORDS and word not in out:
            out.append(word)
    for m in _QUOTED_RE.finditer(stem):
        term = m.group(1).strip()
        if term not in out:
            out.append(term)
    for m in _YEAR_RE.finditer(stem):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def term_evidence(stem: str, chapter_chunks: list) -> tuple[dict[str, list[str]], list]:
    """Which sections of the chapter use each of the question's distinctive terms, and
    the one best chunk per term to show the judge.

    A term the book uses in exactly one section is evidence that depends on neither the
    judge's reading nor retrieval's ranking: the question names a thing, and the book
    names it in one place. A term used in three or more sections (a chapter's own
    subject, "India", the year the whole chapter is about) says nothing and is dropped.
    """
    votes: dict[str, list[str]] = {}
    chunks_to_show: list = []
    seen: set[str] = set()
    for term in distinctive_terms(stem):
        needle = _normalise(term)
        hits = [c for c in chapter_chunks if c.section_number and needle in _normalise(c.text or "")]
        sections: list[str] = []
        for c in hits:
            if c.section_number not in sections:
                sections.append(c.section_number)
        if not sections or len(sections) > 2:
            continue
        votes[term] = sections
        # the shortest chunk mentioning it is the most quotable; one per term
        best = min(hits, key=lambda c: len(c.text or ""))
        if best.id not in seen:
            seen.add(best.id)
            chunks_to_show.append(best)
    return votes, chunks_to_show


def term_vote(votes: dict[str, list[str]]) -> str | None:
    """The one section the question's single-section terms point at, or None when they
    point at different places (or there are none)."""
    single = [secs[0] for secs in votes.values() if len(secs) == 1]
    if not single:
        return None
    top = max(set(single), key=single.count)
    others = [s for s in single if not _related(s, top)]
    return top if not others else None


def _related(a: str | None, b: str | None) -> bool:
    """Same section, or one is the other's parent ('2' and '2.2'): the same place in the
    book at two levels of detail, not a disagreement."""
    if not a or not b:
        return False
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def choose_topic(
    stem: str,
    chapter_id: str,
    chapter_label: str,
    pool: list,
    headings: dict[str, str],
    judge=None,
    *,
    fallback_section: str | None = None,
    embedder=None,
    evidence_passages: int = 6,
    passage_chars: int = 1200,
    all_chunks_of_section=None,
) -> TopicPick:
    """Decide the section within ``chapter_id`` that ``stem`` tests.

    ``pool`` is the content-chunk pool retrieval already uses (see
    ``app.ingest.probe.content_chunks``); only this chapter's section-tagged chunks are
    read from it. ``headings`` is the closed set (see
    ``app.mapping.topic_node.section_headings``). ``judge`` is anything with
    ``pick(stem, chapter_label, headings, passages)``; None, or a judge that fails or
    abstains, leaves the choice to ``fallback_section`` (the chapter judge's own
    grounded section, when it named one -- a model that read the passages still
    outranks word overlap) and only then to retrieval within the chapter -- never to
    a guess.
    """
    chapter_chunks = [
        c for c in pool
        if c.node_id == chapter_id and getattr(c, "section_number", None)
    ]
    if not chapter_chunks or not headings:
        return TopicPick(None, None, "none", False, None,
                         "the book has no section-tagged text for this chapter")

    query = retrieval_query_text(stem)
    # Lexical retrieval is indexed over the whole pool and then scoped to this chapter,
    # not indexed over the chapter alone: TF-IDF's inverse document frequency is a
    # statistic of the corpus, and over one short chapter's handful of chunks every
    # discriminating word scores log(n / (1 + df)) = 0, leaving nothing to rank. Cosine
    # similarity has no such dependence, so the semantic index is built on the chapter's
    # own chunks only -- the cheaper of the two, and exactly as discriminating.
    pool_with_sections = [c for c in pool if getattr(c, "section_number", None)]
    indexes: list = [LexicalIndex(pool_with_sections)]
    if embedder is not None and any(getattr(c, "embedding", None) for c in chapter_chunks):
        indexes.append(SemanticIndex(chapter_chunks, embedder))
    verdict = locate(
        query, indexes, depth=8, scope={chapter_id}, chapter_of=lambda node_id: node_id,
        evidence_passages=evidence_passages, evidence_chapters=1,
    )
    retrieval_section = verdict.section if verdict.section in headings else None

    # What the judge reads: the passages that scored best, then one representative of
    # every other section so no section is absent from the picture -- inclusion earned
    # by being a real section, not by winning a word-overlap contest.
    votes, term_chunks = term_evidence(stem, chapter_chunks)
    named = term_vote(votes)
    passages: list[Candidate] = []
    seen: set[str] = set()
    for c in list(verdict.evidence) + [
        Candidate(c.id, c.reference, c.node_id, c.bucket, 0.0, c.section_number, c.text or "")
        for c in term_chunks
    ] + full_chapter_evidence(chapter_id, chapter_chunks, query):
        if c.chunk_id in seen or not c.text:
            continue
        seen.add(c.chunk_id)
        passages.append(c)
    budget = _adaptive_passage_chars(passage_chars, len(passages))

    def fall_back(why: str) -> TopicPick:
        if fallback_section in headings:
            return TopicPick(
                fallback_section, headings.get(fallback_section), "chapter_judge",
                retrieval_section is None or _related(fallback_section, retrieval_section),
                retrieval_section,
                f"{why}; the section the chapter judge named while reading the passages "
                "was kept",
            )
        return TopicPick(
            retrieval_section, headings.get(retrieval_section or ""), "retrieval",
            False, retrieval_section,
            f"{why}; the chapter's own best-matching passages decided",
        )

    if judge is None:
        return fall_back("no topic judge available")

    shown = [
        Candidate(c.chunk_id, c.reference, c.node_id, c.bucket, c.score, c.section,
                  c.text[:budget])
        for c in passages
    ]
    try:
        choice = judge.pick(stem, chapter_label, headings, shown)
        section = normalise_section(getattr(choice, "section", ""), headings)
        rationale = str(getattr(choice, "rationale", "") or "")
    except Exception:  # noqa: BLE001 -- one question's topic must never sink the paper
        logger.exception("topic judge failed for chapter %s; retrieval decides", chapter_label)
        choice, section, rationale = None, None, ""

    # Evidence outranks the label. The judge had to quote the passage holding the fact;
    # where that sentence sits is the section, whatever number it wrote beside it.
    notes: list[str] = []
    if section is not None:
        evidence = quoted_sections(str(getattr(choice, "quote", "") or ""), shown)
        if evidence and section not in evidence and not any(_related(section, e) for e in evidence):
            anchored = retrieval_section if retrieval_section in evidence else evidence[0]
            notes.append(
                f"the judge named section {section} ({headings.get(section, '')}) but the "
                f"passage it quoted is in section {anchored} ({headings.get(anchored, '')}), "
                "which was taken"
            )
            section = anchored

    # A disagreement with retrieval is re-decided on the two sections' FULL text, not the
    # one representative passage each: the passage that settles it (the sentence naming
    # the Index of Prohibited Books, say) is often not the one word overlap ranked first
    # for its section. One more call, only on the rows that would be flagged anyway.
    claimants: list[str] = [section] if section is not None else []
    for other in (retrieval_section, named):
        if other is not None and not any(_related(other, c) for c in claimants):
            claimants.append(other)
    if section is not None and len(claimants) > 1:
        if named is not None and not _related(section, named):
            notes.append(
                "the question's own terms ("
                + ", ".join(t for t, secs in votes.items() if len(secs) == 1 and _related(secs[0], named))
                + f") appear in the book only under section {named} ({headings.get(named, '')})"
            )
        pair = {s: headings.get(s, "") for s in claimants}
        by_section: dict[str, list] = {s: [] for s in pair}
        for c in chapter_chunks:
            if c.section_number in by_section:
                by_section[c.section_number].append(c)
        if all_chunks_of_section is not None:
            for s in pair:
                by_section[s] = list(all_chunks_of_section(s)) or by_section[s]
        full = [
            Candidate(c.id, c.reference, c.node_id, c.bucket, 0.0, c.section_number,
                      (c.text or "")[:_adaptive_passage_chars(passage_chars, 2 * max(
                          len(v) for v in by_section.values()) or 1)])
            for s in pair for c in by_section[s] if c.text
        ]
        try:
            second = judge.pick(stem, chapter_label, pair, full)
            confirmed = normalise_section(getattr(second, "section", ""), pair)
            evidence = quoted_sections(str(getattr(second, "quote", "") or ""), full)
            if evidence and confirmed not in evidence:
                confirmed = evidence[0]
            listed = " and ".join(claimants)
            if confirmed is not None and confirmed != section:
                notes.append(
                    f"re-read against the full text of sections {listed}, the judge "
                    f"switched to {confirmed} ({headings.get(confirmed, '')}): "
                    + str(getattr(second, "rationale", "") or "")
                )
                section = confirmed
            elif confirmed == section:
                notes.append(f"confirmed against the full text of sections {listed}")
        except Exception:  # noqa: BLE001 -- the first answer stands, flagged below
            logger.exception("topic confirm pass failed for chapter %s", chapter_label)

    if section is None:
        why = (
            "the topic judge found no listed section for this question"
            if choice is not None else "the topic judge could not be asked"
        ) + (f" ({rationale})" if rationale else "")
        return fall_back(why)

    # Settled when the strongest independent evidence agrees: the book's own use of the
    # question's terms when there is one, otherwise retrieval within the chapter.
    if named is not None:
        agreed = _related(section, named)
    else:
        agreed = retrieval_section is None or _related(section, retrieval_section)
    note = rationale
    if notes:
        note = " ".join([rationale, *[n[0].upper() + n[1:] + "." for n in notes]]).strip()
    if not agreed and retrieval_section is not None and not _related(section, retrieval_section):
        note = (
            f"{note} Retrieval within the chapter pointed at section "
            f"{retrieval_section} ({headings.get(retrieval_section, '')}) instead."
        ).strip()
    return TopicPick(section, headings.get(section), "judge", agreed, retrieval_section, note)
