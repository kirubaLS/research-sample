"""Reading marks out of a file, and a person confirming them before anything is stored.

Retyping marks is where they get transposed, and a transposed number looks exactly like a
read one afterwards. So the file is read -- and then somebody who saw the paper says yes.
"""

from __future__ import annotations

import io

import pytest
from sqlalchemy import select


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@pytest.fixture
def student(school):
    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    existing = db.scalar(
        select(StudentProfile).where(
            StudentProfile.section_id == school["section_id"], StudentProfile.roll_no == "077"
        )
    )
    if existing is None:
        existing = StudentProfile(
            school_id=school["school_id"], section_id=school["section_id"],
            name="Reading test student", roll_no="077",
        )
        db.add(existing)
        db.commit()
    sid = existing.id
    db.close()
    return sid


@pytest.fixture
def paper(client, school):
    """A three-question paper, straight into the Q-matrix."""
    aid = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Reading test", "total_marks": 10},
    ).json()["assessment_id"]
    out = client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 2, "board_unit": "X.MATH.U.STATSPROB",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"read-{aid}-1"},
            {"section": "B", "question_no": "2", "max_marks": 3, "board_unit": "X.MATH.U.STATSPROB",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"read-{aid}-2"},
            {"section": "B", "question_no": "3", "max_marks": 5, "board_unit": "X.MATH.U.STATSPROB",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"read-{aid}-3"},
        ]},
    )
    assert out.status_code == 200, out.text
    return aid


def _read(client, school, paper, student, name, data):
    return client.post(
        f"/assessments/{paper}/answers/{student}/read", headers=_auth(school),
        files=[("files", (name, io.BytesIO(data), "text/csv"))],
    )


def test_a_wide_sheet_is_read_and_nothing_is_stored_as_a_mark_yet(
    client, school, paper, student
):
    """The machine proposes; a person disposes. Reading a file must not move a figure."""
    out = _read(client, school, paper, student, "marks.csv", b"Roll,Q1,B/2,B/3\n077,2,1.5,4\n")
    assert out.status_code == 201, out.text
    assert out.json()["read"] == 3

    from app.db import SessionLocal
    from app.models import MarkEvent

    db = SessionLocal()
    events = db.scalars(select(MarkEvent).where(MarkEvent.student_id == student)).all()
    db.close()
    assert events == [], "reading a file must not write a single mark"

    sheet = client.get(
        f"/assessments/{paper}/answers/{student}/reading", headers=_auth(school)
    ).json()
    assert sheet["read"] == 3 and sheet["missing"] == 0
    assert sheet["can_confirm"] is True
    # every proposal traceable to the cell it came from
    assert all("row 2" in q["origin"] for q in sheet["questions"])


def test_a_long_sheet_is_read_the_same_way(client, school, paper, student):
    csv = b"Roll No,Question,Marks\n077,Q1,2\n077,B/2,3\n077,B/3,5\n"
    assert _read(client, school, paper, student, "long.csv", csv).json()["read"] == 3


def test_a_question_the_paper_does_not_have_is_reported_not_invented(
    client, school, paper, student
):
    out = _read(client, school, paper, student, "marks.csv", b"Roll,Q1,Q9\n077,2,5\n").json()
    assert out["read"] == 1
    assert len(out["unmatched"]) == 1
    assert "no question 9" in out["unmatched"][0]["reason"]


def test_a_mark_above_the_maximum_blocks_confirmation_rather_than_being_clamped(
    client, school, paper, student
):
    """Clamping turns a typo into a plausible number nobody would question again."""
    _read(client, school, paper, student, "marks.csv", b"Roll,Q1,B/2,B/3\n077,99,1,4\n")
    sheet = client.get(
        f"/assessments/{paper}/answers/{student}/reading", headers=_auth(school)
    ).json()
    bad = next(q for q in sheet["questions"] if q["question_no"] == "1")
    assert "more than the 2" in bad["problem"]
    assert sheet["can_confirm"] is False

    refused = client.post(
        f"/assessments/{paper}/answers/{student}/reading/confirm",
        headers=_auth(school), json={"by": "Mrs Rani"},
    )
    assert refused.status_code == 422 and "still have a problem" in refused.json()["detail"]


def test_a_person_corrects_a_row_and_then_it_confirms(client, school, paper, student):
    _read(client, school, paper, student, "marks.csv", b"Roll,Q1,B/2,B/3\n077,99,1,4\n")
    fixed = client.patch(
        f"/assessments/{paper}/answers/{student}/reading/A/1//",
        headers=_auth(school), json={"marks": 2, "state": "awarded", "by": "Mrs Rani"},
    ).json()
    assert fixed["can_confirm"] is True
    row = next(q for q in fixed["questions"] if q["question_no"] == "1")
    assert row["marks"] == 2.0 and row["edited_by"] == "Mrs Rani"

    out = client.post(
        f"/assessments/{paper}/answers/{student}/reading/confirm",
        headers=_auth(school), json={"by": "Mrs Rani"},
    )
    assert out.status_code == 200, out.text
    assert out.json()["written"] == 3

    # and now they are marks, carrying where they came from
    from app.db import SessionLocal
    from app.models import MarkEvent

    db = SessionLocal()
    events = db.scalars(select(MarkEvent).where(MarkEvent.student_id == student)).all()
    provenance = [e.provenance for e in events]
    db.close()
    assert len(events) == 3
    assert all(e.source == "teacher" for e in events)
    assert any(p.get("read_from") == "marks.csv" for p in provenance)
    assert any(p.get("edited_by") == "Mrs Rani" for p in provenance)


def test_an_unreadable_value_is_flagged_rather_than_guessed(client, school, paper, student):
    _read(client, school, paper, student, "marks.csv", b"Roll,Q1\n077,three\n")
    sheet = client.get(
        f"/assessments/{paper}/answers/{student}/reading", headers=_auth(school)
    ).json()
    row = next(q for q in sheet["questions"] if q["question_no"] == "1")
    assert row["problem"] and "not a mark" in row["problem"]


def test_absent_and_not_offered_survive_the_read(client, school, paper, student):
    """'AB' is not zero, and the unattempted half of a choice is not zero either."""
    _read(client, school, paper, student, "marks.csv", b"Roll,Q1,B/2\n077,AB,not offered\n")
    sheet = client.get(
        f"/assessments/{paper}/answers/{student}/reading", headers=_auth(school)
    ).json()
    states = {q["question_no"]: q["state"] for q in sheet["questions"] if q["read"]}
    assert states == {"1": "absent", "2": "not_offered"}


def test_a_page_with_nothing_readable_on_it_says_so(client, school, paper, student):
    """Whether or not recognition is available, a blank page yields no marks and says why.
    What must never happen is an empty success that reads like a sheet of zeros."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 400, 500))
    pix.set_rect(pix.irect, (250, 250, 250))
    page.insert_image(pymupdf.Rect(40, 40, 440, 540), pixmap=pix)
    data = doc.tobytes()
    doc.close()

    out = client.post(
        f"/assessments/{paper}/answers/{student}/read", headers=_auth(school),
        files=[("files", ("photo.pdf", io.BytesIO(data), "application/pdf"))],
    )
    assert out.status_code == 422
    detail = out.json()["detail"]
    assert "handwriting" in detail or "could not find a marks table" in detail


def test_a_spreadsheet_is_read_from_its_cells(client, school, paper, student):
    import openpyxl

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Roll", "Q1", "B/2", "B/3"])
    sheet.append(["077", 2, 3, 5])
    buffer = io.BytesIO()
    book.save(buffer)

    out = client.post(
        f"/assessments/{paper}/answers/{student}/read", headers=_auth(school),
        files=[("files", ("marks.xlsx", io.BytesIO(buffer.getvalue()),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))],
    )
    assert out.status_code == 201, out.text
    assert out.json()["read"] == 3


def test_a_file_of_a_kind_we_cannot_read_says_so_and_says_what_to_send(
    client, school, paper, student
):
    out = _read(client, school, paper, student, "marks.docx", b"PK\x03\x04nonsense")
    assert out.status_code == 422
    assert "CSV" in out.json()["detail"]


def _printed_marks_pdf() -> bytes:
    """A marks sheet as a school prints it: a title, a header row, aligned columns."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 60), "BHARATH INTERNATIONAL SR. SEC. SCHOOL", fontsize=12)
    page.insert_text((60, 80), "Cycle Test I - Mathematics - Class 10-A", fontsize=10)
    columns = [60, 200, 300, 400, 500]
    for x, text in zip(columns, ["Roll No", "Q1", "B/2", "B/3", "Total"], strict=True):
        page.insert_text((x, 120), text, fontsize=10)
    for i, row in enumerate([["077", "2", "3", "4.5", "9.5"], ["078", "1", "AB", "5", "6"]]):
        for x, text in zip(columns, row, strict=True):
            page.insert_text((x, 145 + i * 22), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def test_a_printed_marks_sheet_is_read_out_of_the_pdf(client, school, paper, student):
    """A PDF exported from a computer carries its text, so it needs no recognition at all.

    This is the common case a school actually has: the exam cell prints the mark list to
    PDF rather than sending the spreadsheet.
    """
    out = client.post(
        f"/assessments/{paper}/answers/{student}/read", headers=_auth(school),
        files=[("files", ("marks.pdf", io.BytesIO(_printed_marks_pdf()), "application/pdf"))],
    )
    assert out.status_code == 201, out.text
    body = out.json()
    assert body["read"] == 3
    # The Total column is not a question, so it is not read as one.
    assert all("Total" not in u["raw_address"] for u in body["unmatched"])

    sheet = client.get(
        f"/assessments/{paper}/answers/{student}/reading", headers=_auth(school)
    ).json()
    marks = {q["question_no"]: q["marks"] for q in sheet["questions"]}
    assert marks == {"1": 2.0, "2": 3.0, "3": 4.5}


def test_a_pdf_table_is_read_from_its_geometry_not_from_line_breaks():
    """Splitting the page text on whitespace looked reasonable and lost every row: PyMuPDF
    emits each cell of a table on its own line, so a five-column sheet arrived as five
    one-word lines."""
    import pymupdf

    from app.extraction.marksheet import table_from_words

    doc = pymupdf.open(stream=_printed_marks_pdf(), filetype="pdf")
    table = table_from_words(doc[0].get_text("words"))
    doc.close()

    header = next(row for row in table if any(c == "Q1" for c in row))
    body = next(row for row in table if any(c == "077" for c in row))
    assert header.index("Q1") == body.index("2"), "a cell must land under its own heading"
    assert header.index("B/3") == body.index("4.5")


def test_a_scan_is_refused_by_name_where_recognition_is_not_installed(
    client, school, paper, student, monkeypatch
):
    """Text recognition is a system binary, so a deployment either has it or does not.
    Without it a scan must say so and say what to send instead, never read as empty."""
    monkeypatch.setattr("app.extraction.marksheet.ocr_available", lambda: False)
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 400, 500))
    pix.set_rect(pix.irect, (240, 240, 240))
    page.insert_image(pymupdf.Rect(40, 40, 440, 540), pixmap=pix)
    data = doc.tobytes()
    doc.close()

    out = client.post(
        f"/assessments/{paper}/answers/{student}/read", headers=_auth(school),
        files=[("files", ("scan.pdf", io.BytesIO(data), "application/pdf"))],
    )
    assert out.status_code == 422
    detail = out.json()["detail"]
    assert "text recognition is not available" in detail and "spreadsheet" in detail


def _page_image(rows: list[list[str]]) -> bytes:
    """A photograph of a printed marks sheet, as a PNG. What a phone camera produces."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    columns = [60, 200, 320, 440]
    for i, row in enumerate(rows):
        for x, text in zip(columns, row, strict=False):
            page.insert_text((x, 120 + i * 40), text, fontsize=16)
    pix = page.get_pixmap(dpi=200)
    doc.close()
    return pix.tobytes("png")


def test_photographed_pages_are_read_through_the_same_path_as_the_question_paper(
    client, school, paper, student
):
    """Images are merged into one document, in the order they were sent, and read from
    there. Two upload paths accepting different things is how one ends up rejecting a file
    the other allows, with nobody able to say which is right."""
    if not __import__("app.extraction.marksheet", fromlist=["x"]).ocr_available():
        pytest.skip("text recognition is not installed here")

    first = _page_image([["Roll No", "Q1", "B/2"], ["077", "2", "3"]])
    second = _page_image([["Roll No", "B/3"], ["077", "5"]])

    out = client.post(
        f"/assessments/{paper}/answers/{student}/read", headers=_auth(school),
        files=[
            ("files", ("page1.png", io.BytesIO(first), "image/png")),
            ("files", ("page2.png", io.BytesIO(second), "image/png")),
        ],
    )
    assert out.status_code == 201, out.text
    body = out.json()
    assert body["used_ocr"] is True
    assert body["read"] >= 1, "at least one column has to survive recognition"
    assert "2 pages" in body["source"]


def test_every_recognised_mark_is_held_until_a_person_has_looked_at_it(
    client, school, paper, student
):
    """Recognition proposes; it never asserts.

    On a real scan Tesseract reads 'Q1' as 'Qi'. A value it misread the same way would be
    indistinguishable from one read exactly, so no recognised mark may be confirmed until
    somebody has checked it against the sheet -- and until then confirming is refused.
    """
    if not __import__("app.extraction.marksheet", fromlist=["x"]).ocr_available():
        pytest.skip("text recognition is not installed here")

    image = _page_image([["Roll No", "B/2"], ["077", "3"]])
    client.post(
        f"/assessments/{paper}/answers/{student}/read", headers=_auth(school),
        files=[("files", ("sheet.png", io.BytesIO(image), "image/png"))],
    )

    sheet = client.get(
        f"/assessments/{paper}/answers/{student}/reading", headers=_auth(school)
    ).json()
    recognised = [q for q in sheet["questions"] if q["read"]]
    assert recognised, "recognition read nothing at all"
    assert all("text recognition" in q["problem"] for q in recognised)
    assert sheet["can_confirm"] is False

    refused = client.post(
        f"/assessments/{paper}/answers/{student}/reading/confirm",
        headers=_auth(school), json={"by": "Mrs Rani"},
    )
    assert refused.status_code == 422

    # A person accepts the value they can see is right, and now it may be confirmed.
    for row in recognised:
        client.patch(
            f"/assessments/{paper}/answers/{student}/reading/{row['address']}",
            headers=_auth(school),
            json={"marks": row["marks"], "state": "awarded", "by": "Mrs Rani"},
        )
    after = client.get(
        f"/assessments/{paper}/answers/{student}/reading", headers=_auth(school)
    ).json()
    assert after["can_confirm"] is True
