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


