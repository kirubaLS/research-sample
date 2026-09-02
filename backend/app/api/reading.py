"""Reading a student's marks out of a file, and having a person confirm them.

Three acts, kept apart on purpose:

  1. **read** -- a file is parsed into proposals. Nothing counts yet.
  2. **review** -- a person sees every proposal against the paper's own questions, with
     the cell it came from, and corrects what is wrong.
  3. **confirm** -- the proposals become marks, written as 'teacher', because the person
     who pressed the button is the one standing behind the numbers.

The controls that keep this honest are all at step 1, where it is cheapest to refuse:

  * an address the paper does not have is reported unmatched, never created
  * a mark above what the question is worth is flagged, never clamped
  * a value that is not a number is flagged, never guessed at
  * a file that cannot be read is refused by name, never half-read
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_scanner
from app.api.upload import IMAGE_SUFFIXES, pages_to_pdf
from app.db import get_session
from app.extraction.address import Address
from app.extraction.marksheet import Reading, read_any, read_pdf
from app.models import (
    MARK_STATES,
    Assessment,
    MarkEvent,
    ProposedMark,
    Question,
    School,
    StudentProfile,
)

router = APIRouter(prefix="/assessments", tags=["marks-engine"])

MAX_SHEET_BYTES = 15 * 1024 * 1024


def _student(db: Session, school: School, student_id: str) -> StudentProfile:
    student = db.get(StudentProfile, student_id)
    if student is None or student.school_id != school.id:
        raise HTTPException(404, "not found")
    return student


def _assessment(db: Session, school: School, assessment_id: str) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != school.id:
        raise HTTPException(404, "not found")
    return assessment


def _match(questions: list[Question], raw: str | None) -> tuple[Question | None, str | None]:
    """Resolve a parsed address against the paper. The paper is the vocabulary.

    A sheet often writes ``Q4`` where the paper says ``B/4//``. Matching on the question
    number alone is right when it is unambiguous and wrong the moment two sections both
    have a question 4 -- so an ambiguous label is reported as ambiguous rather than
    resolved to whichever came first.
    """
    if not raw:
        return None, "no question number"
    exact = [q for q in questions if q.address == raw]
    if exact:
        return exact[0], None

    parsed = Address.parse(raw.replace("/", " ")) if "/" in raw else None
    parts = raw.split("/")
    number = parts[1] if len(parts) == 4 and parts[1] else (parsed.question_no if parsed else None)
    sub = parts[2] if len(parts) == 4 and parts[2] else None
    alt = parts[3] if len(parts) == 4 and parts[3] else None
    if not number:
        return None, f"{raw!r} is not a question on this paper"

    candidates = [
        q for q in questions
        if q.question_no == number
        and (q.sub_part or "") == (sub or "")
        and (q.choice_alt or "") == (alt or "")
    ]
    if len(candidates) == 1:
        return candidates[0], None
    if not candidates:
        return None, f"this paper has no question {number}"
    return None, (
        f"question {number} is ambiguous: the paper has it in "
        + ", ".join(sorted({c.section or "no section" for c in candidates}))
        + ". Write the section too, as B/" + number + "."
    )


@router.post("/{assessment_id}/answers/{student_id}/read", status_code=201)
async def read_marks(
    assessment_id: str,
    student_id: str,
    files: list[UploadFile] = File(...),
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """Parse what was uploaded into proposals. Writes nothing to the marks.

    Takes what the question-paper scanner takes, through the same code: any number of
    pages, as PDFs or photographs, in the order they were sent. Two upload paths that
    accept different things is how one of them ends up rejecting a file the other allows,
    with nobody able to say which is right.

    A spreadsheet is its own case, because a spreadsheet has cells and a page does not.
    """
    assessment = _assessment(db, school, assessment_id)
    student = _student(db, school, student_id)

    questions = list(db.scalars(select(Question).where(Question.assessment_id == assessment.id)))
    if not questions:
        raise HTTPException(
            422,
            "this paper has no questions yet. Scan it, confirm the extraction and map it "
            "to the book first, so a mark has something to attach to.",
        )

    if not files:
        raise HTTPException(422, "no file was sent")

    first = files[0]
    name = (first.filename or "").lower()
    if len(files) == 1 and not name.endswith((".pdf", *IMAGE_SUFFIXES)):
        # A spreadsheet or a CSV: read from its cells, not from a rendered page.
        data = await first.read()
        if not data:
            raise HTTPException(422, "the file is empty")
        if len(data) > MAX_SHEET_BYTES:
            raise HTTPException(
                413, f"file is larger than {MAX_SHEET_BYTES // 1024 // 1024} MB"
            )
        reading: Reading = read_any(first.filename or "", data, None)
        source_name = first.filename or "file"
    else:
        # Pages: PDFs and photographs, merged in the order they were sent, exactly as the
        # question paper is. An image becomes a page of a PDF and is read from there, so
        # there is one extractor rather than two that can disagree.
        path = await pages_to_pdf(files)
        try:
            reading = read_pdf(path, source=first.filename or "scan")
        finally:
            path.unlink(missing_ok=True)
        source_name = (
            first.filename or "scan"
            if len(files) == 1
            else f"{len(files)} pages starting with {first.filename or 'a page'}"
        )

    if reading.refused:
        # 422 and the reason, rather than an empty success. A file that could not be read
        # and a file with no marks in it look identical from an empty list.
        raise HTTPException(422, reading.refused)

    # A new read replaces the last one: two readings of the same script side by side, with
    # no way to say which a mark came from, is worse than either.
    for old in db.scalars(
        select(ProposedMark).where(
            ProposedMark.assessment_id == assessment.id,
            ProposedMark.student_id == student.id,
        )
    ):
        db.delete(old)
    db.flush()

    by_address: dict[str, Question] = {q.address: q for q in questions}
    unmatched, written, seen = [], 0, set()
    for row in reading.rows:
        question, why = _match(questions, row.address)
        if question is None:
            unmatched.append({**row.as_dict(), "reason": why})
            continue
        if question.address in seen:
            unmatched.append({
                **row.as_dict(),
                "reason": f"question {question.question_no} appears more than once in this file",
            })
            continue
        seen.add(question.address)

        # 'blank' is what the reader says when a cell held something it could not turn
        # into a mark. It is not a mark state, so it is held as an unanswered proposal
        # carrying its own problem: the person reviewing has to supply the number, and
        # the cell's text is right there for them to read.
        state = row.state if row.state in MARK_STATES else "awarded"
        marks = row.marks if state == "awarded" else None
        problem = row.problem
        if row.state not in MARK_STATES and not problem:
            problem = f"nothing readable in this cell ({row.raw_value!r})"
        # Recognised text is a proposal, never an assertion. Every OCR row is held until
        # a person has looked at it against the sheet: on a real scan Tesseract reads 'Q1'
        # as 'Qi', and a value it misread the same way would otherwise be indistinguishable
        # from one read exactly.
        if problem is None and row.via_ocr:
            problem = "read by text recognition; check this one against the sheet"
        if problem is None and state == "awarded" and marks is not None:
            if marks > float(question.max_marks):
                problem = (
                    f"{marks:g} is more than the {float(question.max_marks):g} this "
                    f"question is worth"
                )
            elif marks < 0:
                problem = "a negative mark"

        db.add(ProposedMark(
            school_id=school.id, assessment_id=assessment.id, student_id=student.id,
            address=question.address, marks=marks, state=state,
            source_kind="ocr" if row.via_ocr else "file",
            source_name=source_name[:200],
            origin=row.origin[:200], raw_value=row.raw_value[:64], problem=problem,
        ))
        written += 1
    db.commit()

    return {
        "read": written,
        "unmatched": unmatched,
        "questions_on_paper": len(by_address),
        "rolls_in_file": reading.rolls,
        "problems": reading.problems,
        "source": source_name,
        "used_ocr": reading.used_ocr,
        #: Said plainly: a file naming several students was read for this one only.
        "note": (
            "This file mentions several roll numbers. Only the marks matching the "
            "question labels were read, and they were all applied to this student -- "
            "check them before confirming."
            if len(reading.rolls) > 1 else None
        ),
        "next": f"/assessments/{assessment.id}/answers/{student.id}/reading",
    }


@router.get("/{assessment_id}/answers/{student_id}/reading")
def read_proposals(
    assessment_id: str,
    student_id: str,
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """Every question on the paper, with what was read for it, if anything.

    Driven by the paper rather than by the file: a question the file said nothing about is
    the thing a person is checking for, and a list built from the file hides exactly that.
    """
    assessment = _assessment(db, school, assessment_id)
    student = _student(db, school, student_id)

    questions = list(db.scalars(
        select(Question).where(Question.assessment_id == assessment.id).order_by(Question.address)
    ))
    proposals = {
        p.address: p for p in db.scalars(
            select(ProposedMark).where(
                ProposedMark.assessment_id == assessment.id,
                ProposedMark.student_id == student.id,
            )
        )
    }

    rows = []
    for question in questions:
        p = proposals.get(question.address)
        rows.append({
            "address": question.address,
            "section": question.section,
            "question_no": question.question_no,
            "choice_alt": question.choice_alt,
            "max_marks": float(question.max_marks),
            "stem_text": question.stem_text,
            "read": p is not None,
            "marks": float(p.marks) if p and p.marks is not None else None,
            "state": p.state if p else None,
            "origin": p.origin if p else None,
            "raw_value": p.raw_value if p else None,
            "problem": p.problem if p else None,
            "edited_by": p.edited_by if p else None,
            "source_name": p.source_name if p else None,
        })

    blocked = [r for r in rows if r["problem"]]
    return {
        "assessment": {"id": assessment.id, "title": assessment.title},
        "student": {"id": student.id, "name": student.name, "roll_no": student.roll_no},
        "questions": rows,
        "read": sum(1 for r in rows if r["read"]),
        "missing": sum(1 for r in rows if not r["read"]),
        "blocked": len(blocked),
        #: Confirming with a blocked row would store a mark nobody could defend.
        "can_confirm": bool(rows) and not blocked and any(r["read"] for r in rows),
    }


class EditIn(BaseModel):
    marks: float | None = None
    state: str = "awarded"
    by: str = ""


@router.patch("/{assessment_id}/answers/{student_id}/reading/{address:path}")
def edit_proposal(
    assessment_id: str,
    student_id: str,
    address: str,
    body: EditIn,
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """A person corrects one proposal, or supplies one the file did not have."""
    assessment = _assessment(db, school, assessment_id)
    student = _student(db, school, student_id)

    question = db.scalar(
        select(Question).where(
            Question.assessment_id == assessment.id, Question.address == address
        )
    )
    if question is None:
        raise HTTPException(404, "no such question on this paper")
    if body.state not in MARK_STATES:
        raise HTTPException(422, f"unknown state {body.state!r}")
    if body.state == "awarded":
        if body.marks is None:
            raise HTTPException(422, "awarded but no marks given")
        if body.marks > float(question.max_marks):
            raise HTTPException(
                422,
                f"{body.marks:g} is more than the {float(question.max_marks):g} this "
                f"question is worth",
            )
        if body.marks < 0:
            raise HTTPException(422, "a mark cannot be negative")

    proposal = db.scalar(
        select(ProposedMark).where(
            ProposedMark.assessment_id == assessment.id,
            ProposedMark.student_id == student.id,
            ProposedMark.address == address,
        )
    )
    if proposal is None:
        proposal = ProposedMark(
            school_id=school.id, assessment_id=assessment.id, student_id=student.id,
            address=address, source_kind="person", source_name="", origin="entered by hand",
        )
        db.add(proposal)

    proposal.marks = body.marks if body.state == "awarded" else None
    proposal.state = body.state
    proposal.edited_by = body.by[:120] or "unnamed"
    # Corrected, so the problem the file caused is gone. The correction itself is recorded
    # in edited_by, which is what a later question about this mark actually asks about.
    proposal.problem = None
    db.commit()
    return read_proposals(assessment_id, student_id, school, db)


class ConfirmIn(BaseModel):
    by: str = ""


@router.post("/{assessment_id}/answers/{student_id}/reading/confirm")
def confirm_reading(
    assessment_id: str,
    student_id: str,
    body: ConfirmIn,
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """Turn the confirmed proposals into marks, under the name of whoever confirmed them."""
    assessment = _assessment(db, school, assessment_id)
    student = _student(db, school, student_id)
    if not body.by.strip():
        raise HTTPException(422, "put your name to these marks before confirming them")

    proposals = list(db.scalars(
        select(ProposedMark).where(
            ProposedMark.assessment_id == assessment.id,
            ProposedMark.student_id == student.id,
        )
    ))
    if not proposals:
        raise HTTPException(422, "there is nothing to confirm; read a file first")
    blocked = [p for p in proposals if p.problem]
    if blocked:
        raise HTTPException(
            422,
            f"{len(blocked)} row(s) still have a problem. Correct them first: "
            + "; ".join(f"{p.address} ({p.problem})" for p in blocked[:3]),
        )

    questions = {
        q.address: q for q in db.scalars(
            select(Question).where(Question.assessment_id == assessment.id)
        )
    }
    written = 0
    for p in proposals:
        question = questions.get(p.address)
        if question is None:
            continue
        db.add(MarkEvent(
            assessment_id=assessment.id, student_id=student.id, question_id=question.id,
            state=p.state,
            marks=float(p.marks) if p.state == "awarded" and p.marks is not None else None,
            source="teacher", confidence=1.0, actor_id=body.by[:36],
            provenance={
                "confirmed_by": body.by,
                # How this number arrived, kept with the mark: a disputed figure is asked
                # about months later, and "which cell was this?" is the first question.
                "read_from": p.source_name or p.source_kind,
                "origin": p.origin,
                "raw_value": p.raw_value,
                "edited_by": p.edited_by,
            },
        ))
        written += 1

    for p in proposals:
        db.delete(p)
    db.commit()
    return {"written": written, "confirmed_by": body.by}
