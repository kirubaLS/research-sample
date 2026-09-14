"""AnthropicPaperVisionReader.read() itself -- every page's Claude call fired
concurrently, merged into one PaperVisionReading afterwards in page order -- rather than
either the whole-paper-in-one-request shape it originally replaced (see paper_vision.py's
own docstring for why: an unbounded request size was what produced 'RequestTooLargeError:
Error code: 413' in production) or the later fully-sequential one-call-after-another shape
(replaced because a 20-page paper cost 20 round trips end to end for no reason a page's
own content required).

The real ``anthropic`` package is not installed in this sandbox (a genuine, if not fully
enforced dependency -- see pyproject.toml), so a small fake stands in for it: just enough
of ``anthropic.Anthropic`` and ``anthropic.APIStatusError`` for AnthropicPaperVisionReader
to run against. The fake is keyed by each page's own image bytes, not by call order --
pages are read concurrently now, so nothing guarantees which page's call reaches the fake
first, and a fake keyed by order would silently mismatch a scripted response to the wrong
page under real concurrency the same way a bug in production could.
"""

from __future__ import annotations

import base64
import sys
import types

import pytest


class _FakeAPIStatusError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class _FakeResponse:
    def __init__(self, parsed_output) -> None:
        self.parsed_output = parsed_output


class _FakeMessages:
    def __init__(self, scripted: dict[bytes, object]) -> None:
        self._scripted = dict(scripted)  # keyed by the page's own raw image bytes

    def parse(self, **kwargs):
        content = kwargs["messages"][0]["content"]
        raw = base64.b64decode(content[0]["source"]["data"])
        outcome = self._scripted[raw]
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeResponse(outcome)


class _FakeAnthropic:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Injects a fake `anthropic` module so `import anthropic` (both at module scope in
    AnthropicPaperVisionReader.__init__ and inside read()/​_read_page()) resolves to it."""
    fake = types.ModuleType("anthropic")
    fake.Anthropic = _FakeAnthropic
    fake.APIStatusError = _FakeAPIStatusError
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    return fake


def _reader(monkeypatch, fake_anthropic, scripted: dict[bytes, object]):
    from app.extraction import paper_vision

    reader = paper_vision.AnthropicPaperVisionReader.__new__(paper_vision.AnthropicPaperVisionReader)
    reader.client = types.SimpleNamespace(messages=_FakeMessages(scripted))
    reader.model = "claude-opus-5"
    reader.page_concurrency = 4
    return reader


def _out(*, sections=None, count=None, total=None, questions=()):
    from app.extraction.paper_vision import _DeclaredOut, _PaperOut, _QuestionOut

    return _PaperOut(
        questions=[_QuestionOut(**q) for q in questions],
        declared=_DeclaredOut(sections=sections or {}, question_count=count, total_marks=total),
    )


def test_declared_totals_are_taken_from_whichever_page_states_them_first(monkeypatch, fake_anthropic):
    """The cover page usually carries these, later pages usually do not -- the first
    non-null value seen wins rather than a later blank page silently erasing it."""
    reader = _reader(monkeypatch, fake_anthropic, scripted={
        b"page1": _out(sections={"a": 20.0}, count=38, total=80.0, questions=[
            {"question_no": "1", "max_marks": 2.0, "stem_text": "First question"},
        ]),
        b"page2": _out(questions=[{"question_no": "2", "max_marks": 3.0, "stem_text": "Second question"}]),
    })

    out = reader.read([(b"page1", "image/jpeg"), (b"page2", "image/jpeg")])

    assert out.declared_sections == {"A": 20.0}
    assert out.declared_count == 38
    assert out.declared_total == 80.0
    assert [q.question_no for q in out.questions] == ["1", "2"]


def test_a_page_with_no_section_header_inherits_the_last_one_seen(monkeypatch, fake_anthropic):
    """A section letter is often printed once and left implicit on every later page --
    reading one page per call means a later page has nothing else to infer it from. This
    is the merge step's own job now (the Python-level 'or last_section' fallback), not
    something a prompt hint tells the model before it even sees the previous page's
    answer -- pages are read concurrently, so nothing here could know the prior page's
    section at call time anyway."""
    reader = _reader(monkeypatch, fake_anthropic, scripted={
        b"page1": _out(questions=[{"section": "B", "question_no": "5", "stem_text": "In section B"}]),
        b"page2": _out(questions=[{"question_no": "6", "stem_text": "Still in section B, unmarked"}]),
    })

    out = reader.read([(b"page1", "image/jpeg"), (b"page2", "image/jpeg")])

    assert [q.section for q in out.questions] == ["B", "B"]


def test_a_lettered_sub_part_with_no_number_inherits_the_last_question_seen(
    monkeypatch, fake_anthropic,
):
    """The bug this fixes: 'attempt any three of the following five' groups routinely
    span a page break -- only sub-part (i) sits under the question's printed number,
    (ii) onward continue on the next page with no number above them at all. The model
    correctly leaves question_no blank rather than invent one it cannot see (same
    guardrail as every other field); this used to mean the row was silently dropped
    (`if not number: continue`, no trace). A lettered row with no number is a
    continuation, not garbage -- same carry-over already applied to section."""
    reader = _reader(monkeypatch, fake_anthropic, scripted={
        b"p2": _out(questions=[
            {"section": "B", "question_no": "3", "sub_part": "i", "max_marks": 1.0,
             "stem_text": "first alternative, at the bottom of the page"},
        ]),
        b"p3": _out(questions=[
            {"question_no": "", "sub_part": "ii", "max_marks": 1.0, "stem_text": "continues at the top of the next page"},
            {"question_no": "", "sub_part": "iii", "max_marks": 1.0, "stem_text": "still question 3"},
            {"question_no": "", "sub_part": "iv", "max_marks": 1.0, "stem_text": "still question 3"},
            {"question_no": "", "sub_part": "v", "max_marks": 1.0, "stem_text": "still question 3"},
            {"question_no": "4", "sub_part": "i", "max_marks": 1.0, "stem_text": "a real new question"},
        ]),
    })

    out = reader.read([(b"p2", "image/jpeg"), (b"p3", "image/jpeg")])

    q3_parts = [q.sub_part for q in out.questions if q.question_no == "3"]
    assert q3_parts == ["i", "ii", "iii", "iv", "v"]
    assert next(q for q in out.questions if q.sub_part == "ii").section == "B"
    q4 = next(q for q in out.questions if q.question_no == "4")
    assert q4.sub_part == "i"


def test_a_group_instruction_split_across_the_page_break_still_groups_every_member(
    monkeypatch, fake_anthropic,
):
    """The bug this fixes: the group's own instruction and its 'N x M = Total' arithmetic
    are printed once, next to the group's FIRST sub-item -- almost always the one that
    happens to sit right before a page break. Continuation members (ii)-(v), same as any
    other continuation, have nothing on their own page to read attempt_required or the
    per-item mark from. The question_no/section carry-over already fixed the row from
    being dropped outright; without also carrying attempt_required and the per-item mark,
    those rows survived but silently fell out of the group (no attempt_required means
    group_choices has nothing to key them on), so their marks were still lost."""
    reader = _reader(monkeypatch, fake_anthropic, scripted={
        b"p2": _out(questions=[
            {"section": "B", "question_no": "3", "sub_part": "i", "max_marks": 1.0,
             "stem_text": "first item, with the instruction and 3 x 1 = 3 right above it",
             "attempt_required": 3},
        ]),
        b"p3": _out(questions=[
            {"question_no": "", "sub_part": "ii", "stem_text": "continues, nothing printed above it"},
            {"question_no": "", "sub_part": "iii", "stem_text": "still question 3"},
            {"question_no": "", "sub_part": "iv", "stem_text": "still question 3"},
            {"question_no": "", "sub_part": "v", "stem_text": "still question 3"},
            {"question_no": "4", "sub_part": "i", "max_marks": 2.0, "stem_text": "an ordinary next question"},
        ]),
    })

    out = reader.read([(b"p2", "image/jpeg"), (b"p3", "image/jpeg")])

    q3 = [q for q in out.questions if q.question_no == "3"]
    assert [q.sub_part for q in q3] == ["i", "ii", "iii", "iv", "v"]
    assert all(q.attempt_required == 3 for q in q3)
    assert all(q.max_marks == 1.0 for q in q3)
    q4 = next(q for q in out.questions if q.question_no == "4")
    assert q4.attempt_required is None
    assert q4.max_marks == 2.0


def test_a_row_with_neither_number_nor_sub_part_is_dropped_but_named(
    monkeypatch, fake_anthropic,
):
    """Nothing to anchor a bare, unlettered row to -- still dropped, same as before this
    fix, but now visible in problems instead of vanishing without a trace."""
    reader = _reader(monkeypatch, fake_anthropic, scripted={
        b"p1": _out(questions=[
            {"question_no": "", "stem_text": "stray OCR noise with nothing to anchor it"},
            {"question_no": "1", "stem_text": "a real question"},
        ]),
    })

    out = reader.read([(b"p1", "image/jpeg")])

    assert [q.question_no for q in out.questions] == ["1"]
    assert any("stray OCR noise" in p for p in out.problems)


def test_attempt_required_is_carried_from_the_model_onto_each_group_member(
    monkeypatch, fake_anthropic,
):
    """The 'attempt any N of M' group shape: five sub-items, no OR marker, no choice_alt
    -- attempt_required is what marks them as one group instead of five separate ones.
    0 (the model's default when it never saw this shape) becomes None, the same way
    choice_alt's '' already becomes None, so downstream grouping code can test truthiness
    without every ordinary row explicitly opting out."""
    reader = _reader(monkeypatch, fake_anthropic, scripted={
        b"page1": _out(questions=[
            {"question_no": "5", "sub_part": "i", "max_marks": 1.0,
             "stem_text": "item one", "attempt_required": 3},
            {"question_no": "5", "sub_part": "ii", "max_marks": 1.0,
             "stem_text": "item two", "attempt_required": 3},
            {"question_no": "6", "max_marks": 2.0, "stem_text": "ordinary question"},
        ]),
    })

    out = reader.read([(b"page1", "image/jpeg")])

    by_sub = {q.sub_part: q.attempt_required for q in out.questions if q.question_no == "5"}
    assert by_sub == {"i": 3, "ii": 3}
    ordinary = next(q for q in out.questions if q.question_no == "6")
    assert ordinary.attempt_required is None


def test_or_between_two_whole_sub_parts_reads_as_an_attempt_required_group_of_one(
    monkeypatch, fake_anthropic,
):
    """A third shape: (i) ... OR ... (ii) ... -- the word OR sits between two whole,
    separately numbered sub-items, not two lettered options inside one sub-part. That is
    not what choice_alt represents (it needs the SAME sub_part, differing only by
    choice_alt), so this reads the same as any other 'attempt any N of M' group with
    N=1 -- the merge step itself does nothing new here, it is the same attempt_required
    carry-through as the five-item MCQ group above, just with a group of two."""
    reader = _reader(monkeypatch, fake_anthropic, scripted={
        b"page1": _out(questions=[
            {"question_no": "13", "sub_part": "i", "max_marks": 8.0,
             "stem_text": "write a letter to your headmistress", "attempt_required": 1},
            {"question_no": "13", "sub_part": "ii", "max_marks": 8.0,
             "stem_text": "write a letter to your brother -- OR alternative",
             "attempt_required": 1},
        ]),
    })

    out = reader.read([(b"page1", "image/jpeg")])

    assert [q.choice_alt for q in out.questions] == [None, None]
    assert [q.attempt_required for q in out.questions] == [1, 1]


def test_each_questions_page_is_the_page_it_was_actually_read_from(monkeypatch, fake_anthropic):
    """One call per page means the page number is known outright, not a value the model
    has to guess -- overriding whatever (if anything) the model itself reported."""
    reader = _reader(monkeypatch, fake_anthropic, scripted={
        b"p1": _out(questions=[{"question_no": "1", "stem_text": "p1", "logical_page": 99}]),
        b"p2": _out(questions=[{"question_no": "2", "stem_text": "p2", "logical_page": 1}]),
        b"p3": _out(questions=[{"question_no": "3", "stem_text": "p3"}]),
    })

    out = reader.read([(b"p1", "image/jpeg"), (b"p2", "image/jpeg"), (b"p3", "image/jpeg")])

    assert [q.logical_page for q in out.questions] == [1, 2, 3]


def test_one_bad_page_is_recorded_as_a_problem_without_losing_the_rest_of_the_paper(
    monkeypatch, fake_anthropic,
):
    """The whole point of reading page-by-page: a page ruined by glare, or one that hits
    a transient API error, used to take the entire paper's read down with it."""
    reader = _reader(monkeypatch, fake_anthropic, scripted={
        b"p1": _out(questions=[{"question_no": "1", "stem_text": "fine"}]),
        b"p2": _FakeAPIStatusError(500, "internal error"),
        b"p3": _out(questions=[{"question_no": "3", "stem_text": "also fine"}]),
    })

    out = reader.read([(b"p1", "image/jpeg"), (b"p2", "image/jpeg"), (b"p3", "image/jpeg")])

    assert [q.question_no for q in out.questions] == ["1", "3"]
    assert out.refused is None  # two of three pages read fine -- not a total failure
    assert len(out.problems) == 1
    assert "page 2" in out.problems[0]


def test_every_page_failing_is_a_refusal_naming_each_pages_own_problem(monkeypatch, fake_anthropic):
    reader = _reader(monkeypatch, fake_anthropic, scripted={
        b"p1": _FakeAPIStatusError(413, "Request exceeds the maximum size"),
        b"p2": _FakeAPIStatusError(429, "rate limited"),
    })

    out = reader.read([(b"p1", "image/jpeg"), (b"p2", "image/jpeg")])

    assert out.questions == []
    assert out.refused is not None
    assert "page 1" in out.refused and "page 2" in out.refused


def test_pages_are_read_concurrently_not_one_after_another(monkeypatch, fake_anthropic):
    """The whole point of this change: wall-clock cost bounded by the slowest page, not
    the sum of every page -- proven here by having every page block until every other
    page has also started, which only resolves if they are genuinely running at once."""
    import threading

    n = 5
    barrier = threading.Barrier(n, timeout=5)

    class _BlockingMessages:
        def parse(self, **kwargs):
            barrier.wait()  # deadlocks (and the test times out) if calls are sequential
            content = kwargs["messages"][0]["content"]
            raw = base64.b64decode(content[0]["source"]["data"])
            return _FakeResponse(_out(questions=[
                {"question_no": raw.decode(), "stem_text": "concurrent"},
            ]))

    from app.extraction import paper_vision

    reader = paper_vision.AnthropicPaperVisionReader.__new__(paper_vision.AnthropicPaperVisionReader)
    reader.client = types.SimpleNamespace(messages=_BlockingMessages())
    reader.model = "claude-opus-5"
    reader.page_concurrency = n

    pages = [(str(i).encode(), "image/jpeg") for i in range(n)]
    out = reader.read(pages)

    assert sorted(q.question_no for q in out.questions) == [str(i) for i in range(n)]
