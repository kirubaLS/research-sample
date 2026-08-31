"""Reading a question paper into questions.

Every case here came from a real CBSE paper in this project. The synthetic PDFs reproduce
the exact layout property under test, because the papers themselves cannot ship in the
repo -- but a rule invented from an imagined paper is a rule that fails on the first real
one, so nothing here is imagined.
"""

from __future__ import annotations

import pymupdf
import pytest

from app.extraction.paper import extract_paper, readable_letters


def _pdf(tmp_path, pages: list[list[tuple[float, float, str]]], name="p.pdf"):
    """Write a PDF placing each (x, y, text) exactly, so the mark band is real."""
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page(width=595, height=842)
        for x, y, text in lines:
            page.insert_text((x, y), text, fontsize=10)
    path = tmp_path / name
    doc.save(path)
    doc.close()
    return path


#: x for a right-aligned mark label: the band is 0.845-0.925 of page width
MARK_X = 595 * 0.87


def test_a_scan_is_reported_as_needing_vision_not_returned_empty(tmp_path):
    """The Class X Maths board paper is six pages, 116 images and zero characters. An
    empty result would look exactly like a successful extraction of a paper with no
    questions."""
    doc = pymupdf.open()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8))
    pixmap.clear_with(200)
    for _ in range(3):
        page = doc.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pixmap)
    path = tmp_path / "scan.pdf"
    doc.save(path)
    doc.close()

    out = extract_paper(path)
    assert out.route == "vision"
    assert out.questions == []
    assert not out.ok
    assert "no usable text layer" in out.problems[0]


def test_questions_marks_and_sections_are_read_in_paper_order(tmp_path):
    path = _pdf(tmp_path, [[
        (60, 100, "SECTION A"),
        (60, 130, "1. What is the mean of grouped data?"),
        (MARK_X, 130, "1"),
        (60, 160, "2. Define the modal class."),
        (MARK_X, 160, "2"),
        (60, 200, "SECTION B"),
        (60, 230, "3. Derive the step-deviation formula."),
        (MARK_X, 230, "5"),
    ]])
    out = extract_paper(path)
    assert [(q.section, q.question_no, q.max_marks) for q in out.questions] == [
        ("A", "1", 1.0), ("A", "2", 2.0), ("B", "3", 5.0),
    ]
    assert out.total_marks == 8.0


def test_a_number_outside_the_mark_band_is_not_marks(tmp_path):
    """'(2)' mid-line is an option or a numbered instruction. The band is what separates
    a mark label from a number that merely looks like one."""
    path = _pdf(tmp_path, [[
        (60, 100, "SECTION A"),
        (60, 130, "1. Choose the correct option."),
        (300, 130, "2"),                      # mid-page: not a mark label
        (MARK_X, 160, "4"),                   # in the band: is one
    ]])
    out = extract_paper(path)
    assert [q.max_marks for q in out.questions] == [4.0]


def test_the_second_half_of_an_internal_choice_is_not_another_question(tmp_path):
    """CBSE prints the alternative UNNUMBERED after OR. Treating the next numbered
    question as the alternative made every following question the choice-half of the one
    before it, and a 39-question paper extracted as 46."""
    path = _pdf(tmp_path, [[
        (60, 100, "SECTION A"),
        (60, 130, "28. Explain the process of respiration in yeast."),
        (MARK_X, 130, "3"),
        (60, 160, "OR"),
        (60, 190, "Explain anaerobic respiration in human muscle cells."),
        (60, 230, "29. State one use of ethanol."),
        (MARK_X, 230, "2"),
    ]])
    out = extract_paper(path)
    rows = {(q.question_no, q.choice_alt): q.max_marks for q in out.questions}
    assert rows == {("28", None): 3.0, ("28", "b"): 3.0, ("29", None): 2.0}
    # The alternative inherits its primary's marks -- that is what an internal choice is --
    # and does not double the paper's total.
    assert out.total_marks == 5.0


def test_the_declared_count_is_of_questions_not_of_alternatives(tmp_path):
    path = _pdf(tmp_path, [[
        (60, 80, "This question paper contains 2 questions."),
        (60, 110, "SECTION A"),
        (60, 140, "1. First question of the paper."),
        (MARK_X, 140, "3"),
        (60, 170, "OR"),
        (60, 200, "The alternative to the first question."),
        (60, 240, "2. Second question of the paper."),
        (MARK_X, 240, "3"),
    ]])
    out = extract_paper(path)
    assert out.declared_count == 2
    assert len([q for q in out.questions if q.choice_alt is None]) == 2
    assert not any("declares 2 questions" in p for p in out.problems)


def test_a_gap_in_the_numbering_is_reported(tmp_path):
    """A question the extractor never saw is invisible once stored; a gap is the only
    evidence it existed."""
    path = _pdf(tmp_path, [[
        (60, 100, "SECTION A"),
        (60, 130, "1. The first question of this paper."), (MARK_X, 130, "1"),
        (60, 160, "3. The third question of this paper."), (MARK_X, 160, "1"),
    ]])
    out = extract_paper(path)
    assert any("missing from the paper: [2]" in p for p in out.problems)


def test_a_section_total_that_disagrees_with_the_paper_is_reported(tmp_path):
    path = _pdf(tmp_path, [[
        (60, 80, "Section A : Biology (30 marks)"),
        (60, 110, "SECTION A"),
        (60, 140, "1. Only question in the section."),
        (MARK_X, 140, "1"),
    ]])
    out = extract_paper(path)
    assert out.declared_sections == {"A": 30.0}
    assert any("section A declares 30 marks, 1 were found" in p for p in out.problems)


def test_the_readable_printing_wins_a_bilingual_pair():
    """A ratio was the obvious discriminator and was wrong: the Hindi printing of an MCQ
    extracts as its option markers alone, '(A) (B) (C) (D)', whose only letters are Latin,
    so it scored a perfect 1.0 and beat the English every time."""
    hindi_mcq = "(A) (B) (C) (D)"
    english = "The inner lining of the small intestine has numerous projections called villi."
    assert readable_letters(english) > readable_letters(hindi_mcq)


def test_a_lost_multiplication_sign_is_read_only_when_the_arithmetic_holds():
    """Real papers print '3x1=3' in a font whose glyph does not survive extraction."""
    from app.extraction.mark_grammar import parse_label

    label = parse_label("3 1=3")
    assert label is not None and label.value == 3.0 and label.sub_parts == 3
    assert parse_label("5 2=9") is None      # not marks; two numbers that do not multiply


@pytest.mark.parametrize("heading", ["SECTION A", "Section-B", "section – C"])
def test_section_headings_are_read_in_the_forms_papers_print_them(tmp_path, heading):
    path = _pdf(tmp_path, [[
        (60, 100, heading),
        (60, 130, "1. A question long enough to be kept."),
        (MARK_X, 130, "1"),
    ]])
    out = extract_paper(path)
    assert out.questions[0].section == heading.strip()[-1].upper()
