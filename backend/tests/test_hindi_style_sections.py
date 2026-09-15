"""extract_chapter against Hindi: OCR'd text, one whole-chapter section, and the
end-of-chapter exercise marker.

Built from the real jhkr101.pdf (NCERT Kritika, chapter 1, माता का अँचल), OCR'd through
Tesseract exactly as the deployed pipeline does. That file's exercise heading -- 'अभ्यास'
-- is set as decorative art rather than plain text, so Tesseract renders it as
unrecognisable noise and HINDI_DRILL_LABEL never fires. What IS real text is the numbered
question list itself, beginning directly after the story's last line with no heading at
all -- HINDI_NUMBERED_QUESTION is what actually catches this book's exercises, the same
"no fixed label, trust the numbering" case ENGLISH_NUMBERED_QUESTION already covers for
First Flight's jeff103/108/109.

Tesseract also drops the first question's leading digit here, the same quirk already
known from a contents page's chapter 1 (see _recover_hindi_first_chapter_number) -- the
snippet below reproduces that exact shape: a bare '.' in front of question 1's text.
"""

from __future__ import annotations

import pymupdf

from app.ingest.book import extract_chapter, verify_structure

_HINDI_CHAPTER_TEXT = (
    "हम एक सुर से दौड़े हुए आए और घर में घुस गए। उस समय बाबू जी बैठक के ओसारे में बेठकर "
    "हुक्का गुडगुड़ा रहे थे।\n\n"
    "पर हमने मइयाँ के आँचल की-प्रेम और शांति के चँँदोवे की-छाया न छोड़ी...।\n\n"
    ". प्रस्तुत पाठ के आधार पर यह कहा जा सकता है कि बच्चे का अपने पिता से अधिक जुड़ाव था।\n\n"
    "2. आपके विचार से भोलानाथ अपने साथियों को देखकर सिसकना क्‍यों भूल जाता हे?\n\n"
    "3. आपने देखा होगा कि भोलानाथ और उसके साथी जब-तब खेलते-खाते समय किसी तुकबंदी करते हैं।\n"
)


def _blank_pdf(tmp_path, name="jhkr101.pdf"):
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)
    path = tmp_path / name
    doc.save(path)
    doc.close()
    return path


def test_an_ocrd_hindi_chapter_becomes_one_whole_chapter_section(tmp_path):
    extract = extract_chapter(
        _blank_pdf(tmp_path), number=1, title="माता का अँचल", single_section=True,
        text_override=_HINDI_CHAPTER_TEXT,
    )
    assert [s.number for s in extract.sections] == ["1"]
    assert extract.sections[0].title == "माता का अँचल"


def test_numbered_questions_are_read_as_the_exercise_even_with_no_heading(tmp_path):
    """The regression this guards against: HINDI_DRILL_LABEL alone found nothing on the
    real file (the 'अभ्यास' heading is decorative art, not text), which used to fail
    verify_structure with 'no exercises or questions were found' on a chapter that plainly
    has some."""
    extract = extract_chapter(
        _blank_pdf(tmp_path), number=1, title="माता का अँचल", single_section=True,
        text_override=_HINDI_CHAPTER_TEXT,
    )
    verify_structure(extract)
    assert extract.problems == []
    e_refs = [c.reference for c in extract.chunks if c.bucket == "E"]
    assert len(e_refs) == 3


def test_the_first_questions_dropped_leading_digit_is_still_counted(tmp_path):
    """Tesseract drops question 1's leading digit here just like chapter 1's on a contents
    page -- a bare '.' in front of Devanagari text still has to count as a question, not be
    swallowed into the body."""
    extract = extract_chapter(
        _blank_pdf(tmp_path), number=1, title="माता का अँचल", single_section=True,
        text_override=_HINDI_CHAPTER_TEXT,
    )
    e_chunks = [c for c in extract.chunks if c.bucket == "E"]
    assert any("प्रस्तुत पाठ के आधार पर" in c.text for c in e_chunks)
