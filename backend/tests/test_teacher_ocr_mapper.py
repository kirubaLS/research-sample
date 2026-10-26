"""The teacher dashboard's map step decided by the OCR mapper's pipeline.

The reading, saving and confirming steps are the ones the rest of the suite already covers; here
the model is a stub and the question is whether each answer lands on the right chapter, board
unit, section, family and topic, and whether the older judges are left alone."""

from __future__ import annotations

import io
from types import SimpleNamespace

import pymupdf
import pytest
from sqlalchemy import select

from app.config import get_settings

MARK_X = 595 * 0.87


def _pdf(lines) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text in lines:
        page.insert_text((x, y), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


STATS = [
    (60, 60, "Maximum Marks: 3"), (60, 100, "SECTION A"),
    (60, 130, "1. Find the mean of the grouped data by the step-deviation"),
    (60, 144, "method with an assumed mean of 200 and a class size h."),
    (MARK_X, 130, "3"),
]
POEM = [
    (60, 60, "Maximum Marks: 3"), (60, 100, "SECTION C"),
    (60, 130, "1. What does the poet mean by dust of snow shaken from the hemlock tree?"),
    (MARK_X, 130, "3"),
]


class _Stub:
    """A model that picks one topic for every row."""

    def __init__(self, chapter: str | None, topic: str | None, status="in_syllabus"):
        self.chapter, self.topic, self.status = chapter, topic, status
        self.messages = self
        self.systems = []

    def parse(self, **kw):
        import json

        from app.api import prompt_lab as pl

        self.systems.append(kw["system"])
        body = kw["messages"][0]["content"]
        rows = json.loads(body.split("<questions>\n")[1].split("\n</questions>")[0])
        out = [pl._Row(row=r["row"], chapter_id=self.chapter, topic_id=self.topic, confidence="high",
                       syllabus_status=self.status, reason="stub") for r in rows]
        usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
                                cache_creation_input_tokens=0)
        return SimpleNamespace(parsed_output=pl._Out(mappings=out), usage=usage)


@pytest.fixture
def ocr_on(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ocr_mapper_pipeline", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    return settings


def _stage(client, school, subject, lines):
    h = {"X-API-Key": school["api_key"]}
    aid = client.post("/assessments", headers=h, json={
        "subject_code": subject, "title": "OCR mapper", "total_marks": 3}).json()["assessment_id"]
    r = client.post(f"/assessments/{aid}/scan", headers=h,
                    files=[("files", ("p.pdf", io.BytesIO(_pdf(lines)), "application/pdf"))])
    assert r.status_code == 201, r.text
    assert client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={}).status_code == 200
    return aid, h


def _run_map(client, aid, h):
    out = client.post(f"/assessments/{aid}/map", headers=h)
    assert out.status_code == 202, out.text
    return client.get(f"/assessments/{aid}/map/jobs/{out.json()['job_id']}", headers=h)


def test_a_maths_question_is_filed_by_the_ocr_mappers_answer(client, school, book, ocr_on, monkeypatch):
    from app.api import prompt_lab as pl

    stub = _Stub("M13", "M13.1")
    monkeypatch.setattr(pl, "_client", lambda settings: stub)
    # the older judge must not be asked
    monkeypatch.setattr("app.classify.topic.TopicJudge", lambda *a, **k: pytest.fail("old topic judge ran"))
    aid, h = _stage(client, school, "X.MATH", STATS)
    out = _run_map(client, aid, h)
    assert out.status_code == 200, out.text
    body = out.json()
    result = body.get("result") or body
    assert result["mapped"] == 1 and result["retrieval"] == "ocr_mapper:maths", result
    assert result["with_topic"] == 1 and result["spend"]["calls"] >= 1
    placed = client.get(f"/assessments/{aid}/scan", headers=h).json()["questions"][0]
    assert placed["blocked_reason"] is None
    assert placed["mapped_to"]["chapter"] == "Statistics"
    assert placed["mapped_to"]["curriculum_section"] == "13.1"
    assert placed["mapped_to"]["topic"] == "Mean of Grouped Data"
    assert "CBSE Class X Mathematics" in stub.systems[0][0]["text"], "the Maths prompt, as written"


def test_the_classify_step_leaves_the_ocr_mappers_placement_alone(client, school, book, ocr_on, monkeypatch):
    from app.api import prompt_lab as pl
    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement

    monkeypatch.setattr(pl, "_client", lambda settings: _Stub("M13", "M13.1"))
    aid, h = _stage(client, school, "X.MATH", STATS)
    assert _run_map(client, aid, h).status_code == 200
    out = client.post(f"/assessments/{aid}/place", headers=h)
    assert out.status_code == 202, out.text
    job = client.get(f"/assessments/{aid}/place/jobs/{out.json()['job_id']}", headers=h).json()
    result = job.get("result") or job
    assert result.get("pipeline") == "ocr_mapper", job
    db = SessionLocal()
    q = db.scalars(select(Question).where(Question.assessment_id == aid)).one()
    placement = db.scalars(select(QuestionPlacement).where(QuestionPlacement.question_id == q.id)).one()
    db.close()
    assert placement.source == "model" and "OCR mapper (maths)" in placement.reasoning


def test_an_english_poem_has_no_curriculum_chapter_and_stays_staged(
    client, school, book, ocr_on, monkeypatch,
):
    from app.api import prompt_lab as pl

    monkeypatch.setattr(pl, "_client", lambda settings: _Stub("FP1", "FP1.1"))
    aid, h = _stage(client, school, "X.ENG.FF", POEM)
    out = _run_map(client, aid, h)
    result = out.json().get("result") or out.json()
    assert out.status_code == 200 and result["mapped"] == 0 and result["blocked"] == 1, out.text
    placed = client.get(f"/assessments/{aid}/scan", headers=h).json()["questions"][0]
    assert "not a chapter of the X.ENG.FF curriculum" in placed["blocked_reason"]


def test_the_older_path_is_untouched_when_the_setting_is_off(client, school, book, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ocr_mapper_pipeline", False)
    aid, h = _stage(client, school, "X.MATH", STATS)
    out = _run_map(client, aid, h)
    result = out.json().get("result") or out.json()
    assert out.status_code == 200 and str(result["retrieval"]) in {"lexical", "hybrid"}, out.text


def test_subjects_without_an_ocr_mapper_list_keep_the_older_path():
    from app.mapping import teacher_map as tm

    assert tm.profile_for_assessment("X.HIN.KR") is None and tm.profile_for_assessment("X.TAM") is None
    assert tm.profile_for_assessment("X.SCI").name == "science"
    assert tm.profile_for_assessment("X.MATH").name == "maths"
    assert tm.profile_for_assessment("X.ENG.FWF").name == "english"
    assert tm.profile_for_assessment("X.SST").name == "social"
    assert tm.profile_for_assessment("X.HIST").name == "social"


def test_list_chapters_translate_to_the_curriculums(school):
    from app.curriculum import CURRICULA
    from app.mapping import english_taxonomy as et
    from app.mapping import math_taxonomy as mt
    from app.mapping import ocr_mapper_v2 as v2
    from app.mapping import prompt_taxonomy as pt
    from app.mapping import science_taxonomy as st
    from app.mapping import teacher_map as tm

    db_codes = {c.code for cur in CURRICULA.values() for c in cur.chapters}
    for profile, taxonomy in ((v2.SOCIAL, pt.build()), (v2.SCIENCE, st.build())):
        assert all(tm.chapter_code(profile, c, CURRICULA) in db_codes for c in taxonomy.chapters)
    maths = [tm.chapter_code(v2.MATHS, c, CURRICULA) for c in mt.build().chapters]
    assert maths == [c.code for c in CURRICULA["X.MATH"].chapters]
    english = {c.id: tm.chapter_code(v2.ENGLISH, c, CURRICULA) for c in et.build().chapters}
    assert english["FF1"] == "X.ENG.FF.LETTERTOGOD" and english["FW9"] == "X.ENG.FWF.SAVEDTHEEARTH"
    assert all(english[c] is None for c in ("FP1", "R1", "G3", "W1"))
    assert tm.section_of(v2.MATHS, "M13.1", "1") == "13.1"
    assert tm.section_of(v2.ENGLISH, "FF2.3", "3") == "2.3"
    assert tm.section_of(v2.SOCIAL, "H5.3.2", "3.2") == "3.2"
    assert tm.section_of(v2.SCIENCE, "C2.10", "10") == st.unit_numbers()["C2.10"]
