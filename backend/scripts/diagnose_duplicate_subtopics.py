"""Diagnostic: find subtopic nodes under one subject that share the same label within
their own chapter -- almost always stale leftovers from an earlier upload whose invented
section numbering (for a book with no numbering of its own) differed from the current
one, so the old code was never recognised as "the same section" and never cleaned up.

Prints each duplicate group with its own chunk count, so the empty/near-empty one (the
stale leftover) can be told apart from the one holding the chapter's real content before
deleting it.

Run inside the backend container:
    docker compose -f infra/docker-compose.yml exec backend \
        python3 -m scripts.diagnose_duplicate_subtopics X.ECO
"""
import sys

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.taxonomy import BookChunk, TaxonomyNode

db = SessionLocal()
try:
    subject = sys.argv[1] if len(sys.argv) > 1 else "X.ECO"
    subject_node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == subject))
    if subject_node is None:
        print(f"subject {subject!r} not found")
        raise SystemExit(1)

    chapters = db.scalars(
        select(TaxonomyNode).where(
            TaxonomyNode.kind == "chapter", TaxonomyNode.parent_id == subject_node.id
        )
    ).all()

    found_any = False
    for chapter in chapters:
        subtopics = db.scalars(
            select(TaxonomyNode).where(
                TaxonomyNode.kind == "subtopic", TaxonomyNode.parent_id == chapter.id
            )
        ).all()
        by_label: dict[str, list[TaxonomyNode]] = {}
        for s in subtopics:
            by_label.setdefault(s.label.strip().lower(), []).append(s)

        for label, nodes in by_label.items():
            if len(nodes) < 2:
                continue
            found_any = True
            print(f"\nchapter={chapter.label!r} label={label!r}: {len(nodes)} duplicate node(s)")
            for n in nodes:
                count = db.scalar(select(func.count(BookChunk.id)).where(BookChunk.node_id == n.id))
                print(f"    code={n.code:30s} id={n.id} chunks={count}")

    if not found_any:
        print(f"no duplicate subtopic labels found under {subject}")
finally:
    db.close()
