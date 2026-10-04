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


def score_sections(query: str, chunks: list[tuple[str, str]]) -> dict[str, float]:
    """Stage 1: BM25 over every chunk of a chapter -- (section, text) pairs -- then each
    section scores its best chunk plus ``EXTRA_CHUNKS`` x its next two. Measured on the
    gold paper this put the right section first for 43 of 54 questions and in the top
    three for 50-51; ranking whole sections by TF-IDF, or fusing with the cards or an
    exact-term signal, was worse or no better."""
    docs = [(k, Counter(words(t))) for k, t in chunks]
    docs = [(k, c) for k, c in docs if c]
    if not docs:
        return {}
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
    return {k: (v := sorted(vs, reverse=True))[0] + EXTRA_CHUNKS * sum(v[1:3])
            for k, vs in per.items()}


def rank_sections(query: str, chunks: list[tuple[str, str]]) -> list[str]:
    """The chapter's sections, best first."""
    score = score_sections(query, chunks)
    return sorted(score, key=lambda k: (-score[k], k))


#: how many sections' full text a card read is given, by how clearly BM25 separates the
#: first from the second: ``margin`` = (top1 - top2) / top1. On the gold paper the first
#: section was right for 22 of 22 questions at a margin of 0.5 or more, 12 of 17 between
#: 0.25 and 0.5, and 9 of 15 below 0.25 (11 of 15 within the top two).
MARGIN_CLEAR, MARGIN_LIKELY = 0.5, 0.25


def margin(score: dict[str, float]) -> float:
    top = sorted(score.values(), reverse=True)
    return (top[0] - top[1]) / top[0] if len(top) > 1 and top[0] else 1.0


def sections_to_show(m: float) -> int:
    """One section when retrieval is clear, two when likely, three when ambiguous."""
    return 1 if m >= MARGIN_CLEAR else 2 if m >= MARGIN_LIKELY else 3


#: a quote that is not a verbatim copy still counts when this share of its words sit,
#: in order of appearance, in one stretch of a shown section's text
FUZZY_MIN = 0.85
FUZZY_MIN_WORDS = 6


def quote_overlap(quote: str, text: str) -> float:
    """1.0 when ``quote`` (already normalised) is a verbatim part of ``text``; otherwise
    the best share of the quote's words found in any window of the text about as long as
    the quote -- a paraphrased or lightly reworded copy of a real sentence scores high, a
    sentence that is nowhere in the text scores low. Never authorises an answer alone:
    the caller still requires the section the stretch sits in to be the one named."""
    if quote in text:
        return 1.0
    q = quote.split()
    if len(q) < FUZZY_MIN_WORDS:
        return 0.0
    want = Counter(q)
    t = text.split()
    size = len(q) + 3
    if len(t) < size:
        size = len(t)
    window: Counter = Counter()
    hit = best = 0
    for i, w in enumerate(t):
        window[w] += 1
        hit += window[w] <= want.get(w, 0)
        if i >= size:
            old = t[i - size]
            hit -= window[old] <= want.get(old, 0)
            window[old] -= 1
        best = max(best, hit)
    return best / len(q)


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
