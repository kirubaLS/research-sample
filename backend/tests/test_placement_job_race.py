"""A principal can delete a paper at any moment, including while a teacher's "Read and
classify" job is still mid-flight. The job's write phase used to insert a QuestionPlacement
and a QuestionTier row for every classified question unconditionally -- if the question had
already been deleted (the paper removed underneath the running job), that insert violated
the hard FK both tables carry onto question.id. The failure landed on whichever transaction
reached the conflict second, which was sometimes the delete itself: an unrelated concurrent
placement job could make deleting a paper fail outright, intermittently, for no reason a
principal reading "can't delete this paper" could ever explain."""

from __future__ import annotations

from contextlib import contextmanager

import pytest


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@contextmanager
def _foreign_keys_enforced():
    """Postgres enforces foreign keys unconditionally; sqlite, used only in tests, does not
    unless told to -- exactly why this race's FK violation could pass every test here and
    still 500 in production."""
    from sqlalchemy import event

    from app.db import engine

    def _enable(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    if engine.dialect.name != "sqlite":
        yield
        return
    event.listen(engine, "connect", _enable)
    engine.dispose()
    try:
        yield
    finally:
        event.remove(engine, "connect", _enable)
        engine.dispose()


@pytest.fixture
def paper(client, school):
    import uuid

    tag = uuid.uuid4().hex[:8]
    created = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": f"Race Test {tag}", "total_marks": 4},
    )
    aid = created.json()["assessment_id"]
    added = client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 2,
             "stem_text": "The slant height of a right circular cone of base diameter 14 cm",
             "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME",
             "concept_variant": f"cone slant height {tag}"},
            {"section": "A", "question_no": "2", "max_marks": 2,
             "stem_text": "The slant height of a right circular cone of base diameter 20 cm",
             "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME",
             "concept_variant": f"cone slant height wide {tag}"},
        ]},
    )
    assert added.status_code == 200, added.json()
    return aid


def test_a_question_deleted_while_its_placement_job_is_in_flight_is_skipped_not_inserted(
    client, school, paper, book,
):
    """Simulates the exact race: the job's classifier call has already returned (result in
    hand, naming a question by id), but that question was removed in the meantime -- the
    same state a concurrent delete_assessment leaves the write phase discovering. Mocks
    place_paper directly (rather than routing through real retrieval, which is free to
    change what it returns for reasons unrelated to this race) so the write phase is
    exercised against a result that unambiguously references a question no longer there."""
    from sqlalchemy import select

    from app.api import placement as placement_module
    from app.classify import anthropic_judge as anthropic_judge_module
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import PlacementJob, Question, QuestionPlacement, QuestionTier

    class StubJudge:
        def classify(self, question, evidence):
            raise AssertionError("place_paper is mocked; the judge should never be called")

    class StubJudgeFactory:
        def __new__(cls, *a, **kw):
            return StubJudge()

    settings = get_settings()
    before_key = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    db = SessionLocal()
    try:
        question_1_id = db.scalars(
            select(Question.id).where(Question.assessment_id == paper, Question.question_no == "1")
        ).first()
        job = PlacementJob(school_id=school["school_id"], assessment_id=paper)
        db.add(job)
        db.commit()
        job_id = job.id

        # The race: gone by the time the write phase runs, exactly as delete_assessment's
        # own bulk-delete of Question would leave it while this job was still in flight.
        db.execute(Question.__table__.delete().where(Question.id == question_1_id))
        db.commit()
    finally:
        db.close()

    from app.classify.pipeline import PaperPlacement, PlacedQuestion

    def fake_place_paper(*args, **kwargs):
        return PaperPlacement(
            questions=[PlacedQuestion(
                question_id=question_1_id, marks=2.0,
                chapter="Surface Areas and Volumes", board_unit=None, curriculum_section=None,
                tier="Applying", skill_required="", confidence=0.9, reasoning="a cone",
            )],
            feasible=True, note="", residual={}, reviewed_count=0,
        )

    original_place_paper = placement_module.place_paper
    original_judge_class = anthropic_judge_module.AnthropicJudge
    try:
        placement_module.place_paper = fake_place_paper
        anthropic_judge_module.AnthropicJudge = StubJudgeFactory
        with _foreign_keys_enforced():
            placement_module._run_placement_job(job_id)
    finally:
        settings.anthropic_api_key = before_key
        placement_module.place_paper = original_place_paper
        anthropic_judge_module.AnthropicJudge = original_judge_class

    db = SessionLocal()
    try:
        job = db.get(PlacementJob, job_id)
        assert job.status == "succeeded", job.error_detail

        # No orphaned row for the deleted question -- the FK violation this used to cause
        # is exactly what would have surfaced here as an insert failure instead.
        assert not list(
            db.scalars(select(QuestionPlacement).where(QuestionPlacement.question_id == question_1_id))
        )
        assert not list(
            db.scalars(select(QuestionTier).where(QuestionTier.question_id == question_1_id))
        )

        # The paper's other, untouched question still exists -- the fix skips only the
        # question that was actually deleted, not the whole job.
        question_2_id = db.scalars(
            select(Question.id).where(Question.assessment_id == paper, Question.question_no == "2")
        ).first()
        assert question_2_id is not None
    finally:
        db.close()
