"""Turn a paper whose placements a teacher has confirmed into a gold key. READ-ONLY.

The gold set was one hand-keyed paper. Every paper a teacher reviews is another, for free:
a question whose latest placement was written by a person IS a labelled example. This
exports those, in the shape ``scripts.eval_mapping --gold`` and
``scripts.eval_dense_retrieval --gold`` read, so the evaluation grows with the review queue.

    python -m scripts.export_gold --assessment <id> --out gold/paper_<id>.json

Only confirmed questions are written, and only ones with a chapter and a section. A section
letter's chapter is the one most of its confirmed questions sit in; a question in another
chapter carries its own ``chapter``. Sections are collapsed to the gold key's two levels.
Run it against a staging copy of the database, never production.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

GOLD_DEPTH = 2


def build_gold(rows: list[dict], *, paper: str = "") -> dict:
    """``rows``: address, chapter (code), label, section (already collapsed) per confirmed
    question. Pure, so the shape is testable without a database."""
    by_letter: dict[str, Counter] = {}
    for r in rows:
        by_letter.setdefault(r["address"].split("/", 1)[0], Counter())[(r["chapter"], r["label"])] += 1
    section_chapters = {}
    for letter, counts in sorted(by_letter.items()):
        (code, label), _ = counts.most_common(1)[0]
        section_chapters[letter] = {
            "subject": code.rsplit(".", 1)[0], "chapter": code, "label": label,
        }
    questions = {}
    for r in sorted(rows, key=lambda r: r["address"]):
        entry: dict = {"exact": [r["section"]] if r["section"] else [], "partial": []}
        if r["chapter"] != section_chapters[r["address"].split("/", 1)[0]]["chapter"]:
            entry["chapter"] = r["chapter"]
        questions[r["address"]] = entry
    return {
        "paper": paper or "exported from confirmed placements",
        "description": "Gold key exported from teacher-confirmed placements; sections collapsed "
                       f"to {GOLD_DEPTH} levels; addresses as stored (SECTION/QNO/SUBPART/CHOICE).",
        "section_chapters": section_chapters,
        "targets": {"chapter_correct": len(questions), "max_depth": GOLD_DEPTH},
        "questions": questions,
    }


def confirmed_rows(db, assessment_id: str) -> list[dict]:
    from sqlalchemy import select

    from app.curriculum.book_map import major_of
    from app.models import Question, QuestionPlacement, TaxonomyNode

    out, seen = [], set()
    stmt = (
        select(Question.id, Question.address, QuestionPlacement, TaxonomyNode)
        .join(QuestionPlacement, QuestionPlacement.question_id == Question.id)
        .join(TaxonomyNode, TaxonomyNode.id == QuestionPlacement.chapter_id)
        .where(Question.assessment_id == assessment_id)
        .order_by(Question.id, QuestionPlacement.created_at.desc())
    )
    for qid, address, placement, chapter in db.execute(stmt):
        if qid in seen:
            continue
        seen.add(qid)                       # a question's newest placement is the one that counts
        if placement.source != "human" or not placement.curriculum_section:
            continue
        section = major_of(chapter.code, placement.curriculum_section, GOLD_DEPTH)
        out.append({"address": address, "chapter": chapter.code, "label": chapter.label,
                    "section": section or placement.curriculum_section})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--assessment", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    from sqlalchemy import text

    from app.db import SessionLocal
    from app.models import Assessment

    db = SessionLocal()
    try:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(text("SET TRANSACTION READ ONLY"))
        assessment = db.get(Assessment, args.assessment)
        rows = confirmed_rows(db, args.assessment)
        title = getattr(assessment, "title", "") if assessment else ""
    finally:
        db.rollback()
        db.close()
    if not rows:
        print("no confirmed placements on this paper: nothing to export")
        return 1
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(build_gold(rows, paper=title), indent=1))
    print(f"wrote {len(rows)} confirmed questions to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
