"""Suggesting who an unrecognised roll might be, from the name written next to it.

The roll number is the join key for a mark sheet and the name is only a check on it. That
is the right way round: a handwritten name on an Indian mark sheet is the least reliable
thing on the page -- Karthik, Kartik and Karthick are one student; R. Priya and Priya R
are one student; and the reader misreads letters on top of that. Used as a key, a name
would confidently attach marks to the wrong child.

So when a roll is NOT on the roster, the name is used for the one thing it is good for:
a suggestion. The row still waits for a person; the person now sees "this looks like
Abinaya Murugan, roll 2" instead of a blank, and accepts it with one click or creates the
new student the row describes. A name that fits several students is offered as the list,
never as a pick.

Nothing here writes anything. It returns a candidate and a reason a reviewer can read.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Protocol


class Named(Protocol):
    id: str
    name: str
    roll_no: str


#: below this the best candidate is not offered at all
MIN_SCORE = 0.72
#: and it must beat the runner-up by this much, or both are shown and neither is picked
MIN_MARGIN = 0.12


def normalise(name: str) -> list[str]:
    """Words of a name, lowercased, accents and punctuation folded, initials kept.

    'R. Priya' -> ['r', 'priya']; 'Karthick S/O Murugan' -> ['karthick', 's', 'o', 'murugan'].
    """
    folded = unicodedata.normalize("NFKD", name or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch)).lower()
    return [w for w in re.split(r"[^a-z0-9]+", folded) if w]


def _word_score(a: str, b: str) -> float:
    """How alike two words are, with an initial matching the word it abbreviates."""
    if a == b:
        return 1.0
    if len(a) == 1 or len(b) == 1:
        return 0.9 if a[0] == b[0] else 0.0
    return SequenceMatcher(None, a, b).ratio()


def similarity(written: str, roster: str) -> float:
    """0..1. Order-free: every written word finds its best roster word, and the score is
    the average over the longer name so a missing surname costs something but a swapped
    order costs nothing."""
    ws, rs = normalise(written), normalise(roster)
    if not ws or not rs:
        return 0.0
    longer, shorter = (ws, rs) if len(ws) >= len(rs) else (rs, ws)
    total = 0.0
    for w in longer:
        total += max((_word_score(w, r) for r in shorter), default=0.0)
    return total / len(longer)


@dataclass
class Suggestion:
    """What the name says about who this row is, for a reviewer to accept or ignore."""

    student: Named | None
    score: float
    reason: str
    #: when the name fits several students about equally, all of them, best first
    candidates: list[tuple[Named, float]] = field(default_factory=list)


def suggest(written: str, roster: list[Named]) -> Suggestion:
    if not normalise(written):
        return Suggestion(None, 0.0, "no name was read next to this roll")
    scored = sorted(
        ((s, similarity(written, s.name)) for s in roster),
        key=lambda pair: pair[1], reverse=True,
    )
    if not scored or scored[0][1] < MIN_SCORE:
        return Suggestion(None, scored[0][1] if scored else 0.0,
                          "no student on the roster has a name like this")
    best, best_score = scored[0]
    close = [(s, sc) for s, sc in scored if sc >= MIN_SCORE and best_score - sc < MIN_MARGIN]
    if len(close) > 1:
        names = ", ".join(f"{s.name} (roll {s.roll_no})" for s, _ in close[:4])
        return Suggestion(None, best_score,
                          f"the name fits more than one student: {names}", candidates=close[:4])
    return Suggestion(
        best, best_score,
        f"the name matches {best.name}, roll {best.roll_no}; the sheet's roll may be misread",
        candidates=[(best, best_score)],
    )
