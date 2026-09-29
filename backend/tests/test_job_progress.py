"""progress_done/progress_total on the three background job models.

Each job used to carry only status (pending/running/succeeded/failed) -- nothing
incremental, so a browser polling one had nothing honest to show beyond a generic "still
working" spinner no matter how long the job actually took. These tests prove three
things per job type: (1) progress is committed to the database mid-run, not only once at
the end, by reading it back from a SEPARATE session while the job's own run is still in
the middle of its callback; (2) a failure partway through still leaves the job "failed",
never stuck "running" forever, with whatever progress it reached still recorded; (3) the
polling GET endpoint actually returns the two new fields.
"""

from __future__ import annotations

import io

import pymupdf
import pytest
from sqlalchemy import select

from app.config import get_settings


def _auth(school):
    return {"X-API-Key": school["api_key"]}


def _read_progress(model, job_id):
    """A fresh session, deliberately not the one the job itself is using -- this is what
    proves a write actually committed rather than merely living in some in-memory object
    the job's own call happens to still be holding."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        job = db.get(model, job_id)
        return (job.status, job.progress_done, job.progress_total)
    finally:
        db.close()


def _latest_job_id(model, assessment_id):
    """TestClient runs BackgroundTasks inline, before the HTTP call that queued the job
    ever returns its response body -- so a stub called from inside that background task
    cannot yet know the job_id an assertion after the request will use. It can, however,
    always find its own job by the assessment it was queued for."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        job = db.scalars(
            select(model)
            .where(model.assessment_id == assessment_id)
            .order_by(model.created_at.desc())
        ).first()
        return job.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# PaperScanJob -- pages read out of the paper's total
# ---------------------------------------------------------------------------


@pytest.fixture
def scan_assessment(client, school):
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Progress test", "total_marks": 8},
    )
    assert r.status_code == 200
    return r.json()["assessment_id"]


def _two_page_pdf() -> bytes:
    doc = pymupdf.open()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8))
    pixmap.clear_with(180)
    for _ in range(2):
        page = doc.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pixmap)
    data = doc.tobytes()
    doc.close()
    return data


def test_paper_scan_progress_commits_per_page_as_the_read_runs(
    client, school, scan_assessment, monkeypatch,
):
    from app.extraction import paper_vision as paper_vision_module
    from app.extraction.paper import ExtractedQuestion
    from app.extraction.paper_vision import PaperVisionReading
    from app.models import PaperScanJob

    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    seen_mid_call: list[tuple] = []

    def fake_read_paper_vision(pages, *, api_key, model, page_concurrency, on_progress=None):
        assert on_progress is not None
        on_progress(1, len(pages))
        # Read back from a separate session mid-call: this is the whole point -- the
        # commit must have already landed, not be waiting on this function to return.
        job_id = _latest_job_id(PaperScanJob, scan_assessment)
        seen_mid_call.append(_read_progress(PaperScanJob, job_id))
        on_progress(2, len(pages))
        return PaperVisionReading(questions=[
            ExtractedQuestion(
                section="A", question_no="1", sub_part=None, choice_alt=None,
                max_marks=3.0, stem_text="Find the mean.", logical_page=1,
            ),
        ])

    monkeypatch.setattr(paper_vision_module, "read_paper_vision", fake_read_paper_vision)

    try:
        r = client.post(
            f"/assessments/{scan_assessment}/scan", headers=_auth(school),
            files=[("files", ("scan.pdf", io.BytesIO(_two_page_pdf()), "application/pdf"))],
        )
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]

        job = client.get(
            f"/assessments/{scan_assessment}/scan/jobs/{job_id}", headers=_auth(school),
        )
        assert job.status_code == 200, job.text
        body = job.json()
        assert body["status"] == "succeeded"
        assert body["progress_done"] == 2
        assert body["progress_total"] == 2

        # The mid-call read, taken from the fake reader's own on_progress(1, 2) call,
        # proves the commit happened before the vision call returned -- not just once at
        # the very end.
        assert seen_mid_call == [("pending", 1, 2)]
    finally:
        settings.anthropic_api_key = before


def test_a_paper_scan_that_fails_partway_still_ends_failed_not_stuck_running(
    client, school, scan_assessment, monkeypatch,
):
    """A crash after some pages were read but before the whole read finished must still
    mark the job failed, with the progress it reached kept -- never left "pending"
    (this repo's name for "still running") forever."""
    from app.extraction import paper_vision as paper_vision_module
    from app.models import PaperScanJob

    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    def fake_read_paper_vision(pages, *, api_key, model, page_concurrency, on_progress=None):
        on_progress(1, len(pages))
        raise RuntimeError("network dropped after page 1")

    monkeypatch.setattr(paper_vision_module, "read_paper_vision", fake_read_paper_vision)

    try:
        r = client.post(
            f"/assessments/{scan_assessment}/scan", headers=_auth(school),
            files=[("files", ("scan.pdf", io.BytesIO(_two_page_pdf()), "application/pdf"))],
        )
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]

        status, done, total = _read_progress(PaperScanJob, job_id)
        assert status == "failed"
        assert done == 1
        assert total == 2

        job = client.get(
            f"/assessments/{scan_assessment}/scan/jobs/{job_id}", headers=_auth(school),
        )
        assert job.status_code == 500
    finally:
        settings.anthropic_api_key = before


# ---------------------------------------------------------------------------
# GridSheetJob -- no real per-page signal (one blocking multi-page call), so
# progress_total is known upfront and progress_done only ever moves from null to it.
# ---------------------------------------------------------------------------


@pytest.fixture
def grid_paper(client, school):
    aid = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Grid progress test", "total_marks": 10},
    ).json()["assessment_id"]
    out = client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 2, "board_unit": "X.MATH.U.STATSPROB",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"grid-progress-{aid}-1"},
        ]},
    )
    assert out.status_code == 200, out.text
    return aid


def test_gridsheet_progress_total_is_known_before_the_call_and_done_only_after(
    client, school, grid_paper, monkeypatch,
):
    from app.api import gridsheets as gridsheets_module
    from app.extraction.gridsheet import GridCell, GridReading, GridRow

    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    seen_before_call: list[tuple] = []

    def fake_read_grid(pages, *, api_key, model):
        from app.models import GridSheetJob

        job_id = _latest_job_id(GridSheetJob, grid_paper)
        seen_before_call.append(_read_progress(GridSheetJob, job_id))
        return GridReading(rows=[
            GridRow(roll_no="1", name_as_written="Someone", cells=[GridCell("A/1", "2")]),
        ])

    monkeypatch.setattr(gridsheets_module, "read_grid", fake_read_grid)

    try:
        r = client.post(
            f"/assessments/{grid_paper}/sections/{school['section_id']}/gridsheet",
            headers=_auth(school),
            files=[("files", ("sheet.jpg", io.BytesIO(b"not a real image"), "image/jpeg"))],
        )
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]

        job = client.get(
            f"/assessments/{grid_paper}/gridsheet/jobs/{job_id}", headers=_auth(school),
        )
        assert job.status_code == 200, job.text
        body = job.json()
        assert body["status"] == "succeeded"
        assert body["progress_done"] == 1
        assert body["progress_total"] == 1

        # Before the (fake) vision call ran, progress_total was already set -- the page
        # count is known up front -- but progress_done was still null: honest about not
        # yet claiming any page done for a reader with no real per-page signal.
        assert seen_before_call == [("pending", None, 1)]
    finally:
        settings.anthropic_api_key = before


def test_a_gridsheet_read_that_fails_still_ends_failed_with_only_the_total_known(
    client, school, grid_paper, monkeypatch,
):
    from app.api import gridsheets as gridsheets_module
    from app.models import GridSheetJob

    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    def fake_read_grid(pages, *, api_key, model):
        raise RuntimeError("truncated response")

    monkeypatch.setattr(gridsheets_module, "read_grid", fake_read_grid)

    try:
        r = client.post(
            f"/assessments/{grid_paper}/sections/{school['section_id']}/gridsheet",
            headers=_auth(school),
            files=[("files", ("sheet.jpg", io.BytesIO(b"not a real image"), "image/jpeg"))],
        )
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]

        status, done, total = _read_progress(GridSheetJob, job_id)
        assert status == "failed"
        assert done is None, "no page was ever confirmed read -- honest, not stuck at 0"
        assert total == 1
    finally:
        settings.anthropic_api_key = before


# ---------------------------------------------------------------------------
# PlacementJob -- questions classified out of the paper's total
# ---------------------------------------------------------------------------


@pytest.fixture
def placement_paper(client, school, book):
    import uuid

    tag = uuid.uuid4().hex[:8]
    aid = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": f"Placement progress {tag}", "total_marks": 4},
    ).json()["assessment_id"]
    added = client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 2,
             "stem_text": "The slant height of a right circular cone of base diameter 14 cm",
             "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
             "concept_variant": f"cone slant height {tag}"},
            {"section": "A", "question_no": "2", "max_marks": 2,
             "stem_text": "The slant height of a right circular cone of base diameter 20 cm",
             "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
             "concept_variant": f"cone slant height wide {tag}"},
        ]},
    )
    assert added.status_code == 200, added.json()
    return aid


def test_placement_progress_commits_per_question_as_classification_runs(
    client, school, placement_paper, monkeypatch,
):
    from app.api import placement as placement_module
    from app.classify import anthropic_judge as anthropic_judge_module
    from app.classify.pipeline import PaperPlacement, PlacedQuestion
    from app.models import PlacementJob

    class StubJudge:
        def classify(self, question, evidence):
            raise AssertionError("place_paper is mocked; the judge should never be called")

    class StubJudgeFactory:
        def __new__(cls, *a, **kw):
            return StubJudge()

    settings = get_settings()
    before_key = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    seen_mid_call: list[tuple] = []

    def fake_place_paper(questions, *args, on_progress=None, **kwargs):
        assert on_progress is not None
        question_ids = [q[0] for q in questions]
        on_progress(1, len(question_ids))
        job_id = _latest_job_id(PlacementJob, placement_paper)
        seen_mid_call.append(_read_progress(PlacementJob, job_id))
        on_progress(2, len(question_ids))
        return PaperPlacement(
            questions=[
                PlacedQuestion(
                    question_id=qid, marks=2.0, chapter="Surface Areas and Volumes",
                    board_unit=None, curriculum_section=None, tier="Applying",
                    skill_required="", confidence=0.9, reasoning="a cone",
                )
                for qid in question_ids
            ],
            feasible=True, note="", residual={}, reviewed_count=0,
        )

    original_place_paper = placement_module.place_paper
    original_judge_class = anthropic_judge_module.AnthropicJudge
    try:
        placement_module.place_paper = fake_place_paper
        anthropic_judge_module.AnthropicJudge = StubJudgeFactory

        r = client.post(f"/assessments/{placement_paper}/place", headers=_auth(school))
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]

        job = client.get(
            f"/assessments/{placement_paper}/place/jobs/{job_id}", headers=_auth(school),
        )
        assert job.status_code == 200, job.text
        body = job.json()
        assert body["status"] == "succeeded"
        assert body["progress_done"] == 2
        assert body["progress_total"] == 2
        assert seen_mid_call == [("pending", 1, 2)]
    finally:
        settings.anthropic_api_key = before_key
        placement_module.place_paper = original_place_paper
        anthropic_judge_module.AnthropicJudge = original_judge_class


def test_a_placement_run_that_fails_partway_still_ends_failed_not_stuck_running(
    client, school, placement_paper, monkeypatch,
):
    from app.api import placement as placement_module
    from app.classify import anthropic_judge as anthropic_judge_module
    from app.models import PlacementJob

    class StubJudge:
        def classify(self, question, evidence):
            raise AssertionError("place_paper is mocked; the judge should never be called")

    class StubJudgeFactory:
        def __new__(cls, *a, **kw):
            return StubJudge()

    settings = get_settings()
    before_key = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    def fake_place_paper(questions, *args, on_progress=None, **kwargs):
        on_progress(1, len(questions))
        raise RuntimeError("classifier rate limited")

    original_place_paper = placement_module.place_paper
    original_judge_class = anthropic_judge_module.AnthropicJudge
    try:
        placement_module.place_paper = fake_place_paper
        anthropic_judge_module.AnthropicJudge = StubJudgeFactory

        r = client.post(f"/assessments/{placement_paper}/place", headers=_auth(school))
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]

        status, done, total = _read_progress(PlacementJob, job_id)
        assert status == "failed"
        assert done == 1
        assert total == 2

        job = client.get(
            f"/assessments/{placement_paper}/place/jobs/{job_id}", headers=_auth(school),
        )
        assert job.status_code == 502
    finally:
        settings.anthropic_api_key = before_key
        placement_module.place_paper = original_place_paper
        anthropic_judge_module.AnthropicJudge = original_judge_class
