"""Cheap vision read first, strong read only when the paper's own checksums fail. The reader
is a stub; no paid API is called."""

from __future__ import annotations

from app.extraction.paper import ExtractedQuestion
from app.extraction.paper_vision import PaperVisionReading
from app.extraction.vision_cascade import check, read_total, read_with_cascade


def _q(no, marks, stem="What is a prime number?", **kw):
    return ExtractedQuestion(section="A", question_no=str(no), sub_part=kw.pop("sub", None),
                             choice_alt=kw.pop("alt", None), max_marks=marks, stem_text=stem,
                             logical_page=1, **kw)


def _reading(questions, total=None, count=None, **kw):
    return PaperVisionReading(questions=questions, declared_total=total, declared_count=count, **kw)


def test_a_read_that_matches_the_papers_total_and_count_is_consistent():
    r = _reading([_q(1, 2), _q(2, 3)], total=5, count=2)
    assert check(r).ok


def test_each_mismatch_is_named():
    assert "marks add to 5" in check(_reading([_q(1, 2), _q(2, 3)], total=80)).reasons[0]
    assert "1 questions read" in check(_reading([_q(1, 2)], total=2, count=2)).reasons[0]
    assert "no marks" in " ".join(check(_reading([_q(1, None)], total=2)).reasons)
    assert "no text" in " ".join(check(_reading([_q(1, 2, stem=" ")], total=2)).reasons)


def test_a_paper_that_declares_nothing_cannot_vouch_for_the_cheap_read():
    verdict = check(_reading([_q(1, 2)]))
    assert not verdict.ok and "declares no total" in verdict.reasons[0]


def test_a_binary_or_pair_counts_once():
    r = [_q(1, 4), _q(2, 4, alt="b")]          # the first half carries no letter
    assert read_total(r) == 4


def test_a_case_study_stem_is_not_a_question():
    r = [_q(5, None, stem="passage"), _q(5, 2, sub="a"), _q(5, 2, sub="b")]
    assert read_total(r) == 4
    assert check(_reading(r, total=4)).ok


def _reader(good, bad):
    calls = []

    def read(pages, *, model, on_progress=None, **extra):
        calls.append(model)
        return good if model == "strong" else bad

    return read, calls


def test_a_consistent_cheap_read_is_kept_and_the_strong_model_is_never_called():
    good = _reading([_q(1, 2)], total=2, count=1)
    read, calls = _reader(good=_reading([]), bad=good)
    reading, report = read_with_cascade([b"p"], cheap="cheap", strong="strong", read=read)
    assert reading is good and calls == ["cheap"]
    assert not report["escalated"] and report["strong_pages"] == 0


def test_an_inconsistent_cheap_read_is_re_read_by_the_strong_model():
    strong = _reading([_q(1, 2), _q(2, 3)], total=5, count=2)
    read, calls = _reader(good=strong, bad=_reading([_q(1, 2)], total=5, count=2))
    reading, report = read_with_cascade([b"p", b"q"], cheap="cheap", strong="strong", read=read)
    assert reading is strong and calls == ["cheap", "strong"]
    assert report["escalated"] and report["strong_pages"] == 2 and report["reasons"]


def test_a_refused_cheap_read_escalates():
    refused = PaperVisionReading(refused="nothing readable")
    ok = _reading([_q(1, 2)], total=2)
    read, calls = _reader(good=ok, bad=refused)
    reading, report = read_with_cascade([b"p"], cheap="cheap", strong="strong", read=read)
    assert reading is ok and report["escalated"]
