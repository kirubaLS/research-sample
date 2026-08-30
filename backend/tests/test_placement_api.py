"""Declaring what a paper covers, and settling the questions the machine could not.

A paper is tagged once and then correct for every student who sat it, so the review queue
is the mechanism that turns a proposal into a fact. It has to be short, ordered by where
attention is worth spending, and it must never lose what the machine originally thought.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

# app.db reads the database URL at import time, and conftest sets it in a fixture -- so
# these are imported inside the tests rather than here.


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@pytest.fixture
def paper(client, school):
    """A two-question assessment with stems, which placement needs to read.

    The variants are made unique per test: this fixture runs once per test against one
    database, and the reuse guard is right to refuse a paper that serves the same variant
    to a class twice.
    """
    import uuid

    tag = uuid.uuid4().hex[:8]
    created = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": f"Cyclic Test {tag}", "total_marks": 4},
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
             "stem_text": "Prove that root 5 is irrational",
             "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME",
             "concept_variant": f"irrationality {tag}"},
        ]},
    )
    assert added.status_code == 200, added.json()
    return aid


# --- rung 2, through the API ----------------------------------------------------------

def test_a_paper_can_declare_what_it_covers(client, school, paper):
    r = client.put(
        f"/assessments/{paper}/scope", headers=_auth(school),
        json={"chapters": ["X.MATH.SAV", "X.MATH.REAL"]},
    )
    assert r.status_code == 200
    assert r.json()["chapters"] == 2


def test_a_scope_naming_something_that_is_not_a_chapter_is_refused(client, school, paper):
    """Silently dropping it would leave a paper scoped to less than the teacher declared."""
    r = client.put(
        f"/assessments/{paper}/scope", headers=_auth(school),
        json={"chapters": ["X.MATH.SAV", "X.MATH.NOSUCHTHING"]},
    )
    assert r.status_code == 422
    assert "X.MATH.NOSUCHTHING" in r.json()["detail"]


def test_scope_belongs_to_the_school_that_owns_the_paper(client, school, paper):
    r = client.put(
        f"/assessments/{paper}/scope", headers={"X-API-Key": "not-a-key"},
        json={"chapters": ["X.MATH.SAV"]},
    )
    assert r.status_code == 404


# --- placement preconditions ------------------------------------------------------------

def test_placement_without_a_classifier_key_says_what_is_missing(client, school, paper):
    from app.config import get_settings

    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = None
    try:
        r = client.post(f"/assessments/{paper}/place", headers=_auth(school))
        assert r.status_code == 409
        assert "YAADHUM_ANTHROPIC_API_KEY" in r.json()["detail"]
    finally:
        settings.anthropic_api_key = before


def test_placement_needs_question_text(client, school):
    """Placement reads stems. A paper of bare addresses has nothing to classify."""
    import uuid

    created = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "No stems", "total_marks": 2},
    )
    aid = created.json()["assessment_id"]
    client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [{
            "section": "A", "question_no": "1", "max_marks": 2,
            "board_unit": "X.MATH.U.MENSURATION",
            "concept_family": "X.MATH.CF.VOLUME",
            "concept_variant": f"no stem {uuid.uuid4().hex[:8]}",
        }]},
    )
    r = client.post(f"/assessments/{aid}/place", headers=_auth(school))
    assert r.status_code == 409
    assert "question text" in r.json()["detail"]


# --- the review queue --------------------------------------------------------------------

def test_the_queue_holds_only_what_still_needs_a_person(client, school, paper):
    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement

    db = SessionLocal()
    try:
        questions = db.scalars(
            select(Question).where(Question.assessment_id == paper)
        ).all()
        db.add(QuestionPlacement(
            question_id=questions[0].id, confidence=0.42, source="model",
            needs_review=True, reasoning="could be either",
            evidence=["Example 3"],
        ))
        db.add(QuestionPlacement(
            question_id=questions[1].id, confidence=0.97, source="model",
            needs_review=False, reasoning="clear",
        ))
        db.commit()
    finally:
        db.close()

    body = client.get(f"/assessments/{paper}/review", headers=_auth(school)).json()
    assert body["total_placed"] == 2
    assert body["pending"] == 1
    [pending] = body["questions"]
    assert pending["confidence"] == 0.42
    assert pending["reasoning"] == "could be either"
    assert pending["evidence"] == ["Example 3"]
    # a reviewer needs the real alternatives to choose from
    assert "Surface Areas and Volumes" in body["chapters"]


def test_confirming_records_a_new_placement_rather_than_editing_the_old_one(
    client, school, paper
):
    """How often a teacher overrules the machine is the only honest measure of whether it
    can be trusted on the next paper, and an edit would erase it."""
    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement

    db = SessionLocal()
    try:
        question = db.scalars(
            select(Question).where(Question.assessment_id == paper)
        ).first()
        qid = question.id
        db.add(QuestionPlacement(
            question_id=qid, confidence=0.42, source="model", needs_review=True,
            reasoning="unsure",
        ))
        db.commit()
    finally:
        db.close()

    r = client.post(
        f"/assessments/{paper}/review/{qid}", headers=_auth(school),
        json={"chapter_code": "X.MATH.SAV", "curriculum_section": "12.2",
              "reviewed_by": "kingshuk"},
    )
    assert r.status_code == 200
    assert r.json()["chapter"] == "Surface Areas and Volumes"
    assert r.json()["remaining"] == 0

    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement

    db = SessionLocal()
    try:
        rows = db.scalars(
            select(QuestionPlacement)
            .where(QuestionPlacement.question_id == qid)
            .order_by(QuestionPlacement.created_at)
        ).all()
        assert len(rows) == 2, "the machine's attempt must survive the correction"
        assert rows[0].source == "model"
        assert rows[1].source == "human"
        assert rows[1].reviewed_by == "kingshuk"
        # the settled answer is on the question, which is what analysis reads
        assert db.get(Question, qid).curriculum_section == "12.2"
    finally:
        db.close()


def test_confirming_to_a_chapter_that_does_not_exist_is_refused(client, school, paper):
    from app.db import SessionLocal
    from app.models import Question

    db = SessionLocal()
    try:
        qid = db.scalars(select(Question).where(Question.assessment_id == paper)).first().id
    finally:
        db.close()
    r = client.post(
        f"/assessments/{paper}/review/{qid}", headers=_auth(school),
        json={"chapter_code": "X.MATH.INVENTED", "reviewed_by": "someone"},
    )
    assert r.status_code == 422


def test_a_question_from_another_paper_cannot_be_confirmed_here(client, school, paper):
    other = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Other", "total_marks": 2},
    ).json()["assessment_id"]
    from app.db import SessionLocal
    from app.models import Question

    db = SessionLocal()
    try:
        qid = db.scalars(select(Question).where(Question.assessment_id == paper)).first().id
    finally:
        db.close()
    r = client.post(
        f"/assessments/{other}/review/{qid}", headers=_auth(school),
        json={"chapter_code": "X.MATH.SAV", "reviewed_by": "someone"},
    )
    assert r.status_code == 404
