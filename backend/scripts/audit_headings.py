"""Compare a book's real headings (as extracted from the actual NCERT PDFs, given as a
File/Order/Title TSV) against the subtopic nodes actually stored in the database for that
subject, and print the same kind of table already produced by hand for Social Science:

    Real headings in book | Correctly mapped | Missing | Duplicated | Truncated |
    Extra non-heading subtopics | Total subtopics in DB

Input TSV format (tab-separated, header row "File\tOrder\tTitle"):
    jemh101.pdf	1	Real Numbers
    jemh101.pdf	2	The Fundamental Theorem of Arithmetic
    ...
The FIRST row for each File is treated as the chapter's own title, not a heading inside
it -- everything after that, for that file, is a real heading to look for among the
chapter's subtopic nodes.

Run inside the backend container:
    docker compose -f infra/docker-compose.yml exec backend \
        python3 -m scripts.audit_headings --subject X.MATH --tsv scripts/heading_audit_data/X.MATH.tsv
"""
from __future__ import annotations

import argparse
import csv
import re

from sqlalchemy import select

from app.db import SessionLocal
from app.models.taxonomy import TaxonomyNode


def _normalize_punct(title: str) -> str:
    # A real PDF's text layer sometimes renders extra inter-word spacing ("...and  Life"),
    # a kerning artifact, not a different heading -- confirmed on the real "Mirror
    # Formula and  Magnification" subtopic. Collapsed before comparing so this reads as
    # the same heading it is, not a false "missing" alongside a false "extra".
    title = re.sub(r"\s+", " ", title.strip().lower())
    # A curly apostrophe/quote (‘’“”) and an en/em dash (–—) are the same punctuation as
    # their plain-ASCII equivalents, just rendered differently by whichever tool produced
    # the reference list versus the PDF's own text layer -- confirmed on the real
    # "Jhumming: The 'slash and burn' agriculture" and "Bhoodan – Gramdan" headings, each
    # stored under one spelling and listed under the other, reading as a false "missing"
    # alongside a false "extra" the same way inconsistent whitespace already did above.
    title = title.translate({
        0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x2013: "-", 0x2014: "-",
    })
    return re.sub(r"\s*-\s*", " - ", title)


def _clean(title: str) -> str:
    # Headings in the TSV carry their own numbering ("2.1 The Aristocracy..."); the
    # database's subtopic label does not, since the number is stored separately as
    # section_number. Strip a leading "N", "N.N", "N.N.N" (etc.) prefix before comparing.
    return _normalize_punct(re.sub(r"^\d+(?:\.\d+)*\s+", "", title))


def load_tsv(path: str) -> dict[str, list[str]]:
    chapters: dict[str, list[tuple[str, str]]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            # A topic list pasted together from several blocks can carry its own header
            # row ("File\tOrder\tTitle") repeated partway through -- confirmed on the
            # real X.SCI list, which has it three times. Not a chapter, not a heading.
            if row["File"] == "File" and row["Order"] == "Order" and row["Title"] == "Title":
                continue
            chapters.setdefault(row["File"], []).append((row["Order"], row["Title"]))
    # First row per file = chapter title, not a heading.
    return {
        file: [title for _, title in rows[1:]]
        for file, rows in chapters.items()
        if len(rows) > 1
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--tsv", required=True)
    args = parser.parse_args()

    chapters = load_tsv(args.tsv)
    real_headings = [h for hs in chapters.values() for h in hs]

    db = SessionLocal()
    try:
        subject_node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == args.subject))
        if subject_node is None:
            raise SystemExit(f"subject {args.subject!r} not found in the taxonomy")

        chapter_nodes = db.scalars(
            select(TaxonomyNode).where(
                TaxonomyNode.kind == "chapter", TaxonomyNode.parent_id == subject_node.id
            )
        ).all()
        by_label = {n.label.strip().lower(): n for n in chapter_nodes}

        all_subtopic_labels: list[str] = []
        matched_count = 0
        missing: list[str] = []
        duplicated: list[str] = []
        truncated: list[str] = []

        # load_tsv() above keeps only the headings, dropping each file's own title (the
        # first row) -- recover file -> chapter title in a second pass.
        file_title: dict[str, str] = {}
        with open(args.tsv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            seen_files: set[str] = set()
            for row in reader:
                if row["File"] == "File" and row["Order"] == "Order" and row["Title"] == "Title":
                    continue
                if row["File"] not in seen_files:
                    file_title[row["File"]] = row["Title"]
                    seen_files.add(row["File"])

        for file, headings in chapters.items():
            title = file_title.get(file, "")
            chapter_node = by_label.get(title.strip().lower())
            if chapter_node is None:
                # No chapter loaded under this title -- every heading for it is missing.
                missing.extend(f"{title}: {h}" for h in headings)
                continue

            subtopics = db.scalars(
                select(TaxonomyNode).where(
                    TaxonomyNode.kind == "subtopic", TaxonomyNode.parent_id == chapter_node.id
                )
            ).all()
            labels = [_normalize_punct(s.label) for s in subtopics]
            all_subtopic_labels.extend(labels)

            for heading in headings:
                clean = _clean(heading)
                exact = [l for l in labels if l == clean]
                if len(exact) == 1:
                    matched_count += 1
                elif len(exact) > 1:
                    matched_count += 1
                    duplicated.append(f"{title}: {heading}")
                else:
                    partial = [l for l in labels if l and (clean.startswith(l) or l.startswith(clean)) and l != clean]
                    if partial:
                        matched_count += 1
                        truncated.append(f"{title}: {heading}  (db has: {partial[0]!r})")
                    else:
                        missing.append(f"{title}: {heading}")

        matched_labels = set()
        for file, headings in chapters.items():
            title = file_title.get(file, "")
            chapter_node = by_label.get(title.strip().lower())
            if chapter_node is None:
                continue
            for heading in headings:
                matched_labels.add(_clean(heading))
        extra = [l for l in all_subtopic_labels if l not in matched_labels]

        print(f"subject: {args.subject}")
        print(f"real headings in book: {len(real_headings)}")
        print(f"correctly mapped: {matched_count}")
        print(f"missing: {len(missing)}")
        print(f"duplicated: {len(duplicated)}")
        print(f"truncated: {len(truncated)}")
        print(f"extra non-heading subtopics: {len(extra)}")
        print(f"total subtopics in db: {len(all_subtopic_labels)}")

        if missing:
            print(f"\n--- missing ({len(missing)}) ---")
            for m in missing:
                print(f"  - {m}")
        if duplicated:
            print(f"\n--- duplicated ({len(duplicated)}) ---")
            for d in duplicated:
                print(f"  - {d}")
        if truncated:
            print(f"\n--- truncated ({len(truncated)}) ---")
            for t in truncated:
                print(f"  - {t}")
        if extra:
            print(f"\n--- extra non-heading subtopics ({len(extra)}) ---")
            for e in extra:
                print(f"  - {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
