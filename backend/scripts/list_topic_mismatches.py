"""List questions whose Topic column disagrees with the section stored on the question.

The Topic column shows a question's primary question_skill node (heaviest, then by id);
reports and analysis read ``question.curriculum_section``. The two are written together
and must name the same section. Before this was enforced they could drift apart: a place
run that changed the section of a question whose topic a person had settled, a
skill-anchored question that kept the map step's topic, a case-study sub-part that kept
its sibling's topic after its own section was decided.

READ-ONLY. It changes nothing and has no --apply: a mismatch is fixed by re-running
place on the paper or by settling the question in review. Run it against a staging copy
of the database, never production.

    python -m scripts.list_topic_mismatches
    python -m scripts.list_topic_mismatches --assessment <id>
    python -m scripts.list_topic_mismatches --subject X.SST
"""

from __future__ import annotations

import argparse
from collections import Counter

from sqlalchemy import select

from app.db import SessionLocal
from app.mapping.topic_node import topic_mismatches
from app.models import Assessment, Question


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--assessment", help="only this assessment id")
    parser.add_argument("--subject", help="only assessments of this subject code")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        query = select(Assessment).order_by(Assessment.created_at, Assessment.id)
        if args.assessment:
            query = query.where(Assessment.id == args.assessment)
        if args.subject:
            query = query.where(Assessment.subject_code == args.subject)
        kinds: Counter = Counter()
        papers = 0
        print("READ-ONLY -- nothing will be written")
        for assessment in db.scalars(query):
            ids = list(db.scalars(select(Question.id).where(Question.assessment_id == assessment.id)))
            bad = topic_mismatches(db, ids)
            if not bad:
                continue
            papers += 1
            print(f"\nassessment {assessment.id}  {assessment.subject_code}  "
                  f"({len(bad)} of {len(ids)} questions)")
            for b in sorted(bad, key=lambda b: b["address"]):
                kind = "no section" if b["curriculum_section"] is None else "section differs"
                kinds[kind] += 1
                print(f"  {b['address']:<14} section {b['curriculum_section'] or '-':<6} "
                      f"topic {b['topic_section']:<6} {b['topic_node']}  "
                      f"[{b['topic_source']}, {kind}]")
        print(f"\nTOTAL {sum(kinds.values())} question(s) on {papers} paper(s)"
              + "".join(f", {k} {v}" for k, v in sorted(kinds.items())))
    finally:
        db.rollback()
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
