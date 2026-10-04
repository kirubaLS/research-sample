"""Is this upload a paper the school already has?

Two checks, both cheap and neither a model call:

* **File hash.** Each ORIGINAL uploaded file is hashed before the pages are merged into one
  PDF (the merged PDF's bytes change from one upload to the next, so its hash matches
  nothing). The same file sent again matches exactly.
* **Question stems.** After extraction, the paper's normalised question stems (the same
  ``stem_hash`` every question row stores) are compared with every other paper of the
  same school and subject. A copy re-photographed, re-titled or merged differently still
  carries the same questions: when at least ``STEM_OVERLAP`` of this paper's stems are on
  one existing paper, that paper is a likely duplicate.

On real data the second check is the one that matters: five uploads of one unit test all
had different file hashes and two different titles.

A match is only ever shown to the teacher, with its overlap, before any model call is
spent on mapping and classifying. Nothing is reused or deleted automatically.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

#: the share of this paper's question stems that must be on one existing paper
STEM_OVERLAP = 0.70


def file_hashes(originals) -> list[str]:
    """sha256 of each original uploaded file, in upload order. ``originals`` are
    (bytes, content type, filename) as the scan route reads them."""
    return [hashlib.sha256(content).hexdigest() for content, _, _ in originals]


def stem_set(stems) -> set[str]:
    """The distinct stem hashes of these question stems; blank stems carry nothing."""
    from app.ingest.book import stem_hash

    return {stem_hash(s) for s in stems if s and s.strip()}


def paper_stems(db: Session, assessment_ids) -> dict[str, set[str]]:
    """assessment id -> the stem hashes of its questions: its question rows' stored
    ``stem_hash``, and the staged scanned questions a paper that was never mapped still
    only has."""
    from app.ingest.book import stem_hash
    from app.models import Question, ScannedQuestion

    ids = list(assessment_ids)
    out: dict[str, set[str]] = {i: set() for i in ids}
    if not ids:
        return out
    for aid, h in db.execute(
        select(Question.assessment_id, Question.stem_hash).where(Question.assessment_id.in_(ids))
    ):
        if h:
            out[aid].add(h)
    for aid, text in db.execute(
        select(ScannedQuestion.assessment_id, ScannedQuestion.stem_text)
        .where(ScannedQuestion.assessment_id.in_(ids))
    ):
        if text and text.strip():
            out[aid].add(stem_hash(text))
    return out


def overlap(new: set[str], existing: set[str]) -> float:
    """The share of ``new``'s stems found in ``existing``."""
    return len(new & existing) / len(new) if new else 0.0


def find_duplicates(
    db: Session, assessment, *, stems, hashes: list[str] | None = None,
) -> list[dict]:
    """The other papers of this school and subject that this one matches -- by an
    original file's hash, or by ``STEM_OVERLAP`` of its question stems -- most similar
    first. A paper whose class section is known and differs from this one's is a
    different class's paper, never a duplicate."""
    from app.models import Assessment

    others = [
        a for a in db.scalars(select(Assessment).where(
            Assessment.school_id == assessment.school_id,
            Assessment.subject_code == assessment.subject_code,
            Assessment.id != assessment.id,
        ))
        if not (assessment.class_section_id and a.class_section_id
                and a.class_section_id != assessment.class_section_id)
    ]
    if not others:
        return []
    mine = stem_set(stems)
    theirs = paper_stems(db, [a.id for a in others])
    hashes = set(hashes or [])
    out = []
    for a in others:
        by_hash = bool(hashes & set(a.source_file_hashes or []))
        share = overlap(mine, theirs.get(a.id, set()))
        if not by_hash and share < STEM_OVERLAP:
            continue
        out.append({
            "assessment_id": a.id, "title": a.title, "exam_id": a.exam_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "overlap": round(share, 3),
            "matched_by": [m for m, hit in (("file_hash", by_hash),
                                           ("stems", share >= STEM_OVERLAP)) if hit],
            "questions": len(theirs.get(a.id, set())),
        })
    out.sort(key=lambda d: (-("file_hash" in d["matched_by"]), -d["overlap"], d["created_at"] or ""))
    return out


def pending(assessment) -> bool:
    """A duplicate check found candidates and the teacher has not chosen yet."""
    check = assessment.duplicate_check or {}
    return bool(check.get("candidates")) and not check.get("decision")
