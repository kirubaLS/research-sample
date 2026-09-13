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
