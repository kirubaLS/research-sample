"""Reading a paper's heading: what comes back is cleaned, nothing is stored, and a missing model
key degrades to an empty answer rather than an error."""

from __future__ import annotations

import uuid

import pytest

KEY = "intake-platform-key"
HEAD = {"X-Platform-Key": KEY}


@pytest.fixture(autouse=True)
def _operator():
    from app.config import get_settings

    s = get_settings()
    before = (s.platform_admin_key, s.anthropic_api_key)
    s.platform_admin_key = KEY
    yield
    s.platform_admin_key, s.anthropic_api_key = before


def _teacher(client):
    sid = client.post("/platform/schools", headers=HEAD, json={"name": f"Intake {uuid.uuid4().hex[:6]}"}).json()["id"]
    return client.post(f"/platform/schools/{sid}/keys", headers=HEAD, json={"role": "teacher"}).json()["api_key"]


def _pdf() -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "UNIT TEST 1  MATHEMATICS  CLASS X  Max. Marks: 80  Time: 2 hours  " * 3)
    return doc.tobytes()


def _post(client, key):
    return client.post("/paper-intake/detect", headers={"X-API-Key": key},
                       files=[("files", ("paper.pdf", _pdf(), "application/pdf"))])


def test_the_reply_is_cleaned(client, monkeypatch):
    from app.api import paper_intake
    from app.config import get_settings

    get_settings().anthropic_api_key = "test"
    monkeypatch.setattr(paper_intake, "_ask", lambda s, t, i: (
        {"subject": " Mathematics ", "class": "X", "title": "Unit Test 1", "date": "10 Oct", "total_marks": "80 marks",
         "duration": None}, "m", 0.001))
    r = _post(client, _teacher(client))
    assert r.status_code == 200, r.text
    d = r.json()["detected"]
    assert d["subject"] == "Mathematics" and d["title"] == "Unit Test 1"
    assert d["total_marks"] == 80 and d["date"] is None  # an unparseable date is dropped, not guessed


def test_no_model_key_gives_an_empty_answer(client):
    from app.config import get_settings

    get_settings().anthropic_api_key = None
    r = _post(client, _teacher(client))
    assert r.status_code == 200 and r.json()["detected"]["subject"] is None


def test_it_needs_a_key(client):
    assert client.post("/paper-intake/detect", files=[("files", ("p.pdf", _pdf(), "application/pdf"))]).status_code in (401, 403, 422)
