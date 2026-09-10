"""Real board papers in, board frequency and urgency out.

A board paper is registered here and then walks the same route as any school test:
``POST /assessments/{id}/scan`` to read the PDF, ``/scan/confirm`` for a person to sign
off the extraction, ``/map`` to place every question in a chapter and concept family.
Nothing in that route is duplicated: the only thing this module adds at the front is
"this is the 2024 board exam", and the only thing it adds at the back is the table that
falls out once enough of them are mapped.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.board_frequency import DEFAULT_CONFIG, FrequencyConfig, urgency
from app.api.deps import require_reader, require_scanner
from app.curriculum.board_frequency import (
    DEFAULT_WINDOW,
    board_papers,
    frequency_note,
    recompute,
    stream_of,
    urgency_tier,
    version_for_year,
)
from app.db import get_session
from app.models import (
    Assessment,
    BoardUnitWeight,
    ChapterBoardUnit,
    FamilyBoardFrequency,
    Question,
    School,
    TaxonomyNode,
)

router = APIRouter(tags=["board-frequency"])


#: CBSE prints the Basic Maths paper as '30(B)' or '430'; Standard as '30' or '041'
BASIC_CODE = re.compile(r"\(B\)|^430\b", re.I)


class BoardPaperIn(BaseModel):
    subject_code: str = Field(max_length=32)
    #: the year the board set it -- 2024 for the March 2024 exam
    exam_year: int = Field(ge=2000, le=2100)
    #: the set, as printed: '30/1/1', '30(B)'. Several sets of one year are normal.
    paper_code: str | None = Field(default=None, max_length=32)
    total_marks: float | None = Field(default=None, gt=0)
    #: the syllabus this paper was set under. Defaults to the exam year's own version
    #: ('CBSE-2023-24' for the 2024 exam) -- NOT the current one -- because "was this
    #: family in the syllabus that year" is answered by which version carries it.
    curriculum_version: str | None = Field(default=None, max_length=32)
    #: 'board' is a real exam; 'sample' is CBSE's own sample paper, kept out of the count
    kind: str = Field(default="board", pattern="^(board|sample)$")
    #: 'standard' or 'basic'. Maths only; every other subject is 'standard'.
    stream: str = Field(default="standard", pattern="^(standard|basic)$")
    title: str | None = Field(default=None, max_length=200)


@router.post("/board-papers", status_code=201)
def register_board_paper(
    body: BoardPaperIn,
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """Register one real board paper, then scan it the way any paper is scanned."""
    if body.paper_code and BASIC_CODE.search(body.paper_code) and body.stream != "basic":
        raise HTTPException(
            422,
            f"paper code {body.paper_code!r} is a Basic Maths paper. Register it with "
            f"stream='basic': Basic and Standard are two exams on one syllabus and their "
            f"sets are never pooled.",
        )
    version = body.curriculum_version or version_for_year(body.exam_year)
    duplicate = db.scalar(
        select(Assessment).where(
            Assessment.subject_code == body.subject_code,
            Assessment.paper_kind == body.kind,
            Assessment.exam_year == body.exam_year,
            Assessment.paper_code == body.paper_code,
            Assessment.paper_code.is_not(None),
        )
    )
    if duplicate is not None:
        raise HTTPException(
            409,
            f"{body.subject_code} {body.exam_year} set {body.paper_code!r} is already "
            f"registered as assessment {duplicate.id}. One set counts once; scan that one.",
        )
    label = "Board" if body.kind == "board" else "Sample"
    title = body.title or (
        f"CBSE {label} Paper {body.exam_year} {body.subject_code}"
        + (" Basic" if body.stream == "basic" else "")
        + (f" set {body.paper_code}" if body.paper_code else "")
    )
    # a real board paper declares CBSE's blueprint, which the tier tie-break may use
    declared: dict = {"blueprint": body.kind == "board", "stream": body.stream}
    if body.total_marks:
        declared["total_marks"] = body.total_marks
    a = Assessment(
        school_id=school.id, subject_code=body.subject_code, title=title,
        paper_code=body.paper_code, total_marks=body.total_marks,
        curriculum_version=version,
        paper_kind=body.kind, exam_year=body.exam_year, declared=declared,
    )
    db.add(a)
    db.commit()
    return {
        "assessment_id": a.id,
        "title": a.title,
        "paper_kind": a.paper_kind,
        "exam_year": a.exam_year,
        "stream": body.stream,
        "curriculum_version": version,
        "next": (
            f"POST /assessments/{a.id}/scan with the PDF, then /scan/confirm, then /map. "
            f"The frequency table for {a.subject_code} rebuilds itself after /map."
        ),
    }


@router.get("/board-papers")
def list_board_papers(
    subject_code: str | None = Query(default=None),
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """Every board and sample paper registered, any school, and how far each has got.

    Any school, because the frequency table reads them all: a paper mapped by one school
    counts for every school on the same curriculum, and the list has to show what it
    counted.
    """
    stmt = select(Assessment).where(Assessment.paper_kind.in_(("board", "sample")))
    if subject_code:
        stmt = stmt.where(Assessment.subject_code == subject_code)
    papers = list(db.scalars(stmt.order_by(Assessment.exam_year.desc(), Assessment.paper_code)))
    counts = dict(db.execute(
        select(Question.assessment_id, func.count(Question.id))
        .where(Question.assessment_id.in_([a.id for a in papers]))
        .group_by(Question.assessment_id)
    ).all()) if papers else {}
    return {
        "papers": [
            {
                "assessment_id": a.id,
                "subject_code": a.subject_code,
                "exam_year": a.exam_year,
                "paper_code": a.paper_code,
                "paper_kind": a.paper_kind,
                "stream": stream_of(a),
                "curriculum_version": a.curriculum_version,
                "title": a.title,
                "confirmed": a.scan_confirmed_at is not None,
                "questions_mapped": counts.get(a.id, 0),
                "counts_toward_frequency": a.paper_kind == "board" and counts.get(a.id, 0) > 0,
            }
            for a in papers
        ],
    }


@router.post("/board-frequency/recompute")
def recompute_frequency(
    subject_code: str = Query(..., max_length=32),
    curriculum_version: str = Query(default="CBSE-2026-27"),
    stream: str = Query(default="standard", pattern="^(standard|basic)$"),
    window: int = Query(default=DEFAULT_WINDOW, ge=1, le=10),
    base: str = Query(default="table", pattern="^(table|square)$"),
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """Rebuild the table by hand. /map does this on its own; this is for after a review
    moved a question, after an older syllabus version was seeded, or to compare the
    note's base table against the continuous curve (``base=square``)."""
    if not board_papers(db, subject_code, stream):
        raise HTTPException(
            409,
            f"no mapped {stream} board paper exists for {subject_code}. Register one at "
            f"POST /board-papers, scan it, confirm it and map it first.",
        )
    config = FrequencyConfig(base_curve=base)
    return recompute(db, subject_code, curriculum_version, stream=stream, window=window, config=config)


@router.get("/board-frequency")
def frequency_table(
    subject_code: str = Query(..., max_length=32),
    curriculum_version: str = Query(default="CBSE-2026-27"),
    stream: str = Query(default="standard", pattern="^(standard|basic)$"),
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """Every family's multiplier and urgency, with the evidence each rests on.

    Urgency is the family's board unit weight times its multiplier. A family with no
    weight (its chapter is not mapped to a unit yet) shows a null urgency rather than a
    zero, because zero would read as "no urgency" when it means "not computable".
    """
    rows = list(db.scalars(select(FamilyBoardFrequency).where(
        FamilyBoardFrequency.subject_code == subject_code,
        FamilyBoardFrequency.curriculum_version == curriculum_version,
        FamilyBoardFrequency.stream == stream,
    )))
    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
    unit_of = {
        r.chapter_id: r.board_unit_id
        for r in db.scalars(select(ChapterBoardUnit).where(
            ChapterBoardUnit.curriculum_version == curriculum_version
        ))
    }
    weight_of = {
        w.board_unit_id: float(w.weight_pct)
        for w in db.scalars(select(BoardUnitWeight).where(
            BoardUnitWeight.curriculum_version == curriculum_version
        ))
    }

    out = []
    for row in rows:
        fam = nodes.get(row.concept_family_id)
        chapter = nodes.get(fam.parent_id) if fam and fam.parent_id else None
        unit_id = unit_of.get(chapter.id) if chapter else None
        weight = weight_of.get(unit_id) if unit_id else None
        out.append({
            "concept_family": fam.code if fam else row.concept_family_id,
            "label": fam.label if fam else row.concept_family_id,
            "chapter": chapter.code if chapter else None,
            "board_unit": nodes[unit_id].code if unit_id in nodes else None,
            "board_weight_pct": weight,
            "multiplier": row.multiplier,
            "urgency": urgency(weight, row.multiplier) if weight is not None else None,
            #: VERY HIGH/HIGH/MEDIUM/LOW, keyed to the same share-of-eligible-years
            #: boundaries as the multiplier itself -- see urgency_tier's own docstring for
            #: why this is never derived separately from the number sitting beside it.
            "urgency_tier": urgency_tier(row.years_appeared, row.years_eligible),
            "note": frequency_note(row),
            "base_multiplier": row.base_multiplier,
            "years_eligible": row.years_eligible,
            "years_appeared": row.years_appeared,
            "window_years": row.window_years,
            "marks_by_year": row.marks_by_year,
            "marks_range": row.marks_range,
            "adjustments": row.adjustments,
            "eligibility": row.eligibility,
            "sets_disagree": row.sets_disagree,
            "papers_used": row.papers_used,
            "config_version": row.config_version,
            "computed_at": row.computed_at,
        })
    out.sort(key=lambda r: (-(r["urgency"] or 0.0), -r["multiplier"], r["label"]))
    assumed = sum(
        1 for r in out for src in (r["eligibility"] or {}).values() if src == "assumed"
    )
    return {
        "subject_code": subject_code,
        "curriculum_version": curriculum_version,
        "stream": stream,
        "families": out,
        #: years whose sets disagreed on whether a family appeared -- for a reviewer
        "review": [
            {"concept_family": r["concept_family"], "sets_disagree": r["sets_disagree"]}
            for r in out if r["sets_disagree"]
        ],
        #: family-years resting on an assumption rather than a syllabus record
        "assumed_family_years": assumed,
        "config": {
            "version": DEFAULT_CONFIG.version,
            "base_curve": DEFAULT_CONFIG.base_curve,
            "base_by_share": DEFAULT_CONFIG.base_by_share,
            "tight_range": DEFAULT_CONFIG.tight_range,
            "wide_range": DEFAULT_CONFIG.wide_range,
            "wide_range_cap": DEFAULT_CONFIG.wide_range_cap,
            "low_confidence_years": DEFAULT_CONFIG.low_confidence_years,
            "low_confidence_cap": DEFAULT_CONFIG.low_confidence_cap,
            "floor": DEFAULT_CONFIG.floor,
        },
        "note": (
            "Multipliers follow the Board Frequency & Urgency design note. Every threshold "
            "is a starting proposal to be revisited once real subjects have run through it."
        ) if out else (
            f"no rows yet for {subject_code}. Map at least one board paper, or call "
            f"POST /board-frequency/recompute."
        ),
    }
