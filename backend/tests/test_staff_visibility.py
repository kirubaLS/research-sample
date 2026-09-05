"""GET /admin/staff: read-only visibility into who holds a key for a school, scoped the
same way every other reader route already is -- a principal never reaches another
school's rows, and no key secret is ever returned."""

from __future__ import annotations

import pytest


@pytest.fixture
def principal(client, school):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import StaffKey

    db = SessionLocal()
    if db.scalar(select(StaffKey).where(StaffKey.api_key == "principal-key-staff-vis")) is None:
        db.add(StaffKey(
            school_id=school["school_id"], api_key="principal-key-staff-vis",
            role="principal", label="Mrs Rani, Principal",
        ))
        db.commit()
    db.close()
    return {"X-API-Key": "principal-key-staff-vis"}


def _admin(school):
    return {"X-API-Key": school["api_key"]}


def test_a_principal_sees_who_holds_a_key_for_their_own_school(client, school, principal):
    r = client.get("/admin/staff", headers=principal)
    assert r.status_code == 200
    body = r.json()
    assert any(row["role"] == "principal" and row["label"] == "Mrs Rani, Principal" for row in body)
    # never the secret itself
    assert all("api_key" not in row for row in body)


def test_a_revoked_key_is_still_listed_but_marked(client, school):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import StaffKey

    db = SessionLocal()
    db.add(StaffKey(
        school_id=school["school_id"], api_key="revoked-staff-vis-key",
        role="principal", label="Former Principal",
    ))
    db.commit()
    key = db.scalar(select(StaffKey).where(StaffKey.api_key == "revoked-staff-vis-key"))
    from datetime import UTC, datetime
    key.revoked_at = datetime.now(UTC)
    db.commit()
    db.close()

    r = client.get("/admin/staff", headers=_admin(school))
    row = next(x for x in r.json() if x["label"] == "Former Principal")
    assert row["revoked_at"] is not None


def test_a_principal_cannot_see_another_schools_staff(client, school, principal):
    from app.db import SessionLocal
    from app.models import School, StaffKey

    db = SessionLocal()
    other = School(name="Other Staff School", api_key="other-school-staff-vis-key", state="Tamil Nadu")
    db.add(other)
    db.flush()
    db.add(StaffKey(
        school_id=other.id, api_key="other-principal-staff-vis", role="principal", label="Not Yours",
    ))
    db.commit()
    db.close()

    r = client.get("/admin/staff", headers=principal)
    assert all(row["label"] != "Not Yours" for row in r.json())
