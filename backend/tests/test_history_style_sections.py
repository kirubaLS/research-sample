"""extract_sections and verify_structure against History's own numbering.

History numbers its headings independent of the chapter -- a bare major number with no
decimal ('1  Title', two spaces) and a decimal subsection under it ('2.1 Title', one
space, and '2' here is the second heading in this chapter, not chapter 2) -- and closes
each teaching block with 'Discuss', 'Write in brief' or 'Project' rather than the word
'EXERCISE' or 'QUESTIONS'. Built from the shape of the real jess3xx chapters, including
the two ways that shape first broke: a bare page number swallowing the running header on
the line below it as a section title, and the chapter-numbered pattern finding nothing at
all because History's '2.1' has nothing to do with chapter 1.
"""

from __future__ import annotations

from app.ingest.book import (
    ChapterExtract,
    Chunk,
    Section,
    extract_chapter,
    extract_sections,
    verify_structure,
)


def _history_chapter_text() -> str:
    return (
        "5\nNationalism   in   Europe\n"
        "1  The French Revolution and the Idea of the Nation\n"
        "The first clear expression of nationalism came with the French Revolution.\n"
        "\n7\nNationalism   in   Europe\n"
        "2  The Making of Nationalism in Europe\n"
        "A very general account of the diverse processes.\n"
        "2.1 The Aristocracy and the New Middle Class\n"
        "Socially and politically, a landed aristocracy was the dominant class.\n"
        "2.2 What did Liberal Nationalism Stand for?\n"
        "The term liberalism derives from the Latin root liber.\n"
        "\n13\nNationalism   in   Europe\n"
        "3.3 1848: The Revolution of the Liberals\n"
        "Parallel to the revolts of the poor, unemployed and starving peasants.\n"
        "28\nDiscuss\n"
        "Project\n"
        "1.\nExplain what is meant by the 1848 revolution of the liberals.\n"
        "2.\nChoose three examples to show the contribution of culture.\n"
        "Write in brief\n"
        "1.\nWrite a note on Guiseppe Mazzini.\n"
    )


def test_a_bare_page_number_does_not_swallow_the_running_header_below_it():
    """This was the actual bug: '\\n7\\nNationalism in Europe' matched as a section
    numbered '7' whose title was the running header, because \\s between the number and
    the title consumed the newline between them."""
    sections = extract_sections(_history_chapter_text(), chapter=1)
    numbers = [s.number for s in sections]
    assert "7" not in numbers
    assert "13" not in numbers
    assert "28" not in numbers


def test_the_books_own_numbering_is_read_when_chapter_numbering_finds_nothing():
    sections = extract_sections(_history_chapter_text(), chapter=1)
    assert [s.number for s in sections] == ["1", "2", "2.1", "2.2", "3.3"]
    assert sections[0].title == "The French Revolution and the Idea of the Nation"
    assert sections[2].title == "The Aristocracy and the New Middle Class"


def test_an_end_of_chapter_numbered_question_is_never_read_as_a_heading():
    """'1.\\nExplain what is meant...' -- a period after the number and the text on the
    next line -- must never be mistaken for '1  Title', which has no period and keeps its
    title on the same line."""
    sections = extract_sections(_history_chapter_text(), chapter=1)
    assert not any(s.title.startswith("Explain") for s in sections)
    assert not any(s.title.startswith("Write a note") for s in sections)


def test_discuss_write_in_brief_and_project_are_read_as_drilled_content(tmp_path):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    y = 60
    for line in _history_chapter_text().split("\n"):
        page.insert_text((60, y), line, fontsize=9)
        y += 12
    path = tmp_path / "ch1.pdf"
    doc.save(path)
    doc.close()

    extract = extract_chapter(path, number=1, title="The Rise of Nationalism in Europe")
    assert extract.problems == []
    buckets = [c.bucket for c in extract.chunks]
    assert "E" in buckets


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
