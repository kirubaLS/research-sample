"""How far a question sits from what the book taught.

Two buckets, and the split is the point:

  T  taught as content  — theorems, worked and solved examples in the chapter body.
                          A match here means the student has seen the answer written out.
  E  exercise practice  — end-of-chapter exercises and the school's past papers.

For the taught-verbatim set we do not do fuzzy retrieval at all. NCERT labels its theorems
and examples, so ``canonical_procedure`` is an exact lookup: deterministic and free.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

NUM = re.compile(r"\d+(?:\.\d+)?")
WS = re.compile(r"\s+")


def normalise_stem(text: str) -> str:
    """Canonical form for hashing and similarity: numbers and names folded out."""
    s = unicodedata.normalize("NFKC", text or "").lower()
    s = NUM.sub("<num>", s)
    s = re.sub(r"[^\w\s<>]", " ", s, flags=re.UNICODE)
    return WS.sub(" ", s).strip()


def stem_hash(text: str) -> str:
    return hashlib.sha256(normalise_stem(text).encode("utf-8")).hexdigest()


def _tokens(text: str) -> set[str]:
    return {t for t in normalise_stem(text).split() if len(t) > 2}


def jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def cosine_tf(a: str, b: str) -> float:
    """Cheap lexical cosine. In production this is a dense embedding over pgvector;
    the interface is identical so the backend swaps without touching callers."""
    from collections import Counter
    ca, cb = Counter(normalise_stem(a).split()), Counter(normalise_stem(b).split())
    if not ca or not cb:
        return 0.0
    common = set(ca) & set(cb)
    num = sum(ca[t] * cb[t] for t in common)
    den = (sum(v * v for v in ca.values()) ** 0.5) * (sum(v * v for v in cb.values()) ** 0.5)
    return num / den if den else 0.0


@dataclass(frozen=True)
class CorpusEntry:
    ref: str
    text: str
    bucket: str            # 'T' | 'E'
    node_code: str | None = None
    canonical: bool = False


@dataclass(frozen=True)
class FamiliarityResult:
    score: float
    bucket: str | None     # 'T' | 'E' | None
    match_ref: str | None
    node_code: str | None
    exact: bool = False

    @property
    def band(self) -> str:
        """The row selector for the action x familiarity table."""
        if self.score >= 0.85:
            return "verbatim"
        if self.score >= 0.55:
            return "adapted"
        return "novel"


class FamiliarityIndex:
    """Book-derived index. Exact-hash channel first, then similarity, always tree-scoped."""

    def __init__(self, entries: list[CorpusEntry]):
        self.entries = entries
        self._by_hash: dict[str, CorpusEntry] = {}
        for e in entries:
            self._by_hash.setdefault(stem_hash(e.text), e)

    def score(self, stem: str, *, node_scope: str | None = None) -> FamiliarityResult:
        exact = self._by_hash.get(stem_hash(stem))
        if exact is not None:
            return FamiliarityResult(1.0, exact.bucket, exact.ref, exact.node_code, exact=True)

        pool = self.entries
        if node_scope:
            scoped = [e for e in pool if e.node_code and e.node_code.startswith(node_scope)]
            pool = scoped or pool

        best: tuple[float, CorpusEntry] | None = None
        for e in pool:
            s = max(cosine_tf(stem, e.text), jaccard(stem, e.text))
            # a canonical (named theorem / worked example) match is stronger evidence of
            # reproduction than an exercise match at the same similarity
            if e.canonical:
                s = min(1.0, s * 1.10)
            if best is None or s > best[0]:
                best = (s, e)

        if best is None or best[0] <= 0.0:
            return FamiliarityResult(0.0, None, None, None)
        return FamiliarityResult(best[0], best[1].bucket, best[1].ref, best[1].node_code)
