"""Request-scoped dependencies. Tenancy is resolved once and applied to every query."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import School, StaffKey


@dataclass(frozen=True)
class Staff:
    """Who is asking, and with what authority.

    Roles are ordered: an admin can do everything a principal can. Routes state the
    minimum they need rather than listing the roles that happen to satisfy it today.
    """

    school: School
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def current_staff(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_session),
) -> Staff:
    """Resolve a key to a school and a role.

    A school's own ``api_key`` predates per-person keys and remains that school's admin
    credential, so no deployment loses access. Everything issued since is a ``staff_key``
    row, which is where a principal's read-only key lives.
    """
    school = db.scalar(select(School).where(School.api_key == x_api_key))
    if school is not None:
        return Staff(school=school, role="admin")

    staff = db.scalar(select(StaffKey).where(StaffKey.api_key == x_api_key))
    # A revoked key is treated exactly like one that never existed: answering differently
    # would tell whoever kept it that it was once real.
    if staff is None or staff.revoked_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return Staff(school=staff.school, role=staff.role)


def require_staff(staff: Staff = Depends(current_staff)) -> Staff:
    """Any signed-in member of school staff. Read-only surfaces use this."""
    return staff


def require_admin_staff(staff: Staff = Depends(current_staff)) -> Staff:
    """Anything that changes the school's data, and the whole marks engine.

    A principal is refused here with 403 rather than 404: unlike a wrong key, they are
    genuinely signed in, and telling them the surface exists but is not theirs is the
    honest answer -- there is nothing to hide from someone already inside the school.
    """
    if not staff.is_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "this needs an admin key. A principal key can read results and progress, but "
            "not scan papers, enter marks or change the roster.",
        )
    return staff


def current_school(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_session),
) -> School:
    school = db.scalar(select(School).where(School.api_key == x_api_key))
    if school is None:
        # 404 rather than 403: a wrong key must not confirm that a school exists
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return school


def require_admin(staff: Staff = Depends(require_admin_staff)) -> School:
    """The school an admin key belongs to. Students never reach these routes.

    Kept returning a ``School`` so every route already depending on it is unchanged in
    behaviour except for now refusing a principal key.
    """
    return staff.school


def require_reader(staff: Staff = Depends(require_staff)) -> School:
    """The school any staff key belongs to -- principal or admin. Read-only routes."""
    return staff.school


def require_platform_admin(
    x_platform_key: str = Header(..., alias="X-Platform-Key"),
) -> None:
    """The operator surface: creating schools and minting principal keys.

    Deliberately not derived from a school key. A principal holds one key for one school;
    if that key could also create schools or read another school's key, one leaked key
    would compromise every school on the deployment.

    Unset ``platform_admin_key`` disables the surface entirely rather than falling back to
    something weaker -- a deployment that forgot to configure it must fail closed.
    """
    from app.config import get_settings

    expected = get_settings().platform_admin_key
    if not expected:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "not found",
        )
    # constant time: a byte-by-byte comparison leaks the key one character at a time
    if not secrets.compare_digest(x_platform_key, expected):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
