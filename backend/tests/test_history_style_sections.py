"""extract_chapter against History's own numbering.

History numbers its headings independent of the chapter -- a bare major number with no
decimal ('1  Title', two spaces) and a decimal subsection under it ('2.1 Title', one
space, and '2' here is the second heading in this chapter, not chapter 2) -- and closes
each teaching block with 'Discuss', 'Write in brief' or 'Project' rather than the word
'EXERCISE' or 'QUESTIONS'. Built from the shape of the real jess3xx chapters.

BOOK_NUMBERED_SECTION is only ever matched against a line already known to be bold (see
_sections_by_boldness): a *plain* numbered list in a book's body prose matches the exact
same shape without being a heading, which is what the Political Science files turned out
to have. So every scenario here is exercised through a real (synthetic) bold PDF via
extract_chapter, not by calling extract_sections on plain text alone.
"""

from __future__ import annotations

import pymupdf

from app.ingest.book import (
    BOOK_NUMBERED_SECTION,
    ChapterExtract,
    Chunk,
    Section,
    extract_chapter,
    extract_sections,
    verify_structure,
)


def _bold(page, x, y, text, size=11.0):
    page.insert_text((x, y), text, fontsize=size, fontname="hebo")


def _plain(page, x, y, text, size=10.5):
    page.insert_text((x, y), text, fontsize=size)


def _history_chapter_pdf(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _plain(page, 60, 40, "5")
    _plain(page, 60, 55, "Nationalism   in   Europe")   # a running header, not a heading
    _bold(page, 60, 90, "1  The French Revolution and the Idea of the Nation")
    _plain(page, 60, 110, "The first clear expression of nationalism came with " * 4)
    _plain(page, 60, 200, "7")   # a bare page number: must never swallow the header below
    _plain(page, 60, 215, "Nationalism   in   Europe")
    _bold(page, 60, 250, "2  The Making of Nationalism in Europe")
    _plain(page, 60, 270, "A very general account of the diverse processes " * 4)
    _bold(page, 60, 400, "2.1 The Aristocracy and the New Middle Class")
    _plain(page, 60, 420, "Socially and politically, a landed aristocracy " * 4)
    _bold(page, 60, 550, "3.3 1848: The Revolution of the Liberals")
    _plain(page, 60, 570, "Parallel to the revolts of the poor, unemployed " * 4)
    _bold(page, 60, 700, "Discuss", size=8.0)
    _bold(page, 60, 715, "Project", size=8.0)
    _plain(page, 60, 730, "1.")
    _plain(page, 75, 730, "Explain what is meant by the 1848 revolution of the liberals.")
    _bold(page, 60, 750, "Write in brief", size=8.0)
    _plain(page, 60, 765, "1.")
    _plain(page, 75, 765, "Write a note on Guiseppe Mazzini.")
    path = tmp_path / "ch1.pdf"
    doc.save(path)
    doc.close()
    return path


def test_the_books_own_numbering_is_read_when_chapter_numbering_finds_nothing(tmp_path):
    extract = extract_chapter(
        _history_chapter_pdf(tmp_path), number=1, title="The Rise of Nationalism in Europe"
    )
    assert [s.number for s in extract.sections] == ["1", "2", "2.1", "3.3"]
    assert extract.sections[0].title == "The French Revolution and the Idea of the Nation"
    assert extract.sections[2].title == "The Aristocracy and the New Middle Class"


def test_a_bare_page_number_does_not_swallow_the_running_header_below_it(tmp_path):
    """This was the actual bug: a page number on its own line matched as a section whose
    title was the running header printed below it, because \\s between the number and the
    title consumed the newline between them."""
    extract = extract_chapter(
        _history_chapter_pdf(tmp_path), number=1, title="The Rise of Nationalism in Europe"
    )
    titles = [s.title for s in extract.sections]
    assert "Nationalism   in   Europe" not in titles


def test_an_end_of_chapter_numbered_question_is_never_read_as_a_heading():
    """'1.\\nExplain what is meant...' -- a period after the number and the text on the
    next line -- must never be mistaken for '1  Title', which has no period and keeps its
    title on the same line."""
    assert not BOOK_NUMBERED_SECTION.match("1.")
    assert BOOK_NUMBERED_SECTION.match("1  The French Revolution and the Idea of the Nation")


def test_discuss_write_in_brief_and_project_are_read_as_drilled_content(tmp_path):
    extract = extract_chapter(
        _history_chapter_pdf(tmp_path), number=1, title="The Rise of Nationalism in Europe"
    )
    verify_structure(extract)
    assert extract.problems == []
    assert any(c.bucket == "E" for c in extract.chunks)


def test_gap_detection_is_skipped_for_the_books_own_numbering_not_guessed_at():
    """A '1', '2', '2.1', '3.3' chapter is not missing '1.2' -- it was never numbered
    chapter.section to begin with, and the gap check must not invent a hole that isn't
    there just because a bare '1' has no dot to split on."""
    extract = ChapterExtract(
        number=1, title="x", source_path="x.pdf", sha256="hash",
        chunks=[Chunk("E", "exercise", "Discuss 1.1", "text", "hash", section="1")],
        sections=[
            Section("1", "A", 0, 1), Section("2", "B", 1, 2),
            Section("2.1", "C", 2, 3), Section("3.3", "D", 3, 4),
        ],
        problems=[],
    )
    verify_structure(extract)
    assert extract.problems == []


def test_chapter_numbered_sections_still_take_priority_when_present():
    """A Maths-style chapter (headings anchored to its own chapter number) must never be
    re-read by the looser convention -- the first pattern finding something is final."""
    text = "9.1 Introduction\nBody.\n9.2 Areas of Sector and Segment\nMore body.\n"
    sections = extract_sections(text, chapter=9)
    assert [s.number for s in sections] == ["9.1", "9.2"]
