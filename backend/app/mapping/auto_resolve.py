"""Auto-resolving a family `choose_family` could not settle, when the book text for the
question's own section is available to check the choice against.

``choose_family`` refuses to guess -- correctly, since a wrong guess silently mis-files a
mark under the wrong learning area forever, where a block at least gets a person's
attention. But a person's attention is exactly the thing a teacher scanning a paper in
production does not have: one unplaceable question in an otherwise ordinary paper used to
stall marks entry for every OTHER question in it too (see usePaperScan.ts's onMap). This
module gives the block one more chance to resolve itself, grounded in the same section
text a person doing the PATCH by hand would read -- and only ever a candidate the chapter
itself already proposed, never a family invented on the spot.

Left blocked (returns None) whenever grounding is unavailable, so a paper on a subject with
no classifier key configured, or a chapter with no ingested book text for that section,
behaves exactly as before: still a block, still a person's to settle.
"""

from __future__ import annotations

from dataclasses import dataclass

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


class _FamilyChoice(BaseModel):
    #: the code of the family the section belongs to, verbatim from the list offered --
    #: or "none" when the judge is not confident any of them fits
    family_code: str = Field(description="one of the offered codes, or the literal 'none'")
    rationale: str = Field(description="one sentence: why this family, or why none fits")


_SYSTEM = (
    "You are placing one section of a school textbook chapter under the concept family it "
    "belongs to. You are given the section's own text and a list of candidate families "
    "already proposed for this chapter, each with its label and, where known, the other "
    "sections it already covers. Pick the family whose label the section text is actually "
    "about. If more than one could fit, or none clearly does, say so honestly by "
    "answering 'none' rather than guessing -- a wrong placement is filed as fact and "
    "silently misleads every future report grouped by this family."
)


def _prompt(chapter_label: str, section_text: str, candidates: list[TaxonomyNode],
            sections_of: dict[str, list[str]]) -> str:
    lines = [
        f"Chapter: {chapter_label}",
        "",
        "Section text:",
        section_text[:4000],
        "",
        "Candidate families:",
    ]
    for c in candidates:
        covers = sections_of.get(c.code) or []
        covers_note = f" (already covers section(s) {', '.join(covers)})" if covers else ""
        lines.append(f"- {c.code}: {c.label}{covers_note}")
    lines.append("")
    lines.append("Which family code does the section text belong to? Answer 'none' if unsure.")
    return "\n".join(lines)


def resolve_blocked_family(
    db: Session,
    *,
    api_key: str | None,
    model: str,
    effort: str | None,
    subject_codes: list[str],
    section: str | None,
    chapter: TaxonomyNode,
    candidates: list[TaxonomyNode],
) -> Resolution | None:
    """Try to settle a chapter+section `choose_family` could not, by reading the book.

    Returns None -- leave it blocked -- whenever any precondition for a grounded answer is
    missing: no classifier key, no section to look up, or no ingested text for it. Also
    None when the model itself answers 'none' or names a code that was never offered,
    because a candidate list is the only universe a wrong answer could be caught in.
    """
    if not api_key or not section:
        return None

    chunks = list(db.scalars(
        select(BookChunk).where(
            BookChunk.subject_code.in_(subject_codes),
            BookChunk.section_number == section,
        )
    ))
    if not chunks:
        return None
    section_text = "\n\n".join(c.text for c in chunks if c.text)
    if not section_text.strip():
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
    response = client.messages.parse(
        model=model,
        max_tokens=4000,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": _prompt(chapter.label, section_text, candidates, sections_of),
        }],
        output_format=_FamilyChoice,
        **extra,
    )
    choice = response.parsed_output
    if choice.family_code == "none":
        return None
    winner = next((c for c in candidates if c.code == choice.family_code), None)
    if winner is None:
        return None

    # Record the correction the same way a person's PATCH would (see
    # edit_family_sections): every proposal row sharing this code, not just one run's,
    # or an older run's row hands the same section right back as still uncovered.
    matching = [p for p in proposals if p.code == winner.code]
    sections = sorted(set(clean_sections(matching[0].from_sections) if matching else []) | {section})
    if matching:
        for p in matching:
            p.from_sections = sections
    else:
        import uuid
        from datetime import UTC, datetime

        db.add(ConceptFamilyProposal(
            curriculum_version=winner.curriculum_version, subject_code=subject_codes[0],
            run_id=uuid.uuid4().hex, source="auto_resolve", model=model,
            code=winner.code, label=winner.label, chapter_id=chapter.id,
            rationale=f"auto-resolved by classifier: {choice.rationale}",
            evidence=sections, from_sections=sections,
            applied_at=datetime.now(UTC).isoformat(),
        ))

    return Resolution(family=winner, rationale=choice.rationale)
