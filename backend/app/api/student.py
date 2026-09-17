"""The student portal: signing in with a shared report's PIN, and reading only what was
actually shared.

Unauthenticated by design up to the PIN itself, exactly like ``/t`` (see
``app.api.interest``'s module docstring) -- a student has no account until a teacher
hands them a PIN for one specific report. What comes back from login is not that PIN
again but a short-lived ``StudentSession`` token, so the low-entropy PIN is only ever
typed once rather than replayed on every request.

Every read here is checked against the report's own share state fresh, not against
anything baked into the session at login -- see ``StudentSession``'s own docstring for
why. A report a teacher has since unshared stops being readable the instant that
happens, even mid-session.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Section, StudentProfile, StudentReport, StudentSession
from app.ratelimit import FixedWindowLimiter, client_key

router = APIRouter(prefix="/student", tags=["student-portal"])

#: A PIN is four to six digits, guessable in enough tries -- the same reason
#: ``/t/{class_code}/start`` is rate-limited, and for the same per-IP reason.
_login_limiter = FixedWindowLimiter(limit=20, window_seconds=3600)

_SESSION_LIFETIME = timedelta(days=30)


def _hash_pin(pin: str, student_id: str) -> str:
    """Must match app.api.admin._hash_pin exactly -- both sides of one shared secret."""
    return hashlib.sha256(f"{pin}:{student_id}".encode()).hexdigest()


class StudentLoginIn(BaseModel):
    roll_no: str
    pin: str


@router.post("/{class_code}/login")
def student_login(
    class_code: str,
    body: StudentLoginIn,
    request: Request,
    db: Session = Depends(get_session),
) -> dict:
    """Roll number + PIN, traded for a session token.

    One PIN unlocks exactly the report it was issued for, not a general sign-in -- but a
    correct PIN opens the whole portal for that student, because a parent who can prove
    they hold one shared report's PIN has already been vouched for by the teacher who
    handed it out. Wrong roll number and wrong PIN answer identically, and both count
    against the same rate limit, so a guesser learns nothing either way.
    """
    _login_limiter.check(client_key(request))
    section = db.scalar(select(Section).where(Section.id == class_code))
    if section is None:
        raise HTTPException(404, "incorrect roll number or PIN")
    student = db.scalar(
        select(StudentProfile).where(
            StudentProfile.section_id == section.id, StudentProfile.roll_no == body.roll_no.strip()
        )
    )
    if student is None:
        raise HTTPException(404, "incorrect roll number or PIN")

    pin_hash = _hash_pin(body.pin.strip(), student.id)
    matched = db.scalar(
        select(StudentReport).where(
            StudentReport.student_id == student.id,
            StudentReport.share_pin_hash == pin_hash,
            StudentReport.shared_at.is_not(None),
            StudentReport.share_revoked_at.is_(None),
        )
    )
    if matched is None:
        raise HTTPException(404, "incorrect roll number or PIN")

    session = StudentSession(
        student_id=student.id, school_id=student.school_id,
        token=secrets.token_urlsafe(24),
        expires_at=datetime.now(UTC) + _SESSION_LIFETIME,
    )
    db.add(session)
    db.commit()
    return {
        "session_token": session.token,
        "student_name": student.name,
        "expires_at": session.expires_at.isoformat(),
    }


def current_student(
    x_student_session: str = Header(..., alias="X-Student-Session"),
    db: Session = Depends(get_session),
) -> StudentProfile:
    session = db.scalar(select(StudentSession).where(StudentSession.token == x_student_session))
    if session is None or session.revoked_at is not None:
        raise HTTPException(404, "not signed in")
    # sqlite (tests only; Postgres always returns tz-aware) hands back a naive datetime
    # for a DateTime(timezone=True) column -- same coercion PaperScanJob's staleness
    # check uses, so the two can be compared at all.
    expires_at = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise HTTPException(404, "not signed in")
    student = db.get(StudentProfile, session.student_id)
    if student is None:
        raise HTTPException(404, "not signed in")
    return student


def _shared_report_view(record: StudentReport, *, full: bool = False) -> dict:
    out = {
        "report_id": record.id,
        "assessment_id": record.assessment_id,
        "issued_at": record.created_at.isoformat() if record.created_at else None,
        "earned": float(record.earned),
        "available": float(record.available),
        "assessment_title": record.payload.get("assessment_title"),
        "shared_at": record.shared_at.isoformat() if record.shared_at else None,
    }
    if full:
        out["payload"] = record.payload
    return out


@router.get("/reports")
def my_shared_reports(
    student: StudentProfile = Depends(current_student), db: Session = Depends(get_session)
) -> dict:
    """Every report currently shared with the signed-in student -- never every report
    issued for them, only the ones a teacher chose to hand a PIN out for, and only while
    that share has not since been taken back."""
    records = db.scalars(
        select(StudentReport)
        .where(
            StudentReport.student_id == student.id,
            StudentReport.shared_at.is_not(None),
            StudentReport.share_revoked_at.is_(None),
        )
        .order_by(StudentReport.created_at.desc())
    ).all()
    return {"student_name": student.name, "reports": [_shared_report_view(r) for r in records]}


@router.get("/reports/{report_id}")
def my_shared_report(
    report_id: str,
    student: StudentProfile = Depends(current_student), db: Session = Depends(get_session)
) -> dict:
    """One shared report's full payload. Refused, not just hidden, for a report that
    belongs to someone else or was never (or no longer) shared -- same 404-for-both-
    reasons rule as login above, so a session token cannot be used to probe which report
    ids exist."""
    record = db.get(StudentReport, report_id)
    if (
        record is None
        or record.student_id != student.id
        or record.shared_at is None
        or record.share_revoked_at is not None
    ):
        raise HTTPException(404, "not found")
    return _shared_report_view(record, full=True)


@router.post("/logout")
def student_logout(
    x_student_session: str = Header(..., alias="X-Student-Session"),
    db: Session = Depends(get_session),
) -> dict:
    session = db.scalar(select(StudentSession).where(StudentSession.token == x_student_session))
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        db.commit()
    return {"ok": True}
