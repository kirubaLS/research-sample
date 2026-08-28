"""Request-scoped dependencies. Tenancy is resolved once and applied to every query."""

from __future__ import annotations

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
