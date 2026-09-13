"""A hidden school's classes never appear on the public /t/classes directory."""

from __future__ import annotations

import pytest

from app.config import get_settings

PLATFORM_KEY = "directory-visibility-test-key"


@pytest.fixture(autouse=True)
def _enable_platform():
    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = PLATFORM_KEY
    yield
    settings.platform_admin_key = before


def hdr() -> dict:
    return {"X-Platform-Key": PLATFORM_KEY}


def test_a_new_school_starts_hidden_and_is_absent_from_the_directory(client):
    created = client.post(
        "/platform/schools", headers=hdr(),
        json={"name": "Hidden School", "sections": [{"grade": 9, "name": "B"}]},
    ).json()
    assert created["hidden_from_directory"] is True

    section_id = created["sections"][0]["id"]
    codes = [c["class_code"] for c in client.get("/t/classes").json()]
    assert section_id not in codes


def test_toggling_visibility_makes_it_appear_and_disappear(client):
    created = client.post(
        "/platform/schools", headers=hdr(),
        json={"name": "Toggle School", "sections": [{"grade": 9, "name": "C"}]},
    ).json()
    section_id = created["sections"][0]["id"]

    client.patch(
        f"/platform/schools/{created['id']}/directory-visibility",
        headers=hdr(), json={"hidden": False},
    )
    codes = [c["class_code"] for c in client.get("/t/classes").json()]
    assert section_id in codes

    client.patch(
        f"/platform/schools/{created['id']}/directory-visibility",
        headers=hdr(), json={"hidden": True},
    )
    codes = [c["class_code"] for c in client.get("/t/classes").json()]
    assert section_id not in codes


def test_toggle_requires_the_platform_key(client, school):
    created = client.post(
        "/platform/schools", headers=hdr(),
        json={"name": "Locked School", "sections": [{"grade": 9, "name": "D"}]},
    ).json()

    # a principal (school api_key) key
    r = client.patch(
        f"/platform/schools/{created['id']}/directory-visibility",
        headers={"X-Platform-Key": school["api_key"]}, json={"hidden": False},
    )
    assert r.status_code == 404

    r = client.patch(
        f"/platform/schools/{created['id']}/directory-visibility",
        headers={}, json={"hidden": False},
    )
    assert r.status_code == 404
