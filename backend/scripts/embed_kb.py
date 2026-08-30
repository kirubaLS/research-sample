"""Embed the loaded knowledge base so familiarity becomes decidable.

    python -m scripts.embed_kb --subject X.MATH --dry-run
    python -m scripts.embed_kb --subject X.MATH

Without embeddings only T_VERBATIM can be decided -- an exact hash against a theorem or
worked example. PRACTISED, ADAPTED and NOVEL all need distance, so three of the four
familiarity levels collapse and Competency Tier cannot be derived from the book at all.

Only book content is sent to the embedding provider. Student work never reaches this path.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.ingest.jina import JinaEmbedder
from app.models import BookChunk

#: one request per batch; large enough to be few calls, small enough to retry cheaply
BATCH = 32


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", help="limit to one subject code, e.g. X.MATH")
    parser.add_argument("--re-embed", action="store_true",
                        help="replace existing vectors (needed after changing model or dimensions)")
    parser.add_argument("--dry-run", action="store_true", help="report the work, send nothing")
    args = parser.parse_args()

    settings = get_settings()
    db = SessionLocal()
    try:
        query = select(BookChunk)
        if args.subject:
            query = query.where(BookChunk.subject_code == args.subject)
        chunks = db.scalars(query).all()
        if not chunks:
            raise SystemExit("no chunks -- run scripts.ingest_book first")

        todo = chunks if args.re_embed else [c for c in chunks if not c.embedding]
        tokens = sum(len(c.text) for c in todo) // 4
        print(f"{len(chunks)} chunks, {len(todo)} to embed (~{tokens:,} tokens)")
        print(f"model {settings.embedding_model} at {settings.embedding_dimensions} dimensions")

        if not todo:
            print("nothing to do -- every chunk already has a vector")
            return
        if args.dry_run:
            print("dry run -- nothing sent.")
            return

        embedder = JinaEmbedder(
            settings.jina_api_key or "",
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )

        done = 0
        for start in range(0, len(todo), BATCH):
            batch = todo[start:start + BATCH]
            vectors = embedder.embed_texts([c.text for c in batch])
            if len(vectors) != len(batch):
                raise SystemExit(
                    f"provider returned {len(vectors)} vectors for {len(batch)} chunks; "
                    f"refusing to write a misaligned index"
                )
            for chunk, vector in zip(batch, vectors, strict=True):
                chunk.embedding = vector
            db.commit()          # commit per batch: a failure halfway keeps its progress
            done += len(batch)
            print(f"  embedded {done}/{len(todo)}")

        print(f"done. {done} chunks now searchable by similarity.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
