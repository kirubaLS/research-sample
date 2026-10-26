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


def _map(client, url: str, headers: dict):
    """POST /map now queues a job (202) and the result is read from its job row -- the
    same shape /place has. Pre-check failures still come back inline."""
    out = client.post(url, headers=headers)
    if out.status_code != 202:
        return out
    return client.get(f"{url}/jobs/{out.json()['job_id']}", headers=headers)
