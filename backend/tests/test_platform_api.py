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


def test_rotating_replaces_the_key_immediately(client):
    created = client.post(
        "/platform/schools",
        headers=hdr(),
        json={"name": "Rotation Test School", "sections": [{"grade": 10, "name": "A"}]},
    ).json()
    old = created["api_key"]
    section_id = created["sections"][0]["id"]

    rotated = client.post(f"/platform/schools/{created['id']}/rotate-key", headers=hdr())
    assert rotated.status_code == 200
    new = rotated.json()["api_key"]
    assert new != old

    assert client.get("/admin/me", headers={"X-API-Key": old}).status_code == 404
    assert client.get("/admin/me", headers={"X-API-Key": new}).status_code == 200
    # rotating a credential must not disturb a class link already handed out
    codes = [c["class_code"] for c in client.get("/t/classes").json()]
    assert section_id in codes


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
