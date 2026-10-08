"""A principal sets their own key (password); the old one stops, the new one signs in, and the
operator console shows it."""

from __future__ import annotations

import uuid

import pytest

KEY = "pw-platform-key"
HEAD = {"X-Platform-Key": KEY}


@pytest.fixture(autouse=True)
def _operator():
    from app.config import get_settings

    s = get_settings()
    before = s.platform_admin_key
    s.platform_admin_key = KEY
    yield
    s.platform_admin_key = before


def _principal(client, role="principal"):
    sid = client.post("/platform/schools", headers=HEAD, json={"name": f"Pw School {uuid.uuid4().hex[:6]}"}).json()["id"]
    k = client.post(f"/platform/schools/{sid}/keys", headers=HEAD, json={"role": role, "label": "Head"}).json()
    return sid, k


def _change(client, key, pw):
    return client.post("/admin/me/password", headers={"X-API-Key": key}, json={"new_password": pw})


def test_new_password_replaces_the_key_and_the_operator_sees_it(client):
    sid, k = _principal(client)
    pw = f"Chosen{uuid.uuid4().hex[:8]}9"
    r = _change(client, k["api_key"], pw)
    assert r.status_code == 200, r.text
    assert client.get("/admin/me", headers={"X-API-Key": k["api_key"]}).status_code == 404  # old key is dead
    assert client.get("/admin/me", headers={"X-API-Key": pw}).status_code == 200
    listed = client.get(f"/platform/schools/{sid}/keys", headers=HEAD).json()
    row = next(x for x in listed if x["id"] == k["id"])
    assert row["api_key"] == pw and row["credential_changed_at"]


@pytest.mark.parametrize("bad", ["short1", "alllettersonly", "1234567890123", "has space 1234567", "Password123", "கடவுச்சொல்12345"])
def test_weak_or_malformed_passwords_are_refused(client, bad):
    _, k = _principal(client)
    assert _change(client, k["api_key"], bad).status_code == 422
    assert client.get("/admin/me", headers={"X-API-Key": k["api_key"]}).status_code == 200  # unchanged


def test_a_password_in_use_elsewhere_is_refused_and_teachers_cannot(client):
    _, a = _principal(client)
    _, b = _principal(client)
    assert _change(client, b["api_key"], a["api_key"]).status_code == 409
    _, t = _principal(client, role="teacher")
    assert _change(client, t["api_key"], f"Teach{uuid.uuid4().hex[:8]}7").status_code == 403
