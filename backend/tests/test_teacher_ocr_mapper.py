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


def _english_book():
    """The English books' subject and unit nodes, as set up for a school."""
    from app.curriculum import CURRICULA
    from app.curriculum.apply import apply
    from app.db import SessionLocal

    db = SessionLocal()
    for code in ("X.ENG.FF", "X.ENG.FWF", "X.ENG.WB"):
        apply(db, CURRICULA[code])
    db.close()


def test_an_english_poem_is_filed_under_a_first_flight_chapter_made_on_first_use(
    client, school, book, ocr_on, monkeypatch,
):
    from app.api import prompt_lab as pl
    from app.db import SessionLocal
    from app.models import ChapterBoardUnit, TaxonomyNode

    _english_book()
    monkeypatch.setattr(pl, "_client", lambda settings: _Stub("FP1", "FP1.1"))
    aid, h = _stage(client, school, "X.ENG.FF", POEM)
    out = _run_map(client, aid, h)
    result = out.json().get("result") or out.json()
    assert out.status_code == 200 and result["mapped"] == 1 and result["blocked"] == 0, out.text
    placed = client.get(f"/assessments/{aid}/scan", headers=h).json()["questions"][0]
    assert placed["mapped_to"]["chapter"] == "Dust of Snow (Robert Frost)"
    assert placed["mapped_to"]["curriculum_section"] == "1.1"
    assert placed["mapped_to"]["topic"] == "Meaning, imagery and theme"
    db = SessionLocal()
    chapter = db.scalars(select(TaxonomyNode).where(TaxonomyNode.code == "X.ENG.FF.FP1")).one()
    assert db.scalars(select(ChapterBoardUnit).where(ChapterBoardUnit.chapter_id == chapter.id)).one()
    db.close()
    # a second run makes no second chapter
    from app.mapping import teacher_map as tm

    db = SessionLocal()
    assert tm.ensure_english_chapters(db, chapter.curriculum_version) == 0
    db.close()


def test_the_tier_is_decided_in_the_same_call_and_stored(client, school, book, ocr_on, monkeypatch):
    from app.api import prompt_lab as pl
    from app.classify.current_tier import current_tiers
    from app.db import SessionLocal
    from app.mapping import ocr_mapper_v2 as v2
    from app.models import Question, QuestionPlacement

    class Tiered(_Stub):
        def parse(self, **kw):
            out = super().parse(**kw)
            rows = [v2._TieredRow(**m.model_dump(), cognitive_tier="Analysing, Evaluating & Creating")
                    for m in out.parsed_output.mappings]
            return SimpleNamespace(parsed_output=v2._TieredOut(mappings=rows), usage=out.usage)

    stub = Tiered("M13", "M13.1")
    monkeypatch.setattr(pl, "_client", lambda settings: stub)
    aid, h = _stage(client, school, "X.MATH", STATS)
    assert _run_map(client, aid, h).status_code == 200
    assert len(stub.systems) == 1, "mapping and the tier are one call, not two"
    tier_rules = stub.systems[0][-1]["text"]
    assert "cognitive_tier" in tier_rules and "Remembering & Understanding" in tier_rules
    db = SessionLocal()
    q = db.scalars(select(Question).where(Question.assessment_id == aid)).one()
    tiers, _seen = current_tiers(db, [q.id])
    placement = db.scalars(select(QuestionPlacement).where(QuestionPlacement.question_id == q.id)).one()
    db.close()
    assert tiers[q.id] == "AEC" and placement.tier == "Analysing, Evaluating & Creating"


def test_a_secondary_topic_in_another_chapter_is_recorded_beside_the_primary(
    client, school, book, ocr_on, monkeypatch,
):
    import json

    from app.api import prompt_lab as pl
    from app.db import SessionLocal
    from app.models import Question, QuestionSkill, TaxonomyNode

    class Two(_Stub):
        def parse(self, **kw):
            out = super().parse(**kw)
            for m in out.parsed_output.mappings:
                m.secondary_topic_ids = ["M10.1"]
            return out

    monkeypatch.setattr(pl, "_client", lambda settings: Two("M13", "M13.1"))
    aid, h = _stage(client, school, "X.MATH", STATS)
    assert _run_map(client, aid, h).status_code == 200
    db = SessionLocal()
    q = db.scalars(select(Question).where(Question.assessment_id == aid)).one()
    rows = db.scalars(select(QuestionSkill).where(QuestionSkill.question_id == q.id)).all()
    codes = {db.get(TaxonomyNode, r.node_id).code: r.weight for r in rows}
    db.close()
    assert codes.get("X.MATH.STATS.S13_1") == 1.0, codes
    assert codes.get("X.MATH.CIRCLE.S10_1") == 0.5, codes
    assert json.dumps(codes)


def test_a_subject_without_an_ocr_mapper_list_is_left_staged_with_the_reason(client, school, book, ocr_on):
    aid, h = _stage(client, school, "X.TAM", STATS)
    out = _run_map(client, aid, h)
    result = out.json().get("result") or out.json()
    assert out.status_code == 200 and result["mapped"] == 0 and result["blocked"] == 1, out.text
    placed = client.get(f"/assessments/{aid}/scan", headers=h).json()["questions"][0]
    assert "no topic list or prompt for X.TAM" in placed["blocked_reason"]


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
    assert english["FP1"] == "X.ENG.FF.FP1" and english["R1"] == "X.ENG.WB.R1"
    assert english["G3"] == "X.ENG.WB.G3" and english["W1"] == "X.ENG.WB.W1"
    assert tm.section_of(v2.MATHS, "M13.1", "1") == "13.1"
    assert tm.section_of(v2.ENGLISH, "FF2.3", "3") == "2.3"
    assert tm.section_of(v2.SOCIAL, "H5.3.2", "3.2") == "3.2"
    assert tm.section_of(v2.SCIENCE, "C2.10", "10") == st.unit_numbers()["C2.10"]


def test_topics_the_model_names_in_its_reason_are_kept_as_matching_topics():
    from app.mapping import prompt_taxonomy as pt
    from app.mapping import teacher_map as tm

    result = {"topic": {"id": "H5.2.1"}, "secondary": [{"id": "H5.9"}], "reason_full": (
        "tests four events: Gutenberg (H5.2.1), Marco Polo (H5.2), Bengal Gazette (H5.6.2), "
        "Vernacular Press Act (H5.9) and a made-up ZZ9.9")}
    named = tm.topics_named_in(result, pt.build())
    # the primary, one already listed and an unknown ID are left out
    assert [x["id"] for x in named] == ["H5.2", "H5.6.2"]


def test_a_list_of_roman_numerals_ending_in_i_is_not_a_cut_off_stem():
    from app.api.ocr_lab import _looks_cut_off

    assert not _looks_cut_off("Options : (A) III, II, IV, I (B) II, III, I, IV (D) II, III, IV, I")
    assert _looks_cut_off("Match the following: I. Tilak II. Gandhi III. Nehru IV. E")


def test_the_teacher_flow_does_not_flag_thin_book_support(client, school, book, ocr_on, monkeypatch):
    from app.api import prompt_lab as pl
    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement

    monkeypatch.setattr(pl, "_client", lambda settings: _Stub("M13", "M13.1"))
    aid, h = _stage(client, school, "X.MATH", STATS)
    assert _run_map(client, aid, h).status_code == 200
    db = SessionLocal()
    q = db.scalars(select(Question).where(Question.assessment_id == aid)).one()
    placement = db.scalars(select(QuestionPlacement).where(QuestionPlacement.question_id == q.id)).one()
    db.close()
    assert placement.needs_review is False, "a confident answer is not flagged for the book-text check"
