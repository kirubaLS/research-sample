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
    assert "Surface Areas and Volumes" in [c["label"] for c in body["chapters"]]


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


@pytest.fixture
def sav_families(school):
    """Two fixture-only concept families under the real X.MATH.SAV chapter, neither
    covering any section yet -- the exact shape choose_family() cannot disambiguate
    without a human, and the shape review_queue/confirm now have to offer a lever for."""
    import uuid

    from app.db import SessionLocal
    from app.models import ConceptFamilyProposal, TaxonomyNode

    db = SessionLocal()
    try:
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.SAV"))
        made = []
        for code, label in [
            ("TEST.CONFIRMFAMILY.CF.A", "Surface area of a combination of solids"),
            ("TEST.CONFIRMFAMILY.CF.B", "Conversion of one solid into another"),
        ]:
            node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
            if node is None:
                node = TaxonomyNode(
                    kind="concept_family", code=code, label=label, parent_id=chapter.id,
                    path=code, curriculum_version=chapter.curriculum_version,
                )
                db.add(node)
                db.flush()
            if db.scalar(select(ConceptFamilyProposal).where(
                ConceptFamilyProposal.code == code, ConceptFamilyProposal.subject_code == "X.MATH",
            )) is None:
                db.add(ConceptFamilyProposal(
                    curriculum_version=chapter.curriculum_version, subject_code="X.MATH",
                    run_id=uuid.uuid4().hex, source="llm", model="fixture",
                    code=code, label=label, chapter_id=chapter.id,
                    evidence=[], from_sections=[],
                ))
            made.append(node)
        db.commit()
        ids = [n.id for n in made]
    finally:
        db.close()
    return ids


def test_confirming_a_family_settles_the_question_and_teaches_the_knowledge_base(
    client, school, paper, sav_families,
):
    """The gap the mapping audit surfaced: a chapter with several concept families and no
    usable section leaves choose_family() permanently blocked, and the old confirm() could
    only fix the CHAPTER, never the FAMILY -- so a human reviewing a blocked-family
    question had no way to actually settle it. family_code closes that, and the correction
    must also update ConceptFamilyProposal.from_sections (record_family_section), so the
    SAME section is resolved automatically on every later paper -- a human fixing this
    once, not a person doing it forever."""
    from app.db import SessionLocal
    from app.models import ConceptFamilyProposal, Question, TaxonomyNode

    family_a_id, family_b_id = sav_families

    db = SessionLocal()
    try:
        question = db.scalars(select(Question).where(Question.assessment_id == paper)).first()
        qid = question.id
        family_b = db.get(TaxonomyNode, family_b_id)
        family_b_code = family_b.code
    finally:
        db.close()

    r = client.post(
        f"/assessments/{paper}/review/{qid}", headers=_auth(school),
        json={
            "chapter_code": "X.MATH.SAV", "curriculum_section": "13.5",
            "family_code": family_b_code, "reviewed_by": "kingshuk",
        },
    )
    assert r.status_code == 200

    db = SessionLocal()
    try:
        settled = db.get(Question, qid)
        assert settled.concept_family_id == family_b_id, (
            "confirming a family must actually settle it on the question -- this is what "
            "every report reads"
        )
        assert settled.concept_family_id != family_a_id

        proposal = db.scalar(select(ConceptFamilyProposal).where(
            ConceptFamilyProposal.code == family_b_code, ConceptFamilyProposal.subject_code == "X.MATH",
        ))
        assert "13.5" in (proposal.from_sections or []), (
            "the correction must feed back into the knowledge base itself, so the next "
            "paper's question in this same section resolves automatically instead of "
            "blocking again"
        )
    finally:
        db.close()


def test_confirming_a_family_from_a_different_chapter_is_refused(client, school, paper, sav_families):
    from app.db import SessionLocal
    from app.models import Question

    db = SessionLocal()
    try:
        qid = db.scalars(select(Question).where(Question.assessment_id == paper)).first().id
    finally:
        db.close()

    r = client.post(
        f"/assessments/{paper}/review/{qid}", headers=_auth(school),
        # X.MATH.REAL is a real chapter, but not the one being confirmed to -- a family of
        # the WRONG chapter must never be accepted, silently or otherwise.
        json={"chapter_code": "X.MATH.SAV", "family_code": "X.MATH.REAL", "reviewed_by": "someone"},
    )
    assert r.status_code == 422


def test_review_queue_offers_the_chapters_own_candidate_families(client, school, paper, sav_families):
    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement, TaxonomyNode

    db = SessionLocal()
    try:
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.SAV"))
        question = db.scalars(select(Question).where(Question.assessment_id == paper)).first()
        db.add(QuestionPlacement(
            question_id=question.id, chapter_id=chapter.id, confidence=0.3,
            source="model", needs_review=True, reasoning="blocked",
        ))
        db.commit()
    finally:
        db.close()

    r = client.get(f"/assessments/{paper}/review", headers=_auth(school))
    assert r.status_code == 200
    row = r.json()["questions"][0]
    codes = {f["code"] for f in row["candidate_families"]}
    assert "TEST.CONFIRMFAMILY.CF.A" in codes
    assert "TEST.CONFIRMFAMILY.CF.B" in codes


# --- an outage is not a judgment -----------------------------------------------------------

def _mapped_question(client, school, title, stem):
    """A question the map step has already placed under Statistics 13.3."""
    from app.db import SessionLocal
    from app.models import Question, TaxonomyNode

    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": title, "total_marks": 3,
    }).json()["assessment_id"]
    added = client.post(f"/assessments/{aid}/questions", headers=h, json={"questions": [{
        "section": "A", "question_no": "1", "max_marks": 3, "stem_text": stem,
        "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
        "concept_variant": f"outage fixture {title}",
    }]})
    assert added.status_code == 200, added.json()
    db = SessionLocal()
    try:
        q = db.scalars(select(Question).where(Question.assessment_id == aid)).first()
        stats = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.STATS"))
        q.chapter_id, q.curriculum_section = stats.id, "13.3"
        db.commit()
        return aid, q.id, stats.id
    finally:
        db.close()


def _run_with_judge(school, aid, judge_factory, monkeypatch):
    from app.api.placement import _run_placement_job
    from app.classify import anthropic_judge as anthropic_judge_module
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import PlacementJob

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    monkeypatch.setattr(anthropic_judge_module, "AnthropicJudge", judge_factory)
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
        return db.get(PlacementJob, job_id)
    finally:
        db.close()


def test_a_subjects_chapters_are_listed_numbered_book_by_book(client, school):
    maths = client.get("/admin/subjects/X.MATH/chapters", headers=_auth(school))
    assert maths.status_code == 200, maths.text
    books = maths.json()["books"]
    assert len(books) == 1 and books[0]["subject_code"] == "X.MATH"
    chapters = books[0]["chapters"]
    assert chapters[0] == {"code": "X.MATH.REAL", "number": 1, "label": "Real Numbers", "board_unit": "X.MATH.U.NUMBER"}
    assert [c["number"] for c in chapters] == list(range(1, len(chapters) + 1))
    sst = client.get("/admin/subjects/X.SST/chapters", headers=_auth(school)).json()
    assert [b["subject_code"] for b in sst["books"]] == ["X.HIST", "X.GEO", "X.POL", "X.ECO"]
    assert sst["books"][0]["chapters"][0]["number"] == 1 and sst["books"][1]["chapters"][0]["number"] == 1
    assert client.get("/admin/subjects/X.NOPE/chapters", headers=_auth(school)).status_code == 404


def test_a_paper_can_declare_its_chapters_at_creation(client, school):
    from app.db import SessionLocal
    from app.models import Assessment

    h = _auth(school)
    made = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Scoped at birth", "total_marks": 20,
        "syllabus_scope": ["X.MATH.STATS", "X.MATH.REAL"],
    })
    assert made.status_code == 200, made.text
    db = SessionLocal()
    try:
        assert db.get(Assessment, made.json()["assessment_id"]).syllabus_scope == ["X.MATH.REAL", "X.MATH.STATS"]
    finally:
        db.close()
    bad = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Bad scope", "total_marks": 20,
        "syllabus_scope": ["X.MATH.NOT_A_CHAPTER"],
    })
    assert bad.status_code == 422 and "not chapters" in bad.json()["detail"]
