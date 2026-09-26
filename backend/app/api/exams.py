"""Exam days: a named, dated exam ("Unit Test 2", "Quarterly Exam") that groups each
subject's own paper, and can be scheduled before any paper for it exists.

Every name and date here is one a principal or admin entered through POST /admin/exams;
every score is the same resolved-mark rollup app.api.academics computes for every other
screen, grouped by exam instead of by paper. Papers that were never attached to an exam
(everything entered before this existed) still appear, each as its own conducted entry,
exactly as the old per-paper list showed them.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.academics import (
    TaggedRow,
    _subject_label,
    resolved_rows,
    section_subject_averages,
    tests_with_movement,
)
from app.api.deps import require_admin, require_reader
from app.db import get_session
from app.models import Assessment, Exam, School

router = APIRouter(prefix="/admin/exams", tags=["exams"])


class ExamIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scheduled_date: date


class ExamPaperIn(BaseModel):
    assessment_id: str


def _exam_view(exam: Exam, paper_count: int) -> dict:
    return {
        "id": exam.id, "name": exam.name,
        "scheduled_date": exam.scheduled_date.isoformat(),
        "paper_count": paper_count,
    }


def _get_exam(db: Session, school: School, exam_id: str) -> Exam:
    exam = db.get(Exam, exam_id)
    if exam is None or exam.school_id != school.id:
        raise HTTPException(404, "no such exam")
    return exam


@router.post("")
def create_exam(
    body: ExamIn, school: School = Depends(require_admin), db: Session = Depends(get_session),
) -> dict:
    """Schedule an exam day. It needs no paper yet -- that is what makes it upcoming."""
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "an exam needs a name")
    exam = Exam(school_id=school.id, name=name, scheduled_date=body.scheduled_date)
    db.add(exam)
    db.flush()
    return _exam_view(exam, 0)


@router.post("/{exam_id}/papers")
def attach_paper(
    exam_id: str, body: ExamPaperIn,
    school: School = Depends(require_admin), db: Session = Depends(get_session),
) -> dict:
    """Put an existing paper under this exam. Moving it from another exam is allowed --
    the paper's own marks do not change, only which exam day they are reported under."""
    exam = _get_exam(db, school, exam_id)
    paper = db.get(Assessment, body.assessment_id)
    if paper is None or paper.school_id != school.id:
        raise HTTPException(404, "no such paper")
    paper.exam_id = exam.id
    db.flush()
    count = len(list(db.scalars(select(Assessment.id).where(Assessment.exam_id == exam.id))))
    return _exam_view(exam, count)


@router.delete("/{exam_id}/papers/{assessment_id}")
def detach_paper(
    exam_id: str, assessment_id: str,
    school: School = Depends(require_admin), db: Session = Depends(get_session),
) -> dict:
    exam = _get_exam(db, school, exam_id)
    paper = db.get(Assessment, assessment_id)
    if paper is None or paper.school_id != school.id or paper.exam_id != exam.id:
        raise HTTPException(404, "that paper is not part of this exam")
    paper.exam_id = None
    db.flush()
    count = len(list(db.scalars(select(Assessment.id).where(Assessment.exam_id == exam.id))))
    return _exam_view(exam, count)


def _rollup(db: Session, rows: list[TaggedRow]) -> dict:
    grid = section_subject_averages(db, rows)
    earned = sum(c["earned"] for c in grid)
    available = sum(c["available"] for c in grid)
    for c in grid:
        del c["earned"], c["available"]
    return {
        "grid": grid,
        "school_avg_pct": round(earned / available * 100, 1) if available else None,
        "students_marked": len({t.row.student_id for t in rows}),
        "subjects": sorted({c["subject_label"] for c in grid}),
    }


@router.get("")
def list_exams(
    school: School = Depends(require_reader), db: Session = Depends(get_session),
) -> dict:
    """Upcoming (scheduled, no marks yet), awaiting marks (date passed, no marks yet) and
    conducted (at least one resolved mark), plus the weakest subject across every mark."""
    today = date.today()
    exams = list(db.scalars(select(Exam).where(Exam.school_id == school.id)))
    papers = list(db.scalars(select(Assessment).where(Assessment.school_id == school.id)))
    papers_by_exam: dict[str, list[Assessment]] = {}
    for p in papers:
        if p.exam_id:
            papers_by_exam.setdefault(p.exam_id, []).append(p)
    exam_of = {p.id: p.exam_id for p in papers}

    tagged = resolved_rows(db, school)
    rows_by_exam: dict[str, list[TaggedRow]] = {}
    standalone_rows: list[TaggedRow] = []
    for t in tagged:
        eid = exam_of.get(t.assessment_id)
        if eid:
            rows_by_exam.setdefault(eid, []).append(t)
        else:
            standalone_rows.append(t)

    upcoming, awaiting, conducted = [], [], []
    for exam in exams:
        view = _exam_view(exam, len(papers_by_exam.get(exam.id, [])))
        rows = rows_by_exam.get(exam.id)
        if rows:
            rollup = _rollup(db, rows)
            if rollup["school_avg_pct"] is not None:
                conducted.append({"kind": "exam", **view, "date": view["scheduled_date"], **rollup})
                continue
        if exam.scheduled_date >= today:
            upcoming.append({**view, "status": "Scheduled", "days_away": (exam.scheduled_date - today).days})
        else:
            awaiting.append({**view, "status": "Awaiting marks"})

    # vs last: the conducted exam immediately before this one, by its real scheduled date
    conducted.sort(key=lambda e: e["scheduled_date"])
    prev: dict | None = None
    for e in conducted:
        e["previous"] = {"id": prev["id"], "name": prev["name"]} if prev else None
        e["delta_pct"] = round(e["school_avg_pct"] - prev["school_avg_pct"], 1) if prev else None
        prev = e

    # Papers never attached to an exam keep showing, one entry each, with the same
    # same-subject "vs last" tests_with_movement already gives the old per-paper list.
    movement = {m["assessment_id"]: m for m in tests_with_movement(db, standalone_rows)}
    by_paper: dict[str, list[TaggedRow]] = {}
    for t in standalone_rows:
        by_paper.setdefault(t.assessment_id, []).append(t)
    paper_index = {p.id: p for p in papers}
    for aid, rows in by_paper.items():
        rollup = _rollup(db, rows)
        if rollup["school_avg_pct"] is None:
            continue
        p = paper_index[aid]
        conducted.append({
            "kind": "paper", "id": aid, "name": p.title,
            "date": p.created_at.date().isoformat() if p.created_at else None,
            "scheduled_date": None, "paper_count": 1,
            "previous": None, "delta_pct": movement.get(aid, {}).get("delta_pct"),
            **rollup,
        })

    conducted.sort(key=lambda e: e["date"] or "", reverse=True)
    upcoming.sort(key=lambda e: e["scheduled_date"])
    awaiting.sort(key=lambda e: e["scheduled_date"], reverse=True)

    by_subject: dict[str, list[float]] = {}
    for t in tagged:
        if t.row.counts:
            pair = by_subject.setdefault(t.subject_code, [0.0, 0.0])
            pair[0] += float(t.row.earned)
            pair[1] += float(t.row.max_marks)
    scored = [(code, e / a * 100) for code, (e, a) in by_subject.items() if a > 0]
    weakest = min(scored, key=lambda x: x[1], default=None)

    return {
        "today": today.isoformat(),
        "upcoming": upcoming,
        "awaiting_marks": awaiting,
        "conducted": conducted,
        "weakest_subject": (
            {"subject_code": weakest[0], "label": _subject_label(weakest[0]),
             "avg_score_pct": round(weakest[1], 1)} if weakest else None
        ),
    }
