"""Section cards and chunk-level BM25: a cheap first look at a chapter.

A card is a few lines about one major topic -- its heading, its opening, and the names,
glossary terms and rare words that tell it apart from its neighbours. A chapter's cards
cost about a seventh of its full text, so a judge can see every topic of the chapter for a
fraction of the price and read in full only the two sections BM25 ranks first.

Everything here is deterministic and offline: no model call, no network. The cards are
built once from the book map (``scripts/build_section_cards.py``) and committed as
``reference/book_map/section_cards.json``; BM25 runs over the chapter's own chunks at
placement time.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

CARDS_FILE = Path(__file__).resolve().parent.parent.parent / "reference/book_map/section_cards.json"

_WORD = re.compile(r"[a-z][a-z'’-]{2,}|\d{4}")
_STOP = set("the and for are was were that this with from which their they have has had not but "
            "its into than then also such these those been being can may will would about "
            "when where who what why how all any each other more most one two".split())
_NAMES = re.compile(r"(?<![\w'])(?:[A-Z][\w'’-]+)(?:\s+(?:(?:of|the|and|for|in|on|to)\s+)?[A-Z][\w'’-]+)+")
_MID = re.compile(r"(?<=[)\-–—,;] )([A-Z][a-z][\w'’-]{3,})")
_YEAR = re.compile(r"\b(1[4-9]\d\d|20\d\d)\b")
TERMS_PER_CARD = 18
FIRST_CHARS = 200
#: BM25's usual constants, and the weight of a section's 2nd and 3rd best chunks
K1, B, EXTRA_CHUNKS = 1.4, 0.75, 0.3


def tokens(text: str) -> int:
    """Rough token count (four characters to a token)."""
    return math.ceil(len(text) / 4)


def words(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


def _candidates(text: str) -> Counter:
    """Everything on a section that could decide a question: names, years, mid-sentence
    capitalised words and rare lowercase content words."""
    counts = Counter(_NAMES.findall(text) + _YEAR.findall(text))
    counts.update(_MID.findall(text))
    counts.update(w for w in words(text) if len(w) >= 5)
    return counts


def build_cards(
    sections: dict[str, dict], extras: dict[str, list[str]] | None = None,
    n_terms: int = TERMS_PER_CARD,
) -> dict[str, str]:
    """One card per major topic. ``sections`` maps a topic to {"heading", "chunks"};
    ``extras`` are the book's own vocabulary for it (glossary terms, box titles), always
    listed first. The rest of the terms are the section's rarest: used in at most two
    sections of the chapter, commonest first."""
    extras = extras or {}
    cand = {k: _candidates(" ".join(v["chunks"])) for k, v in sections.items()}
    df: Counter = Counter()
    for c in cand.values():
        df.update(c.keys())
    cards = {}
    for key, counts in cand.items():
        picked = list(dict.fromkeys(extras.get(key, [])))[:6]
        seen = {p.lower() for p in picked}
        for t in sorted(counts, key=lambda t: (df[t], -counts[t], t)):
            if len(picked) >= n_terms:
                break
            if df[t] <= 2 and t.lower() not in seen:
                picked.append(t)
                seen.add(t.lower())
        first = (sections[key]["chunks"] or [""])[0][:FIRST_CHARS].rsplit(" ", 1)[0]
        cards[key] = f"{sections[key]['heading']}. {first}. Key: {'; '.join(picked)}"
    return cards


def rank_sections(query: str, chunks: list[tuple[str, str]]) -> list[str]:
    """Stage 1: BM25 over every chunk of a chapter -- (section, text) pairs -- then each
    section scores its best chunk plus ``EXTRA_CHUNKS`` x its next two. Measured on the
    gold paper this put the right section first for 43 of 54 questions and in the top
    three for 51; ranking whole sections by TF-IDF, or fusing with the cards, was worse."""
    docs = [(k, Counter(words(t))) for k, t in chunks]
    docs = [(k, c) for k, c in docs if c]
    if not docs:
        return []
    n = len(docs)
    avg = sum(sum(c.values()) for _, c in docs) / n
    df = Counter(t for _, c in docs for t in c)
    q = set(words(query))
    per: dict[str, list[float]] = defaultdict(list)
    for k, c in docs:
        length = sum(c.values())
        per[k].append(sum(
            math.log(1 + (n - df[t] + .5) / (df[t] + .5)) * c[t] * (K1 + 1)
            / (c[t] + K1 * (1 - B + B * length / avg))
            for t in q if t in c))
    score = {k: (v := sorted(vs, reverse=True))[0] + EXTRA_CHUNKS * sum(v[1:3])
             for k, vs in per.items()}
    return sorted(score, key=lambda k: (-score[k], k))


@lru_cache(maxsize=1)
def _all_cards() -> dict[str, dict]:
    try:
        return json.loads(CARDS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def load_cards(chapter_code: str) -> dict[str, str] | None:
    """The committed cards of a chapter, topic -> card text; None for a chapter without
    (the caller then reads the whole chapter as it always did)."""
    entry = _all_cards().get(chapter_code)
    return dict(entry["cards"]) if entry and entry.get("cards") else None


def cards_block(cards: dict[str, str], headings: dict[str, str]) -> str:
    """The chapter's cards as one cacheable block, in the order of ``headings`` (book
    order); a listed topic with no card shows its heading alone."""
    return "\n".join(f"[{n}] {cards.get(n) or headings.get(n) or n}" for n in headings)
