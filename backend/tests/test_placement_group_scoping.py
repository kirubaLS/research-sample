"""A single English paper draws on all 3 English books at once, and /place has to retrieve
and place against all of them -- not just whichever book happens to be first -- while never
letting two different subjects' identically-labelled chapters collide (see
app/api/placement.py's _chapters_in_subjects and group_subjects).
"""

from __future__ import annotations

import io
import uuid

import pymupdf
import pytest
from sqlalchemy import select


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@pytest.fixture
def english_books(school):
    """First Flight and Footprints without Feet, each with one real chapter, a concept
    family, and a book chunk retrieval can actually match -- across two of the three books
    in the X.ENG group, so a question phrased for the second book is not silently
    restricted to the first.
    """
    from app.curriculum import X_ENGLISH_FIRST_FLIGHT, X_ENGLISH_FOOTPRINTS
    from app.curriculum.apply import apply as apply_curriculum
    from app.db import SessionLocal
    from app.models import BookChunk, TaxonomyNode

    db = SessionLocal()
    try:
        apply_curriculum(db, X_ENGLISH_FIRST_FLIGHT)
        apply_curriculum(db, X_ENGLISH_FOOTPRINTS)

        ff_chapter = db.scalar(
            select(TaxonomyNode).where(TaxonomyNode.code == "X.ENG.FF.MANDELA")
        )
        fwf_chapter = db.scalar(
            select(TaxonomyNode).where(TaxonomyNode.code == "X.ENG.FWF.SURGERY")
        )

        for chapter, subject_code, family_code, family_label, text in [
            (ff_chapter, "X.ENG.FF", "X.ENG.FF.CF.MANDELA", "Nelson Mandela: Long Walk to Freedom",
             "Mandela described how deep down in every human heart there is mercy and "
             "generosity, and no one is born hating another person because of the colour "
             "of his skin."),
            (fwf_chapter, "X.ENG.FWF", "X.ENG.FWF.CF.SURGERY", "A Triumph of Surgery",
             "Tricki the dog was overfed by his doting owner Mrs Pumphrey until the vet "
             "Mr Herriot took him in for a strict diet and a triumph of surgery."),
        ]:
            db.add(BookChunk(
                curriculum_version=chapter.curriculum_version, subject_code=subject_code,
                node_id=chapter.id, bucket="T", reference=chapter.label, text=text,
                section_number="1", normalised=text.lower(), stem_hash=chapter.code,
            ))
            if db.scalar(
                select(TaxonomyNode).where(TaxonomyNode.code == family_code)
            ) is None:
                # A chapter with exactly one family and no section to match on falls to
                # that family on its own (see app.mapping.family.choose_family), so no
                # ConceptFamilyProposal row is needed for this fixture.
                db.add(TaxonomyNode(
                    kind="concept_family", code=family_code, label=family_label,
                    parent_id=chapter.id, path=family_code,
                    curriculum_version=chapter.curriculum_version,
                ))
        db.commit()
    finally:
        db.close()
    return {"ff_chapter": "Nelson Mandela: Long Walk to Freedom", "fwf_chapter": "A Triumph of Surgery"}


@pytest.fixture
def english_paper(client, school, english_books):
    tag = uuid.uuid4().hex[:8]
    created = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.ENG", "title": f"English Unit Test {tag}", "total_marks": 4},
    )
    aid = created.json()["assessment_id"]
    added = client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 2,
             "stem_text": "Why did Mandela describe deep down in every human heart?",
             "board_unit": "X.ENG.FF.U.WHOLE", "concept_family": "X.ENG.FF.CF.MANDELA",
             "concept_variant": f"mandela {tag}"},
            {"section": "A", "question_no": "2", "max_marks": 2,
             "stem_text": "How did Mr Herriot treat Tricki the overfed dog at the surgery?",
             "board_unit": "X.ENG.FWF.U.WHOLE", "concept_family": "X.ENG.FWF.CF.SURGERY",
             "concept_variant": f"tricki surgery {tag}"},
        ]},
    )
    assert added.status_code == 200, added.json()
    return aid


def test_identical_chapter_labels_in_different_subjects_do_not_collide(school, english_books):
    """The pre-existing global by_label dict collided any two chapters sharing a label,
    anywhere in the taxonomy. Scoped to a group, a same-named chapter belonging to an
    unrelated subject must never be reachable."""
    from app.api.placement import _chapters_in_subjects
    from app.curriculum import group_subjects
    from app.db import SessionLocal
    from app.models import TaxonomyNode

    db = SessionLocal()
    try:
        math_subject = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH"))
        # A chapter under an unrelated subject (Math), deliberately given the exact same
        # label as the English fixture's own chapter.
        collider = TaxonomyNode(
            kind="chapter", code="X.MATH.FAKE_COLLIDER", label="Nelson Mandela: Long Walk to Freedom",
            parent_id=math_subject.id, path="X.MATH.FAKE_COLLIDER",
        )
        db.add(collider)
        db.commit()

        nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
        chapter_ids = _chapters_in_subjects(nodes, group_subjects("X.ENG"))
        by_label = {
            n.label: n for n in nodes.values()
            if n.kind == "chapter" and n.id in chapter_ids
        }
        # The English fixture's own chapter is reachable, and it is the English one --
        # not silently overwritten by Math's identically-labelled fake.
        assert by_label["Nelson Mandela: Long Walk to Freedom"].code == "X.ENG.FF.MANDELA"
        assert collider.id not in chapter_ids
    finally:
        db.delete(db.get(TaxonomyNode, collider.id))
        db.commit()
        db.close()


def test_place_retrieves_book_chunks_across_the_whole_group(school, english_books):
    from app.curriculum import group_subjects
    from app.db import SessionLocal
    from app.models import BookChunk

    db = SessionLocal()
    try:
        codes = group_subjects("X.ENG")
        chunks = db.scalars(
            select(BookChunk).where(BookChunk.subject_code.in_(codes))
        ).all()
        assert {c.subject_code for c in chunks} == {"X.ENG.FF", "X.ENG.FWF"}
    finally:
        db.close()


def test_place_scores_a_group_paper_against_the_second_books_chapter_too(
    client, school, english_paper, english_books,
):
    """A question phrased to match Footprints without Feet must actually be placeable
    there, not silently restricted to whichever book is first in the group."""
    from app.api.placement import _run_placement_job
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import PlacementJob, Question, QuestionPlacement

    settings = get_settings()
    before_key = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    class StubJudge:
        """A real judge reads the passages retrieval found; this stub reproduces its
        answer for each of the two fixture questions, one per book."""

        def classify(self, question, evidence):
            from app.classify.judge import Classification

            if "mandela" in question.lower():
                return Classification(
                    chapter=english_books["ff_chapter"], tier="Understanding",
                    curriculum_section="1.1", skill_required="",
                    reasoning="mandela chapter", confidence=0.9,
                )
            return Classification(
                chapter=english_books["fwf_chapter"], tier="Understanding",
                curriculum_section="1.1", skill_required="",
                reasoning="tricki the dog", confidence=0.9,
            )

    class StubJudgeFactory:
        def __new__(cls, *a, **kw):
            return StubJudge()

    from app.classify import anthropic_judge as anthropic_judge_module

    db = SessionLocal()
    try:
        job = PlacementJob(school_id=school["school_id"], assessment_id=english_paper)
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    original = anthropic_judge_module.AnthropicJudge
    try:
        anthropic_judge_module.AnthropicJudge = StubJudgeFactory
        _run_placement_job(job_id)
    finally:
        settings.anthropic_api_key = before_key
        anthropic_judge_module.AnthropicJudge = original

    db = SessionLocal()
    try:
        job = db.get(PlacementJob, job_id)
        assert job.status == "succeeded", job.error_detail

        questions = {
            q.question_no: q
            for q in db.scalars(
                select(Question).where(Question.assessment_id == english_paper)
            )
        }
        from app.models import TaxonomyNode

        q1_chapter = db.get(TaxonomyNode, questions["1"].chapter_id)
        q2_chapter = db.get(TaxonomyNode, questions["2"].chapter_id)
        assert q1_chapter.label == "Nelson Mandela: Long Walk to Freedom"
        # The second book's chapter, actually reached -- not silently restricted to the
        # first book in the group.
        assert q2_chapter.label == "A Triumph of Surgery"
        assert q1_chapter.id != q2_chapter.id
    finally:
        db.close()


def test_map_retrieves_book_chunks_across_the_whole_group(client, school, english_books):
    """/map (the older, non-LLM lexical route) has to expand a group code the same way
    /place does -- a query for BookChunk.subject_code == 'X.ENG' matches nothing, since
    every chunk is filed under its own book (X.ENG.FF, X.ENG.FWF, ...), which is exactly
    what produced 'no book is loaded for X.ENG' on a real paper with books plainly loaded.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    mark_x = 595 * 0.87
    page.insert_text((60, 90), "SECTION A")
    page.insert_text((60, 120), "1. Why did Mandela describe deep down in every human")
    page.insert_text((60, 134), "heart there is mercy and generosity?")
    page.insert_text((mark_x, 120), "2")
    data = doc.tobytes()
    doc.close()

    created = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.ENG", "title": "English group map test", "total_marks": 2},
    )
    aid = created.json()["assessment_id"]
    up = client.post(
        f"/assessments/{aid}/scan", headers=_auth(school),
        files=[("files", ("paper.pdf", io.BytesIO(data), "application/pdf"))],
    )
    assert up.status_code == 201, up.text
    confirmed = client.post(f"/assessments/{aid}/scan/confirm", headers=_auth(school), json={})
    assert confirmed.status_code == 200, confirmed.text

    mapped = client.post(f"/assessments/{aid}/map", headers=_auth(school))
    assert mapped.status_code == 200, mapped.text
    assert "no book is loaded" not in mapped.text
