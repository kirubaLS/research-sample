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


@real_book
def test_the_probe_reports_what_resolves_and_what_does_not(client, school):
    """The check the schema's closing line asks for, against loaded data rather than a
    description of it."""
    client.post("/platform/books/X.MATH/curriculum", headers=HEAD)
    client.post(
        "/platform/books/X.MATH/contents", headers=HEAD, files=_pdf("00-contents.pdf")
    )
    client.post(
        "/platform/books/X.MATH/chapters", headers=HEAD,
        files=_pdf("12-surface-areas-and-volumes.pdf"),
    )

    r = client.post(
        "/platform/books/X.MATH/probe", headers=HEAD,
        json={"questions": [{
            "q": "17",
            "chapter": "Surface Areas and Volumes",
            "stem": "The slant height of a right circular cone of base diameter 14 cm and "
                    "height 24 cm is",
        }]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "lexical", "no key configured in tests, so no vectors"
    [row] = body["rows"]
    assert row["retrieved"] == "Surface Areas and Volumes"
    assert row["hit"] is True
    assert row["nearest"]
    # without vectors the level is undecidable and must not be guessed
    assert row["familiarity"] is None
    assert "undecidable" in row["why"]


def test_probing_an_unloaded_subject_is_refused(client, school):
    r = client.post(
        "/platform/books/X.NOTHING/probe", headers=HEAD,
        json={"questions": [{"q": "1", "stem": "a question long enough to pass validation"}]},
    )
    assert r.status_code == 409


def test_a_probe_needs_at_least_one_question(client, school):
    r = client.post("/platform/books/X.MATH/probe", headers=HEAD, json={"questions": []})
    assert r.status_code == 422


# --- concept families ----------------------------------------------------------------

def test_families_are_proposed_from_the_books_own_sections(client, school):
    """The book's section headings are what its authors thought the divisions were, and a
    teacher recognises them. A starting point, not an answer."""
    r = client.get("/platform/books/X.MATH/concept-families", headers=HEAD)
    assert r.status_code == 200
    body = r.json()
    assert body["families"], "a loaded book should propose something"
    labels = {f["label"] for f in body["families"]}
    assert "Introduction" not in labels, "a student is not weak at 'Introduction'"
    assert "Summary" not in labels


def test_a_family_is_created_once_and_never_renamed(client, school):
    """Held constant across cycles is the whole property. Renaming one after a class has
    been tested breaks every trend that references it."""
    payload = {"families": [{
        "code": "X.MATH.CF.TEST_ONE",
        "label": "Original Name",
        "chapter_code": "X.MATH.SAV",
    }]}
    first = client.post("/platform/books/X.MATH/concept-families", headers=HEAD, json=payload)
    assert first.status_code == 201
    assert first.json()["created"] == 1

    renamed = {"families": [{
        "code": "X.MATH.CF.TEST_ONE",
        "label": "Different Name Entirely",
        "chapter_code": "X.MATH.SAV",
    }]}
    second = client.post("/platform/books/X.MATH/concept-families", headers=HEAD, json=renamed)
    assert second.json()["created"] == 0
    assert second.json()["already_existed"] == 1

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import TaxonomyNode

    db = SessionLocal()
    try:
        node = db.scalar(
            select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.TEST_ONE")
        )
        assert node.label == "Original Name", "a rename must not go through"
    finally:
        db.close()


def test_a_family_under_a_chapter_that_does_not_exist_is_refused(client, school):
    r = client.post(
        "/platform/books/X.MATH/concept-families", headers=HEAD,
        json={"families": [{
            "code": "X.MATH.CF.ORPHAN", "label": "Orphan",
            "chapter_code": "X.MATH.NOSUCHCHAPTER",
        }]},
    )
    assert r.json()["created"] == 0
    assert "X.MATH.NOSUCHCHAPTER" in r.json()["unknown_chapters"]


# --- proposing families by reading the chapter ---------------------------------------------

def test_proposing_with_a_model_refuses_without_a_key_rather_than_falling_back(client):
    """Falling back to the headings here would be the worst outcome: the caller asked for
    the reading, would be billed nothing, and would get a different answer with nothing
    saying so."""
    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = None
    try:
        # force=true so the request reaches the key check rather than stopping at the
        # already-has-proposals conflict, which depends on what else has run.
        r = client.post(
            "/platform/books/X.MATH/concept-families/propose-llm?force=true", headers=HEAD
        )
    finally:
        settings.anthropic_api_key = before
    assert r.status_code in (422, 503), r.text
    if r.status_code == 503:
        assert "YAADHUM_ANTHROPIC_API_KEY" in r.json()["detail"]


def test_proposals_read_back_empty_before_any_run(client):
    # A subject no run has touched. Asking X.MATH made this assertion a statement about
    # every other test in the suite rather than about the endpoint.
    body = client.get("/platform/books/X.SCI/concept-families/proposals", headers=HEAD).json()
    assert body["proposed"] == 0 and body["families"] == [] and body["runs"] == []


def test_a_stored_run_reads_back_with_its_evidence_and_blocks_a_silent_rerun(client):
    """The pass costs real money. A second one must be asked for explicitly, and must not
    overwrite the proposals a person may already have reviewed."""
    import uuid

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import ConceptFamilyProposal, TaxonomyNode

    db = SessionLocal()
    chapter = db.scalar(
        select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.STATS")
    )
    run = str(uuid.uuid4())
    db.add(
        ConceptFamilyProposal(
            curriculum_version="CBSE-2026-27", subject_code="X.MATH", run_id=run,
            source="llm", model="claude-haiku-4-5",
            code="X.MATH.CF.STEP_DEVIATION_METHOD", label="Step-deviation method",
            chapter_id=chapter.id if chapter else None,
            rationale="Exercise 14.1 drills it separately from the direct method.",
            evidence=["EXERCISE 14.1"], from_sections=["14.1"],
        )
    )
    db.commit()
    db.close()

    body = client.get("/platform/books/X.MATH/concept-families/proposals", headers=HEAD).json()
    assert body["proposed"] == 1
    [family] = body["families"]
    assert family["label"] == "Step-deviation method"
    assert family["evidence"] == ["EXERCISE 14.1"]     # the proof travels with the proposal
    assert family["applied_at"] is None                # stored is not applied

    again = client.post("/platform/books/X.MATH/concept-families/propose-llm", headers=HEAD)
    assert again.status_code == 409
    assert "force=true" in again.json()["detail"]


def test_a_stored_proposal_carries_the_chapter_code_needed_to_apply_it(client):
    """POST /concept-families is keyed on chapter_code. Returning only a display label
    made the review-then-apply round trip impossible: the chapter silently landed in
    unknown_chapters and the family was never created."""
    body = client.get(
        "/platform/books/X.MATH/concept-families/proposals", headers=HEAD
    ).json()
    assert body["families"], "expected the proposal stored by the previous test"
    [family] = body["families"]
    assert family["chapter_code"] == "X.MATH.STATS"
    assert family["chapter"] == "Statistics"

    # The exact shape the apply endpoint reads, built only from what this response gave us.
    applied = client.post(
        "/platform/books/X.MATH/concept-families",
        headers=HEAD,
        json={"families": [{
            "code": family["code"],
            "label": family["label"],
            "chapter_code": family["chapter_code"],
        }]},
    )
    assert applied.status_code == 201, applied.text
    assert applied.json() == {
        "created": 1, "already_existed": 0, "unknown_chapters": [],
        "note": "Existing families are left alone; a rename would break past comparisons.",
    }


def test_a_chapter_that_fails_does_not_throw_away_the_chapters_already_paid_for(
    client, school
):
    """A failure on one chapter used to abort the request with a bare 500: the money was
    spent, the work was done, and nothing was kept or explained. Each chapter is now
    committed as it completes, and the failure is reported with its reason."""
    from unittest.mock import patch

    from sqlalchemy import select

    from app.curriculum.llm_families import FamilyProposal
    from app.db import SessionLocal
    from app.models import ConceptFamilyProposal

    settings = get_settings()
    before_key = settings.anthropic_api_key
    settings.anthropic_api_key = "sk-not-used-the-call-is-patched"

    # Two chapters with content, so one can succeed while the other fails.
    db = SessionLocal()
    from app.models import BookChunk, TaxonomyNode

    for code, section, ref in (
        ("X.MATH.STATS", "S14_1", "Section 14.1"),
        ("X.MATH.PROB", "S15_1", "Section 15.1"),
    ):
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
        node = TaxonomyNode(
            kind="subtopic", code=f"{code}.{section}", label="A section",
            parent_id=chapter.id, path=f"{code}.{section}",
            curriculum_version=chapter.curriculum_version,
        )
        db.add(node)
        db.flush()
        db.add(BookChunk(
            curriculum_version=chapter.curriculum_version, subject_code="X.MATH",
            node_id=node.id, bucket="T", reference=ref,
            text="taught content", normalised="taught content", stem_hash=ref,
        ))
    db.commit()
    db.close()

    calls = {"n": 0}

    def flaky(self, chapter_label, passages):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("upstream said no")
        return [FamilyProposal(label=f"Family for {chapter_label}", rationale="r",
                               evidence=[passages[0][0]], from_sections=[])]

    try:
        with patch(
            "app.curriculum.llm_families.AnthropicFamilyProposer.propose", flaky
        ):
            r = client.post(
                "/platform/books/X.MATH/concept-families/propose-llm",
                headers=HEAD, params={"force": "true"},
            )
    finally:
        settings.anthropic_api_key = before_key

    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["failed"]) == 1
    assert "upstream said no" in body["failed"][0]["error"]
    assert body["proposed"] >= 1, "the chapters that succeeded must survive the one that did not"
    assert "re-run with force=true" in body["warning"]

    db = SessionLocal()
    stored = db.scalars(
        select(ConceptFamilyProposal).where(ConceptFamilyProposal.run_id == body["run_id"])
    ).all()
    db.close()
    assert len(stored) == body["proposed"]


def test_the_book_status_says_which_chapters_have_nothing_behind_them(client):
    """A whole-book total hides the one thing that decides whether a paper can be read.

    A chapter with no passages can never be matched, so every question from it comes back
    "no chapter in the book matched" -- and the screen said 213 chunks loaded.
    """
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import BookChunk, TaxonomyNode

    client.post("/platform/books/X.MATH/curriculum", headers=HEAD)

    db = SessionLocal()
    stats = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.STATS"))
    db.add(BookChunk(
        curriculum_version=stats.curriculum_version, subject_code="X.MATH",
        node_id=stats.id, bucket="T", reference="Section 13.2", section_number="13.2",
        text="the mean of grouped data", normalised="the mean of grouped data",
        stem_hash="cover-1",
    ))
    db.commit()
    db.close()

    body = client.get("/platform/books/X.MATH", headers=HEAD).json()
    by_chapter = {c["chapter"]: c for c in body["coverage"]}
    # Counts are relative, not exact: this suite shares one database, so another test's
    # chunks land in Statistics too. What has to hold is the distinction the screen draws.
    assert by_chapter["Statistics"]["chunks"] >= 1
    assert by_chapter["Statistics"]["with_a_section"] >= 1
    assert by_chapter["Probability"]["chunks"] == 0
    # Named, not just counted: the point is knowing which paper cannot be read yet.
    assert "Probability" in body["chapters_with_nothing_behind_them"]
    assert "Statistics" not in body["chapters_with_nothing_behind_them"]


def test_a_hindi_upload_is_read_through_gemini_not_the_pdfs_own_text_layer(client, monkeypatch):
    """Kritika's real text layer decodes as mojibake (a pre-Unicode font, no ToUnicode
    CMap -- see app.ingest.hindi_ocr). Stubs gemini_read_text rather than calling the real
    API: what this test checks is that the upload path calls it and threads its answer all
    the way to a written chapter, not the quality of Gemini's own Hindi transcription.

    A Hindi upload is backgrounded (see IngestJob) rather than answered directly -- a
    real Gemini call cannot finish inside Render's own request timeout. TestClient runs a
    BackgroundTasks task to completion before client.post() returns, so the job is already
    resolved by the time this polls its status; a real deployment's browser would poll for
    longer, but the same two calls -- POST then GET .../jobs/{id} -- are what it does.
    """
    from app.config import get_settings

    settings = get_settings()
    before = settings.gemini_api_key
    settings.gemini_api_key = "test-gemini-key"

    def fake_gemini_read_text(pdf_bytes, *, api_key, model):
        assert api_key == "test-gemini-key"
        # distinguishing by size is enough here: a real 1-page prelims vs. a real chapter
        return (
            "विषय सूची\n1. माता का अँचल 1\n-शिवपूजन सहाय\n"
            if len(pdf_bytes) < 2000
            else "माता का अँचल\nयह एक कहानी है।\nअभ्यास\n1. प्रश्न।\n"
        )

    monkeypatch.setattr("app.api.books.gemini_read_text", fake_gemini_read_text)

    client.post("/platform/books/X.HIN.KR/curriculum", headers=HEAD)
    contents = client.post(
        "/platform/books/X.HIN.KR/contents", headers=HEAD,
        files={"file": ("jhkr1ps.pdf", io.BytesIO(b"x" * 100), "application/pdf")},
    )
    assert contents.status_code == 202, contents.json()
    contents_job = client.get(
        f"/platform/books/X.HIN.KR/jobs/{contents.json()['job_id']}", headers=HEAD,
    ).json()
    assert contents_job["status"] == "succeeded", contents_job
    assert contents_job["chapters_expected"] == 1

    chapter = client.post(
        "/platform/books/X.HIN.KR/chapters", headers=HEAD,
        files={"file": ("jhkr101.pdf", io.BytesIO(b"x" * 5000), "application/pdf")},
    )
    assert chapter.status_code == 202, chapter.json()
    chapter_job = client.get(
        f"/platform/books/X.HIN.KR/jobs/{chapter.json()['job_id']}", headers=HEAD,
    ).json()
    assert chapter_job["status"] == "succeeded", chapter_job
    assert chapter_job["chapter"] == 1
    assert chapter_job["sections"] == 1

    settings.gemini_api_key = before


def test_a_gemini_connection_failure_is_surfaced_not_a_bare_500(client, monkeypatch):
    """'Could not reach the API' on a request that reached the backend was an unretried
    transport failure (a dropped connection, a read timeout) bubbling up as an unhandled
    exception inside the (then-synchronous) upload handler. gemini_read_text now retries
    that itself, and the call runs in a background job -- this checks what a job's own
    status shows once retries are exhausted: the same 502 a synchronous upload would have
    raised, not a job stuck at 'pending' with no visible cause."""
    import httpx as httpx_module

    from app.config import get_settings
    from app.ingest.gemini_ocr import gemini_read_text

    settings = get_settings()
    before = settings.gemini_api_key
    settings.gemini_api_key = "test-gemini-key"

    def always_fails(pdf_bytes, *, api_key, model):
        raise httpx_module.ConnectError("[Errno -2] Name or service not known")

    monkeypatch.setattr("app.api.books.gemini_read_text", always_fails)

    client.post("/platform/books/X.HIN.KR/curriculum", headers=HEAD)
    r = client.post(
        "/platform/books/X.HIN.KR/contents", headers=HEAD,
        files={"file": ("jhkr1ps.pdf", io.BytesIO(b"x" * 100), "application/pdf")},
    )
    assert r.status_code == 202, r.json()
    job = client.get(f"/platform/books/X.HIN.KR/jobs/{r.json()['job_id']}", headers=HEAD)
    assert job.status_code == 502
    assert "Gemini could not be reached" in job.json()["detail"]

    settings.gemini_api_key = before

    # not mocked here: a real retry loop that actually retries a transport failure
    # against an address that will never resolve, confirming it gives up rather than
    # hanging or raising something this test's own mock could have papered over. A real
    # one-page PDF, not arbitrary bytes: gemini_read_text renders each page itself now
    # (one call per page, not per file -- see the module docstring), so it has to open
    # successfully before the network call it is this test's job to fail.
    import pymupdf

    doc = pymupdf.open()
    doc.new_page(width=100, height=100)
    one_page_pdf = doc.tobytes()
    doc.close()

    with pytest.raises(RuntimeError, match="failed after"):
        gemini_read_text(
            one_page_pdf, api_key="k", model="m",
            timeout=1.0, max_retries=2,
        )


def test_a_hindi_upload_without_a_gemini_key_fails_the_job_by_name(client):
    from app.config import get_settings

    settings = get_settings()
    before = settings.gemini_api_key
    settings.gemini_api_key = None

    client.post("/platform/books/X.HIN.KR/curriculum", headers=HEAD)
    r = client.post(
        "/platform/books/X.HIN.KR/contents", headers=HEAD,
        files={"file": ("jhkr1ps.pdf", io.BytesIO(b"x" * 100), "application/pdf")},
    )
    assert r.status_code == 202, r.json()
    job = client.get(f"/platform/books/X.HIN.KR/jobs/{r.json()['job_id']}", headers=HEAD)
    assert job.status_code == 409
    assert "Gemini API key" in job.json()["detail"]

    settings.gemini_api_key = before


def test_a_job_for_another_subject_is_not_found(client):
    r = client.get("/platform/books/X.HIN.KR/jobs/not-a-real-id", headers=HEAD)
    assert r.status_code == 404


def test_status_counts_expected_chapters_for_a_book_with_no_section_list(client):
    """Every subject but Maths publishes chapter titles only (expected_chapters), not a
    chapter.section list (expected_sections) -- upload_contents' own "N chapters expected"
    already falls back to it, but this endpoint's `expected` set read only
    expected_sections, so every subject but Maths showed "0 chapters expected" here. The
    frontend treats 0 as falsy and renders it as "5/?" instead of the real total."""
    from app.db import SessionLocal
    from app.models import BookSource

    client.post("/platform/books/X.HIST/curriculum", headers=HEAD)

    db = SessionLocal()
    db.add(BookSource(
        curriculum_version="CBSE-2026-27", subject_code="X.HIST",
        expected_sections={}, expected_chapters={"1": "x", "2": "y", "3": "z"}, files={},
    ))
    db.commit()
    db.close()

    body = client.get("/platform/books/X.HIST", headers=HEAD).json()
    assert body["expected_chapters"] == 3


def _one_page(lines: list[str]) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    y = 60
    for line in lines:
        page.insert_text((60, y), line, fontsize=10)
        y += 14
    data = doc.tobytes()
    doc.close()
    return data


def test_uploading_a_chapter_again_fills_in_the_sections_it_was_missing(client):
    """Re-uploading was the obvious fix for a book with no sections, and did nothing.

    A chunk is written only when its hash is absent, and the same file hashes the same, so
    every chunk already existed and the run reported nothing written -- while the sections
    it had just worked out were thrown away. Filling the gap in place touches neither the
    text nor the vector, so a book does not have to be embedded again to gain the topics it
    always had.
    """
    from sqlalchemy import select, update

    from app.db import SessionLocal
    from app.models import BookChunk

    client.post("/platform/books/X.MATH/curriculum", headers=HEAD)
    client.post(
        "/platform/books/X.MATH/contents", headers=HEAD,
        files={"file": ("00-contents.pdf", _one_page([
            "Contents", "13. Statistics", "13.1 Introduction",
            "13.2 Mean of Grouped Data",
        ]), "application/pdf")},
    )
    chapter = _one_page(
        ["13 Statistics", "13.1 Introduction"]
        + ["Statistics is the collection of data. " * 3] * 4
        + ["13.2 Mean of Grouped Data"]
        + ["The mean uses class marks. " * 3] * 4
        # A chapter with no worked example is refused as a bad extraction, and rightly.
        + ["Example 1 : Find the mean of the distribution."]
        + ["Working shown here. " * 3] * 4
    )

    first = client.post(
        "/platform/books/X.MATH/chapters", headers=HEAD,
        files={"file": ("jemh113.pdf", chapter, "application/pdf")},
    )
    assert first.status_code == 201, first.text
    assert first.json()["chunks"] > 0
    assert first.json()["sections_filled"] == 0

    # A book loaded before the section was recorded.
    db = SessionLocal()
    db.execute(update(BookChunk).values(section_number=None))
    db.commit()
    db.close()

    again = client.post(
        "/platform/books/X.MATH/chapters", headers=HEAD,
        files={"file": ("jemh113.pdf", chapter, "application/pdf")},
    )
    assert again.status_code == 201, again.text
    body = again.json()
    # Nothing new written -- which is exactly why re-uploading used to be a no-op.
    assert body["chunks"] == 0
    assert body["sections_filled"] > 0

    db = SessionLocal()
    try:
        filled = db.scalars(
            select(BookChunk).where(BookChunk.section_number.isnot(None))
        ).all()
        assert filled, "the second read worked the sections out and stored none of them"
    finally:
        db.close()
