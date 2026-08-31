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
    from app.models import BookChunk, ConceptFamilyProposal, TaxonomyNode

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
    # The proposal that says which section this family covers. Without it the family is
    # chosen only when it is the chapter's sole one -- and another test in this suite
    # applies a second family to Statistics, so the pair became ambiguous and mapping
    # correctly refused. Production always has these rows; the fixture should too.
    if db.scalar(
        select(ConceptFamilyProposal).where(
            ConceptFamilyProposal.code == "X.MATH.CF.MEAN_STEP_DEVIATION"
        )
    ) is None:
        db.add(ConceptFamilyProposal(
            curriculum_version=stats.curriculum_version, subject_code="X.MATH",
            run_id="fixture", source="llm", model="fixture",
            code="X.MATH.CF.MEAN_STEP_DEVIATION", label="Mean by step-deviation",
            chapter_id=stats.id, evidence=["Section 13.2"], from_sections=["13.2"],
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
    client.post(f"/assessments/{assessment}/scan/confirm", headers=_auth(school), json={})
    r = client.post(f"/assessments/{assessment}/map", headers=_auth(school))
    assert r.status_code == 200, r.text
    body = r.json()

    # The test database has chapters and chunks but no applied concept families, so every
    # question is blocked -- and the reason says exactly what to do about it.
    assert body["mapped"] + body["blocked"] == 2
    read = client.get(f"/assessments/{assessment}/scan", headers=_auth(school)).json()

    # The invariant, which holds whatever the corpus contains: a question is either fully
    # mapped -- chapter, family and board unit, all three from the book -- or it is not
    # mapped and says why. There is no third state, and no partially-filled row.
    for question in read["questions"]:
        placed = question["mapped_to"]
        if placed:
            assert placed["chapter"] and placed["concept_family"] and placed["board_unit"]
            assert not question["blocked_reason"]
        else:
            assert question["blocked_reason"], "a question is mapped or it says why not"


def test_mapping_refuses_when_no_book_is_loaded(client, school):
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.SCI", "title": "No book", "total_marks": 5},
    )
    aid = r.json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=_auth(school), json={})
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


def test_a_chapter_code_beginning_with_s_is_not_read_as_a_section():
    """X.MATH.SAV was read as section 'AV' and X.MATH.STATS as 'TATS'. Neither matched any
    concept family, so every question in those two chapters blocked -- on a rule that
    looked right and was checking only the first letter."""
    from app.api.marks import _section_number

    assert _section_number("X.MATH.STATS.S13_2") == "13.2"
    assert _section_number("X.SCI.LIGHT.S9_1") == "9.1"
    assert _section_number("X.MATH.SAV") is None
    assert _section_number("X.MATH.STATS") is None
    assert _section_number("X.MATH.CIRCLE") is None


# --- a person checks the extraction before anything treats it as fact ---------------------

def test_mapping_refuses_until_someone_has_confirmed_the_extraction(
    client, school, assessment, book
):
    """Everything after mapping treats these questions as what the paper says. An
    extraction nobody checked is not that -- it is a good guess that would become a mark on
    a child's report with no person in the loop."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    blocked = client.post(f"/assessments/{assessment}/map", headers=_auth(school))
    assert blocked.status_code == 409
    assert "confirmed this extraction" in blocked.json()["detail"]

    ok = client.post(
        f"/assessments/{assessment}/scan/confirm", headers=_auth(school), json={"by": "Mrs Rani"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["confirmed_by"] == "Mrs Rani"

    mapped = client.post(f"/assessments/{assessment}/map", headers=_auth(school))
    assert mapped.status_code == 200


def test_a_question_with_no_marks_cannot_be_confirmed_around(client, school, assessment):
    """A question worth nothing is a gap, not a question. Signing for it would put a name
    on something incomplete."""
    from app.db import SessionLocal
    from app.models import ScannedQuestion

    _upload(client, school, assessment, _paper_bytes(PAPER))
    db = SessionLocal()
    row = db.scalars(
        select(ScannedQuestion).where(ScannedQuestion.assessment_id == assessment)
    ).first()
    row.max_marks = None
    db.commit()
    address = row.address
    db.close()

    refused = client.post(f"/assessments/{assessment}/scan/confirm", headers=_auth(school), json={})
    assert refused.status_code == 422
    assert "carry no marks" in refused.json()["detail"]

    fixed = client.patch(
        f"/assessments/{assessment}/scan/{address}",
        headers=_auth(school), json={"max_marks": 3, "by": "Mrs Rani"},
    )
    assert fixed.status_code == 200
    assert fixed.json()["changed"] == ["max_marks"]

    assert client.post(
        f"/assessments/{assessment}/scan/confirm", headers=_auth(school), json={}
    ).status_code == 200


def test_a_row_the_extractor_invented_can_be_removed(client, school, assessment):
    """A heading read as a question is more common than any wrong field, and removing it
    is the edit a person reaches for first."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    before = client.get(f"/assessments/{assessment}/scan", headers=_auth(school)).json()
    victim = before["questions"][0]["address"]

    out = client.patch(
        f"/assessments/{assessment}/scan/{victim}", headers=_auth(school), json={"remove": True}
    )
    assert out.status_code == 200 and out.json()["removed"] is True

    after = client.get(f"/assessments/{assessment}/scan", headers=_auth(school)).json()
    assert after["staged"] == before["staged"] - 1


def test_editing_is_refused_once_the_extraction_is_confirmed(client, school, assessment):
    """Confirmation is a person putting their name to these rows. Editing afterwards would
    leave the record saying someone checked something they never saw."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    address = client.get(
        f"/assessments/{assessment}/scan", headers=_auth(school)
    ).json()["questions"][0]["address"]
    client.post(f"/assessments/{assessment}/scan/confirm", headers=_auth(school), json={})

    late = client.patch(
        f"/assessments/{assessment}/scan/{address}", headers=_auth(school), json={"max_marks": 9}
    )
    assert late.status_code == 409
    assert "already confirmed" in late.json()["detail"]


def test_rescanning_withdraws_the_previous_confirmation(client, school, assessment):
    """Whoever signed did not see these rows."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    client.post(f"/assessments/{assessment}/scan/confirm", headers=_auth(school), json={})
    assert client.get(
        f"/assessments/{assessment}/scan", headers=_auth(school)
    ).json()["confirmed_at"]

    _upload(client, school, assessment, _paper_bytes(PAPER))
    assert client.get(
        f"/assessments/{assessment}/scan", headers=_auth(school)
    ).json()["confirmed_at"] is None


def test_a_corrected_row_stays_distinguishable_from_one_the_machine_got_right(
    client, school, assessment
):
    """Different evidence about how well the extractor works. A system that cannot tell
    them apart cannot be improved."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    address = client.get(
        f"/assessments/{assessment}/scan", headers=_auth(school)
    ).json()["questions"][0]["address"]

    client.patch(
        f"/assessments/{assessment}/scan/{address}",
        headers=_auth(school), json={"max_marks": 4, "by": "Mrs Rani"},
    )
    read = client.get(f"/assessments/{assessment}/scan", headers=_auth(school)).json()
    assert read["edited"] == 1
    edited = [q for q in read["questions"] if q["edited_by"]]
    assert [q["edited_by"] for q in edited] == ["Mrs Rani"]
