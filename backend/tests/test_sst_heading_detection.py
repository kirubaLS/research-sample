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
GLOBAL_WORLD_PDF = FIXTURES / "sst_history_making_of_a_global_world.pdf"
real_global_world = pytest.mark.skipif(not GLOBAL_WORLD_PDF.exists(), reason="regression fixture not present")
MONEY_AND_CREDIT_PDF = FIXTURES / "sst_economics_money_and_credit.pdf"
real_money_and_credit = pytest.mark.skipif(not MONEY_AND_CREDIT_PDF.exists(), reason="regression fixture not present")


@pytest.mark.skipif(not DEVELOPMENT_PDF.exists(), reason="regression fixture not present")
def test_a_front_matter_note_bigger_than_every_real_heading_is_not_the_whole_chapter():
    """Only 3 of this chapter's 7 real headings are drawn bold ("How to Compare...",
    "Income and Other Criteria", "Public Facilities") -- the other 4 ("What Development
    Promises...", "Income and Other Goals", "National Development", "Sustainability of
    Development") are plain text at a larger-than-body size, the same convention
    _sections_by_boldness's own docstring already describes for this book. The bold pass
    alone used to return those first 3 as a non-empty, plausible-looking result and stop
    there -- correct on their own, but silently missing more than half the chapter,
    exactly the shape test_a_lone_section... in test_ingest_book.py exists to catch when
    it collapses all the way to one. This is that same failure at a smaller scale: not
    zero real headings surviving, not one, but three real ones standing in for seven."""
    text = read_text(DEVELOPMENT_PDF)
    sections = _sections_by_boldness(DEVELOPMENT_PDF, text, "Development")

    titles = [s.title for s in sections]
    assert len(sections) == 7, f"got {titles!r}"
    assert not any("NOTES FOR" in t.upper() for t in titles)
    assert any("PUBLIC FACILITIES" in t.upper() for t in titles)
    assert any("INCOME AND OTHER CRITERIA" in t.upper() for t in titles)
    assert any("WHAT DEVELOPMENT PROMISES" in t.upper() for t in titles)
    assert any(t.upper() == "NATIONAL DEVELOPMENT" for t in titles)
    assert any("SUSTAINABILITY OF DEVELOPMENT" in t.upper() for t in titles)
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


@real_global_world
def test_a_running_page_banner_does_not_split_the_section_it_interrupts():
    """The real chapter "The Making of a Global World" prints '2  The Nineteenth Century
    (1815-1914)' exactly once in the extracted text -- not as a real heading, but as a
    running page-top banner glued to a page break, immediately followed by 'Reprint
    2026-27' and the book's own title. Confirmed by position: it appears in the text
    AFTER '2.1 A World Economy Takes Shape' has already started, which a real book would
    never print out of numeric order. Taking it as a heading anyway invented a phantom
    '2' section that stole the back half of 2.1's real content (a food-price discussion
    that plainly continues 2.1's own topic)."""
    extract = extract_chapter(
        GLOBAL_WORLD_PDF, number=3, name="jess303.pdf",
        title="The Making of a Global World", bare_headings=True,
    )
    numbers = [s.number for s in extract.sections]
    assert "2" not in numbers, "the page banner must not become its own section"
    a_world_economy = next(s for s in extract.sections if s.number == "2.1")
    assert a_world_economy.end - a_world_economy.start > 4000, (
        "2.1's real content must not have been cut short by the banner"
    )


@real_global_world
def test_a_number_the_book_itself_reuses_for_two_headings_keeps_both():
    """The same real chapter prints '2.4' twice, for two different real headings --
    'Rinderpest, or the Cattle Plague' and, later, 'Indentured Labour Migration from
    India' -- confirmed as genuine text in the book, not a transcription slip in the
    topic list this was checked against. The old dedup (a bare set of numbers already
    seen) could not tell a real second heading apart from a running header repeating the
    first, and silently dropped the second heading's content into the first's span."""
    extract = extract_chapter(
        GLOBAL_WORLD_PDF, number=3, name="jess303.pdf",
        title="The Making of a Global World", bare_headings=True,
    )
    titles_by_number = {s.number: s.title for s in extract.sections}
    assert titles_by_number.get("2.4") == "Rinderpest, or the Cattle Plague"
    assert "Indentured Labour Migration from India" in titles_by_number.values(), (
        "the second, differently-titled '2.4' must keep its own section, not vanish "
        "into the first one's"
    )


@real_money_and_credit
def test_a_bold_pass_that_finds_only_a_few_of_many_real_headings_is_not_trusted_alone():
    """Only 2 of this chapter's ~15 real headings ("Loan Activities of Banks", "Formal
    Sector Credit in India") are drawn bold; the rest ("Currency", "Deposits with Banks",
    "Formal and Informal Credit: Who gets what?", ...) are plain text at a larger size.
    The bold pass alone returns those 2 as a plausible, non-empty result and used to stop
    there -- correct as far as they go, but standing in for a chapter more than seven
    times their combined length. Not every real heading is recovered yet this way (see
    the module docstring on _sections_by_boldness for the open gap: a book that MIXES
    bold and plain headings within one chapter still needs both signals merged, not one
    chosen over the other) -- this only proves the sparse, bold-only answer is no longer
    trusted on its own.
    """
    text = read_text(MONEY_AND_CREDIT_PDF)
    sections = _sections_by_boldness(MONEY_AND_CREDIT_PDF, text, "Money and Credit")
    titles = [s.title for s in sections]
    assert len(sections) > 2, f"got {titles!r}"
