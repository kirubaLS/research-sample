"""The OCR mapper: the teacher flow's reading steps, then the prompt mapper, nothing stored.

The vision reader and the mapping model are stubs; no paid API is called."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pymupdf
import pytest
from sqlalchemy import func, select

KEY = "ocr-lab-key"
HEAD = {"X-Platform-Key": KEY}
MARK_X = 595 * 0.87

lab = pl = None


@pytest.fixture(autouse=True)
def _modules(_tmp_db):
    global lab, pl
    from app.api import ocr_lab, prompt_lab

    lab, pl = ocr_lab, prompt_lab


@pytest.fixture
def operator(monkeypatch):
    from app.config import get_settings

    s = get_settings()
    before = s.platform_admin_key
    s.platform_admin_key = KEY
    monkeypatch.setattr(s, "anthropic_api_key", "test-key")
    lab._limiter.reset()
    yield
    s.platform_admin_key = before


def _text_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for x, y, t in [
        (60, 60, "This question paper contains 2 questions."),
        (60, 90, "SECTION A"),
        (60, 120, "1. Why did Gandhiji oppose the Rowlatt Act of 1919 and"),
        (60, 134, "call for a nationwide satyagraha against it?"),
        (MARK_X, 120, "3"),
        (60, 180, "2. State two causes for the growth of cotton in the"),
        (60, 194, "black soil regions of India."),
        (MARK_X, 180, "5"),
    ]:
        page.insert_text((x, y), t, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def _scan_pdf(pages: int = 2) -> bytes:
    doc = pymupdf.open()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8))
    pix.clear_with(180)
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pix)
    data = doc.tobytes()
    doc.close()
    return data


def _counts():
    from app.db import SessionLocal
    from app.models import (
        Assessment,
        AuditLog,
        PaperScanJob,
        PlacementJob,
        Question,
        QuestionPlacement,
        ScanDocument,
        ScannedQuestion,
    )

    db = SessionLocal()
    try:
        return {m.__name__: db.scalar(select(func.count()).select_from(m)) for m in (
            Assessment, AuditLog, PaperScanJob, PlacementJob, Question, QuestionPlacement,
            ScanDocument, ScannedQuestion)}
    finally:
        db.close()


class _Messages:
    def parse(self, **kw):
        rows = json.loads(kw["messages"][0]["content"].split("<questions>\n")[1].split("\n</questions>")[0])
        out = []
        for r in rows:
            t = r["text"].lower()
            if "rowlatt" in t:
                out.append(pl._Row(row=r["row"], chapter_id="H2", topic_id="H2.1.2", confidence="high",
                                   syllabus_status="in_syllabus", reason="Rowlatt"))
            else:
                out.append(pl._Row(row=r["row"], chapter_id="G1", topic_id="G1.7.1.2", confidence="medium",
                                   syllabus_status="in_syllabus", reason="soil"))
        usage = SimpleNamespace(input_tokens=900, output_tokens=300, cache_read_input_tokens=7000,
                                cache_creation_input_tokens=0)
        return SimpleNamespace(parsed_output=pl._Out(mappings=out), usage=usage)


def _upload(client, data, name="paper.pdf", **form):
    return client.post("/platform/ocr-lab/run", headers=HEAD,
                       files=[("files", (name, data, "application/pdf"))], data=form)


def test_the_routes_are_behind_the_operator_key(client):
    assert client.post("/platform/ocr-lab/run",
                       files=[("files", ("p.pdf", _text_pdf(), "application/pdf"))]).status_code == 404
    assert client.get("/platform/ocr-lab/jobs/" + "a" * 32).status_code == 404


def test_a_text_paper_is_read_then_mapped_and_nothing_is_stored(client, operator, monkeypatch):
    monkeypatch.setattr(pl, "_client", lambda settings: SimpleNamespace(messages=_Messages()))
    before = _counts()
    r = _upload(client, _text_pdf())
    assert r.status_code == 202, r.text
    assert r.json()["route"] == "text" and r.json()["pages"] == 1
    job = client.get(f"/platform/ocr-lab/jobs/{r.json()['job_id']}", headers=HEAD).json()
    assert job["status"] == "done", job
    result = job["result"]
    assert result["ocr"]["route"] == "text" and result["ocr"]["estimated_usd"] == 0.0
    assert [q["marks"] for q in result["questions"]] == [3.0, 5.0]
    assert result["checks"]["read_total"] == 8.0 and result["checks"]["read_count"] == 2
    by = result["mapping"]["by_address"]
    first = next(iter(by.values()))
    assert first["topic"]["title"] == "The Rowlatt Act"
    assert result["mapping"]["model"] == "claude-haiku-4-5" and result["mapping"]["summary"]["questions"] == 2
    # every answer says which book sections the textbook text pointed to, and whether a second reader looked
    check = first["book_check"]
    assert check["candidates"] and "second_reader" in check and "supported_by_book" in check
    assert result["mapping"]["second_reader_model"]
    assert _counts() == before, "nothing may be written to the database"


def test_reading_without_mapping_needs_no_anthropic_key(client, operator, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    r = _upload(client, _text_pdf(), map_topics="false")
    assert r.status_code == 202, r.text
    job = client.get(f"/platform/ocr-lab/jobs/{r.json()['job_id']}", headers=HEAD).json()
    assert job["status"] == "done" and job["result"]["mapping"] is None
    assert len(job["result"]["questions"]) == 2


def test_mapping_without_a_key_is_refused_up_front(client, operator, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    r = _upload(client, _text_pdf())
    assert r.status_code == 409 and "ANTHROPIC_API_KEY" in r.text


def test_a_scan_goes_to_the_vision_reader_with_its_progress_and_the_pages_are_deleted(
    client, operator, monkeypatch,
):
    from app.extraction.paper import ExtractedQuestion
    from app.extraction.paper_vision import PaperVisionReading

    seen = {}

    def fake_read(pages, *, api_key, model, page_concurrency, on_progress, **extra):
        seen["model"], seen["pages"] = model, len(pages)
        for i in range(len(pages)):
            on_progress(i + 1, len(pages))
        return PaperVisionReading(
            questions=[
                ExtractedQuestion(section="A", question_no="1", sub_part=None, choice_alt=None,
                                  max_marks=3, stem_text="Why did Gandhiji oppose the Rowlatt Act?",
                                  logical_page=1),
                ExtractedQuestion(section="B", question_no="2", sub_part=None, choice_alt=None,
                                  max_marks=2, stem_text="Name two soils of India.", logical_page=2),
            ],
            declared_total=5, declared_count=2)

    import app.extraction.paper_vision as pv

    monkeypatch.setattr(pv, "read_paper_vision", fake_read)
    monkeypatch.setattr(pv, "rasterize_pdf", lambda path: [(b"img", "image/jpeg")] * 2)
    monkeypatch.setattr(pl, "_client", lambda settings: SimpleNamespace(messages=_Messages()))

    before = _counts()
    r = _upload(client, _scan_pdf(2))
    assert r.status_code == 202 and r.json()["route"] == "vision" and r.json()["pages"] == 2
    job_id = r.json()["job_id"]
    job = client.get(f"/platform/ocr-lab/jobs/{job_id}", headers=HEAD).json()
    assert job["status"] == "done", job
    assert seen == {"model": "claude-opus-5", "pages": 2}
    result = job["result"]
    assert result["ocr"]["route"] == "vision" and result["ocr"]["estimated_usd"] > 0
    assert result["checks"]["total_matches"] is True and result["checks"]["read_count"] == 2
    assert lab._job_dir(job_id).joinpath("paper.pdf").exists() is False, "the uploaded pages are not kept"
    assert _counts() == before


def test_a_vision_failure_is_written_to_the_job_not_raised(client, operator, monkeypatch):
    import app.extraction.paper_vision as pv
    from app.extraction.paper_vision import PaperVisionReading

    monkeypatch.setattr(pv, "rasterize_pdf", lambda path: [(b"img", "image/jpeg")])
    monkeypatch.setattr(pv, "read_paper_vision",
                        lambda pages, **kw: PaperVisionReading(refused="nothing readable"))
    r = _upload(client, _scan_pdf(1), map_topics="false")
    job = client.get(f"/platform/ocr-lab/jobs/{r.json()['job_id']}", headers=HEAD).json()
    assert job["status"] == "failed" and "nothing readable" in job["error"]


def test_too_many_pages_and_bad_job_ids_are_refused(client, operator, monkeypatch):
    monkeypatch.setattr(lab, "MAX_PAGES", 1)
    assert _upload(client, _scan_pdf(2), map_topics="false").status_code == 422
    assert client.get("/platform/ocr-lab/jobs/../../etc/passwd", headers=HEAD).status_code in {404, 422}
    assert client.get("/platform/ocr-lab/jobs/notahexid", headers=HEAD).status_code == 404


def test_old_jobs_are_swept(client, operator):
    import os
    import time

    d = lab._root() / ("b" * 32)
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text("{}")
    old = time.time() - lab.JOB_TTL_SECONDS - 60
    os.utime(d, (old, old))
    lab._sweep()
    assert not d.exists()


def test_a_question_that_stops_on_a_stray_letter_is_flagged_as_cut_off():
    from app.api.ocr_lab import _looks_cut_off

    assert _looks_cut_off("Match the following: I. Tilak II. Gandhi III. Nehru IV. E")
    assert _looks_cut_off("Choose the correct option: A. Hindi B.")
    assert not _looks_cut_off("Why did Gandhiji oppose the Rowlatt Act?")
    assert not _looks_cut_off("Name the movement started in 1930 (a) Dandi")


def test_a_science_paper_is_mapped_against_the_science_list(client, operator, monkeypatch):
    class Science:
        def parse(self, **kw):
            body = kw["messages"][0]["content"]
            rows = json.loads(body.split("<questions>\n")[1].split("\n</questions>")[0])
            assert "CBSE Class X Science" in kw["system"][0]["text"] and "C2.10" in kw["system"][1]["text"]
            assert all("section" not in r for r in rows)
            out = [pl._Row(row=r["row"], chapter_id="C2", topic_id="C2.10", confidence="high",
                           syllabus_status="in_syllabus", reason="pH") for r in rows]
            usage = SimpleNamespace(input_tokens=900, output_tokens=300, cache_read_input_tokens=0,
                                    cache_creation_input_tokens=0)
            return SimpleNamespace(parsed_output=pl._Out(mappings=out), usage=usage)

    monkeypatch.setattr(pl, "_client", lambda settings: SimpleNamespace(messages=Science()))
    before = _counts()
    r = _upload(client, _text_pdf(), subject_code="X.SCI")
    assert r.status_code == 202, r.text
    job = client.get(f"/platform/ocr-lab/jobs/{r.json()['job_id']}", headers=HEAD).json()
    assert job["status"] == "done", job
    mapping = job["result"]["mapping"]
    assert mapping["subject"] == "science"
    first = next(iter(mapping["by_address"].values()))
    assert first["chapter"]["title"] == "Acids, Bases and Salts" and first["topic"]["id"] == "C2.10"
    assert _counts() == before
