"""Academic performance, rolled up from the same marks the rest of the API already
trusts -- one screen a principal opens to ask "which classes need attention", built on
real confirmed marks and nothing invented.

Deliberately does not carry an "aspiration", "action plan" or "recheck" -- this
deployment has no data model for any of those yet, and a screen that shows them anyway
would be showing a promise nobody can act on. What is here is derived straight from
``MarkEvent``: a status bucket per student (on_track / needs_attention /
requires_review / not_assessed) from their earned-over-available rate across every
paper they have marks on, rolled up per class.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_reader
from app.db import get_session
from app.models import Assessment, MarkEvent, Question, School, Section, StudentProfile

router = APIRouter(prefix="/admin/academics", tags=["academics"])

#: Below this rate a student is "requires_review"; below the higher one, "needs_attention";
#: at or above it, "on_track". Same three-band shape the BoardX report already uses for
#: upper/lower assembly, picked for consistency rather than re-derived per screen.
_REVIEW_BELOW = 0.50
_ATTENTION_BELOW = 0.75

STATUS_LABELS = {
    "on_track": "On Track",
    "needs_attention": "Needs Attention",
    "requires_review": "Requires Review",
    "not_assessed": "Not Yet Assessed",
}


@dataclass
class _StudentTotals:
    earned: float = 0.0
    available: float = 0.0
    assessment_ids: set[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.assessment_ids is None:
            self.assessment_ids = set()


def student_mark_totals(db: Session, school: School) -> dict[str, _StudentTotals]:
    """Every student's earned/available marks, summed across every paper in this school
    they have a resolved mark on -- the same append-only-log projection
    ``app.api.reports._current_marks`` uses, run once across the whole school instead of
    one assessment at a time, since this screen has to roll every paper up together."""
    from app.models.marks import SOURCE_PRECEDENCE

    rank = {s: i for i, s in enumerate(SOURCE_PRECEDENCE)}

    assessment_ids = list(db.scalars(select(Assessment.id).where(Assessment.school_id == school.id)))
    if not assessment_ids:
        return {}

    max_marks: dict[str, float] = {
        q_id: float(mm)
        for q_id, mm in db.execute(
            select(Question.id, Question.max_marks).where(Question.assessment_id.in_(assessment_ids))
        ).all()
    }

    resolved: dict[tuple[str, str, str], MarkEvent] = {}
    for ev in db.scalars(select(MarkEvent).where(MarkEvent.assessment_id.in_(assessment_ids))):
        key = (ev.assessment_id, ev.student_id, ev.question_id)
        prev = resolved.get(key)
        if (
            prev is None
            or rank.get(ev.source, -1) > rank.get(prev.source, -1)
            or (ev.source == prev.source and ev.created_at >= prev.created_at)
        ):
            resolved[key] = ev

    totals: dict[str, _StudentTotals] = {}
    for (assessment_id, student_id, question_id), ev in resolved.items():
        mm = max_marks.get(question_id)
        if mm is None:
            continue
        row = totals.setdefault(student_id, _StudentTotals())
        row.assessment_ids.add(assessment_id)
        if ev.state == "awarded":
            row.earned += float(ev.marks or 0.0)
            row.available += mm
    return totals


def _status_for(totals: _StudentTotals | None) -> str:
    if totals is None or totals.available <= 0:
        return "not_assessed"
    rate = totals.earned / totals.available
    if rate < _REVIEW_BELOW:
        return "requires_review"
    if rate < _ATTENTION_BELOW:
        return "needs_attention"
    return "on_track"


def _class_summaries(db: Session, school: School) -> list[dict]:
    totals = student_mark_totals(db, school)
    sections = list(
        db.scalars(select(Section).where(Section.school_id == school.id).order_by(Section.grade, Section.name))
    )
    out = []
    for section in sections:
        students = list(
            db.scalars(select(StudentProfile).where(StudentProfile.section_id == section.id))
        )
        counts = {k: 0 for k in STATUS_LABELS}
        earned_sum = available_sum = 0.0
        assessment_ids: set[str] = set()
        for student in students:
            t = totals.get(student.id)
            counts[_status_for(t)] += 1
            if t is not None:
                earned_sum += t.earned
                available_sum += t.available
                assessment_ids |= t.assessment_ids
        out.append({
            "section_id": section.id,
            "label": f"Class {section.grade}-{section.name}",
            "grade": section.grade,
            "name": section.name,
            "student_count": len(students),
            "status_counts": counts,
            "avg_score_pct": round(earned_sum / available_sum * 100, 1) if available_sum else None,
            "test_count": len(assessment_ids),
        })
    return out


@router.get("")
def academics_overview(
    school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> dict:
    """Every class, its status split and its average score -- the landing screen for
    "which classes need attention today"."""
    return {
        "school": {"id": school.id, "name": school.name},
        "classes": _class_summaries(db, school),
    }


def _overview_rows(db: Session, school: School) -> tuple[list[str], list[list[object]]]:
    header = [
        "Class", "Students", "On Track", "Needs Attention", "Requires Review",
        "Not Yet Assessed", "Avg Score %", "Tests With Marks",
    ]
    rows = [
        [
            c["label"], c["student_count"],
            c["status_counts"]["on_track"], c["status_counts"]["needs_attention"],
            c["status_counts"]["requires_review"], c["status_counts"]["not_assessed"],
            c["avg_score_pct"] if c["avg_score_pct"] is not None else "",
            c["test_count"],
        ]
        for c in _class_summaries(db, school)
    ]
    return header, rows


@router.get("/overview.xlsx")
def academics_overview_xlsx(
    school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> Response:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    header, rows = _overview_rows(db, school)
    wb = Workbook()
    ws = wb.active
    ws.title = "Class Overview"
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(row)
    for i, col in enumerate(header, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(14, len(col) + 2)

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{school.name}-class-overview.xlsx"'},
    )


@router.get("/overview.pdf")
def academics_overview_pdf(
    school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> Response:
    from fpdf import FPDF

    def safe(text: object) -> str:
        return str(text if text is not None else "").encode("latin-1", "replace").decode("latin-1")

    header, rows = _overview_rows(db, school)
    pdf = FPDF(format="A4", orientation="L")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, safe(f"{school.name} -- Class Overview"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)

    widths = [45, 22, 22, 30, 28, 28, 24, 26]
    pdf.set_font("Helvetica", "B", 9)
    for w, col in zip(widths, header):
        pdf.cell(w, 8, safe(col), border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for row in rows:
        for w, val in zip(widths, row):
            pdf.cell(w, 7, safe(val), border=1)
        pdf.ln()

    return Response(
        content=bytes(pdf.output()),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{school.name}-class-overview.pdf"'},
    )
