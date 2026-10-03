"""Phase 1.5-1.7: balanced candidates across books, the cross-scope second pass, and the
single-chapter skip with the tier from the topic judge's answer read. Every judge here is
a stub; no paid API is called."""

from __future__ import annotations

import pytest

from app.classify.judge import Classification, ScopedClassification
from app.classify.pipeline import PassOptions, place_paper
from app.ingest.probe import LexicalIndex


class _Chunk:
    def __init__(self, cid, text, node, section=None):
        self.chunk_id = self.id = cid
        self.text = text
        self.reference = cid
        self.node_id = node
        self.bucket = "T"
        self.embedding = None
        self.section_number = section


NAMES = {"H1": "Print Culture", "H2": "Nationalism in Europe", "G1": "Minerals and Energy",
         "P1": "Political Parties"}
BOOK_OF = {"Print Culture": "X.HIST", "Nationalism in Europe": "X.HIST",
           "Minerals and Energy": "X.GEO", "Political Parties": "X.POL"}
UNITS = {label: book for label, book in BOOK_OF.items()}


def _corpus():
    chunks = [
        _Chunk("h1a", "printing press books readers printing press pamphlets books", "H1"),
        _Chunk("h1b", "printing press spread books among readers printing", "H1"),
        _Chunk("h1c", "books printing censorship press readers", "H1"),
        _Chunk("h2a", "printing press nationalism books readers unification", "H2"),
        _Chunk("h2b", "books printing nation state press readers", "H2"),
        _Chunk("g1a", "coal mines books of geology minerals", "G1"),
        _Chunk("p1a", "political party functions elections", "P1"),
    ]
    chunks += [_Chunk(f"pad{i}", f"unrelated filler topic {i}", f"X{i}") for i in range(20)]
    return chunks


def _run(judge, questions, **kw):
    return place_paper(
        questions, [LexicalIndex(_corpus())], judge,
        chapter_of=NAMES.get, unit_of=UNITS.get, section_of=lambda r: None,
        evidence_passages=4, evidence_chapters=1, **kw,
    )


class _Recorder:
    """Records the chapters each call was shown; answers with ``answer(evidence, scoped)``."""

    def __init__(self, answer=None):
        self.seen: list[tuple[set[str], bool]] = []
        self.answer = answer

    def classify(self, question, evidence, **kw):
        scoped = kw.get("scoped", False)
        self.seen.append(({e.chapter for e in evidence}, scoped))
        if self.answer is not None:
            return self.answer(evidence, scoped)
        return Classification(chapter=sorted({e.chapter for e in evidence})[0], tier="Applying",
                              skill_required="x", reasoning="y", confidence=0.9)


class _PlainJudge(_Recorder):
    """A judge with the original signature: classify(question, evidence) only. Any new
    keyword reaching it with the flags off would raise TypeError."""

    def classify(self, question, evidence):  # noqa: D102
        return super().classify(question, evidence)


# --- 1.5 balanced candidates ----------------------------------------------------------------


def test_without_balancing_a_weak_book_can_be_crowded_out():
    judge = _PlainJudge()
    _run(judge, [("q", "printing press books coal", 1.0)])
    assert "Minerals and Energy" not in judge.seen[0][0]


def test_balanced_candidates_show_every_books_best_chapter():
    judge = _Recorder()
    _run(judge, [("q", "printing press books coal", 1.0)],
         options=PassOptions(book_of=BOOK_OF, balanced=True))
    shown = judge.seen[0][0]
    assert "Minerals and Energy" in shown, "the Geography book's best chapter must be shown"
    assert "Print Culture" in shown


def test_balancing_stays_inside_the_questions_scope():
    judge = _Recorder()
    _run(judge, [("q", "printing press books coal", 1.0)],
         scope_of=lambda qid: {"Print Culture", "Nationalism in Europe"},
         options=PassOptions(book_of=BOOK_OF, balanced=True))
    assert judge.seen[0][0] <= {"Print Culture", "Nationalism in Europe"}


# --- 1.6 cross-scope ------------------------------------------------------------------------


def _scoped_answer(no_fit_first=True, second_chapter="Political Parties"):
    def answer(evidence, scoped):
        if scoped:
            return ScopedClassification(
                chapter=sorted({e.chapter for e in evidence})[0], tier="Applying",
                skill_required="x", reasoning="weak", confidence=0.2,
                no_in_scope_chapter=no_fit_first,
            )
        return Classification(chapter=second_chapter, tier="Applying", skill_required="x",
                              reasoning="parties", confidence=0.85)
    return answer


def test_a_question_no_in_scope_chapter_answers_is_placed_outside_and_marked():
    judge = _Recorder(_scoped_answer())
    out = _run(judge, [("q", "printing press political party functions", 1.0)],
               scope_of=lambda qid: {"Print Culture"},
               options=PassOptions(cross_scope=True))
    q = out.questions[0]
    assert q.chapter == "Political Parties" and q.cross_scope
    assert [scoped for _, scoped in judge.seen] == [True, False]
    assert "outside" in q.reasoning


def test_an_in_scope_fit_is_never_re_asked():
    judge = _Recorder(_scoped_answer(no_fit_first=False))
    out = _run(judge, [("q", "printing press books", 1.0)],
               scope_of=lambda qid: {"Print Culture"},
               options=PassOptions(cross_scope=True))
    assert len(judge.seen) == 1 and not out.questions[0].cross_scope
    assert out.questions[0].chapter == "Print Culture"


def test_a_second_pass_landing_back_in_scope_is_not_cross_scope():
    judge = _Recorder(_scoped_answer(second_chapter="Print Culture"))
    out = _run(judge, [("q", "printing press political party functions", 1.0)],
               scope_of=lambda qid: {"Print Culture"},
               options=PassOptions(cross_scope=True))
    assert out.questions[0].chapter == "Print Culture" and not out.questions[0].cross_scope


def test_with_the_flag_off_the_judge_is_called_exactly_as_before():
    judge = _PlainJudge()
    out = _run(judge, [("q", "printing press political party functions", 1.0)],
               scope_of=lambda qid: {"Print Culture"})
    assert not out.questions[0].cross_scope


def test_an_undeclared_scope_is_never_asked_the_scoped_question():
    """No title, no teacher scope, no syllabus: nothing was declared, so nothing can be
    left; inference narrowing the paper later is not a declaration either."""
    judge = _Recorder()
    _run(judge, [("q", "printing press books", 1.0)],
         options=PassOptions(cross_scope=True))
    assert all(not scoped for _, scoped in judge.seen)


# --- 1.7 single-chapter skip -------------------------------------------------------------


def test_a_single_chapter_scope_skips_the_chapter_judge():
    judge = _PlainJudge()
    out = _run(judge, [("q", "coal mines", 1.0)], scope_of=lambda qid: {"Minerals and Energy"},
               options=PassOptions(book_of=BOOK_OF, skip_single_chapter=True))
    q = out.questions[0]
    assert judge.seen == [], "no chapter judge call"
    assert q.chapter == "Minerals and Energy" and q.chapter_judge_skipped
    assert q.confidence == 1.0 and not q.needs_review
    assert q.tier is None, "the tier comes from the topic judge, later"


def test_a_declared_paper_wide_single_chapter_skips_too():
    judge = _PlainJudge()
    out = _run(judge, [("q", "coal mines", 1.0)], scope={"Minerals and Energy"},
               options=PassOptions(skip_single_chapter=True))
    assert judge.seen == [] and out.questions[0].chapter_judge_skipped


def test_a_multi_chapter_scope_still_asks_the_judge():
    judge = _PlainJudge()
    out = _run(judge, [("q", "printing press books", 1.0)],
               scope_of=lambda qid: {"Print Culture", "Nationalism in Europe"},
               options=PassOptions(skip_single_chapter=True))
    assert len(judge.seen) == 1 and not out.questions[0].chapter_judge_skipped


def test_with_the_flag_off_a_single_chapter_scope_still_asks_the_judge():
    judge = _PlainJudge()
    _run(judge, [("q", "coal mines", 1.0)], scope_of=lambda qid: {"Minerals and Energy"})
    assert len(judge.seen) == 1


# --- the tier from the topic judge's answer read --------------------------------------------


class _TierJudge:
    """A whole-chapter topic judge that names a tier on the answer read."""

    def __init__(self, tier):
        self.tier, self.calls = tier, []

    def pick_from_document(self, stem, chapter_label, headings, document, candidates=None,
                           mode="answer", exclude=None, with_tier=False):
        self.calls.append((mode, with_tier))

        class _Choice:
            pass

        c = _Choice()
        c.section, c.quote, c.rationale = "1", "", "coal is a mineral fuel"
        c.answer, c.quotes, c.also = "", [], []
        c.tier = self.tier if with_tier else None
        return c


TOPIC_CHUNKS = [
    _Chunk("t1", "Coal is the most abundantly available fossil fuel in the country.", "G1", "1"),
    _Chunk("t2", "Solar energy is a renewable source.", "G1", "2"),
]


@pytest.mark.parametrize("given, expected", [
    ("Applying", "Applying"),
    ("Remembering & Understanding", "Remembering & Understanding"),
    ("applying", None),               # a paraphrase of a tier is not a tier
    ("Easy", None),
    (None, None),
])
def test_the_answer_read_names_a_grounded_tier_when_asked(given, expected):
    from app.classify.topic import choose_topic

    judge = _TierJudge(given)
    pick = choose_topic("Where is coal found?", "G1", "Minerals and Energy", TOPIC_CHUNKS,
                        {"1": "Coal", "2": "Solar"}, judge, want_tier=True)
    assert pick.tier == expected
    assert judge.calls[0] == ("answer", True)
    assert all(not tiered for mode, tiered in judge.calls[1:]), "only the answer read is asked"


def test_without_asking_no_tier_is_requested():
    from app.classify.topic import choose_topic

    judge = _TierJudge("Applying")
    pick = choose_topic("Where is coal found?", "G1", "Minerals and Energy", TOPIC_CHUNKS,
                        {"1": "Coal", "2": "Solar"}, judge)
    assert pick.tier is None and all(not tiered for _, tiered in judge.calls)


def test_the_live_topic_judge_sends_the_tier_schema_only_on_a_tiered_answer_read():
    import types

    from app.classify import topic

    sent = []

    class _Messages:
        def parse(self, **kwargs):
            sent.append(kwargs)
            return types.SimpleNamespace(parsed_output=None, usage=None)

    judge = topic.TopicJudge.__new__(topic.TopicJudge)
    judge.client = types.SimpleNamespace(messages=_Messages())
    judge.model, judge.output_config = "m", None
    judge.calls = judge.input_tokens = judge.output_tokens = judge.cache_read_tokens = 0
    judge.pick_from_document("q", "c", {"1": "a"}, "doc", mode="answer", with_tier=True)
    judge.pick_from_document("q", "c", {"1": "a"}, "doc", mode="taught", with_tier=True)
    judge.pick_from_document("q", "c", {"1": "a"}, "doc", mode="answer")
    assert sent[0]["output_format"] is topic._TopicChoiceWithTier
    assert "Remembering & Understanding" in sent[0]["messages"][0]["content"]
    assert sent[1]["output_format"] is topic._TopicChoice
    assert sent[2]["output_format"] is topic._TopicChoice
    # the cached chapter prefix is identical whether or not the tier is asked
    assert sent[0]["system"] == sent[2]["system"]


def test_the_live_chapter_judge_sends_the_scoped_schema_only_when_scoped():
    import types

    from app.classify import anthropic_judge
    from app.classify.judge import SYSTEM, Evidence

    sent = []

    class _Messages:
        def parse(self, **kwargs):
            sent.append(kwargs)
            return types.SimpleNamespace(parsed_output=kwargs["output_format"](
                chapter="A", skill_required="x", reasoning="y", confidence=0.5), usage=None)

    judge = anthropic_judge.AnthropicJudge.__new__(anthropic_judge.AnthropicJudge)
    judge.client = types.SimpleNamespace(messages=_Messages())
    judge.model, judge.output_config, judge.passage_chars = "m", None, 1200
    judge.known_sections, judge.violations = None, []
    judge.calls = judge.input_tokens = judge.output_tokens = judge.cache_read_tokens = 0
    evidence = [Evidence("A", "ref", "", "text")]
    judge.classify("q", evidence)
    judge.classify("q", evidence, scoped=True)
    assert sent[0]["system"] == SYSTEM and sent[0]["output_format"] is Classification
    assert sent[1]["output_format"] is ScopedClassification
    assert "no_in_scope_chapter" in sent[1]["system"]
