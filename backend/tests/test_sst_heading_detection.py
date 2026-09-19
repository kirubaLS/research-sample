"""Regression: two real NCERT Social Science chapters that used to collapse to one
section.

_sections_by_boldness picks the chapter's largest bold text as its heading size, having
excluded known noise (EXERCISES, PROJECT WORK, ...) by exact phrase. Two real books broke
that in two different ways:

* Economics' own "Development" chapter opens with a "NOTES FOR TEACHERS" /
  "NOTES FOR THE TEACHER" front-matter block set at 24pt -- bigger than the chapter's
  real headings at 14pt. The THE-less form ("NOTES FOR TEACHERS") did not match the old
  exclusion pattern (it required "FOR THE TEACHER(S)"), so it won "largest bold text in
  the chapter" outright and was returned as the chapter's ONLY section: not a smaller
  list, an empty one wearing a section's shape. Fixed by widening the pattern, and
  because a table caption at that book's real heading size ("TABLE 1.3 PER CAPITA INCOME
  OF SELECT STATES") wraps to a second line the caption's own exclusion does not reach
  ("OF SELECT STATES" alone), a second fix propagates a noise line's exclusion onto a
  wrapped continuation line the same way a real heading's own wrap is later merged back
  together.

* Political Science's "Political Parties" chapter draws its own chapter title at 65pt,
  well above its real headings at 20pt -- exercised correctly already (the title is
  passed in and excluded by the substring check), kept here as a regression against that
  path breaking silently alongside the fix above.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ingest.book import _sections_by_boldness, extract_chapter, read_text

FIXTURES = Path(__file__).parent / "fixtures" / "regression"
DEVELOPMENT_PDF = FIXTURES / "sst_economics_development.pdf"
POLITICAL_PARTIES_PDF = FIXTURES / "sst_polsci_political_parties.pdf"
INDUSTRIALISATION_PDF = FIXTURES / "sst_history_age_of_industrialisation.pdf"


@pytest.mark.skipif(not DEVELOPMENT_PDF.exists(), reason="regression fixture not present")
def test_a_front_matter_note_bigger_than_every_real_heading_is_not_the_whole_chapter():
    text = read_text(DEVELOPMENT_PDF)
    sections = _sections_by_boldness(DEVELOPMENT_PDF, text, "Development")

    titles = [s.title for s in sections]
    assert len(sections) > 1, (
        "the chapter's real headings must survive, not just its front-matter note: "
        f"got {titles!r}"
    )
    assert not any("NOTES FOR" in t.upper() for t in titles)
    assert any("PUBLIC FACILITIES" in t.upper() for t in titles)
    assert any("INCOME AND OTHER CRITERIA" in t.upper() for t in titles)
    # A table caption's wrapped second line ('OF SELECT STATES', 'COUNTRIES', ...) must
    # not survive as a bare section of its own once the caption's own first line is
    # excluded.
    assert not any(t.upper() in ("COUNTRIES", "OF SELECT STATES") for t in titles)


@pytest.mark.skipif(not POLITICAL_PARTIES_PDF.exists(), reason="regression fixture not present")
def test_a_chapter_title_drawn_bigger_than_every_real_heading_is_still_excluded():
    text = read_text(POLITICAL_PARTIES_PDF)
    sections = _sections_by_boldness(POLITICAL_PARTIES_PDF, text, "Political Parties")

    titles = [s.title for s in sections]
    assert len(sections) >= 5, f"got {titles!r}"
    assert "Political Parties" not in titles
    assert any("reformed" in t.lower() for t in titles)
    assert any("national parties" in t.lower() for t in titles)


@pytest.mark.skipif(not INDUSTRIALISATION_PDF.exists(), reason="regression fixture not present")
def test_a_bare_heading_matching_the_chapter_number_does_not_hide_the_rest():
    """History numbers its own headings independently of the chapter (a bare '1', or a
    decimal subsection under it, per BOOK_NUMBERED_SECTION's own docstring) -- never tied
    to the file's own chapter number. extract_sections's pattern is scoped to THIS
    chapter's number, `{chapter}\\.\\d+`, so on the real chapter 4 file it silently matched
    heading 4's own subsections ('4.1 The Early Entrepreneurs', '4.2 Where Did the Workers
    Come From?') by coincidence -- a wrong but non-empty result that skipped the boldness
    fallback outright, leaving the chapter's other five real top-level headings (bare '1'
    through '6') without a section at all. bare_headings=True skips extract_sections for
    History entirely, so this must find every real heading, not just the two that happen
    to share the chapter's own number.
    """
    extract = extract_chapter(
        INDUSTRIALISATION_PDF, number=4, name="04-the-age-of-industrialisation.pdf",
        title="The Age of Industrialisation", bare_headings=True,
    )
    numbers = {s.number for s in extract.sections}
    assert {"1", "2", "3", "4", "5", "6"} <= numbers, (
        f"missing top-level headings not tied to the chapter's own number 4: {numbers!r}"
    )
    titles = [s.title for s in extract.sections]
    assert any("Factories Come Up" == t for t in titles)
    assert any("The Early Entrepreneurs" == t for t in titles)
