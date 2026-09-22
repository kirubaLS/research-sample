"""Diagnostic: list every X.ENG.WB chapter node and how many BookChunk rows sit under it.

Run inside the backend container:
    docker compose -f infra/docker-compose.yml exec backend python3 -m scripts.diagnose_wb

(copy this file to backend/scripts/diagnose_wb.py first, or run inline -- see instructions
given alongside this file)
"""
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.taxonomy import BookChunk, TaxonomyNode

db = SessionLocal()
try:
    chapters = db.scalars(
        select(TaxonomyNode)
        .where(TaxonomyNode.kind == "chapter", TaxonomyNode.code.like("X.ENG.WB.%"))
        .order_by(TaxonomyNode.code)
    ).all()
    print(f"{len(chapters)} chapter node(s) found under X.ENG.WB\n")
    for ch in chapters:
        count = db.scalar(
            select(func.count(BookChunk.id)).where(BookChunk.node_id == ch.id)
        )
        print(f"{ch.code:35s} label={ch.label!r:45s} version={ch.curriculum_version!r:20s} chunks={count}")

    print("\n--- all BookChunk rows for X.ENG.WB, grouped by node_id (in case a chunk is under an unlisted/orphan node) ---")
    rows = db.execute(
        select(BookChunk.node_id, func.count(BookChunk.id))
        .where(BookChunk.subject_code == "X.ENG.WB")
        .group_by(BookChunk.node_id)
    ).all()
    known_ids = {ch.id for ch in chapters}
    for node_id, count in rows:
        flag = "" if node_id in known_ids else "  <-- ORPHAN: chunks exist but no matching chapter node listed above"
        print(f"node_id={node_id} chunks={count}{flag}")
finally:
    db.close()
