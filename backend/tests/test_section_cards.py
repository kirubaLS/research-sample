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


def test_every_major_topic_of_every_listed_chapter_has_a_card():
    data, problems = build()
    assert problems == []
    assert {c.split(".")[1] for c in data} == {"HIST", "GEO", "POL", "ECO", "SCI"}
    assert len(data) == 35
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
    assert load_cards("X.MATH.REAL") is None and load_cards(GEO) and load_cards("X.SCI.CARBON")


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


# --- margin, fuzzy quotes and counted signals --------------------------------------------


def test_the_number_of_sections_shown_follows_the_margin():
    from app.classify.section_cards import margin, sections_to_show

    assert sections_to_show(0.9) == 1 and sections_to_show(0.5) == 1
    assert sections_to_show(0.3) == 2 and sections_to_show(0.25) == 2
    assert sections_to_show(0.1) == 3
    assert margin({"a": 10.0, "b": 4.0, "c": 1.0}) == 0.6 and margin({"a": 3.0}) == 1.0


def test_a_clear_margin_sends_one_section_and_an_ambiguous_one_sends_three(cards_on):
    from app.classify.section_cards import margin, score_sections

    stem, sentence = _stem_and_quote()
    chunks = [(c.section_number, c.text) for c in _minerals_chunks() if c.section_number]
    judge = _Judge("4.2", [sentence])
    _choose(judge, stem)
    shown = judge.calls[0][2].count("## SECTION")
    assert shown == (1 if margin(score_sections(stem, chunks)) >= 0.5 else 2)
    vague = "Explain the importance of resources for the development of the country."
    judge = _Judge("4.2", ["nothing"])
    _choose(judge, vague)
    assert judge.calls[0][2].count("## SECTION") == 3


def test_quote_overlap_accepts_a_close_copy_and_rejects_an_invented_sentence():
    from app.classify.section_cards import quote_overlap

    text = ("lignite is a low grade brown coal it is soft and has a high moisture content "
            "its principal reserves in india are in tamil nadu")
    assert quote_overlap("lignite is a low grade brown coal", text) == 1.0
    assert quote_overlap("lignite is a low grade form of brown coal", text) < 0.85, \
        "an extra word in the middle is not silently forgiven"
    reworded = "lignite is a low grade brown coal it is soft and has high moisture content"
    assert quote_overlap(reworded, text) >= 0.85
    assert quote_overlap("coal was the first fuel ever mined in the british isles", text) < 0.4
    assert quote_overlap("too short", text) == 0.0


def _reword(sentence):
    words = sentence.split()
    assert len(words) > 8
    return " ".join(words[:3] + words[4:])              # one word dropped


def test_a_lightly_reworded_quote_is_accepted_when_the_other_signals_agree(cards_on, monkeypatch):
    import types

    import app.classify.topic as topic

    stem, sentence = _stem_and_quote()
    monkeypatch.setattr(topic, "locate", lambda *a, **k: types.SimpleNamespace(
        section="4.2", evidence=[]))                     # retrieval within the chapter agrees
    judge = _Judge("4.2", [_reword(sentence)])
    pick = _choose(judge, stem)
    assert pick.section == "4.2" and "closely matched" in pick.rationale
    assert [c[0] for c in judge.calls] == ["cards"] and judge.card_tiers == {"accept": 1}


def test_a_reworded_quote_with_retrieval_pointing_elsewhere_is_reviewed_by_the_full_read(
    cards_on, monkeypatch,
):
    import types

    import app.classify.topic as topic

    stem, sentence = _stem_and_quote()
    monkeypatch.setattr(topic, "locate", lambda *a, **k: types.SimpleNamespace(
        section="4.1", evidence=[]))
    judge = _Judge("4.2", [_reword(sentence)])
    _choose(judge, stem)
    assert judge.card_tiers == {"review": 1} and "document" in {c[0] for c in judge.calls}


def test_card_signals_count_what_can_be_observed():
    from app.classify.topic import CARD_ACCEPT, CARD_SIGNALS, card_signals

    full, flags = card_signals("4.2", "4.2", True, ["4.2", "4.1"], ["4.2"], "4.2", "4.2")
    assert full == CARD_SIGNALS == 7 and all(flags.values())
    # a close copy instead of a verbatim quote: one short, still accepted
    p, flags = card_signals("4.2", "4.2", False, ["4.2"], ["4.2"], "4.2", None)
    assert p == 6 and not flags["quote_verbatim"] and p >= CARD_ACCEPT
    # BM25 had the wrong first section but retrieval agrees with the judge: accepted
    p, _ = card_signals("4.2", "4.2", True, ["4.1", "4.2"], ["4.1", "4.2"], "4.2", None)
    assert p == 6 >= CARD_ACCEPT
    # BM25 and retrieval both point elsewhere: two short, not accepted
    p, flags = card_signals("4.2", "4.2", True, ["4.1", "4.2"], ["4.1", "4.2"], "4.1", None)
    assert p == 5 < CARD_ACCEPT and not flags["bm25_agrees"] and not flags["retrieval_agrees"]
    # signals with nothing to say are no evidence against
    assert card_signals("4.2", "4.2", True, ["4.2"], ["4.2"], None, None)[0] == 7


def test_a_book_term_under_another_section_escalates_even_with_a_good_quote(cards_on, monkeypatch):
    import app.classify.topic as topic

    stem, sentence = _stem_and_quote()
    monkeypatch.setattr(topic, "term_vote", lambda votes: "1")
    judge = _Judge("4.2", [sentence])
    _choose(judge, stem)
    assert "document" in {c[0] for c in judge.calls}
    assert judge.card_tiers == {"terms_disagree": 1}


def test_outcomes_are_tallied_by_tier(cards_on):
    stem, sentence = _stem_and_quote()
    judge = _Judge("4.2", [sentence])
    _choose(judge, stem)
    _choose(judge, stem)
    assert judge.card_tiers == {"accept": 2}


def test_dense_fusion_blends_normalised_scores_and_ranks_best_first():
    from scripts.eval_dense_retrieval import dense_scores, fuse, normalise, position

    assert normalise({"a": 10.0, "b": 0.0, "c": 5.0}) == {"a": 1.0, "b": 0.0, "c": 0.5}
    bm25 = {"1": 9.0, "2": 8.0, "3": 1.0}
    dense = {"1": 0.1, "2": 0.9, "3": 0.2}
    assert fuse(bm25, dense, 0.0)[0] == "1" and fuse(bm25, dense, 1.0)[0] == "2"
    assert position(["1", "2", "3"], {"3"}) == 2 and position(["1"], {"9"}) == 1
    scored = dense_scores([1.0, 0.0], [("a", [1.0, 0.0]), ("a", [0.0, 1.0]), ("b", [0.0, 1.0])])
    assert scored["a"] > scored["b"]
