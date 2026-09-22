"""Diagnostic: for a given X.MATH chapter, list its own chapter node and every subtopic
node under it, so a heading the audit calls "missing" or "extra" can be traced to what is
actually stored, rather than guessed at.

Run inside the backend container:
    docker compose -f infra/docker-compose.yml exec backend \
        python3 -m scripts.diagnose_math_subtopics "Pair of Linear Equations in Two Variables"
"""
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models.taxonomy import TaxonomyNode

db = SessionLocal()
try:
    title = sys.argv[1] if len(sys.argv) > 1 else "Pair of Linear Equations in Two Variables"
    chapter = db.scalar(
        select(TaxonomyNode).where(
            TaxonomyNode.kind == "chapter",
            TaxonomyNode.label.ilike(title),
        )
    )
    if chapter is None:
        print(f"no chapter node found with label {title!r} (case-insensitive, exact match)")
        # Show close matches so a typo or a different exact wording is easy to spot.
        close = db.scalars(
            select(TaxonomyNode).where(
                TaxonomyNode.kind == "chapter",
                TaxonomyNode.label.ilike(f"%{title.split()[0]}%"),
            )
        ).all()
        for c in close:
            print(f"  close match: code={c.code} label={c.label!r} parent_id={c.parent_id}")
    else:
        print(f"chapter: code={chapter.code} label={chapter.label!r} parent_id={chapter.parent_id}")
        subtopics = db.scalars(
            select(TaxonomyNode)
            .where(TaxonomyNode.kind == "subtopic", TaxonomyNode.parent_id == chapter.id)
            .order_by(TaxonomyNode.code)
        ).all()
        print(f"{len(subtopics)} subtopic(s) under it:")
        for s in subtopics:
            print(f"  code={s.code:30s} label={s.label!r}")
finally:
    db.close()
