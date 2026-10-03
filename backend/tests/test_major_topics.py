"""Phase 2A-2B: a major topic is at most two levels deep for capped subjects, and the
topic judge is offered only major topics -- built from the real book map of Minerals and
Energy Resources. No paid API is called."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from app.config import get_settings

GEO = "X.GEO.MINERALSENERGY"
CHAPTER_ID = "chapter-minerals"


@pytest.fixture
def cap(monkeypatch):
    monkeypatch.setattr(get_settings(), "topic_depth_cap", True)
    monkeypatch.setattr(get_settings(), "topic_major_only_document", True)


@dataclass
class _Chunk:
    id: str
    reference: str
    node_id: str
    text: str
    section_number: str | None
    bucket: str = "T"
    embedding: list | None = None
    subject_code: str = "X.GEO"


def _minerals_chunks() -> list[_Chunk]:
    """Every text chunk the book-map import makes for the chapter, from the real file."""
    from app.curriculum.book_map import REFERENCE, UNIT_FILES
    from scripts.import_book_map import _text_chunks

    data = json.loads((REFERENCE / UNIT_FILES["X.GEO"]).read_text())
    chapter = next(c for c in data if c["code"] == GEO)
    out = []
    for unit in chapter["units"]:
        for i, (ref, section, text) in enumerate(_text_chunks(GEO, unit)):
            out.append(_Chunk(f"{unit['id']}-{i}", ref[:80], CHAPTER_ID, text, section))
    return out


# --- 2A: collapse_section ----------------------------------------------------------------


def test_collapse_cuts_to_two_levels_for_capped_subjects_only(cap):
    from app.curriculum.depth import collapse_section

    assert collapse_section("X.GEO", "4.1.1") == "4.1"
    assert collapse_section("X.HIST", "3.2") == "3.2"
    assert collapse_section("X.POL", "1") == "1"
    assert collapse_section(None, "4.1.2", chapter_code=GEO) == "4.1"
    assert collapse_section("X.GEO", None) is None
    assert collapse_section("X.GEO", "none") == "none"
    # subjects not in the map keep today's behaviour
    assert collapse_section("X.MATH", "13.2.1") == "13.2.1"
    assert collapse_section("X.SCI", "9.3.7") == "9.3.7"


def test_a_box_is_never_a_topic_it_collapses_to_its_parent(cap):
    from app.curriculum.depth import collapse_section

    assert collapse_section(None, "2.1", chapter_code=GEO) == "2"
    assert collapse_section(None, "2.2.1", chapter_code=GEO) == "2.2"


def test_with_the_cap_off_nothing_is_cut(monkeypatch):
    from app.curriculum.depth import collapse_section

    monkeypatch.setattr(get_settings(), "topic_depth_cap", False)
    assert collapse_section(None, "4.1.2", chapter_code=GEO) == "4.1.2"


def test_the_per_subject_map_decides_which_subjects_are_capped(cap, monkeypatch):
    from app.curriculum.depth import collapse_section

    monkeypatch.setattr(get_settings(), "topic_max_depth_by_subject", {"X.GEO": 1})
    assert collapse_section(None, "4.1.2", chapter_code=GEO) == "4"
    assert collapse_section("X.HIST", "3.2.1") == "3.2.1"


def test_a_pick_is_capped_and_secondaries_that_collapse_onto_it_are_dropped(cap):
    from app.classify.topic import TopicPick, capped
    from app.curriculum.book_map import major_headings
    from app.curriculum.depth import collapse_section

    pick = TopicPick(
        "4.1.2", "4.1.2 Petroleum", "judge", True, "4.1.1", "oil",
        secondaries=(("4.1.4", "4.1.4 Electricity"), ("2.2.1", "2.2.1 Iron Ore"),
                     ("2.2.2", "2.2.2 Manganese"), ("4.1", "4.1 Conventional")),
    )
    out = capped(pick, lambda s: collapse_section(None, s, chapter_code=GEO),
                 major_headings(GEO, 2))
    assert out.section == "4.1" and out.heading == "4.1 Conventional Sources of Energy"
    assert out.retrieval_section == "4.1"
    assert out.secondaries == (("2.2", "2.2 Ferrous Minerals"),)
    assert out.fine_section == "4.1.2"


def test_the_chapter_judges_section_is_cut_before_it_is_grounded(cap):
    import types

    from app.classify import anthropic_judge
    from app.classify.judge import Classification, Evidence

    class _Messages:
        def parse(self, **kwargs):
            return types.SimpleNamespace(usage=None, parsed_output=Classification(
                chapter="Minerals and Energy Resources", curriculum_section="4.1.2",
                skill_required="x", reasoning="y", confidence=0.9))

    judge = anthropic_judge.AnthropicJudge.__new__(anthropic_judge.AnthropicJudge)
    judge.client = types.SimpleNamespace(messages=_Messages())
    judge.model, judge.output_config, judge.passage_chars = "m", None, 1200
    judge.known_sections = {"Minerals and Energy Resources": {"4", "4.1", "4.2"}}
    judge.violations = []
    judge.calls = judge.input_tokens = judge.output_tokens = judge.cache_read_tokens = 0
    judge.section_mapper = lambda chapter, s: s.rsplit(".", 1)[0] if s.count(".") > 1 else s
    out = judge.classify("q", [Evidence("Minerals and Energy Resources", "r", "4.1", "t")])
    assert out.curriculum_section == "4.1" and judge.violations == []


def test_judge_evidence_is_one_passage_per_major_topic(cap):
    from app.curriculum.depth import collapse_section
    from app.ingest.probe import full_chapter_evidence

    chunks = _minerals_chunks()
    for c in chunks:
        c.chunk_id = c.id
    content = [c for c in chunks if c.section_number]
    fine = full_chapter_evidence(CHAPTER_ID, content, "coal petroleum")
    major = full_chapter_evidence(
        CHAPTER_ID, content, "coal petroleum",
        section_key=lambda s: collapse_section(None, s, chapter_code=GEO),
    )
    assert any(c.section.count(".") >= 2 for c in fine)
    assert all(c.section.count(".") <= 1 for c in major)
    assert len({c.section for c in major}) == len(major)
    assert "2.1" not in {c.section for c in major}, "the box joins section 2"


# --- 2B: the topic judge sees major topics only ---------------------------------------------


def test_every_major_heading_is_selectable_even_without_text_of_its_own(cap):
    from app.curriculum.book_map import major_headings

    headings = major_headings(GEO, 2)
    assert headings["4.1"] == "4.1 Conventional Sources of Energy"
    assert "4.1" not in {c.section_number for c in _minerals_chunks()}, (
        "the case under test: 4.1 has no chunk of its own")
    assert "2.1" not in headings, "Rat-Hole Mining is a box, never a topic"
    assert headings["0"] == "0 Introduction"
    assert all(n.count(".") <= 1 for n in headings)
    assert list(headings)[:4] == ["0", "1", "2", "2.2"]


def test_the_chapter_document_renders_deeper_units_under_their_major_topic(cap):
    from app.classify.topic import chapter_document, major_chunks
    from app.curriculum.book_map import major_headings

    headings = major_headings(GEO, 2)
    chunks = major_chunks(CHAPTER_ID, GEO, _minerals_chunks(), 2)
    doc = chapter_document(chunks, headings, render_empty=True)

    start = doc.index("## SECTION 4.1  4.1 Conventional Sources of Energy")
    end = doc.index("## SECTION 4.2  ")
    block = doc[start:end]
    for sub in ("### Coal", "### Petroleum", "### Natural Gas", "### Electricity"):
        assert sub in block, sub
    assert "4.1.1" not in block and "4.1.2" not in block, "deeper numbers are never shown"
    assert "## SECTION 2.1" not in doc
    section_2 = doc[doc.index("## SECTION 2  "):doc.index("## SECTION 2.2  ")]
    assert "### Box: Rat-Hole Mining" in section_2
    assert doc.index("## SECTION 0  0 Introduction") < doc.index("## SECTION 1  ")
    iron = doc[doc.index("## SECTION 2.2  2.2 Ferrous Minerals"):doc.index("## SECTION 2.3  ")]
    assert "### Iron Ore" in iron and "### Manganese" in iron


class _Judge:
    """A whole-chapter judge answering every read with ``section``."""

    def __init__(self, section, quote=""):
        self.section, self.quote, self.calls = section, quote, []

    def pick_from_document(self, stem, chapter_label, headings, document, candidates=None,
                           mode="answer", exclude=None):
        self.calls.append((dict(headings), document, mode))

        class C:
            pass

        c = C()
        c.section, c.quote, c.rationale = self.section, self.quote, "read"
        c.answer, c.quotes, c.also = "", [self.quote] if self.quote else [], []
        return c


def _choose(judge):
    from app.classify.topic import choose_topic
    from app.curriculum.book_map import major_headings

    return choose_topic(
        "Which fossil fuel is found in the Jharia field?", CHAPTER_ID,
        "Minerals and Energy Resources", _minerals_chunks(), major_headings(GEO, 2), judge,
        major=(GEO, 2),
    )


def test_a_major_topic_with_no_text_of_its_own_can_be_chosen(cap):
    judge = _Judge("4.1")
    pick = _choose(judge)
    assert pick.section == "4.1" and pick.heading == "4.1 Conventional Sources of Energy"
    headings, document, _ = judge.calls[0]
    assert "4.1" in headings and "2.1" not in headings
    assert "## SECTION 4.1  4.1 Conventional Sources of Energy" in document


def test_a_quote_from_a_deeper_unit_lands_on_its_major_topic(cap):
    coal = next(c for c in _minerals_chunks() if c.section_number == "4.1.1")
    quote = coal.text.split(".")[0][:120]
    pick = _choose(_Judge("4", quote))
    assert pick.section == "4.1", "the quoted sentence sits under 4.1"


@pytest.mark.parametrize("answer", ["2.1", "4.1.2"])
def test_a_box_or_a_deeper_number_is_not_an_answer(cap, answer):
    pick = _choose(_Judge(answer))
    assert pick.section != answer
    assert pick.section is None or pick.section.count(".") <= 1


def test_the_major_prompts_say_sub_headings_are_never_answers():
    from app.classify import topic

    assert "most specific of the listed sections" in topic._DOCUMENT_SYSTEM_MAJOR
    assert "never itself an answer" in topic._DOCUMENT_SYSTEM_MAJOR
    assert "Section 0" in topic._DOCUMENT_SYSTEM_MAJOR
    assert "most specific of the listed sections" in topic._SYSTEM_MAJOR
    # the parent rule survives: a question spanning sub-sections of one parent goes there
    assert "answer with that parent" in topic._DOCUMENT_SYSTEM_MAJOR


@pytest.mark.parametrize("phrase", [
    "Index of Prohibited Books", "Fear of Print", "political parties", "nuclear",
    "coal mine",
])
def test_no_prompt_carries_an_example_from_the_gold_papers_chapters(phrase):
    """The gold set is one unit test on Print Culture, Minerals and Energy Resources,
    Political Parties and Globalisation; examples from those chapters would inflate it."""
    from app.classify import judge, topic
    from app.mapping import auto_resolve

    for prompt in (topic._SYSTEM, topic._DOCUMENT_SYSTEM, topic._SYSTEM_MAJOR,
                   topic._DOCUMENT_SYSTEM_MAJOR, judge.SYSTEM, auto_resolve._SYSTEM):
        assert phrase.lower() not in prompt.lower()


def test_the_live_judge_uses_the_major_prompt_only_when_asked():
    import types

    from app.classify import topic

    sent = []

    class _Messages:
        def parse(self, **kwargs):
            sent.append(kwargs)
            return types.SimpleNamespace(parsed_output=None, usage=None)

    for major in (False, True):
        judge = topic.TopicJudge.__new__(topic.TopicJudge)
        judge.client = types.SimpleNamespace(messages=_Messages())
        judge.model, judge.output_config, judge.major_only = "m", None, major
        judge.calls = judge.input_tokens = judge.output_tokens = judge.cache_read_tokens = 0
        judge.pick_from_document("q", "c", {"1": "a"}, "doc")
    assert sent[0]["system"][0]["text"] == topic._DOCUMENT_SYSTEM
    assert sent[1]["system"][0]["text"] == topic._DOCUMENT_SYSTEM_MAJOR


def test_answerability_checks_the_whole_major_topic_including_its_sub_headings(cap):
    """A sentence from 4.1.1 (Coal) verifies 4.1, because 4.1's text is its sub-sections'."""
    coal = next(c for c in _minerals_chunks() if c.section_number == "4.1.1")
    quote = coal.text.split(".")[0][:120]

    class Verifying(_Judge):
        def __init__(self):
            super().__init__("4.1", quote)
            self.checked = []

        def answerable(self, stem, chapter_label, headings, document, section, sub_sections=None):
            self.checked.append(section)

            class V:
                pass

            v = V()
            v.answerable, v.quotes, v.reason = True, [quote], "coal"
            return v

    judge = Verifying()
    pick = _choose(judge)
    assert pick.section == "4.1" and pick.verified is True
    assert judge.checked == ["4.1"]


# --- the gold fixture fits the major-topic lists --------------------------------------------


def test_every_gold_section_is_a_selectable_major_topic_of_its_chapter(cap):
    """The gold key is written at two levels; each of its sections must be one the topic
    judge is actually offered, or the target would be unreachable by construction."""
    from pathlib import Path

    from app.curriculum.book_map import major_headings

    path = Path(__file__).parent / "fixtures" / "sst_gold" / "unit_test_2026_09.json"
    gold = json.loads(path.read_text())
    assert len(gold["questions"]) == 55
    assert gold["questions"]["B/16//"] == {
        "exact": ["2.2", "2.3"], "partial": ["2"],
        "note": gold["questions"]["B/16//"]["note"],
    }
    for address, key in gold["questions"].items():
        chapter = gold["section_chapters"][address[0]]["chapter"]
        offered = major_headings(chapter, 2)
        for section in key["exact"] + key.get("partial", []):
            assert section.count(".") <= 1, (address, section)
            assert section in offered, (address, section, chapter)
