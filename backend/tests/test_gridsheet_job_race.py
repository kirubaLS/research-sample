"""A person can dislike a grid-sheet read and re-upload before the first vision call
comes back -- both jobs then run for the same assessment+section, and whichever one's
slow vision call happens to return LAST used to win regardless of which was queued last.
_supersede_pending_gridsheet_jobs (queued the moment a newer upload is accepted) and the
locked re-check _run_gridsheet_job now does immediately before it writes are what stop an
older, slower job's stale rows and ProposedMarks from clobbering a newer upload's.

These tests call the job-runner function directly, out of order, rather than going
through the HTTP endpoint -- TestClient runs BackgroundTasks inline, so two ordinary
uploads never actually interleave the way a real deploy's worker can.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@pytest.fixture
def paper(client, school):
    aid = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Grid sheet job race test", "total_marks": 10},
    ).json()["assessment_id"]
    out = client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 2, "board_unit": "X.MATH.U.STATSPROB",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"grid-race-{aid}-1"},
            {"section": "B", "question_no": "2", "max_marks": 3, "board_unit": "X.MATH.U.STATSPROB",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"grid-race-{aid}-2"},
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


def _queue_job(db, school, aid, section_id, roll_no, marks):
    """A GridSheetJob and its document, built directly against the database -- the same
    rows _queue_vision_reading would have written for one photo upload."""
    from app.api.documents import store_document
    from app.api.gridsheets import _supersede_pending_gridsheet_jobs
    from app.models import GridSheetJob

    document = store_document(
        db, school_id=school["school_id"], assessment_id=aid, student_id=None,
        kind="mark_grid", pages=[(f"photo-{roll_no}-{marks}".encode(), "image/jpeg", None)],
        uploaded_by="",
    )
    job = GridSheetJob(
        school_id=school["school_id"], assessment_id=aid, section_id=section_id,
        document_id=document.id, kind="class_photo",
    )
    db.add(job)
    db.flush()
    _supersede_pending_gridsheet_jobs(db, aid, section_id, except_job_id=job.id)
    db.commit()
    return job.id


def test_an_older_jobs_late_finish_does_not_clobber_a_newer_uploads_marks(
    client, school, paper, roster, monkeypatch
):
    from app.api.gridsheets import _run_gridsheet_job
    from app.config import get_settings
    from app.extraction.gridsheet import GridCell, GridReading, GridRow

    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    readings = {}

    def fake_read_grid(pages, **kw):
        # Pages carry the marks this job's fixture stashed in the fake photo bytes, so
        # each job reads back exactly the reading it was queued with, however jobs run.
        raw = pages[0][0].decode()
        return readings[raw]

    monkeypatch.setattr("app.api.gridsheets.read_grid", fake_read_grid)

    from app.db import SessionLocal

    db = SessionLocal()
    try:
        # The first upload: roll 1 scored 1.5. The person immediately re-uploads (roll 1
        # actually scored 2) before this first job's vision call has returned.
        old_key = "photo-1-old"
        readings[old_key] = GridReading(rows=[
            GridRow(roll_no="1", name_as_written="Aarthi Selvaraj",
                     cells=[GridCell("A/1", "1.5"), GridCell("B/2", "2")]),
        ])
        old_job_id = _queue_job(db, school, paper, school["section_id"], "1", "old")

        new_key = "photo-1-new"
        readings[new_key] = GridReading(rows=[
            GridRow(roll_no="1", name_as_written="Aarthi Selvaraj",
                     cells=[GridCell("A/1", "2"), GridCell("B/2", "3")]),
        ])
        new_job_id = _queue_job(db, school, paper, school["section_id"], "1", "new")
    finally:
        db.close()

    # The newer upload's vision call comes back first (it is not, in general, the case
    # that a race resolves in queue order); the older, now-superseded job's call finally
    # returns after it.
    _run_gridsheet_job(new_job_id)
    _run_gridsheet_job(old_job_id)

    from app.models import GridSheetJob, ProposedMark

    db = SessionLocal()
    try:
        old_job = db.get(GridSheetJob, old_job_id)
        new_job = db.get(GridSheetJob, new_job_id)
        assert old_job.status == "failed", "the superseded job must not report success"
        assert new_job.status == "succeeded"

        marks = {
            m.address: m.marks for m in db.scalars(
                select(ProposedMark).where(
                    ProposedMark.assessment_id == paper, ProposedMark.student_id == roster["1"],
                )
            )
        }
        # The newer upload's marks (2 and 3), not the stale first upload's (1.5 and 2).
        assert marks == {"A/1//": 2.0, "B/2//": 3.0}
    finally:
        db.close()
        settings.anthropic_api_key = before


def test_a_job_queued_after_another_is_already_finished_runs_normally(
    client, school, paper, roster, monkeypatch
):
    """The supersede check must never punish the ordinary, non-racing case: a second
    upload queued well after the first one has already succeeded reads and writes fine."""
    from app.api.gridsheets import _run_gridsheet_job
    from app.config import get_settings
    from app.extraction.gridsheet import GridCell, GridReading, GridRow

    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    readings = {}

    def fake_read_grid(pages, **kw):
        raw = pages[0][0].decode()
        return readings[raw]

    monkeypatch.setattr("app.api.gridsheets.read_grid", fake_read_grid)

    from app.db import SessionLocal
    from app.models import GridSheetJob

    db = SessionLocal()
    try:
        first_key = "photo-2-first"
        readings[first_key] = GridReading(rows=[
            GridRow(roll_no="2", name_as_written="Abinaya Murugan",
                     cells=[GridCell("A/1", "1"), GridCell("B/2", "1")]),
        ])
        first_job_id = _queue_job(db, school, paper, school["section_id"], "2", "first")
    finally:
        db.close()

    _run_gridsheet_job(first_job_id)

    db = SessionLocal()
    try:
        second_key = "photo-2-second"
        readings[second_key] = GridReading(rows=[
            GridRow(roll_no="2", name_as_written="Abinaya Murugan",
                     cells=[GridCell("A/1", "2"), GridCell("B/2", "3")]),
        ])
        second_job_id = _queue_job(db, school, paper, school["section_id"], "2", "second")
    finally:
        db.close()

    _run_gridsheet_job(second_job_id)

    db = SessionLocal()
    try:
        first_job = db.get(GridSheetJob, first_job_id)
        second_job = db.get(GridSheetJob, second_job_id)
        assert first_job.status == "succeeded"
        assert second_job.status == "succeeded"

        from app.models import ProposedMark

        marks = {
            m.address: m.marks for m in db.scalars(
                select(ProposedMark).where(
                    ProposedMark.assessment_id == paper, ProposedMark.student_id == roster["2"],
                )
            )
        }
        assert marks == {"A/1//": 2.0, "B/2//": 3.0}
    finally:
        db.close()
        settings.anthropic_api_key = before
