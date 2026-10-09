"""The prompt mapper: a taxonomy built from the book map, answers checked against it, nothing
written. The model is a stub; no paid API is called."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

# app.db reads the database URL at import time and conftest sets it in a fixture, so the
# modules under test are imported by the autouse fixture below, not here.
lab = pt = None

KEY = "prompt-lab-key"
HEAD = {"X-Platform-Key": KEY}


@pytest.fixture(autouse=True)
def _modules(_tmp_db):
    global lab, pt
    from app.api import prompt_lab
    from app.mapping import prompt_taxonomy

    lab, pt = prompt_lab, prompt_taxonomy


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


# --- the taxonomy --------------------------------------------------------------------------


def test_every_social_science_chapter_is_in_the_taxonomy():
    t = pt.build()
    assert [c.id for c in t.chapters] == (
        [f"H{i}" for i in range(1, 6)] + [f"G{i}" for i in range(1, 8)]
        + [f"P{i}" for i in range(1, 6)] + [f"E{i}" for i in range(1, 6)])
    assert t.topic_count > 250


def test_the_topics_a_hand_written_list_lost_are_all_there():
    """The reason for generating it: each crop, the soil types, the consumer-court sections."""
    t = pt.build()
    titles = {x.title for c in t.chapters for x in c.topics}
    for must in ("Rice", "Jute", "Alluvial Soils", "Black Soil", "Textile Industry", "Sugar Industry",
                 "Where should consumers go to get justice?", "Linguistic States", "Communalism",
                 "Secular state", "Currency", "Deposits with Banks"):
        assert must in titles, must


def test_topics_the_book_does_not_have_are_not_offered():
    titles = {x.title.lower() for c in pt.build().chapters for x in c.topics}
    for invented in ("hazards of mining", "human development report", "classification of industries",
                     "variety of credit arrangements"):
        assert invented not in titles, invented


def test_ids_translate_back_to_the_real_chapter_and_printed_section():
    t = pt.build()
    topic = t.topic("H5.3.2")
    chapter = t.chapter("H5")
    assert chapter.code == "X.HIST.PRINTCULTURE" and topic.number == "3.2"
    assert "Religious Debates" in topic.title
    assert pt.major_topic(chapter, topic) == "3.2"
    # a deep topic reports the two-level topic the reports use
    cotton = next(x for x in t.chapter("G4").topics if x.title == "Cotton")
    assert pt.major_topic(t.chapter("G4"), cotton) == "2.1"


def test_a_boxs_title_is_a_hint_for_its_parent_not_a_topic():
    t = pt.build()
    g3 = t.chapter("G3")
    assert not any(x.title == "Sardar Sarovar Dam" for x in g3.topics)
    parent = next(x for x in g3.topics if x.number == "2")
    assert "Sardar Sarovar Dam" in parent.keywords


def test_hints_are_short_specific_terms_and_every_topic_has_some():
    bare = 0
    for c in pt.build().chapters:
        for x in c.topics:
            assert len(x.keywords) <= pt.KEYWORDS_PER_TOPIC, x.id
            bare += not x.keywords
            for k in x.keywords:
                assert len(k.split()) <= 6 and len(k) >= 3, (x.id, k)
                assert k.split()[0].lower() not in pt._SENTENCE_STARTERS, (x.id, k)
    assert bare == 0, "every topic carries hints, so none is described by its title alone"
    t = pt.build()
    assert len(t.topic("H5.3.3").keywords) >= pt.MIN_TERMS


def test_hints_come_from_the_sections_own_text():
    t = pt.build()
    assert "Index of Prohibited Books" in t.topic("H5.3.3").keywords
    assert any("luvial" in k or k in {"Khadar", "bangar"} for k in t.topic("G1.7.1.1").keywords)


def test_the_rendered_taxonomy_is_cacheable_size_and_indented_by_depth():
    text = pt.render()
    assert 4096 < len(text) // 4 < 20000, "big enough to cache on Haiku, small enough to be cheap"
    assert "\nH5.3.2 | " not in text and "      H5.3.2 | " in text or "    H5.3.2 | " in text
    assert pt.render(subjects={"X.GEO"}).startswith("G1 | ")


# --- resolving answers -----------------------------------------------------------------------


def _row(**kw):
    base = dict(row=0, chapter_id="H2", topic_id="H2.1.2", secondary_topic_ids=[], confidence="high",
                syllabus_status="in_syllabus", reason="Rowlatt Act")
    return lab._Row(**{**base, **kw})


def test_a_good_answer_is_translated_and_settled():
    r = lab.resolve(pt.build(), _row(), None)
    assert r["chapter"]["code"] == "X.HIST.NATIONALISM_INDIA" and r["topic"]["number"] == "1.2"
    assert r["topic"]["title"] == "The Rowlatt Act" and r["needs_review"] is False


def test_an_invented_id_is_reported_and_flagged_never_trusted():
    r = lab.resolve(pt.build(), _row(topic_id="H2.9.9"), None)
    assert r["topic"] is None and r["needs_review"] and "unknown topic id H2.9.9" in r["problems"][0]


def test_a_topic_in_another_chapter_than_named_uses_the_topics_chapter_and_flags_it():
    r = lab.resolve(pt.build(), _row(chapter_id="H1", topic_id="H2.1.2"), None)
    assert r["chapter"]["id"] == "H2" and r["needs_review"] and "topic H2.1.2 is in H2" in r["problems"][0]


def test_a_section_letter_that_contradicts_the_answer_is_flagged():
    r = lab.resolve(pt.build(), _row(), "B")          # B is Geography, the answer is History
    assert r["needs_review"] and "section B" in r["problems"][0]
    assert lab.resolve(pt.build(), _row(), "A")["needs_review"] is False


def test_low_confidence_and_not_in_syllabus_always_go_to_review():
    assert lab.resolve(pt.build(), _row(confidence="low"), None)["needs_review"]
    assert lab.resolve(pt.build(), _row(syllabus_status="partial"), None)["needs_review"]
    nf = lab.resolve(pt.build(), _row(chapter_id=None, topic_id=None, syllabus_status="not_found"), None)
    assert nf["topic"] is None and nf["needs_review"]


def test_secondary_topics_are_checked_and_the_primary_is_not_repeated():
    r = lab.resolve(pt.build(), _row(secondary_topic_ids=["H2.1.1", "H2.1.2", "ZZ.9"]), None)
    assert [s["id"] for s in r["secondary"]] == ["H2.1.1"]
    assert any("ZZ.9" in p for p in r["problems"])


def test_a_missing_answer_is_a_flagged_row_not_a_crash():
    r = lab.resolve(pt.build(), None, None)
    assert r["needs_review"] and r["topic"] is None


# --- the route -------------------------------------------------------------------------------


class _Messages:
    def __init__(self, answers):
        self.answers, self.requests = answers, []

    def parse(self, **kw):
        self.requests.append(kw)
        rows = json.loads(kw["messages"][0]["content"].split("<questions>\n")[1].split("\n</questions>")[0])
        out = lab._Out(mappings=[self.answers(r) for r in rows])
        usage = SimpleNamespace(input_tokens=1200, output_tokens=300,
                                cache_read_input_tokens=7000, cache_creation_input_tokens=0)
        return SimpleNamespace(parsed_output=out, usage=usage)


def _stub(monkeypatch, answers):
    messages = _Messages(answers)
    monkeypatch.setattr(lab, "_client", lambda settings: SimpleNamespace(messages=messages))
    return messages


def _counts():
    from app.db import SessionLocal
    from app.models import Assessment, AuditLog, Question, QuestionPlacement, QuestionSkill, TaxonomyNode

    db = SessionLocal()
    try:
        return {m.__name__: db.scalar(select(func.count()).select_from(m))
                for m in (Assessment, AuditLog, Question, QuestionPlacement, QuestionSkill, TaxonomyNode)}
    finally:
        db.close()


def test_the_routes_are_behind_the_operator_key(client):
    r = client.post("/platform/prompt-lab/run", json={"questions": [{"text": "abc def"}]})
    assert r.status_code == 404
    assert client.get("/platform/prompt-lab/taxonomy").status_code == 404


def test_the_taxonomy_route_says_what_the_model_is_shown(client, operator):
    body = client.get("/platform/prompt-lab/taxonomy?full=1", headers=HEAD).json()
    assert body["chapters"] == 22 and body["topics"] > 250 and body["model"] == "claude-haiku-4-5"
    assert "H5.3.2" in body["text"] and body["approx_tokens"] > 4096
    assert client.get("/platform/prompt-lab/taxonomy", headers=HEAD).json()["text"] is None


def test_a_run_maps_questions_with_haiku_and_a_cached_taxonomy_and_writes_nothing(
    client, operator, monkeypatch,
):
    messages = _stub(monkeypatch, lambda r: lab._Row(
        row=r["row"], chapter_id="H2", topic_id="H2.1.2", confidence="high",
        syllabus_status="in_syllabus", reason="Rowlatt"))
    before = _counts()
    r = client.post("/platform/prompt-lab/run", headers=HEAD, json={"questions": [
        {"text": "Why did Gandhiji oppose the Rowlatt Act?", "section": "A"},
        {"text": "Explain the Rowlatt Act of 1919."}]})
    assert r.status_code == 200, r.text
    body = r.json()
    # one call for the History row (shown only History's list), one for the row with no section
    assert body["model"] == "claude-haiku-4-5" and body["calls"] == 2
    assert body["results"][0]["topic"]["title"] == "The Rowlatt Act"
    assert body["summary"]["questions"] == 2 and body["summary"]["in_syllabus"] == 2
    assert body["spend"]["estimated_usd"] > 0 and body["wrote_nothing"] is True
    request = next(r for r in messages.requests if "H5.3.2" in r["system"][1]["text"]
                   and "G1.7.1.1" not in r["system"][1]["text"])
    assert request["model"] == "claude-haiku-4-5"
    taxonomy_block = request["system"][1]
    assert taxonomy_block["cache_control"] == {"type": "ephemeral"}
    assert any("G1.7.1.1" in r["system"][1]["text"] for r in messages.requests), "no section: the whole list"
    assert _counts() == before


def test_questions_are_sent_in_batches_and_one_failed_batch_does_not_lose_the_rest(
    client, operator, monkeypatch,
):
    calls = {"n": 0}

    class Flaky(_Messages):
        def parse(self, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("overloaded")
            return super().parse(**kw)

    messages = Flaky(lambda r: lab._Row(row=r["row"], chapter_id="G5", topic_id="G5.4.1.1",
                                        confidence="medium", syllabus_status="in_syllabus", reason="coal"))
    monkeypatch.setattr(lab, "_client", lambda settings: SimpleNamespace(messages=messages))
    qs = [{"text": f"Question about coal number {i}"} for i in range(lab.BATCH + 5)]
    body = client.post("/platform/prompt-lab/run", headers=HEAD, json={"questions": qs}).json()
    assert body["calls"] == 1 and len(body["errors"]) == 1 and "rows 0-19" in body["errors"][0]
    assert body["results"][0]["topic"] is None and body["results"][0]["needs_review"]
    assert body["results"][lab.BATCH]["topic"]["title"] == "Coal"


def test_limits_and_missing_key_are_clear(client, operator, monkeypatch):
    from app.config import get_settings

    too_many = [{"text": f"question number {i}"} for i in range(lab.MAX_ROWS + 1)]
    assert client.post("/platform/prompt-lab/run", headers=HEAD,
                       json={"questions": too_many}).status_code == 422
    assert client.post("/platform/prompt-lab/run", headers=HEAD, json={"questions": []}).status_code == 422
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    r = client.post("/platform/prompt-lab/run", headers=HEAD, json={"questions": [{"text": "abc def"}]})
    assert r.status_code == 409 and "ANTHROPIC_API_KEY" in r.text


def test_a_stored_paper_is_mapped_and_compared_with_its_saved_mapping(
    client, school, operator, monkeypatch,
):
    import uuid

    from app.db import SessionLocal
    from app.models import Question, TaxonomyNode

    tag = uuid.uuid4().hex[:8]
    headers = {"X-API-Key": school["api_key"]}
    aid = client.post("/assessments", headers=headers, json={
        "subject_code": "X.MATH", "title": f"Prompt {tag}", "total_marks": 2}).json()["assessment_id"]
    client.post(f"/assessments/{aid}/questions", headers=headers, json={"questions": [{
        "section": "A", "question_no": "1", "max_marks": 2,
        "stem_text": f"Why was the Rowlatt Act opposed? {tag}",
        "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
        "concept_variant": f"p {tag}"}]})
    db = SessionLocal()
    try:
        q = db.scalars(select(Question).where(Question.assessment_id == aid)).first()
        # the saved mapping is History: Nationalism in India, section 1.2
        node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.STATS"))
        q.chapter_id, q.curriculum_section = node.id, "13.3"
        db.commit()
        qid = q.id
    finally:
        db.close()
    _stub(monkeypatch, lambda r: lab._Row(row=r["row"], chapter_id="H2", topic_id="H2.1.2",
                                          confidence="high", syllabus_status="in_syllabus", reason="x"))
    before = _counts()
    body = client.post("/platform/prompt-lab/run", headers=HEAD, json={"assessment_id": aid}).json()
    row = body["results"][0]
    assert row["question_id"] == qid and row["stored"]["chapter"] == "Statistics"
    assert row["stored"]["chapter_agrees"] is False
    assert body["summary"]["compared"] == 1 and body["summary"]["chapter_agrees"] == 0
    assert _counts() == before


def test_the_rules_state_the_closed_list_and_do_not_tell_the_model_nobody_checks():
    assert "CLOSED list" in lab.RULES and "differ from the numbers printed" in lab.RULES
    assert "H5.3.3 are valid" in lab.RULES and "opening text" in lab.RULES
    assert "E4.4" in lab.RULES and "E4.5" in lab.RULES
    assert "Nobody will review" not in lab.RULES and "## Before you answer" in lab.RULES
    assert "describes the TEXTBOOK" in lab.RULES and "describes YOUR certainty" in lab.RULES
    t = pt.build()
    for tid in ("E4.4", "E4.5", "H5.3.3"):
        assert t.topic(tid) is not None, tid


def test_an_answer_with_an_id_the_list_does_not_have_is_asked_again_once(client, operator, monkeypatch):
    seen = []

    def answer(r):
        seen.append(r.get("note"))
        good = r.get("note") is not None
        return lab._Row(row=r["row"], chapter_id="G5", topic_id="G5.9.9" if not good else "G5.2",
                        confidence="high", syllabus_status="in_syllabus", reason="x",
                        considered=["G5.2", "NOPE9"])

    _stub(monkeypatch, answer)
    body = client.post("/platform/prompt-lab/run", headers=HEAD, json={"questions": [
        {"text": "Which mineral is the chief source of aluminium?", "section": "B"}]}).json()
    assert body["calls"] == 2 and any(n and "G5.9.9" in n for n in seen)
    r = body["results"][0]
    assert r["topic"]["id"] == "G5.2" and not r["problems"]
    assert r["considered"] == ["G5.2"], "an unknown ID in considered is dropped, not shown"
