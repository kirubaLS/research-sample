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

Whole chapter, not sampled passages. Every miss so far had one shape: the judge was never
shown the sentence that settles the question, because passages were sampled from the
chapter by word overlap and the settling sentence lost that contest. A Class X chapter is
at most ten thousand words, so nothing needs sampling: the judge reads the ENTIRE chapter,
laid out section by section, quotes the sentence that holds what the question tests, and
the section that sentence sits in is the answer. The chapter text is sent as a cached
prompt prefix, so a paper's fifteen questions on one chapter pay for its text once.
Retrieval and the question's own terms remain as independent cross-checks that decide
whether a row is settled or flagged. The sampled mode below is kept for a chapter too
large to send whole, and for a judge that does not read documents.

Answered, not mentioned -- and verified. Two reads of the same chapter share one bias: when
the answer is never stated in prose (a place shown only on a map, a fact in a caption)
both quote the sentence that names the question's subject, and agreement between them is
worth nothing. So the chosen section is checked on its own -- can this section's text,
alone, answer the question, quoting the sentence that does -- then every other claimant,
and then the judge is re-asked with the failures ruled out. A multi-part question also
names the other sections its parts are answered in, kept as secondary topics.

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

from app.classify.judge import TIER_GUIDE, TIERS
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
    #: other sections a PART of the question is answered in -- (number, heading) pairs,
    #: never the primary or one of its relatives. A chronology, a match-the-columns or a
    #: set of statements to judge tests several places in the chapter at once, and a
    #: report that credits only one of them is wrong about the rest.
    secondaries: tuple[tuple[str, str], ...] = ()
    #: True when the chosen section's own text was checked to answer the question by
    #: itself, False when no section of the chapter could, None when never checked
    verified: bool | None = None
    #: CBSE competency tier named by the answer read, grounded to the board's three; set
    #: only when the caller asked for it (the chapter judge was skipped, so nothing else
    #: names the tier) -- None otherwise, or when the judge abstained
    tier: str | None = None
    #: the section as first decided, before ``capped`` cut it to the subject's depth
    #: ("4.1.2" when ``section`` is "4.1"); None when nothing was cut
    fine_section: str | None = None


def capped(pick: TopicPick, collapse, headings: dict[str, str] | None = None) -> TopicPick:
    """``pick`` with every section cut by ``collapse`` (app.curriculum.depth): the
    primary, retrieval's section and the secondaries. A secondary that collapses onto
    the primary is dropped, and duplicates are removed. The heading follows the collapsed
    section from ``headings`` when it has one. The original section is kept as
    ``fine_section`` when it changed."""
    import dataclasses

    section = collapse(pick.section) if pick.section else pick.section
    seen: set[str] = set()
    secondaries = []
    for other, label in pick.secondaries:
        c = collapse(other)
        if not c or c == section or c in seen:
            continue
        seen.add(c)
        secondaries.append((c, (headings or {}).get(c) or (label if c == other else c)))
    heading = pick.heading
    if section != pick.section:
        heading = (headings or {}).get(section) or section
    return dataclasses.replace(
        pick, section=section, heading=heading,
        retrieval_section=collapse(pick.retrieval_section) if pick.retrieval_section else None,
        secondaries=tuple(secondaries),
        fine_section=pick.section if section != pick.section else pick.fine_section,
    )


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
    #: the answer a student would write, drawn only from the chapter -- asked for first
    #: so that the sentences quoted next are the ones that ANSWER the question, not the
    #: ones that merely mention its subject
    answer: str = Field(
        default="", max_length=600,
        description="the model answer, in 1-3 sentences, from the chapter text only",
    )
    #: up to three verbatim sentences of the chapter the answer is drawn from
    quotes: list[str] = Field(
        default_factory=list,
        description="verbatim sentences of the chapter the answer is drawn from",
    )
    #: the other sections a PART of a multi-part question is answered in, when its parts
    #: are answered in different places (a chronology, a match-the-columns, a set of
    #: statements to judge). Only sections a part is actually answered in -- never one
    #: that merely mentions the subject.
    also: list[str] = Field(
        default_factory=list,
        description="other section numbers from the list, if a part of the question is "
        "answered in a different section from `section` (up to three); empty otherwise",
    )


class _TopicChoiceWithTier(_TopicChoice):
    """The answer read, also naming the competency tier -- asked for only when the
    chapter judge, which normally names it, was skipped (skip_single_chapter_judge)."""

    tier: str | None = Field(
        default=None,
        description="Exactly one of: " + "; ".join(TIERS) + ", or null",
    )


def grounded_tier(value) -> str | None:
    """The tier exactly as the board words it, or None -- the chapter judge's rule
    (app.classify.grounding): a paraphrase of a tier is not a tier."""
    return value if isinstance(value, str) and value in TIERS else None


class _Answerability(BaseModel):
    """Can ONE section's text, alone, answer the question -- the check that separates the
    section that answers a question from the one that merely mentions its subject."""

    answerable: bool = Field(
        description="true only if the named section's own text states what the question "
        "asks for; naming the same subject is not enough"
    )
    quotes: list[str] = Field(
        default_factory=list,
        description="verbatim sentences from that section that answer the question; "
        "empty when not answerable",
    )
    reason: str = Field(max_length=300, description="one sentence")


_SYSTEM = """You place one CBSE Class X exam question under the ONE section of its NCERT
textbook chapter that it tests. The chapter has already been decided; do not question it.

You are given every section of that chapter, numbered, with the book's own heading for
each, and passages from the book. Answer with exactly one section number copied from the
list. Judge what the question ASKS, not which words it shares with a passage: a question
about how a country decides which languages it recognises belongs under the section whose
heading names language policy, even if a later section on Centre-State relations mentions
language in passing.

Rules:
- The section is where the FACT the question tests is written, not the heading that
  sounds most like the question. A question about the Bhakra Nangal project belongs to
  the section whose text mentions that project, even if another section's heading is
  "Water Scarcity". Copy that sentence into `quote`, verbatim, from the passage shown.
- Prefer the most specific section that is genuinely about the question. A sub-section
  (2.2) beats its parent (2) when the question is about that sub-section's subject; the
  parent is right only when the question spans its children or is about the parent's
  own introductory text.
- A sub-question of a passage-based (source-based) question is about the passage's
  subject: place it where the book discusses what the passage discusses.
- A map-skill or one-line locate-and-label item belongs to the section that teaches the
  thing being located (a dam goes under the section on river projects, not the chapter
  intro).
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


#: chapters up to this many characters are sent whole (about 60k tokens); a larger one
#: falls back to the sampled mode
FULL_CHAPTER_MAX_CHARS = 250_000

_DOCUMENT_SYSTEM = """You place one CBSE Class X exam question under the ONE section of its
NCERT textbook chapter that it tests. The chapter has already been decided; do not question
it. The COMPLETE text of the chapter follows, laid out section by section under numbered
headings. Read it. Then answer with the number of the section whose text contains what the
question tests, and copy that sentence, verbatim, into `quote`.

Rules:
- The section is where the question is ANSWERED, not where its subject is mentioned. A
  question that names a thing (a dam, a law, a treaty) but asks what, where, why or how
  belongs where the chapter teaches that answer -- a dam's purposes are taught where
  multi-purpose river projects are taught, measures against a problem are taught where the
  remedies are listed, not where the problem is named. Quote the sentence that answers.
- A sub-question of a passage-based (source-based) question is about the passage's
  subject: place it where the chapter discusses what the passage discusses.
- A map-skill or locate-and-label item belongs to the section that teaches the thing
  being located.
- Prefer the most specific section: a sub-section (2.2) beats its parent (2) when the
  sentence you quote is under the sub-section's heading.
- A question with several parts answered in different places (a chronology to arrange,
  columns to match, statements to judge true or false, a source with sub-questions on
  different things) belongs to the section that answers MOST of it. When its parts fall
  under different sub-sections of ONE parent section, answer with that parent. List every
  other section a part is answered in under `also` -- only sections a part is actually
  answered in, never one that merely mentions the subject. A single-part question leaves
  `also` empty.
- Map work, figures, tables and captions are part of a section's text. A place shown
  only on the map for a section is answered by that section.
- Answer 'none' only when no section of the chapter contains what the question tests."""


#: topic_major_only_document: the section list holds major topics only, so the specificity
#: rule says "of the listed sections", and the document's sub-headings are never answers.
_MAJOR_RULE = (
    "- Prefer the most specific of the listed sections: a listed sub-section (2.2) beats\n"
    "  its parent (2) when the sentence you quote is under the sub-section's heading or one\n"
    "  of its sub-headings. Text under a ### sub-heading belongs to the numbered section it\n"
    "  sits in; a sub-heading is never itself an answer.\n"
    "- Section 0 is the chapter's introduction: answer 0 only when the question is about\n"
    "  the chapter as a whole and no numbered section teaches what it asks."
)
_DOCUMENT_SYSTEM_MAJOR = _DOCUMENT_SYSTEM.replace(
    "- Prefer the most specific section: a sub-section (2.2) beats its parent (2) when the\n"
    "  sentence you quote is under the sub-section's heading.",
    _MAJOR_RULE,
)
_SYSTEM_MAJOR = _SYSTEM.replace(
    "- Prefer the most specific section that is genuinely about the question. A sub-section\n"
    "  (2.2) beats its parent (2) when the question is about that sub-section's subject; the\n"
    "  parent is right only when the question spans its children or is about the parent's\n"
    "  own introductory text.",
    "- Prefer the most specific of the listed sections that is genuinely about the\n"
    "  question. A listed sub-section (2.2) beats its parent (2) when the question is about\n"
    "  that sub-section's subject; the parent is right only when the question spans its\n"
    "  children or is about the parent's own text.",
)
assert _DOCUMENT_SYSTEM_MAJOR != _DOCUMENT_SYSTEM and _SYSTEM_MAJOR != _SYSTEM


_CARDS_SYSTEM = """You place one CBSE Class X exam question under the ONE section of its NCERT
chapter whose text answers it.

You are given a CARD for every section of the chapter (its heading, opening words and the
names and terms that set it apart), and with the question the FULL TEXT of the sections
most likely to hold the answer.

- Write the answer a student would give, in one or two sentences, from the full text shown
  only. Then copy into `quotes`, verbatim from the full text shown, the sentence(s) the
  answer is drawn from (up to three). `section` is the section those sentences are in.
- If the full text shown does NOT contain what the question tests, leave `quotes` empty
  and name in `section` the section whose card most likely holds it.
- A question that spans several sections: name the best one in `section` and the others in
  `also`. A section that only mentions the question's subject is not an answer.
- Prefer the most specific of the listed sections. Section 0 is the chapter's
  introduction: answer 0 only when the question is about the chapter as a whole.
- Map work, figures, tables and captions are part of a section's text.
- Answer 'none' only when no section of the chapter fits."""


def chapter_document(
    chapter_chunks: list, headings: dict[str, str], *, render_empty: bool = False,
) -> str:
    """The whole chapter as one document, section by section in book order, each chunk's
    text under its section heading. Deterministic for a given chapter, so it caches.

    A chunk carrying a ``subheading`` (a deeper unit or a box folded into its major topic
    -- see ``major_chunks``) is rendered under a plain ``### `` sub-heading inside its
    section, after the section's own text, in book order. ``render_empty`` keeps a
    heading that has no text of its own: "4.1 Conventional Sources of Energy" is a real
    topic whose text is all in its sub-headings, or none at all."""
    by_section: dict[str, list] = {n: [] for n in headings}
    for c in chapter_chunks:
        if c.section_number in by_section and (c.text or "").strip():
            by_section[c.section_number].append(c)
    parts: list[str] = []
    for number, heading in headings.items():
        chunks = sorted(
            by_section[number], key=lambda c: (len(c.reference or ""), c.reference or "", c.id),
        )
        if not chunks and not render_empty:
            continue
        titled = heading and heading != number
        parts.append(f"## SECTION {number}  {heading}" if titled else f"## SECTION {number}")
        own = [c for c in chunks if not getattr(c, "subheading", None)]
        parts.extend(c.text.strip() for c in own)
        groups: dict[tuple, list] = {}
        for c in chunks:
            sub = getattr(c, "subheading", None)
            if sub:
                groups.setdefault((_order(getattr(c, "fine_section", None)), sub), []).append(c)
        for (_, sub), members in sorted(groups.items(), key=lambda kv: kv[0]):
            parts.append(f"### {sub}")
            parts.extend(c.text.strip() for c in members)
        parts.append("")
    return "\n".join(parts)


def _order(section: str | None) -> tuple[tuple[int, str], ...]:
    from app.curriculum.book_map import section_key

    return section_key(section)


class _MajorChunk:
    """A chunk seen through its major topic: ``section_number`` is the major topic it
    belongs to ("4.1" for a 4.1.2 chunk, "2" for the Rat-Hole Mining box at 2.1, "0" for
    the chapter's unnumbered introduction); ``fine_section`` is what the book printed;
    ``subheading`` is the deeper unit's own title, or None for the major's own text.
    Everything else is the chunk's own."""

    __slots__ = ("_chunk", "section_number", "fine_section", "subheading")

    def __init__(self, chunk, section: str, fine: str | None, subheading: str | None):
        self._chunk = chunk
        self.section_number = section
        self.fine_section = fine
        self.subheading = subheading

    def __getattr__(self, name):
        return getattr(self._chunk, name)


def major_chunks(chapter_id: str, chapter_code: str, pool: list, max_depth: int) -> list:
    """This chapter's chunks, each placed under its major topic (see ``_MajorChunk``).
    Includes the unnumbered introduction and conclusion text as section "0", which the
    section-tagged view leaves out. A chunk whose section maps to no major topic is
    dropped, as a section the book map does not know."""
    from app.curriculum.book_map import (
        CHAPTER_LEVEL,
        INTRO_SECTION,
        NOT_A_TOPIC,
        chapter_units,
        major_of,
        unit_by_number,
    )
    from app.mapping.topic_node import BOOK_MAP_SUFFIX

    units = unit_by_number(chapter_code)
    unnumbered = {
        u.title.strip().lower(): u for u in chapter_units(chapter_code) or ()
        if u.number is None and u.kind in CHAPTER_LEVEL
    }
    out = []
    for c in pool:
        if c.node_id != chapter_id or getattr(c, "bucket", "T") != "T":
            continue
        fine = getattr(c, "section_number", None)
        major = major_of(chapter_code, fine, max_depth)
        if major is None:
            continue
        subheading = None
        if fine is None:
            title = BOOK_MAP_SUFFIX.sub("", c.reference or "").strip()
            unit = unnumbered.get(title.lower())
            if unit is not None and unit.kind != "intro":
                subheading = unit.title          # "Conclusion", folded into section 0
            fine = INTRO_SECTION
        elif fine != major:
            unit = units.get(fine)
            title = unit.title if unit else fine
            subheading = f"Box: {title}" if unit is not None and unit.kind in NOT_A_TOPIC else title
        out.append(_MajorChunk(c, major, fine, subheading))
    return out


class TopicJudge:
    """One structured call per question, answering from a closed list."""

    def __init__(
        self, api_key: str, model: str, *, effort: str | None = None,
        passage_chars: int = 1200, batched: bool = False, batch_options: dict | None = None,
        major_only: bool = False, legacy_prompts: bool = False,
    ) -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        #: served from the Message Batches API at half price (see app.llm_batch)
        self.batched = batched
        if batched:
            from app.llm_batch import BatchedClient

            self.client = BatchedClient(self.client, **(batch_options or {}))
        self.model = model
        self.output_config = output_config(model, effort)
        self.passage_chars = passage_chars
        #: topic_major_only_document: the prompts say sub-headings are never an answer
        self.major_only = major_only
        #: a subject outside mapping_v2_subjects reads the prompts as they were before the
        #: Social Science rework (app.classify.legacy_prompts), so its mapping does not move
        self.legacy_prompts = legacy_prompts
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0

    def _count(self, response) -> None:
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.input_tokens += getattr(usage, "input_tokens", 0) or 0
            self.output_tokens += getattr(usage, "output_tokens", 0) or 0
            self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
            self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.calls += 1

    def _document_system(self, chapter_label: str, headings: dict[str, str], document: str) -> list:
        """The cached prefix every read of one chapter shares: identical bytes for every
        question, every mode and every check, so it is written to the cache once."""
        section_list = "\n".join(
            f"- {n}  {h}" if h and h != n else f"- {n}" for n, h in headings.items()
        )
        if getattr(self, "legacy_prompts", False):
            from app.classify.legacy_prompts import LEGACY_DOCUMENT_SYSTEM

            system = LEGACY_DOCUMENT_SYSTEM
        else:
            system = _DOCUMENT_SYSTEM_MAJOR if getattr(self, "major_only", False) else _DOCUMENT_SYSTEM
        return [
            {"type": "text", "text": system},
            {
                "type": "text",
                "text": (
                    f"CHAPTER: {chapter_label}\n\nSECTIONS\n{section_list}\n\n"
                    f"FULL TEXT OF THE CHAPTER\n\n{document}"
                ),
                # the chapter is identical for every question on it: written to the
                # cache once, read back at a fraction of the price for the rest
                "cache_control": {"type": "ephemeral"},
            },
        ]

    def pick_from_document(
        self, stem: str, chapter_label: str, headings: dict[str, str], document: str,
        candidates: dict[str, str] | None = None, mode: str = "answer",
        exclude: dict[str, str] | None = None, with_tier: bool = False,
    ) -> _TopicChoice:
        """Read the whole chapter (a cached prefix shared by every question on it) and
        name the section whose text holds what the question tests.

        ``mode`` "answer": write the model answer first, from the chapter only, and quote
        the sentences it is drawn from -- the section is where the question is answered.
        ``mode`` "taught": the plainer reading, where is this taught. The two are asked
        independently and compared. ``candidates`` narrows the answer to a few sections
        for a confirm pass; ``exclude`` names sections already checked and found NOT to
        answer the question, for a relocating read. The document is the same in every
        case, so the cache still hits."""
        extra = {"output_config": self.output_config} if self.output_config else {}
        if mode == "answer":
            ask = (
                "First write, in `answer`, the answer a student would give to this "
                "question using only the chapter above (one to three sentences). Then copy "
                "into `quotes`, verbatim, the sentence or sentences of the chapter your "
                "answer is drawn from (up to three). `section` is the section those "
                "sentences are in. If a part of the question is answered in a different "
                "section, list that section in `also`."
            )
        else:
            ask = (
                "Which section number does this question belong to? Copy the sentence that "
                "contains what it tests into `quote`, verbatim from the chapter above."
            )
        tiered = with_tier and mode == "answer" and not candidates and not exclude
        if tiered:
            ask += "\n\nAlso name the question's competency tier in `tier`.\n" + TIER_GUIDE
        if candidates:
            ask = (
                "Earlier readings disagreed. Decide between ONLY these sections: "
                + ", ".join(f"{n} ({h})" for n, h in candidates.items())
                + ". Which one's text ANSWERS the question, not merely mentions its "
                "subject? Write the answer in `answer`, and copy the sentence(s) it is "
                "drawn from into `quotes`, verbatim from the chapter above."
            )
        if exclude:
            ask = (
                "The text of "
                + ", ".join(f"section {n} ({h})" for n, h in exclude.items())
                + " was checked and does NOT answer this question. Which OTHER section's "
                "text does -- including its map work, figures, tables and captions? Write "
                "the answer in `answer`, copy the sentence(s) it is drawn from into "
                "`quotes`, verbatim from the chapter above, and answer 'none' if no other "
                "section answers it."
            )
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=8000,
            system=self._document_system(chapter_label, headings, document),
            messages=[{"role": "user", "content": f"QUESTION\n{stem.strip()[:3000]}\n\n{ask}"}],
            output_format=_TopicChoiceWithTier if tiered else _TopicChoice,
            **extra,
        )
        self._count(response)
        return response.parsed_output

    def pick_from_cards(
        self, stem: str, chapter_label: str, cards: str, excerpt: str, with_tier: bool = False,
    ) -> _TopicChoice:
        """One read from the chapter's section cards plus the full text of the sections
        retrieval ranked first (``excerpt``). The cards are the cached prefix, identical
        for every question of the chapter."""
        extra = {"output_config": self.output_config} if self.output_config else {}
        ask = (
            "Write the answer in `answer`, copy the sentence(s) it is drawn from into "
            "`quotes` (verbatim from the full text above), and name the section."
        )
        if with_tier:
            ask += "\n\nAlso name the question's competency tier in `tier`.\n" + TIER_GUIDE
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=3000,
            system=[
                {"type": "text", "text": _CARDS_SYSTEM},
                {
                    "type": "text",
                    "text": f"CHAPTER: {chapter_label}\n\nSECTION CARDS\n{cards}",
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": (
                f"QUESTION\n{stem.strip()[:3000]}\n\nFULL TEXT OF THE MOST LIKELY "
                f"SECTIONS\n\n{excerpt}\n\n{ask}"
            )}],
            output_format=_TopicChoiceWithTier if with_tier else _TopicChoice,
            **extra,
        )
        self._count(response)
        return response.parsed_output

    def answerable(
        self, stem: str, chapter_label: str, headings: dict[str, str], document: str,
        section: str, sub_sections: list[str] | None = None,
    ) -> _Answerability:
        """Can ``section``'s text, read alone, answer the question? The verification that
        catches a section which names the question's subject without answering it --
        the same cached chapter, one short answer."""
        extra = {"output_config": self.output_config} if self.output_config else {}
        heading = headings.get(section, "")
        where = f"SECTION {section}" + (f" ({heading})" if heading and heading != section else "")
        if sub_sections:
            where += " together with its sub-sections " + ", ".join(sub_sections)
        ask = (
            f"Read ONLY the text under {where} in the chapter above -- its body, boxes, "
            "map work, figures, tables and captions. Could a student answer this question "
            "fully from that text alone? Set `answerable` true only if that text itself "
            "states what the question asks for; naming the same subject is not enough. If "
            "true, copy the sentence(s) that answer it into `quotes`, verbatim."
        )
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=2000,
            system=self._document_system(chapter_label, headings, document),
            messages=[{"role": "user", "content": f"QUESTION\n{stem.strip()[:3000]}\n\n{ask}"}],
            output_format=_Answerability,
            **extra,
        )
        self._count(response)
        return response.parsed_output

    def _pick_system(self) -> str:
        if getattr(self, "legacy_prompts", False):
            from app.classify.legacy_prompts import LEGACY_SYSTEM

            return LEGACY_SYSTEM
        return _SYSTEM_MAJOR if getattr(self, "major_only", False) else _SYSTEM

    def pick(
        self, stem: str, chapter_label: str, headings: dict[str, str],
        passages: list[Candidate],
    ) -> _TopicChoice:
        extra = {"output_config": self.output_config} if self.output_config else {}
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=8000,
            system=self._pick_system(),
            messages=[{
                "role": "user",
                "content": _prompt(stem, chapter_label, headings, passages, self.passage_chars),
            }],
            output_format=_TopicChoice,
            **extra,
        )
        self._count(response)
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


def topic_lexical_index(pool: list) -> LexicalIndex:
    """The lexical index ``choose_topic`` retrieves within a chapter with: the pool's
    section-tagged chunks, so the index's document frequencies are the book's."""
    return LexicalIndex([c for c in pool if getattr(c, "section_number", None)])


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
    lexical_index=None,
    want_tier: bool = False,
    major: tuple[str, int] | None = None,
    card_mode: bool = False,
    adaptive_reads: bool = False,
    all_sections: bool = False,
) -> TopicPick:
    """Decide the section within ``chapter_id`` that ``stem`` tests.

    ``lexical_index`` is the TF-IDF index over the pool's section-tagged chunks, built
    once by the caller and shared across every question of a run: building it costs
    a tokenisation of the whole book, and a paper's questions decided concurrently
    (see placement.py) each rebuilding it starved the API of the interpreter for the
    duration -- the screen's own requests timed out behind it. Omitted, it is built
    here, as before.

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
    major_section = None
    if major is not None:
        # topic_major_only_document: ``major`` is (chapter code, depth). Every chunk is
        # seen through its major topic, and the introduction joins as section "0".
        from app.curriculum.book_map import major_of

        chapter_code, depth = major
        chapter_chunks = major_chunks(chapter_id, chapter_code, pool, depth)

        def major_section(section):
            return major_of(chapter_code, section, depth) if section else None
    else:
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
    indexes: list = [lexical_index if lexical_index is not None else topic_lexical_index(pool)]
    if embedder is not None and any(getattr(c, "embedding", None) for c in chapter_chunks):
        indexes.append(SemanticIndex(chapter_chunks, embedder))
    verdict = locate(
        query, indexes, depth=8, scope={chapter_id}, chapter_of=lambda node_id: node_id,
        evidence_passages=evidence_passages, evidence_chapters=1,
    )
    retrieval_section = verdict.section
    if major_section is not None:
        retrieval_section = major_section(retrieval_section)
    retrieval_section = retrieval_section if retrieval_section in headings else None

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

    document = (
        chapter_document(chapter_chunks, headings, render_empty=major is not None)
        if hasattr(judge, "pick_from_document") else ""
    )
    if document and card_mode and major is not None and hasattr(judge, "pick_from_cards"):
        from app.classify.section_cards import load_cards

        cards = load_cards(major[0])
        if cards:
            quick = _choose_by_cards(
                stem, chapter_label, chapter_chunks, headings, judge, cards,
                retrieval_section=retrieval_section, named=named, want_tier=want_tier,
                all_sections=all_sections,
            )
            judge.card_hits = getattr(judge, "card_hits", 0) + (quick is not None)
            judge.card_escalations = getattr(judge, "card_escalations", 0) + (quick is None)
            if quick is not None:
                return quick
    if document and len(document) <= FULL_CHAPTER_MAX_CHARS:
        return _choose_from_whole_chapter(
            stem, chapter_label, chapter_chunks, headings, judge, document,
            retrieval_section=retrieval_section, named=named, votes=votes,
            fallback=fall_back, want_tier=want_tier, adaptive_reads=adaptive_reads,
            all_sections=all_sections,
        )

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


def _section_texts(chapter_chunks: list, headings: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {n: "" for n in headings}
    for c in chapter_chunks:
        if c.section_number in out:
            out[c.section_number] += " " + _normalise(c.text or "")
    return out


#: the most of each section's text shown in a card read
CARD_SECTION_CHARS = 7000
#: a card read is taken at this many signals of ``CARD_SIGNALS``
CARD_ACCEPT = 6
#: secondaries kept when topic_apply_all_sections is on (three otherwise)
MAX_SECONDARIES = 5
CARD_SIGNALS = 7


def card_signals(
    section: str, grounded: str, exact: bool, ranked: list[str], shown: list[str],
    retrieval_section: str | None, named: str | None,
) -> tuple[int, dict[str, bool]]:
    """What the application can observe about a card read, counted -- never the model's
    own confidence. A signal with nothing to say (no retrieval section, no term that
    names one place) counts as agreeing: it is no evidence against.

    1. the section named is one of the sections shown in full
    2. the sentences quoted were found in a shown section's text
    3. ... word for word (a close paraphrase of a real sentence scores 2 but not 3)
    4. the section they were found in is the one named
    5. BM25's first section agrees
    6. retrieval within the chapter (lexical + semantic) agrees
    7. the book's own use of the question's terms agrees
    """
    signals = {
        "named_section_shown": any(_related(section, n) for n in shown),
        "quote_found": True,
        "quote_verbatim": exact,
        "quote_in_named_section": _related(grounded, section),
        "bm25_agrees": _related(section, ranked[0]),
        "retrieval_agrees": retrieval_section is None or _related(section, retrieval_section),
        "terms_agree": named is None or _related(section, named),
    }
    return sum(signals.values()), signals


def _choose_by_cards(
    stem: str, chapter_label: str, chapter_chunks: list, headings: dict[str, str],
    judge, cards: dict[str, str], *, retrieval_section: str | None, named: str | None,
    want_tier: bool = False, all_sections: bool = False,
) -> TopicPick | None:
    """The cheap path: ONE call that reads every section's card and the full text of the
    sections BM25 ranks first -- one when retrieval is clear, two when likely, three when
    ambiguous (see ``sections_to_show``). Trusted only on evidence the application can
    check, counted by ``card_signals``: the quoted sentences are found in the book (word
    for word, or a close copy) under the section the judge named, and the independent
    signals agree. Fewer than ``CARD_ACCEPT`` of ``CARD_SIGNALS``, or a term that the book
    uses only under another section, returns None and the caller reads the whole chapter
    as before -- so the saving is only taken where the cheap read is demonstrably sound."""
    from app.classify.section_cards import (
        FUZZY_MIN,
        cards_block,
        margin,
        quote_overlap,
        score_sections,
        sections_to_show,
    )

    score = score_sections(stem, [(c.section_number, c.text or "") for c in chapter_chunks])
    ranked = sorted((n for n in score if n in headings), key=lambda n: (-score[n], n))
    shown = ranked[:sections_to_show(margin(score))]
    if not shown:
        return None
    shown_chunks = [c for c in chapter_chunks if c.section_number in shown]
    shown_headings = {n: headings[n] for n in shown}
    excerpt = chapter_document(shown_chunks, shown_headings, render_empty=False)
    if len(excerpt) > CARD_SECTION_CHARS * len(shown):
        excerpt = excerpt[:CARD_SECTION_CHARS * len(shown)]
    texts = _section_texts(shown_chunks, shown_headings)
    tally = getattr(judge, "card_tiers", None)
    if tally is None:
        tally = judge.card_tiers = {}

    def done(tier: str, pick: TopicPick | None) -> TopicPick | None:
        tally[tier] = tally.get(tier, 0) + 1
        return pick

    try:
        choice = judge.pick_from_cards(
            stem, chapter_label, cards_block(cards, headings), excerpt, with_tier=want_tier,
        )
    except Exception:  # noqa: BLE001 -- the whole-chapter read decides instead
        logger.exception("topic card read failed for %s", chapter_label)
        return done("failed", None)
    section = normalise_section(getattr(choice, "section", ""), headings)
    if section is None:
        return done("no_section", None)
    weight: dict[str, float] = {}
    exact = True
    for q in (str(x) for x in (getattr(choice, "quotes", None) or [])):
        nq = _normalise(q)
        if len(nq) < 12:
            continue
        for n, t in texts.items():
            share = quote_overlap(nq, t)
            if share >= FUZZY_MIN:
                weight[n] = weight.get(n, 0) + len(nq) * share
                exact = exact and share == 1.0
    if not weight:
        return done("no_quote", None)                # nothing quoted from what was shown
    grounded = sorted(weight, key=lambda n: (-weight[n], -n.count("."), n))
    anchor = next((g for g in grounded if _related(g, section)), grounded[0])
    if named is not None and not _related(section, named):
        return done("terms_disagree", None)          # the book's own terms say elsewhere
    points, signals = card_signals(
        section, anchor, exact, ranked, shown, retrieval_section, named)
    if points < CARD_ACCEPT or not signals["quote_in_named_section"]:
        return done("review" if points == CARD_ACCEPT - 1 else "fallback", None)
    also = tuple(
        (s, headings.get(s, s)) for s in dict.fromkeys(
            x for x in (normalise_section(str(a), headings)
                        for a in (getattr(choice, "also", None) or [])) if x is not None
        ) if not _related(s, section)
    )[:MAX_SECONDARIES if all_sections else 3]
    rationale = str(getattr(choice, "rationale", "") or getattr(choice, "answer", "") or "")
    return done("accept", TopicPick(
        section, headings.get(section), "judge", True, retrieval_section,
        f"{rationale} Read from the chapter's section cards and the full text of "
        f"section{'s' if len(shown) > 1 else ''} {' and '.join(shown)}; the quoted "
        f"sentences were {'found' if exact else 'closely matched'} in the book under "
        f"section {anchor} ({points} of {CARD_SIGNALS} signals agree).".strip(),
        secondaries=also, verified=True,
        tier=grounded_tier(getattr(choice, "tier", None)) if want_tier else None,
    ))


def _choose_from_whole_chapter(
    stem: str, chapter_label: str, chapter_chunks: list, headings: dict[str, str],
    judge, document: str, *, retrieval_section: str | None, named: str | None,
    votes: dict[str, list[str]], fallback, want_tier: bool = False,
    adaptive_reads: bool = False, all_sections: bool = False,
) -> TopicPick:
    """The judge reads the entire chapter. Its quote, not its number, is the answer; the
    independent votes (retrieval within the chapter, the book's own use of the
    question's terms) decide whether the row is settled, and a disagreement is decided
    by one more read of the same cached chapter restricted to the sections that claim
    the question."""
    texts = _section_texts(chapter_chunks, headings)

    def quoted_in(quote: str) -> list[str]:
        q = _normalise(quote)
        if len(q) < 12:
            return []
        return [n for n, t in texts.items() if q in t]

    def quote_sections(choice) -> list[str]:
        """Sections the choice's quoted sentences sit in, most-quoted first. A parent's
        text contains its children's, so the deepest section wins a tie."""
        weight: dict[str, int] = {}
        quotes = [str(q) for q in (getattr(choice, "quotes", None) or [])]
        single = str(getattr(choice, "quote", "") or "")
        if single:
            quotes.append(single)
        for q in quotes:
            for sec in quoted_in(q):
                weight[sec] = weight.get(sec, 0) + len(q)
        return sorted(weight, key=lambda n: (-weight[n], -n.count("."), n))

    def anchor(choice, candidates: dict[str, str]) -> tuple[str | None, str, str | None]:
        """(section, rationale, note) -- the quoted sentences' section outranks the
        number the judge wrote."""
        section = normalise_section(getattr(choice, "section", ""), candidates)
        rationale = str(getattr(choice, "rationale", "") or "")
        evidence = quote_sections(choice)
        if not evidence:
            return section, rationale, None
        compatible = [e for e in evidence if section is not None and _related(e, section)]
        pool = compatible or evidence
        top = max(pool, key=lambda n: (n.count("."), n)) if pool is compatible else pool[0]
        if section is not None and _related(top, section):
            return (top if top.count(".") >= section.count(".") else section), rationale, None
        return top, rationale, (
            f"the judge named section {section} ({candidates.get(section, '')}) but the "
            f"sentences it quoted are in section {top} ({headings.get(top, '')}), "
            "which was taken"
        )

    # Read 1: answer-grounded -- where the question is ANSWERED. Read 2: where its subject
    # is taught. Independent reads of the same cached chapter; they usually agree, and
    # when they do not, the difference is exactly the mention-versus-answer trap.
    reads: dict[str, tuple[str | None, str]] = {}
    notes: list[str] = []
    also: list[str] = []
    answer_quoted: list[str] = []
    tier: str | None = None
    answer_is_settled = False
    for mode in ("answer", "taught"):
        if (
            adaptive_reads and mode == "taught" and reads.get("answer", (None, ""))[0] is not None
            and answer_is_settled
        ):
            # The answer read quoted a sentence that is verbatim in the section it named,
            # and retrieval within the chapter and the book's own use of the question's
            # terms both agree. The second read exists to catch a mention-versus-answer
            # miss, and nothing here suggests one: reuse the first read for it (so no
            # claimant disagrees and no confirm read follows) and save the call. The
            # answerability check below still runs on the chosen section.
            reads["taught"] = reads["answer"]
            continue
        try:
            if want_tier and mode == "answer":
                choice = judge.pick_from_document(
                    stem, chapter_label, headings, document, mode=mode, with_tier=True,
                )
                tier = grounded_tier(getattr(choice, "tier", None))
            else:
                choice = judge.pick_from_document(stem, chapter_label, headings, document, mode=mode)
            sec, why, note = anchor(choice, headings)
            reads[mode] = (sec, why)
            if note:
                notes.append(note)
            if mode == "answer":
                answer_is_settled = (
                    sec is not None and note is None and bool(quote_sections(choice))
                    # the same precedence the claimants below use: the book's own terms
                    # when they name a place, retrieval within the chapter only when they
                    # say nothing
                    and (_related(sec, named) if named is not None else (
                        retrieval_section is None or _related(sec, retrieval_section)))
                )
            if mode == "answer":
                answer_quoted = quote_sections(choice)
                also = [
                    s for s in (
                        normalise_section(str(a), headings)
                        for a in (getattr(choice, "also", None) or [])
                    ) if s is not None
                ]
        except Exception:  # noqa: BLE001 -- one question's topic must never sink the paper
            logger.exception("topic judge (%s read) failed for %s", mode, chapter_label)
            reads[mode] = (None, "")
    answer_sec, answer_why = reads["answer"]
    taught_sec, taught_why = reads["taught"]
    section = answer_sec if answer_sec is not None else taught_sec
    rationale = answer_why if answer_sec is not None else taught_why
    if section is None:
        if not any(v[1] for v in reads.values()) and all(v[0] is None for v in reads.values()):
            return fallback("the topic judge could not be asked")
        import dataclasses

        # the tier the answer read named still stands when its section does not
        return dataclasses.replace(fallback(
            "the topic judge found no section of the chapter containing what the "
            "question tests" + (f" ({rationale})" if rationale else "")
        ), tier=tier)
    if taught_sec is not None and answer_sec is not None and not _related(answer_sec, taught_sec):
        notes.append(
            f"the section that answers the question ({answer_sec}, "
            f"{headings.get(answer_sec, '')}) differs from the one that teaches its subject "
            f"({taught_sec}, {headings.get(taught_sec, '')})"
        )

    # Every signal with a claim: the two reads, the book's own use of the question's
    # terms, and -- only when the terms say nothing -- retrieval within the chapter.
    claimants: list[str] = [section]
    for other in (taught_sec, named, retrieval_section if named is None else None):
        if other is not None and not any(_related(other, c) for c in claimants):
            claimants.append(other)
    if named is not None and not _related(section, named):
        notes.append(
            "the question's own terms ("
            + ", ".join(t for t, secs in votes.items() if len(secs) == 1 and _related(secs[0], named))
            + f") appear in the book only under section {named} ({headings.get(named, '')})"
        )
    confirmed: str | None = None
    if len(claimants) > 1:
        candidates = {n: headings.get(n, "") for n in claimants}
        try:
            third = judge.pick_from_document(stem, chapter_label, headings, document, candidates)
            confirmed, why, _ = anchor(third, candidates)
            if confirmed is not None and confirmed != section:
                notes.append(
                    f"re-read against sections {' and '.join(claimants)}, the judge "
                    f"switched to {confirmed} ({headings.get(confirmed, '')}): {why}"
                )
                section = confirmed
            elif confirmed == section:
                notes.append(f"confirmed against sections {' and '.join(claimants)}")
        except Exception:  # noqa: BLE001 -- the first answer stands, flagged below
            logger.exception("topic confirm (whole chapter) failed for %s", chapter_label)

    # Settled when nothing with a claim disagrees, or when the re-read sided with the
    # answer read and the book's own terms do not contradict it.
    if len(claimants) == 1:
        agreed = True
    else:
        agreed = confirmed is not None and _related(confirmed, section) and (
            named is None or _related(section, named)
        )

    # Verification: the section chosen must be able to ANSWER the question from its own
    # text. Two independent reads share one bias -- both quote the sentence that names
    # the question's subject when the chapter never states the answer in prose (a place
    # shown only on a map, a fact in a caption) -- and agreement between them is then
    # worthless. So the chosen section is checked alone, then every other claimant, and
    # when none passes the judge is asked, with those ruled out, where else the answer
    # is. A question no section can answer on its own is kept where it was and flagged.
    verified: bool | None = None
    if hasattr(judge, "answerable"):
        section, verified, agreed = _verify(
            stem, chapter_label, headings, judge, document, texts, section,
            [c for c in claimants if not _related(c, section)], named, agreed, notes,
            anchor,
        )
    limit = 3
    if all_sections:
        # Every section the answer read's quotes sit in is one a part of the question is
        # answered in, and so is every section that laid a claim when the reads did not
        # settle on one: nobody reviews the row, so none of them is dropped.
        also = also + answer_quoted + (claimants if not agreed or verified is not True else [])
        limit = MAX_SECONDARIES
    secondaries = tuple(
        (s, headings.get(s, s)) for s in dict.fromkeys(also)
        if not _related(s, section)
    )[:limit]
    text = rationale
    if notes:
        text = " ".join([rationale, *[n[0].upper() + n[1:] + "." for n in notes]]).strip()
    if not agreed and retrieval_section is not None and not _related(section, retrieval_section):
        text = (
            f"{text} Retrieval within the chapter pointed at section {retrieval_section} "
            f"({headings.get(retrieval_section, '')}) instead."
        ).strip()
    return TopicPick(
        section, headings.get(section), "judge", agreed, retrieval_section, text,
        secondaries=secondaries, verified=verified, tier=tier,
    )


def _sub_sections(section: str, headings: dict[str, str]) -> list[str]:
    return [n for n in headings if n.startswith(section + ".")]


def _verify(
    stem: str, chapter_label: str, headings: dict[str, str], judge, document: str,
    texts: dict[str, str], section: str, others: list[str], named: str | None,
    agreed: bool, notes: list[str], anchor,
) -> tuple[str, bool | None, bool]:
    """(section, verified, agreed) after checking that the section can answer the
    question by itself -- see the caller. A section that passes is settled unless the
    book's own use of the question's terms contradicts it: answerability is the direct
    evidence the two reads' agreement only approximates."""
    checked: dict[str, str] = {}

    def can_answer(sec: str) -> bool | None:
        """True/False, or None when the judge could not be asked."""
        try:
            verdict = judge.answerable(
                stem, chapter_label, headings, document, sec, _sub_sections(sec, headings),
            )
        except Exception:  # noqa: BLE001 -- the unverified answer stands, as before
            logger.exception("topic answerability check failed for %s", chapter_label)
            return None
        answer = getattr(verdict, "answerable", None)
        if not isinstance(answer, bool):
            # not a verdict at all (a malformed or foreign response): not asked
            return None
        if not answer:
            return False
        # The quoted sentence has to sit under that section (or one of its
        # sub-sections), or the "yes" is a paraphrase from somewhere else.
        for q in getattr(verdict, "quotes", None) or []:
            q = _normalise(str(q))
            if len(q) < 12:
                continue
            for n, t in texts.items():
                if q in t and (n == sec or n.startswith(sec + ".")):
                    return True
        return False

    outcome = can_answer(section)
    if outcome is None:
        return section, None, agreed
    if outcome:
        return section, True, named is None or _related(section, named)
    checked[section] = headings.get(section, "")
    for other in others:
        if other in checked:
            continue
        outcome = can_answer(other)
        if outcome is None:
            return section, None, agreed
        if outcome:
            notes.append(
                f"section {section} ({headings.get(section, '')}) cannot answer the "
                f"question on its own; section {other} ({headings.get(other, '')}) can, "
                "and was taken"
            )
            return other, True, named is None or _related(other, named)
        checked[other] = headings.get(other, "")
    # Nothing with a claim can answer it. One relocating read, with the checked sections
    # ruled out, and its answer is verified the same way before it is believed.
    try:
        choice = judge.pick_from_document(
            stem, chapter_label, headings, document, mode="answer", exclude=dict(checked),
        )
        found, why, _ = anchor(choice, headings)
    except Exception:  # noqa: BLE001
        logger.exception("topic relocating read failed for %s", chapter_label)
        found, why = None, ""
    if found is not None and found not in checked and can_answer(found):
        notes.append(
            f"no section first named answers the question on its own; re-read with "
            f"{', '.join(checked)} ruled out, the judge found it answered in section "
            f"{found} ({headings.get(found, '')}): {why}"
        )
        return found, True, named is None or _related(found, named)
    notes.append(
        "no section of the chapter answers this question from its own text; the section "
        "that comes closest was kept"
    )
    return section, False, False
