"""What is actually in this database.

Run it before a migration and again after. The two outputs should differ only where you
expected them to, and if a chapter count moved you want to know now rather than when a
teacher opens a report.

    python -m scripts.inventory                       # whatever YAADHUM_DATABASE_URL says
    YAADHUM_DATABASE_URL=<neon branch> python -m scripts.inventory

Counts only. It prints no student name, no roll number and no answer text, so the output
is safe to paste into a message or a ticket.
"""

from __future__ import annotations

import sys

from sqlalchemy import func, inspect, select

from app.db import SessionLocal, engine
from app.models import (
    Assessment,
    BookChunk,
    ConceptFamilyProposal,
    MarkEvent,
    Question,
    ScanDocument,
    School,
    StudentProfile,
    TaxonomyNode,
)


def main() -> int:
    db = SessionLocal()
    try:
        version = None
        if inspect(engine).has_table("alembic_version"):
            version = db.exec_driver_sql("select version_num from alembic_version").scalar()
        print(f"schema version   {version or 'none -- migrations have never run here'}")
        print()

        print("--- the books -------------------------------------------------")
        for subject in ("X.MATH", "X.SCI"):
            chapters = db.scalar(
                select(func.count()).select_from(TaxonomyNode).where(
                    TaxonomyNode.kind == "chapter", TaxonomyNode.code.like(f"{subject}%")
                )
            )
            chunks = db.scalar(
                select(func.count()).select_from(BookChunk).where(
                    BookChunk.subject_code == subject
                )
            )
            embedded = db.scalar(
                select(func.count()).select_from(BookChunk).where(
                    BookChunk.subject_code == subject, BookChunk.embedding.is_not(None)
                )
            )
            families = db.scalar(
                select(func.count()).select_from(TaxonomyNode).where(
                    TaxonomyNode.kind == "concept_family",
                    TaxonomyNode.code.like(f"{subject}%"),
                )
            )
            proposals = db.scalar(
                select(func.count()).select_from(ConceptFamilyProposal).where(
                    ConceptFamilyProposal.subject_code == subject
                )
            )
            # Embedded matters on its own: without vectors only exact matches resolve, so
            # three of the four familiarity levels collapse and the tier cannot be derived.
            print(
                f"{subject:8s} chapters {chapters:3d}   chunks {chunks:5d}   "
                f"embedded {embedded:5d}   families {families:3d}   proposals {proposals:4d}"
            )

        print()
        print("--- the school ------------------------------------------------")
        for label, model in (
            ("schools", School),
            ("students", StudentProfile),
            ("assessments", Assessment),
            ("questions", Question),
            ("mark events", MarkEvent),
            ("stored documents", ScanDocument),
        ):
            print(f"{label:20s} {db.scalar(select(func.count()).select_from(model)):6d}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
