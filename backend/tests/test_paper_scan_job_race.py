"""A person can dislike a scanned paper's read and re-scan it before the first vision job
comes back. Both jobs then run for the same assessment, and whichever one's slow vision
call happened to return LAST used to win, regardless of which scan was actually the newer
one. _supersede_pending_paper_jobs (called the moment a newer scan request lands) and the
locked re-check _run_paper_scan_job now does immediately before it writes are what stop an
older, slower job's stale questions from clobbering a newer scan's.

These call the job-runner function directly, out of order, rather than through the HTTP
endpoint -- TestClient runs BackgroundTasks inline, so two ordinary re-scans never
actually interleave the way a real deploy's worker process can.
"""

from __future__ import annotations

from sqlalchemy import select


def _auth(school):
    return {"X-API-Key": school["api_key"]}


def _extract(stems: list[str]):
    from app.extraction.paper import ExtractedQuestion, PaperExtract

    questions = [
        ExtractedQuestion(
            section="A", question_no=str(i + 1), sub_part=None, choice_alt=None,
            max_marks=5.0, stem_text=stem, logical_page=1,
        )
        for i, stem in enumerate(stems)
    ]
    return PaperExtract(
        route="vision", page_count=1, questions=questions,
        declared_sections={}, declared_count=len(questions), declared_total=None, problems=[],
    )


def _queue_job(db, school, assessment_id):
    from app.models import PaperScanJob

    from app.api.marks import _supersede_pending_paper_jobs

    job = PaperScanJob(school_id=school["school_id"], assessment_id=assessment_id, pdf_bytes=b"%PDF-fake")
    db.add(job)
    db.flush()
    _supersede_pending_paper_jobs(db, assessment_id, except_job_id=job.id)
    db.commit()
    return job.id


def test_an_older_scan_jobs_late_finish_does_not_clobber_a_newer_scans_questions(
    client, school, monkeypatch
):
    from app.config import get_settings
    from app.extraction import paper_vision

    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    aid = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Paper scan job race test", "total_marks": 10},
    ).json()["assessment_id"]

    readings: dict[str, object] = {}

    class FakeReading:
        def __init__(self, questions):
            self.questions = questions
            self.refused = None
            self.problems: list[str] = []
            self.declared_sections: dict = {}
            self.declared_count = None
            self.declared_total = None

    def fake_rasterize_pdf(path):
        return [path.read_bytes()]

    def fake_read_paper_vision(pages, **kw):
        return readings[pages[0].decode()]

    monkeypatch.setattr(paper_vision, "rasterize_pdf", fake_rasterize_pdf)
    monkeypatch.setattr(paper_vision, "read_paper_vision", fake_read_paper_vision)

    from app.extraction.paper import ExtractedQuestion

    from app.api.marks import _run_paper_scan_job
    from app.db import SessionLocal
    from app.models import PaperScanJob

    db = SessionLocal()
    try:
        old_job_id = _queue_job(db, school, aid)
        job = db.get(PaperScanJob, old_job_id)
        job.pdf_bytes = b"old-scan"
        readings["old-scan"] = FakeReading([
            ExtractedQuestion(
                section="A", question_no="1", sub_part=None, choice_alt=None,
                max_marks=5.0, stem_text="stale question from the first, slow scan",
                logical_page=1,
            ),
        ])

        new_job_id = _queue_job(db, school, aid)
        job = db.get(PaperScanJob, new_job_id)
        job.pdf_bytes = b"new-scan"
        readings["new-scan"] = FakeReading([
            ExtractedQuestion(
                section="A", question_no="1", sub_part=None, choice_alt=None,
                max_marks=5.0, stem_text="the corrected re-scan's own question",
                logical_page=1,
            ),
        ])
        db.commit()
    finally:
        db.close()

    # The re-scan's vision call happens to come back first; the older, now-superseded
    # job's call finally returns after it -- the case that used to let stale rows win.
    _run_paper_scan_job(new_job_id)
    _run_paper_scan_job(old_job_id)

    from app.models import Assessment, ScannedQuestion

    db = SessionLocal()
    try:
        old_job = db.get(PaperScanJob, old_job_id)
        new_job = db.get(PaperScanJob, new_job_id)
        assert old_job.status == "failed", "the superseded job must not report success"
        assert new_job.status == "succeeded"

        rows = list(db.scalars(select(ScannedQuestion).where(ScannedQuestion.assessment_id == aid)))
        stems = {r.stem_text for r in rows}
        assert stems == {"the corrected re-scan's own question"}

        assessment = db.get(Assessment, aid)
        assert assessment.source_sha256 == __import__("hashlib").sha256(b"new-scan").hexdigest()
    finally:
        db.close()
        settings.anthropic_api_key = before
