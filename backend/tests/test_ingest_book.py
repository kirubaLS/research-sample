"""Book extraction, and the checks that stop a bad structure pass reaching the database.

Every failure here is silent in production: a phantom section, a missing one, or the
answer key loaded as practice content all produce confident numbers computed against a
tree nothing contradicts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import pymupdf

from app.ingest.book import (
    ChapterExtract,
    Section,
    chapter_files,
    chapter_number,
    extract_chunks,
    extract_sections,
    parse_toc,
    stem_hash,
    verify_against_toc,
)

BOOK = Path(__file__).resolve().parents[2] / "ncert" / "X" / "maths"
real_book = pytest.mark.skipif(not BOOK.exists(), reason="NCERT PDFs are not in the repo")


# --- the scoping fix, which a real chapter forced -------------------------------------

def test_a_decimal_in_body_text_cannot_pose_as_a_section():
    """Chapter 9 contains '= 28.5 m' then 'Therefore,' -- a chapter-agnostic pattern read
    that as section 28.5 and invented a heading."""
    text = "9.1 Heights and Distances\nthe height is 28.5\nTherefore, the answer\n9.2 Summary\n"
    numbers = [s.number for s in extract_sections(text, chapter=9)]
    assert numbers == ["9.1", "9.2"]


def test_a_running_header_does_not_duplicate_a_section():
    text = "12.2 Volume of Combination of Solids\nbody\n12.2 Volume of Combination of Solids\n"
    assert len(extract_sections(text, chapter=12)) == 1


def test_sections_of_another_chapter_are_ignored():
    text = "8.1 Introduction\n9.1 Heights and Distances\n"
    assert [s.number for s in extract_sections(text, chapter=8)] == ["8.1"]


def test_a_running_header_repeated_verbatim_still_keeps_its_short_title():
    """The 'keep the longest candidate' fix for a heading drawn as several truncated
    copies (see the real Science fixture below) must not change the ordinary running-
    header case: several IDENTICAL short copies of the same title are still just one
    section, at that same short title -- not accidentally "won" by nothing longer."""
    text = "12.2 Volume\nbody\n12.2 Volume\nmore body\n12.2 Volume\n"
    sections = extract_sections(text, chapter=12)
    assert len(sections) == 1
    assert sections[0].title == "Volume"


# --- a real Science chapter, numbered two decimal levels deep --------------------------

SCIENCE_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "regression"
CHEMRXN_PDF = SCIENCE_FIXTURES_DIR / "science_chemical_reactions_and_equations.pdf"
real_chemrxn = pytest.mark.skipif(not CHEMRXN_PDF.exists(), reason="regression fixture not present")
ACIDS_PDF = SCIENCE_FIXTURES_DIR / "science_acids_bases_and_salts.pdf"
real_acids = pytest.mark.skipif(not ACIDS_PDF.exists(), reason="regression fixture not present")
METALS_PDF = SCIENCE_FIXTURES_DIR / "science_metals_and_non_metals.pdf"
real_metals = pytest.mark.skipif(not METALS_PDF.exists(), reason="regression fixture not present")
CARBON_PDF = SCIENCE_FIXTURES_DIR / "science_carbon_and_its_compounds.pdf"
real_carbon = pytest.mark.skipif(not CARBON_PDF.exists(), reason="regression fixture not present")
LIFEPROC_PDF = SCIENCE_FIXTURES_DIR / "science_life_processes.pdf"
real_lifeproc = pytest.mark.skipif(not LIFEPROC_PDF.exists(), reason="regression fixture not present")
CONTROL_PDF = SCIENCE_FIXTURES_DIR / "science_control_and_coordination.pdf"
real_control = pytest.mark.skipif(not CONTROL_PDF.exists(), reason="regression fixture not present")
REPRODUCE_PDF = SCIENCE_FIXTURES_DIR / "science_how_do_organisms_reproduce.pdf"
real_reproduce = pytest.mark.skipif(not REPRODUCE_PDF.exists(), reason="regression fixture not present")
LIGHT_PDF = SCIENCE_FIXTURES_DIR / "science_light_reflection_and_refraction.pdf"
real_light = pytest.mark.skipif(not LIGHT_PDF.exists(), reason="regression fixture not present")
EYE_PDF = SCIENCE_FIXTURES_DIR / "science_human_eye_and_colourful_world.pdf"
real_eye = pytest.mark.skipif(not EYE_PDF.exists(), reason="regression fixture not present")
ELECTRICITY_PDF = SCIENCE_FIXTURES_DIR / "science_electricity.pdf"
real_electricity = pytest.mark.skipif(not ELECTRICITY_PDF.exists(), reason="regression fixture not present")
MAGNETIC_PDF = SCIENCE_FIXTURES_DIR / "science_magnetic_effects_of_electric_current.pdf"
real_magnetic = pytest.mark.skipif(not MAGNETIC_PDF.exists(), reason="regression fixture not present")
ENVIRONMENT_PDF = SCIENCE_FIXTURES_DIR / "science_our_environment.pdf"
real_environment = pytest.mark.skipif(not ENVIRONMENT_PDF.exists(), reason="regression fixture not present")

REALNUM_PDF = SCIENCE_FIXTURES_DIR / "maths_real_numbers.pdf"
real_realnum = pytest.mark.skipif(not REALNUM_PDF.exists(), reason="regression fixture not present")
MATHPOLY_PDF = SCIENCE_FIXTURES_DIR / "maths_polynomials.pdf"
real_mathpoly = pytest.mark.skipif(not MATHPOLY_PDF.exists(), reason="regression fixture not present")
LINEQ_PDF = SCIENCE_FIXTURES_DIR / "maths_pair_linear_equations.pdf"
real_lineq = pytest.mark.skipif(not LINEQ_PDF.exists(), reason="regression fixture not present")
MATHQUAD_PDF = SCIENCE_FIXTURES_DIR / "maths_quadratic_equations.pdf"
real_mathquad = pytest.mark.skipif(not MATHQUAD_PDF.exists(), reason="regression fixture not present")
AP_PDF = SCIENCE_FIXTURES_DIR / "maths_arithmetic_progressions.pdf"
real_ap = pytest.mark.skipif(not AP_PDF.exists(), reason="regression fixture not present")
MATHCIRCLE_PDF = SCIENCE_FIXTURES_DIR / "maths_circles.pdf"
real_mathcircle = pytest.mark.skipif(not MATHCIRCLE_PDF.exists(), reason="regression fixture not present")
FF_LETTERTOGOD_PDF = SCIENCE_FIXTURES_DIR / "english_ff_a_letter_to_god.pdf"
real_ff_lettertogod = pytest.mark.skipif(not FF_LETTERTOGOD_PDF.exists(), reason="regression fixture not present")


@real_chemrxn
def test_a_two_level_decimal_subsection_is_found_not_just_the_top_level():
    """'Chemical Reactions and Equations' is the real chapter that exposed the gap:
    extract_sections used to match only 'chapter.section' ('1.1', '1.2', '1.3'), never
    'chapter.section.subsection' ('1.1.1 Writing a Chemical Equation'), so every one of
    this chapter's 9 real subheadings -- everything the book itself numbers one level
    deeper than its own top-level sections -- was silently missing. 3 sections used to
    come back for a chapter with 12 real numbered headings."""
    from app.ingest.book import read_text

    text = read_text(CHEMRXN_PDF)
    sections = extract_sections(text, chapter=1)
    numbers = [s.number for s in sections]
    assert numbers == [
        "1.1", "1.1.1", "1.1.2", "1.2", "1.2.1", "1.2.2", "1.2.3", "1.2.4", "1.2.5",
        "1.3", "1.3.1", "1.3.2",
    ], numbers
    by_number = {s.number: s.title for s in sections}
    assert by_number["1.1.1"] == "Writing a Chemical Equation"
    assert by_number["1.3.2"] == "Rancidity"


@real_acids
def test_a_heading_drawn_as_several_truncated_copies_keeps_its_longest_copy():
    """'Acids, Bases and Salts' draws its own '2.3.1 Importance of pH in Everyday Life'
    heading as FOUR overlapping, truncated '2.3.1 Impor' copies (a faux-bold rendering
    trick) plus the one real, longer line -- keeping the FIRST copy in the text stream,
    the ordinary running-header convention, used to keep the worst, most truncated one.
    Longest-wins fixes it without changing the ordinary case (see the running-header
    test above)."""
    from app.ingest.book import read_text

    text = read_text(ACIDS_PDF)
    sections = extract_sections(text, chapter=2)
    by_number = {s.number: s.title for s in sections}
    assert by_number["2.3.1"] != "Impor"
    assert by_number["2.3.1"].startswith("Importance of pH")


@real_lineq
def test_a_heading_run_onto_the_same_line_as_its_opening_sentence_is_truncated():
    """'Pair of Linear Equations in Two Variables' renders '3.3.1 Substitution Method'
    and the sentence that follows it on one physical line in the PDF's text layer --
    'Substitution Method : We shall explain the method of substitution by taking' used
    to be kept whole as the title, swallowing the opening sentence because the pattern
    only anchors to end-of-line. NCERT's own ' : ' separator (the same one Theorem and
    Example labels use) is where the real heading actually ends."""
    from app.ingest.book import read_text

    text = read_text(LINEQ_PDF)
    sections = extract_sections(text, chapter=3)
    by_number = {s.number: s.title for s in sections}
    assert by_number["3.3.1"] == "Substitution Method"


@real_ap
def test_a_heading_starting_with_lowercase_mathematical_notation_is_still_found():
    """'Arithmetic Progressions' numbers a real section '5.3 nth Term of an AP' --
    'nth' is standard mathematical notation, not a typo, but the title pattern used to
    require a capital first letter and silently dropped this section entirely, the same
    way Science's 'pH of Salts' did before its own exception was added."""
    from app.ingest.book import read_text

    text = read_text(AP_PDF)
    sections = extract_sections(text, chapter=5)
    by_number = {s.number: s.title for s in sections}
    assert by_number["5.3"] == "nth Term of an AP"


@real_mathcircle
def test_a_bare_exercise_number_split_onto_its_own_line_is_not_a_heading():
    """'Circles' renders 'EXERCISE 10.2' across two physical lines ('EXERCISE' then
    '10.2' alone), leaving a bare '10.2' immediately followed by the exercise's own
    instruction sentence ('In Q.1 to 3, choose the correct option and give
    justification.'). The number/title gap allows crossing one line break to recover a
    genuine two-line heading like this chapter's own '10.4 Summary' -- but that same
    allowance used to read the exercise number and its instruction sentence as a
    heading too, and since the sentence is longer than the real '10.2 Tangent to a
    Circle' heading elsewhere in the chapter, the longest-wins dedup kept the fake one
    and the real upload was rejected outright: 'section 10.2 reads 'In Q.1 to 3, choose
    the correct option and give justification.', contents page says 'Tangent to a
    Circle''."""
    from app.ingest.book import read_text

    text = read_text(MATHCIRCLE_PDF)
    sections = extract_sections(text, chapter=10)
    by_number = {s.number: s.title for s in sections}
    assert by_number["10.2"] == "Tangent to a Circle"
    assert by_number["10.4"] == "Summary"


@real_acids
def test_a_heading_starting_with_the_chemistry_symbol_ph_is_not_excluded():
    """'2.4.2 pH of Salts' is a real heading that correctly starts with a lowercase 'p'
    -- 'pH' is the actual chemistry notation, not a typo -- which the usual
    capital-letter-first rule would otherwise silently exclude."""
    from app.ingest.book import read_text

    text = read_text(ACIDS_PDF)
    sections = extract_sections(text, chapter=2)
    by_number = {s.number: s.title for s in sections}
    assert by_number["2.4.2"] == "pH of Salts"


@real_acids
def test_a_heading_printed_out_of_numeric_order_is_still_correctly_bounded():
    """This chapter's own two-column layout prints '2.1.5's real text ahead of 2.1.4's
    in the plain-text extraction -- verify_against_toc compares by NUMBER, never by
    order, so both sections must still come back complete and correctly bounded despite
    the reversed physical order."""
    from app.ingest.book import read_text

    text = read_text(ACIDS_PDF)
    sections = extract_sections(text, chapter=2)
    by_number = {s.number: s for s in sections}
    assert by_number["2.1.4"].title == "How do Acids and Bases React with each other?"
    assert by_number["2.1.5"].title == "Reaction of Metallic Oxides with Acids"
    starts = [s.start for s in sections]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)


@real_metals
def test_metals_and_non_metals_finds_every_two_level_subsection():
    from app.ingest.book import read_text

    text = read_text(METALS_PDF)
    sections = extract_sections(text, chapter=3)
    assert len(sections) == 20, [s.number for s in sections]


@real_carbon
def test_carbon_and_its_compounds_finds_every_two_level_subsection():
    from app.ingest.book import read_text

    text = read_text(CARBON_PDF)
    sections = extract_sections(text, chapter=4)
    assert len(sections) == 16, [s.number for s in sections]


@real_lifeproc
def test_life_processes_finds_every_two_level_subsection():
    from app.ingest.book import read_text

    text = read_text(LIFEPROC_PDF)
    sections = extract_sections(text, chapter=5)
    assert len(sections) == 13, [s.number for s in sections]


@real_control
def test_control_and_coordination_finds_every_two_level_subsection():
    from app.ingest.book import read_text

    text = read_text(CONTROL_PDF)
    sections = extract_sections(text, chapter=6)
    assert len(sections) == 9, [s.number for s in sections]


@real_reproduce
def test_a_third_level_lettered_subsection_is_found_not_just_the_decimal_levels():
    """'How do Organisms Reproduce?' is the real chapter that exposed a THIRD numbering
    convention: a level under a two-decimal section switches from another digit to a
    parenthesised letter instead ('7.3.3 (a) Male Reproductive System', through '(d)
    Reproductive Health', all four under '7.3.3 Reproduction in Human Beings') -- 13
    sections used to come back for a chapter with 17 real numbered headings."""
    from app.ingest.book import read_text

    text = read_text(REPRODUCE_PDF)
    sections = extract_sections(text, chapter=7)
    numbers = [s.number for s in sections]
    assert numbers[-4:] == ["7.3.3 (a)", "7.3.3 (b)", "7.3.3 (c)", "7.3.3 (d)"], numbers
    by_number = {s.number: s.title for s in sections}
    assert by_number["7.3.3 (a)"] == "Male Reproductive System"
    assert by_number["7.3.3 (d)"] == "Reproductive Health"
    assert len(sections) == 17, numbers


@real_light
def test_light_reflection_and_refraction_finds_every_two_level_subsection():
    from app.ingest.book import read_text

    text = read_text(LIGHT_PDF)
    sections = extract_sections(text, chapter=9)
    assert len(sections) == 15, [s.number for s in sections]


@real_eye
def test_human_eye_and_colourful_world_finds_every_two_level_subsection():
    from app.ingest.book import read_text

    text = read_text(EYE_PDF)
    sections = extract_sections(text, chapter=10)
    assert len(sections) == 9, [s.number for s in sections]


@real_electricity
def test_electricity_finds_every_two_level_subsection():
    from app.ingest.book import read_text

    text = read_text(ELECTRICITY_PDF)
    sections = extract_sections(text, chapter=11)
    assert len(sections) == 11, [s.number for s in sections]


@real_magnetic
def test_magnetic_effects_of_electric_current_finds_every_two_level_subsection():
    from app.ingest.book import read_text

    text = read_text(MAGNETIC_PDF)
    sections = extract_sections(text, chapter=12)
    assert len(sections) == 8, [s.number for s in sections]


@real_environment
def test_our_environment_finds_every_two_level_subsection():
    from app.ingest.book import read_text

    text = read_text(ENVIRONMENT_PDF)
    sections = extract_sections(text, chapter=13)
    assert len(sections) == 5, [s.number for s in sections]


@real_acids
def test_a_heading_faked_bold_as_several_overlapping_offset_copies_is_not_truncated():
    """'2.3.1 Importance of pH in Everyday Life' is drawn as several overlapping,
    differently-truncated copies -- the longest single copy alone used to read as
    'Importance of pH in Ever', silently dropping 'yday Life'. Passing the real PDF's own
    path lets extract_sections read the copies' font size and recognise the ones that
    genuinely continue the heading (same size as its own first line) from this chapter's
    unrelated body text (a different, smaller size), and merge them in."""
    from app.ingest.book import read_text

    text = read_text(ACIDS_PDF)
    sections = extract_sections(text, chapter=2, path=ACIDS_PDF)
    by_number = {s.number: s.title for s in sections}
    assert by_number["2.3.1"] == "Importance of pH in Everyday Life"


@real_acids
def test_a_heading_that_is_a_question_wrapped_onto_a_second_line_is_not_truncated():
    """'2.1.3 How do Metal Carbonates and Metal Hydrogencarbonates React with Acids?'
    wraps onto a second physical line with no overlap or duplication at all -- a plain
    word wrap, unlike the pH heading above. Confirmed this does not depend on the
    heading happening to end mid-question: the merge stops itself at the '?' either way,
    rather than continuing on to swallow the unrelated 'Activity 2.5' caption below it."""
    from app.ingest.book import read_text

    text = read_text(ACIDS_PDF)
    sections = extract_sections(text, chapter=2, path=ACIDS_PDF)
    by_number = {s.number: s.title for s in sections}
    assert (
        by_number["2.1.3"]
        == "How do Metal Carbonates and Metal Hydrogencarbonates React with Acids?"
    )


@real_metals
def test_a_heading_wrapped_onto_a_second_line_with_no_path_is_left_truncated():
    """Without a path to read font sizes from (the synthetic-text unit tests below, and
    any caller that only has the text, not the file), extract_sections cannot tell a
    wrapped heading from ordinary body text -- so it must not guess, and the heading
    comes back exactly as its single matched line reads, same as before this fix."""
    from app.ingest.book import read_text

    text = read_text(METALS_PDF)
    sections = extract_sections(text, chapter=3)  # no path=
    by_number = {s.number: s.title for s in sections}
    assert by_number["3.4.5"] == "Extracting Metals towards the Top of the"


@real_metals
def test_a_heading_wrapped_onto_a_second_line_with_no_overlap_is_not_truncated():
    """'3.4.5 Extracting Metals towards the Top of the' / 'Activity Series' is a plain
    two-line word wrap with no faux-bold duplication at all -- the font-size match is
    still what lets the second line be told apart from the body prose ('The metals high
    up...') immediately below it, which is set at a visibly smaller size."""
    from app.ingest.book import read_text

    text = read_text(METALS_PDF)
    sections = extract_sections(text, chapter=3, path=METALS_PDF)
    by_number = {s.number: s.title for s in sections}
    assert by_number["3.4.5"] == "Extracting Metals towards the Top of the Activity Series"


@real_light
def test_a_heading_whose_own_number_wraps_separately_from_its_wrapped_title_is_not_truncated():
    """'9.2.2' and its title sit on two different physical lines already (the number/title
    line-split extract_sections' own pattern already tolerates), and the title ITSELF
    then wraps onto a further third line ('Representation of Images Formed by Spherical'
    / 'Mirrors Using Ray Diagrams') -- confirmed this does not confuse the font-size
    lookup, which must use the title's own last physical line, not the whole matched
    span with its embedded newline before the title, as the key."""
    from app.ingest.book import read_text

    text = read_text(LIGHT_PDF)
    sections = extract_sections(text, chapter=9, path=LIGHT_PDF)
    by_number = {s.number: s.title for s in sections}
    assert (
        by_number["9.2.2"]
        == "Representation of Images Formed by Spherical Mirrors Using Ray Diagrams"
    )


@real_reproduce
def test_a_heading_followed_by_narrow_column_body_prose_is_not_swallowed():
    """An earlier, text-only version of this merge (short next line, no terminal
    punctuation) broke on this real chapter: 'Budding' sits next to a figure, so its own
    body prose wraps into five short, punctuation-free lines ('Organisms such as Hydra' /
    'use regenerative cells for' / ...) that read exactly like a plausible heading
    continuation as plain text. They are not bold or larger, though -- confirmed the
    font-size gate correctly leaves 'Budding' alone rather than absorbing them."""
    from app.ingest.book import read_text

    text = read_text(REPRODUCE_PDF)
    sections = extract_sections(text, chapter=7, path=REPRODUCE_PDF)
    by_number = {s.number: s.title for s in sections}
    assert by_number["7.2.4"] == "Budding"


# --- buckets --------------------------------------------------------------------------

def test_theorems_and_examples_are_taught_content_exercises_are_practice():
    text = (
        "1.1 Introduction\n"
        "Theorem 1.3 : Root 2 is irrational\nproof body\n"
        "Example 4 : Find the HCF\nworked body\n"
        "EXERCISE 1.2\n1. Prove that...\n"
    )
    chunks = {c.kind: c for c in extract_chunks(text, 1)}
    assert chunks["theorem"].bucket == "T"
    assert chunks["example"].bucket == "T"
    assert chunks["exercise"].bucket == "E"


def test_an_example_written_without_a_space_before_the_colon_still_matches():
    """NCERT writes both 'Example 3 :' and 'Example 3:'."""
    chunks = extract_chunks("1.1 Intro\nExample 3: Find the HCF\nbody\n", 1)
    assert [c.kind for c in chunks].count("example") == 1


def test_an_optional_exercise_is_captured_but_marked_non_examinable():
    """'EXERCISE 5.4 (Optional)*' was dropped entirely by an end-of-line anchor."""
    text = "5.1 Intro\nEXERCISE 5.4 (Optional)*\n1. Which term...\n"
    chunks = [c for c in extract_chunks(text, 5) if c.kind == "exercise"]
    assert len(chunks) == 1
    assert chunks[0].examinable is False


def test_stem_hash_folds_layout_but_not_numbers():
    assert stem_hash("Find the  HCF of 96") == stem_hash("Find the HCF of 96 ")
    assert stem_hash("radius 3.5 cm") != stem_hash("radius 7 cm")


# --- verification against the book's own contents page --------------------------------

def _extract(number: int, sections: list[tuple[str, str]]) -> ChapterExtract:
    return ChapterExtract(
        number=number, title="T", source_path="x.pdf", sha256="0",
        sections=[Section(n, t) for n, t in sections],
        chunks=extract_chunks("1.1 Intro\nExample 1 : x\nbody\n", 1),
    )


def test_a_missing_section_fails_verification():
    toc = {1: [Section("1.1", "Introduction"), Section("1.2", "The Fundamental Theorem")]}
    result = verify_against_toc(_extract(1, [("1.1", "Introduction")]), toc)
    assert not result.ok
    assert "missing section 1.2" in result.problems[0]


def test_an_invented_section_fails_verification():
    toc = {1: [Section("1.1", "Introduction")]}
    result = verify_against_toc(
        _extract(1, [("1.1", "Introduction"), ("1.9", "Nonsense")]), toc
    )
    assert not result.ok
    assert "not in the contents page" in result.problems[0]


def test_a_retitled_section_fails_verification():
    """Catches the book edition moving underneath a stored curriculum_section."""
    toc = {1: [Section("1.1", "Introduction")]}
    result = verify_against_toc(_extract(1, [("1.1", "Something Else")]), toc)
    assert not result.ok


def test_a_chapter_with_no_content_fails_rather_than_loading_empty():
    toc = {1: [Section("1.1", "Introduction")]}
    e = ChapterExtract(1, "T", "x.pdf", "0", [Section("1.1", "Introduction")], [])
    assert not verify_against_toc(e, toc).ok


def test_a_correct_extraction_passes():
    toc = {1: [Section("1.1", "Introduction")]}
    assert verify_against_toc(_extract(1, [("1.1", "Introduction")]), toc).ok


# --- filenames ------------------------------------------------------------------------

def test_both_naming_conventions_are_accepted():
    """Renaming eighteen files before an upload is a requirement with nothing behind it:
    jemh101 already says 'chapter 1' unambiguously."""
    assert chapter_number("12-surface-areas-and-volumes.pdf") == 12
    assert chapter_number("jemh101.pdf") == 1
    assert chapter_number("jemh114.pdf") == 14
    # the pattern is not Maths-specific -- Science is jesc1NN
    assert chapter_number("jesc105.pdf") == 5


def test_the_non_chapter_files_are_not_chapters_under_either_convention():
    """The answers file matches EXERCISE 31 times; loaded, it would make the answer key
    'practice content'."""
    for name in ("an-answers.pdf", "jemh1an.pdf",
                 "a1-proofs-in-mathematics.pdf", "jemh1a1.pdf", "jemh1a2.pdf"):
        assert chapter_number(name) is None, name


def test_the_contents_page_is_recognised_under_either_convention():
    from app.ingest.book import is_contents

    assert is_contents("00-contents.pdf")
    assert is_contents("jemh1ps.pdf")
    assert not is_contents("jemh101.pdf")
    assert not is_contents("jemh1an.pdf")
    # 00-contents is numbered 0, which is not a loadable chapter
    assert chapter_number("00-contents.pdf") == 0


def test_a_chapter_title_comes_from_the_curriculum_when_the_filename_has_none():
    """An NCERT code carries a number and no title, and the title on the page is a running
    header six of fourteen chapters do not show before their first section."""
    from app.curriculum import chapter_title

    assert chapter_title("X.MATH", 12) == "Surface Areas and Volumes"
    assert chapter_title("X.MATH", 9) == "Applications of Trigonometry"
    assert chapter_title("X.MATH", 99) is None
    assert chapter_title("X.NOSUCH", 1) is None


# --- against the real book, when it is present ----------------------------------------

@real_book
def test_the_whole_maths_book_agrees_with_its_own_contents_page():
    from app.ingest.book import extract_chapter, parse_toc

    toc = parse_toc(BOOK / "00-contents.pdf")
    assert len(toc) == 14

    files = sorted(p for p in chapter_files(BOOK) if p.name != "00-contents.pdf")
    assert len(files) == 14

    for path in files:
        result = verify_against_toc(extract_chapter(path), toc)
        assert result.ok, f"{path.name}: {result.problems}"


@real_book
def test_theorems_appear_only_in_the_chapters_that_prove_things():
    from app.ingest.book import extract_chapter

    with_theorems = {
        extract_chapter(p).number
        for p in chapter_files(BOOK)
        if any(c.kind == "theorem" for c in extract_chapter(p).chunks)
    }
    # Real Numbers, Triangles, Circles
    assert with_theorems == {1, 6, 10}


def test_chunks_do_not_swallow_each_other():
    """Slicing each marker kind separately made Theorem 1.1 run to Theorem 1.2 and absorb
    every Example in between -- 6043 characters of overlapping content in one chunk."""
    text = (
        "1.1 Introduction\n"
        "Theorem 1.1 : first\nproof\n"
        "Example 1 : a worked one\nsolution\n"
        "Example 2 : another\nsolution\n"
        "Theorem 1.2 : second\nproof\n"
    )
    chunks = [c for c in extract_chunks(text, 1) if c.kind != "body"]
    assert [c.reference for c in chunks] == [
        "Theorem 1.1", "Example 1", "Example 2", "Theorem 1.2",
    ], "chunks must come out in document order"
    assert "Example 1" not in chunks[0].text
    assert "Theorem 1.2" not in chunks[2].text


@real_book
def test_no_real_chunk_swallows_another():
    """The precise invariant.

    Not "chunk A never names chunk B": NCERT writes "An equivalent version of Theorem 1.2
    was probably first recorded as Proposition 14 of Book IX", which is prose, not
    overlap. Containing another chunk's whole text is overlap by definition.
    """
    from app.ingest.book import extract_chapter

    for path in chapter_files(BOOK):
        chunks = extract_chapter(path).chunks
        for i, chunk in enumerate(chunks):
            for other in chunks[i + 1:]:
                assert other.text not in chunk.text, (
                    f"{path.name}: {chunk.reference} swallows {other.reference}"
                )


@real_book
def test_almost_none_of_the_book_is_dropped():
    """Marker-only chunking captured 72%, and the missing 28% was the expository body --
    definitions and derivations that carry no label. A question drawn from that text found
    no match and was judged NOVEL when it was T_VERBATIM."""
    from app.ingest.book import extract_chapter, read_text

    for path in chapter_files(BOOK):
        total = len(read_text(path))
        captured = sum(len(c.text) for c in extract_chapter(path).chunks)
        share = captured / total
        assert share > 0.95, f"{path.name} captures only {share:.0%} of its text"


@real_book
def test_every_section_of_every_chapter_produces_content():
    """A section with no chunk is a hole in the tree that nothing downstream reveals."""
    from app.ingest.book import extract_chapter

    for path in chapter_files(BOOK):
        extract = extract_chapter(path)
        covered = {c.section for c in extract.chunks}
        for section in extract.sections:
            # 'Summary' sections are a bulleted recap and can fall under the body minimum
            if section.title.strip().lower() == "summary":
                continue
            assert section.number in covered, (
                f"{path.name}: section {section.number} {section.title!r} produced nothing"
            )


# --- retrieval, against real exam questions -------------------------------------------

PROBE = BOOK / "probe-30B.json"


class _Indexed:
    """The minimum LexicalIndex reads: text to score, and an id to report."""

    def __init__(self, text: str, reference: str, chapter: int):
        self.id = reference
        self.text = text
        self.reference = reference
        self.node_id = chapter
        self.bucket = "T"


real_probe = pytest.mark.skipif(
    not PROBE.exists(), reason="the 30(B) probe set lives beside the gitignored book"
)


@real_probe
def test_real_exam_questions_mostly_resolve_to_the_right_chapter():
    """A knowledge base that loads cleanly and cannot place a real question has failed at
    the only thing it exists for, and the ingest summary says nothing about it.

    Built from the PDFs rather than the database so this measures retrieval quality, not
    whether a particular database happens to be loaded.

    Lexical retrieval is deliberately the weakest plausible retriever, so 7/10 is a floor,
    not a target -- two of these questions genuinely need more than word overlap.
    """
    import json

    from app.ingest.book import extract_chapter
    from app.ingest.probe import LexicalIndex

    chunks = []
    chapter_of: dict[int, str] = {}
    for path in chapter_files(BOOK):
        extract = extract_chapter(path)
        chapter_of[extract.number] = extract.title
        for chunk in extract.chunks:
            chunks.append(_Indexed(chunk.text, chunk.reference, extract.number))

    index = LexicalIndex(chunks)
    probes = json.loads(PROBE.read_text())
    hits = 0
    misses = []
    for probe in probes:
        best = index.search(probe["stem"])
        got = chapter_of.get(best[0].node_id, "?") if best else "?"
        if got.lower() == probe["chapter"].lower():
            hits += 1
        else:
            misses.append(f"Q{probe['q']} expected {probe['chapter']!r}, got {got!r}")

    assert hits >= 7, f"only {hits}/{len(probes)} resolved: " + "; ".join(misses)


def test_stopwords_do_not_let_a_short_stem_match_anything():
    """An exam stem is short, so without stopword removal 'the/of/is' dominates the score
    and every question retrieves the longest chunk in the book."""
    from app.ingest.probe import tokens

    assert tokens("The value of the area of a circle is") == ["area", "circle"]


def test_a_tamil_or_hindi_question_tokenizes_instead_of_scoring_zero_everywhere():
    """The bug this fixes: tokens() used to be a plain [a-z]+ regex, so any non-Latin
    script -- an entire Tamil or Hindi paper, not just one hard question -- tokenized to
    nothing and scored 0 against every chunk in the index. Not a bad match: no match was
    ever attempted, so 'no chapter in the book matched this question' fired on every row
    regardless of how obviously a person would have placed it. Unicode's letter (L) and
    mark (M) categories cover any script without a per-language table -- mark matters on
    its own: Tamil (and Hindi) build a syllable from a base consonant plus a combining
    vowel sign, and a plain \\w (word-char) test excludes those marks, which would still
    shred a Tamil word into meaningless single-consonant fragments with nothing in
    common with the same word appearing elsewhere."""
    from app.ingest.probe import tokens

    assert tokens("கிழக்கிலிருந்து வீசும் காற்றின் பெயர் என்ன?") == [
        "கிழக்கிலிருந்து", "வீசும்", "காற்றின்", "பெயர்", "என்ன",
    ]


def test_capitalized_english_still_tokenizes_fully():
    """A second, smaller bug the same regex carried: [a-z]+ is case-sensitive, so a
    capitalized word like a chapter title's 'Light' only ever matched 'ight' -- the
    fix's casefold() step covers this too, not only the non-Latin case."""
    from app.ingest.probe import tokens

    assert tokens("Light Reflection and Refraction") == ["light", "reflection", "refraction"]


def test_science_activities_are_taught_content():
    """Science teaches through Activities where Maths teaches through Theorems: a labelled,
    numbered procedure a student has performed is taught content by any reading, so a
    question using it is not novel."""
    text = (
        "1.1 Chemical Equations\n"
        "Body text about reactions and equations here.\n"
        "Activity 1.1\n"
        "Take a magnesium ribbon and clean it with sandpaper.\n"
        "Activity 1.2\n"
        "Take lead nitrate solution in a test tube.\n"
        "EXERCISE 1.1\n"
        "1. Balance the following equations.\n"
    )
    chunks = {c.reference: c for c in extract_chunks(text, 1)}
    assert chunks["Activity 1.1"].bucket == "T"
    assert chunks["Activity 1.2"].kind == "activity"
    assert chunks["EXERCISE 1.1"].bucket == "E"
    # each activity stops at the next marker rather than swallowing it
    assert "Activity 1.2" not in chunks["Activity 1.1"].text


@real_book
def test_the_activity_pattern_does_not_disturb_the_maths_book():
    """A pattern added for one subject must not change another. Maths has no Activities,
    and its chunk count is the check."""
    from app.ingest.book import extract_chapter

    total = sum(len(extract_chapter(p).chunks) for p in chapter_files(BOOK))
    assert total == 213
    assert not any(
        c.kind == "activity"
        for p in chapter_files(BOOK)
        for c in extract_chapter(p).chunks
    )


# --- Science: a book that is typeset differently -------------------------------------------

def test_a_heading_set_one_character_per_line_is_rejoined():
    """Science sets EXERCISES and QUESTIONS vertically, so the text layer holds
    'E\\nX\\nE\\nR\\nC\\nI\\nS\\nE\\nS'. Every exercise pattern missed it, which left the drilled
    bucket empty for the whole subject with nothing saying so."""
    from app.ingest.book import _collapse_vertical

    lines = ["some prose", *"EXERCISES", "1.", "Which of the statements"]
    assert _collapse_vertical(lines)[:2] == ["some prose", "EXERCISES"]

    # A run of the same character is a bullet list, not a word, and is left alone.
    bullets = ["n", "n", "n", "n", "n", "n"]
    assert _collapse_vertical(bullets) == bullets


def test_a_fake_bold_heading_is_rebuilt_from_its_overlapping_draws():
    """Verbatim from jesc112.pdf: the heading is drawn five times and split mid-word, with
    a single bridge line spanning each pair of fragments."""
    from app.ingest.book import _collapse_bold

    lines = [
        *["12.2"] * 5,
        "12.2 MA", *["MA"] * 3,
        "MAGNETIC FIELD DUE TO A CURRENT", *["GNETIC FIELD DUE TO A CURRENT"] * 3,
        "GNETIC FIELD DUE TO A CURRENT-CARRYING", *["ARRYING"] * 4,
        *["CONDUCTOR"] * 5,
        "A compass needle is a small magnet.",
    ]
    out = _collapse_bold(lines)
    assert "12.2 MAGNETIC FIELD DUE TO A CURRENT-CARRYING CONDUCTOR" in out
    assert "A compass needle is a small magnet." in out


def test_a_one_character_overlap_does_not_swallow_the_paragraph_below():
    """'AFFECT THE' followed by 'ENVIRONMENT?' share a T, and merging on it produced
    'AFFECT THENVIRONMENT?'. Only a bridge line -- drawn once -- may join mid-word."""
    from app.ingest.book import _collapse_bold

    lines = [
        *["13.2"] * 5,
        *["HOW DO OUR ACTIVITIES AFFECT THE"] * 5,
        *["ENVIRONMENT?"] * 5,
        "We are an integral part of the environment.",
    ]
    out = _collapse_bold(lines)
    assert "13.2 HOW DO OUR ACTIVITIES AFFECT THE ENVIRONMENT?" in out
    assert "We are an integral part of the environment." in out


def test_two_bold_labels_side_by_side_are_not_glued_together():
    """'Activity 1.2' and 'Figure 1.2' are drawn next to each other, five times each. Both
    are complete labels; joining adjacent bold fragments unconditionally merged them."""
    from app.ingest.book import _collapse_bold

    out = _collapse_bold([*["Activity 1.2"] * 5, *["Figure 1.2"] * 5])
    assert out == ["Activity 1.2", "Figure 1.2"]


def test_structural_verification_reports_a_gap_in_the_numbering():
    """Science publishes no section list, so this is the strongest check available: a
    missing 9.3 shows up as a gap between 9.2 and 9.4."""
    from app.ingest.book import ChapterExtract, Chunk, Section, verify_structure

    extract = ChapterExtract(
        number=9, title="Light", source_path="x", sha256="y",
        sections=[Section("9.1", "A"), Section("9.2", "B"), Section("9.4", "D")],
        chunks=[Chunk("E", "exercise", "Exercises 9.1", "text", "h", section="9.4")],
    )
    verify_structure(extract)
    assert extract.problems == ["chapter 9: missing section 9.3"]
    assert not extract.ok


def test_structural_verification_refuses_a_chapter_with_no_drilled_content():
    """No exercises means no question from the chapter could ever be judged PRACTISED --
    a hole in the knowledge base that is invisible once loaded."""
    from app.ingest.book import ChapterExtract, Chunk, Section, verify_structure

    extract = ChapterExtract(
        number=8, title="Heredity", source_path="x", sha256="y",
        sections=[Section("8.1", "A"), Section("8.2", "B")],
        chunks=[Chunk("T", "body", "Section 8.1", "text", "h", section="8.1")],
    )
    verify_structure(extract)
    assert extract.problems == [
        "chapter 8: no exercises or questions were found, so no question from it could "
        "ever be judged PRACTISED"
    ]


def test_structural_verification_cannot_see_a_missing_last_section():
    """Stated as a test so the limit is not mistaken for a guarantee: with no published
    section count, a chapter truncated at the end verifies clean."""
    from app.ingest.book import ChapterExtract, Chunk, Section, verify_structure

    extract = ChapterExtract(
        number=11, title="Electricity", source_path="x", sha256="y",
        sections=[Section("11.1", "A"), Section("11.2", "B")],   # the book has eight
        chunks=[Chunk("E", "exercise", "Exercises 11.1", "t", "h", section="11.2")],
    )
    assert verify_structure(extract).ok


def test_a_lone_section_spanning_a_long_chapter_is_flagged_as_suspicious():
    """The exact shape of a real, silent extraction failure: a decorative element (a
    front-matter note, a cover title) beats every real heading on size alone and
    _sections_by_boldness returns it as the chapter's ONLY section. A missing-exercises
    problem alone would not have caught this -- the fake section's own text can still
    contain a real EXERCISE marker if it swallowed the whole chapter, front matter and
    all, exactly as it did for the real Economics chapter this was measured against
    (thousands of characters, one section, named after a note to the teacher)."""
    from app.ingest.book import ChapterExtract, Chunk, Section, verify_structure

    extract = ChapterExtract(
        number=1, title="Development", source_path="x", sha256="y",
        sections=[Section("1", "NOTES FOR TEACHERS", 0, 5000)],
        chunks=[Chunk("E", "exercise", "Exercises", "t", "h", section="1")],
    )
    verify_structure(extract)
    assert any("only one section was found" in w for w in extract.warnings)
    # A warning, not a rejection -- a genuinely single-section chapter (English, Hindi,
    # Tamil) must still load; exercises_required=False is what actually exempts those.
    assert extract.ok


def test_a_short_genuinely_single_section_chapter_is_not_flagged():
    from app.ingest.book import ChapterExtract, Chunk, Section, verify_structure

    extract = ChapterExtract(
        number=2, title="A Short Poem", source_path="x", sha256="y",
        sections=[Section("1", "A Short Poem", 0, 500)],
        chunks=[Chunk("E", "exercise", "Exercises", "t", "h", section="1")],
    )
    verify_structure(extract)
    assert extract.warnings == []


@real_ff_lettertogod
def test_a_real_single_section_english_chapter_chunks_at_its_real_checkpoints():
    """'A Letter to God' (First Flight) has no numbered sections at all -- the real
    checkpoint the book uses instead is 'Oral Comprehension Check', repeated after each
    block of questions. Confirms the real file extracts clean (no problems) under the
    same single_section=True path production uses for every X.ENG* book."""
    from app.ingest.book import extract_chapter

    extract = extract_chapter(
        FF_LETTERTOGOD_PDF, number=1, name="jeff101.pdf", title="A Letter to God",
        single_section=True,
    )
    assert extract.problems == []
    assert len(extract.chunks) > 1
    assert all(c.section == "1" for c in extract.chunks)
    assert any(c.text.strip() == "Oral Comprehension Check" for c in extract.chunks)


def test_the_science_contents_page_yields_chapters_where_it_yields_no_sections():
    from app.ingest.book import TOC_CHAPTER

    page = (
        "CONTENTS\nForeword\niii\n"
        "Chapter 1\nChemical Reactions and Equations\n1\n"
        "Chapter 9\nLight – Reflection and Refraction\n134\n"
        "Chapter 13\nOur Environment\n208\n"
    )
    found = {int(n): t for n, t in TOC_CHAPTER.findall(page)}
    assert found == {
        1: "Chemical Reactions and Equations",
        9: "Light – Reflection and Refraction",
        13: "Our Environment",
    }


def test_a_dash_spelling_does_not_reject_a_correct_chapter():
    """NCERT prints 'Light – Reflection and Refraction' with an en dash. Comparing it
    against a '--' spelling character by character rejected chapter 9 outright."""
    from app.ingest.book import title_key

    assert title_key("Light – Reflection and Refraction") == title_key(
        "Light -- Reflection and Refraction"
    )
    assert title_key("Light — Reflection and Refraction") == title_key(
        "Light - Reflection and Refraction"
    )
    # Not a blanket fold: different chapters stay different.
    assert title_key("Heredity") != title_key("Electricity")


def test_a_curly_apostrophe_does_not_reject_a_correct_chapter():
    """jefp102.pdf's contents page reads 'The Thief’s Story' with a curly apostrophe; the
    curriculum was typed with a plain one and the two were rejected as different chapters
    even though they name the same story."""
    from app.ingest.book import title_key

    assert title_key("The Thief’s Story") == title_key("The Thief's Story")


def test_a_price_on_the_copyright_page_is_never_read_as_a_chapter_section(tmp_path):
    """jewe2ps.pdf's copyright page prints a price, ' 120.00', alone on its own line,
    immediately followed on the next line by 'Printed on 80 GSM paper with NCERT'.
    '\\s+' between the number and the title in parse_toc's own pattern matches straight
    across that newline, so the price and the line below it were read as chapter 120,
    section 120.00 -- a single spurious entry that made `expected_sections` non-empty and
    every real chapter fail with 'chapter N does not appear in the contents page', since
    none of them is chapter 120. The Workbook publishes no chapter.section list at all,
    so the honest answer is empty, not this one invented entry."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 60), "Contents")
    page.insert_text((60, 90), " 120.00")
    page.insert_text((60, 105), "Printed on 80 GSM paper with NCERT")
    path = tmp_path / "toc.pdf"
    doc.save(path)
    doc.close()

    assert parse_toc(path) == {}
