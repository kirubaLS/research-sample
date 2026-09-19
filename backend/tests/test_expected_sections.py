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

# The real section list for jess304.pdf ("The Age of Industrialisation"), exactly as
# given for the whole Social Science curriculum -- History's own headings are numbered
# independently of the chapter (see bare_headings), which is why these numbers are bare
# '1'..'6' and decimal subsections under them, not '4.1' scoped to this being chapter 4.
INDUSTRIALISATION_SECTIONS = [
    {"number": "1", "title": "Before the Industrial Revolution"},
    {"number": "1.1", "title": "The Coming Up of the Factory"},
    {"number": "1.2", "title": "The Pace of Industrial Change"},
    {"number": "2", "title": "Hand Labour and Steam Power"},
    # Not in the user's own hand-typed list for this chapter -- found only by running the
    # real extraction against the real file, which is exactly why this endpoint checks a
    # chapter against verify_against_toc rather than trusting a typed list blindly: a
    # human list can omit a real heading the same way an extractor can invent a fake one.
    {"number": "2.1", "title": "Life of the Workers"},
    {"number": "3", "title": "Industrialisation in the Colonies"},
    {"number": "3.1", "title": "The Age of Indian Textiles"},
    {"number": "3.2", "title": "What Happened to Weavers?"},
    {"number": "3.3", "title": "Manchester Comes to India"},
    {"number": "4", "title": "Factories Come Up"},
    {"number": "4.1", "title": "The Early Entrepreneurs"},
    {"number": "4.2", "title": "Where Did the Workers Come From?"},
    {"number": "5", "title": "The Peculiarities of Industrial Growth"},
    {"number": "5.1", "title": "Small-scale Industries Predominate"},
    {"number": "6", "title": "Market for Goods"},
]


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
    client.post("/platform/books/X.HIST/curriculum", headers=HEAD)

    client.post(
        "/platform/books/X.HIST/expected-sections", headers=HEAD,
        json={"chapters": {"1": [{"number": "1", "title": "Chapter One Heading"}]}},
    )
    second = client.post(
        "/platform/books/X.HIST/expected-sections", headers=HEAD,
        json={"chapters": {"4": INDUSTRIALISATION_SECTIONS}},
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
        assert len(source.expected_sections["4"]) == len(INDUSTRIALISATION_SECTIONS)
    finally:
        db.close()


@real_fixture
def test_a_real_chapter_verifies_clean_against_its_own_hand_typed_oracle(client, school):
    """The exact real section list the user gave for this exact real chapter file --
    proof the hand-typed oracle and the (now-fixed) bare_headings extraction actually
    agree on a real book, not just on each other's assumptions."""
    client.post("/platform/books/X.HIST/curriculum", headers=HEAD)
    client.post(
        "/platform/books/X.HIST/expected-sections", headers=HEAD,
        json={"chapters": {"4": INDUSTRIALISATION_SECTIONS}},
    )

    with open(FIXTURE, "rb") as fh:
        r = client.post(
            "/platform/books/X.HIST/chapters", headers=HEAD,
            files={"file": ("jess304.pdf", fh, "application/pdf")},
        )
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["sections"] == len(INDUSTRIALISATION_SECTIONS)
    assert body["verified_against"] is not None, (
        "a subject with a hand-typed oracle must be verified, not left unverified the "
        "way a subject with no section list at all is"
    )


@real_fixture
def test_a_chapter_missing_from_its_own_oracle_is_rejected_not_loaded_silently(client, school):
    """The whole point: an oracle that expects a section the real upload does not have
    must reject the chapter, the same way Maths already does -- not load a partial
    result and call it done."""
    client.post("/platform/books/X.HIST/curriculum", headers=HEAD)
    incomplete = [s for s in INDUSTRIALISATION_SECTIONS if s["number"] != "6"]
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
