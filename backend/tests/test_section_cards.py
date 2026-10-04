"""Section cards and the one-call card read: built from the real Social Science book map,
no paid API called."""

from __future__ import annotations

import json

import pytest

from app.classify.section_cards import load_cards, rank_sections, tokens
from app.config import get_settings
from app.curriculum.book_map import major_headings
from tests.test_major_topics import CHAPTER_ID, GEO, _minerals_chunks


def build():
    from scripts.build_section_cards import build as _build

    return _build()


@pytest.fixture
def cards_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "topic_depth_cap", True)
    monkeypatch.setattr(get_settings(), "topic_major_only_document", True)


class _C:
    pass


class _Judge:
    """Answers the card read with ``section``/``quotes``; the whole-chapter reads with
    ``fallback``. Records every call."""

    def __init__(self, section, quotes, fallback="4.1"):
        self.section, self.quotes, self.fallback, self.calls = section, quotes, fallback, []

    def pick_from_cards(self, stem, label, cards, excerpt, with_tier=False):
        self.calls.append(("cards", cards, excerpt))
        c = _C()
        c.section, c.quotes, c.also, c.rationale, c.answer = (
            self.section, self.quotes, [], "card read", "")
        return c

    def pick_from_document(self, stem, label, headings, document, candidates=None,
                           mode="answer", exclude=None, with_tier=False):
        self.calls.append(("document", mode))
        c = _C()
        c.section, c.quote, c.quotes, c.also, c.rationale, c.answer = (
            self.fallback, "", [], [], "whole chapter", "")
        return c


def _stem_and_quote():
    """A question made of a real sentence of section 4.2, and that sentence."""
    chunk = next(c for c in _minerals_chunks() if c.section_number == "4.2" and len(c.text) > 200)
    sentence = chunk.text.split(". ")[0][:160]
    return f"Explain: {sentence}", sentence


def _choose(judge, stem, card_mode=True):
    from app.classify.topic import choose_topic

    return choose_topic(
        stem, CHAPTER_ID, "Minerals and Energy Resources", _minerals_chunks(),
        major_headings(GEO, 2), judge, major=(GEO, 2), card_mode=card_mode,
    )


def test_every_major_topic_of_every_social_science_chapter_has_a_card():
    data, problems = build()
    assert problems == []
    assert {c.split(".")[1] for c in data} == {"HIST", "GEO", "POL", "ECO"}
    assert len(data) == 22
    for code, entry in data.items():
        assert set(entry["cards"]) == set(major_headings(code, 2)), code


def test_the_committed_cards_are_current():
    data, _ = build()
    from app.classify.section_cards import CARDS_FILE

    assert json.loads(json.dumps(data)) == json.loads(CARDS_FILE.read_text())


def test_a_chapters_cards_cost_a_fraction_of_its_text():
    data, _ = build()
    for code, entry in data.items():
        assert entry["card_tokens"] <= 0.30 * entry["full_tokens"], code
    assert sum(e["card_tokens"] for e in data.values()) < 0.2 * sum(
        e["full_tokens"] for e in data.values())


def test_bm25_ranks_the_section_that_uses_a_rare_name_first():
    chunks = [(c.section_number, c.text) for c in _minerals_chunks() if c.section_number]
    pool = [c for c in _minerals_chunks() if c.section_number == "4.2" and len(c.text) > 200]
    sentence = pool[0].text.split(". ")[0][:160]
    assert rank_sections(sentence, chunks)[0].startswith("4")


def test_load_cards_is_none_for_a_chapter_without_cards():
    assert load_cards("X.SCI.CARBON") is None and load_cards(GEO)


def test_a_grounded_card_read_is_one_call_and_never_reads_the_chapter(cards_on):
    stem, sentence = _stem_and_quote()
    judge = _Judge("4.2", [sentence])
    pick = _choose(judge, stem)
    assert pick.section == "4.2" and pick.verified is True and pick.agreed
    assert [c[0] for c in judge.calls] == ["cards"]
    assert judge.card_hits == 1 and judge.card_escalations == 0
    _, cards, excerpt = judge.calls[0]
    assert "[0]" in cards and "[4.2]" in cards, "every topic has a card"
    assert tokens(excerpt) < 4500, "only the top two sections' text is sent"


def test_a_quote_that_is_not_in_the_book_escalates_to_the_whole_chapter(cards_on):
    stem, _ = _stem_and_quote()
    judge = _Judge("4.2", ["A sentence the model made up that is nowhere in the chapter."])
    pick = _choose(judge, stem)
    assert [c[0] for c in judge.calls][0] == "cards" and "document" in {c[0] for c in judge.calls}
    assert pick.section == "4.1" and judge.card_escalations == 1


def test_a_quote_under_another_section_than_the_one_named_escalates(cards_on):
    stem, sentence = _stem_and_quote()
    judge = _Judge("2.3", [sentence])
    _choose(judge, stem)
    assert "document" in {c[0] for c in judge.calls} and judge.card_escalations == 1


def test_a_card_read_with_no_quote_escalates(cards_on):
    stem, _ = _stem_and_quote()
    judge = _Judge("4.2", [])
    _choose(judge, stem)
    assert "document" in {c[0] for c in judge.calls}


def test_card_mode_off_never_reads_cards(cards_on):
    stem, sentence = _stem_and_quote()
    judge = _Judge("4.2", [sentence])
    _choose(judge, stem, card_mode=False)
    assert {c[0] for c in judge.calls} == {"document"}


def test_the_setting_defaults_off():
    assert get_settings().topic_card_mode is False
