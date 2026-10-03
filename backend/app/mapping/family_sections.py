"""Which sections each concept family claims -- the table ``choose_family`` reads.

Built from ``concept_family_proposal.from_sections``. Two switches change how:

* ``book_map_only_subtopics``: a family's sections are the UNION over every proposal row
  of its code, as ``auto_resolve`` already reads them. Off: the last row read wins, as
  before (rows come back in no fixed order, so which one wins was never defined).
* ``topic_depth_cap``: for a capped subject every section is cut to the major topic
  ("4.1.2" -> "4.1"), and a family whose own book-map unit is not a major topic -- a
  deeper unit (Coal, 4.1.1) or a box (Rat-Hole Mining) -- is marked ``deep``. Deep
  families stay in the database and on the questions already filed under them; a new
  placement never picks one, because several of them would otherwise claim the same major
  topic (Coal, Petroleum, Natural Gas and Electricity all become 4.1).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass
class FamilySections:
    #: family code -> the sections it claims, as choose_family reads them
    sections_of: dict[str, set[str]] = field(default_factory=dict)
    #: family code -> its sections before any cut, so an exact claim can be preferred
    exact_of: dict[str, set[str]] = field(default_factory=dict)
    #: codes that must not be picked for a new placement (topic_depth_cap)
    deep: set[str] = field(default_factory=set)

    def candidates(self, families: list) -> list:
        """``families`` without the deep ones -- unless that would leave none, when the
        original list stands rather than block a question outright."""
        kept = [f for f in families if f.code not in self.deep]
        return kept or list(families)


def build(
    rows: Iterable, *, union: bool, chapter_code_of: dict[str, str] | None = None,
) -> FamilySections:
    """``rows`` are ConceptFamilyProposal rows; ``chapter_code_of`` maps a family code to
    its chapter's code (needed only for the cap)."""
    from app.api.books import clean_sections
    from app.curriculum.book_map import chapter_units, family_topic
    from app.curriculum.depth import collapse_section, max_depth_for

    out = FamilySections()
    raw: dict[str, set[str]] = {}
    for row in rows:
        sections = set(clean_sections(row.from_sections))
        if union:
            raw.setdefault(row.code, set()).update(sections)
        else:
            raw[row.code] = sections
    out.exact_of = {code: set(s) for code, s in raw.items()}

    chapter_code_of = chapter_code_of or {}
    codes = set(raw) | set(chapter_code_of)
    for code in codes:
        sections = raw.get(code, set())
        chapter_code = chapter_code_of.get(code)
        depth = max_depth_for(chapter_code) if chapter_code else None
        if depth is None:
            if code in raw:
                out.sections_of[code] = set(sections)
            continue
        cut = {collapse_section(None, s, chapter_code=chapter_code) for s in sections}
        cut.discard(None)
        topic = family_topic(chapter_code, code, depth)
        if chapter_units(chapter_code) is not None and topic is None and (
            any(u.catalog == code for u in chapter_units(chapter_code))
        ):
            # the book map files this family under a unit that is not a major topic
            out.deep.add(code)
        elif topic is None and sections and all(s not in cut for s in sections):
            # not a book-map family: deep when every section it claims had to be cut
            out.deep.add(code)
        if topic is not None:
            cut.add(topic)          # the family claims the topic it is, "0" included
            out.exact_of.setdefault(code, set()).add(topic)
        if cut or code in raw:
            out.sections_of[code] = cut
    return out
