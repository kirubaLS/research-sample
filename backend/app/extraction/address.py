"""Question addresses.

The atomic unit is not the question number. Marks are written per sub-part, so the key is

    SECTION / QUESTION_NO / SUB_PART / CHOICE_ALT        e.g.  'C/27//b',  'A/15/iii/b'

Keying on the bare question number does not survive contact with any of the eight real
CBSE 2026 papers.

Resolution against a *closed vocabulary* is the anti-hallucination control at this layer:
a parsed address is accepted only if it exists in the frozen Q-matrix, so an invented
'16(c)' on a paper that has no 16(c) is rejected rather than created.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# --- numeral normalisation -------------------------------------------------------------
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
TAMIL_DIGITS = str.maketrans("௦௧௨௩௪௫௬௭௮௯", "0123456789")

#: choice alternatives are written differently per script
CHOICE_ALIASES = {
    "a": "a", "b": "b", "c": "c", "d": "d",
    "क": "a", "ख": "b", "ग": "c", "घ": "d",          # Hindi
    "அ": "a", "ஆ": "b", "இ": "c", "ஈ": "d",          # Tamil
}

ROMAN = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6,
    "vii": 7, "viii": 8, "ix": 9, "x": 10,
}

_ADDR = re.compile(
    r"""^\s*
    (?:(?:q|प्र|வினா)\s*\.?\s*)?          # optional 'Q' / 'प्र' / 'வினா'
    (?P<qno>\d{1,3})                      # question number
    \s*[.)\-]?\s*
    (?:\(?\s*(?P<sub>[ivx]{1,5})\s*\)?)?  # optional roman sub-part
    \s*
    (?:\(?\s*(?P<alt>[a-dक-घஅ-ஈ])\s*\)?)? # optional choice alternative
    \s*$""",
    re.VERBOSE | re.IGNORECASE,
)


def normalise_numerals(text: str) -> str:
    return text.translate(DEVANAGARI_DIGITS).translate(TAMIL_DIGITS)


def normalise(text: str) -> str:
    """NFKC fold, map non-Latin numerals, collapse whitespace and stray punctuation."""
    s = unicodedata.normalize("NFKC", text or "")
    s = normalise_numerals(s)
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"[^\w\s().\-/]", " ", s, flags=re.UNICODE)
    return " ".join(s.split())


@dataclass(frozen=True, order=True)
class Address:
    section: str | None
    question_no: str
    sub_part: str | None = None
    choice_alt: str | None = None

    def __str__(self) -> str:
        return f"{self.section or ''}/{self.question_no}/{self.sub_part or ''}/{self.choice_alt or ''}"

    @property
    def key(self) -> str:
        return str(self)

    @property
    def sort_key(self) -> tuple[str, int, int, str]:
        return (
            self.section or "",
            int(self.question_no),
            ROMAN.get((self.sub_part or "").lower(), 0),
            self.choice_alt or "",
        )

    @classmethod
    def parse(cls, text: str, *, section: str | None = None) -> Address | None:
        m = _ADDR.match(normalise(text))
        if not m:
            return None
        sub = m.group("sub")
        alt = m.group("alt")
        # a lone 'i'/'v'/'x' is ambiguous between a roman sub-part and nothing; keep it as a
        # sub-part only when it is a legal roman numeral
        if sub and sub.lower() not in ROMAN:
            return None
        if alt:
            alt = CHOICE_ALIASES.get(alt.lower(), alt.lower())
        return cls(section, m.group("qno"), sub.lower() if sub else None, alt)


class AddressResolver:
    """Closed-vocabulary resolution against the frozen Q-matrix."""

    def __init__(self, known: list[str]):
        self.known: set[str] = set(known)
        self._by_qno: dict[str, list[Address]] = {}
        for k in self.known:
            parts = k.split("/")
            addr = Address(parts[0] or None, parts[1], parts[2] or None, parts[3] or None)
            self._by_qno.setdefault(addr.question_no, []).append(addr)

    def resolve(
        self, text: str, *, section_hint: str | None = None
    ) -> tuple[Address | None, str]:
        """Return (address, reason). ``address`` is None when nothing legal matches."""
        parsed = Address.parse(text)
        if parsed is None:
            return None, "unparseable"

        candidates = self._by_qno.get(parsed.question_no, [])
        if not candidates:
            return None, "no_such_question"  # <- the hallucinated 'Q47' case

        exact = [
            c
            for c in candidates
            if c.sub_part == parsed.sub_part and c.choice_alt == parsed.choice_alt
        ]
        if len(exact) == 1:
            return exact[0], "exact"

        # The student named a sub-part or alternative that this paper does not have —
        # e.g. '16(c)' where only 16(a) and 16(b) exist. Reject, never invent.
        if not exact and (parsed.sub_part or parsed.choice_alt):
            return None, "no_such_address"

        # section prior: a page inside the Geography block resolves '4' to 'B/4'
        if section_hint:
            scoped = [c for c in candidates if c.section == section_hint]
            if len(scoped) == 1:
                return scoped[0], "section_prior"
            if scoped:
                candidates = scoped

        # a bare question number that has exactly one address is unambiguous
        if parsed.sub_part is None and parsed.choice_alt is None and len(candidates) == 1:
            return candidates[0], "unique_by_number"

        return None, "ambiguous"


def check_monotonic(addresses: list[Address]) -> list[int]:
    """Indices where reading order breaks. A break is flagged, never silently reordered —
    it usually means a page is out of sequence."""
    breaks: list[int] = []
    for i in range(1, len(addresses)):
        if addresses[i].sort_key < addresses[i - 1].sort_key:
            breaks.append(i)
    return breaks
