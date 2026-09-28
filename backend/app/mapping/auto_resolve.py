"""Auto-resolving a family `choose_family` could not settle, without ever inventing facts
to do it.

``choose_family`` refuses to guess -- correctly, since a wrong guess silently mis-files a
mark under the wrong learning area forever, where a block at least gets a person's
attention. But a person's attention is exactly the thing a teacher scanning a paper in
production does not have: one unplaceable question in an otherwise ordinary paper used to
stall marks entry for every OTHER question in it too (see usePaperScan.ts's onMap). This
module gives the block two chances to resolve itself, in order, each against real book
text rather than the model's memory of what a textbook probably says:

1. The book's own text for the question's exact section number, when it was ingested --
   the same thing a person doing the PATCH by hand would read.
2. Failing that (no chunk carries that exact section number -- a numbering mismatch
   between what the paper's own retrieval named and how the book's chunks were split, or
   an ingestion gap), search the WHOLE chapter's ingested book chunks for the passages
   that actually match this question (lexical retrieval, plus semantic retrieval too when
   embeddings are configured -- the same two retrievers `locate()` fuses elsewhere in this
   pipeline, restricted to this one chapter) and ground the choice in whichever real
   passages come back. The book has already been read into the database in full -- this
   stage uses that, rather than falling back to the bare question text alone.

   Lexical alone is exactly the wrong tool for a chapter whose sibling topics share the
   same vocabulary throughout (a civics chapter's families all reuse words like "party",
   "election", "democracy" in every section) -- TF-IDF has nothing left to discriminate on
   once the topic words are common to the whole chapter, and can miss the one passage that
   actually settles it while surfacing several that merely mention the same nouns.
   Semantic retrieval reads meaning rather than word overlap, so the two are additive
   here exactly as they are in the main pass: this stage asks both (when a semantic index
   can be built at all) and offers the judge the union of what either one found, not
   whichever the lexical index alone turned up.

Either way, the model is handed real, quotable text and is required to quote it: the
quote is checked as a real substring of the passages it was shown before the answer is
trusted at all, so a rationale that cites something not actually there is caught rather
than quietly believed. Neither stage ever answers with a family the chapter did not
already propose, and neither stage is asked to reason from general knowledge of the
syllabus -- only from real passages handed to it in the same message. "None of these fit"
is always a valid, expected answer from either stage, and it is what a paper stays blocked
on when nothing groundable resolves it -- a small residual of blocked questions is the
honest floor here, not a bug.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.books import clean_sections
from app.llm import output_config
from app.models import BookChunk, ConceptFamilyProposal, TaxonomyNode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Resolution:
    """A family chosen for a section nobody had claimed yet, and why."""

    family: TaxonomyNode
    rationale: str
    #: "book_section" when grounded in the exact section's own text, "book_search" when
    #: that section had no chunk and the chapter's own chunks were searched instead -- a
    #: reviewer reads this to know how the placement was found.
    grounded_in: str
    #: the real section number the winning passage actually named, when search (rather
    #: than an exact section lookup) is what found it -- this, not the question's
    #: originally-detected section, is what gets recorded against the family, because it
    #: is the book's own fact rather than a possibly-mismatched guess at one.
    book_section: str | None = None


class _FamilyChoice(BaseModel):
    #: the code of the family the passage belongs to, verbatim from the list offered --
    #: or "none" when the judge is not confident any of them fits
    family_code: str = Field(description="one of the offered codes, or the literal 'none'")
    #: required even for "none", so a refusal is a reasoned one rather than a shrug
    rationale: str = Field(description="one sentence: why this family, or why none fits")
    #: verbatim words copied from the passages given -- checked as a real substring of
    #: them before this answer is trusted at all, so a rationale that cites something not
    #: actually there is caught rather than quietly believed
    quote: str = Field(description="exact words copied from the passages that justify the choice")


_SYSTEM = (
    "You are placing one exam question under the concept family it tests. You are given "
    "the question itself, one or more real passages from the textbook chapter it belongs "
    "to, and a list of candidate families already proposed for this chapter. Pick the "
    "family whose label the passages show this question is actually about. Quote the "
    "exact words of the PASSAGES (not the question) that justify your choice; do not "
    "paraphrase or invent wording, and do not reason from anything you recall about this "
    "textbook beyond what is shown below. If more than one family could fit, or none "
    "clearly does, or the passages do not actually settle it, say so honestly by "
    "answering 'none' -- a wrong placement is filed as fact and silently misleads every "
    "future report grouped by this family."
)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _quote_is_real(quote: str, source: str) -> bool:
    quote = quote.strip()
    return bool(quote) and _normalise(quote) in _normalise(source)


def _candidate_lines(candidates: list[TaxonomyNode], sections_of: dict[str, list[str]]) -> list[str]:
    lines = []
    for c in candidates:
        covers = sections_of.get(c.code) or []
        covers_note = f" (already covers section(s) {', '.join(covers)})" if covers else ""
        lines.append(f"- {c.code}: {c.label}{covers_note}")
    return lines


def _prompt(chapter_label: str, stem_text: str, passages: str,
            candidates: list[TaxonomyNode], sections_of: dict[str, list[str]]) -> str:
    return "\n".join([
        f"Chapter: {chapter_label}",
        "",
        "Question:",
        stem_text[:2000],
        "",
        "Passages from the book:",
        passages[:6000],
        "",
        "Candidate families:",
        *_candidate_lines(candidates, sections_of),
        "",
        "Which family code does this question belong to? Quote the exact words of the "
        "PASSAGES that justify it. Answer 'none' if they don't clearly settle it.",
    ])


def record_family_section(
    db: Session, *, winner: TaxonomyNode, chapter: TaxonomyNode, section: str,
    subject_codes: list[str], proposals: list[ConceptFamilyProposal], model: str,
    source: str, rationale: str,
) -> None:
    """Record that ``winner`` covers ``section``, the same way a person's PATCH to
    edit_family_sections would: every proposal row sharing this code, not just one run's,
    or an older run's row hands the same section right back as still uncovered.

    This is the one place either kind of correction -- an automated resolution here in
    auto_resolve, or a human settling a review-queue row in app.api.placement's confirm()
    -- writes back into the knowledge base itself. Without it, every occurrence of the
    same section-blind chapter is rediscovered from scratch on the next paper, corrected
    once, and forgotten; with it, the SAME correction is what choose_family reads on every
    later paper, so a chapter stops being permanently blocked the first time anyone (human
    or model) settles one of its questions.
    """
    matching = [p for p in proposals if p.code == winner.code]
    sections = sorted(set(clean_sections(matching[0].from_sections) if matching else []) | {section})
    if matching:
        for p in matching:
            p.from_sections = sections
    else:
        db.add(ConceptFamilyProposal(
            curriculum_version=winner.curriculum_version, subject_code=subject_codes[0],
            run_id=uuid.uuid4().hex, source=source, model=model,
            code=winner.code, label=winner.label, chapter_id=chapter.id,
            rationale=rationale,
            evidence=sections, from_sections=sections,
            applied_at=datetime.now(UTC).isoformat(),
        ))


def _ask(client, model: str, effort: str | None, chapter_label: str, stem_text: str,
          passages: str, candidates: list[TaxonomyNode],
          sections_of: dict[str, list[str]]) -> _FamilyChoice | None:
    extra = {"output_config": cfg} if (cfg := output_config(model, effort)) else {}
    response = client.messages.parse(
        model=model, max_tokens=4000, system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": _prompt(chapter_label, stem_text, passages, candidates, sections_of),
        }],
        output_format=_FamilyChoice, **extra,
    )
    choice = response.parsed_output
    if not _quote_is_real(choice.quote, passages):
        return None
    return choice


def resolve_blocked_family(
    db: Session,
    *,
    api_key: str | None,
    model: str,
    effort: str | None,
    subject_codes: list[str],
    section: str | None,
    stem_text: str | None,
    chapter: TaxonomyNode,
    candidates: list[TaxonomyNode],
    jina_api_key: str | None = None,
    embedding_model: str | None = None,
    embedding_dimensions: int | None = None,
) -> Resolution | None:
    """Try to settle a chapter+section `choose_family` could not, against the real book.

    ``jina_api_key``/``embedding_model``/``embedding_dimensions`` are the same settings
    the main placement pass already uses to add semantic retrieval alongside lexical --
    passed through here so stage 2 (see module docstring) is not stuck with lexical alone
    on exactly the chapters where it is weakest.

    Returns None -- leave it blocked -- whenever neither stage can be run at all (no
    classifier key, no question text, or no book chunks ingested anywhere in this
    chapter), neither stage's answer survives its guardrail (a code outside the
    candidates offered, or a quote that is not actually in the passages shown), OR the
    attempt itself fails for any reason at all (the `anthropic` package missing, a
    network error, a malformed response). This is a best-effort second chance for a
    question that was already going to be blocked -- a failure here must never turn into
    a failure of the whole classify/map job for every OTHER question in the paper, which
    is exactly what an unhandled exception here would do.
    """
    try:
        return _resolve_blocked_family(
            db, api_key=api_key, model=model, effort=effort, subject_codes=subject_codes,
            section=section, stem_text=stem_text, chapter=chapter, candidates=candidates,
            jina_api_key=jina_api_key, embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
        )
    except Exception:  # noqa: BLE001 -- see docstring: this must never escape
        logger.exception(
            "auto_resolve failed for chapter %s (subjects %s); leaving the question blocked",
            chapter.code, subject_codes,
        )
        return None


#: how far the winning family's best-matching chunk must lead the runner-up's, in raw
#: cosine similarity, before this is trusted to resolve on its own rather than left for a
#: person. Two families a hundredth of a point apart is not evidence, it is noise -- the
#: choice is exactly as unsettled as choose_family()'s own tie-breaking language says a
#: genuine tie is. 0.08 is a deliberately conservative first cut: cosine similarity on
#: short exam stems against paragraph-length book text rarely clusters tightly by chance,
#: so a real semantic match tends to clear this by a wide margin, while two sections of
#: the same chapter that both mention the same few nouns (a civics chapter's "party",
#: "election") tend to land within it -- exactly where a person should still look.
SEMANTIC_FAMILY_MARGIN = 0.08


def semantic_family_choice(
    chapter_chunks: list[BookChunk],
    candidates: list[TaxonomyNode],
    sections_of: dict[str, list[str]],
    stem_text: str,
    *,
    jina_api_key: str | None,
    embedding_model: str | None,
    embedding_dimensions: int | None,
    margin: float = SEMANTIC_FAMILY_MARGIN,
) -> Resolution | None:
    """Rank each candidate family by how closely ITS OWN book text matches the question,
    using the same embedding infrastructure retrieval already relies on -- reused rather
    than reinvented, and never asked to guess when the case really is ambiguous.

    This is the fallback `choose_family()` itself cannot offer: it only knows a literal
    section number, and the judge frequently has none to give it (chronological-order
    MCQs, Assertion-Reason, map-skill questions rarely cite one book section by name).
    Retrieval already computed real semantic similarity to find the chapter in the first
    place; this reuses that same signal to settle which family WITHIN the chapter, instead
    of discarding it and asking a person every time.

    Returns None -- leave it for the existing (slower, LLM-grounded) stages, or ultimately
    for a person -- whenever there is nothing to rank (no embeddings configured, no chunk
    carries a section any candidate family claims) or the top two families are within
    ``margin`` of each other: a near-tie is a genuine ambiguity, not a gap this should
    paper over.
    """
    if not jina_api_key or not stem_text or not stem_text.strip():
        return None

    section_owner: dict[str, str] = {}
    for code in (c.code for c in candidates):
        for section in sections_of.get(code, []):
            # A section two families both claim (rare, but choose_family's own claimants
            # branch allows it) is not this stage's to arbitrate -- it is exactly the
            # "several families draw on this section" case a person settles, so it is
            # left out of the ranking rather than silently handed to whichever family
            # happened to be seen first.
            section_owner[section] = "?" if section in section_owner else code
    section_owner = {s: code for s, code in section_owner.items() if code != "?"}
    if not section_owner:
        return None

    scored_chunks = [c for c in chapter_chunks if c.section_number in section_owner]
    if not scored_chunks:
        return None

    from app.ingest.jina import JinaEmbedder
    from app.ingest.probe import SemanticIndex

    index = SemanticIndex(scored_chunks, JinaEmbedder(
        jina_api_key, model=embedding_model, dimensions=embedding_dimensions,
    ))
    if not index.chunks:
        return None
    ranked = index.search(stem_text, k=len(index.chunks))
    if not ranked:
        return None

    best_by_family: dict[str, tuple] = {}  # code -> (score, candidate)
    for candidate in ranked:
        code = section_owner.get(candidate.section)
        if code is None:
            continue
        if code not in best_by_family or candidate.score > best_by_family[code][0]:
            best_by_family[code] = (candidate.score, candidate)

    if len(best_by_family) < 1:
        return None
    ranking = sorted(best_by_family.items(), key=lambda kv: -kv[1][0])
    winner_code, (top_score, top_chunk) = ranking[0]
    if len(ranking) > 1:
        _, (second_score, _) = ranking[1]
        if top_score - second_score < margin:
            return None  # near-tie: a person should settle it, not this

    winner = next((c for c in candidates if c.code == winner_code), None)
    if winner is None:
        return None
    lead = f"{top_score:.3f}" + (
        f" vs {ranking[1][1][0]:.3f} for the runner-up" if len(ranking) > 1 else ""
    )
    return Resolution(
        family=winner,
        rationale=(
            f"semantic similarity {lead} against \"{top_chunk.reference}\" "
            f"(section {top_chunk.section}): {top_chunk.text[:200]!r}"
        ),
        grounded_in="semantic_family",
        book_section=top_chunk.section,
    )


def _resolve_blocked_family(
    db: Session,
    *,
    api_key: str | None,
    model: str,
    effort: str | None,
    subject_codes: list[str],
    section: str | None,
    stem_text: str | None,
    chapter: TaxonomyNode,
    candidates: list[TaxonomyNode],
    jina_api_key: str | None = None,
    embedding_model: str | None = None,
    embedding_dimensions: int | None = None,
) -> Resolution | None:
    if not stem_text or not stem_text.strip():
        return None

    proposals = list(db.scalars(
        select(ConceptFamilyProposal).where(
            ConceptFamilyProposal.subject_code.in_(subject_codes),
            ConceptFamilyProposal.code.in_([c.code for c in candidates]),
        )
    ))
    sections_of: dict[str, list[str]] = {}
    for p in proposals:
        sections_of.setdefault(p.code, [])
        sections_of[p.code] = sorted(set(sections_of[p.code]) | set(clean_sections(p.from_sections)))

    # Stage 0: pure semantic ranking of the chapter's own candidate families against the
    # question, no LLM call needed -- cheap, and it is exactly the signal retrieval
    # already computed to find this chapter in the first place, just not yet reused to
    # pick a family within it. Only acts when one family clearly leads; a near-tie falls
    # through to the slower, LLM-grounded stages below, same as before this existed.
    chapter_chunks_for_semantic = list(db.scalars(
        select(BookChunk).where(
            BookChunk.subject_code.in_(subject_codes),
            BookChunk.node_id == chapter.id,
        )
    ))
    semantic_resolution = semantic_family_choice(
        chapter_chunks_for_semantic, candidates, sections_of, stem_text,
        jina_api_key=jina_api_key, embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
    )
    if semantic_resolution is not None:
        if semantic_resolution.book_section:
            record_family_section(
                db, winner=semantic_resolution.family, chapter=chapter,
                section=semantic_resolution.book_section,
                subject_codes=subject_codes, proposals=proposals, model="semantic-embedding",
                source="auto_resolve_semantic_family",
                rationale=f"auto-resolved from semantic_family: {semantic_resolution.rationale}",
            )
        return semantic_resolution

    if not api_key:
        return None

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    def apply_and_return(choice: _FamilyChoice, grounded_in: str, book_section: str | None):
        winner = next((c for c in candidates if c.code == choice.family_code), None)
        if winner is None:
            return None
        recorded_section = book_section or section
        rationale = f'{choice.rationale} (quoted: "{choice.quote}")'
        if recorded_section:
            record_family_section(
                db, winner=winner, chapter=chapter, section=recorded_section,
                subject_codes=subject_codes, proposals=proposals, model=model,
                source=f"auto_resolve_{grounded_in}",
                rationale=f"auto-resolved from {grounded_in}: {rationale}",
            )
        return Resolution(
            family=winner, rationale=rationale, grounded_in=grounded_in,
            book_section=recorded_section,
        )

    # Stage 1: the book's own text for the question's exact section number, when a chunk
    # carries it -- the strongest signal, because it is precisely where the book itself
    # says this question's content lives.
    if section:
        exact_chunks = list(db.scalars(
            select(BookChunk).where(
                BookChunk.subject_code.in_(subject_codes),
                BookChunk.section_number == section,
            )
        ))
        exact_text = "\n\n".join(c.text for c in exact_chunks if c.text)
        if exact_text.strip():
            choice = _ask(
                client, model, effort, chapter.label, stem_text, exact_text,
                candidates, sections_of,
            )
            if choice is None or choice.family_code == "none":
                # An honest "none" (or a quote that didn't check out) from the exact
                # section's own text is a considered answer, not a gap to paper over by
                # widening the search -- it stays blocked rather than falling through.
                return None
            return apply_and_return(choice, "book_section", section)

    # Stage 2: no chunk named this exact section (a numbering mismatch, or a genuine
    # ingestion gap), so search the WHOLE chapter's ingested book chunks -- already read
    # into the database in full -- for the passages that actually match this question,
    # the same way `locate()` searches the whole book to find the chapter in the first
    # place. This is still the book's own words, just found by search rather than an
    # exact section-number lookup.
    from app.ingest.probe import LexicalIndex

    chapter_chunks = list(db.scalars(
        select(BookChunk).where(
            BookChunk.subject_code.in_(subject_codes),
            BookChunk.node_id == chapter.id,
        )
    ))
    if not chapter_chunks:
        return None
    found = LexicalIndex(chapter_chunks).search(stem_text, k=3)

    # Semantic retrieval, additive to lexical rather than a replacement for it: a chapter
    # whose families all draw on the same handful of words (a civics chapter's sections
    # each say "party", "election", "democracy" throughout) gives TF-IDF nothing to
    # discriminate on, and lexical search alone can miss the one passage that actually
    # settles the question while surfacing several that merely share its nouns. Only
    # attempted when embeddings are actually configured and this chapter's chunks
    # actually carry them -- SemanticIndex itself reports 0 usable chunks otherwise, and
    # that is silently fine, not an error.
    if jina_api_key and any(getattr(c, "embedding", None) for c in chapter_chunks):
        from app.ingest.jina import JinaEmbedder
        from app.ingest.probe import SemanticIndex

        semantic = SemanticIndex(chapter_chunks, JinaEmbedder(
            jina_api_key, model=embedding_model, dimensions=embedding_dimensions,
        ))
        seen = {c.chunk_id for c in found}
        for candidate in semantic.search(stem_text, k=3):
            if candidate.chunk_id not in seen:
                seen.add(candidate.chunk_id)
                found.append(candidate)

    if not found:
        return None
    passages = "\n\n".join(f"[{c.reference or c.section or '?'}] {c.text}" for c in found if c.text)
    if not passages.strip():
        return None

    choice = _ask(
        client, model, effort, chapter.label, stem_text, passages, candidates, sections_of,
    )
    if choice is None or choice.family_code == "none":
        return None
    # The section of whichever retrieved passage actually contains the quote -- a real
    # fact read off the specific passage that justified the choice, not the (possibly
    # mismatched) section this question was originally detected under, and not just the
    # top search result if a lower-ranked passage is the one actually quoted.
    book_section = next(
        (c.section for c in found if c.text and _quote_is_real(choice.quote, c.text)), None,
    )
    return apply_and_return(choice, "book_search", book_section)
