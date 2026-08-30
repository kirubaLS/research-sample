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


class SemanticIndex:
    """Nearest chunk by cosine similarity over stored embeddings.

    Falls back to nothing: a chunk without a vector is simply not searchable here, and the
    caller is told how many were skipped rather than getting a quietly partial index.
    """

    def __init__(self, chunks: list, embedder) -> None:
        self.embedder = embedder
        self.chunks = [c for c in chunks if getattr(c, "embedding", None)]
        self.skipped = len(chunks) - len(self.chunks)

    def search(self, question: str, k: int = 3) -> list[Candidate]:
        from app.ingest.embed import cosine

        if not self.chunks:
            return []
        [vector] = self.embedder.embed_texts([question], is_query=True)
        scored = [
            Candidate(c.id, c.reference, c.node_id, c.bucket, cosine(vector, c.embedding))
            for c in self.chunks
        ]
        scored.sort(key=lambda c: -c.score)
        return scored[:k]


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


# --- combining the two, and deciding at the level of a chapter -------------------------


@dataclass(frozen=True)
class ChapterVerdict:
    """Where a question belongs, and how sure the system is that it belongs there."""

    node_id: str | None
    score: float
    margin: float                 # gap to the runner-up: the real confidence signal
    agreed: bool                  # did both retrievers independently pick this chapter
    evidence: list[Candidate]     # the chunks that put it there
    runners_up: list[tuple[str | None, float]]


#: reciprocal-rank fusion constant. 60 is the value the method was published with and
#: needs no calibration -- which is the point: the two scores are not on one scale, and
#: any weighting between them would be a number invented rather than measured.
RRF_K = 60

#: how many chunks may vouch for a chapter
CORROBORATION_DEPTH = 2


def _rrf(ranked: list[list[Candidate]]) -> dict[str, float]:
    """Fuse ranked lists by rank, not by score.

    A cosine similarity and a TF-IDF score cannot be added: they have different ranges and
    different distributions. Rank is the one thing they share.
    """
    fused: dict[str, float] = {}
    for lst in ranked:
        for rank, candidate in enumerate(lst):
            fused[candidate.chunk_id] = fused.get(candidate.chunk_id, 0.0) + 1.0 / (
                RRF_K + rank + 1
            )
    return fused


def locate(
    question: str,
    indexes: list,
    *,
    depth: int = 12,
) -> ChapterVerdict:
    """Which chapter, from every retriever available, aggregated per chapter.

    Two changes from taking the best chunk:

    * **Fusion.** Lexical and semantic retrieval fail on different questions -- "cone,
      slant height" is a literal-word match, "bells ringing at 48, 72 and 108 seconds" is a
      meaning match, and neither method gets both. Fusing their rankings gets the union of
      what they each know.
    * **Chapter voting.** One chunk deciding a chapter makes the answer hostage to a single
      passage that happens to share phrasing. Summing the evidence over the top chunks lets
      a chapter that is repeatedly close beat one that is once very close.

    The margin to the runner-up is what a caller should act on: a chapter that wins by a
    hair is a chapter to ask a human about, not one to report.
    """
    ranked = [index.search(question, k=depth) for index in indexes]
    ranked = [r for r in ranked if r]
    if not ranked:
        return ChapterVerdict(None, 0.0, 0.0, False, [], [])

    fused = _rrf(ranked)
    by_chunk = {c.chunk_id: c for lst in ranked for c in lst}

    scores: dict[str | None, list[float]] = {}
    evidence: dict[str | None, list[Candidate]] = {}
    for chunk_id, score in fused.items():
        candidate = by_chunk[chunk_id]
        scores.setdefault(candidate.node_id, []).append(score)
        evidence.setdefault(candidate.node_id, []).append(candidate)

    # A chapter scores on its best CORROBORATION_DEPTH chunks, not on all of them.
    # Measured on the 30(B) set with lexical retrieval: summing everything scores 6/10
    # because a long chapter accumulates weak matches and beats a short precise one
    # (Circles beat Areas Related to Circles twice that way); taking only the best chunk
    # scores 8/10 and is hostage to one passage that happens to share phrasing. Two is
    # 9/10 -- though on ten questions that is one item's difference, so it is a reasoned
    # default rather than a measured optimum.
    per_chapter = {
        node: sum(sorted(vals, reverse=True)[:CORROBORATION_DEPTH])
        for node, vals in scores.items()
    }
    ordered = sorted(per_chapter.items(), key=lambda kv: -kv[1])
    top_node, top_score = ordered[0]
    runner_up = ordered[1][1] if len(ordered) > 1 else 0.0

    # agreement between independent retrievers is a cheap, honest confidence signal
    agreed = len(ranked) > 1 and len({lst[0].node_id for lst in ranked}) == 1

    return ChapterVerdict(
        node_id=top_node,
        score=top_score,
        margin=top_score - runner_up,
        agreed=agreed,
        evidence=sorted(evidence[top_node], key=lambda c: -c.score)[:3],
        runners_up=[(n, round(s, 4)) for n, s in ordered[1:4]],
    )
