"""Reproduces the exact real-world shape a teacher reported: a case-study/source-based
question (a bare, zero-mark parent -- 'Read the source and answer the questions that
follow' -- plus sub-parts that test comprehension of an unseen passage, not textbook
content) going through the photograph/scan -> confirm -> /map pipeline.

The parent correctly never becomes a Question row (see context_addresses / the loop in
map_paper_to_book) -- that is by design, it carries no marks of its own. The bug this
file guards against is different: raw retrieval (map_paper_to_book calls locate() with no
LLM judge, unlike /place) can find real book evidence for one sub-part -- a shared word
with some unrelated chapter is enough -- and none at all for another, purely as an
accident of vocabulary, even though every sub-part of the same case study is testing the
same unseen source and should be treated identically. Before the fix, a sub-part with no
evidence of its own was blocked permanently: no Question row, no marks entry possible, and
therefore invisible in the marks grid and every report -- "the entire question deleted",
exactly as reported, even though the parent's own zero marks were always expected.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@pytest.fixture
def case_study_assessment(client, school):
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Source-based case study", "total_marks": 4},
    )
    assert r.status_code == 200, r.text
    return r.json()["assessment_id"]


def _stage(db, assessment_id, *, question_no, sub_part, max_marks, stem_text):
    from app.models import ScannedQuestion

    address = "/".join(["", question_no, sub_part or "", ""])
    row = ScannedQuestion(
        assessment_id=assessment_id, address=address, section=None,
        question_no=question_no, sub_part=sub_part, max_marks=max_marks,
        stem_text=stem_text, logical_page=1,
    )
    db.add(row)
    return row


def test_a_case_study_sub_part_with_no_book_evidence_of_its_own_is_not_deleted(
    client, school, case_study_assessment, book,
):
    from app.db import SessionLocal
    from app.models import Question, ScannedQuestion

    aid = case_study_assessment
    db = SessionLocal()
    _stage(
        db, aid, question_no="10", sub_part=None, max_marks=None,
        stem_text="Read the source given below and answer the questions that follow.",
    )
    # Shares real vocabulary with the book's Statistics/step-deviation chunk, so raw
    # retrieval finds it (this is 10.1 mapping correctly, exactly as the teacher reported).
    _stage(
        db, aid, question_no="10", sub_part="1", max_marks=1,
        stem_text="Find the mean of the grouped data by the step-deviation method, "
                   "assumed mean 200.",
    )
    _stage(
        db, aid, question_no="10", sub_part="2", max_marks=1,
        stem_text="State why the step-deviation method uses an assumed mean for "
                   "grouped data with class size h.",
    )
    # A genuine unseen-passage comprehension question -- shares not one content word
    # with anything in the book fixture (X.MATH: statistics, circles, real numbers,
    # arithmetic progressions). This is "10.3": worth real marks, tests the given
    # source, and must not vanish just because it has no textbook vocabulary to match.
    _stage(
        db, aid, question_no="10", sub_part="3", max_marks=2,
        stem_text="Why did poor readers in colonial towns struggle to afford the "
                   "pamphlets and cheap prints hawkers sold door to door?",
    )
    db.commit()
    db.close()

    confirm = client.post(
        f"/assessments/{aid}/scan/confirm", headers=_auth(school), json={},
    )
    assert confirm.status_code == 200, confirm.text

    mapped = _map(client, f"/assessments/{aid}/map", headers=_auth(school))
    assert mapped.status_code == 200, mapped.text
    body = mapped.json()

    # All 3 real sub-parts must become real, gradable Question rows -- none blocked.
    assert body["blocked"] == 0, body
    assert body["mapped"] == 3, body
    assert body["context_stems"] == 1

    db = SessionLocal()
    try:
        questions = {
            q.address: q for q in db.scalars(
                select(Question).where(Question.assessment_id == aid)
            )
        }
        staged = {
            r.address: r for r in db.scalars(
                select(ScannedQuestion).where(ScannedQuestion.assessment_id == aid)
            )
        }

        # The parent itself never becomes a Question -- expected, it carries no marks.
        assert "/10//" in staged
        assert staged["/10//"].question_id is None
        assert staged["/10//"].blocked_reason is None

        # Every sub-part is a real Question, chapter/family assigned, none silently
        # dropped -- this is the core of the bug: before the fix, "/10/3/" here had no
        # Question row at all, and every marks-grid / report / teacher screen that reads
        # Question rows simply never saw it, indistinguishable from a deleted question.
        for addr in ("/10/1/", "/10/2/", "/10/3/"):
            assert addr in questions, f"{addr} was never promoted to a real question"
            q = questions[addr]
            assert q.chapter_id is not None
            assert q.concept_family_id is not None
            assert q.board_unit_id is not None
            assert staged[addr].question_id == q.id
            assert staged[addr].blocked_reason is None

        # 10.3 borrowed its placement from a sibling sub-part of the same case study
        # rather than being force-fit by its own (nonexistent) evidence -- it must be
        # flagged for a person to check, and its chapter must match its siblings', since
        # every sub-part of one case study is testing the same given source.
        q1, q2, q3 = questions["/10/1/"], questions["/10/2/"], questions["/10/3/"]
        assert q3.chapter_id == q1.chapter_id == q2.chapter_id

        from app.models import QuestionPlacement

        p3 = db.scalar(
            select(QuestionPlacement).where(QuestionPlacement.question_id == q3.id)
        )
        assert p3 is not None
        assert p3.needs_review is True
    finally:
        db.close()


def test_a_standalone_question_with_no_evidence_at_all_still_stays_blocked(
    client, school, case_study_assessment, book,
):
    """The fix is scoped to case-study sub-parts rescuing each other. An ordinary
    standalone question (no context parent, no sibling to borrow from) that matches no
    chapter is still a real gap and must still be refused rather than guessed at -- the
    invariant this pipeline's whole design rests on."""
    from app.db import SessionLocal
    from app.models import Question

    aid = case_study_assessment
    db = SessionLocal()
    _stage(
        db, aid, question_no="1", sub_part=None, max_marks=4,
        stem_text="Why did poor readers in colonial towns struggle to afford the "
                   "pamphlets and cheap prints hawkers sold door to door?",
    )
    db.commit()
    db.close()

    confirm = client.post(f"/assessments/{aid}/scan/confirm", headers=_auth(school), json={})
    assert confirm.status_code == 200, confirm.text

    mapped = _map(client, f"/assessments/{aid}/map", headers=_auth(school))
    assert mapped.status_code == 200, mapped.text
    body = mapped.json()
    assert body["mapped"] == 0
    assert body["blocked"] == 1
    assert "/1//" in body["blocked_addresses"]

    db = SessionLocal()
    real = db.scalars(select(Question).where(Question.assessment_id == aid)).all()
    db.close()
    assert real == []


def _map(client, url: str, headers: dict):
    """POST /map now queues a job (202) and the result is read from its job row -- the
    same shape /place has. Pre-check failures still come back inline."""
    out = client.post(url, headers=headers)
    if out.status_code != 202:
        return out
    return client.get(f"{url}/jobs/{out.json()['job_id']}", headers=headers)
