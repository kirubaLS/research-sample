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

def test_a_skill_anchored_question_is_placed_with_no_chapter(client, school, paper, book):
    """End to end through the real write path: a letter-writing question the judge
    confidently says has no chapter must land as chapter_id=None, curriculum_section=None,
    needing no review -- and must not crash reconciliation for the paper's other, ordinary
    question."""
    from sqlalchemy import select

    from app.api.placement import _run_placement_job
    from app.classify import anthropic_judge as anthropic_judge_module
    from app.classify.judge import Classification
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import PlacementJob, Question, QuestionPlacement

    settings = get_settings()
    before_key = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    class StubJudge:
        """Reproduces the real bug's fix: a letter to the headmaster gets no chapter, a
        content question keeps its ordinary answer."""

        def classify(self, question, evidence):
            if "letter" in question.lower():
                return Classification(
                    chapter=None, tier=None,
                    skill_required="write a formal letter requesting library books",
                    reasoning="skill-anchored: a letter invented for this paper",
                    confidence=0.9,
                )
            return Classification(
                chapter="Surface Areas and Volumes", tier="Applying",
                skill_required="mensuration formula", reasoning="a cone",
                confidence=0.95,
            )

    class StubJudgeFactory:
        def __new__(cls, *a, **kw):
            return StubJudge()

    db = SessionLocal()
    try:
        added = client.post(
            f"/assessments/{paper}/questions", headers=_auth(school),
            json={"questions": [{
                "section": "B", "question_no": "3", "max_marks": 5,
                # Shares vocabulary with the book fixture's circle chunk ("tangent",
                # "circle") purely so TF-IDF retrieval returns *some* passages to show the
                # judge -- retrieval cannot know the question is skill-anchored, only the
                # judge reading the passages can, which is exactly the bug being fixed.
                "stem_text": (
                    "Write a letter to your headmaster requesting library books about "
                    "circles and the tangent to a circle"
                ),
                "board_unit": "X.MATH.U.MENSURATION",
                "concept_family": "X.MATH.CF.VOLUME",
                "concept_variant": "letter fixture",
            }]},
        )
        assert added.status_code == 200, added.json()
        letter_qid = db.scalars(
            select(Question).where(
                Question.assessment_id == paper, Question.question_no == "3"
            )
        ).first().id

        job = PlacementJob(school_id=school["school_id"], assessment_id=paper)
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    original_judge_class = anthropic_judge_module.AnthropicJudge
    try:
        anthropic_judge_module.AnthropicJudge = StubJudgeFactory
        _run_placement_job(job_id)
    finally:
        settings.anthropic_api_key = before_key
        anthropic_judge_module.AnthropicJudge = original_judge_class

    db = SessionLocal()
    try:
        job = db.get(PlacementJob, job_id)
        assert job.status == "succeeded", job.error_detail

        placements: dict[str, QuestionPlacement] = {}
        for row in db.scalars(
            select(QuestionPlacement)
            .join(Question, Question.id == QuestionPlacement.question_id)
            .where(Question.assessment_id == paper)
            .order_by(QuestionPlacement.created_at)
        ):
            placements[row.question_id] = row

        letter_placement = placements[letter_qid]
        assert letter_placement.chapter_id is None
        assert letter_placement.curriculum_section is None
        assert not letter_placement.needs_review, (
            "a confident skill-anchored answer needs no one's time"
        )

        letter_question = db.get(Question, letter_qid)
        assert letter_question.chapter_id is None
        assert letter_question.curriculum_section is None
        assert letter_question.skill_required == (
            "write a formal letter requesting library books"
        )
    finally:
        db.close()


def test_classify_auto_resolves_instead_of_overwriting_a_good_placement_with_blocked_text(
    client, school, paper, book, monkeypatch,
):
    """The regression this fixes: classify re-derives choose_family from scratch against
    the JUDGE's own curriculum_section, which is frequently None even for a question that
    mapped cleanly (the judge is not asked to name a section the way retrieval's own
    locate() is). Before auto_resolve was wired into this path too, a chapter with two
    genuinely competing, unclaimed families read as freshly "blocked" on every classify
    run, unconditionally overwriting a perfectly good mapping-time placement with a
    confusing "N families exist ... settle it in review" message and needs_review=True --
    observed in production across an entire paper's worth of otherwise cleanly-placed
    questions. This confirms classify now tries the same real-book-search auto-resolve
    mapping already gets, and that a resolved placement's reasoning names the resolution
    rather than repeating the raw blocked text."""
    from sqlalchemy import select

    from app.api.placement import _run_placement_job
    from app.classify import anthropic_judge as anthropic_judge_module
    from app.classify.judge import Classification
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import (
        BookChunk, ConceptFamilyProposal, PlacementJob, Question, QuestionPlacement,
        TaxonomyNode,
    )

    settings = get_settings()
    before_key = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    # Arithmetic Progressions, not Statistics: the `book` fixture's AP chapter has one
    # chunk and no concept family at all, and nothing else in this suite touches its
    # family count -- Statistics is exercised elsewhere (test_scan_and_map.py's own
    # stage-2 test, and every plain "one family" mapping test) in ways that assume
    # exactly what is there today, and this test's own added families would otherwise
    # make an unrelated chapter's questions genuinely ambiguous for every test that runs
    # afterward in the same shared database.
    db = SessionLocal()
    ap = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.AP"))
    for code, label in [
        ("X.MATH.CF.CLASSIFY_STAGE_A", "nth term of an AP"),
        ("X.MATH.CF.CLASSIFY_STAGE_B", "Sum of n terms of an AP"),
    ]:
        if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code)) is not None:
            continue
        node = TaxonomyNode(
            kind="concept_family", code=code, label=label, parent_id=ap.id,
            path=code, curriculum_version=ap.curriculum_version,
        )
        db.add(node)
        db.flush()
        db.add(ConceptFamilyProposal(
            curriculum_version=ap.curriculum_version, subject_code="X.MATH",
            run_id="fixture-classify-stage2", source="llm", model="fixture",
            code=code, label=label, chapter_id=ap.id, evidence=[], from_sections=[],
        ))
    # TF-IDF's idf goes negative for a term shared by every document in a two-document
    # corpus (see LexicalIndex's own docstring), which the book fixture's AP chapter is
    # without these -- a real chapter's full chunk count never hits this.
    for section, text in [
        ("5.3", "The sum of the first n terms of an arithmetic progression is given by "
                 "n by 2 times twice the first term plus n minus one times the common "
                 "difference."),
        ("5.4", "An arithmetic mean is the average of two numbers placed between them "
                 "so that all three form an arithmetic progression."),
        ("5.5", "Applications of arithmetic progressions include simple interest "
                 "calculations and patterns of seating arrangements."),
    ]:
        code = f"X.MATH.AP.CLASSIFY.{section.replace('.', '_')}"
        if db.scalar(select(BookChunk).where(BookChunk.stem_hash == code)) is not None:
            continue
        db.add(BookChunk(
            curriculum_version=ap.curriculum_version, subject_code="X.MATH",
            node_id=ap.id, bucket="T", reference=f"Section {section}", text=text,
            section_number=section, normalised=text.lower(), stem_hash=code,
        ))
    db.commit()

    stem_text = "Find the nth term of the arithmetic progression 2, 5, 8, 11, ..."
    added = client.post(
        f"/assessments/{paper}/questions", headers=_auth(school),
        json={"questions": [{
            "section": "C", "question_no": "9", "max_marks": 3,
            "stem_text": stem_text,
            "board_unit": "X.MATH.U.MENSURATION",
            "concept_family": "X.MATH.CF.VOLUME",
            "concept_variant": "classify stage2 fixture",
        }]},
    )
    assert added.status_code == 200, added.json()
    qid = db.scalars(
        select(Question).where(Question.assessment_id == paper, Question.question_no == "9")
    ).first().id
    job = PlacementJob(school_id=school["school_id"], assessment_id=paper)
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()

    class StubJudge:
        def classify(self, question, evidence):
            if "arithmetic progression" in question.lower():
                # No curriculum_section -- the judge frequently doesn't name one, and
                # that alone used to be enough to read as "blocked" on classify.
                return Classification(
                    chapter="Arithmetic Progressions", tier="Applying",
                    skill_required="find the nth term of an AP",
                    reasoning="asks for the nth term", confidence=0.9,
                )
            return Classification(
                chapter="Surface Areas and Volumes", tier="Applying",
                skill_required="mensuration formula", reasoning="a cone", confidence=0.95,
            )

    class StubJudgeFactory:
        def __new__(cls, *a, **kw):
            return StubJudge()

    # Stand in for the Anthropic call auto_resolve makes -- a real quote from the
    # fixture's own AP chunk ("the nth term is given by a plus n minus one times d")
    # is what the guardrail should accept.
    import sys
    import types

    from app.mapping.auto_resolve import _FamilyChoice

    class _FakeMessages:
        def parse(self, **kwargs):
            class _Response:
                parsed_output = _FamilyChoice(
                    family_code="X.MATH.CF.CLASSIFY_STAGE_A",
                    rationale="the passage gives the formula for the nth term",
                    quote="the nth term is given by a plus n minus one times d",
                )
            return _Response()

    class _FakeAnthropic:
        def __init__(self, api_key):
            self.messages = _FakeMessages()

    fake_anthropic = types.ModuleType("anthropic")
    fake_anthropic.Anthropic = _FakeAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

    original_judge_class = anthropic_judge_module.AnthropicJudge
    try:
        anthropic_judge_module.AnthropicJudge = StubJudgeFactory
        _run_placement_job(job_id)
    finally:
        settings.anthropic_api_key = before_key
        anthropic_judge_module.AnthropicJudge = original_judge_class

    db = SessionLocal()
    placement = db.scalars(
        select(QuestionPlacement)
        .where(QuestionPlacement.question_id == qid)
        .order_by(QuestionPlacement.created_at.desc())
    ).first()
    assert placement is not None
    assert placement.needs_review, "auto-resolved is still a machine's first read"
    assert "Auto-resolved" in placement.reasoning
    assert "families exist" not in placement.reasoning, (
        "a resolved placement must not also carry the raw blocked-message text"
    )
    question = db.get(Question, qid)
    assert question.concept_family_id is not None
    family = db.get(TaxonomyNode, question.concept_family_id)
    assert family.code == "X.MATH.CF.CLASSIFY_STAGE_A"
    db.close()


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
