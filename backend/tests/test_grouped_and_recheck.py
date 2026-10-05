"""Grouped chapter-judge calls and the reordered re-ask. Every judge is a stub."""

from __future__ import annotations

from app.classify.judge import Classification
from app.classify.pipeline import PassOptions, place_paper
from app.ingest.probe import LexicalIndex


class _Chunk:
    def __init__(self, cid, text, node):
        self.chunk_id = self.id = cid
        self.text = text
        self.reference = cid
        self.node_id = node
        self.bucket = "T"
        self.embedding = None
        self.section_number = None


NAMES = {"G1": "Circles", "H1": "Constructions"}


def _corpus():
    chunks = [
        _Chunk("g1a", "tangent circle radius perpendicular point of contact", "G1"),
        _Chunk("g1b", "circle tangent radius theorem proof chord", "G1"),
        _Chunk("h1a", "construct triangle compass ruler tangent circle construction", "H1"),
        _Chunk("h1b", "construction of tangent to a circle from an external point", "H1"),
    ]
    return chunks + [_Chunk(f"pad{i}", f"unrelated filler topic {i}", f"X{i}") for i in range(20)]


def _cls(chapter, confidence=0.9):
    return Classification(chapter=chapter, curriculum_section=None, tier=None,
                          skill_required="", reasoning="stub", evidence=[],
                          confidence=confidence, alternative_chapter=None)


QUESTIONS = [("q1", "tangent circle radius perpendicular", 1.0),
             ("q2", "circle tangent chord theorem proof", 1.0),
             ("q3", "construct tangent circle external point", 1.0)]


def _run(judge, questions=QUESTIONS, **options):
    return place_paper(
        questions, [LexicalIndex(_corpus()), LexicalIndex(_corpus())], judge,
        chapter_of=NAMES.get, unit_of=NAMES.get, section_of=lambda r: None,
        evidence_passages=4, evidence_chapters=2, options=PassOptions(**options),
    )


class _Grouped:
    def __init__(self, fail_group=False, skip=None):
        self.many, self.single, self.fail_group, self.skip = [], [], fail_group, skip

    def classify_many(self, items):
        self.many.append([i["question"] for i in items])
        if self.fail_group:
            raise RuntimeError("boom")
        return [RuntimeError("missing") if i["question"] == self.skip else _cls("Circles")
                for i in items]

    def classify(self, question, evidence, *, scoped=False, examples=None):
        self.single.append(question)
        return _cls("Circles")


def test_grouped_calls_ask_several_questions_at_once():
    judge = _Grouped()
    out = _run(judge, group_size=2)
    assert judge.many == [["tangent circle radius perpendicular",
                           "circle tangent chord theorem proof"],
                          ["construct tangent circle external point"]]
    assert judge.single == [] and {q.chapter for q in out.questions} == {"Circles"}


def test_a_question_the_group_missed_is_asked_alone():
    judge = _Grouped(skip="circle tangent chord theorem proof")
    _run(judge, group_size=3)
    assert judge.single == ["circle tangent chord theorem proof"]


def test_a_failed_group_falls_back_to_single_calls():
    judge = _Grouped(fail_group=True)
    out = _run(judge, group_size=3)
    assert len(judge.single) == 3 and len(out.questions) == 3


def test_group_size_one_never_groups():
    judge = _Grouped()
    _run(judge)
    assert judge.many == [] and len(judge.single) == 3


# --- the reordered re-ask ----------------------------------------------------------------


class _Scripted:
    """Answers from a script: the first call, then each re-ask."""

    def __init__(self, answers):
        self.answers, self.orders = list(answers), []

    def classify(self, question, evidence, *, scoped=False, examples=None):
        self.orders.append([e.reference for e in evidence])
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return _cls(*a)


ONE = [("q", "tangent circle radius construction external point", 1.0)]


def test_a_confident_answer_is_never_re_asked():
    judge, log = _Scripted([("Circles", 0.95)]), {}
    _run(judge, ONE, recheck=True, recheck_log=log)
    assert len(judge.orders) == 1 and log == {}


def test_a_stable_low_confidence_answer_is_kept_as_it_was():
    judge, log = _Scripted([("Circles", 0.6), ("Circles", 0.7), ("Circles", 0.7)]), {}
    out = _run(judge, ONE, recheck=True, recheck_log=log)
    assert out.questions[0].chapter == "Circles" and not log["q"]["unstable"]
    assert len(judge.orders) == 3
    assert judge.orders[1] != judge.orders[0], "the passages were reordered"


def test_the_majority_chapter_wins_when_the_re_asks_disagree_with_the_first():
    judge, log = _Scripted([("Circles", 0.6), ("Constructions", 0.8),
                            ("Constructions", 0.8)]), {}
    out = _run(judge, ONE, recheck=True, recheck_log=log)
    assert out.questions[0].chapter == "Constructions" and log["q"]["changed"]


def test_an_answer_nobody_repeats_is_capped_for_review():
    judge, log = _Scripted([("Circles", 0.75), ("Constructions", 0.8),
                            ("Circles", 0.8)]), {}
    # Circles twice of three: that IS a majority, so build a three-way split instead
    judge = _Scripted([("Circles", 0.75), ("Constructions", 0.8), (None, 0.8)])
    out = _run(judge, ONE, recheck=True, recheck_log=log)
    q = out.questions[0]
    assert q.chapter == "Circles" and q.judge_confidence == 0.4 and log["q"]["unstable"]


def test_a_failing_re_ask_is_no_vote():
    judge, log = _Scripted([("Circles", 0.6), RuntimeError("x"), RuntimeError("y")]), {}
    out = _run(judge, ONE, recheck=True, recheck_log=log)
    assert out.questions[0].chapter == "Circles" and log["q"]["votes"] == ["Circles"]


def test_a_batched_judge_is_never_re_asked():
    judge = _Scripted([("Circles", 0.6)])
    judge.batched = True
    _run(judge, ONE, recheck=True)
    assert len(judge.orders) == 1


# --- the real judge's grouped call, against a fake client --------------------------------


def test_the_anthropic_judge_groups_questions_into_one_request_and_maps_answers_by_index():
    from types import SimpleNamespace

    from app.classify.anthropic_judge import AnthropicJudge, _Answer, _Many
    from app.classify.judge import Evidence

    sent = {}

    class Messages:
        def parse(self, **kw):
            sent.update(kw)
            answers = [
                _Answer(index=1, chapter="B", skill_required="s", reasoning="r", confidence=0.8),
                _Answer(index=0, chapter="A", skill_required="s", reasoning="r", confidence=0.9),
                # index 2 is missing on purpose
            ]
            usage = SimpleNamespace(input_tokens=10, output_tokens=5,
                                    cache_read_input_tokens=0, cache_creation_input_tokens=0)
            return SimpleNamespace(parsed_output=_Many(answers=answers), usage=usage)

    judge = AnthropicJudge("key", model="claude-sonnet-5")
    judge.client = SimpleNamespace(messages=Messages())

    def ev(chapter):
        return [Evidence(chapter=chapter, reference="r", section="1", text="t")]

    out = judge.classify_many([
        {"question": "one", "evidence": ev("A")},
        {"question": "two", "evidence": ev("B")},
        {"question": "three", "evidence": ev("C")},
    ])
    assert [getattr(o, "chapter", None) for o in out[:2]] == ["A", "B"]
    assert isinstance(out[2], Exception), "a question the answer skipped comes back as an error"
    assert judge.calls == 1 and judge.input_tokens == 10
    prompt = sent["messages"][0]["content"]
    assert "### QUESTION 0" in prompt and "### QUESTION 2" in prompt
    assert "INDEPENDENT questions" in sent["system"]
