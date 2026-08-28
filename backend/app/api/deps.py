"""Request-scoped dependencies. Tenancy is resolved once and applied to every query."""

from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import School


def current_school(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_session),
) -> School:
    school = db.scalar(select(School).where(School.api_key == x_api_key))
    if school is None:
        # 404 rather than 403: a wrong key must not confirm that a school exists
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return school


def require_admin(school: School = Depends(current_school)) -> School:
    """Principal / admin surface. Students never reach these routes — they hold no key."""
    return school


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
