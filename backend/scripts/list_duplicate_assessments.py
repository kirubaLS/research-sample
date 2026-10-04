"""List groups of assessments that are the same paper uploaded more than once.

READ-ONLY. It deletes nothing, merges nothing and has no --apply: which copy to keep is a
person's decision (the one linked to an exam, or carrying marks, is usually the one).

Two papers of the same school and subject are linked when:

* **hash** -- they share an original uploaded file's sha256 (source_file_hashes), or the
  same merged-PDF sha256 (source_sha256); or
* **stems** -- at least 70% of one paper's normalised question stems are on the other
  (app.extraction.duplicates.STEM_OVERLAP: the same test the upload check applies).

Linked papers form groups (a copy of a copy is in the same group). On real data the stems
test is the one that finds them: five uploads of one unit test had five different hashes
and two different titles.

Each group lists every paper with its id, title, created_at, exam_id (the paper linked to
an exam is marked), question counts, its job counts, and its overlap with the group's
first paper. Run it against a staging copy of the database, never production.

    python -m scripts.list_duplicate_assessments
    python -m scripts.list_duplicate_assessments --school <id> --subject X.SST
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict

from sqlalchemy import select

from app.extraction.duplicates import STEM_OVERLAP, overlap, paper_stems


def _linked(a, b, stems) -> list[str]:
    why = []
    if (a.source_sha256 and a.source_sha256 == b.source_sha256) or (
        set(a.source_file_hashes or []) & set(b.source_file_hashes or [])
    ):
        why.append("hash")
    sa, sb = stems.get(a.id, set()), stems.get(b.id, set())
    if max(overlap(sa, sb), overlap(sb, sa)) >= STEM_OVERLAP:
        why.append("stems")
    return why


def _root(parent: dict[str, str], x: str) -> str:
    """The representative of ``x``'s group (union-find, with path halving)."""
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def duplicate_groups(db, *, school_id: str | None = None, subject: str | None = None) -> list[dict]:
    """Every group of two or more linked papers, largest first. Each is {"school_id",
    "subject_code", "papers": [Assessment, ...] oldest first, "links": {(a, b): [why]},
    "stems": {id: set}}."""
    from app.models import Assessment

    query = select(Assessment).order_by(Assessment.created_at, Assessment.id)
    if school_id:
        query = query.where(Assessment.school_id == school_id)
    if subject:
        query = query.where(Assessment.subject_code == subject)
    pools: dict[tuple[str, str], list] = defaultdict(list)
    for a in db.scalars(query):
        pools[(a.school_id, a.subject_code)].append(a)
    groups = []
    for (school, subj), papers in pools.items():
        if len(papers) < 2:
            continue
        stems = paper_stems(db, [p.id for p in papers])
        parent = {p.id: p.id for p in papers}
        links: dict[tuple[str, str], list[str]] = {}
        for i, a in enumerate(papers):
            for b in papers[i + 1:]:
                if a.class_section_id and b.class_section_id and a.class_section_id != b.class_section_id:
                    continue
                why = _linked(a, b, stems)
                if why:
                    links[(a.id, b.id)] = why
                    parent[_root(parent, b.id)] = _root(parent, a.id)
        members: dict[str, list] = defaultdict(list)
        for p in papers:
            members[_root(parent, p.id)].append(p)
        for group in members.values():
            if len(group) > 1:
                groups.append({"school_id": school, "subject_code": subj, "papers": group,
                               "links": links, "stems": stems})
    groups.sort(key=lambda g: (-len(g["papers"]), g["papers"][0].created_at or 0))
    return groups


def main(argv: list[str] | None = None) -> int:
    from app.db import SessionLocal
    from app.models import PaperScanJob, PlacementJob, Question

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--school", help="only this school id")
    parser.add_argument("--subject", help="only this subject code")
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        print("READ-ONLY -- nothing will be written or deleted")
        groups = duplicate_groups(db, school_id=args.school, subject=args.subject)
        for n, g in enumerate(groups, 1):
            ids = [p.id for p in g["papers"]]
            jobs: dict[str, Counter] = defaultdict(Counter)
            for aid, kind, status in db.execute(select(
                PlacementJob.assessment_id, PlacementJob.kind, PlacementJob.status,
            ).where(PlacementJob.assessment_id.in_(ids))):
                jobs[aid][f"{kind}:{status}"] += 1
            for (aid,) in db.execute(select(PaperScanJob.assessment_id).where(
                PaperScanJob.assessment_id.in_(ids))):
                jobs[aid]["scan"] += 1
            mapped = Counter(db.scalars(select(Question.assessment_id).where(
                Question.assessment_id.in_(ids))))
            first = g["stems"].get(ids[0], set())
            print(f"\nGROUP {n}: {len(ids)} papers  school {g['school_id']}  {g['subject_code']}")
            for p in g["papers"]:
                own = g["stems"].get(p.id, set())
                linked_by = sorted({w for (a, b), why in g["links"].items()
                                    if p.id in (a, b) for w in why})
                job_text = ", ".join(f"{k} {v}" for k, v in sorted(jobs[p.id].items())) or "none"
                print(
                    f"  {p.id}  {(p.title or '')[:28]:<28} "
                    f"{p.created_at.isoformat() if p.created_at else '-':<26} "
                    f"exam {p.exam_id or '-'}{'  <- linked to the exam' if p.exam_id else ''}\n"
                    f"      stems {len(own)}, questions {mapped.get(p.id, 0)}, "
                    f"overlap with first {overlap(own, first):.0%}, "
                    f"linked by {'+'.join(linked_by) or '-'}, "
                    f"sha256 {(p.source_sha256 or '-')[:12]}, jobs: {job_text}"
                )
        print(f"\nTOTAL {len(groups)} group(s), "
              f"{sum(len(g['papers']) for g in groups)} paper(s)")
    finally:
        db.rollback()
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
