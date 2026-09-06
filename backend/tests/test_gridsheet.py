"""A class mark-entry sheet: one photograph, many students.

Nothing here can actually read handwriting in a test -- so the vision reader is stubbed,
and what is checked is everything downstream of it: a roll on the roster is resolved and
its marks become ordinary ProposedMarks; a roll not on the roster is flagged rather than
invented; a name that does not match is flagged but not blocked; a person can resolve or
create a student; and confirming only ever moves the clean rows.
"""

from __future__ import annotations

import io

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.extraction.gridsheet import GridCell, GridReading, GridRow


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@pytest.fixture
def paper(client, school):
    aid = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Grid sheet test", "total_marks": 10},
    ).json()["assessment_id"]
    out = client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 2, "board_unit": "X.MATH.U.STATSPROB",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"grid-{aid}-1"},
            {"section": "B", "question_no": "2", "max_marks": 3, "board_unit": "X.MATH.U.STATSPROB",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"grid-{aid}-2"},
        ]},
    )
    assert out.status_code == 200, out.text
    return aid


@pytest.fixture
def roster(client, school):
    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    ids = {}
    for roll, name in (("1", "Aarthi Selvaraj"), ("2", "Abinaya Murugan")):
        existing = db.scalar(
            select(StudentProfile).where(
                StudentProfile.section_id == school["section_id"], StudentProfile.roll_no == roll
            )
        )
        if existing is None:
            existing = StudentProfile(
                school_id=school["school_id"], section_id=school["section_id"],
                name=name, roll_no=roll,
            )
            db.add(existing)
            db.commit()
        ids[roll] = existing.id
    db.close()
    return ids


@pytest.fixture
def stub_grid(monkeypatch):
    """A working vision reader, without a network call: three rows, one for a roll that
    is not on the roster and one whose written name does not match the roster's."""
    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    reading = GridReading(rows=[
        GridRow(roll_no="1", name_as_written="Aarthi Selvaraj", cells=[
            GridCell("A/1", "1.5"), GridCell("B/2", "2"),
        ]),
        GridRow(roll_no="2", name_as_written="Someone Else", cells=[
            GridCell("A/1", "2"), GridCell("B/2", "3"),
        ]),
        GridRow(roll_no="9", name_as_written="Not On Roster", cells=[
            GridCell("A/1", "1"), GridCell("B/2", "1"),
        ]),
    ])

    class StubReader:
        def __init__(self, *a, **kw) -> None:
            pass

        def read(self, pages):
            return reading

    monkeypatch.setattr("app.extraction.gridsheet.AnthropicGridReader", StubReader)
    yield
    settings.anthropic_api_key = before


def _upload(client, school, aid, section_id):
    return client.post(
        f"/assessments/{aid}/sections/{section_id}/gridsheet", headers=_auth(school),
        files=[("files", ("sheet.jpg", io.BytesIO(b"not a real image"), "image/jpeg"))],
    )


def _upload_script(client, school, aid, section_id):
    return client.post(
        f"/assessments/{aid}/sections/{section_id}/script", headers=_auth(school),
        files=[("files", ("script.jpg", io.BytesIO(b"not a real image"), "image/jpeg"))],
    )


def test_a_roll_on_the_roster_is_resolved_and_its_marks_become_proposals(
    client, school, paper, roster, stub_grid
):
    out = _upload(client, school, paper, school["section_id"])
    # TestClient runs BackgroundTasks inline before the response is handed back, so the
    # job has already finished here -- but the endpoint itself only ever promises 202 and
    # a document_id; the counts arrive from polling the job, matching how ingest_job's
    # 202/poll pair already works for a Hindi book upload.
    assert out.status_code == 202, out.text
    job_id = out.json()["job_id"]
    job = client.get(f"/assessments/{paper}/gridsheet/jobs/{job_id}", headers=_auth(school))
    assert job.status_code == 200, job.text
    body = job.json()
    assert body["status"] == "succeeded"
    assert body["clean"] == 1
    assert body["name_mismatch"] == 1
    assert body["unmatched"] == 1

    review = client.get(
        f"/assessments/{paper}/gridsheet/{body['document_id']}", headers=_auth(school)
    ).json()
    clean_row = next(r for r in review["rows"] if r["roll_no"] == "1")
    assert clean_row["status"] == "clean"
    assert clean_row["can_confirm"] is True
    assert {m["address"] for m in clean_row["marks"]} == {"A/1//", "B/2//"}

    # The proposal is an ordinary one -- the per-student reading endpoint sees it too.
    proposals = client.get(
        f"/assessments/{paper}/answers/{roster['1']}/reading", headers=_auth(school)
    ).json()
    assert proposals["read"] == 2


def test_a_roll_not_on_the_roster_is_flagged_not_invented(client, school, paper, roster, stub_grid):
    out = _upload(client, school, paper, school["section_id"])
    document_id = out.json()["document_id"]

    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    count_before = len(list(db.scalars(select(StudentProfile))))
    db.close()

    review = client.get(f"/assessments/{paper}/gridsheet/{document_id}", headers=_auth(school)).json()
    unmatched = next(r for r in review["rows"] if r["roll_no"] == "9")
    assert unmatched["status"] == "unmatched"
    assert unmatched["student"] is None
    assert unmatched["can_confirm"] is False

    db = SessionLocal()
    count_after = len(list(db.scalars(select(StudentProfile))))
    db.close()
    assert count_after == count_before, "an unmatched roll must never silently create a student"


def test_a_name_mismatch_can_be_waved_through_by_a_person(client, school, paper, roster, stub_grid):
    out = _upload(client, school, paper, school["section_id"])
    document_id = out.json()["document_id"]
    review = client.get(f"/assessments/{paper}/gridsheet/{document_id}", headers=_auth(school)).json()
    row = next(r for r in review["rows"] if r["roll_no"] == "2")
    assert row["status"] == "name_mismatch"

    resolved = client.post(
        f"/assessments/{paper}/gridsheet/{document_id}/rows/{row['row_id']}/resolve",
        headers=_auth(school), json={"student_id": roster["2"]},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "clean"


def test_an_unmatched_roll_can_be_created_from_its_own_row(client, school, paper, roster, stub_grid):
    out = _upload(client, school, paper, school["section_id"])
    document_id = out.json()["document_id"]
    review = client.get(f"/assessments/{paper}/gridsheet/{document_id}", headers=_auth(school)).json()
    row = next(r for r in review["rows"] if r["roll_no"] == "9")

    created = client.post(
        f"/assessments/{paper}/gridsheet/{document_id}/rows/{row['row_id']}/resolve",
        headers=_auth(school), json={"create": {"name": "Not On Roster", "roll_no": "9"}},
    )
    assert created.status_code == 200, created.text
    student_id = created.json()["student_id"]

    proposals = client.get(
        f"/assessments/{paper}/answers/{student_id}/reading", headers=_auth(school)
    ).json()
    assert proposals["read"] == 2

    # `school` is a session-scoped fixture: undo the roster change (cascading through the
    # grid row and proposed marks this test created) so roll "9" is still unmatched for
    # every other test in this file.
    cleanup = client.delete(f"/admin/students/{student_id}", headers=_auth(school))
    assert cleanup.status_code == 204, cleanup.text


def test_confirm_moves_only_the_clean_rows(client, school, paper, roster, stub_grid):
    out = _upload(client, school, paper, school["section_id"])
    document_id = out.json()["document_id"]

    confirmed = client.post(
        f"/assessments/{paper}/gridsheet/{document_id}/confirm",
        headers=_auth(school), json={"by": "Mrs Rani"},
    )
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["confirmed"] == ["1"]
    skipped_rolls = {s["roll_no"] for s in body["skipped"]}
    assert skipped_rolls == {"2", "9"}

    from app.db import SessionLocal
    from app.models import MarkEvent

    db = SessionLocal()
    events = db.scalars(select(MarkEvent).where(MarkEvent.student_id == roster["1"])).all()
    db.close()
    assert len(events) == 2


def test_reading_is_backgrounded_so_the_endpoint_answers_before_the_slow_part_runs(
    client, school, paper, roster, stub_grid
):
    """The vision call is the part that can outrun Render's own request timeout -- see
    GridSheetJob's docstring -- so the upload endpoint must promise only a job id and a
    document id, never the reading itself, and a job row must actually exist to poll."""
    out = _upload(client, school, paper, school["section_id"])
    assert out.status_code == 202, out.text
    body = out.json()
    assert set(body) >= {"job_id", "status", "document_id", "next"}
    assert body["status"] == "pending"

    from app.db import SessionLocal
    from app.models import GridSheetJob

    db = SessionLocal()
    job = db.get(GridSheetJob, body["job_id"])
    db.close()
    assert job is not None
    assert job.document_id == body["document_id"]


def test_a_refused_reading_surfaces_through_the_job_not_a_bare_failure(
    client, school, paper, roster, monkeypatch
):
    """A sheet the vision reader could not make sense of is a 422 with the real reason,
    the same as any other refused reading in this codebase -- not a bare 'the job failed'
    and not a silently empty success."""
    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    class RefusingReader:
        def __init__(self, *a, **kw) -> None:
            pass

        def read(self, pages):
            return GridReading(refused="the photograph was too dark to read anything from it")

    monkeypatch.setattr("app.extraction.gridsheet.AnthropicGridReader", RefusingReader)
    try:
        out = _upload(client, school, paper, school["section_id"])
        assert out.status_code == 202, out.text
        job_id = out.json()["job_id"]
        job = client.get(f"/assessments/{paper}/gridsheet/jobs/{job_id}", headers=_auth(school))
        assert job.status_code == 422, job.text
        assert "too dark" in job.text
    finally:
        settings.anthropic_api_key = before


def _upload_csv(client, school, aid, section_id, csv_bytes):
    return client.post(
        f"/assessments/{aid}/sections/{section_id}/gridsheet/file", headers=_auth(school),
        files=[("files", ("marks.csv", io.BytesIO(csv_bytes), "text/csv"))],
    )


def test_a_csv_naming_several_students_is_split_one_row_per_roll(client, school, paper, roster):
    """The CSV/XLSX counterpart to the class photo: no vision call, answers inside one
    request, and a roll the roster doesn't recognise is flagged, not invented."""
    csv_bytes = b"Roll,Q1,B/2\n1,1.5,2\n9,1,1\n"
    out = _upload_csv(client, school, paper, school["section_id"], csv_bytes)
    assert out.status_code == 201, out.text
    body = out.json()
    assert body["clean"] == 1
    assert body["unmatched"] == 1

    review = client.get(
        f"/assessments/{paper}/gridsheet/{body['document_id']}", headers=_auth(school)
    ).json()
    clean_row = next(r for r in review["rows"] if r["roll_no"] == "1")
    assert clean_row["status"] == "clean"
    assert {m["address"] for m in clean_row["marks"]} == {"A/1//", "B/2//"}
    unmatched_row = next(r for r in review["rows"] if r["roll_no"] == "9")
    assert unmatched_row["status"] == "unmatched"

    # Section-blank ("Q1") and section-qualified ("B/2") headers both resolved against
    # the real, section-qualified questions on the paper -- match_address's own job.
    proposals = client.get(
        f"/assessments/{paper}/answers/{roster['1']}/reading", headers=_auth(school)
    ).json()
    assert proposals["read"] == 2


def test_a_csv_naming_no_student_is_refused(client, school, paper):
    """A single-student sheet with no roll column at all belongs to the single-student
    upload, not here -- refused by name rather than silently attributed to nobody."""
    out = _upload_csv(client, school, paper, school["section_id"], b"Q1,B/2\n1.5,2\n")
    assert out.status_code == 422, out.text
    assert "does not name any student" in out.text


def _stub_single_script(monkeypatch, reading):
    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    class StubReader:
        def __init__(self, *a, **kw) -> None:
            pass

        def read(self, pages):
            return reading

    monkeypatch.setattr("app.extraction.gridsheet.AnthropicGridReader", StubReader)
    return settings, before


def test_a_single_scripts_own_name_and_roll_are_read_and_matched(
    client, school, paper, roster, monkeypatch
):
    """One student's own script -- no dropdown, no roll picked up front -- reads their
    name and roll straight off the page and resolves it exactly like a clean grid row."""
    reading = GridReading(rows=[
        GridRow(roll_no="1", name_as_written="Aarthi Selvaraj", cells=[
            GridCell("A/1", "2"), GridCell("B/2", "3"),
        ]),
    ])
    settings, before = _stub_single_script(monkeypatch, reading)
    try:
        out = _upload_script(client, school, paper, school["section_id"])
        assert out.status_code == 202, out.text
        job_id = out.json()["job_id"]
        job = client.get(f"/assessments/{paper}/gridsheet/jobs/{job_id}", headers=_auth(school))
        assert job.status_code == 200, job.text
        body = job.json()
        assert body["status"] == "succeeded"
        assert body["clean"] == 1
    finally:
        settings.anthropic_api_key = before


def test_a_single_scripts_student_missed_off_the_roster_is_flagged_not_invented(
    client, school, paper, monkeypatch
):
    """The student who was absent when the roster was entered and showed up for the exam
    anyway: flagged as unmatched, same as an unrecognised grid-sheet roll, with the same
    create-a-student resolve action -- never silently invented."""
    reading = GridReading(rows=[
        GridRow(roll_no="77", name_as_written="Late Addition", cells=[GridCell("A/1", "2")]),
    ])
    settings, before = _stub_single_script(monkeypatch, reading)
    try:
        out = _upload_script(client, school, paper, school["section_id"])
        job_id = out.json()["job_id"]
        job = client.get(
            f"/assessments/{paper}/gridsheet/jobs/{job_id}", headers=_auth(school)
        ).json()
        assert job["unmatched"] == 1

        review = client.get(
            f"/assessments/{paper}/gridsheet/{job['document_id']}", headers=_auth(school)
        ).json()
        row = review["rows"][0]
        assert row["status"] == "unmatched"

        created = client.post(
            f"/assessments/{paper}/gridsheet/{job['document_id']}/rows/{row['row_id']}/resolve",
            headers=_auth(school), json={"create": {"name": "Late Addition", "roll_no": "77"}},
        )
        assert created.status_code == 200, created.text
    finally:
        settings.anthropic_api_key = before


def test_a_photo_of_several_students_is_refused_on_the_single_script_endpoint(
    client, school, paper, roster, monkeypatch
):
    """A class sheet sent to the single-script endpoint by mistake is caught, not guessed
    past by picking whichever row came first."""
    reading = GridReading(rows=[
        GridRow(roll_no="1", name_as_written="Aarthi Selvaraj", cells=[GridCell("A/1", "2")]),
        GridRow(roll_no="2", name_as_written="Abinaya Murugan", cells=[GridCell("A/1", "1")]),
    ])
    settings, before = _stub_single_script(monkeypatch, reading)
    try:
        out = _upload_script(client, school, paper, school["section_id"])
        job_id = out.json()["job_id"]
        job = client.get(f"/assessments/{paper}/gridsheet/jobs/{job_id}", headers=_auth(school))
        assert job.status_code == 422, job.text
        assert "2 different students" in job.text
    finally:
        settings.anthropic_api_key = before
