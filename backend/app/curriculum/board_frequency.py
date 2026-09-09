"""Rebuild the per-family board-frequency table from the board papers that are mapped.

The evidence is not typed in. It is read off real CBSE board papers that went through the
same scan, confirm and map route as a school test, because that route already extracts
every question with its marks and tags it with a concept family. So "did Volume of
Composite Solids appear in 2024, for how many marks" is a query over Question rows, and
this module is that query plus the pure multiplier in app.analysis.board_frequency.

What counts, and what does not:

* only ``paper_kind == 'board'`` papers. A CBSE sample paper is the board's guess, and a
  school's own test is a school's guess; neither is a record of what happened.
* only papers with at least one placed question -- an unmapped board paper is a PDF, not
  evidence, and it would silently read as "nothing appeared that year".
* board papers from every school. A board paper is public data about the exam, not about
  the school that uploaded it, and the table is keyed on curriculum version, not school.

Eligibility comes from the taxonomy's own validity dates: a family with ``valid_from``
after a given year was not in the syllabus that year, so that year is not counted against
it. A family with no dates is taken as eligible for the whole window, which is right for
the large majority and exactly wrong for a recently added chapter -- so those need their
dates set, and the row says how many years it counted so the omission is visible.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.board_frequency import (
    DEFAULT_CONFIG,
    FrequencyConfig,
    PaperQuestion,
    YearEvidence,
    marks_by_family,
    marks_for_year,
    multiplier,
)
from app.models import Assessment, FamilyBoardFrequency, Question, TaxonomyNode

#: the design note works on the last four real papers; this deployment holds five
DEFAULT_WINDOW = 5


def eligible_in(node: TaxonomyNode, year: int) -> bool:
    """Was this family in the syllabus for the exam of ``year``?"""
    if node.valid_from is not None and node.valid_from.year > year:
        return False
    if node.valid_to is not None and node.valid_to.year < year:
        return False
    return True


def board_papers(db: Session, subject_code: str, curriculum_version: str) -> list[Assessment]:
    """Every mapped board paper for the subject, any school."""
    papers = list(db.scalars(
        select(Assessment).where(
            Assessment.subject_code == subject_code,
            Assessment.curriculum_version == curriculum_version,
            Assessment.paper_kind == "board",
            Assessment.exam_year.is_not(None),
        )
    ))
    mapped = []
    for a in papers:
        has_question = db.scalar(
            select(Question.id).where(Question.assessment_id == a.id).limit(1)
        )
        if has_question:
            mapped.append(a)
    return mapped


def recompute(
    db: Session,
    subject_code: str,
    curriculum_version: str = "CBSE-2026-27",
    *,
    window: int = DEFAULT_WINDOW,
    config: FrequencyConfig = DEFAULT_CONFIG,
) -> dict:
    """Rebuild every family's row for the subject. Idempotent; replaces what was there.

    Returns a summary a route can hand back: how many papers and years were read, and
    how many families were written.
    """
    papers = board_papers(db, subject_code, curriculum_version)
    years_all = sorted({a.exam_year for a in papers})
    years = years_all[-window:] if window else years_all
    in_window = [a for a in papers if a.exam_year in years]

    #: year -> family id -> marks per paper (one entry per set of that year)
    per_year: dict[int, dict[str, list[float]]] = {y: {} for y in years}
    for a in in_window:
        rows = db.scalars(select(Question).where(Question.assessment_id == a.id)).all()
        by_family = marks_by_family([
            PaperQuestion(q.concept_family_id, float(q.max_marks), q.choice_group_id)
            for q in rows
        ])
        for family_id, marks in by_family.items():
            per_year[a.exam_year].setdefault(family_id, []).append(marks)

    # Every family of the subject gets a row, including the ones that never appeared:
    # "never appeared, multiplier 1.0" is a finding, and a missing row reads as "not
    # computed", which is a different thing.
    families = [
        n for n in db.scalars(select(TaxonomyNode).where(TaxonomyNode.kind == "concept_family"))
        if n.code.startswith(subject_code + ".")
    ]

    existing = {
        row.concept_family_id: row
        for row in db.scalars(select(FamilyBoardFrequency).where(
            FamilyBoardFrequency.curriculum_version == curriculum_version,
            FamilyBoardFrequency.subject_code == subject_code,
        ))
    }
    now = datetime.now(UTC).isoformat()
    written = 0
    for fam in families:
        evidence = []
        for y in years:
            sets = per_year.get(y, {}).get(fam.id)
            evidence.append(YearEvidence(
                year=y,
                eligible=eligible_in(fam, y),
                marks=marks_for_year(sets) if sets else None,
            ))
        m = multiplier(evidence, config)
        row = existing.get(fam.id) or FamilyBoardFrequency(
            curriculum_version=curriculum_version, subject_code=subject_code,
            concept_family_id=fam.id,
        )
        row.window_years = years
        row.years_eligible = m.years_eligible
        row.years_appeared = m.years_appeared
        row.marks_by_year = {str(y): v for y, v in m.marks_by_year.items()}
        row.marks_range = m.marks_range
        row.base_multiplier = m.base
        row.multiplier = m.value
        row.adjustments = m.adjustments
        row.papers_used = len(in_window)
        row.config_version = config.version
        row.computed_at = now
        db.add(row)
        written += 1

    # a family that no longer exists under this subject keeps no row
    for family_id, row in existing.items():
        if family_id not in {f.id for f in families}:
            db.delete(row)

    db.commit()
    return {
        "subject_code": subject_code,
        "curriculum_version": curriculum_version,
        "papers_used": len(in_window),
        "years": years,
        "years_available": years_all,
        "families_written": written,
        "config_version": config.version,
        "computed_at": now,
    }


def multipliers(db: Session, subject_code: str, curriculum_version: str) -> dict[str, float]:
    """family node id -> multiplier, for whoever computes urgency. 1.0 where no row exists,
    which is the floor and therefore the only safe default."""
    return {
        row.concept_family_id: float(row.multiplier)
        for row in db.scalars(select(FamilyBoardFrequency).where(
            FamilyBoardFrequency.curriculum_version == curriculum_version,
            FamilyBoardFrequency.subject_code == subject_code,
        ))
    }
