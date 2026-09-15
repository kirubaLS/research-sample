"""/platform/overview: the operator's cross-school aggregate, one screen instead of
switching between schools one at a time."""

from __future__ import annotations

import pytest

from app.config import get_settings

PLATFORM_KEY = "platform-test-key-overview"


@pytest.fixture(autouse=True)
def _enable_platform():
    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = PLATFORM_KEY
    yield
    settings.platform_admin_key = before


def hdr(key: str = PLATFORM_KEY) -> dict:
    return {"X-Platform-Key": key}


def test_overview_sums_students_and_papers_across_every_school(client):
    a = client.post(
        "/platform/schools", headers=hdr(),
        json={"name": "Overview School A", "sections": [{"grade": 10, "name": "A"}]},
    ).json()
    b = client.post(
        "/platform/schools", headers=hdr(),
        json={"name": "Overview School B", "sections": [{"grade": 10, "name": "A"}]},
    ).json()

    client.post(
        "/assessments", headers={"X-API-Key": a["api_key"]},
        json={"subject_code": "X.MATH", "title": "A's paper", "total_marks": 10},
    )

    r = client.get("/platform/overview", headers=hdr())
    assert r.status_code == 200
    body = r.json()

    rows = {row["id"]: row for row in body["schools"]}
    assert rows[a["id"]]["papers"] == 1
    assert rows[b["id"]]["papers"] == 0
    # every school starts with exactly one working admin credential: its own api_key
    assert rows[a["id"]]["admin_keys"] == 1
    assert rows[b["id"]]["admin_keys"] == 1

    assert body["totals"]["schools"] >= 2
    assert body["totals"]["papers"] >= 1


def test_a_revoked_key_does_not_count_as_an_active_principal(client):
    school = client.post(
        "/platform/schools", headers=hdr(),
        json={"name": "Overview School C", "sections": [{"grade": 10, "name": "A"}]},
    ).json()
    issued = client.post(
        f"/platform/schools/{school['id']}/keys", headers=hdr(),
        json={"role": "principal", "label": "Mr Iyer"},
    ).json()

    before = client.get("/platform/overview", headers=hdr()).json()
    before_row = next(r for r in before["schools"] if r["id"] == school["id"])
    assert before_row["principal_keys"] == 1

    client.post(f"/platform/schools/{school['id']}/keys/{issued['id']}/revoke", headers=hdr())

    after = client.get("/platform/overview", headers=hdr()).json()
    after_row = next(r for r in after["schools"] if r["id"] == school["id"])
    assert after_row["principal_keys"] == 0


def test_a_school_key_cannot_reach_the_overview(client, school):
    r = client.get("/platform/overview", headers={"X-API-Key": school["api_key"]})
    assert r.status_code == 404
