"""Reading a class mark-entry sheet -- one photograph, many students -- into the same
proposal pipeline every other reading writes to.

A grid sheet cannot be confirmed the way a single student's reading is: a roll the roster
does not recognise is not a reason to lose the marks next to it, and a name that does not
quite match the roster is not a reason to refuse either -- both are reasons to ask a
person, once, and let every clean row through untouched. So a row becomes an ordinary
``ProposedMark`` only once it is resolved to a real student; until then its cells are held
on the row itself, exactly as read.

Four acts:

  1. **upload** -- the photograph is read and split into one row per roll number. A roll
     already on the roster, whose written name is not too far from the roster's own, is
     resolved on the spot; anything else waits.
  2. **review** -- a person sees every row: matched or not, and what would be confirmed.
  3. **resolve** -- a person points an unresolved row at an existing student, or creates
     one from the row's own name and roll, or simply says a flagged match is fine.
  4. **confirm** -- every clean row's marks become MarkEvents in one call. A row still
     flagged is skipped and named, never silently dropped and never guessed through.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_scanner
from app.api.documents import content_type_for, store_document
from app.api.matching import match_address
from app.api.schemas import StudentCreateIn
from app.config import get_settings
from app.db import get_session
from app.extraction.gridsheet import read_grid
from app.extraction.marksheet import parse_address
from app.models import (
    Assessment,
    GridSheetRow,
    MarkEvent,
    ProposedMark,
    Question,
    ScanDocument,
    School,
    Section,
    StudentProfile,
)

router = APIRouter(prefix="/assessments", tags=["marks-engine"])

MAX_SHEET_BYTES = 15 * 1024 * 1024


def _assessment(db: Session, school: School, assessment_id: str) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != school.id:
        raise HTTPException(404, "not found")
    return assessment


def _section(db: Session, school: School, section_id: str) -> Section:
    section = db.get(Section, section_id)
    if section is None or section.school_id != school.id:
        raise HTTPException(404, "not found")
    return section


def _row_in_scope(db: Session, assessment: Assessment, document_id: str, row_id: str) -> GridSheetRow:
    row = db.get(GridSheetRow, row_id)
    if row is None or row.assessment_id != assessment.id or row.document_id != document_id:
        raise HTTPException(404, "not found")
    return row


def _name_matches(written: str, roster: str) -> bool:
    """Loose enough that a middle name, initial or transliteration spelling does not flag
    every row; tight enough that a wrong roll number still gets caught."""
    written_words = {w for w in written.lower().split() if w}
    roster_words = {w for w in roster.lower().split() if w}
    if not written_words or not roster_words:
        return True
    return bool(written_words & roster_words)


def _write_proposed_marks(
    db: Session,
    school: School,
    assessment: Assessment,
    questions: list[Question],
    student: StudentProfile,
    row: GridSheetRow,
    source_name: str,
) -> None:
    """Turn one resolved row's cells into this student's ProposedMarks -- the same table,
    the same shape, that a single-student reading writes to. A re-resolve (a different
    student picked, a correction) replaces whatever this row wrote before."""
    for old in db.scalars(
        select(ProposedMark).where(
            ProposedMark.assessment_id == assessment.id,
            ProposedMark.student_id == student.id,
        )
    ):
        db.delete(old)
    db.flush()

    seen: set[str] = set()
    for cell in row.cells:
        canonical, _why = parse_address(cell.get("question_label") or "")
        question, _why = match_address(questions, canonical)
        if question is None or question.address in seen:
            continue
        seen.add(question.address)

        raw = cell.get("raw_value") or ""
        marks: float | None = None
        problem: str | None = None
        if not raw:
            problem = "left blank on the sheet"
        else:
            try:
                marks = float(raw)
            except ValueError:
                problem = f"{raw!r} is not a number"
        if problem is None and marks is not None:
            if marks > float(question.max_marks):
                problem = (
                    f"{marks:g} is more than the {float(question.max_marks):g} this "
                    f"question is worth"
                )
            elif marks < 0:
                problem = "a negative mark"

        db.add(ProposedMark(
            school_id=school.id, assessment_id=assessment.id, student_id=student.id,
            address=question.address, marks=marks, state="awarded",
            source_kind="ocr_grid", source_name=source_name[:200],
            origin=f"grid sheet, roll {row.roll_no}"[:200], raw_value=raw[:64], problem=problem,
        ))


@router.post("/{assessment_id}/sections/{section_id}/gridsheet", status_code=201)
async def upload_gridsheet(
    assessment_id: str,
    section_id: str,
    files: list[UploadFile] = File(...),
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """Read a class mark-entry sheet and stage one row per roll number it names."""
    assessment = _assessment(db, school, assessment_id)
    section = _section(db, school, section_id)

    questions = list(db.scalars(select(Question).where(Question.assessment_id == assessment.id)))
    if not questions:
        raise HTTPException(
            422,
            "this paper has no questions yet. Scan it, confirm the extraction and map it "
            "to the book first, so a mark has something to attach to.",
        )
    if not files:
        raise HTTPException(422, "no file was sent")

    pages: list[tuple[bytes, str]] = []
    for upload in files:
        content = await upload.read()
        if not content:
            raise HTTPException(422, f"{upload.filename or 'a page'} is empty")
        if len(content) > MAX_SHEET_BYTES:
            raise HTTPException(
                413, f"{upload.filename or 'a page'} is larger than "
                     f"{MAX_SHEET_BYTES // 1024 // 1024} MB"
            )
        pages.append((content, content_type_for(upload.filename, upload.content_type)))

    reading = read_grid(pages, api_key=get_settings().anthropic_api_key)
    if reading.refused:
        raise HTTPException(422, reading.refused)

    document = store_document(
        db, school_id=school.id, assessment_id=assessment.id, student_id=None,
        kind="mark_grid", pages=[(content, content_type, None) for content, content_type in pages],
        uploaded_by="",
    )

    roster = list(db.scalars(select(StudentProfile).where(StudentProfile.section_id == section.id)))
    by_roll = {s.roll_no: s for s in roster}
    source_name = files[0].filename or "grid sheet"

    rows: list[GridSheetRow] = []
    for parsed in reading.rows:
        student = by_roll.get(parsed.roll_no)
        if student is None:
            status = "unmatched"
        elif _name_matches(parsed.name_as_written, student.name):
            status = "clean"
        else:
            status = "name_mismatch"

        grid_row = GridSheetRow(
            school_id=school.id, assessment_id=assessment.id, section_id=section.id,
            document_id=document.id, roll_no=parsed.roll_no,
            name_as_written=parsed.name_as_written[:200],
            student_id=student.id if student else None, status=status,
            cells=[{"question_label": c.question_label, "raw_value": c.raw_value} for c in parsed.cells],
        )
        db.add(grid_row)
        db.flush()
        if student is not None:
            _write_proposed_marks(db, school, assessment, questions, student, grid_row, source_name)
        rows.append(grid_row)
    db.commit()

    return {
        "document_id": document.id,
        "rows": len(rows),
        "clean": sum(1 for r in rows if r.status == "clean"),
        "name_mismatch": sum(1 for r in rows if r.status == "name_mismatch"),
        "unmatched": sum(1 for r in rows if r.status == "unmatched"),
        "problems": reading.problems,
        "next": f"/assessments/{assessment.id}/gridsheet/{document.id}",
    }


@router.get("/{assessment_id}/gridsheet/{document_id}")
def review_gridsheet(
    assessment_id: str,
    document_id: str,
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """Every row this sheet produced, with what would be confirmed for it."""
    assessment = _assessment(db, school, assessment_id)
    rows = list(db.scalars(
        select(GridSheetRow)
        .where(GridSheetRow.document_id == document_id, GridSheetRow.assessment_id == assessment.id)
        .order_by(GridSheetRow.roll_no)
    ))
    if not rows:
        raise HTTPException(404, "not found")

    out = []
    for row in rows:
        marks = []
        blocked = False
        student = None
        if row.student_id is not None:
            student = db.get(StudentProfile, row.student_id)
            proposals = list(db.scalars(
                select(ProposedMark).where(
                    ProposedMark.assessment_id == assessment.id,
                    ProposedMark.student_id == row.student_id,
                )
            ))
            blocked = any(p.problem for p in proposals)
            marks = [
                {
                    "address": p.address,
                    "marks": float(p.marks) if p.marks is not None else None,
                    "state": p.state,
                    "raw_value": p.raw_value,
                    "problem": p.problem,
                }
                for p in proposals
            ]
        out.append({
            "row_id": row.id,
            "roll_no": row.roll_no,
            "name_as_written": row.name_as_written,
            "status": row.status,
            "note": row.note,
            "student": {"id": student.id, "name": student.name} if student else None,
            "marks": marks,
            "can_confirm": row.status == "clean" and not blocked and bool(marks),
        })

    return {
        "document_id": document_id,
        "assessment": {"id": assessment.id, "title": assessment.title},
        "rows": out,
        "ready_to_confirm": sum(1 for r in out if r["can_confirm"]),
    }


class ResolveIn(BaseModel):
    #: point this row at a student already on the roster
    student_id: str | None = None
    #: or create one from the sheet's own name and roll
    create: StudentCreateIn | None = None


@router.post("/{assessment_id}/gridsheet/{document_id}/rows/{row_id}/resolve")
def resolve_row(
    assessment_id: str,
    document_id: str,
    row_id: str,
    body: ResolveIn,
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """Point an unmatched or a name-mismatched row at a real student.

    Also how a name mismatch is waved through: resolve the row to the student it already
    matched, and it becomes clean. Nothing here is silent -- the row keeps who confirmed it
    was fine, in the same audit trail every other proposal carries.
    """
    assessment = _assessment(db, school, assessment_id)
    row = _row_in_scope(db, assessment, document_id, row_id)
    if body.student_id and body.create:
        raise HTTPException(422, "pick an existing student or create one, not both")

    if body.create is not None:
        clash = db.scalar(
            select(StudentProfile).where(
                StudentProfile.section_id == row.section_id,
                StudentProfile.roll_no == body.create.roll_no,
            )
        )
        if clash is not None:
            raise HTTPException(409, f"roll {body.create.roll_no} already belongs to {clash.name}")
        student = StudentProfile(
            school_id=school.id, section_id=row.section_id, name=body.create.name,
            roll_no=body.create.roll_no, age=body.create.age, gender=body.create.gender,
            dob=body.create.dob,
        )
        db.add(student)
        db.flush()
    elif body.student_id:
        student = db.get(StudentProfile, body.student_id)
        if student is None or student.school_id != school.id:
            raise HTTPException(404, "no such student")
    else:
        raise HTTPException(422, "give a student_id, or create a new student from this row")

    row.student_id = student.id
    row.status = "clean"
    row.note = None
    db.flush()

    questions = list(db.scalars(select(Question).where(Question.assessment_id == assessment.id)))
    document = db.get(ScanDocument, document_id)
    _write_proposed_marks(
        db, school, assessment, questions, student, row,
        document.uploaded_by if document and document.uploaded_by else "grid sheet",
    )
    db.commit()
    return {"row_id": row.id, "student_id": student.id, "status": row.status}


class ConfirmGridIn(BaseModel):
    by: str = ""


@router.post("/{assessment_id}/gridsheet/{document_id}/confirm")
def confirm_gridsheet(
    assessment_id: str,
    document_id: str,
    body: ConfirmGridIn,
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """Confirm every clean row in one call. A flagged row is skipped and named, never
    guessed through -- the response says exactly which rolls still need a person."""
    assessment = _assessment(db, school, assessment_id)
    if not body.by.strip():
        raise HTTPException(422, "put your name to these marks before confirming them")

    rows = list(db.scalars(
        select(GridSheetRow).where(
            GridSheetRow.document_id == document_id, GridSheetRow.assessment_id == assessment.id
        )
    ))
    if not rows:
        raise HTTPException(404, "not found")

    questions = {
        q.address: q for q in db.scalars(select(Question).where(Question.assessment_id == assessment.id))
    }
    confirmed, skipped = [], []
    for row in rows:
        if row.status != "clean" or row.student_id is None:
            skipped.append({"roll_no": row.roll_no, "reason": f"not resolved ({row.status})"})
            continue
        proposals = list(db.scalars(
            select(ProposedMark).where(
                ProposedMark.assessment_id == assessment.id,
                ProposedMark.student_id == row.student_id,
            )
        ))
        blocked = [p for p in proposals if p.problem]
        if blocked:
            skipped.append({
                "roll_no": row.roll_no,
                "reason": f"{len(blocked)} row(s) still have a problem",
            })
            continue
        if not proposals:
            skipped.append({"roll_no": row.roll_no, "reason": "nothing to confirm"})
            continue

        for p in proposals:
            question = questions.get(p.address)
            if question is None:
                continue
            db.add(MarkEvent(
                assessment_id=assessment.id, student_id=row.student_id, question_id=question.id,
                state=p.state,
                marks=float(p.marks) if p.state == "awarded" and p.marks is not None else None,
                source="teacher", confidence=1.0, actor_id=body.by[:36],
                provenance={
                    "confirmed_by": body.by,
                    "read_from": p.source_name or p.source_kind,
                    "origin": p.origin,
                    "raw_value": p.raw_value,
                    "edited_by": p.edited_by,
                },
            ))
        for p in proposals:
            db.delete(p)
        confirmed.append(row.roll_no)

    db.commit()
    return {"confirmed": confirmed, "skipped": skipped, "confirmed_by": body.by}
