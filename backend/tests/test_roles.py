"""Three people use this system, and only one of them can change anything.

A student holds no key at all and reaches the test through a class link. A principal
holds a key that reads every result and every student's progress. An admin holds the key
that scans papers, enters marks and changes the roster. Before this split the principal
and the admin were the same credential, which meant an office laptop left signed in could
alter a mark.
"""

from __future__ import annotations

import pytest

PLATFORM = {"X-Platform-Key": "test-platform-key"}


@pytest.fixture
def principal(client, school):
    """A principal key, issued the way the operator console issues one."""
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


def test_a_principal_can_read_the_dashboard(client, school, principal):
    r = client.get("/admin/overview", headers=principal)
    assert r.status_code == 200
    assert r.json()["school"]["name"] == "Bharath International Sr. Sec."


def test_a_principal_is_told_what_their_key_may_do(client, school, principal):
    """The permissions come from the server. A screen that guessed them from the role
    name is one release away from hiding the wrong button."""
    body = client.get("/admin/me", headers=principal).json()
    assert body["role"] == "principal"
    assert body["can"] == {
        "read_results": True, "scan_papers": False, "enter_marks": False,
        "manage_roster": False, "manage_schools": False,
    }
    assert body["scope"] == "one_school"

    admin = client.get("/admin/me", headers=_admin(school)).json()
    assert admin["role"] == "admin"
    assert all(admin["can"].values())


def test_a_principal_cannot_create_a_paper_or_enter_a_mark(client, school, principal):
    created = client.post(
        "/assessments", headers=principal,
        json={"subject_code": "X.MATH", "title": "Not theirs", "total_marks": 5},
    )
    assert created.status_code == 403
    assert "admin key" in created.json()["detail"]


def test_a_principal_can_still_list_the_papers_they_cannot_change(client, school, principal):
    """Read and write are separated per route, not per screen: the progress a principal
    signs in for is exactly the same data the admin is producing."""
    assert client.get("/assessments", headers=principal).status_code == 200


def test_a_revoked_key_is_indistinguishable_from_one_that_never_existed(client, school):
    from datetime import UTC, datetime

    from app.db import SessionLocal
    from app.models import StaffKey

    db = SessionLocal()
    key = StaffKey(
        school_id=school["school_id"], api_key="revoked-key-xyz",
        role="principal", label="left the school",
        revoked_at=datetime.now(UTC),
    )
    db.add(key)
    db.commit()
    db.close()

    r = client.get("/admin/overview", headers={"X-API-Key": "revoked-key-xyz"})
    assert r.status_code == 404, "telling them it was once real is itself information"


def test_the_console_issues_a_principal_key_once_and_never_reads_it_back(client, school):
    from app.config import get_settings

    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = "test-platform-key"
    try:
        issued = client.post(
            f"/platform/schools/{school['school_id']}/keys",
            headers=PLATFORM, json={"role": "principal", "label": "Mrs Rani"},
        )
        assert issued.status_code == 201, issued.text
        secret = issued.json()["api_key"]

        listed = client.get(
            f"/platform/schools/{school['school_id']}/keys", headers=PLATFORM
        ).json()
        mine = next(k for k in listed if k["label"] == "Mrs Rani")
        assert "api_key" not in mine, "no route may read a key back"

        # It works, then it is revoked, then it does not.
        assert client.get("/admin/me", headers={"X-API-Key": secret}).status_code == 200
        client.post(
            f"/platform/schools/{school['school_id']}/keys/{mine['id']}/revoke",
            headers=PLATFORM,
        )
        assert client.get("/admin/me", headers={"X-API-Key": secret}).status_code == 404
    finally:
        settings.platform_admin_key = before


def test_an_unknown_role_is_refused_rather_than_stored(client, school):
    from app.config import get_settings

    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = "test-platform-key"
    try:
        r = client.post(
            f"/platform/schools/{school['school_id']}/keys",
            headers=PLATFORM, json={"role": "superuser", "label": "no"},
        )
        assert r.status_code == 422
    finally:
        settings.platform_admin_key = before


@pytest.fixture
def platform_admin(client):
    """An admin key: no school, every school."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import StaffKey

    db = SessionLocal()
    if db.scalar(select(StaffKey).where(StaffKey.api_key == "admin-key-all")) is None:
        db.add(StaffKey(school_id=None, api_key="admin-key-all", role="admin", label="Yaadhum"))
        db.commit()
    db.close()
    return {"X-API-Key": "admin-key-all"}


@pytest.fixture
def second_school(client):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import School, Section

    db = SessionLocal()
    s = db.scalar(select(School).where(School.name == "Second School"))
    if s is None:
        s = School(name="Second School", api_key="second-school-key", state="Tamil Nadu")
        db.add(s)
        db.flush()
        db.add(Section(school_id=s.id, grade=10, name="A"))
        db.commit()
    out = s.id
    db.close()
    return out


def test_an_admin_can_act_on_any_school_by_naming_it(
    client, school, second_school, platform_admin
):
    first = client.get(
        "/admin/me", headers={**platform_admin, "X-School-Id": school["school_id"]}
    ).json()
    second = client.get(
        "/admin/me", headers={**platform_admin, "X-School-Id": second_school}
    ).json()

    assert first["name"] == "Bharath International Sr. Sec."
    assert second["name"] == "Second School"
    assert first["scope"] == second["scope"] == "all_schools"
    assert first["can"]["manage_schools"] is True


def test_an_admin_who_names_no_school_is_asked_which_one(client, platform_admin):
    """Guessing one would be the worst outcome: every answer would look correct, for the
    wrong school."""
    r = client.get("/admin/me", headers=platform_admin)
    assert r.status_code == 400
    assert "X-School-Id" in r.json()["detail"]


def test_a_principal_cannot_reach_another_school_by_naming_it(
    client, school, second_school, principal
):
    """Not by being compared and refused -- by there being no code path that reads a
    school from a principal's request at all."""
    body = client.get(
        "/admin/me", headers={**principal, "X-School-Id": second_school}
    ).json()
    assert body["school_id"] == school["school_id"]
    assert body["name"] == "Bharath International Sr. Sec."


def test_a_principal_cannot_create_a_school(client, principal):
    r = client.post(
        "/platform/schools", headers=principal,
        json={"name": "Their Own School", "sections": [{"grade": 10, "name": "A"}]},
    )
    assert r.status_code == 404, "the console must not even acknowledge itself to them"


def test_a_school_bound_key_cannot_create_a_second_school(client, school):
    """The school's own key is an admin for that school. It runs the school; it does not
    get to make another one, so one leaked school credential stays one school."""
    r = client.post(
        "/platform/schools", headers=_admin(school),
        json={"name": "Sneaky School", "sections": [{"grade": 10, "name": "A"}]},
    )
    assert r.status_code == 404


def test_an_admin_key_creates_schools_without_the_operator_key(client, platform_admin):
    from app.config import get_settings

    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = None      # the operator key is not even configured
    try:
        r = client.post(
            "/platform/schools", headers=platform_admin,
            json={"name": "Third School", "sections": [{"grade": 10, "name": "B"}]},
        )
        assert r.status_code == 201, r.text
        assert r.json()["name"] == "Third School"
    finally:
        settings.platform_admin_key = before
