"""The operator surface: create a school, add sections, mint a principal's key.

This is the GUI equivalent of ``scripts.create_school`` and ``scripts.admin_key``, for the
person running the deployment rather than the person running a school. It sits behind
``X-Platform-Key`` -- a separate secret from any school key -- because a principal must
never be able to create schools or read another school's credential.

Two rules the routes here are built around:

* A key is shown **once**, at the moment it is created or rotated. Listing schools returns
  no keys at all, so a screen left open in a staffroom cannot leak one.
* Rotation is immediate and total: the previous key stops working on the next request.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_admin
from app.config import get_settings
from app.db import get_session
from app.models import STAFF_ROLES, School, Section, StaffKey, StudentProfile
from app.ratelimit import FixedWindowLimiter, client_key

router = APIRouter(
    prefix="/platform", tags=["platform"], dependencies=[Depends(require_platform_admin)]
)

#: the operator key is the highest credential here, so guessing at it gets a low ceiling
_limiter = FixedWindowLimiter(limit=get_settings().platform_rate_limit_per_hour)


class SectionIn(BaseModel):
    grade: int = Field(ge=1, le=12)
    name: str = Field(min_length=1, max_length=8)

    @field_validator("name")
    @classmethod
    def _normalise(cls, v: str) -> str:
        # 'a' and 'A' are the same class; storing both would split a roster in two
        return v.strip().upper()


def _key_view(k: StaffKey) -> dict:
    """Never carries ``api_key``. Listing a key must not be a way of reading it."""
    return {
        "id": k.id,
        "role": k.role,
        "label": k.label,
        "school_id": k.school_id,
        "created_at": k.created_at.isoformat() if k.created_at else None,
        "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
    }


class StaffKeyIn(BaseModel):
    role: str = Field(default="principal")
    label: str = Field(default="", max_length=120)


class SchoolIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    board: str = Field(default="CBSE", max_length=32)
    state: str | None = Field(default="Tamil Nadu", max_length=64)
    training_consent: str = "operational_only"
    sections: list[SectionIn] = Field(default_factory=lambda: [SectionIn(grade=10, name="A")])

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("training_consent")
    @classmethod
    def _consent(cls, v: str) -> str:
        allowed = {"operational_only", "improve_models", "research"}
        if v not in allowed:
            raise ValueError(f"training_consent must be one of {sorted(allowed)}")
        return v


def _section_view(section: Section) -> dict:
    return {
        "id": section.id,
        "label": f"Class {section.grade}-{section.name}",
        "grade": section.grade,
        "name": section.name,
        "student_path": f"/t/{section.id}",
    }


def _school_view(db: Session, school: School) -> dict:
    """Never includes the API key. Listing is a different act from issuing."""
    sections = db.scalars(
        select(Section).where(Section.school_id == school.id).order_by(Section.grade, Section.name)
    ).all()
    students = db.scalar(
        select(func.count(StudentProfile.id)).where(StudentProfile.school_id == school.id)
    )
    return {
        "id": school.id,
        "name": school.name,
        "board": school.board,
        "state": school.state,
        "training_consent": school.training_consent,
        "students": students or 0,
        "sections": [_section_view(s) for s in sections],
    }


@router.get("/me")
def whoami(request: Request) -> dict:
    """Validates the operator key. The console's sign-in check."""
    _limiter.check(client_key(request))
    return {"role": "platform_admin"}


@router.get("/schools")
def list_schools(db: Session = Depends(get_session)) -> list[dict]:
    schools = db.scalars(select(School).order_by(School.name)).all()
    return [_school_view(db, s) for s in schools]


@router.post("/schools", status_code=status.HTTP_201_CREATED)
def create_school(body: SchoolIn, db: Session = Depends(get_session)) -> dict:
    """Create a school, its sections, and the principal's key.

    The key comes back exactly once, in this response. There is no route that reads it
    back later -- only ``/rotate``, which replaces it.
    """
    if db.scalar(select(School).where(School.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "a school with that name already exists")

    school = School(
        name=body.name,
        board=body.board,
        state=body.state,
        api_key=secrets.token_urlsafe(24),
        training_consent=body.training_consent,
    )
    db.add(school)
    db.flush()

    seen: set[tuple[int, str]] = set()
    for spec in body.sections:
        if (spec.grade, spec.name) in seen:
            continue
        seen.add((spec.grade, spec.name))
        db.add(Section(school_id=school.id, grade=spec.grade, name=spec.name))
    db.commit()
    db.refresh(school)

    view = _school_view(db, school)
    view["api_key"] = school.api_key
    view["api_key_notice"] = (
        "This key is shown once. Give it to the principal and store it somewhere safe -- "
        "if it is lost, issue a new one with Rotate."
    )
    return view


@router.post("/schools/{school_id}/sections", status_code=status.HTTP_201_CREATED)
def add_section(
    school_id: str, body: SectionIn, db: Session = Depends(get_session)
) -> dict:
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    existing = db.scalar(
        select(Section).where(
            Section.school_id == school_id,
            Section.grade == body.grade,
            Section.name == body.name,
        )
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "that class already exists")
    section = Section(school_id=school_id, grade=body.grade, name=body.name)
    db.add(section)
    db.commit()
    db.refresh(section)
    return _section_view(section)


@router.get("/keys")
def list_admin_keys(db: Session = Depends(get_session)) -> list[dict]:
    """Admin keys, which belong to no school. The secrets are not here."""
    keys = db.scalars(
        select(StaffKey).where(StaffKey.school_id.is_(None)).order_by(StaffKey.created_at)
    ).all()
    return [_key_view(k) for k in keys]


@router.post("/keys", status_code=status.HTTP_201_CREATED)
def issue_admin_key(body: StaffKeyIn, db: Session = Depends(get_session)) -> dict:
    """Issue an admin key: every school on this deployment, and the power to create more.

    Not attached to a school, on purpose. An admin who had a home school would be one
    forgotten header away from acting on the wrong one; with none, every request has to
    name the school it is about.
    """
    key = StaffKey(
        school_id=None, api_key=secrets.token_urlsafe(24), role="admin",
        label=body.label.strip(),
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    view = _key_view(key)
    view["api_key"] = key.api_key
    view["api_key_notice"] = (
        "Shown once. This key can create schools and act on every school on this "
        "deployment -- store it as carefully as the operator key itself."
    )
    return view


@router.post("/keys/{key_id}/revoke")
def revoke_admin_key(key_id: str, db: Session = Depends(get_session)) -> dict:
    key = db.get(StaffKey, key_id)
    if key is None or key.school_id is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such key")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        db.commit()
    return _key_view(key)


@router.get("/schools/{school_id}/keys")
def list_staff_keys(school_id: str, db: Session = Depends(get_session)) -> list[dict]:
    """Who holds a key at this school, and with what role. The secrets are not here.

    There is no route anywhere that reads a key back. If one is lost it is revoked and a
    new one issued, which is also the only honest thing to tell a principal who asks.
    """
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    keys = db.scalars(
        select(StaffKey).where(StaffKey.school_id == school_id).order_by(StaffKey.created_at)
    ).all()
    return [_key_view(k) for k in keys]


@router.post("/schools/{school_id}/keys", status_code=status.HTTP_201_CREATED)
def issue_staff_key(school_id: str, body: StaffKeyIn, db: Session = Depends(get_session)) -> dict:
    """Issue a key for one person at one school.

    A principal key reads results and progress across the school. It cannot scan a paper,
    enter marks or change the roster -- so the person who runs the assessments and the
    person who reads them are no longer the same credential, and an office laptop left
    signed in cannot alter a mark.
    """
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    if body.role not in STAFF_ROLES:
        raise HTTPException(422, f"role must be one of {', '.join(STAFF_ROLES)}")

    key = StaffKey(
        school_id=school.id, api_key=secrets.token_urlsafe(24),
        role=body.role, label=body.label.strip(),
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    view = _key_view(key)
    view["api_key"] = key.api_key
    view["api_key_notice"] = (
        "Shown once. Give it to the person named and store it somewhere safe -- there is "
        "no route that reads it back, only revoke and re-issue."
    )
    return view


@router.post("/schools/{school_id}/keys/{key_id}/revoke")
def revoke_staff_key(school_id: str, key_id: str, db: Session = Depends(get_session)) -> dict:
    """Stop a key working. The row stays: who held access, and until when, is the first
    question asked after anything goes wrong."""
    key = db.get(StaffKey, key_id)
    if key is None or key.school_id != school_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such key")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        db.commit()
    return _key_view(key)


@router.post("/schools/{school_id}/rotate-key")
def rotate_key(school_id: str, db: Session = Depends(get_session)) -> dict:
    """Issue a new principal key. The old one stops working immediately.

    Sections and every student record are untouched -- rotating a credential must not
    disturb a class link a school has already handed out.
    """
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
    school.api_key = secrets.token_urlsafe(24)
    db.commit()
    return {
        "school_id": school.id,
        "name": school.name,
        "api_key": school.api_key,
        "api_key_notice": (
            "Shown once. Anyone holding the previous key is now signed out."
        ),
    }
