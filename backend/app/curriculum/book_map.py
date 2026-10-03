"""The structure of a book-map chapter -- its units, their printed numbers, titles, kinds
and parents -- read from the audited reference files under ``backend/reference``.

Only the structure is kept: no body text. It answers questions the chunk table cannot,
because a chunk carries a section number and a reference but not what kind of unit it came
from: "2.1 Rat-Hole Mining" in Minerals and Energy Resources is a BOX that happens to
occupy number 2.1, not a section, and "4.1 Conventional Sources of Energy" is a real
heading with no text of its own (everything under it is 4.1.1-4.1.4).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[2] / "reference"

#: subject code -> its units file, as scripts/import_book_map.py reads them
UNIT_FILES = {
    "X.HIST": "book_map/history/history_units.json",
    "X.GEO": "book_map/geography/geography_units.json",
    "X.POL": "book_map/politics/politics_units.json",
    "X.ECO": "book_map/economics/economics_units.json",
    "X.SCI": "book_map_science/science_units.json",
}

#: unit kinds that are never a topic of their own: their text belongs to their parent
NOT_A_TOPIC = frozenset({"box"})
#: unit kinds that are the chapter itself rather than one of its sections
CHAPTER_LEVEL = frozenset({"intro", "summary"})

#: the pseudo-section for a chapter's unnumbered introduction or conclusion: "chapter
#: level, no subtopic". Its text is all chapter level, but only the introduction's family
#: IS section 0; a summary or conclusion family is deep (kept for questions already on it)
INTRO_SECTION = "0"
INTRO_KIND = "intro"
INTRO_TITLE = "Introduction"


@dataclass(frozen=True)
class Unit:
    number: str | None
    title: str
    kind: str
    #: the printed number of the parent unit, or None for a top-level unit
    parent: str | None
    #: the concept-family code the book map assigns this unit (its "catalog")
    catalog: str | None = None


def depth(section: str | None) -> int:
    return len(section.split(".")) if section else 0


#: one part of a section number: digits and, when the book prints one number twice, one
#: trailing lowercase letter for the second ("2.4b" in The Making of a Global World)
_PART = re.compile(r"^(\d+)([a-z]?)$")


def section_key(section: str | None) -> tuple[tuple[int, str], ...]:
    """Book order for section numbers: "2.4" < "2.4b" < "2.5" < "2.10". Parts that are
    not numbers are left out, so "" and "0" sort first."""
    out = []
    for part in (section or "").split("."):
        match = _PART.match(part)
        if match:
            out.append((int(match.group(1)), match.group(2)))
    return tuple(out)


@lru_cache(maxsize=8)
def _subject_units(subject_code: str) -> dict[str, tuple[Unit, ...]]:
    rel = UNIT_FILES.get(subject_code)
    if rel is None or not (REFERENCE / rel).exists():
        return {}
    data = json.loads((REFERENCE / rel).read_text())
    out: dict[str, tuple[Unit, ...]] = {}
    for chapter in data:
        by_id = {u["id"]: u for u in chapter["units"]}
        units = []
        for u in chapter["units"]:
            parent = by_id.get(u.get("parent") or "")
            units.append(Unit(
                number=str(u["number"]) if u.get("number") else None,
                title=(u.get("title") or "").strip(),
                kind=u.get("kind") or "section",
                parent=str(parent["number"]) if parent and parent.get("number") else None,
                catalog=u.get("catalog") or None,
            ))
        out[chapter["code"]] = tuple(units)
    return out


def chapter_units(chapter_code: str) -> tuple[Unit, ...] | None:
    """The chapter's units in book order, or None when it is not a book-map chapter."""
    subject = chapter_code.rsplit(".", 1)[0]
    return _subject_units(subject).get(chapter_code)


def heading_label(number: str, title: str) -> str:
    """'4.1 Conventional Sources of Energy' -- the same "{number} {title}" form the
    book-map chunk references and the subtopic node labels use."""
    return f"{number} {title}" if title else number


def intro_label(title: str | None) -> str:
    """The title section 0 shows. An introduction that carries examinable content is
    titled for it in the book map ("Introduction: Types and Classification of
    Resources"); every other introduction, Politics' printed "Overview" included, shows
    as plain "Introduction"."""
    title = (title or "").strip()
    return title if title.startswith(INTRO_TITLE + ":") else INTRO_TITLE


def major_headings(chapter_code: str, max_depth: int) -> dict[str, str] | None:
    """The selectable topics of a chapter at ``max_depth``: every numbered unit no deeper
    than that which is not a box, whether or not it has text of its own, plus "0
    Introduction" when the chapter has an unnumbered introduction. In book order. None
    for a chapter the book map does not describe."""
    units = chapter_units(chapter_code)
    if units is None:
        return None
    out: dict[str, str] = {}
    intro = next((u for u in units if u.number is None and u.kind == INTRO_KIND), None)
    if intro is not None:
        out[INTRO_SECTION] = heading_label(INTRO_SECTION, intro_label(intro.title))
    numbered = [
        u for u in units
        if u.number is not None and u.kind not in NOT_A_TOPIC and depth(u.number) <= max_depth
    ]
    for u in sorted(numbered, key=lambda u: section_key(u.number)):
        out.setdefault(u.number, heading_label(u.number, u.title))
    return out


def unit_by_number(chapter_code: str) -> dict[str, Unit]:
    return {u.number: u for u in chapter_units(chapter_code) or () if u.number}


def major_of(chapter_code: str, section: str | None, max_depth: int) -> str | None:
    """The selectable topic ``section`` belongs to at ``max_depth``: itself when it is
    one; its parent when it is a box; otherwise its nearest ancestor that is one. An
    unnumbered (introduction) section maps to "0" when the chapter has one. Returns the
    section unchanged for a chapter the book map does not describe."""
    headings = major_headings(chapter_code, max_depth)
    if headings is None:
        return section
    if section is None or section == "":
        return INTRO_SECTION if INTRO_SECTION in headings else None
    units = unit_by_number(chapter_code)
    current: str | None = section
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        if current in headings:
            return current
        unit = units.get(current)
        if unit is not None and unit.kind in NOT_A_TOPIC and unit.parent:
            current = unit.parent
            continue
        current = current.rsplit(".", 1)[0] if "." in current else None
    return None


def family_topic(chapter_code: str, family_code: str, max_depth: int) -> str | None:
    """The major topic a book-map family IS, when its own unit is a selectable topic at
    ``max_depth`` ("0" for an introduction's family); None when its unit is deeper than
    that, a box, or a summary or conclusion -- a family that is not a major topic of its
    own -- or when the book map does not know the family."""
    headings = major_headings(chapter_code, max_depth) or {}
    for u in chapter_units(chapter_code) or ():
        if u.catalog != family_code:
            continue
        if u.number is None:
            return INTRO_SECTION if INTRO_SECTION in headings and u.kind == INTRO_KIND else None
        return u.number if u.number in headings else None
    return None
