"""Find the book sections whose own text best matches a question.

The prompt mapper shows a model titles and a few key terms and asks it to choose. That works
until two neighbouring sections look alike, and then the model decides on a title. This reads
the books themselves: every section's printed text is indexed (BM25, in memory, no database, no
network) and a question is matched against it, so the model can be handed the few sections
whose text actually talks about what was asked, with the matching sentences.

Dependency-free and read-only. It reads the same audited book-map files the taxonomy is built
from, and it works for any paper, because the thing it matches against is the book, not an
answer key.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from app.curriculum.book_map import REFERENCE, UNIT_FILES
from app.mapping import prompt_taxonomy as pt

K1, B = 1.4, 0.75

_WORD = re.compile(r"[a-z0-9]+")
#: words that carry no topic: grammar, and the vocabulary of exam instructions
_STOP = set("""a an and are as at be been being but by can could did do does done for from had has have
how if in into is it its may might no not of on or our out over shall should so some such than that the
their them then there these they this those through to under up was we were what when where which while who
whom whose why will with would you your also any each both more most other only own same very
explain analyse analyze examine justify describe discuss state mention name suggest choose select identify
write give list define compare evaluate following given correct incorrect option options statement statements
assertion reason read carefully answer questions question source passage match column matched pair pairs
one two three four five marks mark suitable suitably examples example arguments argument following true false
below above here""".split())


def _stem(w: str) -> str:
    for suffix in ("ations", "ation", "ings", "ing", "edly", "ies", "es", "ed", "ly", "s"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return w


def tokens(text: str) -> list[str]:
    out = []
    for w in _WORD.findall((text or "").lower().replace("’", "'")):
        if w in _STOP or (len(w) < 3 and not w.isdigit()):
            continue
        out.append(_stem(w))
    return out


@dataclass(frozen=True)
class Hit:
    topic_id: str
    score: float
    snippet: str


class SectionIndex:
    """BM25 over ``docs``: topic id -> (subject, the section's own text)."""

    def __init__(self, docs: dict[str, tuple[str, str]]) -> None:
        self.text: dict[str, str] = {}
        self.subject: dict[str, str] = {}
        self._tf: dict[str, Counter] = {}
        self._len: dict[str, int] = {}
        self._df: Counter = Counter()
        for tid, (subject, text) in docs.items():
            self.text[tid] = text
            self.subject[tid] = subject
            toks = tokens(text)
            tf = Counter(toks)
            # adjacent word pairs: "print censorship", "hot springs" say more than either word
            tf.update(f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False))
            self._tf[tid] = tf
            self._len[tid] = sum(tf.values())
        for tf in self._tf.values():
            self._df.update(tf.keys())
        self._n = max(1, len(self._tf))
        self._avg = sum(self._len.values()) / self._n

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log(1 + (self._n - df + 0.5) / (df + 0.5))

    def search(self, query: str, subject: str | None = None, k: int = 8) -> list[Hit]:
        toks = tokens(query)
        q = Counter(toks)
        q.update(f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False))
        scored = []
        for tid, tf in self._tf.items():
            if subject and self.subject[tid] != subject:
                continue
            norm = K1 * (1 - B + B * self._len[tid] / self._avg)
            score = 0.0
            for term, qn in q.items():
                f = tf.get(term, 0)
                if f:
                    score += self._idf(term) * (f * (K1 + 1)) / (f + norm) * (1 + 0.3 * math.log(qn))
            if score > 0:
                scored.append((score, tid))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [Hit(tid, round(s, 2), self.snippet(tid, set(toks))) for s, tid in scored[:k]]

    def snippet(self, tid: str, qterms: set[str], limit: int = 330) -> str:
        sentences = re.split(r"(?<=[.?!])\s+", self.text.get(tid, ""))
        ranked = sorted(
            ((sum(self._idf(t) for t in set(tokens(s)) & qterms), i, s) for i, s in enumerate(sentences)),
            key=lambda x: (-x[0], x[1]))
        best = [s for score, _, s in ranked[:2] if score > 0]
        return " … ".join(best)[:limit]


def social_docs() -> dict[str, tuple[str, str]]:
    """Social Science: every section of the four books, by the taxonomy's own IDs."""
    import json

    taxonomy = pt.build()
    docs: dict[str, tuple[str, str]] = {}
    for subject, prefix in pt.SUBJECTS:
        data = json.loads((REFERENCE / UNIT_FILES[subject]).read_text(encoding="utf-8"))
        for index, ch in enumerate(data, start=1):
            chapter_id = f"{prefix}{index}"
            units = ch.get("units", [])
            extra: dict[str, list[str]] = {}
            for u in units:
                number = str(u.get("number") or "")
                if u.get("kind") == "box" and "." in number:
                    owner = extra.setdefault(number.rsplit(".", 1)[0], [])
                    owner.extend(pt._strings(u.get("body") or []))
                    owner.append(u.get("title") or "")
            for u in units:
                number = u.get("number")
                if not number or u.get("kind") in pt._NOT_TOPICS:
                    continue
                tid = f"{chapter_id}.{number}"
                if taxonomy.topic(tid) is None:
                    continue
                title = pt._title(u.get("title") or "")
                parts = [title] * 3 + pt._strings(u.get("body") or []) + extra.get(str(number), [])
                parts += pt._strings(u.get("activities") or [])
                docs[tid] = (subject, " ".join(pt._clean(p) for p in parts if p))
    return docs


@lru_cache(maxsize=1)
def index() -> SectionIndex:
    """The Social Science books."""
    return SectionIndex(social_docs())


@lru_cache(maxsize=1)
def science_index() -> SectionIndex:
    """The Science book, by the Science topic list's IDs."""
    from app.mapping import science_taxonomy

    return SectionIndex(science_taxonomy.docs())


@lru_cache(maxsize=1)
def math_index() -> SectionIndex:
    """Mathematics, by the Mathematics topic list's IDs (searched on its key terms and wording)."""
    from app.mapping import math_taxonomy

    return SectionIndex(math_taxonomy.docs())
