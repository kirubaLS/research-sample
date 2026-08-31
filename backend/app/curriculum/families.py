"""Proposing concept families from a loaded book.

A **concept family** is the axis a report compares against itself over time. It sits
between the two things the book already gives us, both of which are unusable for that:

* **Chapter is too coarse.** "Weak in Surface Areas and Volumes" is not something a teacher
  can act on -- the chapter contains surface area and volume of composite solids, and a
  student can be fine at one and lost in the other.
* **Section is too fine and, worse, unstable.** Section numbers move when NCERT reprints,
  and a question often spans two. A trend keyed on "12.2" breaks the year the book is
  renumbered, silently, and every historical comparison becomes wrong.

A family is a stable learning area a teacher would recognise as one thing to reteach. Held
constant across cycles, it is what makes "the class improved" a measurement rather than a
hope: cycle one asks a cone-and-hemisphere question, cycle two asks a cylinder-and-cone
one, and because both are Volume of Composite Solids the two scores are comparable.

They are **proposed** here and never applied automatically. Renaming a family after a class
has been tested breaks every trend that references it, so the list is a commitment, and a
commitment is a person's to make.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

#: Section headings that are not learning areas. A student is not weak at "Introduction".
NOT_A_FAMILY = frozenset({"introduction", "summary"})


@dataclass(frozen=True)
class Proposal:
    code: str
    label: str
    chapter_code: str
    chapter_label: str
    #: the section it came from, so a reviewer can see the source of the suggestion
    from_section: str
    #: how much taught content sits under it -- a family with nothing behind it is a
    #: heading, not a learning area
    chunks: int


def readable(label: str) -> str:
    """Undo a typographic choice, without changing a word.

    Science sets its section headings in full capitals -- that is how the book prints
    them, not what they are called. Carried through, a report would tell a teacher the
    student is weak at "HOW DO OUR ACTIVITIES AFFECT THE ENVIRONMENT?".

    Sentence case rather than title case: these headings are as often questions as noun
    phrases, and "How Do Our Activities Affect The Environment?" is no better. A label
    that is not entirely uppercase is left exactly as the book set it -- Maths already
    prints "Volume of a Combination of Solids" and there is nothing to fix.
    """
    if not label.isupper():
        return label
    out = label.lower()
    for i, ch in enumerate(out):
        if ch.isalpha():
            return out[:i] + ch.upper() + out[i + 1:]
    return out


#: Long enough to stay readable, short enough for a report column and an index.
CODE_CHARS = 40
#: Reserved at the end of a truncated code for the digest that keeps it unique.
DIGEST_CHARS = 6


def slugify(label: str) -> str:
    """A stable code from a label. Stable is the whole point: this outlives the label.

    A plain character cut was wrong in two ways, and codes are never renamed, so both
    would have been permanent. It severed words -- "Trigonometric ratios of standard
    angles (0 deg, 30 deg...)" became ...ANGLES_0_3, which reads as nought point three --
    and two labels sharing a 40-character prefix produced one code for two families,
    silently merging two trends into one row.

    So a truncated code is cut at a word boundary and carries a short digest of the whole
    label. The digest makes it unique by construction rather than by luck; the word
    boundary keeps it legible to whoever reads it in a report six months from now. A label
    that fits is untouched, which is most of them and every one written so far.
    """
    cleaned = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    # drop the filler that makes codes long without making them distinct
    parts = [p for p in cleaned.split("_") if p not in {"of", "a", "the", "to", "and", "on"}]
    full = "_".join(parts)
    if len(full) <= CODE_CHARS:
        return full.upper()

    digest = hashlib.sha256(label.strip().encode("utf-8")).hexdigest()[:DIGEST_CHARS]
    room = CODE_CHARS - DIGEST_CHARS - 1
    kept: list[str] = []
    for part in parts:
        if len("_".join([*kept, part])) > room:
            break
        kept.append(part)
    stem = "_".join(kept) or full[:room].rstrip("_")
    return f"{stem}_{digest}".upper()


def propose(
    sections: list[tuple[str, str, str, int]],
    subject_code: str,
) -> list[Proposal]:
    """Candidate families from a chapter's section headings.

    ``sections`` is (chapter code, chapter label, section label, chunks beneath it).

    The book's own section headings are the best starting point available: they are what
    the authors thought the divisions of the chapter were, and a teacher recognises them.
    But they are a starting point -- a reviewer merges the ones that are one idea and drops
    the ones that are not learning areas.
    """
    out: list[Proposal] = []
    seen: set[str] = set()
    for chapter_code, chapter_label, section_label, chunks in sections:
        label = readable(section_label.strip())
        if label.lower() in NOT_A_FAMILY:
            continue
        code = f"{subject_code}.CF.{slugify(label)}"
        if code in seen:
            continue
        seen.add(code)
        out.append(
            Proposal(
                code=code,
                label=label,
                chapter_code=chapter_code,
                chapter_label=chapter_label,
                from_section=section_label,
                chunks=chunks,
            )
        )
    return out
