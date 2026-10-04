"""Phase 5: stop duplicate papers.

* Each ORIGINAL uploaded file is hashed before merging, and after extraction the question
  stems are compared with the school's other papers of the subject; a match is returned to
  the teacher before any model call is spent, and nothing is reused automatically
  (duplicate_upload_check).
* The automatic pipeline never queues a second map/classify pair while one is pending
  (auto_pipeline_dedupe).
* scripts/list_duplicate_assessments.py groups copies by hash and by stem overlap.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from tests.test_scan_and_map import MARK_X, _auth, _paper_bytes, _upload

STEMS = [
    "Find the mean of the grouped data by the step-deviation method, assumed mean 200.",
    "Prove that the tangent at any point of a circle is perpendicular to the radius.",
    "Find the 20th term of the arithmetic progression 3, 7, 11, and so on.",
]


def _paper(stems, *, header="This question paper contains questions."):
    lines = [(60, 60, header), (60, 90, "SECTION A")]
    y = 120
    for i, stem in enumerate(stems, 1):
        lines.append((60, y, f"{i}. {stem[:45]}"))
        lines.append((60, y + 14, stem[45:]))
        lines.append((MARK_X, y, "2"))
        y += 60
    return _paper_bytes([lines])


def _new_paper(client, school, title="Unit test", subject="X.MATH"):
    r = client.post("/assessments", headers=_auth(school),
                    json={"subject_code": subject, "title": title})
    assert r.status_code == 200, r.json()
    return r.json()["assessment_id"]


@pytest.fixture
def check_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "duplicate_upload_check", True)
    monkeypatch.setattr(get_settings(), "auto_pipeline", False)


# --- 5.1 the file hash and the content check -------------------------------------------


def test_a_first_upload_matches_nothing(client, school, check_on):
    tag = uuid.uuid4().hex
    aid = _new_paper(client, school)
    r = _upload(client, school, aid, _paper([f"{tag} {s}" for s in STEMS]))
    assert r.status_code == 201, r.json()
    assert r.json()["duplicates"] == []


def test_the_same_file_again_matches_by_hash_and_stems(client, school, check_on):
    tag = uuid.uuid4().hex
    data = _paper([f"{tag} {s}" for s in STEMS])
    first = _new_paper(client, school, "Cycle Test I")
    assert _upload(client, school, first, data).json()["duplicates"] == []
    second = _new_paper(client, school, "Bharath Social")
    found = _upload(client, school, second, data).json()["duplicates"]
    assert [d["assessment_id"] for d in found] == [first]
    assert found[0]["matched_by"] == ["file_hash", "stems"] and found[0]["overlap"] == 1.0
    assert found[0]["title"] == "Cycle Test I"


def test_a_re_made_file_with_another_title_still_matches_by_its_stems(client, school, check_on):
    """The real case: every copy had a different hash and two different titles."""
    tag = uuid.uuid4().hex
    first = _new_paper(client, school, "Cycle Test I")
    _upload(client, school, first, _paper([f"{tag} {s}" for s in STEMS]))
    second = _new_paper(client, school, "Bharath Social")
    found = _upload(client, school, second, _paper(
        [f"{tag} {s}" for s in STEMS], header="BHARATH SCHOOL - Social Science Cycle Test",
    )).json()["duplicates"]
    assert [(d["assessment_id"], d["matched_by"]) for d in found] == [(first, ["stems"])]


def test_below_seventy_percent_is_not_a_duplicate(client, school, check_on):
    tag = uuid.uuid4().hex
    first = _new_paper(client, school)
    _upload(client, school, first, _paper([f"{tag} {s}" for s in STEMS]))
    other = uuid.uuid4().hex
    second = _new_paper(client, school)
    # one of three stems shared: 33%
    found = _upload(client, school, second, _paper(
        [f"{tag} {STEMS[0]}", f"{other} {STEMS[1]}", f"{other} {STEMS[2]}"],
    )).json()["duplicates"]
    assert found == []


def test_original_files_are_hashed_before_merging(client, school, check_on):
    import hashlib

    from app.db import SessionLocal
    from app.models import Assessment

    data = _paper([f"{uuid.uuid4().hex} {s}" for s in STEMS])
    aid = _new_paper(client, school)
    _upload(client, school, aid, data)
    db = SessionLocal()
    try:
        a = db.get(Assessment, aid)
        assert a.source_file_hashes == [hashlib.sha256(data).hexdigest()]
    finally:
        db.close()


def test_a_known_different_class_section_is_never_a_duplicate(client, school, check_on):
    from app.db import SessionLocal
    from app.models import Section

    db = SessionLocal()
    try:
        a_sec = Section(school_id=school["school_id"], grade=10, name=uuid.uuid4().hex[:6])
        b_sec = Section(school_id=school["school_id"], grade=10, name=uuid.uuid4().hex[:6])
        db.add_all([a_sec, b_sec])
        db.commit()
        a_id, b_id = a_sec.id, b_sec.id
    finally:
        db.close()
    tag = uuid.uuid4().hex
    data = _paper([f"{tag} {s}" for s in STEMS])
    first = client.post("/assessments", headers=_auth(school), json={
        "subject_code": "X.MATH", "title": "10A", "class_section_id": a_id}).json()["assessment_id"]
    _upload(client, school, first, data)
    second = client.post("/assessments", headers=_auth(school), json={
        "subject_code": "X.MATH", "title": "10B", "class_section_id": b_id}).json()["assessment_id"]
    assert _upload(client, school, second, data).json()["duplicates"] == []
    # unknown on one side: still shown, the teacher decides
    third = _new_paper(client, school)
    assert len(_upload(client, school, third, data).json()["duplicates"]) == 2


def test_an_unknown_class_section_is_refused(client, school):
    r = client.post("/assessments", headers=_auth(school), json={
        "subject_code": "X.MATH", "title": "x", "class_section_id": str(uuid.uuid4())})
    assert r.status_code == 404


def test_with_the_check_off_nothing_changes(client, school, monkeypatch):
    monkeypatch.setattr(get_settings(), "auto_pipeline", False)
    data = _paper([f"{uuid.uuid4().hex} {s}" for s in STEMS])
    first = _new_paper(client, school)
    _upload(client, school, first, data)
    second = _new_paper(client, school)
    body = _upload(client, school, second, data).json()
    assert "duplicates" not in body


# --- the teacher chooses; nothing is mapped until they do --------------------------------


@pytest.fixture
def pipeline_spy(monkeypatch):
    """auto_pipeline on, with the pipeline itself replaced by a recorder (no model calls)."""
    from app.api import marks

    monkeypatch.setattr(get_settings(), "duplicate_upload_check", True)
    monkeypatch.setattr(get_settings(), "auto_pipeline", True)
    ran: list[str] = []
    monkeypatch.setattr(marks, "_run_auto_pipeline", lambda aid, jobs: ran.append(aid))
    return ran


def test_a_match_holds_the_automatic_pipeline_until_the_teacher_chooses(client, school, pipeline_spy):
    data = _paper([f"{uuid.uuid4().hex} {s}" for s in STEMS])
    first = _new_paper(client, school)
    r = _upload(client, school, first, data).json()
    assert r["auto"] and pipeline_spy == [first], "no match: the pipeline runs as before"

    second = _new_paper(client, school)
    r = _upload(client, school, second, data).json()
    assert r["duplicates"] and "auto" not in r and pipeline_spy == [first], (
        "a match: no map or classify call is spent before the teacher answers")
    body = client.get("/assessments", headers=_auth(school)).json()
    rows = body["assessments"] if isinstance(body, dict) else body
    listed = {p["id"]: p for p in rows}
    assert listed[second]["duplicates_pending"][0]["assessment_id"] == first
    assert listed[first]["duplicates_pending"] is None

    bad = client.post(f"/assessments/{second}/duplicates/decision", headers=_auth(school),
                      json={"choice": "open_existing", "assessment_id": str(uuid.uuid4())})
    assert bad.status_code == 422
    keep = client.post(f"/assessments/{second}/duplicates/decision", headers=_auth(school),
                       json={"choice": "keep_new"})
    assert keep.status_code == 200, keep.json()
    assert keep.json()["auto"]["map_job_id"] and pipeline_spy == [first, second]


def test_open_existing_names_the_paper_and_changes_nothing_else(client, school, pipeline_spy):
    from app.db import SessionLocal
    from app.models import Assessment, ScannedQuestion

    data = _paper([f"{uuid.uuid4().hex} {s}" for s in STEMS])
    first = _new_paper(client, school)
    _upload(client, school, first, data)
    second = _new_paper(client, school)
    _upload(client, school, second, data)
    r = client.post(f"/assessments/{second}/duplicates/decision", headers=_auth(school),
                    json={"choice": "open_existing", "assessment_id": first})
    assert r.json() == {"assessment_id": second, "open": first}
    assert pipeline_spy == [first], "nothing runs for the new upload"
    db = SessionLocal()
    try:
        assert db.get(Assessment, second) is not None, "never deleted automatically"
        assert db.scalars(select(ScannedQuestion).where(
            ScannedQuestion.assessment_id == second)).first() is not None
        assert db.get(Assessment, second).duplicate_check["decision"]["choice"] == "open_existing"
    finally:
        db.close()


def test_a_decision_needs_a_match_waiting(client, school, check_on):
    aid = _new_paper(client, school)
    r = client.post(f"/assessments/{aid}/duplicates/decision", headers=_auth(school),
                    json={"choice": "keep_new"})
    assert r.status_code == 409


# --- 5.2 one map/classify pair at a time -----------------------------------------------


def test_no_second_pair_is_queued_while_one_is_pending(client, school, monkeypatch):
    from app.api.marks import _queue_auto_pipeline
    from app.db import SessionLocal
    from app.models import PlacementJob

    aid = _new_paper(client, school)
    db = SessionLocal()
    try:
        monkeypatch.setattr(get_settings(), "auto_pipeline_dedupe", True)
        first = _queue_auto_pipeline(db, school["school_id"], aid)
        assert "already_queued" not in first
        again = _queue_auto_pipeline(db, school["school_id"], aid)
        assert again == {**first, "already_queued": True}
        assert len(db.scalars(select(PlacementJob).where(
            PlacementJob.assessment_id == aid)).all()) == 2
        # once they finish, the next scan queues a fresh pair
        for job in db.scalars(select(PlacementJob).where(PlacementJob.assessment_id == aid)):
            job.status = "succeeded"
        db.commit()
        assert "already_queued" not in _queue_auto_pipeline(db, school["school_id"], aid)
        # off: a pair every time, as before
        monkeypatch.setattr(get_settings(), "auto_pipeline_dedupe", False)
        assert "already_queued" not in _queue_auto_pipeline(db, school["school_id"], aid)
    finally:
        db.close()


# --- 5.3 the listing script: the backup's shape -------------------------------------------

#: the backup's five copies of one unit test: five different hashes, two titles, one
#: linked to the exam
COPIES = [
    ("32ebf883", "Bharath Social", "0b8baeb0b534"),
    ("2654797a", "Cycle Test I", "657f581b3272"),
    ("6253a5c9", "Bharath Social", "72cb39ad63da"),
    ("03c447fd", "Cycle Test I", "5b3d5893337a"),
    ("959e36d4", "Cycle Test I", "76b08d3d1ec6"),
]


def _seed_copies(db, school_id, tag):
    from app.models import Assessment, Exam, ScannedQuestion

    stems = [f"{tag} question {i} about the printing press and nationalism" for i in range(55)]
    exam = Exam(school_id=school_id, name=f"Cycle Test I {tag[:6]}",
                scheduled_date=datetime(2026, 9, 1).date())
    db.add(exam)
    db.flush()
    ids = {}
    t0 = datetime(2026, 9, 2, tzinfo=UTC)
    for n, (prefix, title, sha) in enumerate(COPIES):
        a = Assessment(id=f"{prefix}-{tag[:4]}-{uuid.uuid4().hex[:4]}-0000-{uuid.uuid4().hex[:12]}",
                       school_id=school_id, subject_code="X.SST", title=title,
                       source_sha256=sha + tag[:52], created_at=t0 + timedelta(hours=n),
                       exam_id=exam.id if prefix == "959e36d4" else None)
        db.add(a)
        db.flush()
        own = list(stems)
        if n == 1:
            own = own[:54] + [f"{tag} a stem the vision read garbled"]   # one misread
        if n == 3:
            own = own[:50]                                              # a short read
        for i, s in enumerate(own):
            db.add(ScannedQuestion(assessment_id=a.id, address=f"A/{i + 1}//", section="A",
                                   question_no=str(i + 1), max_marks=1, stem_text=s))
        ids[prefix] = a.id
    # a different paper of the same school and subject, and the same paper in another subject
    other = Assessment(school_id=school_id, subject_code="X.SST", title="Half yearly",
                       created_at=t0 + timedelta(days=30))
    elsewhere = Assessment(school_id=school_id, subject_code="X.ENG", title="Cycle Test I",
                           created_at=t0 + timedelta(days=1))
    db.add_all([other, elsewhere])
    db.flush()
    for i in range(20):
        db.add(ScannedQuestion(assessment_id=other.id, address=f"A/{i + 1}//", section="A",
                               question_no=str(i + 1), max_marks=1,
                               stem_text=f"{tag} a different question {i} on federalism"))
    for i, s in enumerate(stems):
        db.add(ScannedQuestion(assessment_id=elsewhere.id, address=f"A/{i + 1}//", section="A",
                               question_no=str(i + 1), max_marks=1, stem_text=s))
    db.commit()
    return ids, exam.id


def test_the_listing_finds_the_backups_five_copies_as_one_group(school, capsys):
    from app.db import SessionLocal
    from scripts import list_duplicate_assessments

    tag = uuid.uuid4().hex
    db = SessionLocal()
    try:
        ids, exam_id = _seed_copies(db, school["school_id"], tag)
        groups = list_duplicate_assessments.duplicate_groups(
            db, school_id=school["school_id"], subject="X.SST")
        mine = [g for g in groups if any(p.id == ids["959e36d4"] for p in g["papers"])]
        assert len(mine) == 1
        group = mine[0]
        assert sorted(p.id for p in group["papers"]) == sorted(ids.values())
        assert all("stems" in why and "hash" not in why for why in group["links"].values()
                   if set(why))
        assert [p.id for p in group["papers"] if p.exam_id] == [ids["959e36d4"]]
    finally:
        db.close()

    assert list_duplicate_assessments.main(["--school", school["school_id"], "--subject", "X.SST"]) == 0
    out = capsys.readouterr().out
    assert "READ-ONLY" in out
    assert f"{ids['959e36d4']}" in out and "<- linked to the exam" in out
    group_text = out[out.rindex("GROUP", 0, out.index(ids["32ebf883"])):]
    group_text = group_text[:group_text.find("\nGROUP", 1)] if "\nGROUP" in group_text[1:] else group_text
    assert "5 papers" in group_text.splitlines()[0]
    assert "Half yearly" not in group_text, "a different paper is never grouped"


def test_the_listing_writes_nothing(school):
    from app.db import SessionLocal
    from app.models import Assessment, ScannedQuestion
    from scripts import list_duplicate_assessments

    db = SessionLocal()
    try:
        before = (db.query(Assessment).count(), db.query(ScannedQuestion).count())
    finally:
        db.close()
    list_duplicate_assessments.main([])
    db = SessionLocal()
    try:
        assert (db.query(Assessment).count(), db.query(ScannedQuestion).count()) == before
    finally:
        db.close()


# --- the papers list shows the hold, and only while it lasts --------------------------------


def _listed(client, school, aid):
    body = client.get("/assessments", headers=_auth(school)).json()
    return {p["id"]: p for p in body["assessments"]}[aid]


def test_the_list_shows_a_held_paper_until_it_is_released(client, school, pipeline_spy):
    data = _paper([f"{uuid.uuid4().hex} {s}" for s in STEMS])
    first = _new_paper(client, school, "Cycle Test I")
    _upload(client, school, first, data)
    second = _new_paper(client, school)
    _upload(client, school, second, data)
    held = _listed(client, school, second)["duplicates_pending"]
    assert held[0]["title"] == "Cycle Test I" and held[0]["overlap"] == 1.0
    client.post(f"/assessments/{second}/duplicates/decision", headers=_auth(school),
                json={"choice": "keep_new"})
    assert _listed(client, school, second)["duplicates_pending"] is None


@pytest.mark.parametrize("check, stage, shown", [
    ({"candidates": [{"assessment_id": "x"}], "decision": None}, "scanned", True),
    ({"candidates": [{"assessment_id": "x"}], "decision": None}, "confirmed", True),
    # mapped by hand: the hold is over, whatever was decided
    ({"candidates": [{"assessment_id": "x"}], "decision": None}, "mapped", False),
    ({"candidates": [{"assessment_id": "x"}], "decision": {"choice": "keep_new"}}, "scanned", False),
    ({"candidates": [], "decision": None}, "scanned", False),
    (None, "scanned", False),
])
def test_the_label_shows_only_while_the_pipeline_is_held(check, stage, shown):
    import types

    from app.extraction.duplicates import held_by

    paper = types.SimpleNamespace(duplicate_check=check)
    assert bool(held_by(paper, stage)) is shown


def test_a_second_decision_starts_nothing_more(client, school, pipeline_spy):
    data = _paper([f"{uuid.uuid4().hex} {s}" for s in STEMS])
    first = _new_paper(client, school)
    _upload(client, school, first, data)
    second = _new_paper(client, school)
    _upload(client, school, second, data)
    url = f"/assessments/{second}/duplicates/decision"
    one = client.post(url, headers=_auth(school), json={"choice": "keep_new"})
    assert one.status_code == 200 and one.json()["auto"]["map_job_id"]
    assert pipeline_spy == [first, second]
    # the double-click, the second tab, the retry: the earlier answer, nothing queued
    again = client.post(url, headers=_auth(school), json={"choice": "keep_new"})
    assert again.status_code == 200
    assert again.json()["already_decided"] is True
    assert again.json()["decision"]["choice"] == "keep_new" and "auto" not in again.json()
    # ...even a different answer: the first one stands
    other = client.post(url, headers=_auth(school),
                        json={"choice": "open_existing", "assessment_id": first})
    assert other.json()["already_decided"] is True
    assert other.json()["decision"]["choice"] == "keep_new"
    assert pipeline_spy == [first, second], "the pipeline ran once for this paper"
