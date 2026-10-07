"""Classify must not erase a chapter and topic the mapping step settled without doubt.

Reported on real papers, in every subject: the map step placed a question correctly, then the
Classify button replaced its chapter and topic with different ones. These tests pin the
guard (app.api.placement.mapping_hold): a confident mapping stays, the disagreement is
flagged with both answers, and the classifier's tier is still recorded.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

H = lambda school: {"X-API-Key": school["api_key"]}  # noqa: E731


def _paper(client, school, stem="Find the modal class and hence the mode of the frequency distribution"):
    tag = uuid.uuid4().hex[:8]
    aid = client.post("/assessments", headers=H(school), json={
        "subject_code": "X.MATH", "title": f"Keep {tag}", "total_marks": 3}).json()["assessment_id"]
    r = client.post(f"/assessments/{aid}/questions", headers=H(school), json={"questions": [{
        "section": "A", "question_no": "1", "max_marks": 3, "stem_text": stem,
        "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
        "concept_variant": f"keep {tag}"}]})
    assert r.status_code == 200, r.json()
    return aid


def _state(aid):
    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement, TaxonomyNode

    db = SessionLocal()
    try:
        q = db.scalars(select(Question).where(Question.assessment_id == aid)).first()
        chapter = db.get(TaxonomyNode, q.chapter_id).label if q.chapter_id else None
        rows = db.scalars(select(QuestionPlacement).where(QuestionPlacement.question_id == q.id)
                          .order_by(QuestionPlacement.created_at)).all()
        return {"qid": q.id, "chapter": chapter, "section": q.curriculum_section,
                "placements": rows and [(r.source, r.needs_review, r.review_reason, r.tier,
                                         r.reasoning) for r in rows]}
    finally:
        db.close()


def _seed_mapping(aid, *, flagged=False, source="model", section="13.3", code="X.MATH.STATS"):
    """What the map step leaves: the question in a chapter and section, plus its placement."""
    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement, TaxonomyNode

    db = SessionLocal()
    try:
        q = db.scalars(select(Question).where(Question.assessment_id == aid)).first()
        node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
        q.chapter_id, q.curriculum_section = node.id, section
        db.add(QuestionPlacement(question_id=q.id, chapter_id=node.id, curriculum_section=section,
                                 source=source, needs_review=flagged, confidence=0.8,
                                 review_reason="topic_differs" if flagged else None))
        db.commit()
    finally:
        db.close()


def _classify(school, aid, monkeypatch, *, chapter="Surface Areas and Volumes",
              section="12.2", protect=True, topic=None):
    from app.api.placement import _run_placement_job
    from app.classify import anthropic_judge as aj
    from app.classify import topic as topic_module
    from app.classify.judge import Classification
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import PlacementJob

    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "classify_protects_mapping", protect)

    class Chapter:
        def __init__(self, *a, **kw):
            pass

        def classify(self, question, evidence, **kw):
            return Classification(chapter=chapter, curriculum_section=section, tier="Applying",
                                  skill_required="apply a formula", reasoning="the classifier's read",
                                  confidence=0.9)

    class Topic:
        def __init__(self, *a, **kw):
            pass

        def pick(self, stem, chapter_label, headings, passages):
            class C:
                pass
            c = C()
            c.section = topic or next(iter(sorted(headings)), None)
            c.rationale = "topic read"
            return c

    monkeypatch.setattr(aj, "AnthropicJudge", Chapter)
    monkeypatch.setattr(topic_module, "TopicJudge", Topic)
    db = SessionLocal()
    try:
        job = PlacementJob(school_id=school["school_id"], assessment_id=aid)
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()
    _run_placement_job(job_id)
    db = SessionLocal()
    try:
        job = db.get(PlacementJob, job_id)
        return job.status, job.error_detail, job.result
    finally:
        db.close()


def test_a_confident_mapping_survives_a_classifier_that_disagrees(client, school, book, monkeypatch):
    aid = _paper(client, school)
    _seed_mapping(aid)
    before = _state(aid)
    assert before["chapter"] == "Statistics" and before["section"] == "13.3"

    status, error, result = _classify(school, aid, monkeypatch)
    assert status == "succeeded", error
    after = _state(aid)
    assert (after["chapter"], after["section"]) == ("Statistics", "13.3"), "the mapping stands"
    source, flagged, reason, tier, reasoning = after["placements"][-1]
    assert flagged and reason == "classifier_differs"
    assert tier == "Applying", "the classifier's tier is still recorded"
    assert "Kept the mapping's Statistics" in reasoning and "Surface Areas and Volumes" in reasoning
    assert result["kept_mapping"] == 1 and result["kept_mapping_addresses"]


def test_clicking_classify_again_does_not_overwrite_the_held_disagreement(
    client, school, book, monkeypatch,
):
    aid = _paper(client, school)
    _seed_mapping(aid)
    _classify(school, aid, monkeypatch)
    _classify(school, aid, monkeypatch)
    after = _state(aid)
    assert (after["chapter"], after["section"]) == ("Statistics", "13.3")
    assert after["placements"][-1][2] == "classifier_differs"


def test_an_agreeing_classifier_changes_nothing_it_should_not(client, school, book, monkeypatch):
    aid = _paper(client, school)
    _seed_mapping(aid)
    status, error, result = _classify(school, aid, monkeypatch, chapter="Statistics", section="13.3",
                                      topic="13.3")
    assert status == "succeeded", error
    assert result.get("kept_mapping", 0) == 0
    assert _state(aid)["chapter"] == "Statistics"


def test_a_mapping_the_map_step_doubted_is_still_for_the_classifier_to_settle(
    client, school, book, monkeypatch,
):
    aid = _paper(client, school)
    _seed_mapping(aid, flagged=True)
    status, error, result = _classify(school, aid, monkeypatch, chapter="Statistics",
                                      section="13.2", topic="13.2")
    assert status == "succeeded", error
    assert result.get("kept_mapping", 0) == 0
    assert _state(aid)["section"] == "13.2", "the doubted mapping was refined"


def test_a_persons_placement_is_never_overwritten(client, school, book, monkeypatch):
    aid = _paper(client, school)
    _seed_mapping(aid, source="human")
    _classify(school, aid, monkeypatch)
    after = _state(aid)
    assert (after["chapter"], after["section"]) == ("Statistics", "13.3")


def test_with_the_guard_off_classify_overwrites_as_it_used_to(client, school, book, monkeypatch):
    aid = _paper(client, school)
    _seed_mapping(aid)
    status, error, _ = _classify(school, aid, monkeypatch, chapter="Statistics", section="13.2",
                                 topic="13.2", protect=False)
    assert status == "succeeded", error
    assert _state(aid)["section"] == "13.2", "no guard: the classifier's section replaced it"


def test_the_reason_is_a_stored_review_code():
    from app.classify.review_rule import REASONS, ReviewInputs, review_reasons

    assert "classifier_differs" in REASONS
    assert review_reasons(ReviewInputs(classifier_differs=True)) == ["classifier_differs"]
    assert review_reasons(ReviewInputs()) == []


def test_a_different_topic_in_the_same_chapter_is_held_too(client, school, book, monkeypatch):
    aid = _paper(client, school)
    _seed_mapping(aid)
    status, error, result = _classify(school, aid, monkeypatch, chapter="Statistics",
                                      section="13.2", topic="13.2")
    assert status == "succeeded", error
    after = _state(aid)
    assert (after["chapter"], after["section"]) == ("Statistics", "13.3")
    assert result["kept_mapping"] == 1


def test_a_sub_section_of_the_mapped_topic_is_a_refinement_not_a_disagreement(
    client, school, book, monkeypatch,
):
    from app.classify.topic import _related

    assert _related("13.3", "13.3.1") and not _related("13.2", "13.3")
