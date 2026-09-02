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
        files=[("files", (name, io.BytesIO(data), "application/pdf"))],
    )


def _upload_many(client, school, aid, parts):
    """parts: list of (filename, bytes, content-type), in page order."""
    return client.post(
        f"/assessments/{aid}/scan",
        headers=_auth(school),
        files=[("files", (name, io.BytesIO(data), mime)) for name, data, mime in parts],
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
        # 8, because that is what the fixture paper adds up to: confirming a scan whose
        # marks disagree with the paper's own total is refused, and this test is about the
        # book being absent, not about the totals.
        json={"subject_code": "X.SCI", "title": "No book", "total_marks": 8},
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


# --- one page or many, PDFs or photographs -------------------------------------------------

def _one_page_pdf(lines):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text in lines:
        page.insert_text((x, y), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def _png(colour=(255, 255, 255)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (595, 842), colour).save(buf, "PNG")
    return buf.getvalue()


def test_several_pdf_pages_are_read_as_one_paper(client, school, assessment):
    first = _one_page_pdf([
        (60, 90, "SECTION A"),
        (60, 130, "1. First question on the first page."), (MARK_X, 130, "2"),
    ])
    second = _one_page_pdf([
        (60, 90, "2. Second question, on a separate page."), (MARK_X, 90, "3"),
    ])
    r = _upload_many(client, school, assessment, [
        ("p1.pdf", first, "application/pdf"),
        ("p2.pdf", second, "application/pdf"),
    ])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["pages"] == 2
    assert body["questions"] == 2
    assert body["total_marks"] == 5.0


def test_the_order_sent_is_the_order_read_not_the_filename_order(client, school, assessment):
    """A phone names photographs by the second they were taken and a scanner by a counter
    that resets. Sorting by name reorders a paper silently, and a paper read out of order
    produces question numbers that look plausible and are wrong."""
    page_one = _one_page_pdf([
        (60, 90, "SECTION A"),
        (60, 130, "1. This is the first question."), (MARK_X, 130, "1"),
    ])
    page_two = _one_page_pdf([(60, 90, "2. This is the second question."), (MARK_X, 90, "1")])

    r = _upload_many(client, school, assessment, [
        ("zzz-taken-first.pdf", page_one, "application/pdf"),
        ("aaa-taken-second.pdf", page_two, "application/pdf"),
    ])
    assert r.status_code == 201, r.text
    read = client.get(f"/assessments/{assessment}/scan", headers=_auth(school)).json()
    assert [q["question_no"] for q in read["questions"]] == ["1", "2"]
    assert [q["page"] for q in read["questions"]] == [1, 2]


def test_a_photograph_is_accepted_and_routed_to_vision(client, school, assessment):
    """A teacher photographing a paper has JPEGs, not a PDF. The image is accepted, and
    then correctly reported as unreadable text -- which is a different failure from
    'wrong file type', and the difference matters to whoever is standing there."""
    r = _upload_many(client, school, assessment, [("page1.png", _png(), "image/png")])
    assert r.status_code == 422
    assert "no usable text layer" in r.json()["detail"]


def test_a_file_that_is_neither_says_which_one(client, school, assessment):
    r = _upload_many(
        client, school, assessment, [("notes.docx", b"PK\x03\x04zzz", "application/octet-stream")]
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "notes.docx" in detail and "not a PDF or an image" in detail


def test_an_empty_page_is_named_rather_than_silently_skipped(client, school, assessment):
    good = _one_page_pdf([(60, 90, "SECTION A"), (60, 130, "1. A question."), (MARK_X, 130, "1")])
    r = _upload_many(client, school, assessment, [
        ("good.pdf", good, "application/pdf"),
        ("blank.pdf", b"", "application/pdf"),
    ])
    assert r.status_code == 422
    assert "blank.pdf is empty" in r.json()["detail"]


# ----------------------------------------------------------------------------------------
# Sub-part marks, through HTTP
# ----------------------------------------------------------------------------------------
#: A case study: a paragraph of context, then parts worth 1, 1 and 2. Read as one question
#: it is worth 1, and the paper is four marks short with nothing on screen to show it.
CASE_STUDY = [[
    (60, 60, "Maximum Marks: 6"),
    (60, 90, "SECTION A"),
    (60, 120, "1. Find the mean of the grouped data by the"),
    (60, 134, "step-deviation method, assumed mean 200."),
    (MARK_X, 120, "2"),
    (60, 200, "SECTION E"),
    (60, 230, "2. A dairy packs milk in sealed vessels shaped like a cylinder"),
    (60, 244, "with two hemispherical ends of the same radius."),
    (60, 274, "(i) Find the length of the cylindrical portion."),
    (MARK_X, 274, "1"),
    (60, 304, "(ii) Find the curved surface area of the cylinder."),
    (MARK_X, 304, "1"),
    (60, 334, "(iii) Find the total surface area of the vessel."),
    (MARK_X, 334, "2"),
]]


@pytest.fixture
def case_study_assessment(client, school):
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Case study", "total_marks": 6},
    )
    return r.json()["assessment_id"]


def test_each_sub_part_is_staged_with_its_own_marks(client, school, case_study_assessment):
    out = _upload(client, school, case_study_assessment, _paper_bytes(CASE_STUDY))
    assert out.status_code == 201, out.text
    body = out.json()

    assert body["total_marks"] == 6
    assert body["declared"]["total_marks"] == 6
    assert body["sub_parts"] == 3
    assert body["problems"] == []

    read = client.get(
        f"/assessments/{case_study_assessment}/scan", headers=_auth(school)
    ).json()
    marks = {q["address"]: q["max_marks"] for q in read["questions"]}
    assert marks["E/2/i/"] == 1
    assert marks["E/2/ii/"] == 1
    assert marks["E/2/iii/"] == 2
    assert read["marks"] == {"read": 6.0, "declared": 6.0, "short_by": 0.0}


def test_a_shared_stem_does_not_block_the_scan_from_being_confirmed(
    client, school, case_study_assessment
):
    """The paragraph above (i), (ii), (iii) carries no marks and is not a gap."""
    _upload(client, school, case_study_assessment, _paper_bytes(CASE_STUDY))
    read = client.get(
        f"/assessments/{case_study_assessment}/scan", headers=_auth(school)
    ).json()
    assert read["marks_missing"] == 0
    context = [q for q in read["questions"] if q["is_context"]]
    assert [q["address"] for q in context] == ["E/2//"]

    out = client.post(
        f"/assessments/{case_study_assessment}/scan/confirm",
        headers=_auth(school), json={},
    )
    assert out.status_code == 200, out.text
    assert out.json()["total_marks"] == 6


def test_confirming_is_refused_while_the_marks_do_not_add_up(client, school):
    """The guardrail the totals exist for.

    Every row here is readable and looks right. The paper is simply short, because a
    sub-part's marks were never found -- and a report built on it would understate what
    the student was asked, silently.
    """
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Short", "total_marks": 80},
    )
    aid = r.json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(PAPER))

    out = client.post(f"/assessments/{aid}/scan/confirm", headers=_auth(school), json={})
    assert out.status_code == 422
    detail = out.json()["detail"]
    assert "worth 80 marks" in detail and "add up to 8" in detail
    assert "72 are missing" in detail
    # And it says where to look, because "the totals disagree" is not actionable.
    assert "(i), (ii), (iii)" in detail


def test_the_marks_a_person_corrects_are_what_the_total_is_held_to(client, school):
    """Editing a row's marks has to move the total, or the check cannot be satisfied."""
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Fixable", "total_marks": 10},
    )
    aid = r.json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(PAPER))
    assert client.post(
        f"/assessments/{aid}/scan/confirm", headers=_auth(school), json={}
    ).status_code == 422

    # The paper really is worth 10: question 2 is a 7-mark question read as 5.
    fix = client.patch(
        f"/assessments/{aid}/scan/A/2//", headers=_auth(school), json={"max_marks": 7},
    )
    assert fix.status_code == 200, fix.text

    out = client.post(f"/assessments/{aid}/scan/confirm", headers=_auth(school), json={})
    assert out.status_code == 200, out.text
    assert out.json()["total_marks"] == 10


def test_the_marks_a_student_was_asked_for_count_a_choice_once(client, school):
    """A question printed as "(a) ... OR ... (b)" is worth its marks once.

    Adding both halves doubled what the sheet said the student was asked for; counting
    only the (a) half lost the marks entirely when the student answered (b) and (a) was
    marked as not offered, which is the normal way round.
    """
    from app.api.marks import _available

    rows = [
        {"section": "B", "question_no": "22", "sub_part": None, "choice_alt": "a",
         "max_marks": 2.0, "state": "not_offered"},
        {"section": "B", "question_no": "22", "sub_part": None, "choice_alt": "b",
         "max_marks": 2.0, "state": "awarded"},
        {"section": "A", "question_no": "1", "sub_part": None, "choice_alt": None,
         "max_marks": 1.0, "state": "awarded"},
    ]
    assert _available(rows) == 3.0

    # Untouched, both halves still count the question once.
    for row in rows:
        row["state"] = None
    assert _available(rows) == 3.0

    # A question the student was not asked at all counts for nothing.
    rows[2]["state"] = "not_offered"
    assert _available(rows) == 2.0
