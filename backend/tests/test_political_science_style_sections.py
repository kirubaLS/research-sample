"""extract_chapter against Political Science: real headings that are bold but unnumbered,
and three new ways the earlier fixes still weren't enough.

Built from the shape of the real jess4xx files, each reproducing one bug found there:

* A book's body prose can contain a *plain* (non-bold) numbered list -- 'Chapter 2, Power
  is shared among different organs of government...' -- that matches
  BOOK_NUMBERED_SECTION's shape exactly without being a heading at all. Only a bold line
  is allowed to satisfy it now.
* The chapter's own cover text -- 'Chapter 2' in large type, and the chapter's title set
  even bigger than that -- otherwise wins "the chapter's largest bold text" outright and
  becomes the entire heading list, single-handedly, because a cover page is drawn far
  bigger than any real heading.
* A title set across several separate bold lines on the cover ('Gender,' / 'Religion and'
  / 'Caste') has no single line equal to the whole title, so each fragment must be
  excluded as a *substring* of it, not by exact match.
"""

from __future__ import annotations

import pymupdf

from app.ingest.book import extract_chapter, verify_structure


def _bold(page, x, y, text, size=20.0):
    page.insert_text((x, y), text, fontsize=size, fontname="hebo")


def _plain(page, x, y, text, size=10.5):
    page.insert_text((x, y), text, fontsize=size)


def _polsci_chapter_pdf(tmp_path, chapter_title="Gender, Religion and Caste"):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _bold(page, 60, 60, "Chapter 3", size=40.0)               # cover: never a heading
    words = chapter_title.split(" ")
    _bold(page, 60, 130, words[0], size=65.0)                # 'Gender,'
    _bold(page, 60, 200, " ".join(words[1:3]), size=65.0)    # 'Religion and'
    _bold(page, 60, 270, words[3], size=65.0)                # 'Caste'
    _bold(page, 60, 340, "Gender and politics")
    _plain(page, 60, 360, "The literacy rate among women is much lower " * 4)
    # a *plain* numbered list in body prose: same shape as a heading, never bold
    _plain(page, 60, 470, "1.")
    _plain(page, 75, 470, "Gender division is not based on biology but social expectations.")
    _bold(page, 60, 560, "Religion, communalism and politics")
    _plain(page, 60, 580, "Communalism is a political doctrine " * 4)
    _bold(page, 60, 680, "Exercises", size=100.0)
    _plain(page, 60, 750, "1. What is meant by communal politics?")
    path = tmp_path / "ch3.pdf"
    doc.save(path)
    doc.close()
    return path


def test_real_headings_are_found_despite_being_smaller_than_the_cover(tmp_path):
    extract = extract_chapter(
        _polsci_chapter_pdf(tmp_path), number=3, title="Gender, Religion and Caste",
    )
    assert [s.title for s in extract.sections] == [
        "Gender and politics", "Religion, communalism and politics",
    ]


def test_a_plain_numbered_list_in_body_prose_is_never_read_as_a_heading(tmp_path):
    extract = extract_chapter(
        _polsci_chapter_pdf(tmp_path), number=3, title="Gender, Religion and Caste",
    )
    titles = [s.title for s in extract.sections]
    assert not any("Gender division" in t for t in titles)


def test_the_chapter_cover_and_its_wrapped_title_are_never_read_as_headings(tmp_path):
    extract = extract_chapter(
        _polsci_chapter_pdf(tmp_path), number=3, title="Gender, Religion and Caste",
    )
    titles = [s.title for s in extract.sections]
    assert "Chapter 3" not in titles
    assert not any(t in ("Gender,", "Religion and", "Caste") for t in titles)


def test_exercises_at_a_huge_size_does_not_swallow_the_real_headings(tmp_path):
    extract = extract_chapter(
        _polsci_chapter_pdf(tmp_path), number=3, title="Gender, Religion and Caste",
    )
    verify_structure(extract)
    assert extract.problems == []
    assert any(c.bucket == "E" for c in extract.chunks)
