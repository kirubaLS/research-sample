"""extract_chapter against Economics: real headings that are not bold at all.

Economics sets its real headings in a custom embedded subset font that carries no bold
flag -- only a size visibly larger than the body. Tried as a fallback, only when the
strict bold pass finds nothing usable at all: a book whose real headings genuinely are
bold (History, Geography, Political Science) must never have this looser, noisier
signal reconsidering them, which is exactly what regressed those three books the first
time this was tried as an OR-condition blended into the same pass instead of a separate
fallback attempt.

Built from the shape of the real jess2xx files, each line reproducing a real problem
found there:

* Everything in the chapter is drawn 5 times as identical overlapping passes (page
  numbers, running headers, story captions) -- the same fake-bold trick Science uses on
  single headings, which read_text's own collapsing was built for but never runs on the
  per-span view this fallback reads.
* 'NOTES FOR THE TEACHER' (front matter), 'SUGGESTED READINGS' (back matter) and
  "LET'S WORK THESE/THIS OUT" (a recurring in-chapter drill prompt) are all set bigger
  than the real headings, and none is excludable by the "biggest size" heuristic alone.
"""

from __future__ import annotations

import pymupdf

from app.ingest.book import extract_chapter, verify_structure


#: the real headings' own ink, also used by the cover -- what the colour fallback keys on
_HEADING_COLOUR = (0.2, 0.1, 0.05)
_CAPTION_COLOUR = (0.4, 0.4, 0.1)


def _custom_heading_font(page, x, y, text, size=12.0):
    """Economics' real headings: a distinct size, but flags=4 -- no bold bit at all."""
    page.insert_text((x, y), text, fontsize=size, color=_HEADING_COLOUR)


def _repeated(page, x, y, text, size=18.0, times=5, color=_CAPTION_COLOUR):
    """The fake-bold-by-repetition trick: the same line drawn several times over itself."""
    for _ in range(times):
        page.insert_text((x, y), text, fontsize=size, color=color)


def _economics_chapter_pdf(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _repeated(page, 60, 60, "74", size=13.5)                       # a repeated page number
    # the cover: same ink as the real headings, which is what the colour fallback reads
    page.insert_text((60, 80), "Chapter 5 : Consumer Rights", fontsize=14.0, color=_HEADING_COLOUR)
    _custom_heading_font(page, 60, 100, "NOTES FOR THE TEACHER", size=24.0)
    _custom_heading_font(page, 60, 160, "SAFETY IS EVERYONE'S RIGHT", size=12.0)
    page.insert_text((60, 180), "Manufacturers must follow safety rules " * 4, fontsize=10.5)
    _repeated(page, 60, 300, "Reji's Suffering", size=18.0)        # a story caption
    _custom_heading_font(page, 60, 340, "When choice is denied", size=12.0)
    page.insert_text((60, 360), "Consumers have the right to choose " * 4, fontsize=10.5)
    page.insert_text((60, 500), "Let’s Work These Out", fontsize=14.0)
    page.insert_text((60, 520), "1. Discuss a time you were denied a choice.", fontsize=10.5)
    page.insert_text((60, 600), "EXERCISES", fontsize=14.0)
    page.insert_text((60, 620), "1. What is meant by consumer protection?", fontsize=10.5)
    _custom_heading_font(page, 60, 700, "SUGGESTED READINGS", size=18.0)
    _custom_heading_font(page, 60, 720, "Books", size=12.0)
    path = tmp_path / "jess205.pdf"
    doc.save(path)
    doc.close()
    return path


def test_non_bold_headings_are_found_when_nothing_bold_is_usable(tmp_path):
    extract = extract_chapter(
        _economics_chapter_pdf(tmp_path), number=5, title="Consumer Rights",
    )
    titles = [s.title for s in extract.sections]
    assert "SAFETY IS EVERYONE'S RIGHT" in titles
    assert "When choice is denied" in titles


def test_repeated_overlapping_draws_do_not_multiply_a_single_heading(tmp_path):
    extract = extract_chapter(
        _economics_chapter_pdf(tmp_path), number=5, title="Consumer Rights",
    )
    titles = [s.title for s in extract.sections]
    assert titles.count("Reji's Suffering") == 0   # a story caption, not a heading at all
    assert "74" not in titles


def test_front_and_back_matter_and_the_recurring_drill_are_never_headings(tmp_path):
    extract = extract_chapter(
        _economics_chapter_pdf(tmp_path), number=5, title="Consumer Rights",
    )
    titles = [s.title for s in extract.sections]
    for excluded in ("NOTES FOR THE TEACHER", "SUGGESTED READINGS", "Let’s Work These Out"):
        assert excluded not in titles


def test_lets_work_these_out_and_exercises_are_read_as_drilled_content(tmp_path):
    extract = extract_chapter(
        _economics_chapter_pdf(tmp_path), number=5, title="Consumer Rights",
    )
    verify_structure(extract)
    assert extract.problems == []
    assert any(c.bucket == "E" for c in extract.chunks)


def test_a_book_whose_real_headings_are_bold_never_uses_the_size_fallback(tmp_path):
    """The regression this guards: the size-based fallback used to run as an OR blended
    into the same pass as bold, and picking up a bigger non-heading (a huge chapter
    title, a drill label) broke books whose real headings were bold all along. It must
    only ever run once the bold pass finds nothing usable at all."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 60, ), "Chapter 5", fontsize=40.0, fontname="hebo")
    page.insert_text((60, 100), "A Real Heading", fontsize=20.0, fontname="hebo")
    page.insert_text((60, 120), "Body text about the topic " * 6, fontsize=10.5)
    page.insert_text((60, 300), "EXERCISES", fontsize=14.0, fontname="hebo")
    page.insert_text((60, 320), "1. A question.", fontsize=10.5)
    path = tmp_path / "jess205.pdf"
    doc.save(path)
    doc.close()

    extract = extract_chapter(path, number=5, title="x")
    assert [s.title for s in extract.sections] == ["A Real Heading"]
