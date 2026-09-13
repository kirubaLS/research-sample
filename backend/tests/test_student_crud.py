"""Student roster CRUD: a principal manages their own school's roster now (see test_roles's
manage_roster widening), the same way they already scan papers and enter marks."""

from __future__ import annotations

import pytest


@pytest.fixture
def principal(client, school):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import StaffKey

    db = SessionLocal()
    if db.scalar(select(StaffKey).where(StaffKey.api_key == "principal-key-abc")) is None:
        db.add(StaffKey(
            school_id=school["school_id"], api_key="principal-key-abc",
            role="principal", label="Mrs Rani, Principal",
        ))
        db.commit()
    db.close()
    return {"X-API-Key": "principal-key-abc"}


def _admin(school):
    return {"X-API-Key": school["api_key"]}


def test_a_principal_adds_a_student_to_their_own_school(client, school, principal):
    r = client.post(
        f"/admin/sections/{school['section_id']}/students", headers=principal,
        json={"name": "Kavya S", "roll_no": "21"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Kavya S"
    assert body["roll_no"] == "21"

    roster = client.get(f"/admin/sections/{school['section_id']}/students", headers=principal).json()
    assert any(s["roll_no"] == "21" and s["name"] == "Kavya S" for s in roster["students"])


def test_a_duplicate_roll_number_is_refused_not_silently_overwritten(client, school, principal):
    client.post(
        f"/admin/sections/{school['section_id']}/students", headers=principal,
        json={"name": "First Student", "roll_no": "22"},
    )
    r = client.post(
        f"/admin/sections/{school['section_id']}/students", headers=principal,
        json={"name": "Second Student", "roll_no": "22"},
    )
    assert r.status_code == 409
    assert "First Student" in r.json()["detail"]


def test_a_student_can_be_edited(client, school, principal):
    created = client.post(
        f"/admin/sections/{school['section_id']}/students", headers=principal,
        json={"name": "Before Name", "roll_no": "23"},
    ).json()

    r = client.patch(
        f"/admin/students/{created['student_id']}", headers=principal,
        json={"name": "After Name"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["changed"] == ["name"]

    roster = client.get(f"/admin/sections/{school['section_id']}/students", headers=principal).json()
    row = next(s for s in roster["students"] if s["student_id"] == created["student_id"])
    assert row["name"] == "After Name"
    assert row["roll_no"] == "23"


def test_editing_to_a_roll_number_already_in_use_is_refused(client, school, principal):
    client.post(
        f"/admin/sections/{school['section_id']}/students", headers=principal,
        json={"name": "Held Roll", "roll_no": "24"},
    )
    created = client.post(
        f"/admin/sections/{school['section_id']}/students", headers=principal,
        json={"name": "Wants Roll 24", "roll_no": "25"},
    ).json()

    r = client.patch(
        f"/admin/students/{created['student_id']}", headers=principal, json={"roll_no": "24"},
    )
    assert r.status_code == 409
    assert "Held Roll" in r.json()["detail"]


def test_a_student_can_be_removed_and_disappears_from_the_roster(client, school, principal):
    created = client.post(
        f"/admin/sections/{school['section_id']}/students", headers=principal,
        json={"name": "Leaving Student", "roll_no": "26"},
    ).json()

    r = client.delete(f"/admin/students/{created['student_id']}", headers=principal)
    assert r.status_code == 204

    roster = client.get(f"/admin/sections/{school['section_id']}/students", headers=principal).json()
    assert all(s["student_id"] != created["student_id"] for s in roster["students"])


def test_removing_a_student_also_clears_their_test_session_and_result(client, school, principal):
    """The cascade this guards: a hard delete that stopped at StudentProfile would leave a
    TestSession/ProfileResult pointing at a student_id nothing resolves to any more."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import ProfileResult, StudentProfile, TestSession

    created = client.post(
        f"/admin/sections/{school['section_id']}/students", headers=principal,
        json={"name": "Tested Student", "roll_no": "27"},
    ).json()
    student_id = created["student_id"]

    db = SessionLocal()
    session = TestSession(school_id=school["school_id"], student_id=student_id, locale="en")
    db.add(session)
    db.flush()
    db.add(ProfileResult(session_id=session.id, holland_code="RIA"))
    db.commit()
    session_id = session.id
    db.close()

    r = client.delete(f"/admin/students/{student_id}", headers=principal)
    assert r.status_code == 204

    db = SessionLocal()
    assert db.get(StudentProfile, student_id) is None
    assert db.get(TestSession, session_id) is None
    assert db.scalar(
        select(ProfileResult).where(ProfileResult.session_id == session_id)
    ) is None
    db.close()


def test_a_student_in_another_school_is_not_reachable(client, school, principal):
    """A principal's own-school scoping (require_scanner) applies here exactly like it
    already does for scanning and marks."""
    from app.db import SessionLocal
    from app.models import School, Section, StudentProfile

    db = SessionLocal()
    other = School(name="Other School", api_key="other-school-key-roster-test", state="Tamil Nadu")
    db.add(other)
    db.flush()
    other_section = Section(school_id=other.id, grade=10, name="A")
    db.add(other_section)
    db.flush()
    other_student = StudentProfile(
        school_id=other.id, section_id=other_section.id, name="Not Yours", roll_no="1",
    )
    db.add(other_student)
    db.commit()
    other_student_id = other_student.id
    db.close()

    assert client.patch(
        f"/admin/students/{other_student_id}", headers=principal, json={"name": "Hijacked"},
    ).status_code == 404
    assert client.delete(
        f"/admin/students/{other_student_id}", headers=principal,
    ).status_code == 404


def test_an_admin_can_manage_the_roster_too(client, school):
    r = client.post(
        f"/admin/sections/{school['section_id']}/students", headers=_admin(school),
        json={"name": "Admin Added", "roll_no": "28"},
    )
    assert r.status_code == 201, r.text
