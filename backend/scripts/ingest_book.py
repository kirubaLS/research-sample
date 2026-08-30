"""Load a subject's book into the knowledge base.

    python -m scripts.ingest_book ../ncert/X/maths --subject X.MATH --dry-run
    python -m scripts.ingest_book ../ncert/X/maths --subject X.MATH

Always dry-run first. A mis-read structure pass poisons every number computed downstream
and is invisible once loaded, so the run refuses to write unless every chapter agrees with
the book's own contents page.

Expects the layout in docs/yaadhum-knowledge-base.md:

    00-contents.pdf              the prelims -- the verification oracle, never content
    01-real-numbers.pdf ...      the chapters
    an-answers.pdf               EXCLUDED: answers to the exercises, not content
    a1-*.pdf, a2-*.pdf           EXCLUDED: outside the Class X syllabus
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select

from app.db import SessionLocal
from app.ingest.book import ChapterExtract, extract_chapter, parse_toc, verify_against_toc
from app.models import BookChunk, CanonicalProcedure, ChapterBoardUnit, TaxonomyNode

CONTENTS = "00-contents.pdf"


def chapter_files(directory: Path) -> list[Path]:
    """Numbered chapters only.

    The answers file matches 'EXERCISE' 31 times, so a looser glob would load the answer
    key as practice content -- silent, and badly wrong.
    """
    return sorted(p for p in directory.glob("[0-9][0-9]-*.pdf") if p.name != CONTENTS)


def load(db, extract: ChapterExtract, subject: str, version: str) -> dict:
    subject_node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == subject))
    if subject_node is None:
        raise SystemExit(f"subject {subject!r} is not in the taxonomy -- seed it first")

    # Match an existing chapter by its title before minting a new node. The chapters a
    # syllabus load already created carry the board-unit mapping; creating a parallel node
    # per chapter would leave the ingested content with no board unit, and board impact
    # would silently come out blank rather than wrong.
    chapter = db.scalar(
        select(TaxonomyNode).where(
            TaxonomyNode.kind == "chapter",
            func.lower(TaxonomyNode.label) == extract.title.lower(),
        )
    )
    chapter_code = chapter.code if chapter else f"{subject}.CH{extract.number:02d}"
    if chapter is None:
        chapter = TaxonomyNode(
            kind="chapter", code=chapter_code, label=extract.title,
            parent_id=subject_node.id, path=chapter_code, curriculum_version=version,
        )
        db.add(chapter)
        db.flush()

    for section in extract.sections:
        code = f"{chapter_code}.S{section.number.replace('.', '_')}"
        if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code)) is None:
            db.add(TaxonomyNode(
                kind="subtopic", code=code, label=section.title,
                parent_id=chapter.id, path=code, curriculum_version=version,
            ))

    written = {"chunks": 0, "procedures": 0}
    for chunk in extract.chunks:
        if db.scalar(
            select(BookChunk).where(
                BookChunk.stem_hash == chunk.stem_hash,
                BookChunk.curriculum_version == version,
            )
        ) is None:
            db.add(BookChunk(
                curriculum_version=version, subject_code=subject, node_id=chapter.id,
                bucket=chunk.bucket, reference=chunk.reference,
                text=chunk.text, normalised=chunk.text,
                stem_hash=chunk.stem_hash,
            ))
            written["chunks"] += 1

        # Theorems and worked examples also get an exact-match row: familiarity has to
        # answer "is this literally Theorem 1.3?" with yes or no, not a similarity score
        # above a threshold that would need tuning per subject forever.
        if chunk.kind in ("theorem", "example") and db.scalar(
            select(CanonicalProcedure).where(
                CanonicalProcedure.stem_hash == chunk.stem_hash,
                CanonicalProcedure.curriculum_version == version,
            )
        ) is None:
            db.add(CanonicalProcedure(
                curriculum_version=version, subject_code=subject, chapter_id=chapter.id,
                name=chunk.reference, reference=chunk.reference,
                canonical_stem=chunk.text, stem_hash=chunk.stem_hash,
                taught_verbatim=True,
            ))
            written["procedures"] += 1

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--subject", required=True, help="taxonomy subject code, e.g. X.MATH")
    parser.add_argument("--curriculum-version", default="CBSE-2026-27")
    parser.add_argument("--dry-run", action="store_true", help="report and write nothing")
    args = parser.parse_args()

    contents = args.directory / CONTENTS
    if not contents.exists():
        raise SystemExit(
            f"{contents} not found. The contents page is what makes an extraction "
            f"checkable rather than merely plausible; without it, do not load."
        )

    toc = parse_toc(contents)
    files = chapter_files(args.directory)
    if not files:
        raise SystemExit(f"no NN-*.pdf chapter files in {args.directory}")

    print(f"contents page lists {len(toc)} chapters; found {len(files)} chapter files\n")

    extracts = [verify_against_toc(extract_chapter(p), toc) for p in files]

    for e in extracts:
        c = e.counts()
        print(
            f"  {'ok  ' if e.ok else 'FAIL'} ch{e.number:>2}  {e.title[:32]:32} "
            f"sections={c['sections']:>2}  theorem={c['theorem']:>2} "
            f"example={c['example']:>2} exercise={c['exercise']}"
        )
        for problem in e.problems:
            print(f"         - {problem}")

    failed = [e for e in extracts if not e.ok]
    missing = sorted(set(toc) - {e.number for e in extracts})
    if missing:
        print(f"\n  note: contents page lists chapters {missing} with no file supplied")

    print()
    if failed:
        print(f"{len(failed)} chapter(s) disagree with the contents page. Nothing written.")
        sys.exit(1)

    total = sum(len(e.chunks) for e in extracts)
    print(f"all {len(extracts)} chapters agree with the contents page ({total} chunks)")

    if args.dry_run:
        print("dry run -- nothing written. Re-run without --dry-run to load.")
        return

    db = SessionLocal()
    try:
        written = {"chunks": 0, "procedures": 0}
        for e in extracts:
            for k, v in load(db, e, args.subject, args.curriculum_version).items():
                written[k] += v
        db.commit()
        print(f"loaded {written['chunks']} chunks, {written['procedures']} canonical procedures")

        # Board impact is computed per board unit, so a chapter with no mapping contributes
        # nothing and does so quietly. Name them rather than leaving a blank in a report.
        mapped = {row[0] for row in db.execute(select(ChapterBoardUnit.chapter_id)).all()}
        unmapped = [
            db.get(TaxonomyNode, node_id).label
            for (node_id,) in db.execute(select(BookChunk.node_id).distinct()).all()
            if node_id not in mapped
        ]
        if unmapped:
            print()
            print(f"{len(unmapped)} chapter(s) have no board unit yet, so they are invisible")
            print("to board-impact reporting until mapped:")
            for label in sorted(unmapped):
                print(f"  - {label}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
