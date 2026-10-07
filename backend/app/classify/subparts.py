"""Reading a sub-question together with the question it belongs to.

A paper's sub-questions are often only meaningful with their passage or stem: "Name a suitable
substance used to bring about Step 3 and write the balanced chemical equation" is about metal
extraction only because of the passage above it, and on its own words it reads as Chemical
Reactions. Two general rules, both default OFF and both subject-gated through
``app.mapping.subject_scope`` (the subjects whose mapping is being reworked):

* ``subpart_retrieval_with_passage`` -- the chapter search for a sub-part reads the shared stem
  in front of it, as the place step's judge already does.
* ``subpart_chapter_agreement`` -- a sub-part whose own first guess is weak, while the other
  sub-parts of its question clearly agree on another chapter that is also among its own top
  candidates, goes to that chapter. A weak guess is outvoted by its siblings; a confident one
  is never moved, and a chapter nothing in the sub-part's own retrieval supports is never
  imposed.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

#: the share of a question's sub-parts that must agree for the others to be held to it
MIN_AGREEMENT = 0.60
#: fewer sub-parts than this cannot outvote anything
MIN_SUBPARTS = 3
#: a first guess is weak when the gap to its runner-up is under this share of its own score
WEAK_MARGIN = 0.15
#: the agreed chapter must be among the sub-part's own best this-many candidates
OWN_CANDIDATES = 3


def with_passage(stem: str | None, passage: str | None, sub_part: str | None) -> str:
    """``stem`` as the search should read it: a sub-part reads its passage first, once."""
    stem = stem or ""
    passage = (passage or "").strip()
    if not sub_part or not passage or passage in stem:
        return stem
    return f"{passage}\n\n{stem}"


@dataclass(frozen=True)
class FirstLook:
    """One row's first chapter guess: the question it belongs to (None when it is not a
    sub-part), its candidate chapters best first, how weak the lead is and whether the
    independent retrievers agreed."""

    address: str
    group: tuple | None
    ranked: list[str]
    relative_margin: float
    agreed: bool = False


def sibling_overrides(looks: list[FirstLook]) -> dict[str, str]:
    """address -> the chapter a weakly-placed sub-part should be held to."""
    groups: dict[tuple, list[FirstLook]] = {}
    for look in looks:
        if look.group is not None and look.ranked:
            groups.setdefault(look.group, []).append(look)
    out: dict[str, str] = {}
    for members in groups.values():
        if len(members) < MIN_SUBPARTS:
            continue
        tally = Counter(m.ranked[0] for m in members)
        chapter, count = tally.most_common(1)[0]
        if count / len(members) < MIN_AGREEMENT:
            continue
        for m in members:
            if m.ranked[0] == chapter:
                continue
            weak = m.relative_margin < WEAK_MARGIN or not m.agreed
            if weak and chapter in m.ranked[:OWN_CANDIDATES]:
                out[m.address] = chapter
    return out
