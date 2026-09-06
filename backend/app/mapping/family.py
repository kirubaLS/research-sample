"""Choosing which concept family a question belongs to.

The family is the axis every trend report groups by, so which one a question lands in
decides what a school is told it is weak at. Two steps place a question -- retrieval, then
the judge reading the passages retrieval found -- and both have to answer this the same
way, or the same question moves family depending on which step touched it last.

So the rule lives here once. It reads the book's own record of which sections each family
draws on; nothing about any subject, chapter or section is written into it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


class Family(Protocol):
    """Whatever carries a family's identity. A taxonomy node satisfies this."""

    code: str
    label: str


@dataclass(frozen=True)
class Choice:
    """The family chosen, and what is unsettled about the choice."""

    family: Family | None
    #: why nobody can choose, when family is None -- said in full, for a person to act on
    blocked: str | None = None
    #: chosen, but more than one candidate had an equal claim
    unsettled: str | None = None


def choose_family(
    candidates: Sequence[Family],
    sections_of: Mapping[str, set[str]],
    section: str | None,
    chapter_label: str,
) -> Choice:
    """Which family of a chapter a question in ``section`` belongs to.

    A run proposes many families per chapter and several legitimately draw on one section,
    so more than one claimant is normal rather than an error. Where that happens the
    narrowest claim wins -- a family covering only 13.2 fits a question in 13.2 better than
    one covering 13.2, 13.3 and 13.4 -- and the code breaks ties, so placing the same paper
    twice gives the same answer. Picking whichever the database returned first was neither
    of those things.

    A chapter with exactly one family and no section to match on falls to that family:
    there is nothing to choose between. With several and no section, nothing can choose,
    and saying so is the only honest answer.
    """
    if not candidates:
        return Choice(
            None,
            blocked=(
                f"no concept family exists for {chapter_label}. Open the book screen for "
                f"this subject and create the families it proposes."
            ),
        )

    claimants = [
        f for f in candidates if section and section in sections_of.get(f.code, set())
    ]
    if len(claimants) == 1:
        return Choice(claimants[0])
    if claimants:
        return Choice(
            min(claimants, key=lambda f: (len(sections_of.get(f.code, ())), f.code)),
            unsettled=(
                f"{len(claimants)} families of {chapter_label} draw on section {section}; "
                f"the narrowest was taken and a person should settle it"
            ),
        )
    if len(candidates) == 1:
        return Choice(candidates[0])
    return Choice(
        None,
        blocked=(
            f"{len(candidates)} families exist for {chapter_label} and none claims "
            + (
                f"section {section}, which is where the book puts this question"
                if section
                else "a section, and the passages that matched name no section either"
            )
            + ". Settle it in review, or re-create the families from the book so each "
            "one records the section it covers."
        ),
    )
