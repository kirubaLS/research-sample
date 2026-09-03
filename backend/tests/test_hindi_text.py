"""app.ingest.hindi_text: which OCR backend a Hindi upload actually uses.

Tesseract is preferred whenever this deployment can run it -- local, no network round
trip, and the accuracy this project needs (see the module's own docstring for why).
Gemini is the fallback for a deployment on Render's native Python runtime, which cannot
install the system binary at all.
"""

from __future__ import annotations

import pytest

from app.ingest.hindi_text import hindi_read_text


def test_tesseract_is_preferred_when_available(monkeypatch):
    monkeypatch.setattr("app.ingest.hindi_text.ocr_available", lambda: True)
    monkeypatch.setattr("app.ingest.hindi_text.ocr_read_text", lambda pdf_bytes: "from tesseract")
    monkeypatch.setattr(
        "app.ingest.hindi_text.gemini_read_text",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Gemini should not be called")),
    )

    assert hindi_read_text(b"x", gemini_api_key=None, gemini_model="m") == "from tesseract"


def test_gemini_is_the_fallback_when_tesseract_is_not_available(monkeypatch):
    monkeypatch.setattr("app.ingest.hindi_text.ocr_available", lambda: False)
    monkeypatch.setattr(
        "app.ingest.hindi_text.gemini_read_text",
        lambda pdf_bytes, *, api_key, model: f"from gemini ({api_key}, {model})",
    )

    result = hindi_read_text(b"x", gemini_api_key="k", gemini_model="m")
    assert result == "from gemini (k, m)"


def test_neither_backend_available_is_a_named_failure_not_a_silent_one(monkeypatch):
    monkeypatch.setattr("app.ingest.hindi_text.ocr_available", lambda: False)

    with pytest.raises(ValueError, match="Gemini API key"):
        hindi_read_text(b"x", gemini_api_key=None, gemini_model="m")
