"""Reading a sub-question with its passage, sibling agreement, and filling an instruction-only
row from the PDF's own text layer."""

from __future__ import annotations

import pymupdf
import pytest

from app.classify.subparts import FirstLook, sibling_overrides, with_passage
from app.config import Settings
from app.extraction.text_layer_repair import assertion_reason_for, repair_instruction_stems
from app.mapping.subject_scope import SUBJECT_FLAGS, for_subject

# --- with_passage -----------------------------------------------------------------------


def test_a_sub_part_reads_its_passage_first_and_only_once():
    assert with_passage("Name the process.", "A metal M occurs as ore.", "a") == \
        "A metal M occurs as ore.\n\nName the process."
    assert with_passage("A metal M occurs as ore. Name the process.", "A metal M occurs as ore.", "a") \
        == "A metal M occurs as ore. Name the process."


@pytest.mark.parametrize("stem, passage, sub", [
    ("Plain question.", "A passage.", None),       # not a sub-part
    ("Plain question.", None, "a"), ("Plain question.", "  ", "a"),
])
def test_without_a_sub_part_or_a_passage_the_stem_is_unchanged(stem, passage, sub):
    assert with_passage(stem, passage, sub) == stem


# --- sibling agreement ------------------------------------------------------------------


def _look(address, ranked, margin=0.05, agreed=True, group=("B", "28")):
    return FirstLook(address, group, ranked, margin, agreed)


def test_a_weak_outlier_goes_to_the_chapter_its_siblings_agree_on():
    looks = [
        _look("B/28//a", ["METALS", "CHEMRXN"], 0.4),
        _look("B/28//b", ["CHEMRXN", "METALS", "ACIDS"], 0.02, agreed=False),   # the outlier
        _look("B/28//c", ["METALS", "ACIDS"], 0.5),
        _look("B/28//d", ["METALS"], 0.6),
    ]
    assert sibling_overrides(looks) == {"B/28//b": "METALS"}


def test_a_confident_outlier_is_never_moved():
    looks = [_look(f"B/28//{c}", ["METALS"], 0.5) for c in "abc"] + [
        _look("B/28//d", ["CHEMRXN", "METALS"], 0.6, agreed=True)]
    assert sibling_overrides(looks) == {}


def test_a_chapter_nothing_in_the_sub_parts_own_retrieval_supports_is_not_imposed():
    looks = [_look(f"B/28//{c}", ["METALS"], 0.5) for c in "abc"] + [
        _look("B/28//d", ["LIGHT", "EYE", "ELECTRICITY"], 0.01, agreed=False)]
    assert sibling_overrides(looks) == {}, "METALS is nowhere in d's own top three"


def test_no_majority_no_override():
    looks = [
        _look("B/29//a", ["METALS"], 0.5), _look("B/29//b", ["CHEMRXN", "METALS"], 0.01),
        _look("B/29//c", ["CARBON", "METALS"], 0.01), _look("B/29//d", ["ACIDS", "METALS"], 0.01),
    ]
    assert sibling_overrides(looks) == {}, "1 of 4 is not an agreement"


def test_too_few_sub_parts_cannot_outvote_anything():
    looks = [_look("B/28//a", ["METALS"], 0.5), _look("B/28//b", ["CHEMRXN", "METALS"], 0.01)]
    assert sibling_overrides(looks) == {}


def test_a_row_that_is_not_a_sub_part_is_left_alone():
    looks = [FirstLook("A/1//", None, ["LIFEPROC"], 0.01)] * 5
    assert sibling_overrides(looks) == {}


def test_different_questions_are_judged_separately():
    looks = [_look(f"B/28//{c}", ["METALS"], 0.5, group=("B", "28")) for c in "abc"] + [
        _look(f"C/38//{c}", ["LIGHT"], 0.5, group=("C", "38")) for c in "abc"] + [
        _look("C/38//d", ["EYE", "LIGHT"], 0.01, agreed=False, group=("C", "38"))]
    assert sibling_overrides(looks) == {"C/38//d": "LIGHT"}


# --- the flags are per-subject -----------------------------------------------------------


def test_the_new_flags_default_off_and_follow_the_subject_list():
    s = Settings()
    assert s.subpart_retrieval_with_passage is False and s.subpart_chapter_agreement is False
    assert s.science_text_layer_repair is False
    assert "subpart_retrieval_with_passage" in SUBJECT_FLAGS and "subpart_chapter_agreement" in SUBJECT_FLAGS
    on = Settings(subpart_retrieval_with_passage=True, subpart_chapter_agreement=True)
    assert for_subject(on, "X.SCI").subpart_chapter_agreement
    assert for_subject(on, "X.GEO").subpart_retrieval_with_passage
    assert not for_subject(on, "X.MATH").subpart_chapter_agreement
    assert not for_subject(on, "X.ENG.FF").subpart_retrieval_with_passage


def test_the_text_layer_repair_is_science_only():
    from app.classify.science_scope import science_on

    assert "science_text_layer_repair" not in SUBJECT_FLAGS, "Science's own flag, not the shared list"
    on = Settings(science_text_layer_repair=True)
    assert science_on(on, "X.SCI", "science_text_layer_repair")
    for subject in ("X.MATH", "X.SST", "X.GEO", None):
        assert not science_on(on, subject, "science_text_layer_repair")


# --- the text-layer repair ---------------------------------------------------------------


def _pdf_with_page_break() -> bytes:
    """Page 1 ends with an assertion-reason instruction; page 2 opens with the answer codes and
    the statements -- the layout that makes a page-by-page reader return the instruction alone."""
    doc = pymupdf.open()
    one = doc.new_page(width=595, height=842)
    for y, text in [
        (60, "23. The reaction is used to join railway tracks. Aluminium acts as :"),
        (80, "(A) an oxidising agent  (B) a reducing agent"),
        (110, "For Question number 24, two statements are given, one labelled as Assertion (A)"),
        (125, "and the other labelled as Reason (R). Select the correct answer."),
        (800, "Page 4 of 7"),
    ]:
        one.insert_text((50, y), text, fontsize=10)
    two = doc.new_page(width=595, height=842)
    for y, text in [
        (60, "(A) Both Assertion (A) and Reason (R) are true and Reason (R) explains it."),
        (80, "(D) Assertion (A) is false, but Reason (R) is true."),
        (110, "24."),
        (110, "Assertion (A) : Copper articles acquire a green coating in moist air."),
        (125, "Reason (R) : Copper forms basic copper carbonate."),
        (160, "25. Write balanced equations for the reactions that take place when :"),
    ]:
        two.insert_text((50 if y != 110 or text != "24." else 20, y), text, fontsize=10)
    out = doc.tobytes()
    doc.close()
    return out


class _Q:
    def __init__(self, address, number, stem):
        self.address, self.question_no, self.stem_text = address, number, stem


INSTRUCTION = (
    "For Question number 24, two statements are given, one labelled as Assertion (A) and the "
    "other labelled as Reason (R). Select the correct answer to this question."
)


def test_an_instruction_only_row_is_filled_from_the_text_layer():
    rows = [_Q("B/24//", "24", INSTRUCTION)]
    done = repair_instruction_stems(rows, [(_pdf_with_page_break(), "application/pdf", "p.pdf")])
    assert done == ["B/24//"]
    assert rows[0].stem_text.startswith("Assertion (A) : Copper articles")
    assert "Reason (R) : Copper forms basic copper carbonate." in rows[0].stem_text
    assert "Question number 24" not in rows[0].stem_text and "25." not in rows[0].stem_text


def test_a_stem_the_reader_got_is_never_replaced():
    real = "Assertion (A) : The reader read this. Reason (R) : All of it."
    rows = [_Q("B/24//", "24", real), _Q("B/23//", "23", "An ordinary question about aluminium.")]
    assert repair_instruction_stems(rows, [(_pdf_with_page_break(), "application/pdf", "p.pdf")]) == []
    assert rows[0].stem_text == real and rows[1].stem_text.startswith("An ordinary")


def test_a_paper_with_no_text_layer_or_no_pdf_is_left_as_it_was():
    rows = [_Q("B/24//", "24", INSTRUCTION)]
    assert repair_instruction_stems(rows, [(b"\x89PNG not a pdf", "image/png", "p.png")]) == []
    assert repair_instruction_stems(rows, []) == []
    assert rows[0].stem_text == INSTRUCTION


def test_a_question_number_that_is_not_a_plain_number_is_not_looked_up():
    assert assertion_reason_for("8-9", "8. Assertion (A) : x. Reason (R) : y.") is None
    assert assertion_reason_for("", "") is None
    text = "24. Assertion (A) : a. 1 Reason (R) : b.\n25. Next question."
    assert assertion_reason_for("24", text) == "Assertion (A) : a. Reason (R) : b."
