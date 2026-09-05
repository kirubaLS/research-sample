"""extract_chapter against Tamil: one whole-chapter section (like English/Hindi), and the
end-of-chapter question marker.

Body text below is placeholder prose written for this test, not the textbook's own words --
only the structural exercise heading and the numbered-question layout are the real,
confirmed shape (see TAMIL_DRILL_LABEL/TAMIL_NUMBERED_QUESTION in app.ingest.book), the
same way a fixed heading label like 'EXERCISES' or 'अभ्यास' is trusted elsewhere in this
module without needing the surrounding body text to be real.
"""

from __future__ import annotations

import pymupdf

from app.ingest.book import extract_chapter, verify_structure

_TAMIL_CHAPTER_TEXT = (
    "இது ஒரு எடுத்துக்காட்டு வாக்கியம். இது இரண்டாவது வாக்கியம்.\n\n"
    "இது மூன்றாவது வாக்கியம், பயிற்சிக்கு முன் வரும் உரை.\n\n"
    "கற்பவை கற்றபின்...\n\n"
    "1. \t\n"
    "“இது முதல் கேள்வி.” இதற்கான விடையை எழுதுக.\n\n"
    "2. \t\n"
    "“இது இரண்டாவது கேள்வி.” விளக்கமாக விடையளிக்கவும்.\n"
)


def _blank_pdf(tmp_path, name="01-chapter.pdf"):
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)
    path = tmp_path / name
    doc.save(path)
    doc.close()
    return path


def test_a_tamil_chapter_becomes_one_whole_chapter_section(tmp_path):
    extract = extract_chapter(
        _blank_pdf(tmp_path), number=1, title="ஒரு எடுத்துக்காட்டு தலைப்பு",
        single_section=True, text_override=_TAMIL_CHAPTER_TEXT,
    )
    assert [s.number for s in extract.sections] == ["1"]


def test_the_fixed_heading_and_numbered_questions_are_read_as_the_exercise(tmp_path):
    """The regression this guards against: without TAMIL_DRILL_LABEL/
    TAMIL_NUMBERED_QUESTION, every real Tamil chapter upload 422'd with 'no exercises or
    questions were found' -- confirmed on the real book, where 28 of 36 chapters failed
    this way before these markers existed."""
    extract = extract_chapter(
        _blank_pdf(tmp_path), number=1, title="ஒரு எடுத்துக்காட்டு தலைப்பு",
        single_section=True, text_override=_TAMIL_CHAPTER_TEXT,
    )
    verify_structure(extract)
    assert extract.problems == []
    e_refs = [c.reference for c in extract.chunks if c.bucket == "E"]
    assert any("கற்பவை கற்றபின்" in r for r in e_refs)
    assert any("வினா 1.1" in r for r in e_refs)
    assert any("வினா 1.2" in r for r in e_refs)
