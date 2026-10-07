"""Science-only mapping rules (app.classify.science_scope): a section held to its discipline,
and instruction-only rows not placed by their boilerplate. Every rule acts for X.SCI only."""

from __future__ import annotations

import pytest

from app.classify import science_scope as sci
from app.config import Settings

AR_PREAMBLE = (
    "For Questions number 8 and 9, two statements are given, one labelled as Assertion (A) and "
    "the other labelled as Reason (R). Select the correct answer to these questions from the "
    "codes (A), (B), (C) and (D) as given below. (A) Both Assertion (A) and Reason (R) are true "
    "and Reason (R) is the correct explanation of the Assertion (A). (D) Assertion (A) is false, "
    "but Reason (R) is true."
)


# --- instruction-only rows ---------------------------------------------------------------


@pytest.mark.parametrize("stem", [
    AR_PREAMBLE,
    "For Question number 24, two statements are given, one labelled as Assertion (A) and the "
    "other labelled as Reason (R). Select the correct answer from the codes (A), (B), (C), (D).",
    "Attempt either option (a) or (b) :",
    "Attempt either option (a) or (b).",
    "Read the following passage and answer the questions that follow :",
])
def test_an_instruction_with_nothing_after_it_is_not_a_question(stem):
    assert sci.instruction_only(stem)


@pytest.mark.parametrize("stem", [
    "Assertion (A) : Lymph flows through the same vessels as blood. Reason (R) : Lymph carries fat.",
    "For Question number 9, two statements are given. Assertion (A) : Lymph flows through blood "
    "vessels. Reason (R) : Lymph carries fat. Select the correct answer.",
    "An element X is so soft that it can be cut with a knife and is stored under kerosene.",
    "Read the following passage and answer the questions that follow : A student took four test "
    "tubes P, Q, R and S and placed 1 mL of starch solution in each.",
    "(b) Plants do not possess any specialised excretory organ. State any two ways.",
    "", None,
])
def test_a_real_question_is_never_taken_for_an_instruction(stem):
    assert sci.instruction_only(stem) is None


# --- section discipline ------------------------------------------------------------------


def _paper():
    """The shape of this school's paper: A Biology, B Chemistry, C Physics, with the first
    pass's few wrong guesses (a Carbon and a Chemical Reactions row in A, a Reproduction row
    in C, a Human Eye row in C that is still Physics)."""
    a = ["X.SCI.LIFEPROC"] * 20 + ["X.SCI.CARBON", "X.SCI.CHEMRXN", "X.SCI.REPRO"]
    b = ["X.SCI.METALS"] * 14 + ["X.SCI.CHEMRXN"] * 6 + ["X.SCI.CARBON"]
    c = ["X.SCI.LIGHT"] * 12 + ["X.SCI.EYE", "X.SCI.REPRO"]
    return [("A", x) for x in a] + [("B", x) for x in b] + [("C", x) for x in c]


def test_a_section_that_is_overwhelmingly_one_discipline_is_held_to_it():
    assert sci.section_disciplines(_paper()) == {
        "A": sci.BIOLOGY, "B": sci.CHEMISTRY, "C": sci.PHYSICS}


def test_a_mixed_section_is_left_alone():
    """A board paper's section A is MCQs from every discipline: no discipline, no narrowing."""
    mixed = [("A", c) for c in (["X.SCI.LIFEPROC"] * 6 + ["X.SCI.METALS"] * 6 + ["X.SCI.LIGHT"] * 6)]
    assert sci.section_disciplines(mixed) == {}


def test_a_section_with_too_few_questions_is_left_alone():
    assert sci.section_disciplines([("A", "X.SCI.LIFEPROC")] * 3) == {}


def test_a_printed_title_naming_a_discipline_wins_over_the_vote():
    votes = [("A", "X.SCI.LIFEPROC")] * 10
    assert sci.section_disciplines(votes, {"A": "SECTION A (Chemistry)"}) == {"A": sci.CHEMISTRY}
    assert sci.section_disciplines([], {"B": "Physics", "C": "Section C"}) == {"B": sci.PHYSICS}


LABELS = {code: f"label of {code}" for code in sci.CHAPTER_DISCIPLINE}


def test_question_scopes_hold_each_question_to_its_sections_discipline():
    questions = [(f"q{i}", s, c) for i, (s, c) in enumerate(_paper())]
    scopes, sections = sci.question_scopes(questions, LABELS)
    assert sections == {"A": sci.BIOLOGY, "B": sci.CHEMISTRY, "C": sci.PHYSICS}
    biology = {LABELS[c] for c in sci.chapters_of(sci.BIOLOGY)}
    assert scopes["q20"] == scopes["q22"] == biology, "the Carbon and Reproduction guesses are in range"
    assert "label of X.SCI.CARBON" not in scopes["q0"]
    assert "label of X.SCI.REPRO" in scopes["q0"] and "label of X.SCI.CHEMRXN" not in scopes["q0"]
    physics = {LABELS[c] for c in sci.chapters_of(sci.PHYSICS)}
    assert scopes[f"q{23 + 21 + 13}"] == physics, "a Reproduction guess in Section C can only go to Physics"


def test_a_teachers_paper_scope_is_respected_inside_the_discipline():
    questions = [(f"q{i}", s, c) for i, (s, c) in enumerate(_paper())]
    teacher = {LABELS["X.SCI.LIFEPROC"], LABELS["X.SCI.METALS"], LABELS["X.SCI.LIGHT"]}
    scopes, _ = sci.question_scopes(questions, LABELS, paper_scope=teacher)
    assert scopes["q0"] == {LABELS["X.SCI.LIFEPROC"]}
    # a section whose discipline has no chapter in the teacher's scope is not narrowed at all
    only_biology = {LABELS["X.SCI.LIFEPROC"]}
    scopes, _ = sci.question_scopes(questions, LABELS, paper_scope=only_biology)
    assert "q30" not in scopes


# --- Science only ------------------------------------------------------------------------


@pytest.mark.parametrize("subject", ["X.MATH", "X.SST", "X.HIST", "X.ENG.FF", "X.TAM", None, ""])
def test_no_other_subject_is_ever_touched(subject):
    s = Settings(science_section_scope=True, science_instruction_rows=True)
    assert not sci.science_on(s, subject, "science_section_scope")
    assert not sci.science_on(s, subject, "science_instruction_rows")


def test_a_science_paper_needs_the_flag_as_well():
    assert sci.science_on(Settings(science_section_scope=True), "X.SCI", "science_section_scope")
    assert not sci.science_on(Settings(), "X.SCI", "science_section_scope")
    assert not sci.science_on(Settings(), "X.SCI", "science_instruction_rows")


def test_the_science_flags_default_off_and_are_not_in_the_shared_subject_list():
    from app.mapping.subject_scope import SUBJECT_FLAGS

    s = Settings()
    assert s.science_section_scope is False and s.science_instruction_rows is False
    assert "science_section_scope" not in SUBJECT_FLAGS
    assert "science_instruction_rows" not in SUBJECT_FLAGS


def test_every_science_chapter_has_a_discipline():
    from app.curriculum import CURRICULA

    assert {c.code for c in CURRICULA["X.SCI"].chapters} == set(sci.CHAPTER_DISCIPLINE)


# --- what the map step does with a row ---------------------------------------------------


def test_the_map_step_blocks_a_lone_instruction_and_skips_a_heading_with_options():
    on = Settings(science_instruction_rows=True)
    assert sci.instruction_row_action(on, "X.SCI", AR_PREAMBLE, siblings=1)[0] == sci.BLOCK
    assert sci.instruction_row_action(on, "X.SCI", AR_PREAMBLE, siblings=1)[1]
    assert sci.instruction_row_action(on, "X.SCI", "Attempt either option (a) or (b) :", siblings=3) \
        == (sci.SKIP, None)
    assert sci.instruction_row_action(on, "X.SCI", "A real question about lymph.", siblings=1) is None


@pytest.mark.parametrize("subject", ["X.MATH", "X.SST", "X.GEO", "X.ENG.FF", None])
def test_the_map_step_leaves_every_other_subject_alone(subject):
    on = Settings(science_instruction_rows=True)
    assert sci.instruction_row_action(on, subject, AR_PREAMBLE, siblings=1) is None
    assert sci.instruction_row_action(on, subject, "Attempt either option (a) or (b) :", siblings=3) is None


def test_with_the_flag_off_science_maps_as_before():
    assert sci.instruction_row_action(Settings(), "X.SCI", AR_PREAMBLE, siblings=1) is None
