"""Does dense retrieval help the section shortlist? READ-ONLY, one cheap Jina call per question.

For each question of the gold paper this ranks the chapter's major topics three ways -- BM25
over the chunks (``section_cards.score_sections``), dense (cosine of the question's Jina
embedding against the chunks' stored embeddings, scored the same way: a section's best
chunk plus 0.3 x its next two) and a fusion of the two -- and prints where the gold section
lands: top-1 and top-3 for each, and the fusion at several weights.

Reads the paper's stored questions and the book's stored chunks from the database (Postgres
session opened READ ONLY; nothing is written). Calls Jina only to embed each question once
(about 55 short queries). No model call, no other network.

    docker compose exec -T backend python -m scripts.eval_dense_retrieval \\
        --assessment <id> --gold /tmp/gold.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from app.classify.section_cards import EXTRA_CHUNKS, margin, score_sections

WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)          # share of the fused score that is dense


def dense_scores(vector, chunks: list[tuple[str, list[float]]]) -> dict[str, float]:
    """(section, embedding) pairs -> section score: best chunk + EXTRA_CHUNKS x next two."""
    from app.ingest.embed import cosine

    per: dict[str, list[float]] = defaultdict(list)
    for section, emb in chunks:
        per[section].append(cosine(vector, emb))
    return {k: (v := sorted(vs, reverse=True))[0] + EXTRA_CHUNKS * sum(v[1:3])
            for k, vs in per.items()}


def normalise(score: dict[str, float]) -> dict[str, float]:
    """Min-max to 0..1 so BM25 and cosine scores can be blended."""
    if not score:
        return {}
    lo, hi = min(score.values()), max(score.values())
    return {k: (v - lo) / (hi - lo) if hi > lo else 0.0 for k, v in score.items()}


def fuse(bm25: dict[str, float], dense: dict[str, float], weight: float) -> list[str]:
    """Sections best first by (1 - weight) x BM25 + weight x dense, each normalised."""
    a, b = normalise(bm25), normalise(dense)
    keys = set(a) | set(b)
    mix = {k: (1 - weight) * a.get(k, 0.0) + weight * b.get(k, 0.0) for k in keys}
    return sorted(mix, key=lambda k: (-mix[k], k))


def position(order: list[str], gold: set[str]) -> int:
    return min((order.index(g) for g in gold if g in order), default=len(order))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--assessment", required=True)
    ap.add_argument("--gold", required=True)
    args = ap.parse_args(argv)

    from sqlalchemy import select, text

    from app.config import get_settings
    from app.curriculum.book_map import major_of
    from app.db import SessionLocal
    from app.ingest.jina import JinaEmbedder
    from app.models import BookChunk, Question, TaxonomyNode

    settings = get_settings()
    if not settings.jina_api_key:
        raise SystemExit("no Jina key in this environment")
    embedder = JinaEmbedder(
        settings.jina_api_key, model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    gold = json.loads(Path(args.gold).read_text())
    db = SessionLocal()
    try:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(text("SET TRANSACTION READ ONLY"))
        stems = {q.address: q.stem_text for q in db.scalars(
            select(Question).where(Question.assessment_id == args.assessment)) if q.stem_text}
        by_chapter: dict[str, tuple[list, list]] = {}
        for info in gold["section_chapters"].values():
            code = info["chapter"]
            node = db.scalars(select(TaxonomyNode).where(TaxonomyNode.code == code)).first()
            if node is None:
                continue
            bm, dn = [], []
            for c in db.scalars(select(BookChunk).where(
                BookChunk.node_id == node.id, BookChunk.bucket == "T")):
                top = major_of(code, c.section_number, 2) if c.section_number else major_of(code, None, 2)
                if top is None:
                    continue
                bm.append((top, c.text or ""))
                if c.embedding:
                    dn.append((top, c.embedding))
            by_chapter[code] = (bm, dn)
    finally:
        db.rollback()
        db.close()

    rows = []
    for address, key in gold["questions"].items():
        stem = stems.get(address)
        code = gold["section_chapters"][address.split("/", 1)[0]]["chapter"]
        if not stem or key.get("chapter") or code not in by_chapter:
            continue
        bm, dn = by_chapter[code]
        if not dn:
            continue
        gold_sections = {major_of(code, s, 2) for s in key["exact"]} - {None}
        [vector] = embedder.embed_texts([stem], is_query=True)
        rows.append((score_sections(stem, bm), dense_scores(vector, dn), gold_sections))
    n = len(rows)
    print(f"questions scored {n} (those with stored text and embeddings)")
    for w in WEIGHTS:
        pos = [position(fuse(b, d, w), g) for b, d, g in rows]
        label = "BM25 only" if w == 0 else "dense only" if w == 1 else f"dense weight {w}"
        print(f"{label:<18} top-1 {sum(p == 0 for p in pos):>2}/{n}   top-3 {sum(p < 3 for p in pos):>2}/{n}")
    print("\nmargin of the BM25 ranking vs whether dense AGREES with its first section:")
    for lo, hi in ((0, .25), (.25, .5), (.5, 9)):
        sel = [(b, d, g) for b, d, g in rows if lo <= margin(b) < hi]
        agree = [(b, d, g) for b, d, g in sel
                 if fuse(b, d, 0)[0] == fuse(b, d, 1)[0]]
        right = sum(position(fuse(b, d, 0), g) == 0 for b, d, g in agree)
        print(f"margin {lo}-{hi}: {len(sel)} q; dense agrees on {len(agree)}, BM25 first right on {right}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
