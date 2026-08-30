"""Ask the knowledge base where a real question belongs, and how familiar it is.

This is the check the schema's own closing line demands -- push real questions through
and see what breaks -- run against the knowledge base rather than against a description
of it.

Retrieval is lexical (TF-IDF over the chunk text). That is deliberately the *weakest*
plausible retriever: whatever it gets right is a floor, and where it fails names what an
embedding index would have to earn its place by fixing.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from app.ingest.book import normalise

#: words that carry no subject signal and would otherwise dominate a short exam stem
STOPWORDS = frozenset(
    "the a an of is are was in to and or then which following not if by with for be that "
    "at on value find given show prove it its this these those from as we you".split()
)


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", normalise(text)) if w not in STOPWORDS and len(w) > 2]


@dataclass(frozen=True)
class Candidate:
    chunk_id: str
    reference: str
    node_id: str | None
    bucket: str
    score: float


class LexicalIndex:
    """TF-IDF over chunk text. No model, no network, no tuning knobs."""

    def __init__(self, chunks: list) -> None:
        self.chunks = chunks
        self.tf = [Counter(tokens(c.text)) for c in chunks]
        self.n = max(len(chunks), 1)
        self.df: Counter[str] = Counter()
        for tf in self.tf:
            self.df.update(tf.keys())
        self.norm = [math.sqrt(sum(tf.values())) or 1.0 for tf in self.tf]

    def search(self, question: str, k: int = 3) -> list[Candidate]:
        q = Counter(tokens(question))
        scored: list[Candidate] = []
        for chunk, tf, norm in zip(self.chunks, self.tf, self.norm, strict=True):
            score = sum(
                q[w] * tf[w] * math.log(self.n / (1 + self.df[w])) for w in q if w in tf
            )
            if score > 0:
                scored.append(
                    Candidate(chunk.id, chunk.reference, chunk.node_id, chunk.bucket,
                              score / norm)
                )
        scored.sort(key=lambda c: -c.score)
        return scored[:k]
