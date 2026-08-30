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


def test_status_says_the_curriculum_comes_first(client):
    """Board units and weightage come from the syllabus, not the book, so a subject with
    no curriculum has nowhere to put a chapter's marks."""
    body = client.get("/platform/books/X.SOMETHING", headers=HEAD).json()
    assert body["curriculum_ready"] is False
    assert body["contents_uploaded"] is False
    assert "curriculum" in body["next"]


def test_the_curriculum_can_be_set_up_without_a_shell(client):
    r = client.post("/platform/books/X.MATH/curriculum", headers=HEAD)
    assert r.status_code == 201
    body = r.json()
    assert body["board_units"] == 7
    assert body["chapters"] == 14

    # idempotent: the console will be re-opened and the button pressed again
    again = client.post("/platform/books/X.MATH/curriculum", headers=HEAD).json()
    assert all(v == 0 for v in again["created"].values())

    assert client.get("/platform/books/X.MATH", headers=HEAD).json()["curriculum_ready"]


def test_an_unknown_subject_is_refused_with_the_known_ones(client):
    r = client.post("/platform/books/X.LATIN/curriculum", headers=HEAD)
    assert r.status_code == 422
    assert "X.MATH" in r.json()["detail"]


def test_a_contents_page_for_a_subject_with_no_curriculum_is_refused(client):
    """Otherwise the book loads into a taxonomy with no board unit to score against, and
    board impact comes out blank rather than wrong."""
    r = client.post(
        "/platform/books/X.SOMETHING/contents", headers=HEAD,
        files={"file": ("00-contents.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert r.status_code == 422
    assert "curriculum first" in r.json()["detail"]


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
def test_ncert_own_filenames_are_accepted(client, school):
    """The path a real operator is on: the files come off NCERT's site named jemh1NN."""
    import shutil
    import tempfile

    client.post("/platform/books/X.MATH/curriculum", headers=HEAD)
    client.post(
        "/platform/books/X.MATH/contents", headers=HEAD, files=_pdf("00-contents.pdf")
    )

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "jemh112.pdf"
        shutil.copy(BOOK / "12-surface-areas-and-volumes.pdf", raw)
        with open(raw, "rb") as fh:
            r = client.post(
                "/platform/books/X.MATH/chapters", headers=HEAD,
                files={"file": ("jemh112.pdf", fh, "application/pdf")},
            )

    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["chapter"] == 12
    # the title cannot come from the filename, so it comes from the curriculum
    assert body["title"] == "Surface Areas and Volumes"


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
