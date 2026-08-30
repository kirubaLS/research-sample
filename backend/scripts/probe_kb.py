"""Push real questions through the knowledge base and report what resolves.

    python -m scripts.probe_kb ../ncert/X/maths/probe-30B.json

The file is a JSON list of {"q": "...", "stem": "...", "chapter": "..."} where `chapter`
is the answer you expect. Chapter is checked; familiarity is reported, not graded, since
only the exact level can be decided without an embedding index.

Run this after loading a subject. A knowledge base that loads cleanly and then cannot
place a real question is the failure that matters, and it is invisible from the ingest
summary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.ingest.book import stem_hash
from app.ingest.embed import classify_familiarity
from app.ingest.jina import JinaEmbedder
from app.ingest.probe import LexicalIndex, SemanticIndex
from app.models import BookChunk, CanonicalProcedure, TaxonomyNode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", type=Path)
    parser.add_argument("--top", type=int, default=1, help="candidates to consider a hit")
    parser.add_argument("--lexical", action="store_true",
                        help="force word-overlap retrieval even when vectors exist")
    args = parser.parse_args()

    probes = json.loads(args.questions.read_text())
    db = SessionLocal()
    try:
        chunks = db.scalars(select(BookChunk)).all()
        if not chunks:
            raise SystemExit("knowledge base is empty -- run scripts.ingest_book first")
        labels = {n.id: n.label for n in db.scalars(select(TaxonomyNode)).all()}

        settings = get_settings()
        embedded = [c for c in chunks if c.embedding]
        if embedded and settings.jina_api_key and not args.lexical:
            index = SemanticIndex(
                chunks,
                JinaEmbedder(
                    settings.jina_api_key, model=settings.embedding_model,
                    dimensions=settings.embedding_dimensions,
                ),
            )
            mode = f"semantic ({len(embedded)}/{len(chunks)} chunks embedded)"
        else:
            index = LexicalIndex(chunks)
            mode = "lexical -- only T_VERBATIM is decidable"
            if not embedded:
                mode += "; run scripts.embed_kb"
        print(f"retrieval: {mode}\n")

        print(f"{'Q':>4}  {'expected':30} {'retrieved':30} {'ok':3}  familiarity")
        hits = 0
        for probe in probes:
            found = index.search(probe["stem"], k=args.top)
            got = [labels.get(c.node_id, "?") for c in found]
            ok = probe["chapter"].lower() in [g.lower() for g in got]
            hits += ok

            verbatim = db.scalar(
                select(CanonicalProcedure).where(
                    CanonicalProcedure.stem_hash == stem_hash(probe["stem"])
                )
            )
            if verbatim:
                familiarity = "T_VERBATIM (exact)"
            elif isinstance(index, SemanticIndex) and found:
                call = classify_familiarity(
                    found[0].score, found[0].reference, found[0].bucket
                )
                familiarity = f"{call.level or 'abstained'} ({call.similarity:.2f})"
            else:
                familiarity = "undecidable (no embedding index)"
            print(
                f"{probe['q']:>4}  {probe['chapter'][:30]:30} {got[0][:30]:30} "
                f"{'yes' if ok else 'NO ':3}  {familiarity}"
            )

        print()
        print(f"chapter resolved: {hits}/{len(probes)}")
        if not isinstance(index, SemanticIndex):
            print(
                "familiarity: only T_VERBATIM is decidable without vectors. PRACTISED, "
                "ADAPTED and NOVEL need similarity, so Competency Tier cannot be derived "
                "from the book -- it comes from the paper's blueprint, which 2A makes the "
                "authority anyway."
            )
        else:
            print(
                "familiarity thresholds are provisional until measured on real papers; "
                "a call near a boundary abstains rather than guessing."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
