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

    ``home`` is the school the key itself names. A principal has one and it is the only
    school they can ever reach. An admin has none, because an admin works across schools
    and says which one per request.
    """

    role: str
    home: School | None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def current_staff(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_session),
) -> Staff:
    """Resolve a key to a role, and to the school it names if it names one.

    A school's own ``api_key`` predates per-person keys and still works, as an admin bound
    to that one school, so no deployment loses access.
    """
    school = db.scalar(select(School).where(School.api_key == x_api_key))
    if school is not None:
        return Staff(role="admin", home=school)

    # The operator key opens the school side too, as an admin belonging to no school, so a
    # request has to name the one it is about. Not an escalation: this key already creates
    # schools and issues their credentials, so anything it could reach this way it could
    # reach by minting a key for itself. What it buys is that whoever runs the deployment
    # can scan a paper for a school without first issuing themselves a second credential.
    from app.config import get_settings  # noqa: PLC0415 - avoids a cycle at import time

    operator = get_settings().platform_admin_key
    if operator and secrets.compare_digest(x_api_key, operator):
        return Staff(role="admin", home=None)

    staff = db.scalar(select(StaffKey).where(StaffKey.api_key == x_api_key))
    # A revoked key is treated exactly like one that never existed: answering differently
    # would tell whoever kept it that it was once real.
    if staff is None or staff.revoked_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return Staff(role=staff.role, home=staff.school)


def school_in_scope(staff: Staff, requested: str | None, db: Session) -> School:
    """Which school this request is about.

    For anyone who is not an admin the answer comes from their key and nothing else. The
    requested id is not consulted, not compared and not reported on -- there is simply no
    path by which a principal's request reads a school from the request, which is a
    stronger guarantee than checking that it matches.
    """
    if not staff.is_admin:
        assert staff.home is not None, "a non-admin key always names its school"
        return staff.home

    if requested:
        school = db.get(School, requested)
        if school is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such school")
        return school
    if staff.home is not None:
        return staff.home
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "this key works across schools, so the request has to say which one. Send the "
        "school id in the X-School-Id header.",
    )


def require_staff(
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> Staff:
    """Any signed-in member of staff. Read-only surfaces use this."""
    school_in_scope(staff, x_school_id, db)      # rejects an admin who named no school
    return staff


def require_scanner(
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> School:
    """Reading a paper, storing a script, entering marks: any signed-in member of staff.

    A principal does this as well as an admin. It is a deliberate widening of what a
    principal may do -- they can now produce marks, not only read them -- so the earlier
    property that a signed-in dashboard could not alter a mark no longer holds. Every mark
    still records who confirmed it, which is what a disputed figure is actually checked
    against.

    What stays admin-only is the roster and the school itself: who the students are, and
    which credentials exist.
    """
    return school_in_scope(staff, x_school_id, db)


def require_admin_staff(staff: Staff = Depends(current_staff)) -> Staff:
    """Anything that changes a school's data, and the whole marks engine.

    A principal is refused with 403 rather than 404: unlike a wrong key, they are
    genuinely signed in, and telling them the surface exists but is not theirs is the
    honest answer -- there is nothing to hide from someone already inside the school.
    """
    if not staff.is_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "this needs an admin key. A principal key reads results, scans papers and "
            "enters marks for their own school, but does not change the roster or issue "
            "credentials.",
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


def require_admin(
    staff: Staff = Depends(require_admin_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> School:
    """The school an admin request is acting on. Students never reach these routes."""
    return school_in_scope(staff, x_school_id, db)


def require_reader(
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> School:
    """The school a read is about -- an admin's chosen one, or a principal's only one."""
    return school_in_scope(staff, x_school_id, db)


def require_platform_admin(
    x_platform_key: str | None = Header(default=None, alias="X-Platform-Key"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_session),
) -> None:
    """Creating schools, loading books, issuing keys.

    Two credentials open this, and only two:

    * the operator key, ``YAADHUM_PLATFORM_ADMIN_KEY``, which bootstraps a deployment and
      is the only way to issue the first admin key;
    * an **admin** staff key that names no school, because an admin creates schools and
      works across them -- that is the whole point of the role.

    A principal key never opens it, and neither does a school's own key, which is an admin
    bound to one school: it can run that school, not create another. So one leaked school
    credential still cannot reach a second school's data.

    Unset ``platform_admin_key`` disables the operator key entirely rather than falling
    back to something weaker -- a deployment that forgot to configure it must fail closed.
    An admin staff key still works, because it was issued deliberately.
    """
    from app.config import get_settings

    expected = get_settings().platform_admin_key
    # constant time: a byte-by-byte comparison leaks the key one character at a time
    if expected and x_platform_key and secrets.compare_digest(x_platform_key, expected):
        return

    if x_api_key:
        staff = db.scalar(select(StaffKey).where(StaffKey.api_key == x_api_key))
        if staff and staff.revoked_at is None and staff.role == "admin" and staff.school_id is None:
            return

    # 404 for every failure, so a probe cannot tell a wrong key from a disabled console
    raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
