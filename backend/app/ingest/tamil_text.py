"""Tamil books: a real Unicode text layer, unlike Hindi's (see app.ingest.hindi_ocr) --
no OCR backend needed at all -- but with its own font-level artifact to correct first.

Checked against the real CBSE Tamil Class X book (174 pages, pymupdf's own extraction,
not a third-party converter's): the font subsets used for chapter bodies repeat certain
glyphs -- a consonant, a vowel sign, sometimes with a stray U+FFFD between the repeats --
two or three times in a row where the printed page has it once. 'சாாார்ந்த' should read
'சார்ந்த' ("related to"); 'மொ�ொழியின்' should read 'மொழியின்' ("of language"). This is
never genuine Tamil orthography -- a real doubled consonant is written with an explicit
virama between the two (க்க​), not the same bare code point twice -- so collapsing any run
of an identical Tamil character (optionally separated by U+FFFD) is safe and verified to
turn corrupted words back into real ones across sampled pages spanning the whole book.

It does not recover everything: about 0.57% of characters book-wide are a bare U+FFFD with
no duplicate to collapse -- a genuinely unmapped glyph, not a formatting artifact, and no
regex fixes that. Left in place rather than silently dropped, the same way OCR noise
elsewhere in this codebase is surfaced rather than hidden.
"""

from __future__ import annotations

import re

import pymupdf

#: U+0B80-U+0BFF, the Tamil Unicode block. Restricting the match to it (rather than any
#: character) is what keeps this from ever touching an English word, a digit, or
#: punctuation that happens to repeat for a real reason (e.g. '!!' in body text).
_TAMIL_CHAR_RUN = re.compile(r"([஀-௿])(?:�?\1)+")


def clean_tamil_text(text: str) -> str:
    """Collapse the font's own glyph-repeat artifact -- see module docstring."""
    return _TAMIL_CHAR_RUN.sub(r"\1", text)


def tamil_read_text(source: str | bytes) -> str:
    """A Tamil book's real text: pymupdf's own extraction, cleaned.

    Accepts a path or raw bytes so a caller holding an upload in memory does not need a
    temp file just to read text from it -- the same shape app.ingest.hindi_text's OCR
    backends take.
    """
    doc = pymupdf.open(stream=source, filetype="pdf") if isinstance(source, bytes) else pymupdf.open(source)
    try:
        raw = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()
    return clean_tamil_text(raw)
