"""Sharing an issued report with the student it belongs to: real PIN issuance, a real
student session, and a student portal that reads only what was actually shared."""

from __future__ import annotations


def _auth(school: dict) -> dict:
    return {"X-API-Key": school["api_key"]}


def _make_student_and_report(school, *, roll_no="7", name="Asha"):
    from app.db import SessionLocal
    from app.models import StudentProfile, StudentReport

    db = SessionLocal()
    student = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name=name, roll_no=roll_no,
    )
    db.add(student)
    db.flush()
    report = StudentReport(
        school_id=school["school_id"], assessment_id="fake-assessment", student_id=student.id,
        issued_by="teacher", sha256="deadbeef", earned=8, available=10,
        payload={"assessment_title": "Cycle Test I"},
    )
    db.add(report)
    db.commit()
    student_id, report_id = student.id, report.id
    db.close()
    return student_id, report_id


def test_sharing_a_report_returns_a_pin_the_student_can_log_in_with(client, school):
    student_id, report_id = _make_student_and_report(school)

    shared = client.post(
        f"/admin/teacher/reports/{report_id}/share", headers=_auth(school), json={"by": "Ms. Rao"},
    )
    assert shared.status_code == 201, shared.text
    body = shared.json()
    assert "pin" in body and len(body["pin"]) == 6
    assert body["class_code"] == school["section_id"]
    assert body["roll_no"] == "7"
    assert body["shared"] is True

    login = client.post(
        f"/student/{school['section_id']}/login",
        json={"roll_no": "7", "pin": body["pin"]},
    )
    assert login.status_code == 200, login.text
    token = login.json()["session_token"]
    assert login.json()["student_name"] == "Asha"

    mine = client.get("/student/reports", headers={"X-Student-Session": token})
    assert mine.status_code == 200
    assert [r["report_id"] for r in mine.json()["reports"]] == [report_id]

    full = client.get(f"/student/reports/{report_id}", headers={"X-Student-Session": token})
    assert full.status_code == 200
    assert full.json()["payload"] == {"assessment_title": "Cycle Test I"}


def test_a_wrong_pin_is_refused_and_does_not_say_why(client, school):
    _make_student_and_report(school, roll_no="8")
    r = client.post("/student/{}/login".format(school["section_id"]), json={"roll_no": "8", "pin": "000000"})
    assert r.status_code == 404


def test_an_unshared_report_never_issues_a_working_pin(client, school):
    """A report nobody has shared yet has no share_pin_hash at all -- there is no PIN to
    guess right, not even by coincidence."""
    _, report_id = _make_student_and_report(school, roll_no="9")
    r = client.post("/student/{}/login".format(school["section_id"]), json={"roll_no": "9", "pin": "123456"})
    assert r.status_code == 404


def test_unsharing_a_report_locks_the_student_out_of_that_report_but_not_the_session(client, school):
    student_id, report_id = _make_student_and_report(school, roll_no="10")
    shared = client.post(
        f"/admin/teacher/reports/{report_id}/share", headers=_auth(school), json={},
    ).json()
    login = client.post(
        f"/student/{school['section_id']}/login", json={"roll_no": "10", "pin": shared["pin"]},
    ).json()
    token = login["session_token"]

    unshared = client.post(f"/admin/teacher/reports/{report_id}/unshare", headers=_auth(school))
    assert unshared.status_code == 200
    assert unshared.json()["shared"] is False

    # the session token itself still resolves -- it is the report that dropped out
    mine = client.get("/student/reports", headers={"X-Student-Session": token})
    assert mine.status_code == 200
    assert mine.json()["reports"] == []

    full = client.get(f"/student/reports/{report_id}", headers={"X-Student-Session": token})
    assert full.status_code == 404


def test_reissuing_a_share_kills_the_old_pin(client, school):
    _, report_id = _make_student_and_report(school, roll_no="11")
    first = client.post(
        f"/admin/teacher/reports/{report_id}/share", headers=_auth(school), json={},
    ).json()
    second = client.post(
        f"/admin/teacher/reports/{report_id}/share", headers=_auth(school), json={},
    ).json()

    old_login = client.post(
        f"/student/{school['section_id']}/login", json={"roll_no": "11", "pin": first["pin"]},
    )
    # the old PIN only still works if it happened to collide with the new one
    if first["pin"] != second["pin"]:
        assert old_login.status_code == 404

    new_login = client.post(
        f"/student/{school['section_id']}/login", json={"roll_no": "11", "pin": second["pin"]},
    )
    assert new_login.status_code == 200


def test_a_class_teacher_can_share_a_report_for_their_class(client, school):
    student_id, report_id = _make_student_and_report(school, roll_no="12")
    teacher = client.post(
        "/admin/teachers", headers=_auth(school),
        json={"label": "Class teacher", "assignments": [
            {"type": "class", "section_id": school["section_id"]},
        ]},
    ).json()
    teacher_headers = {"X-API-Key": teacher["api_key"]}

    r = client.post(f"/admin/teacher/reports/{report_id}/share", headers=teacher_headers, json={})
    assert r.status_code == 201, r.text


def test_a_teacher_cannot_share_a_report_outside_their_assignments(client, school):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Section

    db = SessionLocal()
    other_section = Section(school_id=school["school_id"], grade=9, name="Z")
    db.add(other_section)
    db.commit()
    other_section_id = other_section.id
    db.close()

    student_id, report_id = _make_student_and_report(school, roll_no="13")
    # move this report's student into the section the teacher does NOT hold
    from app.models import StudentProfile

    db = SessionLocal()
    student = db.get(StudentProfile, student_id)
    student.section_id = other_section_id
    db.commit()
    db.close()

    teacher = client.post(
        "/admin/teachers", headers=_auth(school),
        json={"label": "Unrelated teacher", "assignments": [
            {"type": "class", "section_id": school["section_id"]},
        ]},
    ).json()
    teacher_headers = {"X-API-Key": teacher["api_key"]}

    r = client.post(f"/admin/teacher/reports/{report_id}/share", headers=teacher_headers, json={})
    assert r.status_code == 404


def test_teacher_student_reports_lists_what_can_be_shared(client, school):
    student_id, report_id = _make_student_and_report(school, roll_no="14")
    r = client.get(f"/admin/teacher/students/{student_id}/reports", headers=_auth(school))
    assert r.status_code == 200, r.text
    assert [row["report_id"] for row in r.json()["reports"]] == [report_id]
    assert r.json()["reports"][0]["shared"] is False
