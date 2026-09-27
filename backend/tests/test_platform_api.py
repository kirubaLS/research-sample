"""The operator surface, and the boundary that matters most: a school key is not it."""

from __future__ import annotations

import pytest

from app.config import get_settings

PLATFORM_KEY = "platform-test-key-abc"


@pytest.fixture(autouse=True)
def _enable_platform():
    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = PLATFORM_KEY
    yield
    settings.platform_admin_key = before


def hdr(key: str = PLATFORM_KEY) -> dict:
    return {"X-Platform-Key": key}


def test_create_school_returns_the_key_and_the_class_links(client):
    r = client.post(
        "/platform/schools",
        headers=hdr(),
        json={
            "name": "Green Valley Matric",
            "state": "Tamil Nadu",
            "sections": [{"grade": 10, "name": "A"}, {"grade": 10, "name": "b"}],
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["api_key"]
    # 'b' and 'B' are the same class -- storing both would split a roster in two
    labels = sorted(s["label"] for s in body["sections"])
    assert labels == ["Class 10-A", "Class 10-B"]
    assert all(s["student_path"] == f"/t/{s['id']}" for s in body["sections"])

    # the key the console just showed actually signs the principal in
    me = client.get("/admin/me", headers={"X-API-Key": body["api_key"]})
    assert me.status_code == 200
    assert me.json()["name"] == "Green Valley Matric"


def test_listing_schools_never_returns_a_key(client):
    client.post(
        "/platform/schools",
        headers=hdr(),
        json={"name": "Listing Test School", "sections": [{"grade": 10, "name": "A"}]},
    )
    rows = client.get("/platform/schools", headers=hdr()).json()
    assert rows, "the school just created should be listed"
    # a console left open in a staffroom must not be a key on screen
    assert all("api_key" not in row for row in rows)


def test_operator_can_view_a_schools_principal_and_admin_keys(client):
    school = client.post(
        "/platform/schools",
        headers=hdr(),
        json={"name": "Key Viewing School", "sections": [{"grade": 10, "name": "A"}]},
    ).json()
    issued = client.post(
        f"/platform/schools/{school['id']}/keys",
        headers=hdr(), json={"role": "principal", "label": "Mrs. Iyer"},
    ).json()

    rows = client.get(f"/platform/schools/{school['id']}/keys", headers=hdr()).json()
    assert len(rows) == 1
    assert rows[0]["id"] == issued["id"]
    # the whole point: the operator can read the key back after the one-time reveal is gone
    assert rows[0]["api_key"] == issued["api_key"]
    assert rows[0]["revoked_at"] is None

    client.post(f"/platform/schools/{school['id']}/keys/{issued['id']}/revoke", headers=hdr())
    revoked = client.get(f"/platform/schools/{school['id']}/keys", headers=hdr()).json()
    # a revoked key is still shown, marked revoked, not hidden -- the operator needs the history
    assert revoked[0]["api_key"] == issued["api_key"]
    assert revoked[0]["revoked_at"] is not None


def test_a_school_cannot_see_another_schools_keys_through_this_route(client):
    school_a = client.post(
        "/platform/schools", headers=hdr(),
        json={"name": "Keys School A", "sections": [{"grade": 10, "name": "A"}]},
    ).json()
    school_b = client.post(
        "/platform/schools", headers=hdr(),
        json={"name": "Keys School B", "sections": [{"grade": 10, "name": "A"}]},
    ).json()
    key_a = client.post(
        f"/platform/schools/{school_a['id']}/keys",
        headers=hdr(), json={"role": "principal", "label": "A's principal"},
    ).json()

    rows = client.get(f"/platform/schools/{school_b['id']}/keys", headers=hdr()).json()
    assert all(r["id"] != key_a["id"] for r in rows)


def test_rotating_replaces_the_key_immediately(client):
    created = client.post(
        "/platform/schools",
        headers=hdr(),
        json={"name": "Rotation Test School", "sections": [{"grade": 10, "name": "A"}]},
    ).json()
    old = created["api_key"]
    section_id = created["sections"][0]["id"]
    # a school is hidden from the public directory until an operator opts it in
    client.patch(
        f"/platform/schools/{created['id']}/directory-visibility",
        headers=hdr(), json={"hidden": False},
    )

    rotated = client.post(f"/platform/schools/{created['id']}/rotate-key", headers=hdr())
    assert rotated.status_code == 200
    new = rotated.json()["api_key"]
    assert new != old

    assert client.get("/admin/me", headers={"X-API-Key": old}).status_code == 404
    assert client.get("/admin/me", headers={"X-API-Key": new}).status_code == 200
    # rotating a credential must not disturb a class link already handed out
    codes = [c["class_code"] for c in client.get("/t/classes").json()]
    assert section_id in codes


def test_rotating_a_single_staff_key_replaces_it_without_touching_others(client):
    school = client.post(
        "/platform/schools", headers=hdr(),
        json={"name": "Staff Key Rotation School", "sections": [{"grade": 10, "name": "A"}]},
    ).json()
    principal = client.post(
        f"/platform/schools/{school['id']}/keys",
        headers=hdr(), json={"role": "principal", "label": "Mrs. Iyer"},
    ).json()
    teacher = client.post(
        f"/platform/schools/{school['id']}/keys",
        headers=hdr(), json={"role": "teacher", "label": "Mr. Rao"},
    ).json()
    old_principal_key = principal["api_key"]
    old_teacher_key = teacher["api_key"]

    rotated = client.post(
        f"/platform/schools/{school['id']}/keys/{principal['id']}/rotate", headers=hdr()
    )
    assert rotated.status_code == 200
    body = rotated.json()
    assert body["id"] == principal["id"]
    assert body["api_key"] != old_principal_key
    assert body["api_key_notice"]

    # old principal key is dead, new one works
    assert client.get("/admin/me", headers={"X-API-Key": old_principal_key}).status_code == 404
    assert client.get("/admin/me", headers={"X-API-Key": body["api_key"]}).status_code == 200
    # the teacher key is untouched
    rows = client.get(f"/platform/schools/{school['id']}/keys", headers=hdr()).json()
    teacher_row = next(r for r in rows if r["id"] == teacher["id"])
    assert teacher_row["api_key"] == old_teacher_key


def test_rotating_a_revoked_staff_key_is_rejected(client):
    school = client.post(
        "/platform/schools", headers=hdr(),
        json={"name": "Revoked Rotation School", "sections": [{"grade": 10, "name": "A"}]},
    ).json()
    teacher = client.post(
        f"/platform/schools/{school['id']}/keys",
        headers=hdr(), json={"role": "teacher", "label": "Mr. Rao"},
    ).json()
    client.post(f"/platform/schools/{school['id']}/keys/{teacher['id']}/revoke", headers=hdr())
    r = client.post(f"/platform/schools/{school['id']}/keys/{teacher['id']}/rotate", headers=hdr())
    assert r.status_code == 409


def test_rotating_a_staff_key_from_another_school_is_rejected(client):
    school_a = client.post(
        "/platform/schools", headers=hdr(),
        json={"name": "Rotate Cross A", "sections": [{"grade": 10, "name": "A"}]},
    ).json()
    school_b = client.post(
        "/platform/schools", headers=hdr(),
        json={"name": "Rotate Cross B", "sections": [{"grade": 10, "name": "A"}]},
    ).json()
    key_a = client.post(
        f"/platform/schools/{school_a['id']}/keys",
        headers=hdr(), json={"role": "principal", "label": "A's principal"},
    ).json()
    r = client.post(f"/platform/schools/{school_b['id']}/keys/{key_a['id']}/rotate", headers=hdr())
    assert r.status_code == 404


def test_onboarding_checklist_reflects_only_real_signals(client):
    school = client.post(
        "/platform/schools", headers=hdr(),
        json={"name": "Checklist School", "sections": [{"grade": 10, "name": "A"}]},
    ).json()
    section_id = school["sections"][0]["id"]

    checklist = client.get(
        f"/platform/schools/{school['id']}/onboarding-checklist", headers=hdr()
    ).json()
    steps = {s["key"]: s for s in checklist["steps"]}
    assert steps["school_created"]["done"] is True
    assert steps["school_created"]["at"] is not None
    # nothing else has happened yet
    assert steps["principal_invited"]["done"] is False
    assert steps["principal_invited"]["at"] is None
    assert steps["students_onboarded"]["done"] is False
    assert checklist["done_count"] == 1
    assert checklist["total_steps"] == 8

    # add a student via the roster (bulk-add), NOT the onboarding wizard
    client.post(
        f"/platform/schools/{school['id']}/students/bulk",
        headers=hdr(), json={"students": [{"name": "Asha", "roll_no": "1", "section_id": section_id}]},
    )
    checklist2 = client.get(
        f"/platform/schools/{school['id']}/onboarding-checklist", headers=hdr()
    ).json()
    steps2 = {s["key"]: s for s in checklist2["steps"]}
    # a roster add is not "onboarded" -- no real wizard fields were ever set
    assert steps2["students_onboarded"]["done"] is False
    assert checklist2["students_enrolled"] == 1
    assert checklist2["students_onboarded_count"] == 0

    # issue a principal key -- that step should now be real and dated
    client.post(
        f"/platform/schools/{school['id']}/keys",
        headers=hdr(), json={"role": "principal", "label": "Mrs. Iyer"},
    )
    checklist3 = client.get(
        f"/platform/schools/{school['id']}/onboarding-checklist", headers=hdr()
    ).json()
    steps3 = {s["key"]: s for s in checklist3["steps"]}
    assert steps3["principal_invited"]["done"] is True
    assert steps3["principal_invited"]["at"] is not None


def test_a_school_key_cannot_reach_the_operator_surface(client, school):
    """The whole point of a second credential."""
    for headers in (
        {"X-Platform-Key": school["api_key"]},   # a principal's key, offered as the operator's
        {"X-API-Key": school["api_key"]},        # or on its own header
        {},
    ):
        r = client.get("/platform/schools", headers=headers)
        assert r.status_code in (401, 403, 404, 422), headers


def test_the_surface_is_off_when_no_key_is_configured(client):
    """A deployment that never sets the secret must fail closed, not fall back."""
    settings = get_settings()
    settings.platform_admin_key = None
    r = client.get("/platform/schools", headers=hdr())
    assert r.status_code == 404


def test_duplicate_school_and_duplicate_class_are_refused(client):
    body = {"name": "Duplicate Test School", "sections": [{"grade": 10, "name": "A"}]}
    first = client.post("/platform/schools", headers=hdr(), json=body)
    assert first.status_code == 201
    assert client.post("/platform/schools", headers=hdr(), json=body).status_code == 409

    school_id = first.json()["id"]
    add = client.post(
        f"/platform/schools/{school_id}/sections", headers=hdr(), json={"grade": 10, "name": "B"}
    )
    assert add.status_code == 201
    assert add.json()["label"] == "Class 10-B"
    again = client.post(
        f"/platform/schools/{school_id}/sections", headers=hdr(), json={"grade": 10, "name": "b"}
    )
    assert again.status_code == 409
