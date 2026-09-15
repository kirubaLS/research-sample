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

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

#: Section headings that are not learning areas. A student is not weak at "Introduction".
NOT_A_FAMILY = frozenset({"introduction", "summary"})


def dominant_script(text: str) -> str | None:
    """The Unicode script most of ``text``'s letters belong to, or ``None`` if it has none.

    Generic on purpose: it reads the character data, not a table of subject codes to
    languages, so it works for whichever script a book turns out to use without anyone
    having enumerated it in advance. "TAMIL LETTER..." and "DEVANAGARI LETTER..." both come
    straight out of ``unicodedata.name`` -- the first word of the Unicode character name is
    its script, for every script this app will ever see a book in.
    """
    counts: Counter[str] = Counter()
    for ch in text:
        if not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        counts[name.split(" ", 1)[0]] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def script_mismatch(label: str, reference_text: str) -> tuple[str, str] | None:
    """``(label_script, reference_script)`` if they disagree, else ``None``.

    ``reference_text`` should be real content already known to belong to the same chapter
    or subject -- other section labels, book chunk text -- so the comparison is always
    against what that book actually contains, never a hardcoded expectation.
    """
    label_script = dominant_script(label)
    reference_script = dominant_script(reference_text)
    if label_script is None or reference_script is None:
        return None
    if label_script == reference_script:
        return None
    return label_script, reference_script


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


def slugify(label: str) -> str:
    """A stable code from a label. Stable is the whole point: this outlives the label."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    # drop the filler that makes codes long without making them distinct
    parts = [p for p in cleaned.split("_") if p not in {"of", "a", "the", "to", "and", "on"}]
    return "_".join(parts)[:40].upper()


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
        label = section_label.strip()
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
