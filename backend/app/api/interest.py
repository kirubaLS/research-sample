"""Use case 1 routes.

The student surface is unauthenticated by design — a per-class code, never an account —
and it is a dead end: no route here returns a score, a Holland code or a stream.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import CompletionOut, ProfileIn, ResponseBatchIn, SessionOut
from app.db import get_session
from app.models import (
    ItemResponse,
    ProfileResult,
    ScaleScore,
    School,
    Section,
    StudentProfile,
    TestSession,
)
from app.psychometrics.instrument import items, likert, screens
from app.psychometrics.scoring import score as score_profile
from app.psychometrics.validity import Response as VResponse
from app.psychometrics.validity import screen as screen_validity

router = APIRouter(prefix="/t", tags=["interest-test"])


def _school_by_code(db: Session, class_code: str) -> tuple[School, Section]:
    section = db.scalar(select(Section).where(Section.id == class_code))
    if section is None:
        raise HTTPException(404, "class not found")
    school = db.get(School, section.school_id)
    if school is None:
        raise HTTPException(404, "class not found")
    return school, section


@router.post("/{class_code}/start", response_model=SessionOut)
def start(class_code: str, body: ProfileIn, db: Session = Depends(get_session)) -> SessionOut:
    school, section = _school_by_code(db, class_code)

    student = db.scalar(
        select(StudentProfile).where(
            StudentProfile.section_id == section.id, StudentProfile.roll_no == body.roll_no
        )
    )
    if student is None:
        student = StudentProfile(
            school_id=school.id, section_id=section.id, name=body.name,
            roll_no=body.roll_no, age=body.age, gender=body.gender,
        )
        db.add(student)
        db.flush()

    existing = db.scalar(
        select(TestSession).where(
            TestSession.student_id == student.id, TestSession.completed_at.is_(None)
        )
    )
    if existing is not None:
        session = existing          # resume by roll number + class code
    else:
        seed = random.Random(f"{student.id}").randint(1, 10**9)
        session = TestSession(
            school_id=school.id, student_id=student.id, locale=body.locale,
            item_order=[seed], started_at=datetime.now(UTC),
        )
        db.add(session)
        db.flush()

    seed = (session.item_order or [1])[0]
    lk = likert()
    payload = [
        [
            {
                "item_id": it.id,
                "text": it.localised(session.locale),
                "options": lk["labels"].get(session.locale, lk["labels"]["en"]),
            }
            for it in group
        ]
        for group in screens(seed)
    ]
    return SessionOut(
        session_id=session.id, locale=session.locale, total_items=len(items()), screens=payload
    )


@router.post("/session/{session_id}/responses")
def submit(session_id: str, body: ResponseBatchIn, db: Session = Depends(get_session)) -> dict:
    """Idempotent per item — every answer is written the moment it is tapped."""
    session = db.get(TestSession, session_id)
    if session is None or session.completed_at is not None:
        raise HTTPException(404, "session not found")

    existing = {
        r.item_id: r
        for r in db.scalars(select(ItemResponse).where(ItemResponse.session_id == session_id))
    }
    for r in body.responses:
        row = existing.get(r.item_id)
        shown = datetime.fromtimestamp(r.shown_at, UTC) if r.shown_at else None
        answered = datetime.fromtimestamp(r.answered_at, UTC) if r.answered_at else None
        if row is None:
            db.add(
                ItemResponse(
                    session_id=session_id, item_id=r.item_id, value=r.value,
                    shown_at=shown, answered_at=answered,
                )
            )
        else:
            row.value, row.shown_at, row.answered_at = r.value, shown, answered
    db.flush()
    count = len(
        list(db.scalars(select(ItemResponse).where(ItemResponse.session_id == session_id)))
    )
    return {"saved": len(body.responses), "answered": count, "total_items": len(items())}


@router.post("/session/{session_id}/complete", response_model=CompletionOut)
def complete(session_id: str, db: Session = Depends(get_session)) -> CompletionOut:
    session = db.get(TestSession, session_id)
    if session is None:
        raise HTTPException(404, "session not found")

    rows = list(db.scalars(select(ItemResponse).where(ItemResponse.session_id == session_id)))
    responses = [
        VResponse(
            r.item_id,
            r.value,
            (r.answered_at - r.shown_at).total_seconds()
            if r.answered_at and r.shown_at
            else None,
        )
        for r in rows
    ]
    report = screen_validity(responses, len(items()))
    session.validity = report.status
    session.validity_detail = report.as_dict()
    session.completed_at = datetime.now(UTC)

    if report.status != "invalid":
        outcome = score_profile({r.item_id: r.value for r in rows})
        for s in outcome.scales:
            db.add(
                ScaleScore(
                    session_id=session_id, scale=s.scale, raw=s.raw, centered=s.centered,
                    percentile=s.percentile, ci_low=s.ci_low, ci_high=s.ci_high,
                )
            )
        db.add(
            ProfileResult(
                session_id=session_id, holland_code=outcome.holland_code,
                differentiation=outcome.differentiation, consistency=outcome.consistency,
                stream_fit=outcome.stream_fit,
                recommendation_withheld=outcome.recommendation_withheld,
                withheld_reason=outcome.withheld_reason,
            )
        )
    db.flush()

    # No score. No code. No stream. The student journey ends here.
    return CompletionOut(
        message="Thank you for completing the test. Your responses have been recorded.",
        submitted=len(rows),
    )
