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


# ----------------------------------------------------------------------------------------
# Sub-parts that carry their own marks
#
# Every case below is from the Class X unit test paper this pilot reads. That paper is
# worth 80 marks and was read as 69: the eleven that went missing were sub-part marks the
# reader never looked for.
# ----------------------------------------------------------------------------------------
def test_sub_parts_with_their_own_marks_become_their_own_questions(tmp_path):
    """A case study is worth 4 marks as 1 + 1 + 2, not 1.

    The reader took the first label it saw, 1, as the mark for the whole question and
    dropped the rest on the floor. Three case studies cost the paper nine marks.
    """
    path = _pdf(tmp_path, [[
        (60, 100, "SECTION E"),
        (60, 130, "36. A dairy packs milk in sealed vessels shaped like a cylinder."),
        (60, 160, "(i) Find the length of the cylindrical portion."),
        (MARK_X, 160, "1"),
        (60, 190, "(ii) Find the curved surface area of the cylinder."),
        (MARK_X, 190, "1"),
        (60, 220, "(iii) Find the total surface area of the vessel."),
        (MARK_X, 220, "2"),
    ]])

    out = extract_paper(path)
    by_address = {q.address: q for q in out.questions}

    assert by_address["E/36/i/"].max_marks == 1
    assert by_address["E/36/ii/"].max_marks == 1
    assert by_address["E/36/iii/"].max_marks == 2
    assert out.total_marks == 4

    # The paragraph above the sub-parts is the stem they share, not a fourth question.
    parent = by_address["E/36//"]
    assert parent.is_context
    assert parent.max_marks is None
    assert "dairy" in parent.stem_text


def test_a_context_stem_is_not_reported_as_a_question_missing_its_marks(tmp_path):
    """Flagging it would train the reader to ignore the warning that matters."""
    path = _pdf(tmp_path, [[
        (60, 100, "SECTION E"),
        (60, 130, "36. A dairy packs milk in sealed vessels shaped like a cylinder."),
        (60, 160, "(i) Find the length of the cylindrical portion."),
        (MARK_X, 160, "1"),
    ]])

    out = extract_paper(path)
    assert not any("no mark label" in p for p in out.problems)


def test_a_sub_part_without_its_own_marks_stays_part_of_its_question(tmp_path):
    """The rule that keeps the split honest.

    Question 24 asks for the probability that a ball is "(i) red (ii) not black" -- one
    2-mark question whose parts are a wrapped sentence. Splitting those would invent two
    questions worth nothing and lose the two marks that are really there.
    """
    path = _pdf(tmp_path, [[
        (60, 100, "SECTION B"),
        (60, 130, "24. A bag contains 5 red balls and 7 black balls. Find the"),
        (MARK_X, 130, "2"),
        (60, 160, "(i) red"),
        (60, 190, "(ii) not black"),
    ]])

    out = extract_paper(path)
    assert [q.address for q in out.questions] == ["B/24//"]
    question = out.questions[0]
    assert question.max_marks == 2
    assert "(i) red" in question.stem_text and "(ii) not black" in question.stem_text
    assert out.total_marks == 2


def test_a_sub_part_can_itself_offer_an_internal_choice(tmp_path):
    """'(iii) (a) ... OR (iii) (b) ...' is one 2-mark sub-part, not two."""
    path = _pdf(tmp_path, [[
        (60, 100, "SECTION E"),
        (60, 130, "36. A dairy packs milk in sealed vessels shaped like a cylinder."),
        (60, 160, "(iii) (a) Find the total surface area of the vessel."),
        (MARK_X, 160, "2"),
        (290, 190, "O R"),
        (60, 220, "(iii) (b) Find the volume of the vessel."),
        (MARK_X, 220, "2"),
    ]])

    out = extract_paper(path)
    by_address = {q.address: q for q in out.questions}
    assert by_address["E/36/iii/a"].max_marks == 2
    assert by_address["E/36/iii/b"].max_marks == 2
    assert out.total_marks == 2


def test_a_letter_spaced_or_is_still_an_or(tmp_path):
    """Papers letter-space the word to set it apart, and it extracts as 'O R'.

    Matching only the unspaced word meant every internal choice in the pilot paper was
    read as more of the question before it: six questions, and both halves in one stem.
    """
    path = _pdf(tmp_path, [[
        (60, 100, "SECTION B"),
        (60, 130, "22. (a) Find the mean of the following distribution."),
        (MARK_X, 130, "2"),
        (290, 160, "O R"),
        (60, 190, "(b) Find the modal class of the distribution."),
    ]])

    out = extract_paper(path)
    by_address = {q.address: q for q in out.questions}
    assert set(by_address) == {"B/22//a", "B/22//b"}
    # An alternative is worth what the question it replaces is worth.
    assert by_address["B/22//b"].max_marks == 2
    # And a student answers one of the two.
    assert out.total_marks == 2


def test_an_a_with_no_b_is_not_a_choice(tmp_path):
    """Reading '(a)' as half a choice is a guess until the other half turns up."""
    path = _pdf(tmp_path, [[
        (60, 100, "SECTION B"),
        (60, 130, "21. (a) Find the mean of the following distribution."),
        (MARK_X, 130, "2"),
        (60, 160, "22. Define the modal class."),
        (MARK_X, 160, "2"),
    ]])

    out = extract_paper(path)
    by_address = {q.address: q for q in out.questions}
    assert set(by_address) == {"B/21//", "B/22//"}
    assert by_address["B/21//"].stem_text.startswith("(a)")
    assert out.total_marks == 4


def test_a_mark_printed_on_the_stems_own_line_is_still_read(tmp_path):
    """Question 23 read as carrying no marks because its label shared the stem's row.

    The label is a separate span in a different font at the right margin; the sentence it
    follows is one span in the body font. That difference is what tells them apart.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 100), "SECTION B", fontsize=10)
    page.insert_text((60, 130), "23. Find the value of the missing frequency f.", fontsize=10)
    page.insert_text((MARK_X, 130), "2", fontsize=10, fontname="hebo")
    path = tmp_path / "same-row.pdf"
    doc.save(path)
    doc.close()

    out = extract_paper(path)
    assert [q.address for q in out.questions] == ["B/23//"]
    assert out.questions[0].max_marks == 2
    assert not out.questions[0].stem_text.endswith("2")


# ----------------------------------------------------------------------------------------
# What the paper says it is worth
# ----------------------------------------------------------------------------------------
def test_the_total_the_paper_declares_is_checked_against_what_was_read(tmp_path):
    """The check that catches a mark nothing else notices.

    Every row that was read looks fine; the paper is simply short. Without this the
    extraction reported no problems at all while eleven marks were missing.
    """
    path = _pdf(tmp_path, [[
        (60, 60, "Maximum Marks: 80"),
        (60, 100, "SECTION A"),
        (60, 130, "1. What is the mean of grouped data?"),
        (MARK_X, 130, "1"),
    ]])

    out = extract_paper(path)
    assert out.declared_total == 80
    assert out.total_marks == 1
    assert any(
        "worth 80 marks and 1 were read" in p and "79 are unaccounted for" in p
        for p in out.problems
    )


def test_a_paper_whose_marks_add_up_reports_no_shortfall(tmp_path):
    path = _pdf(tmp_path, [[
        (60, 60, "Maximum Marks: 3"),
        (60, 100, "SECTION A"),
        (60, 130, "1. What is the mean of grouped data?"),
        (MARK_X, 130, "1"),
        (60, 160, "2. Define the modal class of a distribution."),
        (MARK_X, 160, "2"),
    ]])

    out = extract_paper(path)
    assert out.total_marks == 3
    assert not any("unaccounted for" in p for p in out.problems)


def test_a_section_that_declares_its_marks_per_question_is_checked(tmp_path):
    """'This section comprises 5 questions of 2 marks each' is a self-check worth 10."""
    path = _pdf(tmp_path, [[
        (60, 100, "SECTION B"),
        (60, 115, "This section comprises 5 questions of 2 marks each."),
        (60, 145, "21. Find the mean of the following distribution."),
        (MARK_X, 145, "2"),
    ]])

    out = extract_paper(path)
    assert out.declared_sections["B"] == 10
    assert any("section B declares 10 marks, 2 were found" in p for p in out.problems)


def test_a_question_cannot_carry_marks_and_have_sub_parts_that_do(tmp_path):
    """Either the label belongs to the question or to its parts. Both is a misread, and
    guessing which would silently double or halve the paper."""
    path = _pdf(tmp_path, [[
        (60, 100, "SECTION E"),
        (60, 130, "36. A dairy packs milk in sealed vessels shaped like a cylinder."),
        (MARK_X, 130, "4"),
        (60, 160, "(i) Find the length of the cylindrical portion."),
        (MARK_X, 160, "1"),
    ]])

    out = extract_paper(path)
    assert any("carry marks of their own and also have sub-parts" in p for p in out.problems)


def test_a_running_header_is_not_read_as_the_other_half_of_a_choice(tmp_path):
    """When OR falls at a page break, the footer and the next page's header come between
    it and the alternative. Question 27's alternative was recorded as the school's name."""
    header = (60, 40, "Bharat International Senior Secondary School and Yaadhum")
    footer = (60, 800, "Page of 6")
    path = _pdf(tmp_path, [
        [header, footer, (60, 100, "SECTION C"),
         (60, 130, "27. (a) Find the capacity of the glass."), (MARK_X, 130, "3"),
         (290, 160, "O R")],
        [header, footer, (60, 130, "(b) Find the volume of the iron pole.")],
        [header, footer, (60, 130, "28. Find the mean of the distribution."),
         (MARK_X, 130, "3")],
    ])

    out = extract_paper(path)
    by_address = {q.address: q for q in out.questions}
    assert "volume of the iron pole" in by_address["C/27//b"].stem_text
    assert not any("Bharat" in q.stem_text for q in out.questions)
