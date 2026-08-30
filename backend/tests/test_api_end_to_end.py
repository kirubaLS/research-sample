"""Both products, end to end, through the HTTP surface."""

from __future__ import annotations

import time

from app.psychometrics.instrument import items


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"] == "up"
    assert body["models"]["high_stakes"] == "claude-opus-5"


# --------------------------------------------------------------------------------------
# Use case 1
# --------------------------------------------------------------------------------------
def test_interest_test_flow_and_the_role_boundary(client, school):
    start = client.post(
        f"/t/{school['section_id']}/start",
        json={"name": "Test Student", "roll_no": "047", "age": 15,
              "gender": "female", "locale": "ta"},
    )
    assert start.status_code == 200
    payload = start.json()
    assert payload["total_items"] == 36
    assert len(payload["screens"]) == 6
    assert payload["locale"] == "ta"
    # Tamil localisation actually reaches the client
    assert any(ord(ch) > 0x0B80 for ch in payload["screens"][0][0]["text"])

    session_id = payload["session_id"]
    now = time.time()
    responses = []
    for n, item in enumerate(items()):
        # a realistic responder: strongly Investigative, mildly Realistic, varied elsewhere.
        # A perfectly uniform responder trips the straight-line detector, correctly.
        if item.scale == "I":
            value = 5 if n % 3 else 4
        elif item.scale == "R":
            value = 4 if n % 2 else 3
        else:
            value = 1 + (n % 3)
        responses.append(
            {"item_id": item.id, "value": value,
             "shown_at": now + n * 5, "answered_at": now + n * 5 + 4}
        )
    saved = client.post(f"/t/session/{session_id}/responses", json={"responses": responses})
    assert saved.status_code == 200
    assert saved.json()["answered"] == 36

    done = client.post(f"/t/session/{session_id}/complete")
    assert done.status_code == 200
    body = done.json()
    # THE BOUNDARY: no score, no code, no stream reaches a student route
    assert set(body) == {"message", "submitted"}
    text = str(body).lower()
    for forbidden in ("holland", "riasec", "science", "commerce", "percentile", "stream"):
        assert forbidden not in text


def test_only_an_admin_can_see_the_profile(client, school):
    students = client.get(
        "/reports/interest/does-not-exist", headers={"X-API-Key": school["api_key"]}
    )
    assert students.status_code == 404

    # resolve the student created above
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    student = db.scalar(select(StudentProfile).where(StudentProfile.roll_no == "047"))
    sid = student.id
    db.close()

    anon = client.get(f"/reports/interest/{sid}")
    assert anon.status_code == 422        # no API key at all

    wrong = client.get(f"/reports/interest/{sid}", headers={"X-API-Key": "not-a-key"})
    assert wrong.status_code == 404       # never confirms the record exists

    ok = client.get(f"/reports/interest/{sid}", headers={"X-API-Key": school["api_key"]})
    assert ok.status_code == 200
    report = ok.json()
    assert report["validity"] == "valid"
    assert report["holland_code"].startswith("I")
    assert report["stream_fit"]["Science"] > 0.9
    assert report["recommendation_withheld"] is False


# --------------------------------------------------------------------------------------
# Use case 2
# --------------------------------------------------------------------------------------
def _auth(school):
    return {"X-API-Key": school["api_key"]}


def test_marks_engine_flow(client, school):
    """A faithful slice of Maths 30(B): Section B (5 x 2 = 10) with choice on Q22."""
    created = client.post(
        "/assessments",
        headers=_auth(school),
        json={
            "subject_code": "X.MATH", "title": "Unit Test II — Section B",
            "paper_code": "30(B)", "total_marks": 10,
            "declared": {"question_count": 5, "total_marks": 10, "sections": {"B": 10}},
        },
    )
    assert created.status_code == 200
    aid = created.json()["assessment_id"]

    def layer1(variant: str) -> dict:
        return {
            "board_unit": "X.MATH.U.MENSURATION",
            "concept_family": "X.MATH.CF.VOLUME",
            "concept_variant": variant,
            "chapter": "X.MATH.SAV",
            "curriculum_section": "12.2",
        }

    questions = [
        {"section": "B", "question_no": str(20 + i), "max_marks": 2, "question_type": "VSA",
         **layer1(f"variant {20 + i}")}
        for i in range(1, 6)
        if 20 + i != 22
    ]
    questions += [
        {"section": "B", "question_no": "22", "choice_alt": "a", "max_marks": 2,
         "question_type": "VSA", **layer1("variant 22a")},
        {"section": "B", "question_no": "22", "choice_alt": "b", "max_marks": 2,
         "question_type": "VSA", **layer1("variant 22b")},
    ]
    added = client.post(
        f"/assessments/{aid}/questions", headers=_auth(school), json={"questions": questions}
    )
    assert added.status_code == 200
    assert added.json()["choice_groups"] == 1

    verified = client.post(
        f"/assessments/{aid}/verify",
        headers=_auth(school),
        json={"B": [5, 2.0, 10.0]},
    )
    assert verified.status_code == 200
    report = verified.json()
    assert report["passed"], report
    assert len(report["gates"]) == 4

    frozen = client.post(f"/assessments/{aid}/freeze", headers=_auth(school))
    assert frozen.status_code == 200 and frozen.json()["version"] == 1

    marks = client.post(
        f"/assessments/{aid}/marks",
        headers=_auth(school),
        json={
            "section": "B",
            "marks": [
                {"student_roll": "047", "address": "21", "marks": 2},
                {"student_roll": "047", "address": "23", "marks": 1},
                {"student_roll": "047", "address": "24", "marks": 2},
                {"student_roll": "047", "address": "25", "marks": 0},
                {"student_roll": "047", "address": "22(b)", "marks": 1},
                {"student_roll": "047", "address": "22(a)", "state": "not_offered"},
                {"student_roll": "047", "address": "22(c)", "marks": 2},   # does not exist
                {"student_roll": "047", "address": "21", "marks": 99},     # out of range
            ],
        },
    )
    assert marks.status_code == 200
    body = marks.json()
    assert body["written"] == 6
    reasons = {r["reason"] for r in body["rejected"]}
    assert reasons == {"no_such_address", "out_of_range"}


def test_student_report_reads_the_curriculum_columns(client, school):
    """The single-paper report: strengths, focus, and no invented coverage gap.

    Regression: _rows() used to leave board_unit null on every row, so the board-weighted
    indicator aggregated nothing and the report claimed the paper carried no marks for
    Mensuration -- the unit it tested end to end.
    """
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Assessment, StudentProfile

    db = SessionLocal()
    aid = db.scalar(
        select(Assessment.id).where(Assessment.title == "Unit Test II — Section B")
    )
    sid = db.scalar(select(StudentProfile.id).where(StudentProfile.roll_no == "047"))
    db.close()
    assert aid and sid

    r = client.get(
        f"/reports/student/{sid}", headers=_auth(school), params={"assessment_id": aid}
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # 2 + 1 + 2 + 0 + 1 over five counted questions; 22(a) is not_offered and excluded.
    assert body["total"] == {"earned": 6.0, "available": 10.0, "rate": 0.6, "questions": 5}
    assert body["not_offered"] == ["B/22//a"]

    units = {i["board_unit"]: i for i in body["board_weighted_indicators"]}
    assert "X.MATH.U.MENSURATION" in units, body["board_weighted_indicators"]
    assert units["X.MATH.U.MENSURATION"]["marks_available"] == 10.0
    # ...and the unit that was tested is therefore not reported as a coverage gap.
    assert "X.MATH.U.MENSURATION" not in {g["board_unit"] for g in body["coverage_gaps"]}

    # Every question carries a concept family, so that is the axis the report groups by.
    assert body["topic_axis"] == "concept_family"
    assert [t["key"] for t in body["topics"]] == ["X.MATH.CF.VOLUME"]

    # 60% is not a strength and must not be claimed as one.
    assert body["strengths"] == []
    assert [f["key"] for f in body["focus"]] == ["X.MATH.CF.VOLUME"]


def test_every_number_in_the_report_carries_its_proof(client, school):
    """No line is an assertion: each one expands to the questions it is made of."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Assessment, StudentProfile

    db = SessionLocal()
    aid = db.scalar(
        select(Assessment.id).where(Assessment.title == "Unit Test II — Section B")
    )
    sid = db.scalar(select(StudentProfile.id).where(StudentProfile.roll_no == "047"))
    db.close()

    body = client.get(
        f"/reports/student/{sid}", headers=_auth(school), params={"assessment_id": aid}
    ).json()

    shown = body["topics"] + body["focus"] + body["all_crosstab"] + body["tier_summary"]
    assert shown
    for finding in shown:
        ev = finding["evidence"]
        assert ev, finding                       # a line nobody can check is not a finding
        assert len(ev) == finding["questions"]
        # The proof reconciles to the number exactly -- a teacher adds the column up.
        assert sum(e["earned"] for e in ev) == finding["earned"]
        assert sum(e["max_marks"] for e in ev) == finding["available"]

    topic = body["topics"][0]
    assert [e["address"] for e in topic["evidence"]] == [
        "B/21//", "B/22//b", "B/23//", "B/24//", "B/25//"
    ]
    zero = next(e for e in topic["evidence"] if e["address"] == "B/25//")
    assert zero["earned"] == 0.0 and zero["lost"] == 2.0
    assert zero["question_no"] == "25" and zero["section"] == "B"
    assert zero["curriculum_section"] == "12.2"
    assert zero["concept_variant"] == "variant 25"
    # Provenance is present and states plainly that a person typed this one in.
    assert zero["placement"]["source"] == "import"
    assert zero["placement"]["needs_review"] is False

    # The board-weighted indicator is proved the same way.
    mensuration = next(
        i for i in body["board_weighted_indicators"]
        if i["board_unit"] == "X.MATH.U.MENSURATION"
    )
    assert len(mensuration["evidence"]) == mensuration["questions"] == 5


def test_reconcile_repairs_a_misread_through_the_api(client, school):
    created = client.post(
        "/assessments",
        headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Reconcile", "total_marks": 12},
    )
    aid = created.json()["assessment_id"]
    client.post(
        f"/assessments/{aid}/questions",
        headers=_auth(school),
        json={
            "questions": [
                {"section": "A", "question_no": q, "max_marks": m,
                 "board_unit": "X.MATH.U.MENSURATION",
                 "concept_family": "X.MATH.CF.VOLUME",
                 "concept_variant": f"reconcile variant {q}"}
                for q, m in [("4", 1), ("12", 2), ("19", 3), ("26", 3), ("30", 3)]
            ]
        },
    )
    res = client.post(
        f"/assessments/{aid}/reconcile",
        headers=_auth(school),
        json={
            "student_roll": "047",
            "distributions": {
                "A/4//": {"1": 0.94, "0": 0.06},
                "A/12//": {"2": 0.88, "1": 0.10, "0": 0.02},
                "A/19//": {"3": 0.52, "1": 0.44, "2": 0.03, "0": 0.01},
                "A/26//": {"0": 0.91, "1": 0.06, "2": 0.02, "3": 0.01},
                "A/30//": {"1": 0.83, "2": 0.15, "0": 0.01, "3": 0.01},
            },
            "grand_total": 5.0,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["feasible"]
    assert sum(body["assignment"].values()) == 5.0
    assert body["assignment"]["A/19//"] == 1.0     # repaired from the naive 3


def test_tenancy_is_enforced(client, school):
    from app.db import SessionLocal
    from app.models import School

    db = SessionLocal()
    other = School(name="Another School", api_key="other-key-999")
    db.add(other)
    db.commit()
    db.close()

    mine = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Private"},
    ).json()["assessment_id"]

    leaked = client.post(
        f"/assessments/{mine}/verify", headers={"X-API-Key": "other-key-999"}
    )
    assert leaked.status_code == 404      # 404, never 403


# --------------------------------------------------------------------------------------
# The dashboard's own routes — the answer to "where is the student link?"
# --------------------------------------------------------------------------------------
def test_whoami_validates_the_key(client, school):
    assert client.get("/admin/me", headers=_auth(school)).json()["name"].startswith("Bharath")
    assert client.get("/admin/me", headers={"X-API-Key": "nope"}).status_code == 404


def test_overview_carries_the_student_link_and_progress(client, school):
    body = client.get("/admin/overview", headers=_auth(school)).json()
    assert body["school"]["name"].startswith("Bharath")
    section = next(s for s in body["sections"] if s["section_id"] == school["section_id"])
    # this is the link a teacher hands out; it exists nowhere else
    assert section["student_path"] == f"/t/{school['section_id']}"
    assert section["students"] >= 1
    assert section["completed"] >= 1


def test_roster_shows_status_per_student(client, school):
    body = client.get(
        f"/admin/sections/{school['section_id']}/students", headers=_auth(school)
    ).json()
    assert body["section"]["student_path"].endswith(school["section_id"])
    by_roll = {r["roll_no"]: r for r in body["students"]}
    assert by_roll["047"]["status"] == "complete"
    assert by_roll["047"]["holland_code"].startswith("I")
    assert by_roll["047"]["top_stream"] == "Science"


def test_cohort_summarises_the_class(client, school):
    body = client.get(f"/admin/cohort/{school['section_id']}", headers=_auth(school)).json()
    assert body["counted"] >= 1
    assert sum(body["streams"].values()) == body["counted"]


def test_dashboard_routes_are_tenant_scoped(client, school):
    for path in ("/admin/overview", f"/admin/sections/{school['section_id']}/students"):
        assert client.get(path, headers={"X-API-Key": "other-key-999"}).status_code in (200, 404)
    # another school sees no sections of ours
    body = client.get("/admin/overview", headers={"X-API-Key": "other-key-999"}).json()
    assert all(s["section_id"] != school["section_id"] for s in body["sections"])


def test_class_directory_is_public_and_reveals_nothing_else(client, school):
    """A student needs a real link without a key; they must not get anything more."""
    r = client.get("/t/classes")
    assert r.status_code == 200
    rows = r.json()
    assert rows, "the seeded section should be listed"
    row = rows[0]
    assert row["class_code"] and row["label"].startswith("Class ")
    # the directory is a way in, not a leak: no roster, no results, no key
    assert set(row) == {"class_code", "label", "grade", "school"}


def test_the_api_blocks_a_paper_that_reuses_a_variant(client, school):
    """The cross-cycle guard, at the edge where a real paper is registered.

    Same concept family across two cycles is the intent; the same variant is the failure,
    and it is silent -- the class simply scores better next time.
    """
    def make_paper(title: str, variant: str) -> str:
        created = client.post(
            "/assessments", headers=_auth(school),
            json={"subject_code": "X.MATH", "title": title, "total_marks": 2},
        )
        aid = created.json()["assessment_id"]
        return aid, client.post(
            f"/assessments/{aid}/questions", headers=_auth(school),
            json={"questions": [{
                "section": "A", "question_no": "1", "max_marks": 2,
                "board_unit": "X.MATH.U.MENSURATION",
                "concept_family": "X.MATH.CF.VOLUME",
                "concept_variant": variant,
            }]},
        )

    _, first = make_paper("Cycle 1", "Cone + Hemisphere, r = 3.5 cm")
    assert first.status_code == 200

    # a new question in the same family is exactly what should be allowed
    _, fresh = make_paper("Cycle 2", "Cylinder + Hemisphere, h = 10 cm")
    assert fresh.status_code == 200

    # the same question again is refused, and the message names where it came from
    _, repeat = make_paper("Cycle 3", "cone  +  hemisphere,  r = 3.5 cm")
    assert repeat.status_code == 409
    assert "Cycle 1" in repeat.json()["detail"]
