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

from app.ingest.book import (
    _NOT_A_HEADING,
    _locate_known_sections,
    _sections_by_boldness,
    extract_chapter,
    read_text,
)

FIXTURES = Path(__file__).parent / "fixtures" / "regression"
DEVELOPMENT_PDF = FIXTURES / "sst_economics_development.pdf"
POLITICAL_PARTIES_PDF = FIXTURES / "sst_polsci_political_parties.pdf"
INDUSTRIALISATION_PDF = FIXTURES / "sst_history_age_of_industrialisation.pdf"
GLOBAL_WORLD_PDF = FIXTURES / "sst_history_making_of_a_global_world.pdf"
real_global_world = pytest.mark.skipif(not GLOBAL_WORLD_PDF.exists(), reason="regression fixture not present")
MONEY_AND_CREDIT_PDF = FIXTURES / "sst_economics_money_and_credit.pdf"
real_money_and_credit = pytest.mark.skipif(not MONEY_AND_CREDIT_PDF.exists(), reason="regression fixture not present")
SECTORS_PDF = FIXTURES / "sst_economics_sectors.pdf"
real_sectors = pytest.mark.skipif(not SECTORS_PDF.exists(), reason="regression fixture not present")
CONSUMER_RIGHTS_PDF = FIXTURES / "sst_economics_consumer_rights.pdf"
real_consumer_rights = pytest.mark.skipif(not CONSUMER_RIGHTS_PDF.exists(), reason="regression fixture not present")
GLOBALISATION_PDF = FIXTURES / "sst_economics_globalisation.pdf"
real_globalisation = pytest.mark.skipif(not GLOBALISATION_PDF.exists(), reason="regression fixture not present")
RESOURCES_DEVELOPMENT_PDF = FIXTURES / "sst_geography_resources_and_development.pdf"
real_resources_development = pytest.mark.skipif(
    not RESOURCES_DEVELOPMENT_PDF.exists(), reason="regression fixture not present"
)


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
    # 11, not 7: the chapter has real sub-headings ("Average Income", "Human Development
    # Report") beyond its 7 major ones, at yet another size level multi_size now also
    # recognises. Not asserted as an exact upper bound elsewhere in this file on purpose --
    # what matters is that none of the garbage this fix specifically had to clean up
    # (overlapping fake-bold draws, a table caption's wrapped tail) survives, checked below.
    assert len(sections) == 11, f"got {titles!r}"
    assert "HUMAN DEVELOPMENT REPORT" in titles, (
        "a fake-bold overlap ('HUMAN' x4, 'HUMAN DEVELOPMENT', 'REPOR' x4, 'REPORT') must "
        "collapse into one real heading, not survive as several fragments"
    )
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
def test_a_chapter_with_three_real_heading_sizes_keeps_all_of_them():
    """Only 2 of this chapter's 19 real headings ("Loan Activities of Banks", "Formal
    Sector Credit in India") are drawn bold; the rest print at two other plain,
    larger-than-body sizes -- 18pt for a named case study ("Cheque Payments", "A House
    Loan", "Grameen Bank of Bangladesh", ...) and 12pt for a finer level ("Currency",
    "Deposits with Banks", "Formal and Informal Credit: Who gets what?"). The bold pass
    alone used to return those 2 as a plausible, non-empty result and stop there; the
    size-based pass alone used to take only its own single largest size and discard the
    other two real levels. _sections_by_boldness's ``multi_size`` combines every real
    size cohort instead of picking one, which is what actually recovers all 19."""
    text = read_text(MONEY_AND_CREDIT_PDF)
    sections = _sections_by_boldness(MONEY_AND_CREDIT_PDF, text, "Money and Credit")
    titles = [s.title for s in sections]
    assert len(sections) == 19, f"got {titles!r}"
    assert "Currency" in titles and "Cheque Payments" in titles and "LOAN ACTIVITIES OF BANKS" in titles
    # A running header repeating the chapter's own title on every page ('De moc ra tic
    # Polit ics', letter-spaced by the page design) must not survive as a heading now
    # that more than one size cohort is let through -- confirmed as a real regression
    # against Political Parties before the repeat-count filter was added.
    assert not any("De moc ra tic" in t or "Polit ics" in t for t in titles)


@real_sectors
def test_a_noise_phrase_split_across_its_own_wrap_is_still_excluded():
    """"LET'S WORK THESE OUT" is already an excluded phrase, but this chapter draws it
    wrapped across two separate lines ('LET'S WORK THESE' / 'OUT') -- the exclusion check
    on each raw line before merging never sees the whole phrase, only after the two are
    joined back into one heading. Checked again post-merge for exactly this gap."""
    text = read_text(SECTORS_PDF)
    sections = _sections_by_boldness(SECTORS_PDF, text, "Sectors of the Indian Economy")
    titles = [s.title for s in sections]
    assert len(sections) == 14, f"got {titles!r}"
    assert not any("LET" in t.upper() for t in titles)
    assert "Kanta" in titles and "Kamal" in titles


@real_consumer_rights
def test_a_full_chapter_of_mixed_case_and_plain_headings_is_recovered():
    text = read_text(CONSUMER_RIGHTS_PDF)
    sections = _sections_by_boldness(CONSUMER_RIGHTS_PDF, text, "Consumer Rights")
    titles = [s.title for s in sections]
    assert len(sections) == 15, f"got {titles!r}"
    assert "THE CONSUMER IN THE MARKETPLACE" in titles
    assert "Where should consumers go to get justice?" in titles


def test_an_exercise_label_followed_by_its_own_section_number_is_still_excluded():
    """A real production upload of History's 'Nationalism in Europe' chapter left three
    stray book_chunk rows behind under section_number '9': 'Discuss 1.9', 'Write In Brief
    1.11', 'Project 1.12'. _NOT_A_HEADING already excludes the bare words 'DISCUSS',
    'WRITE IN BRIEF' and 'PROJECT', but its trailing-number chapter.section label (the
    same 'N.M' shape a real numbered heading carries) was never accounted for, so a line
    that pairs the exclusion word with its own number sailed through as a fake heading."""
    for text in ("Discuss 1.9", "Write In Brief 1.11", "Project 1.12", "Activity 4.2"):
        assert _NOT_A_HEADING.match(text), text
    # A real heading that merely starts with a similar word must not be swept up.
    assert not _NOT_A_HEADING.match("Discussing the Treaty of Versailles")


@real_globalisation
def test_a_boxed_example_laid_out_ahead_of_its_own_heading_does_not_drop_every_section_after_it():
    """A shared, monotonically-advancing search cursor used to assume every heading's own
    position in ``text`` came in the same order this function's own heading list did.
    False here: this chapter's own boxed example ('Spreading of Production by an MNC')
    sits BELOW its section heading ('Production Across Countries') on the page, but
    read_text's plain text extraction lays its content out ahead of that heading. Once
    the shared cursor got past that boxed example while still looking for the heading
    above it, every real heading still to come in the chapter silently vanished -- 21
    real headings collapsed to 9, not just the one out of order. All 21 must survive.
    ('Spreading of Production' / 'by an MNC' -- once two separate entries because their
    real 21.2pt gap narrowly missed the old flat 20pt wrap-merge threshold -- are one
    real two-line heading and now merge into one, see _pick_sections' own note on
    scaling that threshold with the heading's size.)"""
    text = read_text(GLOBALISATION_PDF)
    sections = _sections_by_boldness(GLOBALISATION_PDF, text, "Globalisation and the Indian Economy")
    titles = [s.title for s in sections]
    assert len(sections) == 21, f"got {titles!r}"
    assert not any("ADDITIONAL" in t.upper() for t in titles)
    assert "Spreading  of Production by an MNC" in titles
    assert "WORLD TRADE ORGANISATION" in titles
    assert "A Garment Worker" in titles
    assert "THE STRUGGLE FOR A FAIR GLOBALISATION" in titles
    # Content boundaries must stay valid (non-overlapping, strictly increasing) even
    # though this chapter's own extracted text order does not match its visual layout.
    starts = [s.start for s in sections]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)


@real_resources_development
def test_a_chapter_no_typographic_signal_can_parse_is_located_by_its_own_known_titles():
    """"Resources and Development" is the real chapter that exhausted every typographic
    signal tried: real headings span three different bold sizes, several are plain
    (non-bold) text at exactly the chapter's own body size, one ('Conservation of
    Resources') is an inline lead-in glued to its own paragraph on the same physical
    line, and a soil-profile diagram draws its own layer labels bold at a real heading's
    own size. _locate_known_sections sidesteps all of it: the chapter's own real
    headings are already known (typed from the contents page), so it matches them
    against the page's own styled spans by STRING instead of guessing which spans are
    headings from typography."""
    text = read_text(RESOURCES_DEVELOPMENT_PDF)
    titles = [
        "Resources and Development", "Development of Resources", "Sustainable development",
        "Rio de Janeiro Earth Summit, 1992", "Agenda 21", "Resource Planning",
        "Conservation of Resources", "Resource Planning in India", "Land Resources",
        "Land Utilisation", "Land Use Pattern in India",
        "Land Degradation and Conservation Measures", "Soil as a Resource",
        "Classification of Soils", "Alluvial Soils", "Black Soil",
        "Red and Yellow Soils", "Laterite Soil", "Arid Soils", "Forest Soils",
        "Soil Erosion and Soil Conservation",
    ]
    sections, missing = _locate_known_sections(RESOURCES_DEVELOPMENT_PDF, text, titles)
    assert missing == []
    assert len(sections) == 21
    # The given list types "Land Resources" before "Land Utilisation", but the book
    # genuinely prints "LAND UTILISATION" first -- renumbered by where each was actually
    # found, not the order given, so the real book order must survive here.
    numbers_by_title = {s.title: s.number for s in sections}
    assert int(numbers_by_title["Land Utilisation"]) < int(numbers_by_title["Land Resources"])
    # Content boundaries must stay valid (non-overlapping, strictly increasing).
    starts = [s.start for s in sections]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)
