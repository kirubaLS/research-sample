"""Teacher role: scoped by class/subject assignment, never wider."""

from __future__ import annotations


def _auth(school: dict) -> dict:
    return {"X-API-Key": school["api_key"]}


def test_admin_me_returns_a_teacher_shape(client, school):
    created = client.post(
        "/admin/teachers", headers=_auth(school),
        json={
            "label": "Ms. Rao",
            "assignments": [
                {"type": "class", "section_id": school["section_id"]},
            ],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["role"] == "teacher"
    assert "api_key" in body
    key = body["api_key"]

    me = client.get("/admin/me", headers={"X-API-Key": key}).json()
    assert me["role"] == "teacher"
    assert me["assignments"] == [
        {
            "type": "class",
            "section_id": school["section_id"],
            "section_label": me["assignments"][0]["section_label"],
            "subject_code": None,
        }
    ]
    assert me["assignments"][0]["section_label"].startswith("Class ")


def test_principal_and_admin_me_shape_is_unchanged(client, school):
    """Adding the teacher role must not alter what a principal/admin key gets back."""
    me = client.get("/admin/me", headers=_auth(school)).json()
    assert "assignments" not in me
    assert me["role"] == "admin"
    assert set(me["can"]) == {
        "read_results", "scan_papers", "enter_marks", "manage_roster", "manage_schools",
    }


def test_class_teacher_can_read_but_not_enter_marks_outside_their_subject(client, school):
    created = client.post(
        "/admin/teachers", headers=_auth(school),
        json={"label": "Class teacher", "assignments": [
            {"type": "class", "section_id": school["section_id"]},
        ]},
    ).json()
    key = created["api_key"]
    teacher_headers = {"X-API-Key": key}

    # can read the roster for their own class
    r = client.get(f"/admin/teacher/sections/{school['section_id']}/students", headers=teacher_headers)
    assert r.status_code == 200

    # cannot enter marks for any subject -- a class assignment alone never grants that
    assessment = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Unit Test", "total_marks": 10},
    ).json()
    upload = client.post(
        f"/assessments/{assessment['assessment_id']}/sections/{school['section_id']}/gridsheet",
        headers=teacher_headers,
        files={"files": ("sheet.png", b"not-a-real-image", "image/png")},
    )
    assert upload.status_code == 404


def test_subject_teacher_can_enter_marks_for_their_subject_but_not_read_generically(client, school):
    assessment = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Subject Teacher Unit Test", "total_marks": 10},
    ).json()
    aid = assessment["assessment_id"]
    client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [{
            "section": "A", "question_no": "1", "max_marks": 10, "mark_step": 1,
            "question_type": "long", "board_unit": "X.MATH.U.ALGEBRA",
            "concept_family": "X.MATH.CF.VOLUME", "concept_variant": "v1",
        }]},
    )

    created = client.post(
        "/admin/teachers", headers=_auth(school),
        json={"label": "Subject teacher", "assignments": [
            {"type": "subject", "section_id": school["section_id"], "subject_code": "X.MATH"},
        ]},
    ).json()
    teacher_headers = {"X-API-Key": created["api_key"]}

    upload = client.post(
        f"/assessments/{aid}/sections/{school['section_id']}/gridsheet",
        headers=teacher_headers,
        files={"files": ("sheet.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")},
    )
    assert upload.status_code == 202

    # a subject assignment does not open the generic (unscoped) reader surface
    r = client.get("/reports/paper/" + aid, headers=teacher_headers)
    assert r.status_code == 403


def test_revoked_teacher_key_is_rejected_like_a_nonexistent_one(client, school):
    created = client.post(
        "/admin/teachers", headers=_auth(school),
        json={"label": "Temp", "assignments": []},
    ).json()
    key = created["api_key"]
    assert client.get("/admin/me", headers={"X-API-Key": key}).status_code == 200

    revoke = client.post(f"/admin/teachers/{created['id']}/revoke", headers=_auth(school))
    assert revoke.status_code == 200

    r = client.get("/admin/me", headers={"X-API-Key": key})
    assert r.status_code == 404


def test_teacher_key_cannot_manage_roster_or_keys(client, school):
    created = client.post(
        "/admin/teachers", headers=_auth(school),
        json={"label": "Ms. Rao", "assignments": []},
    ).json()
    teacher_headers = {"X-API-Key": created["api_key"]}

    # require_admin-gated: creating another teacher key
    r = client.post(
        "/admin/teachers", headers=teacher_headers,
        json={"label": "Another", "assignments": []},
    )
    assert r.status_code == 403

    # require_reader-gated generic surface: refused, not silently scoped
    r = client.get(f"/admin/sections/{school['section_id']}/students", headers=teacher_headers)
    assert r.status_code == 403


def test_renaming_a_teacher_changes_only_the_label(client, school):
    created = client.post(
        "/admin/teachers", headers=_auth(school),
        json={
            "label": "Ms. Rao",
            "assignments": [{"type": "class", "section_id": school["section_id"]}],
        },
    ).json()
    original_key = created["api_key"]

    r = client.patch(
        f"/admin/teachers/{created['id']}", headers=_auth(school), json={"label": "Ms. R. Rao"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] == "Ms. R. Rao"
    assert "api_key" not in body
    assert len(body["assignments"]) == 1

    # the old key still works -- rename never touches the credential
    assert client.get("/admin/me", headers={"X-API-Key": original_key}).status_code == 200


def test_renaming_a_teacher_refuses_an_empty_label(client, school):
    created = client.post(
        "/admin/teachers", headers=_auth(school), json={"label": "Ms. Rao", "assignments": []},
    ).json()
    r = client.patch(
        f"/admin/teachers/{created['id']}", headers=_auth(school), json={"label": "   "},
    )
    assert r.status_code == 422


def test_reissuing_a_teacher_key_kills_the_old_one_and_keeps_assignments(client, school):
    created = client.post(
        "/admin/teachers", headers=_auth(school),
        json={
            "label": "Ms. Rao",
            "assignments": [{"type": "class", "section_id": school["section_id"]}],
        },
    ).json()
    old_key = created["api_key"]
    assert client.get("/admin/me", headers={"X-API-Key": old_key}).status_code == 200

    r = client.post(f"/admin/teachers/{created['id']}/reissue", headers=_auth(school))
    assert r.status_code == 200, r.text
    body = r.json()
    new_key = body["api_key"]
    assert new_key != old_key
    assert len(body["assignments"]) == 1

    # the old key is dead, the new one works, and it carries the same assignments
    assert client.get("/admin/me", headers={"X-API-Key": old_key}).status_code == 404
    me = client.get("/admin/me", headers={"X-API-Key": new_key})
    assert me.status_code == 200
    assert len(me.json()["assignments"]) == 1


def test_a_revoked_teacher_key_cannot_be_reissued(client, school):
    created = client.post(
        "/admin/teachers", headers=_auth(school), json={"label": "Temp", "assignments": []},
    ).json()
    client.post(f"/admin/teachers/{created['id']}/revoke", headers=_auth(school))

    r = client.post(f"/admin/teachers/{created['id']}/reissue", headers=_auth(school))
    assert r.status_code == 409
