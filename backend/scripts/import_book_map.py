"""Replace the Social Science knowledge base with the audited book_map.

backend/reference/book_map/ is a page-verified, board-paper-tested unit map for the four
Class X Social Science NCERT books (History, Politics, Economics, Geography) -- see its
own README.md/AUDIT.md/HANDOVER.md. Its 22 chapter codes match app.curriculum's own
X_HIST/X_POL/X_ECO/X_GEO definitions exactly (confirmed chapter by chapter before this
script was written), so those chapter nodes are kept as-is -- this only replaces what
sits BELOW a chapter: its concept families, their section coverage, and its book text.

Why replace rather than add alongside: `_run_placement_job`'s own `sections_of` is a
plain dict keyed by concept-family code with no ORDER BY on the query that fills it --
if a stale, section-empty proposal row for the same code survives next to a fresh
correct one, which one `choose_family` sees is arbitrary. Leaving old rows in place is
not a neutral "extra data point", it is a live landmine. So this script deletes what it
is superseding rather than only adding to it -- explicitly asked for, and the safe way
to do it.

Safe to delete outright:
* Every BookChunk row for X.HIST/X.POL/X.ECO/X.GEO -- nothing else holds a hard foreign
  key to a specific chunk (evidence is a free-text reference, never a chunk id).
* Every ConceptFamilyProposal row for those subjects -- provenance-only, and the
  argument above for why stale ones must not survive alongside new ones.
* A concept_family TaxonomyNode whose code is not in the new map AND has zero real
  Question rows pointing at it -- dead, unused, safe.

Never deleted, only updated in place (same id, so nothing that points at it breaks):
* Chapter TaxonomyNode rows (matched by code -- already exist from app.curriculum).
* A concept_family TaxonomyNode whose code IS in the new map (its label/parent are
  refreshed to match, its id never changes).

Reported, never touched: a concept_family TaxonomyNode not in the new map that DOES have
a real Question filed under it. Deleting that would orphan an already-graded student's
report. This script will not decide that for you -- it prints exactly which chapter,
which family, and how many questions, and leaves it alone.

Dry-run by default. Pass --apply to actually commit.

Run inside the backend container, against the real database:
    docker compose -f infra/docker-compose.yml exec backend python -m scripts.import_book_map
    docker compose -f infra/docker-compose.yml exec backend python -m scripts.import_book_map --apply
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from sqlalchemy import func, select

from app.db import SessionLocal
from app.ingest.book import normalise, stem_hash
from app.models import BookChunk, ConceptFamilyProposal, Question, TaxonomyNode

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference" / "book_map"
SUBJECT_FILES = {
    "X.HIST": "history/history_units.json",
    "X.GEO": "geography/geography_units.json",
    "X.POL": "politics/politics_units.json",
    "X.ECO": "economics/economics_units.json",
}
RUN_ID = "book_map_import_v1"


def _text_chunks(chapter_code: str, unit: dict) -> list[tuple[str, str, str]]:
    """Every (reference, section_number, text) triple this unit contributes, primary and
    supporting evidence alike -- this book map's own README says activities and captions
    ARE searched when locating a topic, just not the first thing offered, and this
    retrieval has no tiering mechanism to prefer one bucket over another anyway."""
    number = unit.get("number")
    title = unit.get("title") or unit["id"]
    label = f"{number} {title}" if number else title
    out: list[tuple[str, str, str]] = []

    for b in unit.get("body", []):
        text = (b.get("text") or "").strip()
        if text:
            out.append((label, number, text))

    for t in unit.get("terms", []):
        term, definition = t.get("term"), (t.get("definition") or "").strip()
        if term and definition:
            out.append((f"{label} (glossary: {term})", number, f"{term} -- {definition}"))

    for box in unit.get("boxes", []):
        text = " ".join(x for x in box.get("text", []) if x).strip()
        if text:
            box_label = f"{label} (box: {box['title']})" if box.get("title") else f"{label} (box)"
            out.append((box_label, number, text))

    for src in unit.get("sources", []):
        text = " ".join(x for x in src.get("text", []) if x).strip()
        if text:
            src_label = f"{label} (source: {src['title']})" if src.get("title") else f"{label} (source)"
            out.append((src_label, number, text))

    for act in unit.get("activities", []):
        text = " ".join(x for x in act.get("text", []) if x).strip()
        if text:
            out.append((f"{label} (activity)", number, text))

    for cap in unit.get("captions", []):
        text = (cap.get("text") or "").strip()
        if text:
            out.append((f"{label} (caption)", number, text))

    return out


def _load_chapter(path: Path, chapter_code: str) -> dict:
    data = json.loads(path.read_text())
    matches = [c for c in data if c["code"] == chapter_code]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one chapter {chapter_code!r} in {path}, found {len(matches)}")
    return matches[0]


def _plan_subject(db, subject_code: str, path: Path) -> dict:
    """Read-only: what this subject's import would do. Used by both --dry-run's report
    and --apply's actual writes, so the two can never silently disagree."""
    data = json.loads(path.read_text())
    subject_node = db.scalar(
        select(TaxonomyNode).where(TaxonomyNode.kind == "subject", TaxonomyNode.code == subject_code)
    )
    if subject_node is None:
        raise RuntimeError(
            f"no subject taxonomy node for {subject_code!r} -- run app.curriculum.apply's "
            f"curriculum loader for this subject first"
        )

    chapters_in_map = {c["code"] for c in data}
    existing_chapters = {
        n.code: n for n in db.scalars(
            select(TaxonomyNode).where(TaxonomyNode.kind == "chapter", TaxonomyNode.parent_id == subject_node.id)
        )
    }
    missing_chapters = sorted(chapters_in_map - set(existing_chapters))
    if missing_chapters:
        raise RuntimeError(
            f"{subject_code}: chapters in the book map but not in this database's taxonomy: "
            f"{missing_chapters} -- run the curriculum loader first, or the codes have drifted"
        )

    new_family_codes: set[str] = set()
    for chapter in data:
        for unit in chapter["units"]:
            if unit.get("catalog"):
                new_family_codes.add(unit["catalog"])

    existing_families = list(db.scalars(
        select(TaxonomyNode).where(
            TaxonomyNode.kind == "concept_family",
            TaxonomyNode.parent_id.in_([n.id for n in existing_chapters.values()]),
        )
    ))
    stale_families = [f for f in existing_families if f.code not in new_family_codes]
    stale_with_questions = []
    stale_deletable = []
    for f in stale_families:
        n = db.scalar(select(func.count(Question.id)).where(Question.concept_family_id == f.id))
        (stale_with_questions if n else stale_deletable).append((f, n))

    old_chunks = db.scalar(select(func.count(BookChunk.id)).where(BookChunk.subject_code == subject_code))
    old_proposals = db.scalar(
        select(func.count(ConceptFamilyProposal.id)).where(ConceptFamilyProposal.subject_code == subject_code)
    )

    return {
        "subject_node": subject_node,
        "chapters": existing_chapters,
        "new_family_codes": new_family_codes,
        "stale_deletable": stale_deletable,
        "stale_with_questions": stale_with_questions,
        "old_chunk_count": old_chunks,
        "old_proposal_count": old_proposals,
        "data": data,
    }


def _apply_subject(db, subject_code: str, plan: dict) -> None:
    chapters = plan["chapters"]

    # 1. Wipe what this import supersedes.
    db.query(BookChunk).filter(BookChunk.subject_code == subject_code).delete()
    db.query(ConceptFamilyProposal).filter(ConceptFamilyProposal.subject_code == subject_code).delete()
    for family, _ in plan["stale_deletable"]:
        db.delete(family)

    # 2. One concept_family node per catalog code, updated in place if it already exists.
    family_nodes: dict[str, TaxonomyNode] = {
        n.code: n for n in db.scalars(
            select(TaxonomyNode).where(
                TaxonomyNode.kind == "concept_family",
                TaxonomyNode.parent_id.in_([c.id for c in chapters.values()]),
            )
        )
    }

    for chapter_json in plan["data"]:
        chapter = chapters[chapter_json["code"]]
        family_sections: dict[str, set[str]] = {}
        family_labels: dict[str, str] = {}

        for unit in chapter_json["units"]:
            catalog = unit.get("catalog")
            if not catalog:
                continue
            family_labels.setdefault(catalog, unit.get("title") or catalog)
            if unit.get("number"):
                family_sections.setdefault(catalog, set()).add(str(unit["number"]))

            for reference, section, text in _text_chunks(chapter_json["code"], unit):
                db.add(BookChunk(
                    curriculum_version=chapter.curriculum_version, subject_code=subject_code,
                    node_id=chapter.id, bucket="T", reference=reference[:80],
                    section_number=section, text=text, normalised=normalise(text).lower(),
                    stem_hash=stem_hash(text),
                ))

        exercise = chapter_json.get("exercise")
        if exercise and exercise.get("text"):
            for i, item in enumerate(exercise["text"], start=1):
                text = (item or "").strip()
                if not text:
                    continue
                db.add(BookChunk(
                    curriculum_version=chapter.curriculum_version, subject_code=subject_code,
                    node_id=chapter.id, bucket="E", reference=f"Exercise Q{i}"[:80],
                    section_number=None, text=text, normalised=normalise(text).lower(),
                    stem_hash=stem_hash(text),
                ))

        for code, label in family_labels.items():
            node = family_nodes.get(code)
            if node is None:
                node = TaxonomyNode(
                    kind="concept_family", code=code, label=label, parent_id=chapter.id,
                    path=code, curriculum_version=chapter.curriculum_version,
                )
                db.add(node)
                db.flush()
                family_nodes[code] = node
            else:
                node.label = label
                node.parent_id = chapter.id

            sections = sorted(family_sections.get(code, set()))
            db.add(ConceptFamilyProposal(
                curriculum_version=chapter.curriculum_version, subject_code=subject_code,
                run_id=RUN_ID, source="book_map", model=None,
                code=code, label=label, chapter_id=chapter.id,
                rationale="imported from the audited NCERT book_map (see reference/book_map/README.md)",
                evidence=sections, from_sections=sections,
            ))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="commit the changes; default is dry-run")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        plans = {}
        for subject_code, rel_path in SUBJECT_FILES.items():
            path = REFERENCE_DIR / rel_path
            if not path.exists():
                print(f"SKIP {subject_code}: {path} not found")
                continue
            plans[subject_code] = _plan_subject(db, subject_code, path)

        for subject_code, plan in plans.items():
            print(f"\n=== {subject_code} ===")
            print(f"Chapters matched: {len(plan['chapters'])}")
            print(f"Concept families in the new map: {len(plan['new_family_codes'])}")
            print(f"Old BookChunk rows to delete: {plan['old_chunk_count']}")
            print(f"Old ConceptFamilyProposal rows to delete: {plan['old_proposal_count']}")
            print(f"Old concept families with no questions filed (deleted): {len(plan['stale_deletable'])}")
            if plan["stale_with_questions"]:
                print(
                    f"Old concept families with REAL QUESTIONS filed -- kept untouched, "
                    f"not part of this import:"
                )
                for f, n in plan["stale_with_questions"]:
                    print(f"  - {f.code} ({f.label}): {n} question(s)")

        if not args.apply:
            print("\nDry run only -- nothing was changed. Re-run with --apply to commit.")
            return

        for subject_code, plan in plans.items():
            _apply_subject(db, subject_code, plan)
        db.commit()
        print("\nApplied.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
