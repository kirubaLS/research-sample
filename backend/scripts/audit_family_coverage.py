"""Find every chapter where concept-family placement is structurally blind.

Grew directly out of a real audit: a Class 10 Political Parties paper had every single
question flagged for review, and most were wrong. The root cause traced to
app.mapping.family.choose_family(): when a chapter has more than one concept family and
the judge's proposed section gets stripped (app.classify.grounding.ground(), because the
book's own headings never yielded a numbered section for that chapter -- see
app.ingest.book's "without this the section is lost"), there is nothing left to
disambiguate on, and choose_family() correctly refuses to guess rather than silently
picking one. Correct behaviour, but it means every question of that chapter is
permanently stuck needing a human -- not just on the paper that surfaced it.

This script finds every OTHER chapter with the same blind spot before it produces the
next bad report, and separately measures how much it has already cost in needs_review
rows sitting unresolved. Read-only: it changes nothing.

Run inside the backend container so it reads the same database the app does:
    docker compose -f infra/docker-compose.yml exec backend python -m scripts.audit_family_coverage
Or locally against the dev sqlite db:
    python -m scripts.audit_family_coverage
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from app.db import SessionLocal
from app.models import ConceptFamilyProposal, QuestionPlacement, TaxonomyNode


def main() -> None:
    db = SessionLocal()
    try:
        chapters = {
            n.id: n
            for n in db.scalars(select(TaxonomyNode).where(TaxonomyNode.kind == "chapter"))
        }
        families = {
            n.id: n
            for n in db.scalars(select(TaxonomyNode).where(TaxonomyNode.kind == "concept_family"))
        }

        # Every applied family, grouped by its chapter -- the same population
        # choose_family() draws its `candidates` from.
        by_chapter: dict[str, list[TaxonomyNode]] = defaultdict(list)
        for fam in families.values():
            if fam.parent_id in chapters:
                by_chapter[fam.parent_id].append(fam)

        # from_sections lives on the PROPOSAL, keyed by code+subject+run -- the applied
        # node itself carries no section data, so this is the only place to read it.
        # Latest proposal per family code wins, same as apply_curriculum would use.
        sections_by_code: dict[str, list[str]] = {}
        for prop in db.scalars(
            select(ConceptFamilyProposal).order_by(ConceptFamilyProposal.created_at)
        ):
            sections_by_code[prop.code] = prop.from_sections or []

        blind: list[tuple[TaxonomyNode, int]] = []
        single_family: list[TaxonomyNode] = []
        for chapter_id, fams in by_chapter.items():
            chapter = chapters[chapter_id]
            if len(fams) <= 1:
                single_family.append(chapter)
                continue
            total_sections = sum(len(sections_by_code.get(f.code, [])) for f in fams)
            if total_sections == 0:
                blind.append((chapter, len(fams)))

        print(f"{len(chapters)} chapters, {len(families)} applied concept families.\n")

        if blind:
            print(
                "CHAPTERS WHERE FAMILY PLACEMENT IS BLIND (multiple families, none carry a "
                "section -- every question here is forced into 'blocked' review the moment "
                "curriculum_section comes back None, exactly the Political Parties failure):"
            )
            for chapter, n in sorted(blind, key=lambda t: t[0].label):
                print(f"  - {chapter.label} ({chapter.code}): {n} families, 0 sections between them")
        else:
            print("No chapter is fully section-blind across every one of its families.")

        print(f"\n{len(single_family)} chapters have only one family (nothing to disambiguate, safe by construction).")

        # Cross-reference against what actually happened: needs_review placements whose
        # own reasoning names this exact "blocked" condition (choose_family's own wording,
        # via _run_placement_job's `choice.blocked` append), grouped by chapter.
        blocked_counts: dict[str, int] = defaultdict(int)
        total_needs_review = 0
        for row in db.scalars(
            select(QuestionPlacement).where(QuestionPlacement.needs_review.is_(True))
        ):
            total_needs_review += 1
            if row.reasoning and "families of" in row.reasoning and "draw on section" in row.reasoning:
                chapter = chapters.get(row.chapter_id) if row.chapter_id else None
                key = chapter.label if chapter else "(no chapter recorded)"
                blocked_counts[key] += 1

        print(f"\n{total_needs_review} QuestionPlacement rows currently need review, school-wide.")
        if blocked_counts:
            print("Of those, blocked specifically by family disambiguation (not a chapter question at all):")
            for label, count in sorted(blocked_counts.items(), key=lambda kv: -kv[1]):
                print(f"  - {label}: {count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
