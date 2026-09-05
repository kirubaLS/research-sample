"""app.ingest.hindi_text: which OCR backend a Hindi upload actually uses.

Sarvam is preferred whenever a key is configured -- Indic-specialised OCR, the accuracy
option. Tesseract is next -- local, no network round trip, free (see the module's own
docstring for the full reasoning). Gemini is the last resort, for a deployment with
neither of the other two.
"""

from __future__ import annotations

import pytest

from app.ingest.hindi_text import hindi_read_text


def test_sarvam_is_preferred_when_a_key_is_configured(monkeypatch):
    monkeypatch.setattr(
        "app.ingest.hindi_text.sarvam_read_text",
        lambda pdf_bytes, *, api_key, language: f"from sarvam ({api_key}, {language})",
    )
    monkeypatch.setattr(
        "app.ingest.hindi_text.ocr_available",
        lambda: (_ for _ in ()).throw(AssertionError("Tesseract should not be checked")),
    )
    monkeypatch.setattr(
        "app.ingest.hindi_text.gemini_read_text",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Gemini should not be called")),
    )

    result = hindi_read_text(
        b"x", gemini_api_key=None, gemini_model="m",
        sarvam_api_key="sk", sarvam_language="hi-IN",
    )
    assert result == "from sarvam (sk, hi-IN)"


def test_tesseract_is_preferred_over_gemini_when_sarvam_is_not_configured(monkeypatch):
    monkeypatch.setattr("app.ingest.hindi_text.ocr_available", lambda: True)
    monkeypatch.setattr("app.ingest.hindi_text.ocr_read_text", lambda pdf_bytes: "from tesseract")
    monkeypatch.setattr(
        "app.ingest.hindi_text.gemini_read_text",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Gemini should not be called")),
    )

    assert hindi_read_text(b"x", gemini_api_key=None, gemini_model="m") == "from tesseract"


def test_gemini_is_the_last_resort_when_neither_sarvam_nor_tesseract_is_available(monkeypatch):
    monkeypatch.setattr("app.ingest.hindi_text.ocr_available", lambda: False)
    monkeypatch.setattr(
        "app.ingest.hindi_text.gemini_read_text",
        lambda pdf_bytes, *, api_key, model: f"from gemini ({api_key}, {model})",
    )

    result = hindi_read_text(b"x", gemini_api_key="k", gemini_model="m")
    assert result == "from gemini (k, m)"


def test_no_backend_available_is_a_named_failure_not_a_silent_one(monkeypatch):
    monkeypatch.setattr("app.ingest.hindi_text.ocr_available", lambda: False)

    with pytest.raises(ValueError, match="Gemini API key"):
        hindi_read_text(b"x", gemini_api_key=None, gemini_model="m")
