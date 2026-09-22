"""Remove Words and Expressions chunks that got mis-attached to First Flight's chapter
nodes before the node-scoping fix (app/api/books.py, scripts/ingest_book.py).

These rows are correctly tagged subject_code="X.ENG.WB" but sit under a First Flight
chapter node instead of their own Workbook node -- diagnose_wb.py calls them "orphans"
because no X.ENG.WB.* chapter node owns them. Deleting them is safe: a correct re-upload
of the Workbook (after this fix is deployed) writes its own chunks under the Workbook's
own chapter nodes from scratch, and does not depend on these rows in any way.

Run inside the backend container, dry-run first:
    docker compose -f infra/docker-compose.yml exec backend python3 -m scripts.cleanup_wb_orphans --dry-run
    docker compose -f infra/docker-compose.yml exec backend python3 -m scripts.cleanup_wb_orphans
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db import SessionLocal
from app.models.taxonomy import BookChunk, TaxonomyNode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report and delete nothing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        wb_node_ids = {
            n.id
            for n in db.scalars(
                select(TaxonomyNode).where(
                    TaxonomyNode.kind == "chapter", TaxonomyNode.code.like("X.ENG.WB.%")
                )
            )
        }
        orphans = db.scalars(
            select(BookChunk).where(
                BookChunk.subject_code == "X.ENG.WB", BookChunk.node_id.notin_(wb_node_ids)
            )
        ).all()

        if not orphans:
            print("no orphaned X.ENG.WB chunks found -- nothing to clean up")
            return

        by_node: dict = {}
        for chunk in orphans:
            by_node.setdefault(chunk.node_id, []).append(chunk)

        for node_id, chunks in by_node.items():
            node = db.get(TaxonomyNode, node_id)
            label = node.label if node else "(unknown node)"
            print(f"node_id={node_id} label={label!r}: {len(chunks)} mis-attached WB chunk(s)")
            for chunk in chunks:
                print(f"    - {chunk.text[:70]!r}")

        if args.dry_run:
            print(f"\ndry run -- {len(orphans)} chunk(s) would be deleted. Re-run without --dry-run to delete.")
            return

        for chunk in orphans:
            db.delete(chunk)
        db.commit()
        print(f"\ndeleted {len(orphans)} mis-attached chunk(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
