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


def test_a_section_no_family_claims_is_reported_as_uncovered(client, school, book):
    """Section 13.3 (Mode of Grouped Data) has a loaded chunk but no family claims it --
    the fixture's only Statistics family, Mean by step-deviation, covers 13.2 alone, and
    once a chapter has any stored proposal the heading-based fallback stops proposing for
    its other sections (see `covered` in propose_families). That is exactly the shape of
    the real gap a teacher only ever discovered when a question in that section came back
    unmapped: nothing here should have to fail a paper to be found."""
    r = client.get("/platform/books/X.MATH/concept-families", headers=HEAD)
    assert r.status_code == 200
    uncovered = {u["chapter_code"]: u["sections"] for u in r.json()["uncovered_sections"]}
    assert uncovered.get("X.MATH.STATS") == ["13.3"]
    # 13.2 is claimed by the fixture's own family and must not also be flagged.
    assert "13.2" not in uncovered.get("X.MATH.STATS", [])
    # A chapter with no stored proposal falls back to the heading proposals, which do
    # claim their own sections, so it must not be flagged as having any gap at all.
    assert "X.MATH.CIRCLE" not in uncovered


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

def test_chapter_passages_carry_the_chunks_own_section_not_an_empty_one(client, school):
    """The bug this fixes: passages were built by matching a chunk's node_id against the
    chapter's SUBTOPIC nodes' own ids, to read off the section number the taxonomy holds
    for that subtopic. Every chunk is filed under the CHAPTER's node_id, never any
    subtopic's (see `_load`) -- so that lookup never matched anything, for any subject,
    and every passage a family-proposing model was ever shown carried an empty section.
    A model with no real section ever shown to it can only guess one, so its
    `from_sections` answered to a number retrieval (which reads the chunk's own
    section_number directly, see app.ingest.probe) would never independently produce --
    exactly why mapping kept finding families that claimed no section a real question
    ever landed in."""
    from sqlalchemy import select

    from app.api.books import _chapter_passages
    from app.db import SessionLocal
    from app.models import BookChunk, TaxonomyNode

    db = SessionLocal()
    try:
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.STATS"))
        db.add(BookChunk(
            curriculum_version=chapter.curriculum_version, subject_code="X.MATH",
            node_id=chapter.id, bucket="T", reference="Section 13.2",
            section_number="13.2", text="The mean of grouped data uses class marks.",
            normalised="the mean of grouped data uses class marks.",
            stem_hash="test-chapter-passages-section",
        ))
        db.commit()

        passages = _chapter_passages(db, "X.MATH", chapter.id)
    finally:
        db.close()

    matched = [p for p in passages if p[0] == "Section 13.2"]
    assert matched, "the chunk just added should be one of this chapter's passages"
    assert matched[0][1] == "13.2"


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
        "created": 1, "already_existed": 0, "unknown_chapters": [], "wrong_subject": [],
        "note": "Existing families are left alone; a rename would break past comparisons.",
    }


def test_a_familys_sections_can_be_corrected_without_renaming_it(client):
    """The bug this fixes: a family whose label and chapter are exactly right can still
    have the wrong section on it (a model shown a whole-chapter book cited a question
    number instead of the bare "1" the chapter's chunks actually carry), and there used
    to be no way to fix just that -- only create a new family under a new code, which
    breaks every trend already keyed on the old one. PATCH corrects the one field that is
    metadata about where mapping looks, not the family's own permanent identity."""
    created = client.post(
        "/platform/books/X.MATH/concept-families", headers=HEAD,
        json={"families": [{
            "code": "X.MATH.CF.SECTION_FIX_TEST", "label": "Original label",
            "chapter_code": "X.MATH.STATS", "from_sections": ["30.1"],
        }]},
    )
    assert created.json()["created"] == 1, created.text

    patched = client.patch(
        "/platform/books/X.MATH/concept-families/X.MATH.CF.SECTION_FIX_TEST",
        headers=HEAD, json={"from_sections": ["1"]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json() == {"code": "X.MATH.CF.SECTION_FIX_TEST", "from_sections": ["1"]}

    body = client.get("/platform/books/X.MATH/concept-families/proposals", headers=HEAD).json()
    [family] = [f for f in body["families"] if f["code"] == "X.MATH.CF.SECTION_FIX_TEST"]
    assert family["from_sections"] == ["1"]
    # Never touched: the identity a report's trend depends on.
    assert family["label"] == "Original label"
    assert family["chapter_code"] == "X.MATH.STATS"


def test_correcting_a_family_that_does_not_exist_says_so(client):
    r = client.patch(
        "/platform/books/X.MATH/concept-families/X.MATH.CF.NO_SUCH_FAMILY",
        headers=HEAD, json={"from_sections": ["1"]},
    )
    assert r.status_code == 404


def test_applied_families_are_listed_regardless_of_which_run_proposed_them(client, school):
    """The bug this fixes: GET /concept-families/proposals only shows the latest run, so
    a family applied earlier (or corrected by PATCH afterwards) has no code visible
    anywhere -- exactly the case where a reviewer has spotted something wrong in the
    review screen (a wrong-language label) and needs to find and delete it."""
    # A made-up section that matches nothing any real chunk in this suite resolves to --
    # this file's tests run in a session-scoped, shared DB, so a real section number
    # (like STATS's own 13.2) would make this family a silent extra claimant for other
    # tests' mapping decisions elsewhere in the suite.
    created = client.post(
        "/platform/books/X.MATH/concept-families", headers=HEAD,
        json={"families": [{
            "code": "X.MATH.CF.APPLIED_LISTING_TEST", "label": "Findable label",
            "chapter_code": "X.MATH.STATS", "from_sections": ["77.7"],
        }]},
    )
    assert created.json()["created"] == 1, created.text

    # A second run happens afterward -- the family above must still be listed, even
    # though it is no longer part of the "latest" run.
    client.post(
        "/platform/books/X.MATH/concept-families", headers=HEAD,
        json={"families": [{
            "code": "X.MATH.CF.APPLIED_LISTING_TEST_2", "label": "A later family",
            "chapter_code": "X.MATH.STATS", "from_sections": ["77.8"],
        }]},
    )

    body = client.get(
        "/platform/books/X.MATH/concept-families/applied", headers=HEAD
    ).json()
    [family] = [f for f in body["families"] if f["code"] == "X.MATH.CF.APPLIED_LISTING_TEST"]
    assert family["label"] == "Findable label"
    assert family["chapter_code"] == "X.MATH.STATS"
    assert family["from_sections"] == ["77.7"]
    assert family["questions"] == 0


def test_an_unused_family_can_be_deleted(client, school):
    """The undo for bulk-applying a run's proposals without reading each one first: a
    family with a broken or wrong-language label that nothing has used yet should be
    removable outright, not just correctable field by field."""
    created = client.post(
        "/platform/books/X.MATH/concept-families", headers=HEAD,
        json={"families": [{
            "code": "X.MATH.CF.DELETE_ME_TEST", "label": "Nonsense label",
            "chapter_code": "X.MATH.STATS",
        }]},
    )
    assert created.json()["created"] == 1, created.text

    deleted = client.delete(
        "/platform/books/X.MATH/concept-families/X.MATH.CF.DELETE_ME_TEST", headers=HEAD,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"code": "X.MATH.CF.DELETE_ME_TEST", "deleted": True}

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import TaxonomyNode

    db = SessionLocal()
    try:
        assert db.scalar(
            select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.DELETE_ME_TEST")
        ) is None
    finally:
        db.close()


def test_deleting_a_family_that_does_not_exist_says_so(client):
    r = client.delete(
        "/platform/books/X.MATH/concept-families/X.MATH.CF.NO_SUCH_FAMILY", headers=HEAD,
    )
    assert r.status_code == 404


def test_a_family_already_carrying_marks_is_refused_deletion(client, school, book):
    """Deleting a family a real question is filed under would orphan its marks -- the
    same protection the audit route already gives wrong-subject/empty-code families,
    extended to every other way a family ends up unwanted."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Assessment, Question, TaxonomyNode

    db = SessionLocal()
    try:
        family = db.scalar(
            select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.MEAN_STEP_DEVIATION")
        )
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.STATS"))
        board_unit = db.scalar(
            select(TaxonomyNode).where(TaxonomyNode.id == chapter.parent_id)
        )
        assessment = Assessment(
            school_id=school["school_id"],
            subject_code="X.MATH", title="Family deletion guard", total_marks=3,
        )
        db.add(assessment)
        db.flush()
        db.add(Question(
            assessment_id=assessment.id, address="/1//", question_no="1",
            max_marks=3.0, board_unit_id=board_unit.id, chapter_id=chapter.id,
            curriculum_section="13.2", concept_family_id=family.id,
            concept_variant="test question", variant_hash="test-hash",
        ))
        db.commit()
        family_code = family.code
    finally:
        db.close()

    r = client.delete(f"/platform/books/X.MATH/concept-families/{family_code}", headers=HEAD)
    assert r.status_code == 409
    assert "orphan" in r.json()["detail"]


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
    CMap -- see app.ingest.hindi_ocr). Stubs hindi_read_text (app.ingest.hindi_text's
    dispatcher, which books.py now calls) rather than calling a real backend: what this
    test checks is that the upload path calls it and threads its answer all the way to a
    written chapter, not the quality or choice of any one backend's transcription -- and
    stubbing here rather than one level down (gemini_read_text) means the test does not
    care whether Tesseract happens to be installed in whatever environment runs it.

    A Hindi upload is backgrounded (see IngestJob) rather than answered directly -- a
    real OCR call cannot be relied on to finish inside Render's own request timeout.
    TestClient runs a BackgroundTasks task to completion before client.post() returns, so
    the job is already resolved by the time this polls its status; a real deployment's
    browser would poll for longer, but the same two calls -- POST then GET .../jobs/{id}
    -- are what it does.
    """
    from app.config import get_settings

    settings = get_settings()
    before = settings.gemini_api_key
    settings.gemini_api_key = "test-gemini-key"

    def fake_hindi_read_text(pdf_bytes, **kwargs):
        assert kwargs["gemini_api_key"] == "test-gemini-key"
        # distinguishing by size is enough here: a real 1-page prelims vs. a real chapter
        return (
            "विषय सूची\n1. माता का अँचल 1\n-शिवपूजन सहाय\n"
            if len(pdf_bytes) < 2000
            else "माता का अँचल\nयह एक कहानी है।\nअभ्यास\n1. प्रश्न।\n"
        )

    monkeypatch.setattr("app.api.books.hindi_read_text", fake_hindi_read_text)

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

    def always_fails(pdf_bytes, **kwargs):
        raise httpx_module.TransportError("[Errno -2] Name or service not known")

    monkeypatch.setattr("app.api.books.hindi_read_text", always_fails)

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


def test_a_hindi_upload_with_neither_backend_available_fails_the_job_by_name(
    client, monkeypatch,
):
    """app.ingest.hindi_text prefers Tesseract when it is actually installed (see that
    module's docstring), so 'no Gemini key configured' alone is no longer a failure --
    only the case where neither backend can run is. ocr_available is forced False here so
    the test is deterministic regardless of whether the machine running it happens to have
    tesseract-ocr-hin installed."""
    from app.config import get_settings

    monkeypatch.setattr("app.ingest.hindi_text.ocr_available", lambda: False)

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


def test_a_hindi_upload_prefers_tesseract_when_it_is_available(client, monkeypatch):
    """The point of app.ingest.hindi_text: given a choice, use the local, free, more
    reliable backend rather than the network one, with no Gemini key needed at all."""
    from app.config import get_settings

    monkeypatch.setattr("app.ingest.hindi_text.ocr_available", lambda: True)

    def fake_ocr_read_text(pdf_bytes):
        return "विषय सूची\n1. माता का अँचल 1\n-शिवपूजन सहाय\n"

    monkeypatch.setattr("app.ingest.hindi_text.ocr_read_text", fake_ocr_read_text)

    settings = get_settings()
    before = settings.gemini_api_key
    settings.gemini_api_key = None  # no key at all -- must not be needed

    client.post("/platform/books/X.HIN.KR/curriculum", headers=HEAD)
    r = client.post(
        "/platform/books/X.HIN.KR/contents", headers=HEAD,
        files={"file": ("jhkr1ps.pdf", io.BytesIO(b"x" * 100), "application/pdf")},
    )
    assert r.status_code == 202, r.json()
    job = client.get(f"/platform/books/X.HIN.KR/jobs/{r.json()['job_id']}", headers=HEAD).json()
    assert job["status"] == "succeeded", job
    assert job["chapters_expected"] == 1

    settings.gemini_api_key = before


def test_a_noisy_ocr_title_does_not_reject_a_correctly_numbered_hindi_chapter(
    client, monkeypatch,
):
    """The real bug: Kritika's contents page OCR'd chapter 1's title as 'माता का अआँचल ।'
    (an inserted vowel sign, a stray danda where the page number should be) against the
    clean 'माता का अँचल' the curriculum entry (X_HINDI_KRITIKA) carries. An exact
    title_key comparison rejected the chapter over nothing but that OCR noise, even
    though it is correctly identified by number. Fixed with a difflib similarity ratio,
    Hindi-only -- this checks the chapter upload succeeds despite the mismatch."""
    from app.config import get_settings

    settings = get_settings()
    before = settings.gemini_api_key
    settings.gemini_api_key = "test-gemini-key"

    def fake_hindi_read_text(pdf_bytes, **kwargs):
        if len(pdf_bytes) < 2000:
            # the noisy real OCR shape for the contents page
            return "विषय सूची\n. माता का अआँचल ।\n८ शिवपूजन सहाय\n2. साना-साना हाथ जोडि 0\n"
        return "माता का अँचल\nयह एक कहानी है।\nअभ्यास\n1. प्रश्न।\n"

    monkeypatch.setattr("app.api.books.hindi_read_text", fake_hindi_read_text)

    client.post("/platform/books/X.HIN.KR/curriculum", headers=HEAD)
    contents = client.post(
        "/platform/books/X.HIN.KR/contents", headers=HEAD,
        files={"file": ("jhkr1ps.pdf", io.BytesIO(b"x" * 100), "application/pdf")},
    )
    contents_job = client.get(
        f"/platform/books/X.HIN.KR/jobs/{contents.json()['job_id']}", headers=HEAD,
    ).json()
    assert contents_job["status"] == "succeeded", contents_job

    chapter = client.post(
        "/platform/books/X.HIN.KR/chapters", headers=HEAD,
        files={"file": ("jhkr101.pdf", io.BytesIO(b"x" * 5000), "application/pdf")},
    )
    chapter_job = client.get(
        f"/platform/books/X.HIN.KR/jobs/{chapter.json()['job_id']}", headers=HEAD,
    ).json()
    assert chapter_job["status"] == "succeeded", chapter_job
    assert chapter_job["chapter"] == 1

    settings.gemini_api_key = before


def test_a_job_for_another_subject_is_not_found(client):
    r = client.get("/platform/books/X.HIN.KR/jobs/not-a-real-id", headers=HEAD)
    assert r.status_code == 404


def test_no_db_session_is_open_while_hindi_ocr_runs(client, monkeypatch):
    """The real bug: _run_ingest_job used to open one session and hold it for the whole
    job, including the slow OCR call -- which sat idle-in-transaction long enough that
    Postgres/PgBouncer killed the connection before the job's own final commit could run,
    losing a result OCR had already produced (psycopg.errors.IdleInTransactionSessionTimeout
    on the real deployment). Regression-tested by calling _run_ingest_job directly (not
    through the HTTP client, whose own request-scoped session is a separate concern) and
    counting how many of *its* sessions are open at the moment OCR runs -- must be zero."""
    import io as io_module

    from app.api.books import IngestJob, _run_ingest_job
    from app.config import get_settings
    from app.db import SessionLocal as real_session_local

    open_sessions = 0
    max_open_during_ocr = 0

    def tracked_session_local():
        nonlocal open_sessions
        session = real_session_local()
        open_sessions += 1
        real_close = session.close

        def tracked_close():
            nonlocal open_sessions
            open_sessions -= 1
            real_close()

        session.close = tracked_close
        return session

    def fake_hindi_read_text(pdf_bytes, **kwargs):
        nonlocal max_open_during_ocr
        max_open_during_ocr = max(max_open_during_ocr, open_sessions)
        return "विषय सूची\n1. माता का अँचल 1\n-शिवपूजन सहाय\n"

    monkeypatch.setattr("app.api.books.hindi_read_text", fake_hindi_read_text)

    settings = get_settings()
    before = settings.gemini_api_key
    settings.gemini_api_key = "test-gemini-key"

    client.post("/platform/books/X.HIN.KR/curriculum", headers=HEAD)
    client.post(
        "/platform/books/X.HIN.KR/contents", headers=HEAD,
        files={"file": ("jhkr1ps.pdf", io_module.BytesIO(b"x" * 100), "application/pdf")},
    )

    db = real_session_local()
    job = IngestJob(
        subject_code="X.HIN.KR", curriculum_version="CBSE-2026-27", kind="contents",
        filename="jhkr1ps.pdf", pdf_bytes=b"y" * 100,
    )
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()

    # Patched only for the call under test, not the fixtures/setup above -- so the count
    # reflects _run_ingest_job's own sessions alone.
    monkeypatch.setattr("app.db.SessionLocal", tracked_session_local)
    _run_ingest_job(job_id)

    assert max_open_during_ocr == 0

    settings.gemini_api_key = before


def test_status_counts_expected_chapters_for_a_book_with_no_section_list(client):
    """Every subject but Maths publishes chapter titles only (expected_chapters), not a
    chapter.section list (expected_sections) -- upload_contents' own "N chapters expected"
    already falls back to it, but this endpoint's `expected` set read only
    expected_sections, so every subject but Maths showed "0 chapters expected" here. The
    frontend treats 0 as falsy and renders it as "5/?" instead of the real total."""
    from app.db import SessionLocal
    from app.models import BookSource

    from sqlalchemy import select

    client.post("/platform/books/X.HIST/curriculum", headers=HEAD)

    db = SessionLocal()
    # get-or-create, not a blind insert: another test in this session (expected-sections)
    # may already have created X.HIST's one BookSource row (curriculum_version,
    # subject_code) is a unique constraint, so a second unconditional insert here would
    # violate it whenever that test happens to run first.
    source = db.scalar(
        select(BookSource).where(
            BookSource.curriculum_version == "CBSE-2026-27",
            BookSource.subject_code == "X.HIST",
        )
    )
    if source is None:
        source = BookSource(curriculum_version="CBSE-2026-27", subject_code="X.HIST", files={})
        db.add(source)
    source.expected_sections = {}
    source.expected_chapters = {"1": "x", "2": "y", "3": "z"}
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


def test_uploading_a_chapter_again_corrects_a_wrong_section_not_only_a_blank_one(client):
    """The bug the fill-in-the-gap fix above did not cover: a chapter whose FIRST pass
    could only read it as one giant single_section block (headings this extractor
    could not detect at all yet -- the exact shape a Tamil or Hindi chapter hit before
    its heading detection worked) stores every chunk under the SAME placeholder section
    "1", which is not a blank -- `not existing.section_number` is already false. A later,
    corrected pass that reads the real "13.1"/"13.2" headings used to leave every chunk
    answering to that same wrong "1" forever, no matter how many times the fixed
    extractor re-read the same file, because a chunk is written only when its hash is
    absent and the file hashes the same either time."""
    from sqlalchemy import select, update

    from app.db import SessionLocal
    from app.models import BookChunk

    client.post("/platform/books/X.MATH/curriculum", headers=HEAD)
    client.post(
        "/platform/books/X.MATH/contents", headers=HEAD,
        files={"file": ("00-contents.pdf", _one_page([
            "Contents", "1. Real Numbers", "1.1 Euclid's Division Lemma",
            "1.2 Fundamental Theorem",
        ]), "application/pdf")},
    )
    # Distinct wording from every other book-upload test in this file and from the
    # `book` fixture's own seeded chunks (also filed under a chapter named "Statistics"
    # this file already uses) -- otherwise this test's chunks hash the same as another
    # test's and reuse THEIR already-correct rows instead of creating its own, which is
    # exactly the scoping the comment above was written to avoid.
    chapter = _one_page(
        ["1 Real Numbers", "1.1 Euclid's Division Lemma"]
        + ["Euclid's division lemma states that for positive integers. " * 3] * 4
        + ["1.2 Fundamental Theorem"]
        + ["Every composite number is a product of primes uniquely. " * 3] * 4
        + ["Example 1 : Express 140 as a product of its prime factors."]
        + ["Working shown here for the factor tree. " * 3] * 4
    )

    db = SessionLocal()
    before_ids = set(db.scalars(select(BookChunk.id)).all())
    db.close()

    first = client.post(
        "/platform/books/X.MATH/chapters", headers=HEAD,
        files={"file": ("jemh101.pdf", chapter, "application/pdf")},
    )
    assert first.status_code == 201, first.text
    assert first.json()["chunks"] > 0

    # This test's own chapter reuses the real X.MATH.REAL chapter node (a session-wide
    # taxonomy, shared with the `book` fixture used elsewhere in this suite, which files
    # its own chunks under that same chapter too) -- scoped to the rows THIS upload just
    # created rather than a blanket UPDATE/SELECT over the whole table, which would reach
    # rows other tests in this session-scoped DB still depend on.
    db = SessionLocal()
    mine_ids = set(db.scalars(select(BookChunk.id)).all()) - before_ids
    db.close()
    assert mine_ids, "the upload created no chunks to test the correction against"

    # Simulating the first, undetected-headings pass: every chunk of THIS test's own
    # chapter answers to the same placeholder section, not to nothing.
    db = SessionLocal()
    db.execute(update(BookChunk).where(BookChunk.id.in_(mine_ids)).values(section_number="1"))
    db.commit()
    db.close()

    again = client.post(
        "/platform/books/X.MATH/chapters", headers=HEAD,
        files={"file": ("jemh101.pdf", chapter, "application/pdf")},
    )
    assert again.status_code == 201, again.text
    assert again.json()["sections_filled"] > 0

    db = SessionLocal()
    try:
        sections = {
            row.section_number
            for row in db.scalars(select(BookChunk).where(BookChunk.id.in_(mine_ids))).all()
        }
        # The real section(s) this pass actually read -- not still collapsed under the
        # one placeholder value the earlier pass got stuck on.
        assert sections != {"1"}
    finally:
        db.close()


# --- families belong to one subject ---------------------------------------------------------

def test_apparatus_headings_are_not_proposed_as_families():
    """'Notes for the teacher' and 'Project work' are the book's furniture, not things a
    student can be weak at. A Hindi heading has no Latin letters for a slug, and once
    gave every such family the one code 'X.HIN.CF.'; now it gets a code of its own."""
    from app.curriculum.families import not_a_learning_area, propose

    assert not_a_learning_area("Notes for the teacher")
    assert not_a_learning_area("Project work")
    assert not_a_learning_area("Let's work these out")
    assert not_a_learning_area("Government Publications")
    assert not not_a_learning_area("Types of farming")
    proposed = propose([
        ("X.GEO.AGRICULTURE", "Agriculture", "4.1", "Types of farming", 3),
        ("X.GEO.AGRICULTURE", "Agriculture", "4.9", "Project work", 0),
        ("X.HIN.KR.MAIN", "मैं क्यों लिखता हूँ?", "1.1", "मैं क्यों लिखता हूँ?", 2),
    ], "X.GEO")
    assert [p.label for p in proposed] == ["Types of farming", "मैं क्यों लिखता हूँ?"]
    hindi = proposed[1].code
    assert hindi.startswith("X.GEO.CF.L") and len(hindi) > len("X.GEO.CF.")


def test_proposals_and_creation_stay_inside_the_subject(client, school):
    """Every chapter in the tree used to be proposed under whichever subject asked, so
    Maths was offered 'A Letter to God' as X.MATH.CF.LETTER_GOD -- and could create it."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import TaxonomyNode

    db = SessionLocal()
    try:
        subject = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH"))
        if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.ENG.FF.LETTERTOGOD")) is None:
            db.add(TaxonomyNode(
                kind="chapter", code="X.ENG.FF.LETTERTOGOD", label="A Letter to God",
                parent_id=subject.id, path="X.ENG.FF.LETTERTOGOD",
            ))
            db.commit()
    finally:
        db.close()

    proposed = client.get("/platform/books/X.MATH/concept-families", headers=HEAD).json()
    assert all(f["chapter_code"].startswith("X.MATH.") for f in proposed["families"])
    assert "possible_duplicates" in proposed

    refused = client.post("/platform/books/X.MATH/concept-families", headers=HEAD, json={
        "families": [{"code": "X.MATH.CF.LETTER_GOD", "label": "A Letter to God",
                      "chapter_code": "X.ENG.FF.LETTERTOGOD"}],
    }).json()
    assert refused["created"] == 0
    assert refused["wrong_subject"] == ["X.MATH.CF.LETTER_GOD -> X.ENG.FF.LETTERTOGOD"]


def test_the_audit_finds_and_removes_a_family_filed_under_the_wrong_subject(client, school):
    """A family created the old way, hanging off an English chapter with a Maths code, is
    listed by the audit and removed by applying it -- unless a question points at it."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import TaxonomyNode

    db = SessionLocal()
    try:
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.ENG.FF.LETTERTOGOD"))
        if chapter is None:
            subject = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH"))
            chapter = TaxonomyNode(kind="chapter", code="X.ENG.FF.LETTERTOGOD", label="A Letter to God",
                                   parent_id=subject.id, path="X.ENG.FF.LETTERTOGOD")
            db.add(chapter)
            db.flush()
        if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.LETTER_GOD")) is None:
            db.add(TaxonomyNode(kind="concept_family", code="X.MATH.CF.LETTER_GOD",
                                label="A Letter to God", parent_id=chapter.id, path="X.MATH.CF.LETTER_GOD"))
        db.commit()
    finally:
        db.close()

    audit = client.get("/platform/books/X.MATH/concept-families/audit", headers=HEAD).json()
    wrong = {f["code"]: f for f in audit["wrong_subject"]}
    assert wrong["X.MATH.CF.LETTER_GOD"]["chapter_code"] == "X.ENG.FF.LETTERTOGOD"
    assert wrong["X.MATH.CF.LETTER_GOD"]["questions"] == 0

    applied = client.post("/platform/books/X.MATH/concept-families/audit/apply", headers=HEAD).json()
    assert applied["removed"] >= 1
    db = SessionLocal()
    try:
        assert db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.LETTER_GOD")) is None
    finally:
        db.close()
    after = client.get("/platform/books/X.MATH/concept-families/audit", headers=HEAD).json()
    assert not any(f["code"] == "X.MATH.CF.LETTER_GOD" for f in after["wrong_subject"])


def test_the_audit_runs_across_every_subject_in_one_call(client, school):
    """'audit' is a literal path, never read as a subject code, and the all-subjects
    apply removes what each per-subject apply would."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import TaxonomyNode

    db = SessionLocal()
    try:
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.SAV"))
        if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.ECO.CF.VOLUME_WRONG")) is None:
            db.add(TaxonomyNode(kind="concept_family", code="X.ECO.CF.VOLUME_WRONG",
                                label="Volume", parent_id=chapter.id, path="X.ECO.CF.VOLUME_WRONG"))
            db.commit()
    finally:
        db.close()

    everything = client.get("/platform/books/audit", headers=HEAD).json()
    eco = next(s for s in everything["subjects"] if s["subject"] == "X.ECO")
    assert eco["wrong_subject"] >= 1 and everything["removable"] >= 1

    applied = client.post("/platform/books/audit/apply", headers=HEAD).json()
    assert applied["removed"] >= 1
    db = SessionLocal()
    try:
        assert db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.ECO.CF.VOLUME_WRONG")) is None
    finally:
        db.close()


def _corrupted_label() -> str:
    """Devanagari text on a Math family -- the corruption signal is script-based and
    subject-agnostic (see app.ingest.tamil_text._OTHER_INDIC_SCRIPT), so any subject's
    fixtures can exercise it without a real Tamil book loaded."""
    return "पराचीन जञान परपरा"


def test_a_corrupted_family_with_a_confident_match_is_fixed_by_label_only(client, school, book):
    """Exactly one corrupted family and exactly one clean proposal under the same
    chapter is the confident case: dry run reports it, apply updates ONLY the label --
    code, id, and any Question FK pointing at it are untouched."""
    import uuid

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import (
        Assessment, ConceptFamilyProposal, Question, TaxonomyNode,
    )

    db = SessionLocal()
    try:
        circle = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CIRCLE"))
        chapter = TaxonomyNode(
            kind="chapter", code="X.MATH.REPAIR_CONFIDENT_CHAPTER",
            label="Repair Confident Test Chapter", parent_id=circle.parent_id,
            path="X.MATH.REPAIR_CONFIDENT_CHAPTER",
            curriculum_version=circle.curriculum_version,
        )
        db.add(chapter)
        db.flush()
        family = TaxonomyNode(
            kind="concept_family", code="X.MATH.CF.REPAIR_CONFIDENT_TEST",
            label=_corrupted_label(), parent_id=chapter.id,
            path="X.MATH.CF.REPAIR_CONFIDENT_TEST",
            curriculum_version=chapter.curriculum_version,
        )
        db.add(family)
        db.flush()
        family_id = family.id

        assessment = Assessment(
            school_id=school["school_id"], subject_code="X.MATH",
            title="Repair guard", total_marks=3,
        )
        db.add(assessment)
        db.flush()
        db.add(Question(
            assessment_id=assessment.id, address="/1//", question_no="1",
            max_marks=3.0, board_unit_id=chapter.parent_id, chapter_id=chapter.id,
            curriculum_section="10.1", concept_family_id=family_id,
            concept_variant="repair test question", variant_hash="repair-test-hash",
        ))

        run_id = uuid.uuid4().hex
        db.add(ConceptFamilyProposal(
            curriculum_version=chapter.curriculum_version, subject_code="X.MATH",
            run_id=run_id, source="llm", model="fixture-clean",
            code="X.MATH.CF.TANGENT_TO_A_CIRCLE", label="Tangent to a Circle",
            chapter_id=chapter.id, evidence=["Theorem 10.1"], from_sections=["10.1"],
        ))
        db.commit()
    finally:
        db.close()

    dry = client.post(
        "/platform/books/X.MATH/concept-families/repair-corrupted", headers=HEAD,
    ).json()
    assert dry["dry_run"] is True
    fixed = next(f for f in dry["would_fix"] if f["code"] == "X.MATH.CF.REPAIR_CONFIDENT_TEST")
    assert fixed["old_label"] == _corrupted_label()
    assert fixed["new_label"] == "Tangent to a Circle"

    db = SessionLocal()
    try:
        still = db.scalar(select(TaxonomyNode).where(TaxonomyNode.id == family_id))
        assert still.label == _corrupted_label()  # dry run wrote nothing
    finally:
        db.close()

    applied = client.post(
        "/platform/books/X.MATH/concept-families/repair-corrupted?dry_run=false",
        headers=HEAD,
    ).json()
    assert applied["dry_run"] is False
    applied_entry = next(
        f for f in applied["would_fix"] if f["code"] == "X.MATH.CF.REPAIR_CONFIDENT_TEST"
    )
    assert applied_entry["applied"] is True

    db = SessionLocal()
    try:
        fixed_node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.id == family_id))
        assert fixed_node.label == "Tangent to a Circle"
        assert fixed_node.code == "X.MATH.CF.REPAIR_CONFIDENT_TEST"  # code untouched
        assert fixed_node.id == family_id  # id untouched

        question = db.scalar(select(Question).where(Question.variant_hash == "repair-test-hash"))
        assert question.concept_family_id == family_id  # FK untouched
    finally:
        db.close()

    # Idempotent: a second dry run finds it already clean, and a second apply is a no-op.
    again = client.post(
        "/platform/books/X.MATH/concept-families/repair-corrupted", headers=HEAD,
    ).json()
    assert not any(f["code"] == "X.MATH.CF.REPAIR_CONFIDENT_TEST" for f in again["would_fix"])
    assert not any(
        f["code"] == "X.MATH.CF.REPAIR_CONFIDENT_TEST" for f in again["flagged_for_review"]
    )
    assert not any(
        f["code"] == "X.MATH.CF.REPAIR_CONFIDENT_TEST" for f in again["unreferenced"]
    )
    reapplied = client.post(
        "/platform/books/X.MATH/concept-families/repair-corrupted?dry_run=false",
        headers=HEAD,
    ).json()
    assert not any(
        f["code"] == "X.MATH.CF.REPAIR_CONFIDENT_TEST" for f in reapplied["would_fix"]
    )


def test_a_corrupted_family_with_no_confident_match_is_flagged_not_touched(client, school, book):
    """Two clean proposals under one chapter is the 'one family became five' case: no
    guessing, the corrupted family is reported for review and never modified, even under
    apply=false. It carries a real question, so it belongs in flagged_for_review, not
    unreferenced."""
    import uuid

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Assessment, ConceptFamilyProposal, Question, TaxonomyNode

    db = SessionLocal()
    try:
        real = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.REAL"))
        chapter = TaxonomyNode(
            kind="chapter", code="X.MATH.REPAIR_AMBIGUOUS_CHAPTER",
            label="Repair Ambiguous Test Chapter", parent_id=real.parent_id,
            path="X.MATH.REPAIR_AMBIGUOUS_CHAPTER",
            curriculum_version=real.curriculum_version,
        )
        db.add(chapter)
        db.flush()
        family = TaxonomyNode(
            kind="concept_family", code="X.MATH.CF.REPAIR_AMBIGUOUS_TEST",
            label=_corrupted_label(), parent_id=chapter.id,
            path="X.MATH.CF.REPAIR_AMBIGUOUS_TEST",
            curriculum_version=chapter.curriculum_version,
        )
        db.add(family)
        db.flush()
        family_id = family.id

        assessment = Assessment(
            school_id=school["school_id"], subject_code="X.MATH",
            title="Repair ambiguity guard", total_marks=2,
        )
        db.add(assessment)
        db.flush()
        db.add(Question(
            assessment_id=assessment.id, address="/1//", question_no="1",
            max_marks=2.0, board_unit_id=chapter.parent_id, chapter_id=chapter.id,
            curriculum_section="1.2", concept_family_id=family_id,
            concept_variant="ambiguous repair test question",
            variant_hash="repair-ambiguous-hash",
        ))

        run_id = uuid.uuid4().hex
        for i, label in enumerate(["Fundamental Theorem of Arithmetic", "Prime Factorisation"]):
            db.add(ConceptFamilyProposal(
                curriculum_version=chapter.curriculum_version, subject_code="X.MATH",
                run_id=run_id, source="llm", model="fixture-clean",
                code=f"X.MATH.CF.REAL_CLEAN_{i}", label=label,
                chapter_id=chapter.id, evidence=["Theorem 1.1"], from_sections=["1.2"],
            ))
        db.commit()
    finally:
        db.close()

    dry = client.post(
        "/platform/books/X.MATH/concept-families/repair-corrupted", headers=HEAD,
    ).json()
    assert not any(f["code"] == "X.MATH.CF.REPAIR_AMBIGUOUS_TEST" for f in dry["would_fix"])
    flagged = next(
        f for f in dry["flagged_for_review"] if f["code"] == "X.MATH.CF.REPAIR_AMBIGUOUS_TEST"
    )
    assert flagged["question_count"] == 1
    assert set(flagged["candidate_labels"]) == {
        "Fundamental Theorem of Arithmetic", "Prime Factorisation",
    }

    applied = client.post(
        "/platform/books/X.MATH/concept-families/repair-corrupted?dry_run=false",
        headers=HEAD,
    ).json()
    assert not any(
        f["code"] == "X.MATH.CF.REPAIR_AMBIGUOUS_TEST" for f in applied["would_fix"]
    )

    db = SessionLocal()
    try:
        untouched = db.scalar(select(TaxonomyNode).where(TaxonomyNode.id == family_id))
        assert untouched.label == _corrupted_label()
    finally:
        db.close()


def test_a_corrupted_family_with_no_questions_and_no_match_is_unreferenced(client, school, book):
    """No Question references it and no candidate proposal exists under its chapter: it
    is reported as unreferenced (safe to delete by hand) but never modified here."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import TaxonomyNode

    db = SessionLocal()
    try:
        ap = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.AP"))
        chapter = TaxonomyNode(
            kind="chapter", code="X.MATH.REPAIR_UNREFERENCED_CHAPTER",
            label="Repair Unreferenced Test Chapter", parent_id=ap.parent_id,
            path="X.MATH.REPAIR_UNREFERENCED_CHAPTER",
            curriculum_version=ap.curriculum_version,
        )
        db.add(chapter)
        db.flush()
        family = TaxonomyNode(
            kind="concept_family", code="X.MATH.CF.REPAIR_UNREFERENCED_TEST",
            label=_corrupted_label(), parent_id=chapter.id,
            path="X.MATH.CF.REPAIR_UNREFERENCED_TEST",
            curriculum_version=chapter.curriculum_version,
        )
        db.add(family)
        db.commit()
        family_id = family.id
    finally:
        db.close()

    dry = client.post(
        "/platform/books/X.MATH/concept-families/repair-corrupted", headers=HEAD,
    ).json()
    assert not any(
        f["code"] == "X.MATH.CF.REPAIR_UNREFERENCED_TEST" for f in dry["would_fix"]
    )
    unref = next(
        f for f in dry["unreferenced"] if f["code"] == "X.MATH.CF.REPAIR_UNREFERENCED_TEST"
    )
    assert unref["question_count"] == 0

    applied = client.post(
        "/platform/books/X.MATH/concept-families/repair-corrupted?dry_run=false",
        headers=HEAD,
    ).json()
    assert not any(
        f["code"] == "X.MATH.CF.REPAIR_UNREFERENCED_TEST" for f in applied["would_fix"]
    )

    db = SessionLocal()
    try:
        untouched = db.scalar(select(TaxonomyNode).where(TaxonomyNode.id == family_id))
        assert untouched.label == _corrupted_label()
    finally:
        db.close()


def test_a_clean_label_is_never_reported_or_touched(client, school):
    """X.MATH.CF.VOLUME's label is ordinary English -- it must not appear anywhere in
    the repair report, dry run or applied."""
    for dry_run in ("true", "false"):
        r = client.post(
            f"/platform/books/X.MATH/concept-families/repair-corrupted?dry_run={dry_run}",
            headers=HEAD,
        ).json()
        codes = (
            {f["code"] for f in r["would_fix"]}
            | {f["code"] for f in r["flagged_for_review"]}
            | {f["code"] for f in r["unreferenced"]}
        )
        assert "X.MATH.CF.VOLUME" not in codes
