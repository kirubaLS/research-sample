"""Loading a book through the browser.

The same guards as the CLI, because it is the same pipeline reached a second way. A
deployment without shell access still has to be able to load a book, and these are the
mistakes that would otherwise be made silently.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from app.config import get_settings

BOOK = Path(__file__).resolve().parents[2] / "ncert" / "X" / "maths"
real_book = pytest.mark.skipif(not BOOK.exists(), reason="NCERT PDFs are not in the repo")

KEY = "platform-test-key-abc"
HEAD = {"X-Platform-Key": KEY}


@pytest.fixture(autouse=True)
def _enable_platform():
    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = KEY
    yield
    settings.platform_admin_key = before


def _pdf(name: str):
    return {"file": (name, open(BOOK / name, "rb"), "application/pdf")}


def test_the_upload_surface_needs_the_operator_key(client):
    r = client.get("/platform/books/X.MATH")
    assert r.status_code in (401, 403, 404, 422)


def test_status_says_what_to_do_before_anything_is_loaded(client):
    body = client.get("/platform/books/X.SOMETHING", headers=HEAD).json()
    assert body["contents_uploaded"] is False
    assert "contents page" in body["next"]


def test_a_non_pdf_is_refused(client):
    r = client.post(
        "/platform/books/X.MATH/contents", headers=HEAD,
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert r.status_code == 422


def test_an_empty_file_is_refused(client):
    r = client.post(
        "/platform/books/X.MATH/contents", headers=HEAD,
        files={"file": ("x.pdf", io.BytesIO(b""), "application/pdf")},
    )
    assert r.status_code == 422


@real_book
def test_a_chapter_before_the_contents_page_is_refused(client, school):
    """Accepting one would mean accepting it on trust: there is nothing to check it against."""
    r = client.post(
        "/platform/books/X.MATH/chapters", headers=HEAD, files=_pdf("01-real-numbers.pdf")
    )
    assert r.status_code == 409
    assert "contents page first" in r.json()["detail"]


@real_book
def test_the_full_upload_flow(client, school):
    contents = client.post(
        "/platform/books/X.MATH/contents?edition=Reprint 2026-27",
        headers=HEAD, files=_pdf("00-contents.pdf"),
    )
    assert contents.status_code == 201
    assert contents.json()["chapters_expected"] == 14

    loaded = client.post(
        "/platform/books/X.MATH/chapters", headers=HEAD,
        files=_pdf("12-surface-areas-and-volumes.pdf"),
    )
    assert loaded.status_code == 201
    body = loaded.json()
    assert body["chapter"] == 12
    assert body["sections"] == 4
    assert body["chunks"] > 0

    # re-uploading the same chapter must not duplicate its content
    again = client.post(
        "/platform/books/X.MATH/chapters", headers=HEAD,
        files=_pdf("12-surface-areas-and-volumes.pdf"),
    )
    assert again.json()["chunks"] == 0

    status = client.get("/platform/books/X.MATH", headers=HEAD).json()
    assert status["loaded_chapters"] == 1
    assert 12 not in status["missing_chapters"]
    assert status["edition"] == "Reprint 2026-27"


@real_book
def test_the_answers_file_cannot_be_loaded_as_a_chapter(client, school):
    """It matches EXERCISE 31 times: loaded, it would make the answer key 'practice'."""
    client.post(
        "/platform/books/X.MATH/contents", headers=HEAD, files=_pdf("00-contents.pdf")
    )
    r = client.post(
        "/platform/books/X.MATH/chapters", headers=HEAD, files=_pdf("an-answers.pdf")
    )
    assert r.status_code == 422
    assert "answer key" in r.json()["detail"]


@real_book
def test_a_chapter_that_disagrees_with_the_contents_page_writes_nothing(client, school):
    """The upload is named as chapter 3 but is chapter 4 -- its sections cannot match."""
    client.post(
        "/platform/books/X.MATH/contents", headers=HEAD, files=_pdf("00-contents.pdf")
    )
    before = client.get("/platform/books/X.MATH", headers=HEAD).json()["chunks"]

    with open(BOOK / "04-quadratic-equations.pdf", "rb") as fh:
        r = client.post(
            "/platform/books/X.MATH/chapters", headers=HEAD,
            files={"file": ("03-pair-of-linear-equations.pdf", fh, "application/pdf")},
        )
    assert r.status_code == 422
    assert "disagrees with the contents page" in r.json()["detail"]
    after = client.get("/platform/books/X.MATH", headers=HEAD).json()["chunks"]
    assert after == before, "a rejected chapter must leave nothing behind"


def test_embedding_without_a_key_says_what_breaks(client, school):
    settings = get_settings()
    before = settings.jina_api_key
    settings.jina_api_key = None
    try:
        r = client.post("/platform/books/X.MATH/embed", headers=HEAD)
        assert r.status_code == 409
        assert "YAADHUM_JINA_API_KEY" in r.json()["detail"]
    finally:
        settings.jina_api_key = before
