"""Put the subtopic nodes of the Social Science books back on the book map's numbering.

Two writers made subtopic nodes under the same chapters with different numbering: the PDF
ingest numbered sections in READING ORDER ("X.POL.PARTIES.S4" = "Functions"), and the
mapping steps number them by the book map's PRINTED numbers ("X.POL.PARTIES.S1_2" =
"1.2 Functions"). Where the two codes collided, a node was relabelled and came to mean a
different section. The book map is the only source of subtopics for these subjects, so
every subtopic node of every chapter is sorted into one of:

  KEEP     a book-map major topic (depth <= the cap), labelled as the book map labels it
  RELABEL  a book-map major topic whose label has drifted; set back to the book map's
  ORPHAN   no book-map major topic: a reading-order duplicate ("Functions" at S4, which is
           1.2 in the book map), an unnumbered heading ("Overview", "Popular"), a box
  DEEP     a book-map unit deeper than the cap (4.1.2 Petroleum)

For every ORPHAN and DEEP node it lists the question_skill rows that point at it, and the
question rows that carry its section, with the KEEP node each would be repointed to (a
DEEP node's is its major topic; an ORPHAN's is the book-map unit its label names, else the
question's own section). Nothing is guessed: a reference with no target is listed as
UNRESOLVED and left exactly where it is.

With --apply (and --i-have-a-backup):
  * RELABEL nodes are relabelled;
  * every resolved reference is repointed (a duplicate of a row the question already has
    on the target is deleted instead), and a question whose section was the node's is
    moved to the target's;
  * an ORPHAN node is deleted once nothing references it -- unless its code is itself a
    major topic's code, in which case it is relabelled to that topic and kept;
  * DEEP nodes stay where they are; nothing writes to them any more (topic_depth_cap).
A JSON undo file lists every changed row's old values.

Dry run by default. Run it against a staging copy of the database first, never
production. The cap is read from topic_max_depth_by_subject (default 2) whether or not
topic_depth_cap is switched on.

    python -m scripts.clean_book_map_subtopics
    python -m scripts.clean_book_map_subtopics --apply --i-have-a-backup
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select

from app.config import get_settings
from app.curriculum import CURRICULA
from app.curriculum.book_map import (
    CHAPTER_LEVEL,
    INTRO_SECTION,
    chapter_units,
    depth,
    major_headings,
    major_of,
    section_key,
)
from app.db import SessionLocal
from app.mapping.topic_node import section_number
from app.models import (
    BookChunk,
    CanonicalProcedure,
    Prerequisite,
    Question,
    QuestionSkill,
    TaxonomyAlias,
    TaxonomyNode,
)
from scripts._row_safety import UndoLog, add_safety_args, require_backup

SUBJECTS = ("X.HIST", "X.GEO", "X.POL", "X.ECO")


def _words(label: str | None) -> str:
    """'1.2 Functions' -> 'functions'; '(Overview)' -> 'overview'."""
    text = re.sub(r"^[\s.]*(?:\d+(?:\.\d+)*[a-z]?\b)?[\d.\s]*", "", (label or "").lower())
    return " ".join(re.findall(r"[a-z]+", text))


def _same(a: str | None, b: str | None) -> bool:
    """The same heading, or one cut short of the other ('Post-war Settlement and the' for
    '... and the Bretton Woods Institutions'). A short label merely contained in a long
    one -- 'Water Resources' inside 'Multi-purpose River Projects and Integrated Water
    Resources Management' -- is not the same heading."""
    x, y = _words(a), _words(b)
    if not x or not y:
        return False
    if x == y:
        return True
    short, long_ = sorted((x, y), key=len)
    return long_.startswith(short) and len(short.split()) >= 0.6 * len(long_.split())


@dataclass
class Ref:
    kind: str                 # "question_skill" | "question"
    row_id: str
    question_id: str
    address: str
    question_section: str | None
    weight: float | None = None
    target: str | None = None


@dataclass
class Entry:
    node: TaxonomyNode
    number: str | None
    status: str               # KEEP | RELABEL | ORPHAN | DEEP
    reason: str = ""
    new_label: str | None = None
    target: str | None = None
    refs: list[Ref] = field(default_factory=list)


def _title_index(chapter_code: str, majors: dict[str, str], cap: int) -> list[tuple[str, str]]:
    """(title, major topic) for every unit of the chapter, deepest units last, so a label
    can be traced to the unit it names."""
    out: list[tuple[str, str]] = []
    for u in chapter_units(chapter_code) or ():
        if u.number is None:
            if u.kind in CHAPTER_LEVEL and INTRO_SECTION in majors:
                out.append((u.title, INTRO_SECTION))
            continue
        target = major_of(chapter_code, u.number, cap)
        if target:
            out.append((u.title, target))
    return out


def plan_chapter(db, chapter: TaxonomyNode, cap: int) -> list[Entry]:
    majors = major_headings(chapter.code, cap) or {}
    titles = _title_index(chapter.code, majors, cap)
    units = {u.number: u for u in chapter_units(chapter.code) or () if u.number}

    def named_target(label: str | None) -> tuple[str, str] | None:
        """(major topic, book-map title) the label names, exact words first. A label that
        is the chapter's own title names the chapter as a whole: its introduction."""
        if INTRO_SECTION in majors and _words(label) == _words(chapter.label):
            return INTRO_SECTION, chapter.label
        for title, target in titles:
            if _words(title) == _words(label):
                return target, title
        for title, target in titles:
            if _same(title, label):
                return target, title
        return None

    entries: list[Entry] = []
    nodes = db.scalars(select(TaxonomyNode).where(
        TaxonomyNode.kind == "subtopic", TaxonomyNode.parent_id == chapter.id,
    )).all()
    nodes = sorted(nodes, key=lambda n: (
        section_key(section_number(n.code)) or ((10**6, ""),),
        n.code,
    ))
    for node in nodes:
        number = section_number(node.code)
        if number is not None and number in majors:
            expected = majors[number]
            named = named_target(node.label)
            exactly = named is not None and _words(named[1]) == _words(node.label)
            if node.label == expected:
                entries.append(Entry(node, number, "KEEP"))
            elif exactly and named[0] != number:
                entries.append(Entry(
                    node, number, "ORPHAN", target=named[0],
                    reason=f"reading-order duplicate: {node.label!r} is "
                           f"{named[1]!r} in the book map, under {named[0]}",
                ))
            elif _same(node.label, expected):
                entries.append(Entry(node, number, "RELABEL", new_label=expected,
                                     reason="label drifted from the book map's"))
            elif named is not None and named[0] != number:
                entries.append(Entry(
                    node, number, "ORPHAN", target=named[0],
                    reason=f"reading-order duplicate: {node.label!r} is "
                           f"{named[1]!r} in the book map, under {named[0]}",
                ))
            else:
                entries.append(Entry(
                    node, number, "ORPHAN",
                    reason=f"label {node.label!r} names no book-map unit; the code "
                           f"belongs to {expected!r}",
                ))
        elif number is not None and number in units:
            unit = units[number]
            target = major_of(chapter.code, number, cap)
            if unit.kind == "box":
                entries.append(Entry(node, number, "ORPHAN", target=target,
                                     reason=f"a box ({unit.title!r}), never a topic"))
            else:
                entries.append(Entry(node, number, "DEEP", target=target,
                                     reason=f"depth {depth(number)} > {cap}"))
        else:
            named = named_target(node.label)
            entries.append(Entry(
                node, number, "ORPHAN", target=named[0] if named else None,
                reason=(
                    f"no book-map unit numbered {number}"
                    + (f"; label names {named[1]!r}" if named else "")
                ) if number else "the code carries no section number",
            ))

    # references
    for entry in entries:
        if entry.status not in ("ORPHAN", "DEEP"):
            continue
        for link in db.scalars(select(QuestionSkill).where(QuestionSkill.node_id == entry.node.id)):
            q = db.get(Question, link.question_id)
            entry.refs.append(Ref(
                "question_skill", link.id, link.question_id, q.address if q else "?",
                q.curriculum_section if q else None, link.weight,
            ))
        if entry.number:
            for q in db.scalars(select(Question).where(
                Question.chapter_id == chapter.id,
                Question.curriculum_section == entry.number,
            )):
                if entry.status == "DEEP" or any(r.question_id == q.id for r in entry.refs):
                    entry.refs.append(Ref("question", q.id, q.id, q.address,
                                          q.curriculum_section))
        for ref in entry.refs:
            ref.target = entry.target
            if ref.target is None and ref.question_section:
                own = major_of(chapter.code, ref.question_section, cap)
                if own in majors and own != entry.number:
                    ref.target = own
    return entries


def _target_node(db, chapter: TaxonomyNode, target: str, label: str, created: list,
                 undo: UndoLog) -> TaxonomyNode:
    code = f"{chapter.code}.S{target.replace('.', '_')}"
    node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
    if node is None:
        node = TaxonomyNode(kind="subtopic", code=code, label=label, parent_id=chapter.id,
                            path=code, curriculum_version=chapter.curriculum_version)
        db.add(node)
        db.flush()
        created.append(code)
        undo.inserted("taxonomy_node", node.id, {"code": code, "label": label})
    return node


def _still_referenced(db, node_id: str) -> list[str]:
    def count(model, *conditions):
        return select(func.count()).select_from(model).where(*conditions)

    checks = [
        ("question_skill", count(QuestionSkill, QuestionSkill.node_id == node_id)),
        ("taxonomy_alias", count(TaxonomyAlias, TaxonomyAlias.node_id == node_id)),
        ("prerequisite", count(
            Prerequisite,
            (Prerequisite.node_id == node_id) | (Prerequisite.requires_id == node_id),
        )),
        ("canonical_procedure", count(CanonicalProcedure, CanonicalProcedure.subtopic_id == node_id)),
        ("book_chunk", count(BookChunk, BookChunk.node_id == node_id)),
        ("taxonomy_node", count(TaxonomyNode, TaxonomyNode.parent_id == node_id)),
    ]
    return [f"{n} {name}" for name, q in checks if (n := db.scalar(q))]


def apply_chapter(db, chapter: TaxonomyNode, entries: list[Entry], cap: int,
                  undo: UndoLog) -> Counter:
    majors = major_headings(chapter.code, cap) or {}
    done: Counter = Counter()
    created: list[str] = []
    for entry in entries:
        if entry.status == "RELABEL":
            undo.updated("taxonomy_node", entry.node.id, {"label": entry.node.label},
                         {"label": entry.new_label})
            entry.node.label = entry.new_label
            done["relabelled"] += 1
    for entry in entries:
        for ref in entry.refs:
            if ref.target is None:
                done["unresolved"] += 1
                continue
            target = _target_node(db, chapter, ref.target, majors.get(ref.target, ref.target),
                                  created, undo)
            if ref.kind == "question_skill":
                link = db.get(QuestionSkill, ref.row_id)
                twin = db.scalar(select(QuestionSkill).where(
                    QuestionSkill.question_id == ref.question_id,
                    QuestionSkill.node_id == target.id,
                ))
                if twin is not None and twin.id != link.id:
                    undo.deleted("question_skill", link.id, {
                        "question_id": link.question_id, "node_id": link.node_id,
                        "source": link.source, "weight": link.weight,
                        "confidence": link.confidence,
                    })
                    if (link.weight or 0) > (twin.weight or 0):
                        undo.updated("question_skill", twin.id, {"weight": twin.weight},
                                     {"weight": link.weight})
                        twin.weight = link.weight
                    db.delete(link)
                    done["skill_rows_merged"] += 1
                else:
                    undo.updated("question_skill", link.id, {"node_id": link.node_id},
                                 {"node_id": target.id})
                    link.node_id = target.id
                    done["skill_rows_repointed"] += 1
            else:
                q = db.get(Question, ref.row_id)
                if q.curriculum_section != ref.target:
                    undo.updated("question", q.id, {"curriculum_section": q.curriculum_section},
                                 {"curriculum_section": ref.target})
                    q.curriculum_section = ref.target
                    done["questions_moved"] += 1
        db.flush()
    for entry in entries:
        if entry.status != "ORPHAN":
            continue
        if any(r.target is None for r in entry.refs):
            done["orphans_kept_unresolved"] += 1
            continue
        if entry.number in majors:
            # the code itself belongs to a major topic: keep the node, with that label
            expected = majors[entry.number]
            undo.updated("taxonomy_node", entry.node.id, {"label": entry.node.label},
                         {"label": expected})
            entry.node.label = expected
            done["orphans_relabelled_to_their_code"] += 1
            continue
        still = _still_referenced(db, entry.node.id)
        if still:
            done["orphans_kept_referenced"] += 1
            print(f"    kept {entry.node.code}: still referenced by {', '.join(still)}")
            continue
        undo.deleted("taxonomy_node", entry.node.id, {
            "code": entry.node.code, "label": entry.node.label, "kind": entry.node.kind,
            "parent_id": entry.node.parent_id, "path": entry.node.path,
            "curriculum_version": entry.node.curriculum_version,
        })
        db.delete(entry.node)
        done["orphans_deleted"] += 1
    done["nodes_created"] += len(created)
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_safety_args(parser)
    args = parser.parse_args(argv)
    require_backup(args)

    settings = get_settings()
    db = SessionLocal()
    undo = UndoLog("clean_book_map_subtopics", args.undo_file) if args.apply else None
    try:
        print("DRY RUN -- nothing will be written" if not args.apply else "APPLYING")
        totals: Counter = Counter()
        for subject in SUBJECTS:
            cap = int((settings.topic_max_depth_by_subject or {}).get(subject)
                      or settings.topic_max_depth)
            for ch in CURRICULA[subject].chapters:
                chapter = db.scalar(select(TaxonomyNode).where(
                    TaxonomyNode.code == ch.code, TaxonomyNode.kind == "chapter"))
                if chapter is None or chapter_units(ch.code) is None:
                    continue
                entries = plan_chapter(db, chapter, cap)
                counts = Counter(e.status for e in entries)
                totals.update(counts)
                print(f"\n{chapter.code}  {chapter.label}  (cap {cap})  "
                      + ", ".join(f"{k} {counts[k]}" for k in ("KEEP", "RELABEL", "ORPHAN", "DEEP")))
                for e in entries:
                    line = f"  {e.status:<7} {e.node.code:<36} {e.node.label!r}"
                    if e.status == "RELABEL":
                        line += f" -> {e.new_label!r}"
                    if e.status in ("ORPHAN", "DEEP"):
                        line += f"  [{e.reason}] -> {e.target or 'per question'}"
                    print(line)
                    for r in e.refs:
                        print(f"            {r.kind:<14} {r.row_id[:8]} question {r.address:<12}"
                              f" section {r.question_section!s:<6}"
                              + (f" weight {r.weight}" if r.weight is not None else "")
                              + f" -> {r.target or 'UNRESOLVED'}")
                if args.apply:
                    done = apply_chapter(db, chapter, entries, cap, undo)
                    if done:
                        print("    applied: " + ", ".join(f"{k} {v}" for k, v in sorted(done.items())))
        print("\nTOTAL " + ", ".join(f"{k} {totals[k]}" for k in ("KEEP", "RELABEL", "ORPHAN", "DEEP")))
        if args.apply:
            db.commit()
            print(f"undo file: {undo.write()}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
