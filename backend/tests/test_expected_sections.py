"""A hand-typed section oracle for a book whose own contents page cannot supply one.

Only Maths publishes a real chapter.section list on its contents page (`parse_toc`) --
every other CBSE Class X subject's prelims stops at chapter titles, so every chapter of
Geography, Political Science, Economics and History has only ever been checked by
`verify_structure`'s heuristics: real, but unable to say a heading is MISSING, only that
what was found looks internally consistent. Every heading-detection bug found this
session (a front-matter note outscoring real headings, a table caption's wrapped second
line, a coincidental chapter-number match hiding five real headings) would have loaded
silently under that weaker check. `POST .../expected-sections` lets a person paste in the
book's own real section list once, by hand, and from then on a chapter upload for that
subject is checked with `verify_against_toc` -- the same hard oracle Maths already gets.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings

KEY = "platform-test-key-abc"
HEAD = {"X-Platform-Key": KEY}

FIXTURE = Path(__file__).parent / "fixtures" / "regression" / "sst_history_age_of_industrialisation.pdf"
real_fixture = pytest.mark.skipif(not FIXTURE.exists(), reason="regression fixture not present")
PARTIES_FIXTURE = Path(__file__).parent / "fixtures" / "regression" / "sst_polsci_political_parties.pdf"
real_parties_fixture = pytest.mark.skipif(not PARTIES_FIXTURE.exists(), reason="regression fixture not present")
GLOBAL_WORLD_FIXTURE = Path(__file__).parent / "fixtures" / "regression" / "sst_history_making_of_a_global_world.pdf"
real_global_world_fixture = pytest.mark.skipif(
    not GLOBAL_WORLD_FIXTURE.exists(), reason="regression fixture not present"
)
DEVELOPMENT_FIXTURE = Path(__file__).parent / "fixtures" / "regression" / "sst_economics_development.pdf"
SECTORS_FIXTURE = Path(__file__).parent / "fixtures" / "regression" / "sst_economics_sectors.pdf"
MONEY_AND_CREDIT_FIXTURE = Path(__file__).parent / "fixtures" / "regression" / "sst_economics_money_and_credit.pdf"
CONSUMER_RIGHTS_FIXTURE = Path(__file__).parent / "fixtures" / "regression" / "sst_economics_consumer_rights.pdf"
ECO_FIXTURES = [DEVELOPMENT_FIXTURE, SECTORS_FIXTURE, MONEY_AND_CREDIT_FIXTURE, CONSUMER_RIGHTS_FIXTURE]
real_eco_fixtures = pytest.mark.skipif(
    not all(f.exists() for f in ECO_FIXTURES), reason="regression fixture not present"
)
GEOGRAPHY_CH1_FIXTURE = (
    Path(__file__).parent / "fixtures" / "regression" / "sst_geography_resources_and_development.pdf"
)
real_geography_ch1_fixture = pytest.mark.skipif(
    not GEOGRAPHY_CH1_FIXTURE.exists(), reason="regression fixture not present"
)

# The real section list for jess304.pdf ("The Age of Industrialisation"), read from the
# same data scripts/load_expected_sections.py actually loads -- one source of truth,
# checked against the real file rather than duplicated by hand a second time here.
# Imported lazily (see the tests that use these) because scripts.load_expected_sections
# imports app.api.books, which touches app.db's engine at import time -- unsafe at test
# module collection, before conftest's _tmp_db fixture has set YAADHUM_DATABASE_URL.
def _expected_sections():
    from scripts.load_expected_sections import EXPECTED_SECTIONS

    return EXPECTED_SECTIONS


@pytest.fixture(autouse=True)
def _enable_platform():
    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = KEY
    yield
    settings.platform_admin_key = before


def test_a_subject_with_no_curriculum_is_refused(client):
    r = client.post(
        "/platform/books/X.NOTHING/expected-sections", headers=HEAD,
        json={"chapters": {"1": [{"number": "1", "title": "Whatever"}]}},
    )
    assert r.status_code == 422
    assert "curriculum first" in r.json()["detail"]


def test_setting_one_chapter_does_not_erase_another(client, school):
    industrialisation_sections = _expected_sections()["X.HIST"]["4"]
    client.post("/platform/books/X.HIST/curriculum", headers=HEAD)

    client.post(
        "/platform/books/X.HIST/expected-sections", headers=HEAD,
        json={"chapters": {"1": [{"number": "1", "title": "Chapter One Heading"}]}},
    )
    second = client.post(
        "/platform/books/X.HIST/expected-sections", headers=HEAD,
        json={"chapters": {"4": industrialisation_sections}},
    )
    assert second.status_code == 201
    assert second.json()["chapters_set"] == ["4"]

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import BookSource

    db = SessionLocal()
    try:
        source = db.scalar(
            select(BookSource).where(
                BookSource.subject_code == "X.HIST",
                BookSource.curriculum_version == "CBSE-2026-27",
            )
        )
        assert "1" in source.expected_sections, "the first call's chapter must survive"
        assert len(source.expected_sections["4"]) == len(industrialisation_sections)
    finally:
        db.close()


@real_fixture
def test_a_real_chapter_verifies_clean_against_its_own_hand_typed_oracle(client, school):
    """The exact real section list the user gave for this exact real chapter file --
    proof the hand-typed oracle and the (now-fixed) bare_headings extraction actually
    agree on a real book, not just on each other's assumptions."""
    industrialisation_sections = _expected_sections()["X.HIST"]["4"]
    client.post("/platform/books/X.HIST/curriculum", headers=HEAD)
    client.post(
        "/platform/books/X.HIST/expected-sections", headers=HEAD,
        json={"chapters": {"4": industrialisation_sections}},
    )

    with open(FIXTURE, "rb") as fh:
        r = client.post(
            "/platform/books/X.HIST/chapters", headers=HEAD,
            files={"file": ("jess304.pdf", fh, "application/pdf")},
        )
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["sections"] == len(industrialisation_sections)
    assert body["verified_against"] is not None, (
        "a subject with a hand-typed oracle must be verified, not left unverified the "
        "way a subject with no section list at all is"
    )


@real_fixture
def test_a_chapter_missing_from_its_own_oracle_is_rejected_not_loaded_silently(client, school):
    """The whole point: an oracle that expects a section the real upload does not have
    must reject the chapter, the same way Maths already does -- not load a partial
    result and call it done."""
    industrialisation_sections = _expected_sections()["X.HIST"]["4"]
    client.post("/platform/books/X.HIST/curriculum", headers=HEAD)
    incomplete = [s for s in industrialisation_sections if s["number"] != "6"]
    incomplete.append({"number": "7", "title": "A Section This Book Does Not Have"})
    client.post(
        "/platform/books/X.HIST/expected-sections", headers=HEAD,
        json={"chapters": {"4": incomplete}},
    )

    with open(FIXTURE, "rb") as fh:
        r = client.post(
            "/platform/books/X.HIST/chapters", headers=HEAD,
            files={"file": ("jess304.pdf", fh, "application/pdf")},
        )
    assert r.status_code == 422
    assert "missing section 7" in r.json()["detail"]
    assert "section 6 is not in the contents page" in r.json()["detail"]


@real_geography_ch1_fixture
def test_locate_known_sections_is_refused_without_an_expected_list(client, school):
    """Never a silent fallback to the usual typographic detection -- see
    upload_chapter's own note on ``locate_known_sections``. Requested for a chapter with
    no expected section list set, it must refuse outright, not quietly extract by
    typography as if the flag had not been passed. Placed here, before every other test
    in this file that calls ``load_expected_sections.main()``: ``client`` is
    session-scoped (one shared database for the whole test run), and ``main()`` with no
    args loads EVERY subject's data at once, X.GEO included, not just whichever subject
    a given test is nominally about -- the first such call anywhere in this file would
    otherwise seed X.GEO's own expected sections before this negative case ever got to
    run, no matter where among the X.GEO-specific tests it was placed."""
    client.post("/platform/books/X.GEO/curriculum", headers=HEAD)
    # A BookSource row must exist for chapter upload to get past its own "upload the
    # contents page first" check before reaching the locate_known_sections check this
    # test is actually about -- set for chapter 2, deliberately NOT chapter 1, so
    # chapter 1's own expected-section list stays unset, which is the actual case under
    # test.
    client.post(
        "/platform/books/X.GEO/expected-sections", headers=HEAD,
        json={"chapters": {"2": [{"number": "1", "title": "placeholder"}]}},
    )

    with open(GEOGRAPHY_CH1_FIXTURE, "rb") as fh:
        r = client.post(
            "/platform/books/X.GEO/chapters?locate_known_sections=true", headers=HEAD,
            files={"file": ("jess101.pdf", fh, "application/pdf")},
        )
    assert r.status_code == 422
    assert "locate_known_sections" in r.json()["detail"]


@real_fixture
@real_parties_fixture
def test_the_loader_scripts_full_dataset_verifies_both_proven_chapters(client, school):
    """scripts.load_expected_sections is what actually ships this to a real deployment
    (`python -m scripts.load_expected_sections`, no dry-run) -- this runs its own
    EXPECTED_SECTIONS data, unmodified, through the same set_expected_sections path the
    HTTP endpoint uses, then re-uploads both chapters it claims are proven and checks
    both come back verified clean. Anyone editing that data (adding a subject once its
    PDF is checked, say) gets this test failing the moment the new entry disagrees with
    a real file, rather than a silent bad oracle reaching a real deployment."""
    from scripts.load_expected_sections import main as load_all

    client.post("/platform/books/X.HIST/curriculum", headers=HEAD)
    client.post("/platform/books/X.POL/curriculum", headers=HEAD)
    load_all([])

    with open(FIXTURE, "rb") as fh:
        history = client.post(
            "/platform/books/X.HIST/chapters", headers=HEAD,
            files={"file": ("jess304.pdf", fh, "application/pdf")},
        )
    assert history.status_code == 201, history.json()
    assert history.json()["verified_against"] is not None

    with open(PARTIES_FIXTURE, "rb") as fh:
        parties = client.post(
            "/platform/books/X.POL/chapters", headers=HEAD,
            files={"file": ("jess404.pdf", fh, "application/pdf")},
        )
    assert parties.status_code == 201, parties.json()
    assert parties.json()["verified_against"] is not None
    assert parties.json()["sections"] == len(_expected_sections()["X.POL"]["4"])


@real_global_world_fixture
def test_the_loader_scripts_data_verifies_the_chapter_with_a_real_duplicate_number(client, school):
    """Chapter 3 ("The Making of a Global World") is the hardest case in the loaded
    dataset: it has a real, book-printed duplicate ('2.4' twice, for two different
    headings) and it originally surfaced a running-page-banner bug in the extractor
    itself (see app.ingest.book's BOOK_NUMBERED_SECTION dedup comment). This proves the
    fixed extractor and the disambiguated oracle ('2.4-2') actually agree on the real
    file end to end, the same way the other proven chapters do."""
    from scripts.load_expected_sections import main as load_all

    client.post("/platform/books/X.HIST/curriculum", headers=HEAD)
    load_all([])

    with open(GLOBAL_WORLD_FIXTURE, "rb") as fh:
        r = client.post(
            "/platform/books/X.HIST/chapters", headers=HEAD,
            files={"file": ("jess303.pdf", fh, "application/pdf")},
        )
    assert r.status_code == 201, r.json()
    assert r.json()["verified_against"] is not None
    assert r.json()["sections"] == len(_expected_sections()["X.HIST"]["3"])


@real_eco_fixtures
def test_the_loader_scripts_data_verifies_all_four_economics_chapters(client, school):
    """The four Economics chapters that forced the multi-size fix in the first place
    (see app.ingest.book's _sections_by_boldness docstring) -- each proven individually
    in test_sst_heading_detection.py, this proves the SAME data the loader script ships
    verifies clean end to end for all four together, the way a real deployment would
    actually load them."""
    from scripts.load_expected_sections import main as load_all

    client.post("/platform/books/X.ECO/curriculum", headers=HEAD)
    load_all([])

    for chapter_number, filename, fixture in [
        ("1", "jess201.pdf", DEVELOPMENT_FIXTURE),
        ("2", "jess202.pdf", SECTORS_FIXTURE),
        ("3", "jess203.pdf", MONEY_AND_CREDIT_FIXTURE),
        ("5", "jess205.pdf", CONSUMER_RIGHTS_FIXTURE),
    ]:
        with open(fixture, "rb") as fh:
            r = client.post(
                "/platform/books/X.ECO/chapters", headers=HEAD,
                files={"file": (filename, fh, "application/pdf")},
            )
        assert r.status_code == 201, (chapter_number, r.json())
        assert r.json()["verified_against"] is not None
        assert r.json()["sections"] == len(_expected_sections()["X.ECO"][chapter_number])


@real_geography_ch1_fixture
def test_the_loader_scripts_data_verifies_geography_by_locating_known_sections(client, school):
    """Geography's own real headings cannot be told apart from a diagram caption, a
    table cell or the chapter's own body prose by boldness, size or colour -- every
    typographic attempt tried and reverted (see app.ingest.book's _sections_by_boldness
    docstring). Proven a different way instead: the chapter's own known real headings,
    already typed from the contents page, located directly in the text by
    _locate_known_sections and passed with ?locate_known_sections=true. This proves the
    loader's own data does the same end to end a real deployment would."""
    from scripts.load_expected_sections import main as load_all

    client.post("/platform/books/X.GEO/curriculum", headers=HEAD)
    load_all([])

    with open(GEOGRAPHY_CH1_FIXTURE, "rb") as fh:
        r = client.post(
            "/platform/books/X.GEO/chapters?locate_known_sections=true", headers=HEAD,
            files={"file": ("jess101.pdf", fh, "application/pdf")},
        )
    assert r.status_code == 201, r.json()
    assert r.json()["verified_against"] == "contents page (by known titles)"
    assert r.json()["sections"] == len(_expected_sections()["X.GEO"]["1"])
