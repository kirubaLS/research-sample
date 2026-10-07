"""One concept family per major topic, for the capped Social Science subjects.

With topic_depth_cap on, a question's topic is at most two levels deep, and every family
must claim a major topic. The book map already gives most major topics a family of their
own (Conventional Sources of Energy claims 4.1). Its deeper units have families too --
Coal, Petroleum, Natural Gas and Electricity -- and all of them collapse onto 4.1, where
they would compete for every question. This script, per capped chapter:

  REUSE   a major topic that already has its own book-map family: nothing to create
  CREATE  a major topic with no family of its own: a new family is proposed, code
          {subject}.CF.{slug(heading)}, label = the book map's heading, claiming exactly
          that section
  REPOINT a question on a SCHOOL paper whose family is a deep one (a deeper unit, or a
          box): moved to the family of the major topic it belongs to

Board papers are listed and never touched. Deep families stay in the database, unused for
new placements (app.mapping.family_sections marks them).

Dry run by default. Run it against a staging copy of the database first, never
production. --apply requires --i-have-a-backup and writes a JSON undo file.

    python -m scripts.propose_major_topic_families
    python -m scripts.propose_major_topic_families --apply --i-have-a-backup
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import get_settings
from app.curriculum import CURRICULA
from app.curriculum.book_map import (
    CHAPTER_LEVEL,
    INTRO_SECTION,
    chapter_units,
    family_topic,
    major_headings,
    major_of,
)
from app.curriculum.families import slugify
from app.db import SessionLocal
from app.models import Assessment, ConceptFamilyProposal, Question, TaxonomyNode
from scripts._row_safety import UndoLog, add_safety_args, require_backup

SUBJECTS = ("X.HIST", "X.GEO", "X.POL", "X.ECO", "X.SCI")
RUN_ID = "major_topic_families_v1"


def _title(heading: str, section: str) -> str:
    """'4.1 Conventional Sources of Energy' -> 'Conventional Sources of Energy'."""
    prefix = f"{section} "
    return heading[len(prefix):] if heading.startswith(prefix) else heading


def plan_chapter(db, chapter: TaxonomyNode, subject: str, cap: int) -> dict:
    majors = major_headings(chapter.code, cap) or {}
    families = db.scalars(select(TaxonomyNode).where(
        TaxonomyNode.kind == "concept_family", TaxonomyNode.parent_id == chapter.id,
    )).all()
    by_code = {f.code: f for f in families}
    unit_of_family = {
        u.catalog: u for u in chapter_units(chapter.code) or () if u.catalog
    }
    own: dict[str, TaxonomyNode] = {}       # major topic -> the family that IS it
    deep: dict[str, str | None] = {}        # deep family code -> its major topic
    for f in families:
        topic = family_topic(chapter.code, f.code, cap)
        if topic is not None:
            own.setdefault(topic, f)
        elif f.code in unit_of_family:
            unit = unit_of_family[f.code]
            # an unnumbered (conclusion, summing-up) family's text is chapter level: "0"
            deep[f.code] = (major_of(chapter.code, unit.number, cap) if unit.number
                            else INTRO_SECTION if unit.kind in CHAPTER_LEVEL else None)

    rows = []
    for section, heading in majors.items():
        if section in own:
            rows.append(("REUSE", section, own[section].code, own[section].label))
            continue
        title = _title(heading, section)
        if section == INTRO_SECTION:
            title = f"{chapter.label}: Introduction"
        code = f"{subject}.CF.{slugify(title)}"
        if code in by_code:
            # the slug is already a family of this chapter (a different section's): the
            # code must stay unique, so the section number joins it
            code = f"{subject}.CF.{slugify(f'{chapter.code.rsplit(chr(46), 1)[-1]} {section} {title}')}"
        rows.append(("CREATE", section, code, title))

    target_code = {section: code for _, section, code, _ in rows}
    repoints, board = [], []
    if deep:
        questions = db.scalars(select(Question).where(
            Question.concept_family_id.in_([by_code[c].id for c in deep])
        )).all()
        kinds = {
            a.id: a.paper_kind for a in db.scalars(select(Assessment).where(
                Assessment.id.in_({q.assessment_id for q in questions})
            ))
        }
        code_of_id = {f.id: f.code for f in families}
        for q in questions:
            family_code = code_of_id[q.concept_family_id]
            # The question's own section decides first: it is what the question was
            # placed under, collapsed to its major topic. Only when that topic has no
            # family does the deep family's own major topic stand in.
            own = major_of(chapter.code, q.curriculum_section, cap) if q.curriculum_section else None
            if own is not None and own in target_code:
                section, why = own, "question section"
            else:
                section, why = deep.get(family_code), "deep family's topic"
            item = (q, family_code, section, target_code.get(section), why)
            (board if kinds.get(q.assessment_id) == "board" else repoints).append(item)
    return {"rows": rows, "deep": deep, "repoints": repoints, "board": board, "by_code": by_code}


def apply_chapter(db, chapter: TaxonomyNode, subject: str, plan: dict, undo: UndoLog) -> Counter:
    done: Counter = Counter()
    by_code = dict(plan["by_code"])
    for action, section, code, label in plan["rows"]:
        if action != "CREATE":
            continue
        node = TaxonomyNode(kind="concept_family", code=code, label=label, parent_id=chapter.id,
                            path=code, curriculum_version=chapter.curriculum_version)
        db.add(node)
        db.flush()
        by_code[code] = node
        proposal = ConceptFamilyProposal(
            curriculum_version=chapter.curriculum_version, subject_code=subject,
            run_id=RUN_ID, source="major_topic", model=None, code=code, label=label,
            chapter_id=chapter.id,
            rationale="one family per major topic (topic_depth_cap)",
            evidence=[section], from_sections=[section],
            applied_at=datetime.now(UTC).isoformat(),
        )
        db.add(proposal)
        db.flush()
        undo.inserted("taxonomy_node", node.id, {"code": code, "label": label})
        undo.inserted("concept_family_proposal", proposal.id, {"code": code, "section": section})
        done["families_created"] += 1
    for q, _, _, target, _ in plan["repoints"]:
        if target is None or target not in by_code:
            done["repoints_unresolved"] += 1
            continue
        undo.updated("question", q.id, {"concept_family_id": q.concept_family_id},
                     {"concept_family_id": by_code[target].id})
        q.concept_family_id = by_code[target].id
        done["questions_repointed"] += 1
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_safety_args(parser)
    args = parser.parse_args(argv)
    require_backup(args)

    settings = get_settings()
    db = SessionLocal()
    undo = UndoLog("propose_major_topic_families", args.undo_file) if args.apply else None
    totals: Counter = Counter()
    try:
        print("DRY RUN -- nothing will be written" if not args.apply else "APPLYING")
        for subject in SUBJECTS:
            cap = int((settings.topic_max_depth_by_subject or {}).get(subject)
                      or settings.topic_max_depth)
            for ch in CURRICULA[subject].chapters:
                chapter = db.scalar(select(TaxonomyNode).where(
                    TaxonomyNode.code == ch.code, TaxonomyNode.kind == "chapter"))
                if chapter is None or chapter_units(ch.code) is None:
                    continue
                plan = plan_chapter(db, chapter, subject, cap)
                counts = Counter(action for action, *_ in plan["rows"])
                totals.update(counts)
                totals["deep families"] += len(plan["deep"])
                totals["REPOINT"] += len(plan["repoints"])
                totals["board questions left alone"] += len(plan["board"])
                print(f"\n{chapter.code}  {chapter.label}  (cap {cap})  REUSE {counts['REUSE']}, "
                      f"CREATE {counts['CREATE']}, deep families {len(plan['deep'])}, "
                      f"REPOINT {len(plan['repoints'])}")
                for action, section, code, label in plan["rows"]:
                    print(f"  {action:<7} {section:<5} {code:<58} {label!r}")
                for code, section in sorted(plan["deep"].items()):
                    where = ("chapter level" if section == INTRO_SECTION
                             else f"major topic {section or '?'}")
                    print(f"  deep    {code:<64} -> {where} (kept, unused)")
                for q, family_code, section, target, why in plan["repoints"]:
                    print(f"  REPOINT question {q.address:<12} {family_code} -> "
                          f"{target or 'UNRESOLVED'} (section {section or '?'}, by {why})")
                for q, family_code, _, _, _ in plan["board"]:
                    print(f"  skip    question {q.address:<12} {family_code} (board paper, untouched)")
                if args.apply:
                    done = apply_chapter(db, chapter, subject, plan, undo)
                    if done:
                        print("    applied: " + ", ".join(f"{k} {v}" for k, v in sorted(done.items())))
        print("\nTOTAL " + ", ".join(f"{k} {v}" for k, v in totals.items()))
        if args.apply:
            db.commit()
            print(f"undo file: {undo.write()}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
