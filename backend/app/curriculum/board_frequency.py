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
  the school that uploaded it.
* one **stream** at a time. CBSE sets Maths as Standard and Basic on one syllabus, and a
  Basic set weighting a family differently would pull the Standard median, so the table
  is built per stream and a paper counts only toward its own.

Papers are matched to families by family **code**, not node id, so a paper registered
under its own year's version and the table keyed on the current version's node meet on
one row.

Eligibility -- "was this family in the syllabus that year" -- is answered from the best
record available, in this order, and the row says which was used for each year:

1. **appeared**: it was on that year's paper, so it was in the syllabus, whatever any
   record says.
2. **curriculum_version**: if the syllabus for that exam year has been recorded
   (SyllabusVersion: one row per revision, listing the families it did NOT have), the
   family is eligible exactly when it is not on that list. This is the one to rely on:
   one record per syllabus revision, not per-family dates.
3. **dates**: the node's own valid_from / valid_to, as an override where set.
4. **assumed**: nothing is known, so it is taken as eligible. Right for most families and
   exactly wrong for a recently added chapter -- which is why the row records it.
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
from app.models import Assessment, FamilyBoardFrequency, Question, SyllabusVersion, TaxonomyNode

#: the design note works on the last four real papers; this deployment holds five
DEFAULT_WINDOW = 5
STREAMS = ("standard", "basic")
#: the syllabus the table is keyed on -- the one reports read today
CURRENT_VERSION = "CBSE-2026-27"


def version_for_year(exam_year: int) -> str:
    """The curriculum version a board exam was set under: the 2024 exam closes the
    2023-24 academic year, so it is 'CBSE-2023-24'."""
    start = exam_year - 1
    return f"CBSE-{start}-{str(exam_year)[-2:]}"


def stream_of(assessment: Assessment) -> str:
    return ((assessment.declared or {}).get("stream") or "standard").lower()


def eligibility(
    fam: TaxonomyNode,
    year: int,
    *,
    appeared: bool,
    excluded_by_version: dict[str, set[str]],
) -> tuple[bool, str]:
    """(eligible, source) for one family in one exam year -- see the module docstring."""
    if appeared:
        return True, "appeared"
    version = version_for_year(year)
    if version in excluded_by_version:
        return fam.code not in excluded_by_version[version], "curriculum_version"
    if fam.valid_from is not None or fam.valid_to is not None:
        if fam.valid_from is not None and fam.valid_from.year > year:
            return False, "dates"
        if fam.valid_to is not None and fam.valid_to.year < year:
            return False, "dates"
        return True, "dates"
    return True, "assumed"


def board_papers(db: Session, subject_code: str, stream: str = "standard") -> list[Assessment]:
    """Every mapped board paper for the subject and stream, any school, any version."""
    papers = list(db.scalars(
        select(Assessment).where(
            Assessment.subject_code == subject_code,
            Assessment.paper_kind == "board",
            Assessment.exam_year.is_not(None),
        )
    ))
    mapped = []
    for a in papers:
        if stream_of(a) != stream:
            continue
        has_question = db.scalar(
            select(Question.id).where(Question.assessment_id == a.id).limit(1)
        )
        if has_question:
            mapped.append(a)
    return mapped


def recompute(
    db: Session,
    subject_code: str,
    curriculum_version: str = CURRENT_VERSION,
    *,
    stream: str = "standard",
    window: int = DEFAULT_WINDOW,
    config: FrequencyConfig = DEFAULT_CONFIG,
) -> dict:
    """Rebuild every family's row for the subject and stream. Idempotent.

    ``curriculum_version`` names whose family nodes the rows are keyed on -- the current
    syllabus. Evidence comes from papers of every version.
    """
    papers = board_papers(db, subject_code, stream)
    years_all = sorted({a.exam_year for a in papers})
    years = years_all[-window:] if window else years_all
    in_window = [a for a in papers if a.exam_year in years]

    all_nodes = list(db.scalars(select(TaxonomyNode)))
    by_id = {n.id: n for n in all_nodes}
    code_of = {n.id: n.code for n in all_nodes}
    #: for each recorded older syllabus, the family codes it did not have
    excluded_by_version: dict[str, set[str]] = {
        row.curriculum_version: set(row.excluded_families or [])
        for row in db.scalars(select(SyllabusVersion).where(
            SyllabusVersion.subject_code == subject_code
        ))
    }

    #: year -> family code -> marks per set of that year
    per_year: dict[int, dict[str, list[float]]] = {y: {} for y in years}
    sets_in_year: dict[int, int] = {y: 0 for y in years}
    for a in in_window:
        rows = db.scalars(select(Question).where(Question.assessment_id == a.id)).all()
        by_family = marks_by_family([
            PaperQuestion(code_of.get(q.concept_family_id, q.concept_family_id),
                          float(q.max_marks), q.choice_group_id)
            for q in rows
        ])
        sets_in_year[a.exam_year] += 1
        for code, marks in by_family.items():
            per_year[a.exam_year].setdefault(code, []).append(marks)

    # Every family of the current version gets a row, including the ones that never
    # appeared: "never appeared, multiplier 1.0" is a finding, and a missing row reads as
    # "not computed", which is a different thing.
    families = [
        n for n in all_nodes
        if n.kind == "concept_family"
        and n.curriculum_version == curriculum_version
        and n.code.startswith(subject_code + ".")
        # by its chapter, not just its code prefix: the proposal route once coded Science
        # and English families X.MATH.CF.*, and those must not get a row in the Maths table
        and n.parent_id in by_id
        and by_id[n.parent_id].code.startswith(subject_code + ".")
    ]

    existing = {
        row.concept_family_id: row
        for row in db.scalars(select(FamilyBoardFrequency).where(
            FamilyBoardFrequency.curriculum_version == curriculum_version,
            FamilyBoardFrequency.subject_code == subject_code,
            FamilyBoardFrequency.stream == stream,
        ))
    }
    now = datetime.now(UTC).isoformat()
    written, assumed_years = 0, 0
    for fam in families:
        evidence: list[YearEvidence] = []
        for y in years:
            sets = per_year.get(y, {}).get(fam.code, [])
            appeared = bool(sets)
            eligible, source = eligibility(
                fam, y, appeared=appeared, excluded_by_version=excluded_by_version,
            )
            if source == "assumed":
                assumed_years += 1
            evidence.append(YearEvidence(
                year=y, eligible=eligible,
                marks=marks_for_year(sets) if sets else None,
                eligibility_source=source,
                sets_with=len(sets), sets_without=sets_in_year[y] - len(sets),
            ))
        m = multiplier(evidence, config)
        row = existing.get(fam.id) or FamilyBoardFrequency(
            curriculum_version=curriculum_version, subject_code=subject_code,
            stream=stream, concept_family_id=fam.id,
        )
        row.window_years = years
        row.years_eligible = m.years_eligible
        row.years_appeared = m.years_appeared
        row.marks_by_year = {str(y): v for y, v in m.marks_by_year.items()}
        row.marks_range = m.marks_range
        row.base_multiplier = m.base
        row.multiplier = m.value
        row.adjustments = m.adjustments
        row.eligibility = {str(e.year): e.eligibility_source for e in evidence}
        row.sets_disagree = {
            str(e.year): {"with": e.sets_with, "without": e.sets_without}
            for e in evidence if e.sets_with and e.sets_without
        } or None
        row.papers_used = len(in_window)
        row.config_version = config.version
        row.computed_at = now
        db.add(row)
        written += 1

    # a family that no longer exists under this version keeps no row
    current = {f.id for f in families}
    for family_id, row in existing.items():
        if family_id not in current:
            db.delete(row)

    db.commit()
    return {
        "subject_code": subject_code,
        "curriculum_version": curriculum_version,
        "stream": stream,
        "papers_used": len(in_window),
        "sets_per_year": {str(y): n for y, n in sets_in_year.items()},
        "years": years,
        "years_available": years_all,
        "families_written": written,
        #: family-years whose eligibility rests on nothing: seed those years' syllabus
        #: versions (POST /books/{subject}/curriculum?version=...) and recompute
        "assumed_family_years": assumed_years,
        "recorded_versions": sorted(excluded_by_version),
        "config_version": config.version,
        "computed_at": now,
    }


def multipliers(
    db: Session, subject_code: str, curriculum_version: str, stream: str = "standard",
) -> dict[str, float]:
    """family node id -> multiplier, for whoever computes urgency. 1.0 where no row exists,
    which is the floor and therefore the only safe default."""
    return {
        row.concept_family_id: float(row.multiplier)
        for row in db.scalars(select(FamilyBoardFrequency).where(
            FamilyBoardFrequency.curriculum_version == curriculum_version,
            FamilyBoardFrequency.subject_code == subject_code,
            FamilyBoardFrequency.stream == stream,
        ))
    }


def frequency_rows(
    db: Session, subject_code: str, curriculum_version: str, stream: str = "standard",
) -> dict[str, FamilyBoardFrequency]:
    """family node id -> its stored row, for a report that wants to say why."""
    return {
        row.concept_family_id: row
        for row in db.scalars(select(FamilyBoardFrequency).where(
            FamilyBoardFrequency.curriculum_version == curriculum_version,
            FamilyBoardFrequency.subject_code == subject_code,
            FamilyBoardFrequency.stream == stream,
        ))
    }


def frequency_note(row: FamilyBoardFrequency) -> str:
    """One line a teacher reads: 'asked in 4 of the last 5 board exams'."""
    n, of = row.years_appeared, row.years_eligible
    if of == 0:
        return "no board-exam history for this topic yet"
    if n == 0:
        return f"not asked in any of the last {of} board exams"
    if n == of:
        return f"asked in every one of the last {of} board exams"
    return f"asked in {n} of the last {of} board exams"


def urgency_tier(
    years_appeared: int, years_eligible: int, config: FrequencyConfig = DEFAULT_CONFIG,
) -> str | None:
    """VERY HIGH / HIGH / MEDIUM / LOW, for a principal reading a badge rather than a
    multiplier.

    Deliberately keyed to the same share-of-eligible-years boundaries as
    ``base_multiplier`` (config.base_by_share), not a second set of cut points invented
    for display -- the badge and the number underneath it must always agree, or "VERY
    HIGH" next to a 1.25x multiplier is the kind of thing that quietly breaks trust in
    the whole page the first time someone checks the two against each other.

    None, not a string, when there is nothing to judge: zero eligible years is "no
    board-exam history for this topic yet" (frequency_note's own case), not "LOW" -- LOW
    is a real judgement about a family that keeps failing to reappear, and a topic with no
    eligible years at all has never had the chance to.
    """
    if years_eligible <= 0:
        return None
    share = years_appeared / years_eligible
    # The share cut points, not the multiplier values they produce: base_curve='square'
    # turns the same shares into 2.0/1.56/1.25 rather than table's 2.0/1.5/1.25, and the
    # tier has to track the shares either way, not a multiplier value that moves under it.
    labels = ["VERY HIGH", "HIGH", "MEDIUM"]
    for (minimum, _base), label in zip(config.base_by_share, labels, strict=False):
        if share >= minimum:
            return label
    return "LOW"
