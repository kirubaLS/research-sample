"""AnthropicPaperVisionReader.read() itself -- one Claude call per page, merged into one
PaperVisionReading -- rather than the whole-paper-in-one-request shape it replaced (see
paper_vision.py's own docstring for why: an unbounded request size was what produced
'RequestTooLargeError: Error code: 413' in production).

The real ``anthropic`` package is not installed in this sandbox (a genuine, if not fully
enforced dependency -- see pyproject.toml), so a small fake stands in for it: just enough
of ``anthropic.Anthropic`` and ``anthropic.APIStatusError`` for AnthropicPaperVisionReader
to run against, with ``messages.parse`` scripted per call to test the merge and
per-page-failure logic these tests are actually about.
"""

from __future__ import annotations

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
    def __init__(self, scripted) -> None:
        self._scripted = list(scripted)  # one entry consumed per call, in order

    def parse(self, **kwargs):
        outcome = self._scripted.pop(0)
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


def _reader(monkeypatch, fake_anthropic, scripted):
    from app.extraction import paper_vision

    reader = paper_vision.AnthropicPaperVisionReader.__new__(paper_vision.AnthropicPaperVisionReader)
    reader.client = types.SimpleNamespace(messages=_FakeMessages(scripted))
    reader.model = "claude-opus-5"
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
    reader = _reader(monkeypatch, fake_anthropic, scripted=[
        _out(sections={"a": 20.0}, count=38, total=80.0, questions=[
            {"question_no": "1", "max_marks": 2.0, "stem_text": "First question"},
        ]),
        _out(questions=[{"question_no": "2", "max_marks": 3.0, "stem_text": "Second question"}]),
    ])

    out = reader.read([(b"page1", "image/jpeg"), (b"page2", "image/jpeg")])

    assert out.declared_sections == {"A": 20.0}
    assert out.declared_count == 38
    assert out.declared_total == 80.0
    assert [q.question_no for q in out.questions] == ["1", "2"]


def test_a_page_with_no_section_header_inherits_the_last_one_seen(monkeypatch, fake_anthropic):
    """A section letter is often printed once and left implicit on every later page --
    reading one page per call means a later page has nothing else to infer it from."""
    reader = _reader(monkeypatch, fake_anthropic, scripted=[
        _out(questions=[{"section": "B", "question_no": "5", "stem_text": "In section B"}]),
        _out(questions=[{"question_no": "6", "stem_text": "Still in section B, unmarked"}]),
    ])

    out = reader.read([(b"page1", "image/jpeg"), (b"page2", "image/jpeg")])

    assert [q.section for q in out.questions] == ["B", "B"]


def test_each_questions_page_is_the_page_it_was_actually_read_from(monkeypatch, fake_anthropic):
    """One call per page means the page number is known outright, not a value the model
    has to guess -- overriding whatever (if anything) the model itself reported."""
    reader = _reader(monkeypatch, fake_anthropic, scripted=[
        _out(questions=[{"question_no": "1", "stem_text": "p1", "logical_page": 99}]),
        _out(questions=[{"question_no": "2", "stem_text": "p2", "logical_page": 1}]),
        _out(questions=[{"question_no": "3", "stem_text": "p3"}]),
    ])

    out = reader.read([(b"p1", "image/jpeg"), (b"p2", "image/jpeg"), (b"p3", "image/jpeg")])

    assert [q.logical_page for q in out.questions] == [1, 2, 3]


def test_one_bad_page_is_recorded_as_a_problem_without_losing_the_rest_of_the_paper(
    monkeypatch, fake_anthropic,
):
    """The whole point of reading page-by-page: a page ruined by glare, or one that hits
    a transient API error, used to take the entire paper's read down with it."""
    reader = _reader(monkeypatch, fake_anthropic, scripted=[
        _out(questions=[{"question_no": "1", "stem_text": "fine"}]),
        _FakeAPIStatusError(500, "internal error"),
        _out(questions=[{"question_no": "3", "stem_text": "also fine"}]),
    ])

    out = reader.read([(b"p1", "image/jpeg"), (b"p2", "image/jpeg"), (b"p3", "image/jpeg")])

    assert [q.question_no for q in out.questions] == ["1", "3"]
    assert out.refused is None  # two of three pages read fine -- not a total failure
    assert len(out.problems) == 1
    assert "page 2" in out.problems[0]


def test_every_page_failing_is_a_refusal_naming_each_pages_own_problem(monkeypatch, fake_anthropic):
    reader = _reader(monkeypatch, fake_anthropic, scripted=[
        _FakeAPIStatusError(413, "Request exceeds the maximum size"),
        _FakeAPIStatusError(429, "rate limited"),
    ])

    out = reader.read([(b"p1", "image/jpeg"), (b"p2", "image/jpeg")])

    assert out.questions == []
    assert out.refused is not None
    assert "page 1" in out.refused and "page 2" in out.refused
