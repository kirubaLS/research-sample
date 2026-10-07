"""The question lab: one question through the pipeline, nothing written.

The point of these tests is the promise in the module docstring -- the lab never changes
data -- so every run is bracketed by a count of every table it could conceivably touch.
Judges are stubs; no paid API is called.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

KEY = "lab-platform-key"
HEAD = {"X-Platform-Key": KEY}
STEM = "Find the modal class and hence the mode of the frequency distribution"


@pytest.fixture
def operator():
    from app.config import get_settings

    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = KEY
    yield
    settings.platform_admin_key = before


def _counts():
    from app.db import SessionLocal
    from app.models import (
        Assessment,
        AuditLog,
        ConceptFamilyProposal,
        PlacementJob,
        Question,
        QuestionPlacement,
        QuestionSkill,
        QuestionTier,
        TaxonomyNode,
    )

    db = SessionLocal()
    try:
        return {m.__name__: db.scalar(select(func.count()).select_from(m)) for m in (
            Assessment, AuditLog, ConceptFamilyProposal, PlacementJob, Question,
            QuestionPlacement, QuestionSkill, QuestionTier, TaxonomyNode)}
    finally:
        db.close()


def test_the_lab_is_behind_the_operator_key(client, book):
    assert client.post("/platform/question-lab/run",
                       json={"subject_code": "X.MATH", "stem": STEM}).status_code == 404
    assert client.get("/platform/question-lab/find?q=modal").status_code == 404


def test_retrieval_mode_maps_a_question_and_writes_nothing(client, school, book, operator):
    before = _counts()
    r = client.post("/platform/question-lab/run", headers=HEAD,
                    json={"subject_code": "X.MATH", "stem": STEM, "school_id": school["school_id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["wrote_nothing"] is True and body["mode"] == "retrieval"
    final = body["final"]
    assert final["chapter"] == "Statistics" and final["topic"]["section"] == "13.3"
    assert final["topic"]["source"] in {"retrieval", "judge"}
    assert body["retrieval"]["chapter"] == "Statistics" and body["retrieval"]["evidence"]
    assert set(body["signals"]) >= {"gate", "memory", "classifier"}
    assert body["signals"]["memory"]["remembered_questions"] >= 0
    assert body["spend"]["calls"] == 0 and body["spend"]["estimated_usd"] == 0
    assert _counts() == before, "the lab must not write a single row"


def test_a_book_that_is_not_loaded_is_a_clear_conflict(client, operator):
    r = client.post("/platform/question-lab/run", headers=HEAD,
                    json={"subject_code": "X.NOPE", "stem": STEM})
    assert r.status_code == 409 and "no book loaded" in r.text


def test_the_stem_must_be_real_text(client, operator):
    assert client.post("/platform/question-lab/run", headers=HEAD,
                       json={"subject_code": "X.MATH", "stem": "ab"}).status_code == 422


def test_full_mode_needs_a_key_and_says_so(client, book, operator, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    r = client.post("/platform/question-lab/run", headers=HEAD,
                    json={"subject_code": "X.MATH", "stem": STEM, "mode": "full"})
    assert r.status_code == 409 and "ANTHROPIC_API_KEY" in r.text


def test_full_mode_runs_the_judges_reports_the_spend_and_still_writes_nothing(
    client, school, book, operator, monkeypatch,
):
    from app.classify import anthropic_judge as aj
    from app.classify import topic as topic_module
    from app.classify.judge import Classification
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")

    class Chapter:
        def __init__(self, *a, **kw):
            self.calls = self.input_tokens = self.output_tokens = 0
            self.cache_read_tokens = self.cache_write_tokens = 0

        def classify(self, question, evidence, **kw):
            self.calls += 1
            self.input_tokens += 5000
            self.output_tokens += 1500
            return Classification(chapter="Statistics", curriculum_section="13.3", tier="Applying",
                                  skill_required="use the mode formula", reasoning="asks for the mode",
                                  confidence=0.9)

    class Topic:
        def __init__(self, *a, **kw):
            self.calls = self.input_tokens = self.output_tokens = 0
            self.cache_read_tokens = self.cache_write_tokens = 0

        def pick(self, stem, chapter_label, headings, passages):
            self.calls += 1
            self.input_tokens += 900
            self.output_tokens += 400

            class C:
                section = "13.3"
                rationale = "the modal class"
            return C()

    monkeypatch.setattr(aj, "AnthropicJudge", Chapter)
    monkeypatch.setattr(topic_module, "TopicJudge", Topic)

    before = _counts()
    r = client.post("/platform/question-lab/run", headers=HEAD,
                    json={"subject_code": "X.MATH", "stem": STEM, "mode": "full", "marks": 3,
                          "school_id": school["school_id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    final = body["final"]
    assert final["source"] == "judges" and final["tier"] == "Applying"
    assert final["chapter"] == "Statistics" and final["topic"]["section"] == "13.3"
    assert body["spend"]["calls"] == 2 and body["spend"]["models"] == [get_settings().model_classifier]
    assert body["spend"]["estimated_usd"] > 0
    assert body["spend"]["estimated_usd_topic_batched"] <= body["spend"]["estimated_usd"]
    assert _counts() == before


def test_a_stored_question_can_be_found_and_compared_without_changing_it(client, school, book, operator):
    tag = uuid.uuid4().hex[:8]
    headers = {"X-API-Key": school["api_key"]}
    aid = client.post("/assessments", headers=headers, json={
        "subject_code": "X.MATH", "title": f"Lab {tag}", "total_marks": 3}).json()["assessment_id"]
    client.post(f"/assessments/{aid}/questions", headers=headers, json={"questions": [{
        "section": "A", "question_no": "1", "max_marks": 3, "stem_text": f"{STEM} {tag}",
        "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
        "concept_variant": f"lab {tag}"}]})
    found = client.get(f"/platform/question-lab/find?q={tag}", headers=HEAD).json()["questions"]
    assert len(found) == 1 and found[0]["stem"].endswith(tag)
    before = _counts()
    r = client.post("/platform/question-lab/run", headers=HEAD, json={
        "subject_code": "X.MATH", "stem": found[0]["stem"], "question_id": found[0]["question_id"],
        "school_id": school["school_id"]})
    assert r.status_code == 200, r.text
    stored = r.json()["stored"]
    assert stored["question_id"] == found[0]["question_id"] and stored["address"] == "A/1//"
    assert _counts() == before


def test_a_search_with_wildcards_does_not_match_everything(client, operator):
    assert client.get("/platform/question-lab/find?q=%25%25%25", headers=HEAD).json()["questions"] == []
    assert client.get("/platform/question-lab/find?q=ab", headers=HEAD).status_code == 422


def test_the_lab_says_whether_the_subject_runs_the_newer_mapping_logic(client, book, operator):
    body = client.post("/platform/question-lab/run", headers=HEAD,
                       json={"subject_code": "X.MATH", "stem": STEM}).json()
    assert isinstance(body["v2_subject"], bool)
    try:
        from app.mapping.subject_scope import applies
    except ImportError:
        assert body["v2_subject"] is True       # no per-subject gating on this branch
    else:
        assert body["v2_subject"] == applies("X.MATH")
