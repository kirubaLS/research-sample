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


_SYSTEM = """You place one CBSE Class X exam question under the ONE section of its NCERT
textbook chapter that it tests. The chapter has already been decided; do not question it.

You are given every section of that chapter, numbered, with the book's own heading for
each, and passages from the book. Answer with exactly one section number copied from the
list. Judge what the question ASKS, not which words it shares with a passage: a question
about the functions of political parties belongs under the section whose heading names
functions, even if a later section on reform mentions functions in passing.

Rules:
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
    passages: list[Candidate] = []
    seen: set[str] = set()
    for c in list(verdict.evidence) + full_chapter_evidence(chapter_id, chapter_chunks, query):
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

    try:
        choice = judge.pick(stem, chapter_label, headings, [
            Candidate(c.chunk_id, c.reference, c.node_id, c.bucket, c.score, c.section,
                      c.text[:budget])
            for c in passages
        ])
        section = normalise_section(getattr(choice, "section", ""), headings)
        rationale = str(getattr(choice, "rationale", "") or "")
    except Exception:  # noqa: BLE001 -- one question's topic must never sink the paper
        logger.exception("topic judge failed for chapter %s; retrieval decides", chapter_label)
        choice, section, rationale = None, None, ""

    if section is None:
        why = (
            "the topic judge found no listed section for this question"
            if choice is not None else "the topic judge could not be asked"
        ) + (f" ({rationale})" if rationale else "")
        return fall_back(why)

    agreed = retrieval_section is None or _related(section, retrieval_section)
    note = rationale
    if not agreed:
        note = (
            f"{rationale} Retrieval within the chapter pointed at section "
            f"{retrieval_section} ({headings.get(retrieval_section, '')}) instead."
        ).strip()
    return TopicPick(section, headings.get(section), "judge", agreed, retrieval_section, note)
