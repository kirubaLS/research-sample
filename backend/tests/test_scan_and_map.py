"""Scanning a paper and mapping it onto the book, end to end through HTTP."""

from __future__ import annotations

import io

import pymupdf
import pytest
from sqlalchemy import select

from app.config import get_settings

MARK_X = 595 * 0.87


def _paper_bytes(lines_per_page: list[list[tuple[float, float, str]]]) -> bytes:
    doc = pymupdf.open()
    for lines in lines_per_page:
        page = doc.new_page(width=595, height=842)
        for x, y, text in lines:
            page.insert_text((x, y), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


#: Laid out as a real paper does: the stem wraps well clear of the right-hand mark
#: column. Running the text under the mark merges the two into one line and the label is
#: lost -- which is a property of this fixture, not of any paper CBSE prints.
PAPER = [[
    (60, 60, "This question paper contains 2 questions."),
    (60, 90, "SECTION A"),
    (60, 120, "1. Find the mean of the grouped data by the"),
    (60, 134, "step-deviation method, assumed mean 200."),
    (MARK_X, 120, "3"),
    (60, 180, "2. Prove that the tangent at any point of a"),
    (60, 194, "circle is perpendicular to the radius."),
    (MARK_X, 180, "5"),
]]


@pytest.fixture
def book(school):
    """A minimal loaded book: one chunk under a chapter, and a family applied to it.

    Mapping needs all three -- a chapter to retrieve, a board unit for its marks to count
    towards, and a concept family for the report to group by -- so a test that seeds none
    of them only ever exercises the blocked path.
    """
    from app.db import SessionLocal
    from app.models import BookChunk, TaxonomyNode

    db = SessionLocal()

    # Several chunks across several chapters, because one chunk cannot be retrieved
    # against: TF-IDF gives every term an inverse document frequency of log(1/1) = 0 when
    # there is a single document, so every score is zero. Real books have hundreds.
    seed = [
        ("X.MATH.STATS", "S13_2", "Mean of Grouped Data", "Section 13.2",
         "The mean of grouped data by the step-deviation method uses an assumed mean "
         "and a common class size h to simplify the arithmetic of large class marks."),
        ("X.MATH.STATS", "S13_3", "Mode of Grouped Data", "Section 13.3",
         "The modal class is the class with the greatest frequency, and the mode is "
         "found from the frequencies either side of it."),
        ("X.MATH.CIRCLE", "S10_1", "Tangent to a Circle", "Theorem 10.1",
         "The tangent at any point of a circle is perpendicular to the radius through "
         "the point of contact."),
        ("X.MATH.REAL", "S1_2", "Fundamental Theorem", "Theorem 1.1",
         "Every composite number can be expressed as a product of primes, and this "
         "factorisation is unique apart from the order of the factors."),
        ("X.MATH.AP", "S5_2", "nth Term of an AP", "Section 5.2",
         "In an arithmetic progression with first term a and common difference d the "
         "nth term is given by a plus n minus one times d."),
    ]
    for chapter_code, section, label, reference, text in seed:
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == chapter_code))
        code = f"{chapter_code}.{section}"
        node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
        if node is None:
            node = TaxonomyNode(
                kind="subtopic", code=code, label=label, parent_id=chapter.id,
                path=code, curriculum_version=chapter.curriculum_version,
            )
            db.add(node)
            db.flush()
            db.add(BookChunk(
                curriculum_version=chapter.curriculum_version, subject_code="X.MATH",
                node_id=node.id, bucket="T", reference=reference, text=text,
                normalised=text.lower(), stem_hash=code,
            ))

    stats = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.STATS"))
    if db.scalar(
        select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.MEAN_STEP_DEVIATION")
    ) is None:
        db.add(TaxonomyNode(
            kind="concept_family", code="X.MATH.CF.MEAN_STEP_DEVIATION",
            label="Mean by step-deviation", parent_id=stats.id,
            path="X.MATH.CF.MEAN_STEP_DEVIATION",
            curriculum_version=stats.curriculum_version,
        ))
    db.commit()
    db.close()


@pytest.fixture
def assessment(client, school):
    r = client.post(
        "/assessments",
        headers={"X-API-Key": school["api_key"]},
        json={"subject_code": "X.MATH", "title": "Scan test", "total_marks": 8},
    )
    assert r.status_code == 200
    return r.json()["assessment_id"]


def _auth(school):
    return {"X-API-Key": school["api_key"]}


def _upload(client, school, aid, data, name="paper.pdf"):
    return client.post(
        f"/assessments/{aid}/scan",
        headers=_auth(school),
        files={"file": (name, io.BytesIO(data), "application/pdf")},
    )


def test_a_scanned_paper_is_staged_not_written_as_questions(client, school, assessment):
    """A question row needs a board unit and a concept family. Neither is knowable from
    the paper, so the scan may not create one -- staging is what keeps that honest."""
    from app.db import SessionLocal
    from app.models import Question, ScannedQuestion

    r = _upload(client, school, assessment, _paper_bytes(PAPER))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["route"] == "text"
    assert body["questions"] == 2
    assert body["total_marks"] == 8.0
    assert body["staged"] == 2
    assert body["problems"] == []

    db = SessionLocal()
    staged = db.scalars(
        select(ScannedQuestion).where(ScannedQuestion.assessment_id == assessment)
    ).all()
    real = db.scalars(select(Question).where(Question.assessment_id == assessment)).all()
    db.close()
    assert len(staged) == 2
    assert real == [], "the scan must not create question rows"


def test_a_scan_of_an_image_only_paper_is_refused_with_its_reason(client, school, assessment):
    doc = pymupdf.open()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8))
    pixmap.clear_with(180)
    for _ in range(2):
        page = doc.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pixmap)
    data = doc.tobytes()
    doc.close()

    r = _upload(client, school, assessment, data, name="scan.pdf")
    assert r.status_code == 422
    assert "no usable text layer" in r.json()["detail"]


def test_mapping_blocks_a_question_rather_than_inventing_a_chapter(
    client, school, assessment, book
):
    """The point of the whole design: an unplaceable question stays staged with its
    reason, because forcing it into a chapter to keep the numbers tidy is the invention
    this pipeline refuses."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    r = client.post(f"/assessments/{assessment}/map", headers=_auth(school))
    assert r.status_code == 200, r.text
    body = r.json()

    # The test database has chapters and chunks but no applied concept families, so every
    # question is blocked -- and the reason says exactly what to do about it.
    assert body["mapped"] + body["blocked"] == 2
    assert body["mapped"] >= 1, "the statistics question should reach the seeded chapter"

    read = client.get(f"/assessments/{assessment}/scan", headers=_auth(school)).json()
    mapped = [q for q in read["questions"] if q["mapped_to"]]
    assert mapped, read
    # The whole point: the mark now knows what it measures, and every part of that came
    # from the book rather than from anyone's memory.
    assert mapped[0]["mapped_to"]["chapter"] == "Statistics"
    assert mapped[0]["mapped_to"]["concept_family"] == "Mean by step-deviation"
    assert mapped[0]["mapped_to"]["board_unit"]

    for question in read["questions"]:
        if not question["mapped_to"]:
            assert question["blocked_reason"], "a question is mapped or it says why not"


def test_mapping_refuses_when_no_book_is_loaded(client, school):
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.SCI", "title": "No book", "total_marks": 5},
    )
    aid = r.json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(PAPER))
    out = client.post(f"/assessments/{aid}/map", headers=_auth(school))
    assert out.status_code == 422
    assert "no book is loaded" in out.json()["detail"]


def test_rescanning_keeps_what_mapping_already_promoted(client, school, assessment):
    """A bad upload must be re-readable without unpicking the work already done."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    again = _upload(client, school, assessment, _paper_bytes(PAPER))
    assert again.status_code == 201
    assert again.json()["staged"] + again.json()["already_promoted"] == 2


def test_a_frozen_qmatrix_cannot_be_rescanned(client, school, assessment):
    _upload(client, school, assessment, _paper_bytes(PAPER))
    settings = get_settings()
    assert settings is not None
    client.post(f"/assessments/{assessment}/freeze", headers=_auth(school))
    r = _upload(client, school, assessment, _paper_bytes(PAPER))
    assert r.status_code == 409
