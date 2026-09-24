"""Auto-resolving a family `choose_family` could not settle, without ever inventing facts
to do it.

``choose_family`` refuses to guess -- correctly, since a wrong guess silently mis-files a
mark under the wrong learning area forever, where a block at least gets a person's
attention. But a person's attention is exactly the thing a teacher scanning a paper in
production does not have: one unplaceable question in an otherwise ordinary paper used to
stall marks entry for every OTHER question in it too (see usePaperScan.ts's onMap). This
module gives the block two chances to resolve itself, in order, each against something
real rather than the model's memory of what a textbook probably says:

1. The book's own text for the question's section, when it was ingested -- the same thing
   a person doing the PATCH by hand would read.
2. Failing that (no chunk was ingested for that exact section), the question's OWN text --
   real, teacher-confirmed exam content, just not the book's. This is a weaker signal, so
   it is held to a stricter guardrail: the model must quote the exact words of the
   question that justify its answer, and that quote is checked as a real substring of the
   question before the answer is trusted at all. A rationale that cannot point at real
   words in the real question is discarded exactly like a request for "none".

Neither stage ever answers with a family the chapter did not already propose, and neither
stage is asked to reason from general knowledge of the syllabus -- only from a real
passage handed to it in the same message. "None of these fit" is always a valid, expected
answer from either stage, and it is what a paper stays blocked on when nothing groundable
resolves it -- a small residual of blocked questions is the honest floor here, not a bug.
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class Resolution:
    """A family chosen for a section nobody had claimed yet, and why."""

    family: TaxonomyNode
    rationale: str
    #: "book" when grounded in the book's own section text, "question" when the book had
    #: no chunk for this section and the question's own words were used instead -- a
    #: reviewer reads this to know how much to trust the placement.
    grounded_in: str


class _FamilyChoice(BaseModel):
    #: the code of the family the passage belongs to, verbatim from the list offered --
    #: or "none" when the judge is not confident any of them fits
    family_code: str = Field(description="one of the offered codes, or the literal 'none'")
    #: required even for "none", so a refusal is a reasoned one rather than a shrug
    rationale: str = Field(description="one sentence: why this family, or why none fits")


class _GroundedFamilyChoice(_FamilyChoice):
    #: verbatim words copied from the passage given -- checked as a real substring of it
    #: before this answer is trusted at all, so a rationale that cites something not
    #: actually there is caught rather than quietly believed
    quote: str = Field(description="exact words copied from the passage that justify the choice")


_BOOK_SYSTEM = (
    "You are placing one section of a school textbook chapter under the concept family it "
    "belongs to. You are given the section's own text and a list of candidate families "
    "already proposed for this chapter, each with its label and, where known, the other "
    "sections it already covers. Pick the family whose label the section text is actually "
    "about. If more than one could fit, or none clearly does, say so honestly by "
    "answering 'none' rather than guessing -- a wrong placement is filed as fact and "
    "silently misleads every future report grouped by this family."
)

_QUESTION_SYSTEM = (
    "You are placing one exam question under the concept family it tests, using ONLY the "
    "question's own text below -- the book's own passage for this section was not "
    "available, so this is your only real evidence. You are given the question and a list "
    "of candidate families already proposed for its chapter. Quote the exact words of the "
    "question that justify your choice; do not paraphrase or invent wording. If the "
    "question does not clearly say enough to choose, answer 'none' -- a wrong placement is "
    "filed as fact and silently misleads every future report grouped by this family. Never "
    "reason from what you recall the textbook chapter generally covers: judge only the "
    "words given."
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


def _book_prompt(chapter_label: str, section_text: str, candidates: list[TaxonomyNode],
                  sections_of: dict[str, list[str]]) -> str:
    return "\n".join([
        f"Chapter: {chapter_label}",
        "",
        "Section text:",
        section_text[:4000],
        "",
        "Candidate families:",
        *_candidate_lines(candidates, sections_of),
        "",
        "Which family code does the section text belong to? Answer 'none' if unsure.",
    ])


def _question_prompt(chapter_label: str, stem_text: str, candidates: list[TaxonomyNode],
                      sections_of: dict[str, list[str]]) -> str:
    return "\n".join([
        f"Chapter: {chapter_label}",
        "",
        "Question text:",
        stem_text[:2000],
        "",
        "Candidate families:",
        *_candidate_lines(candidates, sections_of),
        "",
        "Which family code does this question test? Quote the exact words of the question "
        "that justify it. Answer 'none' if the question does not clearly say enough.",
    ])


def _apply_correction(
    db: Session, *, winner: TaxonomyNode, chapter: TaxonomyNode, section: str,
    subject_codes: list[str], proposals: list[ConceptFamilyProposal], model: str,
    source: str, rationale: str,
) -> None:
    """Record the correction the same way a person's PATCH would (see
    edit_family_sections): every proposal row sharing this code, not just one run's, or an
    older run's row hands the same section right back as still uncovered."""
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
            rationale=f"auto-resolved from {source}: {rationale}",
            evidence=sections, from_sections=sections,
            applied_at=datetime.now(UTC).isoformat(),
        ))


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
) -> Resolution | None:
    """Try to settle a chapter+section `choose_family` could not, against something real.

    Returns None -- leave it blocked -- whenever neither stage can be run at all (no
    classifier key, or nothing real to ground either one in) or neither stage's answer
    survives its guardrail: a code outside the candidates offered, or -- for the
    question-text stage -- a quote that is not actually in the question.
    """
    if not api_key:
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

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    extra = {"output_config": cfg} if (cfg := output_config(model, effort)) else {}

    # Stage 1: the book's own text for this exact section, when it was ingested.
    section_text = None
    if section:
        chunks = list(db.scalars(
            select(BookChunk).where(
                BookChunk.subject_code.in_(subject_codes),
                BookChunk.section_number == section,
            )
        ))
        joined = "\n\n".join(c.text for c in chunks if c.text)
        section_text = joined if joined.strip() else None

    if section_text is not None:
        response = client.messages.parse(
            model=model, max_tokens=4000, system=_BOOK_SYSTEM,
            messages=[{
                "role": "user",
                "content": _book_prompt(chapter.label, section_text, candidates, sections_of),
            }],
            output_format=_FamilyChoice, **extra,
        )
        choice = response.parsed_output
        winner = next((c for c in candidates if c.code == choice.family_code), None)
        if winner is not None:
            _apply_correction(
                db, winner=winner, chapter=chapter, section=section,
                subject_codes=subject_codes, proposals=proposals, model=model,
                source="auto_resolve_book", rationale=choice.rationale,
            )
            return Resolution(family=winner, rationale=choice.rationale, grounded_in="book")
        # An honest "none" (or a name outside the list) from a real reading of the book's
        # own section text is a considered answer, not a gap to paper over with a weaker
        # signal -- it stays blocked rather than falling through to stage 2.
        return None

    # Stage 2: no book chunk was ingested for this section at all, so there is nothing of
    # the book's own to check a book-grounded answer against. Fall back to the question's
    # own text -- still real, still what the model is asked to quote from -- only when
    # there is a section number in the first place; with none at all, choose_family's own
    # blocked message already said so and there is no extra signal here to add.
    if not section or not stem_text or not stem_text.strip():
        return None

    response = client.messages.parse(
        model=model, max_tokens=4000, system=_QUESTION_SYSTEM,
        messages=[{
            "role": "user",
            "content": _question_prompt(chapter.label, stem_text, candidates, sections_of),
        }],
        output_format=_GroundedFamilyChoice, **extra,
    )
    choice = response.parsed_output
    if not _quote_is_real(choice.quote, stem_text):
        return None
    winner = next((c for c in candidates if c.code == choice.family_code), None)
    if winner is None:
        return None

    _apply_correction(
        db, winner=winner, chapter=chapter, section=section,
        subject_codes=subject_codes, proposals=proposals, model=model,
        source="auto_resolve_question", rationale=f'{choice.rationale} (quoted: "{choice.quote}")',
    )
    return Resolution(
        family=winner,
        rationale=f'{choice.rationale} (quoted: "{choice.quote}")',
        grounded_in="question",
    )
