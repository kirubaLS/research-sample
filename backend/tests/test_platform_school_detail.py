"""The 6-tab ops console school detail screen: school details, principal/teacher key
edits, teacher assignments, student roster and the activity trail behind them."""

from __future__ import annotations

import pytest

from app.config import get_settings

PLATFORM_KEY = "platform-test-key-detail"


@pytest.fixture(autouse=True)
def _enable_platform():
    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = PLATFORM_KEY
    yield
    settings.platform_admin_key = before


def hdr(key: str = PLATFORM_KEY) -> dict:
    return {"X-Platform-Key": key}


def _make_school(client, name="Detail Test School"):
    return client.post(
        "/platform/schools",
        headers=hdr(),
        json={"name": name, "sections": [{"grade": 10, "name": "A"}, {"grade": 10, "name": "B"}]},
    ).json()


def test_get_single_school_returns_full_detail(client):
    school = _make_school(client, "Get One School")
    r = client.get(f"/platform/schools/{school['id']}", headers=hdr())
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Get One School"
    assert body["code"] is None
    assert "api_key" not in body


def test_get_single_school_404_for_unknown_id(client):
    r = client.get("/platform/schools/does-not-exist", headers=hdr())
    assert r.status_code == 404


def test_patch_school_details_updates_only_given_fields(client):
    school = _make_school(client, "Patch School Details")
    r = client.patch(
        f"/platform/schools/{school['id']}", headers=hdr(),
        json={"code": "SCH-001", "city": "Chennai", "address": "12 MG Road",
              "academic_year": "2025-26"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "SCH-001"
    assert body["city"] == "Chennai"
    assert body["address"] == "12 MG Road"
    assert body["academic_year"] == "2025-26"
    # untouched fields keep their prior value
    assert body["name"] == "Patch School Details"
    assert body["board"] == "CBSE"

    again = client.get(f"/platform/schools/{school['id']}", headers=hdr()).json()
    assert again["code"] == "SCH-001"


def test_patch_school_bad_training_consent_rejected(client):
    school = _make_school(client, "Bad Consent School")
    r = client.patch(
        f"/platform/schools/{school['id']}", headers=hdr(),
        json={"training_consent": "not-a-real-value"},
    )
    assert r.status_code == 422


def test_patch_staff_key_contact_details(client):
    school = _make_school(client, "Key Contact School")
    key = client.post(
        f"/platform/schools/{school['id']}/keys", headers=hdr(),
        json={"role": "principal", "label": "Mrs. Iyer"},
    ).json()
    r = client.patch(
        f"/platform/schools/{school['id']}/keys/{key['id']}", headers=hdr(),
        json={"name": "Kavitha Iyer", "email": "kavitha@example.com", "phone": "9876500000"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Kavitha Iyer"
    assert body["email"] == "kavitha@example.com"
    assert body["phone"] == "9876500000"
    assert body["api_key"] == key["api_key"]


def test_patch_staff_key_wrong_school_is_404(client):
    school_a = _make_school(client, "Wrong School A")
    school_b = _make_school(client, "Wrong School B")
    key = client.post(
        f"/platform/schools/{school_a['id']}/keys", headers=hdr(),
        json={"role": "principal", "label": "A's principal"},
    ).json()
    r = client.patch(
        f"/platform/schools/{school_b['id']}/keys/{key['id']}", headers=hdr(),
        json={"name": "Someone Else"},
    )
    assert r.status_code == 404


def test_teacher_assignments_round_trip(client):
    school = _make_school(client, "Assignments School")
    section_a = school["sections"][0]["id"]
    section_b = school["sections"][1]["id"]
    key = client.post(
        f"/platform/schools/{school['id']}/keys", headers=hdr(),
        json={"role": "teacher", "label": "Mr. Raman"},
    ).json()

    empty = client.get(
        f"/platform/schools/{school['id']}/keys/{key['id']}/assignments", headers=hdr()
    )
    assert empty.status_code == 200
    assert empty.json() == []

    r = client.patch(
        f"/platform/schools/{school['id']}/keys/{key['id']}/assignments", headers=hdr(),
        json={"assignments": [
            {"type": "class", "section_id": section_a},
            {"type": "subject", "section_id": section_b, "subject_code": "MATH"},
        ]},
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2

    again = client.get(
        f"/platform/schools/{school['id']}/keys/{key['id']}/assignments", headers=hdr()
    ).json()
    assert len(again) == 2

    # replacing with a smaller set drops what isn't listed anymore
    replaced = client.patch(
        f"/platform/schools/{school['id']}/keys/{key['id']}/assignments", headers=hdr(),
        json={"assignments": [{"type": "class", "section_id": section_a}]},
    ).json()
    assert len(replaced) == 1


def test_teacher_assignments_reject_section_from_another_school(client):
    school_a = _make_school(client, "Assign Cross A")
    school_b = _make_school(client, "Assign Cross B")
    other_section = school_b["sections"][0]["id"]
    key = client.post(
        f"/platform/schools/{school_a['id']}/keys", headers=hdr(),
        json={"role": "teacher", "label": "Cross-school teacher"},
    ).json()
    r = client.patch(
        f"/platform/schools/{school_a['id']}/keys/{key['id']}/assignments", headers=hdr(),
        json={"assignments": [{"type": "class", "section_id": other_section}]},
    )
    assert r.status_code == 422


def test_bulk_add_students_and_list_roster(client):
    school = _make_school(client, "Bulk Students School")
    section_id = school["sections"][0]["id"]
    r = client.post(
        f"/platform/schools/{school['id']}/students/bulk", headers=hdr(),
        json={"students": [
            {"name": "Asha Kumar", "roll_no": "1", "section_id": section_id,
             "parent_name": "R. Kumar", "parent_whatsapp": "9000000001"},
            {"name": "Bala Singh", "roll_no": "2", "section_id": section_id, "age": 15,
             "gender": "M"},
        ]},
    )
    assert r.status_code == 201
    created = r.json()
    assert len(created) == 2
    assert created[0]["parent_name"] == "R. Kumar"

    roster = client.get(f"/platform/schools/{school['id']}/students", headers=hdr())
    assert roster.status_code == 200
    names = {row["name"] for row in roster.json()}
    assert {"Asha Kumar", "Bala Singh"} <= names
    row = next(row for row in roster.json() if row["name"] == "Asha Kumar")
    assert row["section_label"] == "Class 10-A"


def test_bulk_add_students_rejects_unknown_section(client):
    school = _make_school(client, "Bad Section School")
    r = client.post(
        f"/platform/schools/{school['id']}/students/bulk", headers=hdr(),
        json={"students": [{"name": "X", "roll_no": "9", "section_id": "nope"}]},
    )
    assert r.status_code == 422


def test_activity_log_captures_school_lifecycle(client):
    school = _make_school(client, "Activity School")
    section_id = school["sections"][0]["id"]

    client.patch(f"/platform/schools/{school['id']}", headers=hdr(), json={"city": "Madurai"})
    key = client.post(
        f"/platform/schools/{school['id']}/keys", headers=hdr(),
        json={"role": "principal", "label": "P1"},
    ).json()
    client.post(
        f"/platform/schools/{school['id']}/keys/{key['id']}/revoke", headers=hdr()
    )
    client.post(
        f"/platform/schools/{school['id']}/students/bulk", headers=hdr(),
        json={"students": [{"name": "Z", "roll_no": "5", "section_id": section_id}]},
    )

    r = client.get(f"/platform/schools/{school['id']}/activity", headers=hdr())
    assert r.status_code == 200
    actions = [row["action"] for row in r.json()]
    assert "school_created" in actions
    assert "school_edited" in actions
    assert "key_issued" in actions
    assert "key_revoked" in actions
    assert "students_added" in actions
    # newest first
    timestamps = [row["created_at"] for row in r.json()]
    assert timestamps == sorted(timestamps, reverse=True)


def test_activity_log_is_scoped_per_school(client):
    school_a = _make_school(client, "Activity Scope A")
    school_b = _make_school(client, "Activity Scope B")
    r = client.get(f"/platform/schools/{school_a['id']}/activity", headers=hdr())
    ids = {row["id"] for row in r.json()}
    r_b = client.get(f"/platform/schools/{school_b['id']}/activity", headers=hdr())
    ids_b = {row["id"] for row in r_b.json()}
    assert ids.isdisjoint(ids_b)


def test_new_endpoints_are_refused_without_platform_credentials(client):
    school = _make_school(client, "Auth Denial School")
    key = client.post(
        f"/platform/schools/{school['id']}/keys", headers=hdr(),
        json={"role": "principal", "label": "P"},
    ).json()

    denial_calls = [
        ("GET", f"/platform/schools/{school['id']}"),
        ("PATCH", f"/platform/schools/{school['id']}"),
        ("PATCH", f"/platform/schools/{school['id']}/keys/{key['id']}"),
        ("GET", f"/platform/schools/{school['id']}/keys/{key['id']}/assignments"),
        ("PATCH", f"/platform/schools/{school['id']}/keys/{key['id']}/assignments"),
        ("GET", f"/platform/schools/{school['id']}/students"),
        ("POST", f"/platform/schools/{school['id']}/students/bulk"),
        ("GET", f"/platform/schools/{school['id']}/activity"),
    ]
    for method, path in denial_calls:
        # no credentials at all
        r = client.request(method, path, json={} if method in ("PATCH", "POST") else None)
        assert r.status_code == 404, (method, path, r.status_code)
        # a school's own principal key must not open the operator surface either
        r2 = client.request(
            method, path, headers={"X-API-Key": key["api_key"]},
            json={} if method in ("PATCH", "POST") else None,
        )
        assert r2.status_code in (401, 403, 404, 422), (method, path, r2.status_code)
