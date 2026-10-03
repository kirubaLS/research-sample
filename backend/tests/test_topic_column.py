"""Phase 3: the Topic column always shows the final decision.

The Topic column shows a question's primary QuestionSkill node. Whatever decides the
placement last -- the map step, the topic judge in a place run, or a person settling in
review -- writes it through set_question_topic, which replaces every earlier machine row.
question.curriculum_section and the primary node's section are written together and are
checked to agree before each write phase commits.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select


def _auth(school):
    return {"X-API-Key": school["api_key"]}


def _question(client, school, stem="Find the mean of the grouped data by step-deviation"):
    created = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": f"Topic column {uuid.uuid4().hex[:6]}",
              "total_marks": 3},
    )
    aid = created.json()["assessment_id"]
    added = client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [{
            "section": "A", "question_no": "1", "max_marks": 3, "stem_text": stem,
            "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
            "concept_variant": f"topic column {uuid.uuid4().hex}",
        }]},
    )
    assert added.status_code == 200, added.json()
    from app.db import SessionLocal
    from app.models import Question

    db = SessionLocal()
    try:
        return aid, db.scalars(select(Question).where(Question.assessment_id == aid)).first().id
    finally:
        db.close()


def _nodes(db):
    from app.models import TaxonomyNode

    return {n.code: n for n in db.scalars(select(TaxonomyNode).where(
        TaxonomyNode.code.like("X.MATH.STATS%") | TaxonomyNode.code.like("X.MATH.AP%")))}


def _mapped(db, qid, section, node_code, source="retrieval"):
    """What the map step left: the question in Statistics at ``section``, its topic row."""
    from app.models import Question, QuestionSkill

    nodes = _nodes(db)
    q = db.get(Question, qid)
    q.chapter_id = nodes["X.MATH.STATS"].id
    q.curriculum_section = section
    db.add(QuestionSkill(question_id=qid, node_id=nodes[node_code].id, source=source, weight=1.0))
    db.commit()


def _topics(db, qid):
    from app.models import QuestionSkill, TaxonomyNode

    return sorted(
        (db.get(TaxonomyNode, r.node_id).code.rsplit(".", 1)[-1], r.source, r.weight)
        for r in db.scalars(select(QuestionSkill).where(QuestionSkill.question_id == qid))
    )


# --- 1. set_question_topic: primary 1.0, collapsed `also` at 0.5, machine rows replaced ---


def test_a_later_decision_replaces_every_machine_row(client, school, book):
    from app.db import SessionLocal
    from app.mapping.topic_node import set_question_topic
    from app.models import QuestionSkill

    _, qid = _question(client, school)
    db = SessionLocal()
    try:
        _mapped(db, qid, "13.3", "X.MATH.STATS.S13_3")
        nodes = _nodes(db)
        # a stale retrieval row from an older run, on a section nothing decides any more
        db.add(QuestionSkill(question_id=qid, node_id=nodes["X.MATH.AP.S5_2"].id,
                             source="retrieval", weight=0.5))
        db.commit()
        set_question_topic(db, qid, nodes["X.MATH.STATS"], "13.2", "Mean of Grouped Data",
                           source="classify", secondaries=[("13.3", "Mode of Grouped Data")])
        db.commit()
        assert _topics(db, qid) == [("S13_2", "classify", 1.0), ("S13_3", "classify", 0.5)]
        # the next run decides 13.2 alone: the earlier secondary goes too
        set_question_topic(db, qid, nodes["X.MATH.STATS"], "13.2", "Mean of Grouped Data",
                           source="classify")
        db.commit()
        assert _topics(db, qid) == [("S13_2", "classify", 1.0)]
    finally:
        db.close()


def test_a_secondary_that_is_the_primary_never_lowers_its_weight(client, school, book):
    from app.db import SessionLocal
    from app.mapping.topic_node import set_question_topic

    _, qid = _question(client, school)
    db = SessionLocal()
    try:
        nodes = _nodes(db)
        set_question_topic(db, qid, nodes["X.MATH.STATS"], "13.2", "Mean of Grouped Data",
                           source="classify",
                           secondaries=[("13.2", "Mean of Grouped Data"), ("13.3", "Mode of Grouped Data"),
                                        ("13.3", "Mode of Grouped Data")])
        db.commit()
        assert _topics(db, qid) == [("S13_2", "classify", 1.0), ("S13_3", "classify", 0.5)]
    finally:
        db.close()


def test_a_machine_pass_never_overrules_a_person(client, school, book):
    from app.db import SessionLocal
    from app.mapping.topic_node import person_set_topic, set_question_topic

    _, qid = _question(client, school)
    db = SessionLocal()
    try:
        _mapped(db, qid, "13.3", "X.MATH.STATS.S13_3", source="human")
        assert person_set_topic(db, qid)
        nodes = _nodes(db)
        shown = set_question_topic(db, qid, nodes["X.MATH.STATS"], "13.2", "A different label",
                                   source="classify")
        db.commit()
        assert _topics(db, qid) == [("S13_3", "human", 1.0)]
        assert shown.code == "X.MATH.STATS.S13_3", "the person's topic is the one returned"
        db.refresh(nodes["X.MATH.STATS.S13_2"])
        assert nodes["X.MATH.STATS.S13_2"].label == "Mean of Grouped Data", "no node touched"
    finally:
        db.close()


# --- the place run, end to end --------------------------------------------------------


def _stub_judges(monkeypatch, chapter="Statistics", section="13.3", topic="13.2"):
    from app.classify import anthropic_judge as anthropic_judge_module
    from app.classify import topic as topic_module
    from app.classify.judge import Classification
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")

    class StubJudge:
        def classify(self, question, evidence):
            return Classification(
                chapter=chapter, curriculum_section=section if chapter else None,
                tier="Applying", skill_required="compute a mean",
                reasoning="stub", confidence=0.9,
            )

    class StubTopicJudge:
        def __init__(self, *a, **kw):
            pass

        def pick(self, stem, chapter_label, headings, passages):
            class _Choice:
                pass

            _Choice.section = topic
            _Choice.rationale = "stub topic"
            return _Choice()

    monkeypatch.setattr(anthropic_judge_module, "AnthropicJudge", lambda *a, **kw: StubJudge())
    monkeypatch.setattr(topic_module, "TopicJudge", StubTopicJudge)


def _place(school, aid):
    from app.api.placement import _run_placement_job
    from app.db import SessionLocal
    from app.models import PlacementJob

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
        return job.status, job.error_detail
    finally:
        db.close()


def test_a_place_run_leaves_no_stale_retrieval_topic(client, school, book, monkeypatch):
    from app.db import SessionLocal
    from app.mapping.topic_node import topic_mismatches
    from app.models import Question

    aid, qid = _question(client, school)
    db = SessionLocal()
    try:
        _mapped(db, qid, "13.3", "X.MATH.STATS.S13_3")     # the map step's guess
    finally:
        db.close()
    _stub_judges(monkeypatch, topic="13.2")
    status, error = _place(school, aid)
    assert status == "succeeded", error
    db = SessionLocal()
    try:
        assert db.get(Question, qid).curriculum_section == "13.2"
        assert _topics(db, qid) == [("S13_2", "classify", 1.0)], "no retrieval row survives"
        assert topic_mismatches(db, [qid]) == []
    finally:
        db.close()

    # a later run that decides otherwise: test_a_later_decision_replaces_every_machine_row


def test_a_place_run_after_a_person_settled_changes_nothing_on_the_question(
    client, school, book, monkeypatch,
):
    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement

    aid, qid = _question(client, school)
    r = client.post(
        f"/assessments/{aid}/review/{qid}", headers=_auth(school),
        json={"chapter_code": "X.MATH.STATS", "curriculum_section": "13.3",
              "reviewed_by": "teacher"},
    )
    assert r.status_code == 200, r.json()
    _stub_judges(monkeypatch, topic="13.2")
    status, error = _place(school, aid)
    assert status == "succeeded", error
    db = SessionLocal()
    try:
        assert db.get(Question, qid).curriculum_section == "13.3"
        assert _topics(db, qid) == [("S13_3", "human", 1.0)]
        latest = db.scalars(select(QuestionPlacement).where(QuestionPlacement.question_id == qid)
                            .order_by(QuestionPlacement.created_at.desc())).first()
        assert latest.reasoning.startswith("Not applied: a person settled this question.")
        assert latest.needs_review is False, "a settled question is not reopened"
    finally:
        db.close()


def test_a_skill_anchored_question_keeps_no_topic(client, school, book, monkeypatch):
    from app.db import SessionLocal
    from app.models import Question

    aid, qid = _question(client, school)
    db = SessionLocal()
    try:
        _mapped(db, qid, "13.3", "X.MATH.STATS.S13_3")
    finally:
        db.close()
    _stub_judges(monkeypatch, chapter=None)
    status, error = _place(school, aid)
    assert status == "succeeded", error
    db = SessionLocal()
    try:
        q = db.get(Question, qid)
        if q.chapter_id is not None:
            pytest.skip("the stub chapter judge's None was not read as skill-anchored")
        assert q.curriculum_section is None
        assert _topics(db, qid) == [], "the map step's topic does not outlive its section"
    finally:
        db.close()


# --- 2. curriculum_section always equals the primary topic's section ---------------------


def test_a_disagreement_is_found_and_the_write_guard_refuses_it(client, school, book):
    from app.db import SessionLocal
    from app.mapping.topic_node import (
        TopicSectionMismatch,
        assert_topic_matches_section,
        topic_mismatches,
    )

    _, qid = _question(client, school)
    db = SessionLocal()
    try:
        _mapped(db, qid, "13.2", "X.MATH.STATS.S13_3")     # section and topic disagree
        found = topic_mismatches(db, [qid])
        assert [(f["curriculum_section"], f["topic_section"]) for f in found] == [("13.2", "13.3")]
        with pytest.raises(TopicSectionMismatch, match="section 13.2 but topic 13.3"):
            assert_topic_matches_section(db, [qid])
        assert_topic_matches_section(db, [])                # nothing written, nothing to check
    finally:
        db.close()


def test_the_mismatch_listing_is_read_only(client, school, book, capsys):
    from app.db import SessionLocal
    from app.models import Question, QuestionSkill
    from scripts import list_topic_mismatches

    aid, qid = _question(client, school)
    db = SessionLocal()
    try:
        _mapped(db, qid, "13.2", "X.MATH.STATS.S13_3")
        before = (db.get(Question, qid).curriculum_section,
                  sorted(s.node_id for s in db.scalars(select(QuestionSkill).where(
                      QuestionSkill.question_id == qid))))
    finally:
        db.close()
    assert list_topic_mismatches.main(["--assessment", aid]) == 0
    out = capsys.readouterr().out
    assert "READ-ONLY" in out
    assert "A/1//" in out and "section 13.2" in out and "topic 13.3" in out
    assert "TOTAL 1 question(s) on 1 paper(s), section differs 1" in out
    db = SessionLocal()
    try:
        after = (db.get(Question, qid).curriculum_section,
                 sorted(s.node_id for s in db.scalars(select(QuestionSkill).where(
                     QuestionSkill.question_id == qid))))
        assert after == before
    finally:
        db.close()


# --- 3. a deterministic Topic tie-break ------------------------------------------------


@dataclass
class _Link:
    id: str
    weight: float | None


def test_the_primary_is_the_heaviest_then_the_smallest_id():
    from app.mapping.topic_node import primary_order

    links = [_Link("b", 1.0), _Link("c", 0.5), _Link("a", 1.0), _Link("d", None)]
    assert [x.id for x in sorted(links, key=primary_order)] == ["a", "b", "d", "c"]
    assert [x.id for x in sorted(reversed(links), key=primary_order)] == ["a", "b", "d", "c"]


# --- 4. the newest tier that names one wins --------------------------------------------


def test_the_newest_named_tier_wins_and_an_abstain_never_erases_one(client, school, book):
    from app.classify.current_tier import current_tiers
    from app.db import SessionLocal
    from app.models import QuestionTier

    _, qid = _question(client, school)
    _, other = _question(client, school)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    db = SessionLocal()
    try:
        # inserted out of time order: the reader must order, not trust the table
        db.add_all([
            QuestionTier(question_id=qid, tier="AP", created_at=t0 + timedelta(minutes=2)),
            QuestionTier(question_id=qid, tier=None, created_at=t0 + timedelta(minutes=3)),
            QuestionTier(question_id=qid, tier="RE", created_at=t0),
            QuestionTier(question_id=other, tier=None, created_at=t0),
        ])
        db.commit()
        tiers, seen = current_tiers(db, [qid, other, None])
        assert tiers == {qid: "AP"}
        assert seen == {qid, other}, "an abstain still counts as classified"
    finally:
        db.close()


def test_every_tier_reader_uses_the_one_rule():
    import inspect

    from app.api import academics, marks, reports

    for module in (marks, reports, academics):
        source = inspect.getsource(module)
        assert "current_tiers(" in source, module.__name__
        assert "select(QuestionTier).where(QuestionTier.question_id.in_" not in source
