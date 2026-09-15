"""parse_toc_chapters against the Tamil contents page's own column layout.

www.cbsetamil.com's book has no chapter LABEL anywhere on the page -- no 'Chapter N', no
leading number, not even a per-chapter unit number (the வ.எண் column is set once per
இயல், not once per chapter). Every existing TOC_CHAPTER* pattern and the Economics
position-by-"Chapter"-label fallback find nothing here at all, so chapter identity is read
purely from the title/page-number columns' x-position -- see
_tamil_toc_chapters_by_position's own docstring for how that was derived from the real
book's own word coordinates.

No Tamil-capable font is installed in this environment for pymupdf to render real glyphs
with (unlike English/Devanagari's synthetic-PDF tests elsewhere in this suite), so a real
PDF cannot be built here the way those are. Instead pymupdf.open is stubbed to return
canned page.get_text("words") tuples at the SAME x-coordinates the real contents page
uses (verified against the real file directly, not guessed) -- this still exercises the
actual row-clustering and column-filtering logic, just without needing font rendering to
get there.
"""

from __future__ import annotations

import pymupdf
import pytest

from app.ingest.book import parse_toc_chapters

#: matches the real page's own column x-ranges (see _TAMIL_TITLE_X/_TAMIL_PAGENUM_X)
_UNIT_X, _THEME_X, _TITLE_X, _PAGENUM_X, _MONTH_X = 65.0, 140.0, 234.0, 458.0, 502.0


class _FakePage:
    def __init__(self, words):
        self._words = words

    def get_text(self, mode="text"):
        if mode == "words":
            # (x0, y0, x1, y1, text, block_no, line_no, word_no) -- only the fields
            # _tamil_toc_chapters_by_position actually reads are populated for real.
            return [(x0, y0, x0 + 10, y0 + 10, text, 0, 0, 0) for x0, y0, text in self._words]
        # parse_toc_chapters itself calls read_text -> page.get_text() with no args first,
        # to decide whether the page is Tamil at all -- must return something containing
        # Tamil script, or the position-based path is never tried.
        return " ".join(t for _, _, t in self._words)


class _FakeDoc:
    def __init__(self, pages):
        self._pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self._pages)


#: Row 1: unit number, theme and the first chapter's title+page glued onto one visual
#: line, the way the real page's own row 1 does -- the unit-number and theme columns must
#: never be concatenated into the title.
#: Row 2: an ordinary title row, no glued columns.
#: Row 3: a title row with a CORRUPTED month name leaking in from the month column -- the
#: real bug this fix targets: '�' doubles a glyph in "ஆகஸ்டு" the same way
#: app.ingest.tamil_text's own docstring describes, so it must be cleaned before the
#: exact-match check against the month set, not after.
#: Row 4/5: a standalone month row and a page-footer roman numeral -- neither ends in a
#: digit, so neither should ever be read as a chapter.
_PAGE_WORDS = [
    (_UNIT_X, 120, "1"),
    (_THEME_X, 120, "மொழி,"), (_THEME_X + 60, 120, "மனிதம்"),
    (_TITLE_X, 120, "அன்னை"), (_TITLE_X + 60, 120, "மொழியே"), (_PAGENUM_X, 120, "2"),
    (_TITLE_X, 150, "அமுதஊற்று"), (_PAGENUM_X, 150, "4"),
    (_TITLE_X, 180, "விருந்து"), (_PAGENUM_X, 180, "46"), (_MONTH_X, 180, "ஆக�க�ஸ்டு"),
    (_MONTH_X, 210, "ஜூன்"),
    (300, 800, "VIII"),
]


@pytest.fixture
def tamil_contents(monkeypatch):
    monkeypatch.setattr(pymupdf, "open", lambda *a, **k: _FakeDoc([_FakePage(_PAGE_WORDS)]))
    return "fake-tamil-contents.pdf"


def test_the_unit_number_and_theme_columns_are_not_glued_onto_the_title(tamil_contents):
    found = parse_toc_chapters(tamil_contents)
    assert found[1] == "அன்னை மொழியே"


def test_a_corrupted_month_token_leaking_into_a_title_row_is_still_dropped(tamil_contents):
    """Real production bug: an unclean month token failed its exact-match check against
    _TAMIL_MONTH_NAMES, survived as the row's last token, failed isdigit(), and the whole
    title row ('பாய்ச்சல் 102' in the real book) silently disappeared rather than just
    losing the one stray word."""
    found = parse_toc_chapters(tamil_contents)
    assert found[3] == "விருந்து"


def test_a_standalone_month_row_and_a_page_footer_are_never_read_as_chapters(tamil_contents):
    found = parse_toc_chapters(tamil_contents)
    assert set(found) == {1, 2, 3}
    assert all("VIII" not in t and "ஜூன்" not in t for t in found.values())
