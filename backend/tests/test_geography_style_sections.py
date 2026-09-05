"""extract_chapter against a book that numbers no headings at all -- bare or decimal.

Geography publishes no section list and its own subheadings carry no number, so nothing
in a chapter's plain text says where one begins. What marks a real heading is typography:
bold, at the chapter's own largest bold size -- a margin glossary term and a figure
caption are bold too, but smaller. Built from the real jess1xx files' actual font sizes
(12.0pt bold headings against 10.5pt bold noise), including the two ways this first
carried the wrong answer: a same-size bold drill word ('PROJECT/ACTIVITY') read as a
heading, and 'EXERCISES' drawn sideways coming back as the same word five times on one
line rather than Science's one-character-per-line split.
"""

from __future__ import annotations

import pymupdf

from app.ingest.book import extract_chapter, verify_structure


def _bold(page, x, y, text, size=12.0):
    page.insert_text((x, y), text, fontsize=size, fontname="hebo")  # a built-in bold font


def _plain(page, x, y, text, size=10.5):
    page.insert_text((x, y), text, fontsize=size)


def _geography_chapter_pdf(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _plain(page, 60, 60, "2")
    _plain(page, 60, 75, "CONTEMPORARY INDIA - II")
    _bold(page, 60, 100, "DEVELOPMENT OF RESOURCES", size=12.0)
    _plain(page, 60, 120, "Resources are vital for human survival " * 6)
    _bold(page, 60, 220, "Sustainable development", size=10.5)   # margin glossary noise
    _plain(page, 60, 235, "A term coined at the Rio Earth Summit.")
    _bold(page, 60, 260, "LAND UTILISATION", size=12.0)
    _plain(page, 60, 280, "Land resources are used for the following purposes " * 6)
    page2 = doc.new_page(width=595, height=842)
    _bold(page2, 60, 60, "LAND DEGRADATION AND CONSERVATION", size=12.0)
    _bold(page2, 60, 78, "MEASURES", size=12.0)   # a title wrapped across two lines
    _plain(page2, 60, 100, "Human activities have brought about degradation of land " * 6)
    _bold(page2, 60, 300, "EXERCISES  EXERCISES  EXERCISES  EXERCISES  EXERCISES", size=8.0)
    _bold(page2, 60, 320, "PROJECT/ACTIVITY", size=12.0)   # same size as real headings
    _plain(page2, 60, 340, "1. Identify three states rich in minerals.")
    path = tmp_path / "jess101.pdf"
    doc.save(path)
    doc.close()
    return path


def test_headings_are_found_by_their_own_largest_bold_size(tmp_path):
    extract = extract_chapter(_geography_chapter_pdf(tmp_path), number=1, title="x")
    titles = [s.title for s in extract.sections]
    assert titles == [
        "DEVELOPMENT OF RESOURCES",
        "LAND UTILISATION",
        "LAND DEGRADATION AND CONSERVATION MEASURES",
    ]


def test_a_same_size_bold_drill_word_is_never_read_as_a_heading(tmp_path):
    extract = extract_chapter(_geography_chapter_pdf(tmp_path), number=1, title="x")
    assert "PROJECT/ACTIVITY" not in [s.title for s in extract.sections]


def test_a_smaller_bold_margin_term_is_never_read_as_a_heading(tmp_path):
    extract = extract_chapter(_geography_chapter_pdf(tmp_path), number=1, title="x")
    assert "Sustainable development" not in [s.title for s in extract.sections]


def test_exercises_drawn_sideways_is_still_found_as_one_drilled_marker(tmp_path):
    extract = extract_chapter(_geography_chapter_pdf(tmp_path), number=1, title="x")
    verify_structure(extract)
    assert extract.problems == []
    assert any(c.bucket == "E" for c in extract.chunks)


def test_headings_are_found_even_when_the_largest_bold_text_is_all_noise(tmp_path):
    """The real bug on jess105/106: every 12pt bold line in the chapter was 'ACTIVITY' or
    'PROJECT WORK', and picking the chapter's largest bold size BEFORE excluding those
    left either nothing, or the drill word standing in for every real heading. Real
    headings here sit one size down, at 10.5 -- noise must be filtered out first, so the
    heading size is decided from what is actually left over."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _bold(page, 60, 60, "Study of Minerals by Geographers and Geologists", size=10.5)
    _plain(page, 60, 80, "A very general account of how minerals are studied " * 6)
    _bold(page, 60, 300, "Hazards of Mining", size=10.5)
    _plain(page, 60, 320, "Mining is a hazardous occupation for workers " * 6)
    _bold(page, 60, 500, "ACTIVITY", size=12.0)   # bigger than every real heading here
    _plain(page, 60, 520, "Find out about mining hazards in your region.")
    _bold(page, 60, 600, "EXERCISES  EXERCISES  EXERCISES  EXERCISES  EXERCISES", size=8.0)
    _plain(page, 60, 620, "1. Name any two states rich in minerals.")
    path = tmp_path / "jess105.pdf"
    doc.save(path)
    doc.close()

    extract = extract_chapter(path, number=5, title="x")
    verify_structure(extract)
    assert extract.problems == []
    titles = [s.title for s in extract.sections]
    assert titles == ["Study of Minerals by Geographers and Geologists", "Hazards of Mining"]
    assert "ACTIVITY" not in titles


def test_headings_at_the_same_visual_size_are_grouped_despite_float_precision(tmp_path):
    """The real bug: two headings both set at "10.5pt" can carry different exact floats
    (10.5 vs 10.500472068786621) depending on how the PDF's font matrix scaled them.
    Comparing those unrounded kept only whichever single float happened to be the max,
    dropping every other real heading at the same size a person would call identical."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _bold(page, 60, 60, "Tidal Energy", size=10.5)
    _plain(page, 60, 80, "Tidal energy is generated using the rise and fall " * 5)
    # A tiny scale nudge on the font matrix is what actually produces a non-round float
    # in a real PDF; inserting through a slightly different transform reproduces it here.
    page.insert_text((60, 300), "Geo Thermal Energy", fontsize=10.5 + 1e-6, fontname="hebo")
    _plain(page, 60, 320, "Geothermal energy is heat energy from within the earth " * 5)
    path = tmp_path / "jess105.pdf"
    doc.save(path)
    doc.close()

    extract = extract_chapter(path, number=5, title="x")
    titles = [s.title for s in extract.sections]
    assert titles == ["Tidal Energy", "Geo Thermal Energy"]
