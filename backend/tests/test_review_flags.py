"""Phase 4: review flags that mean something.

* The chapter judge cites passages by their printed number; the numbers are checked, and a
  reference string is still read as a tolerant fallback. A citation problem is a warning,
  never a confidence cap (cite_passages_by_number).
* A row is flagged for one of six reasons only, and the reason is stored on it
  (review_flag_rule).
* question_placement.reasoning is cut to 1000 characters before insert (unflagged).
"""

from __future__ import annotations

import types

import pytest

from app.classify.grounding import ground, resolve_citations
from app.classify.judge import (
    Classification,
    Evidence,
    NumberedClassification,
    NumberedScopedClassification,
    ScopedClassification,
)
from app.classify.review_rule import REASONS, ReviewInputs, reason_code, review_reasons

EVIDENCE = [
    Evidence("Print Culture", "6.2 Print Comes to India", "6.2",
             "The printing press first came to Goa with Portuguese missionaries in the mid-"
             "sixteenth century."),
    Evidence("Print Culture", "9 Print and Censorship", "9",
             "The Vernacular Press Act was passed in 1878, modelled on the Irish Press Laws."),
    Evidence("Nationalism in Europe", "5 Visualising the Nation", "5",
             "Artists in the eighteenth and nineteenth centuries represented a country as if "
             "it were a person."),
]


# --- 4.1 citations by passage number ----------------------------------------------------


@pytest.mark.parametrize("cited, refs", [
    ([1, 3], ["6.2 Print Comes to India", "5 Visualising the Nation"]),
    (["[2]", "2"], ["9 Print and Censorship"]),
    # the printed passage line, with or without its number and section
    (["[1] Print Culture -- 6.2 Print Comes to India (section 6.2)"], ["6.2 Print Comes to India"]),
    (["Print Culture -- 9 Print and Censorship (section 9)"], ["9 Print and Censorship"]),
    (["Print Culture -- 9 Print and Censorship"], ["9 Print and Censorship"]),
    # a bare reference, and a quote from one shown passage
    (["5 Visualising the Nation"], ["5 Visualising the Nation"]),
    (["the Vernacular Press Act was passed in 1878"], ["9 Print and Censorship"]),
])
def test_a_citation_resolves_to_the_passage_it_names(cited, refs):
    got, problems = resolve_citations(cited, EVIDENCE)
    assert got == refs and problems == []


@pytest.mark.parametrize("cited", [[0], [4], ["[7]"], ["Theorem 99.9"], ["press"], [True]])
def test_a_citation_of_nothing_shown_is_a_problem(cited):
    got, problems = resolve_citations(cited, EVIDENCE)
    assert got == [] and len(problems) == 1


def test_a_citation_problem_is_a_warning_never_a_confidence_cap():
    answer = NumberedClassification(
        chapter="Print Culture", curriculum_section="9", tier="Applying",
        skill_required="x", reasoning="y", evidence=[2, 9], confidence=0.92,
    )
    checked = ground(answer, EVIDENCE, known_sections={"Print Culture": {"9", "6.2"}},
                     cite_by_number=True)
    assert checked.violations == []
    assert checked.warnings == ["cited passage [9] was never shown (1-3)"]
    assert checked.classification.confidence == 0.92
    assert checked.classification.evidence == ["9 Print and Censorship"]
    assert type(checked.classification) is Classification


def test_a_scoped_answer_keeps_its_scope_signal_through_grounding():
    answer = NumberedScopedClassification(
        chapter="Print Culture", skill_required="x", reasoning="y", evidence=[1],
        confidence=0.2, no_in_scope_chapter=True,
    )
    checked = ground(answer, EVIDENCE, cite_by_number=True)
    assert isinstance(checked.classification, ScopedClassification)
    assert checked.classification.no_in_scope_chapter is True


def test_with_the_flag_off_an_invented_reference_still_caps_as_before():
    answer = Classification(chapter="Print Culture", skill_required="x", reasoning="y",
                            evidence=["Theorem 99.9"], confidence=0.9)
    checked = ground(answer, EVIDENCE)
    assert checked.violations and checked.classification.confidence == 0.4
    assert checked.warnings == []


def _live_judge(numbered: bool, answer: dict):
    from app.classify import anthropic_judge

    sent = []

    class _Messages:
        def parse(self, **kwargs):
            sent.append(kwargs)
            return types.SimpleNamespace(
                parsed_output=kwargs["output_format"](**answer), usage=None)

    judge = anthropic_judge.AnthropicJudge.__new__(anthropic_judge.AnthropicJudge)
    judge.client = types.SimpleNamespace(messages=_Messages())
    judge.model, judge.output_config, judge.passage_chars = "m", None, 1200
    judge.known_sections, judge.violations, judge.section_mapper = None, [], None
    judge.calls = judge.input_tokens = judge.output_tokens = judge.cache_read_tokens = 0
    judge.cite_by_number, judge.citation_warnings = numbered, []
    return judge, sent


def test_the_live_judge_asks_for_numbers_and_returns_references():
    from app.classify.judge import CITE_NOTE

    judge, sent = _live_judge(True, {
        "chapter": "Print Culture", "skill_required": "x", "reasoning": "y",
        "evidence": [2, 5], "confidence": 0.8,
    })
    result = judge.classify("q", EVIDENCE)
    assert sent[0]["output_format"] is NumberedClassification
    assert sent[0]["system"].endswith(CITE_NOTE)
    assert "[2] Print Culture -- 9 Print and Censorship (section 9)" in sent[0]["messages"][0]["content"]
    assert result.evidence == ["9 Print and Censorship"] and result.confidence == 0.8
    assert judge.citation_warnings == [("q", ["cited passage [5] was never shown (1-3)"])]
    assert judge.violations == []
    judge.classify("q", EVIDENCE, scoped=True)
    assert sent[1]["output_format"] is NumberedScopedClassification


def test_with_the_flag_off_the_live_judge_is_unchanged():
    from app.classify.judge import SYSTEM

    judge, sent = _live_judge(False, {
        "chapter": "Print Culture", "skill_required": "x", "reasoning": "y",
        "evidence": ["9 Print and Censorship"], "confidence": 0.8,
    })
    judge.classify("q", EVIDENCE)
    assert sent[0]["output_format"] is Classification and sent[0]["system"] == SYSTEM


# --- 4.2 the six reasons ----------------------------------------------------------------


@pytest.mark.parametrize("inputs, reasons", [
    (ReviewInputs(), []),
    (ReviewInputs(judge_failed=True), ["judge_failed"]),
    (ReviewInputs(cross_scope=True), ["cross_scope"]),
    (ReviewInputs(blueprint_overruled=True), ["blueprint_overruled"]),
    (ReviewInputs(family_unsettled=True), ["family"]),
    (ReviewInputs(family_blocked=True), ["family"]),
    (ReviewInputs(chapter_confidence=0.6, chapters_shown=2), ["low_confidence"]),
    # one chapter to choose from: a low confidence is not a doubt about the chapter
    (ReviewInputs(chapter_confidence=0.6, chapters_shown=1), []),
    (ReviewInputs(chapter_confidence=0.7, chapters_shown=3), []),
    (ReviewInputs(topic_source="judge", topic_section="4.2", retrieval_section="4.1"),
     ["topic_differs"]),
    # answerability verified the judge's section: the disagreement is settled
    (ReviewInputs(topic_source="judge", topic_section="4.2", retrieval_section="4.1",
                  topic_verified=True), []),
    # a parent and its own sub-section are not a disagreement
    (ReviewInputs(topic_source="judge", topic_section="4.1", retrieval_section="4.1.2"), []),
    (ReviewInputs(topic_source="judge", topic_section="4.2", retrieval_section="4.2",
                  topic_verified=False), ["topic_unverified"]),
    (ReviewInputs(topic_source="retrieval", topic_section="4.2"), ["topic_unverified"]),
    (ReviewInputs(topic_source="none"), []),
])
def test_a_row_is_flagged_for_the_seven_reasons_only(inputs, reasons):
    assert review_reasons(inputs) == reasons


def test_the_stored_reason_is_whole_codes_in_priority_order_within_the_column():
    every = list(REASONS)
    code = reason_code(every)
    assert len(code) <= 64 and code.startswith("judge_failed,cross_scope,blueprint_overruled")
    assert all(part in REASONS for part in code.split(","))
    assert reason_code([]) is None


def test_the_map_step_uses_the_rule_and_a_provisional_topic_is_no_doubt(monkeypatch):
    from app.api.marks import _map_review
    from app.classify.topic import TopicPick

    pick = TopicPick("4.2", "h", "judge", False, "4.1", "r", verified=None)
    on = types.SimpleNamespace(review_flag_rule=True)
    assert _map_review(on, pick, False, family_unsettled=False, old=False) == {
        "needs_review": True, "review_reason": "topic_differs"}
    assert _map_review(on, pick, True, family_unsettled=False, old=True) == {
        "needs_review": False, "review_reason": None}
    assert _map_review(on, pick, True, family_unsettled=True, old=True)["review_reason"] == "family"
    off = types.SimpleNamespace(review_flag_rule=False)
    assert _map_review(off, pick, False, family_unsettled=False, old=True) == {"needs_review": True}


def test_the_pipeline_records_the_chapter_judges_own_confidence_and_choice():
    from tests.test_judge_options import _PlainJudge, _run

    out = _run(_PlainJudge(), [("q", "printing press books", 1.0)],
               scope_of=lambda qid: {"Print Culture", "Nationalism in Europe"})
    q = out.questions[0]
    assert q.judge_confidence == 0.9 and q.chapters_shown >= 1


def test_a_skipped_chapter_judge_has_no_confidence_to_doubt():
    from app.classify.pipeline import PassOptions
    from tests.test_judge_options import BOOK_OF, _PlainJudge, _run

    out = _run(_PlainJudge(), [("q", "coal mines", 1.0)],
               scope_of=lambda qid: {"Minerals and Energy"},
               options=PassOptions(book_of=BOOK_OF, skip_single_chapter=True))
    assert out.questions[0].judge_confidence is None and out.questions[0].chapters_shown == 0


def test_every_flagged_row_of_a_place_run_carries_a_reason(client, school, book, monkeypatch):
    from sqlalchemy import select

    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import QuestionPlacement
    from tests.test_topic_column import _place, _question, _stub_judges

    monkeypatch.setattr(get_settings(), "review_flag_rule", True)
    aid, qid = _question(client, school)
    _stub_judges(monkeypatch, topic="13.2")
    status, error = _place(school, aid)
    assert status == "succeeded", error
    db = SessionLocal()
    try:
        rows = db.scalars(select(QuestionPlacement).where(QuestionPlacement.question_id == qid))
        for row in rows:
            if row.needs_review:
                assert row.review_reason, "a flag without a reason"
                assert set(row.review_reason.split(",")) <= set(REASONS)
            else:
                assert row.review_reason is None
    finally:
        db.close()


# --- 4.3 reasoning fits its column -------------------------------------------------------


def test_reasoning_is_cut_to_1000_characters_before_insert(client, school, book):
    from app.db import SessionLocal
    from app.models import QuestionPlacement
    from tests.test_topic_column import _question

    _, qid = _question(client, school)
    db = SessionLocal()
    try:
        row = QuestionPlacement(question_id=qid, reasoning="x" * 1500, confidence=0.5)
        db.add(row)
        db.commit()
        assert len(db.get(QuestionPlacement, row.id).reasoning) == 1000
        row.reasoning = "short"
        assert row.reasoning == "short"
    finally:
        db.close()


# --- the offline replay -------------------------------------------------------------------


def _replay(text, confidence=0.9, source="model", cross_scope=None):
    from scripts.replay_review_flags import replay_row

    return replay_row(text, confidence=confidence, source=source, cross_scope=cross_scope)


def test_the_replay_reads_each_stored_condition():
    r = _replay("asks for X Topic 4.2 (Non-Conventional): quoted. 2 families of Minerals "
                "draw on section 4.2; the narrowest was taken and a person should settle it")
    assert r["family"] == "yes" and r["verdict"] == "flagged"
    r = _replay("the reading model's answer for this question was invalid (x) -- needs a person.")
    assert r["judge_failed"] == "yes" and r["low_confidence"] == "no"
    r = _replay("y Topic 4.2 (h): r. No section of the chapter answers this question from its "
                "own text; the section that comes closest was kept.")
    assert r["topic_unverified"] == "yes"
    r = _replay("y Topic 4.2 (h): the topic judge could not be asked; the chapter decided")
    assert r["topic_unverified"] == "yes" and r["topic_differs"] == "no"
    r = _replay("y Topic 4.2 (h): r.", cross_scope=True)
    assert r["cross_scope"] == "yes"
    r = _replay("y Topic 4.2 (h): r.", source="blueprint")
    assert r["blueprint_overruled"] == "yes" and r["verdict"] == "flagged"


def test_the_replay_says_unknown_when_an_input_was_not_stored():
    # below 0.7: whether more than one chapter was shown is not stored
    assert _replay("y Topic 4.2 (h): r.", confidence=0.5)["low_confidence"] == "unknown"
    # a blueprint row lost the judge's own confidence (and is flagged as overruled anyway)
    assert _replay("y", source="blueprint")["low_confidence"] == "unknown"
    # a disagreement note without answerability's verdict
    r = _replay("y Topic 4.2 (h): r. Retrieval within the chapter pointed at section 4.1 (h).")
    assert r["topic_differs"] == "unknown" and r["verdict"] == "unknown"
    # ...and a clean, confident row is known not to be flagged
    assert _replay("y Topic 4.2 (h): r.")["verdict"] == "not flagged"


def test_the_replay_reads_map_rows_and_settled_rows():
    r = _replay("lexical retrieval, margin 0.010. Topic 4.2 (h): provisional: the classify step "
                "queued behind this map decides the topic", confidence=0.03)
    assert r["verdict"] == "not flagged"
    r = _replay("Not applied: a person settled this question. y Topic 4.2 (h): r.", confidence=0.1)
    assert r["verdict"] == "not flagged"


def test_the_replay_script_is_read_only(client, school, book, capsys):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import QuestionPlacement
    from scripts import replay_review_flags
    from tests.test_topic_column import _question

    aid, qid = _question(client, school)
    db = SessionLocal()
    try:
        db.add(QuestionPlacement(question_id=qid, confidence=0.95, needs_review=True,
                                 reasoning="y Topic 13.2 (Mean of Grouped Data): r."))
        db.commit()
        before = db.scalars(select(QuestionPlacement).where(
            QuestionPlacement.question_id == qid)).all()
        before = [(r.id, r.needs_review, r.review_reason) for r in before]
    finally:
        db.close()
    assert replay_review_flags.main(["--assessment", aid]) == 0
    out = capsys.readouterr().out
    assert "READ-ONLY" in out
    assert "TODAY flagged 1; NEW RULE flagged 0, not flagged 1, unknown 0" in out
    db = SessionLocal()
    try:
        after = [(r.id, r.needs_review, r.review_reason) for r in db.scalars(select(
            QuestionPlacement).where(QuestionPlacement.question_id == qid))]
        assert after == before
    finally:
        db.close()
