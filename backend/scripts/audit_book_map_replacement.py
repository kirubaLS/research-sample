"""Read-only: what replacing the Social Science knowledge base would actually touch.

Before importing reference/book_map/ (the audited, page-verified NCERT unit map for
X.HIST/X.POL/X.ECO/X.GEO) and removing the old auto-ingested data for those four
subjects, this reports what is safe to delete outright versus what must be carefully
migrated rather than dropped:

* BookChunk rows for these subjects -- nothing else holds a hard foreign key to a
  specific chunk (evidence is stored as free-text references, never a chunk id), so
  these are always safe to delete and replace wholesale.
* TaxonomyNode chapter/concept_family rows -- Question.chapter_id, Question.
  concept_family_id, and QuestionPlacement's own copies are REAL foreign keys. Any
  question a teacher has already placed or graded points at one of these ids. A node
  whose CODE also appears in the new book map can be kept (same id, just re-labelled/
  re-parented if needed); a node whose code does NOT appear in the new map, but which
  real questions still point to, cannot simply be deleted -- those questions would need
  their placement re-run (or hand review) against the new map first.

Run inside the backend container, against the real database:
    docker compose -f infra/docker-compose.yml exec backend python -m scripts.audit_book_map_replacement
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import BookChunk, ConceptFamilyProposal, Question, TaxonomyNode

SUBJECT_CODES = ["X.HIST", "X.GEO", "X.POL", "X.ECO"]


def main() -> None:
    db = SessionLocal()
    try:
        for subject_code in SUBJECT_CODES:
            print(f"\n=== {subject_code} ===")

            chunk_count = db.scalar(
                select(func.count(BookChunk.id)).where(BookChunk.subject_code == subject_code)
            )
            print(f"BookChunk rows (safe to delete + replace wholesale): {chunk_count}")

            subject_node = db.scalar(
                select(TaxonomyNode).where(TaxonomyNode.kind == "subject", TaxonomyNode.code == subject_code)
            )
            if subject_node is None:
                print("No subject taxonomy node found -- nothing else to check here.")
                continue

            chapters = list(db.scalars(
                select(TaxonomyNode).where(TaxonomyNode.kind == "chapter", TaxonomyNode.parent_id == subject_node.id)
            ))
            chapter_ids = {c.id for c in chapters}
            families = list(db.scalars(
                select(TaxonomyNode).where(
                    TaxonomyNode.kind == "concept_family", TaxonomyNode.parent_id.in_(chapter_ids)
                )
            )) if chapter_ids else []
            print(f"Chapters: {len(chapters)}   Concept families: {len(families)}")

            # Every family a REAL question already points at -- these ids must survive
            # (kept, or the question repointed) rather than being dropped outright.
            family_ids = {f.id for f in families}
            used_family_ids = set(db.scalars(
                select(Question.concept_family_id).where(Question.concept_family_id.in_(family_ids)).distinct()
            )) if family_ids else set()
            print(f"Concept families with at least one real question already filed under them: {len(used_family_ids)}")
            if used_family_ids:
                for f in families:
                    if f.id not in used_family_ids:
                        continue
                    n = db.scalar(select(func.count(Question.id)).where(Question.concept_family_id == f.id))
                    print(f"  - {f.code} ({f.label}): {n} question(s) filed here")

            proposal_count = db.scalar(
                select(func.count(ConceptFamilyProposal.id)).where(
                    ConceptFamilyProposal.subject_code == subject_code
                )
            )
            print(f"ConceptFamilyProposal rows (history; safe to supersede): {proposal_count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
