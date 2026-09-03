"""extract_chapter against English: no subsections at all, just fixed-name checkpoints.

First Flight and Footprints without Feet are a continuous story or poem with no numbered
or bold subheading anywhere -- unlike every other book so far, forcing a "sections"
detection pass onto them would either find nothing (correctly reported as a failure) or
pick up noise pretending to be a heading. So the caller (subject-scoped in
`app.api.books`, never guessed here) asks for a single whole-chapter section instead, and
the only structure inside it is BARE_DRILL_LABEL's new English markers: 'Oral
Comprehension Check' (a mid-story checkpoint, repeated), 'Think about it' and 'Talk about
it' (end-of-story). Built from the shape of the real jeff1xx/jefp1xx files.

The Workbook (jewe2xx) is different again: a unit's entire body IS the exercise -- there
is no taught-then-drilled split -- so its whole section is bucket E, not T.
"""

from __future__ import annotations

import pymupdf

from app.ingest.book import extract_chapter, verify_structure


def _plain(page, x, y, text, size=10.5):
    page.insert_text((x, y), text, fontsize=size)


def _english_story_pdf(tmp_path, name="jeff101.pdf"):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _plain(page, 60, 60, "THE house sat on the crest of a low hill. " * 6)
    _plain(page, 60, 200, "Oral Comprehension Check")
    _plain(page, 60, 220, "1.")
    _plain(page, 75, 220, "What did Lencho hope for?")
    _plain(page, 60, 300, "That night was a sorrowful one, all our work for nothing. " * 6)
    _plain(page, 60, 500, "Think about it")
    _plain(page, 60, 520, "1.")
    _plain(page, 75, 520, "Do you think Lencho was a wise man?")
    _plain(page, 60, 600, "Talk about it")
    _plain(page, 60, 620, "1.")
    _plain(page, 75, 620, "Discuss letters of faith you have read about.")
    path = tmp_path / name
    doc.save(path)
    doc.close()
    return path


def test_a_continuous_story_becomes_one_whole_chapter_section(tmp_path):
    extract = extract_chapter(
        _english_story_pdf(tmp_path), number=1, title="A Letter to God", single_section=True,
    )
    assert [s.number for s in extract.sections] == ["1"]
    assert extract.sections[0].title == "A Letter to God"


def test_the_english_checkpoints_are_read_as_drilled_content(tmp_path):
    extract = extract_chapter(
        _english_story_pdf(tmp_path), number=1, title="A Letter to God", single_section=True,
    )
    verify_structure(extract)
    assert extract.problems == []
    e_refs = [c.reference for c in extract.chunks if c.bucket == "E"]
    assert any("Oral Comprehension Check" in r for r in e_refs)
    assert any("Think About It" in r for r in e_refs)
    assert any("Talk About It" in r for r in e_refs)


def test_without_single_section_a_storys_prose_finds_no_sections_at_all(tmp_path):
    """The regression this guards against: a story has no numbered or bold heading of any
    kind, so without single_section it must honestly report nothing found, never silently
    invent a section out of noise the way a book with real headings would."""
    extract = extract_chapter(
        _english_story_pdf(tmp_path), number=1, title="A Letter to God",
    )
    assert extract.sections == []


def test_a_workbook_unit_is_entirely_exercise_content_not_taught_body(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _plain(page, 60, 60, "You have read about Lencho in 'A Letter to God'. " * 6)
    _plain(page, 60, 300, "Rearrange the jumbled sentences to make a coherent story. " * 4)
    path = tmp_path / "jewe201.pdf"
    doc.save(path)
    doc.close()

    extract = extract_chapter(
        path, number=1, title="A Letter to God", single_section=True, body_bucket="E",
    )
    assert extract.chunks and all(c.bucket == "E" for c in extract.chunks)
    verify_structure(extract)
    assert extract.problems == []
