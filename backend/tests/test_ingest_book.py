"""Book extraction, and the checks that stop a bad structure pass reaching the database.

Every failure here is silent in production: a phantom section, a missing one, or the
answer key loaded as practice content all produce confident numbers computed against a
tree nothing contradicts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ingest.book import (
    ChapterExtract,
    Section,
    chapter_number,
    extract_chunks,
    extract_sections,
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


# --- buckets --------------------------------------------------------------------------

def test_theorems_and_examples_are_taught_content_exercises_are_practice():
    text = (
        "Theorem 1.3 : Root 2 is irrational\nproof body\n"
        "Example 4 : Find the HCF\nworked body\n"
        "EXERCISE 1.2\n1. Prove that...\n"
    )
    chunks = {c.kind: c for c in extract_chunks(text)}
    assert chunks["theorem"].bucket == "T"
    assert chunks["example"].bucket == "T"
    assert chunks["exercise"].bucket == "E"


def test_an_example_written_without_a_space_before_the_colon_still_matches():
    """NCERT writes both 'Example 3 :' and 'Example 3:'."""
    assert len(extract_chunks("Example 3: Find the HCF\nbody\n")) == 1


def test_an_optional_exercise_is_captured_but_marked_non_examinable():
    """'EXERCISE 5.4 (Optional)*' was dropped entirely by an end-of-line anchor."""
    chunks = extract_chunks("EXERCISE 5.4 (Optional)*\n1. Which term...\n")
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
        chunks=extract_chunks("Example 1 : x\nbody\n"),
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

def test_only_numbered_chapter_files_are_chapters():
    assert chapter_number("12-surface-areas-and-volumes.pdf") == 12
    # the answers file matches EXERCISE 31 times; treating it as a chapter would load the
    # answer key as practice content
    assert chapter_number("an-answers.pdf") is None
    assert chapter_number("a1-proofs-in-mathematics.pdf") is None
    assert chapter_number("00-contents.pdf") == 0


# --- against the real book, when it is present ----------------------------------------

@real_book
def test_the_whole_maths_book_agrees_with_its_own_contents_page():
    from app.ingest.book import extract_chapter, parse_toc

    toc = parse_toc(BOOK / "00-contents.pdf")
    assert len(toc) == 14

    files = sorted(p for p in BOOK.glob("[0-9][0-9]-*.pdf") if p.name != "00-contents.pdf")
    assert len(files) == 14

    for path in files:
        result = verify_against_toc(extract_chapter(path), toc)
        assert result.ok, f"{path.name}: {result.problems}"


@real_book
def test_theorems_appear_only_in_the_chapters_that_prove_things():
    from app.ingest.book import extract_chapter

    with_theorems = {
        extract_chapter(p).number
        for p in BOOK.glob("[0-9][0-9]-*.pdf")
        if any(c.kind == "theorem" for c in extract_chapter(p).chunks)
    }
    # Real Numbers, Triangles, Circles
    assert with_theorems == {1, 6, 10}
