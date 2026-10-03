"""Phase 1.1: a paper's own structure -- section titles and syllabus lines -- is read and
stored verbatim, behind ``paper_capture_structure``. Nothing here calls a paid API: the
vision reader is driven through a scripted fake client."""

from __future__ import annotations

import base64
import io
import types

import pymupdf
import pytest
from sqlalchemy import select

from app.config import get_settings

MARK_X = 595 * 0.87


# --- the vision reader ------------------------------------------------------------------


class _Messages:
    def __init__(self, reply) -> None:
        self.reply = reply
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        content = kwargs["messages"][0]["content"]
        raw = base64.b64decode([b for b in content if b["type"] == "image"][-1]["source"]["data"])
        reply = self.reply[raw] if isinstance(self.reply, dict) else self.reply
        return types.SimpleNamespace(parsed_output=reply)


def _reader(reply, *, capture: bool):
    from app.extraction import paper_vision

    reader = paper_vision.AnthropicPaperVisionReader.__new__(
        paper_vision.AnthropicPaperVisionReader
    )
    reader.client = types.SimpleNamespace(messages=_Messages(reply))
    reader.model = "claude-opus-5"
    reader.page_concurrency = 1
    reader.capture_structure = capture
    return reader


def test_vision_with_the_flag_off_sends_exactly_the_old_prompt_and_format():
    from app.extraction import paper_vision

    reply = paper_vision._PaperOut(questions=[
        paper_vision._QuestionOut(section="A", question_no="1", max_marks=1, stem_text="Q one"),
    ])
    reader = _reader(reply, capture=False)
    out = reader.read([(b"p1", "image/jpeg")])

    call = reader.client.messages.calls[0]
    assert call["system"] == paper_vision.SYSTEM
    assert call["output_format"] is paper_vision._PaperOut
    assert out.section_titles == {} and out.syllabus_lines == []


def test_vision_with_the_flag_on_asks_for_titles_and_keeps_them_verbatim():
    from app.extraction import paper_vision

    page1 = paper_vision._PaperStructureOut(
        questions=[paper_vision._QuestionOut(section="B", question_no="11", stem_text="Q")],
        declared=paper_vision._DeclaredStructureOut(
            section_titles={"b": "Geography : Minerals and Energy Resources",
                            "c": "  "},
            syllabus_lines=["History Ch 1-2, Geography Ch 1, 3"],
        ),
    )
    page2 = paper_vision._PaperStructureOut(
        questions=[paper_vision._QuestionOut(section="C", question_no="20", stem_text="Q")],
        declared=paper_vision._DeclaredStructureOut(
            section_titles={"B": "a later page must not overwrite the first title",
                            "C": "Political Science : Political Parties"},
            syllabus_lines=["History Ch 1-2, Geography Ch 1, 3"],
        ),
    )
    reader = _reader({b"p1": page1, b"p2": page2}, capture=True)
    out = reader.read([(b"p1", "image/jpeg"), (b"p2", "image/jpeg")])

    call = reader.client.messages.calls[0]
    assert call["system"].startswith(paper_vision.SYSTEM)
    assert "section_titles" in call["system"] and "Never infer" in call["system"]
    assert call["output_format"] is paper_vision._PaperStructureOut
    assert out.section_titles == {
        "B": "Geography : Minerals and Energy Resources",
        "C": "Political Science : Political Parties",
    }
    assert out.syllabus_lines == ["History Ch 1-2, Geography Ch 1, 3"]


def test_an_older_style_reply_still_parses_with_the_flag_on():
    """The new fields are optional: a reply that omits them is valid."""
    from app.extraction import paper_vision

    parsed = paper_vision._PaperStructureOut.model_validate_json(
        '{"questions": [{"question_no": "1"}], "declared": {"sections": {"A": 20}}}'
    )
    assert parsed.declared.section_titles == {}
    assert parsed.declared.syllabus_lines == []
    reader = _reader(parsed, capture=True)
    out = reader.read([(b"p1", "image/jpeg")])
    assert out.declared_sections == {"A": 20.0}
    assert out.section_titles == {}


# --- the text route ---------------------------------------------------------------------


def _pdf(tmp_path, lines):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text in lines:
        page.insert_text((x, y), text, fontsize=10)
    path = tmp_path / "p.pdf"
    doc.save(path)
    doc.close()
    return path


def test_the_text_route_keeps_the_title_printed_after_the_section_letter(tmp_path):
    from app.extraction.paper import extract_paper

    path = _pdf(tmp_path, [
        (60, 40, "Maximum Marks: 4"),
        (60, 60, "Syllabus: History Ch 5, Geography Ch 5"),
        (60, 80, "Section A comprises 1 question of 2 marks each."),
        (60, 110, "SECTION A (History : Print Culture and the Modern World)"),
        (60, 140, "1. Explain how print culture shaped the reading habits of the poor."),
        (MARK_X, 140, "2"),
        (60, 180, "SECTION - B"),
        (60, 194, "(Geography : Minerals and Energy Resources)"),
        (60, 220, "2. Describe the distribution of coal deposits across the country."),
        (MARK_X, 220, "2"),
    ])
    out = extract_paper(path)
    assert out.section_titles == {
        "A": "History : Print Culture and the Modern World",
        "B": "Geography : Minerals and Energy Resources",
    }
    assert out.syllabus_lines == ["Syllabus: History Ch 5, Geography Ch 5"]
    assert [q.section for q in out.questions] == ["A", "B"]


def test_a_bare_syllabus_label_collects_the_entries_under_it(tmp_path):
    from app.extraction.paper import extract_paper

    path = _pdf(tmp_path, [
        (60, 40, "Syllabus:"),
        (60, 54, "History - Chapter 1, 2"),
        (60, 68, "Economics - Ch 3"),
        (60, 82, "General Instructions"),
        (60, 110, "SECTION A"),
        (60, 140, "1. Describe the process of unification of a nation-state in Europe."),
        (MARK_X, 140, "2"),
    ])
    out = extract_paper(path)
    assert out.syllabus_lines == ["Syllabus:", "History - Chapter 1, 2", "Economics - Ch 3"]
    assert out.section_titles == {}


def test_a_paper_with_no_titles_and_no_syllabus_records_nothing(tmp_path):
    from app.extraction.paper import extract_paper

    path = _pdf(tmp_path, [
        (60, 110, "SECTION A"),
        (60, 140, "1. Describe the process of unification of a nation-state in Europe."),
        (MARK_X, 140, "2"),
    ])
    out = extract_paper(path)
    assert out.section_titles == {} and out.syllabus_lines == []


# --- storage in assessment.declared -----------------------------------------------------


def _paper_bytes(lines) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text in lines:
        page.insert_text((x, y), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


PAPER = [
    (60, 40, "Maximum Marks: 8"),
    (60, 60, "This question paper contains 2 questions."),
    (60, 90, "SECTION A (Statistics)"),
    (60, 120, "1. Find the mean of the grouped data by the"),
    (60, 134, "step-deviation method, assumed mean 200."),
    (MARK_X, 120, "3"),
    (60, 180, "2. Prove that the tangent at any point of a"),
    (60, 194, "circle is perpendicular to the radius."),
    (MARK_X, 180, "5"),
]


@pytest.mark.parametrize("flag", [False, True])
def test_titles_reach_assessment_declared_only_with_the_flag_on(client, school, monkeypatch, flag):
    from app.db import SessionLocal
    from app.models import Assessment

    monkeypatch.setattr(get_settings(), "paper_capture_structure", flag)
    headers = {"X-API-Key": school["api_key"]}
    aid = client.post("/assessments", headers=headers, json={
        "subject_code": "X.MATH", "title": f"Structure {flag}", "total_marks": 8,
    }).json()["assessment_id"]
    r = client.post(
        f"/assessments/{aid}/scan", headers=headers,
        files=[("files", ("p.pdf", io.BytesIO(_paper_bytes(PAPER)), "application/pdf"))],
    )
    assert r.status_code == 201, r.text

    db = SessionLocal()
    declared = db.scalar(select(Assessment).where(Assessment.id == aid)).declared
    db.close()
    assert declared["total_marks"] == 8.0
    assert declared["question_count"] == 2
    if flag:
        assert declared["section_titles"] == {"A": "Statistics"}
    else:
        assert "section_titles" not in declared and "syllabus_lines" not in declared
