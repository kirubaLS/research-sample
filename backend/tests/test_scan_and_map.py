"""Scanning a paper and mapping it onto the book, end to end through HTTP."""

from __future__ import annotations

import io

import pymupdf
import pytest
from sqlalchemy import select

from app.config import get_settings

MARK_X = 595 * 0.87


def _paper_bytes(lines_per_page: list[list[tuple[float, float, str]]]) -> bytes:
    doc = pymupdf.open()
    for lines in lines_per_page:
        page = doc.new_page(width=595, height=842)
        for x, y, text in lines:
            page.insert_text((x, y), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


#: Laid out as a real paper does: the stem wraps well clear of the right-hand mark
#: column. Running the text under the mark merges the two into one line and the label is
#: lost -- which is a property of this fixture, not of any paper CBSE prints.
PAPER = [[
    (60, 60, "This question paper contains 2 questions."),
    (60, 90, "SECTION A"),
    (60, 120, "1. Find the mean of the grouped data by the"),
    (60, 134, "step-deviation method, assumed mean 200."),
    (MARK_X, 120, "3"),
    (60, 180, "2. Prove that the tangent at any point of a"),
    (60, 194, "circle is perpendicular to the radius."),
    (MARK_X, 180, "5"),
]]


@pytest.fixture
def assessment(client, school):
    r = client.post(
        "/assessments",
        headers={"X-API-Key": school["api_key"]},
        json={"subject_code": "X.MATH", "title": "Scan test", "total_marks": 8},
    )
    assert r.status_code == 200
    return r.json()["assessment_id"]


def _auth(school):
    return {"X-API-Key": school["api_key"]}


def _upload(client, school, aid, data, name="paper.pdf"):
    return client.post(
        f"/assessments/{aid}/scan",
        headers=_auth(school),
        files=[("files", (name, io.BytesIO(data), "application/pdf"))],
    )


def _upload_many(client, school, aid, parts):
    """parts: list of (filename, bytes, content-type), in page order."""
    return client.post(
        f"/assessments/{aid}/scan",
        headers=_auth(school),
        files=[("files", (name, io.BytesIO(data), mime)) for name, data, mime in parts],
    )


def test_a_scanned_paper_is_staged_not_written_as_questions(client, school, assessment):
    """A question row needs a board unit and a concept family. Neither is knowable from
    the paper, so the scan may not create one -- staging is what keeps that honest."""
    from app.db import SessionLocal
    from app.models import Question, ScannedQuestion

    r = _upload(client, school, assessment, _paper_bytes(PAPER))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["route"] == "text"
    assert body["questions"] == 2
    assert body["total_marks"] == 8.0
    assert body["staged"] == 2
    assert body["problems"] == []

    db = SessionLocal()
    staged = db.scalars(
        select(ScannedQuestion).where(ScannedQuestion.assessment_id == assessment)
    ).all()
    real = db.scalars(select(Question).where(Question.assessment_id == assessment)).all()
    db.close()
    assert len(staged) == 2
    assert real == [], "the scan must not create question rows"


def test_a_scan_of_an_image_only_paper_is_queued_and_refused_without_a_vision_key(
    client, school, assessment,
):
    """A scan cannot be read inside the request -- it needs a vision call, so it is
    queued as a PaperScanJob (202) rather than read here. With no Anthropic key
    configured (the test environment's default), the job itself then fails with the
    same 'no usable text layer'-shaped reason a synchronous refusal would have given."""
    doc = pymupdf.open()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8))
    pixmap.clear_with(180)
    for _ in range(2):
        page = doc.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pixmap)
    data = doc.tobytes()
    doc.close()

    r = _upload(client, school, assessment, data, name="scan.pdf")
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    job = client.get(f"/assessments/{assessment}/scan/jobs/{job_id}", headers=_auth(school))
    assert job.status_code == 422, job.text
    assert "cannot be read" in job.text


def test_a_job_stuck_pending_past_the_stale_window_is_failed_not_polled_forever(
    client, school, assessment,
):
    """A worker killed mid-scan (an OOM-kill, a deploy restart) never reaches the
    try/except in _run_paper_scan_job -- a process kill bypasses Python exception
    handling entirely -- so nothing ever writes "failed" to that job's row. Without a
    staleness check here, a poller would sit on that job forever. This reproduces that
    exact shape: a job manually left at "pending" with an old created_at, standing in for
    the process that died before it could finish."""
    from datetime import UTC, datetime, timedelta

    from app.db import SessionLocal
    from app.models.documents import PaperScanJob

    db = SessionLocal()
    job = PaperScanJob(school_id=school["school_id"], assessment_id=assessment, pdf_bytes=b"%PDF-1.4")
    db.add(job)
    db.commit()
    job.created_at = datetime.now(UTC) - timedelta(minutes=30)
    db.commit()
    job_id = job.id
    db.close()

    r = client.get(f"/assessments/{assessment}/scan/jobs/{job_id}", headers=_auth(school))
    assert r.status_code == 504, r.text
    assert "restarted" in r.text or "retake" in r.text


def test_two_context_rows_reading_the_same_question_are_merged_not_a_crash(
    client, school, assessment, monkeypatch,
):
    """The production shape that crashed the whole scan: a case-study question's
    instruction line ("Read the passage and answer...") and the passage itself were read
    as two separate is_context rows, both section A / question 1 / no sub_part -- the
    same address (uq_scanned_address is a database unique constraint), which used to
    reach the INSERT and fail the entire paper's read, losing every other question on it
    along with the one bad one."""
    from app.extraction.paper import ExtractedQuestion
    from app.extraction.paper_vision import PaperVisionReading

    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    class StubReader:
        def __init__(self, *a, **kw) -> None:
            pass

        def read(self, pages, on_progress=None):
            return PaperVisionReading(questions=[
                ExtractedQuestion(
                    section="A", question_no="1", sub_part=None, choice_alt=None,
                    max_marks=None, stem_text="Read the passage and answer the questions.",
                    logical_page=1, is_context=True,
                ),
                ExtractedQuestion(
                    section="A", question_no="1", sub_part=None, choice_alt=None,
                    max_marks=None, stem_text="The passage itself, in full.",
                    logical_page=1, is_context=True,
                ),
                ExtractedQuestion(
                    section="A", question_no="1", sub_part="i", choice_alt=None,
                    max_marks=1.0, stem_text="What does the passage say?",
                    logical_page=1,
                ),
            ])

    monkeypatch.setattr("app.extraction.paper_vision.AnthropicPaperVisionReader", StubReader)
    try:
        doc = pymupdf.open()
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8))
        pixmap.clear_with(180)
        page = doc.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pixmap)
        data = doc.tobytes()
        doc.close()

        out = _upload(client, school, assessment, data, name="scan.pdf")
        assert out.status_code == 202, out.text
        job_id = out.json()["job_id"]

        for _ in range(20):
            job = client.get(f"/assessments/{assessment}/scan/jobs/{job_id}", headers=_auth(school))
            if job.json().get("status") != "pending":
                break
        assert job.status_code == 200, job.text
        body = job.json()
        # The one real sub-question survives, and the two context rows merged into one
        # instead of either colliding or silently dropping the other's text.
        assert body["staged"] == 2, body

        scan = client.get(f"/assessments/{assessment}/scan", headers=_auth(school))
        rows = {r["address"]: r["stem_text"] for r in scan.json()["questions"]}
        assert "Read the passage" in rows["A/1//"]
        assert "The passage itself" in rows["A/1//"]
    finally:
        settings.anthropic_api_key = before


def test_a_scanned_papers_vision_read_stages_questions_the_same_way_text_does(
    client, school, assessment, monkeypatch
):
    """The whole point of the vision route: once it reads the paper, everything after
    that -- staging, review, mapping -- is the one pipeline the text route already uses,
    not a second one. Stubbed here because nothing in a test can actually read an image."""
    from app.extraction.paper import ExtractedQuestion
    from app.extraction.paper_vision import PaperVisionReading

    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    class StubReader:
        def __init__(self, *a, **kw) -> None:
            pass

        def read(self, pages, on_progress=None):
            return PaperVisionReading(questions=[
                ExtractedQuestion(
                    section="A", question_no="1", sub_part=None, choice_alt=None,
                    max_marks=3.0, stem_text="Find the mean of the grouped data.",
                    logical_page=1,
                ),
                ExtractedQuestion(
                    section="A", question_no="2", sub_part=None, choice_alt=None,
                    max_marks=5.0, stem_text="Prove the tangent is perpendicular.",
                    logical_page=1,
                ),
            ])

    monkeypatch.setattr("app.extraction.paper_vision.AnthropicPaperVisionReader", StubReader)
    try:
        doc = pymupdf.open()
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8))
        pixmap.clear_with(180)
        page = doc.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pixmap)
        data = doc.tobytes()
        doc.close()

        out = _upload(client, school, assessment, data, name="scan.pdf")
        assert out.status_code == 202, out.text
        job_id = out.json()["job_id"]

        job = client.get(f"/assessments/{assessment}/scan/jobs/{job_id}", headers=_auth(school))
        assert job.status_code == 200, job.text
        body = job.json()
        assert body["status"] == "succeeded"
        assert body["route"] == "vision"
        assert body["staged"] == 2

        from app.db import SessionLocal
        from app.models import ScannedQuestion

        db = SessionLocal()
        staged = db.scalars(
            select(ScannedQuestion).where(ScannedQuestion.assessment_id == assessment)
        ).all()
        db.close()
        assert {s.question_no for s in staged} == {"1", "2"}
    finally:
        settings.anthropic_api_key = before


def test_a_vision_read_that_falls_short_of_the_papers_own_declared_total_is_blocked(
    client, school, assessment, monkeypatch
):
    """The guardrail against a vision hallucination or a missed question: the model is
    told to read what the paper's OWN cover declares itself worth, never to compute it
    from what it just extracted, and confirm_scan holds the extraction to that number --
    the same check a text-route read has always had, now applied to a vision read too.
    A question the model missed (or invented too few marks for) surfaces here, not as a
    silently accepted, quietly wrong Q-matrix."""
    from app.extraction.paper import ExtractedQuestion
    from app.extraction.paper_vision import PaperVisionReading

    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    class StubReader:
        def __init__(self, *a, **kw) -> None:
            pass

        def read(self, pages, on_progress=None):
            return PaperVisionReading(
                questions=[
                    ExtractedQuestion(
                        section="A", question_no="1", sub_part=None, choice_alt=None,
                        max_marks=3.0, stem_text="Find the mean of the grouped data.",
                        logical_page=1,
                    ),
                ],
                # The paper declares 8 marks on its own cover; only 3 were extracted --
                # a question 2 the model missed entirely.
                declared_total=8.0,
            )

    monkeypatch.setattr("app.extraction.paper_vision.AnthropicPaperVisionReader", StubReader)
    try:
        doc = pymupdf.open()
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8))
        pixmap.clear_with(180)
        page = doc.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pixmap)
        data = doc.tobytes()
        doc.close()

        out = _upload(client, school, assessment, data, name="scan.pdf")
        job_id = out.json()["job_id"]
        job = client.get(f"/assessments/{assessment}/scan/jobs/{job_id}", headers=_auth(school))
        assert job.status_code == 200, job.text
        assert job.json()["staged"] == 1

        confirmed = client.post(
            f"/assessments/{assessment}/scan/confirm", headers=_auth(school), json={"by": "Mrs Rani"},
        )
        assert confirmed.status_code == 422, confirmed.text
        assert "8 marks" in confirmed.text and "add up to 3" in confirmed.text
    finally:
        settings.anthropic_api_key = before


#: Same layout as PAPER, plus a cover line declaring its own total -- exercises the
#: primary confidence signal (declared vs. read) rather than the "nothing to compare
#: against" trust-by-default path PAPER alone exercises.
PAPER_WITH_DECLARED_TOTAL = [[
    (60, 40, "Maximum Marks: 8"),
    *PAPER[0],
]]


def test_a_correctly_parsed_text_paper_never_triggers_the_vision_fallback(
    client, school, assessment,
):
    """The confidence check's whole point is to catch a bad rule-based read, not to run
    a paid vision call on every ordinary scan. A paper whose declared total matches what
    was read, with no unmarked leaf question, must be accepted synchronously -- route
    'text', 201, no PaperScanJob."""
    from app.db import SessionLocal
    from app.models.documents import PaperScanJob

    r = _upload(client, school, assessment, _paper_bytes(PAPER_WITH_DECLARED_TOTAL))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["route"] == "text"
    assert body["total_marks"] == 8.0

    db = SessionLocal()
    jobs = db.scalars(select(PaperScanJob).where(PaperScanJob.assessment_id == assessment)).all()
    db.close()
    assert jobs == [], "a confidently-read text paper must not queue a vision job"


def test_a_text_extraction_that_looks_unreliable_falls_back_to_vision(
    client, school, assessment, monkeypatch,
):
    """The core of this feature: the rule-based parser can silently mis-read a paper (a
    dropped question, a lost mark label) and nothing about the extraction itself looks
    like an error -- it just reads short. When the sum of what was read falls well short
    of what the paper's own cover declares, that read is not shipped; the same paper is
    queued for a vision re-read instead, exactly the way a photograph with no text layer
    already is."""
    from app.extraction.paper import ExtractedQuestion
    from app.extraction.paper_vision import PaperVisionReading

    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"

    class StubReader:
        def __init__(self, *a, **kw) -> None:
            pass

        def read(self, pages, on_progress=None):
            # The vision route recovers the question the text route's parser dropped.
            return PaperVisionReading(
                questions=[
                    ExtractedQuestion(
                        section="A", question_no="1", sub_part=None, choice_alt=None,
                        max_marks=3.0, stem_text="Find the mean of the grouped data.",
                        logical_page=1,
                    ),
                    ExtractedQuestion(
                        section="A", question_no="2", sub_part=None, choice_alt=None,
                        max_marks=5.0, stem_text="Prove the tangent is perpendicular.",
                        logical_page=1,
                    ),
                ],
                declared_total=8.0,
            )

    monkeypatch.setattr("app.extraction.paper_vision.AnthropicPaperVisionReader", StubReader)
    try:
        # The text route's own extraction is stubbed directly: a genuinely bad
        # rule-based read is hard to construct as a well-formed fixture (the layouts
        # that confuse the parser are themselves the bugs), and app.api.marks is the
        # layer under test here, not paper.py's parsing rules.
        from app.extraction.paper import ExtractedQuestion as EQ
        from app.extraction.paper import PaperExtract

        bad_extract = PaperExtract(
            route="text", page_count=1,
            questions=[
                EQ(
                    section="A", question_no="1", sub_part=None, choice_alt=None,
                    max_marks=3.0, stem_text="Find the mean of the grouped data.",
                    logical_page=1,
                ),
                # question 2 lost entirely, e.g. by an over-eager furniture drop --
                # the exact shape of the CBSE bug this feature was built for.
            ],
            declared_total=8.0,
        )
        # extract_paper is imported locally inside scan_paper (not at module scope in
        # app.api.marks), so the patch target is its home module, app.extraction.paper.
        monkeypatch.setattr("app.extraction.paper.extract_paper", lambda *a, **kw: bad_extract)

        r = _upload(client, school, assessment, _paper_bytes(PAPER))
        assert r.status_code == 202, r.text
        body = r.json()
        assert "job_id" in body
        assert "re-read" in body.get("detail", "")

        job_id = body["job_id"]
        job = client.get(f"/assessments/{assessment}/scan/jobs/{job_id}", headers=_auth(school))
        assert job.status_code == 200, job.text
        # The vision read's own two questions were staged, not the text route's one.
        assert job.json()["staged"] == 2
    finally:
        settings.anthropic_api_key = before


def test_mapping_blocks_a_question_rather_than_inventing_a_chapter(
    client, school, assessment, book
):
    """The point of the whole design: an unplaceable question stays staged with its
    reason, because forcing it into a chapter to keep the numbers tidy is the invention
    this pipeline refuses."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    client.post(f"/assessments/{assessment}/scan/confirm", headers=_auth(school), json={})
    r = _map(client, f"/assessments/{assessment}/map", headers=_auth(school))
    assert r.status_code == 200, r.text
    body = r.json()

    # The test database has chapters and chunks but no applied concept families, so every
    # question is blocked -- and the reason says exactly what to do about it.
    assert body["mapped"] + body["blocked"] == 2
    read = client.get(f"/assessments/{assessment}/scan", headers=_auth(school)).json()

    # The invariant, which holds whatever the corpus contains: a question is either fully
    # mapped -- chapter, family and board unit, all three from the book -- or it is not
    # mapped and says why. There is no third state, and no partially-filled row.
    for question in read["questions"]:
        placed = question["mapped_to"]
        if placed:
            assert placed["chapter"] and placed["concept_family"] and placed["board_unit"]
            assert not question["blocked_reason"]
        else:
            assert question["blocked_reason"], "a question is mapped or it says why not"


def test_auto_resolve_searches_the_chapter_when_the_exact_section_has_no_chunk(monkeypatch):
    """Stage 2 of auto_resolve: no chunk carries this exact section number (a numbering
    mismatch, or a genuine ingestion gap), so the whole chapter's already-ingested chunks
    are searched instead of falling back to the bare question text.

    A fully self-contained fixture chapter, under a fixture-only subject code no other
    test or real subject uses -- this calls resolve_blocked_family directly rather than
    through the HTTP pipeline, so there is no reason to touch any real curriculum data
    (X.MATH's shared LexicalIndex is rebuilt from every chunk under its subject codes,
    so even an unrelated chapter's added chunks shift retrieval scores suite-wide for
    every other X.MATH-based test -- this is what test_scan_and_map's own earlier
    version of this test got wrong)."""
    from sqlalchemy import select

    from app.db import SessionLocal, init_db
    from app.mapping.auto_resolve import _FamilyChoice, resolve_blocked_family
    from app.models import BookChunk, ConceptFamilyProposal, TaxonomyNode

    init_db()
    db = SessionLocal()
    chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "TEST.AUTORESOLVE.CH"))
    if chapter is None:
        chapter = TaxonomyNode(
            kind="chapter", code="TEST.AUTORESOLVE.CH", label="Fixture-only test chapter",
            path="TEST.AUTORESOLVE.CH", curriculum_version="TEST-FIXTURE",
        )
        db.add(chapter)
        db.flush()
    candidates = []
    for code, label in [
        ("TEST.AUTORESOLVE.CF.A", "Modal class of grouped data"),
        ("TEST.AUTORESOLVE.CF.B", "Cumulative frequency and the ogive"),
    ]:
        node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
        if node is None:
            node = TaxonomyNode(
                kind="concept_family", code=code, label=label, parent_id=chapter.id,
                path=code, curriculum_version="TEST-FIXTURE",
            )
            db.add(node)
            db.flush()
            db.add(ConceptFamilyProposal(
                curriculum_version="TEST-FIXTURE", subject_code="TEST.AUTORESOLVE",
                run_id="fixture-stage2", source="llm", model="fixture",
                code=code, label=label, chapter_id=chapter.id,
                evidence=[], from_sections=[],
            ))
        candidates.append(node)
    # Several real passages, so TF-IDF's idf does not go negative for a term shared by
    # every document in a too-small corpus (see LexicalIndex's own docstring: it is
    # deliberately the weakest plausible retriever) -- a real chapter's full chunk count
    # never hits this.
    for section, text in [
        ("13.3", "The modal class is the class with the greatest frequency, and the "
                  "mode is found from the frequencies either side of it."),
        ("13.4", "The coefficient of variation measures relative variability of a "
                  "distribution using its mean and standard deviation."),
        ("13.5", "Correlation between two variables is measured by covariance divided "
                  "by the product of their standard deviations."),
        ("13.6", "The standard deviation of grouped data can be found by the direct "
                  "method or the assumed mean method."),
    ]:
        code = f"TEST.AUTORESOLVE.CHUNK.{section.replace('.', '_')}"
        if db.scalar(select(BookChunk).where(BookChunk.stem_hash == code)) is not None:
            continue
        db.add(BookChunk(
            curriculum_version="TEST-FIXTURE", subject_code="TEST.AUTORESOLVE",
            node_id=chapter.id, bucket="T", reference=f"Section {section}", text=text,
            section_number=section, normalised=text.lower(), stem_hash=code,
        ))
    db.commit()
    db.close()

    # The 13.3 chunk above reads: "The modal class is the class with the greatest
    # frequency, and the mode is found from the frequencies either side of it." A real
    # quote from it is what the guardrail should accept; words that never appear in any
    # of these fixture passages are what it should refuse.
    real_quote = "the class with the greatest frequency"
    fake_quote = "the ogive is drawn from cumulative frequencies"

    def install_fake(family_code: str, quote: str):
        import sys
        import types

        class _FakeMessages:
            def parse(self, **kwargs):
                class _Response:
                    parsed_output = _FamilyChoice(
                        family_code=family_code,
                        rationale="the passage names the modal class by its frequency",
                        quote=quote,
                    )
                return _Response()

        class _FakeAnthropic:
            def __init__(self, api_key):
                self.messages = _FakeMessages()

        mod = types.ModuleType("anthropic")
        mod.Anthropic = _FakeAnthropic
        monkeypatch.setitem(sys.modules, "anthropic", mod)

    stem_text = "Find the modal class for the given frequency distribution table."

    # section="99.9" so stage 1 (exact section lookup) has nothing to find, forcing stage
    # 2's chapter-wide search -- a real answer, real quote, should be accepted.
    db = SessionLocal()
    install_fake("TEST.AUTORESOLVE.CF.A", real_quote)
    resolution = resolve_blocked_family(
        db, api_key="test-key", model="claude-fake", effort=None,
        subject_codes=["TEST.AUTORESOLVE"], section="99.9", stem_text=stem_text,
        chapter=chapter, candidates=candidates,
    )
    assert resolution is not None
    assert resolution.family.code == "TEST.AUTORESOLVE.CF.A"
    assert resolution.grounded_in == "book_search"
    assert resolution.book_section == "13.3", "the real chunk the quote came from, not the guessed-at section"
    db.close()

    # A fabricated quote -- words in neither retrieved passage -- must be refused
    # regardless of how plausible the chosen family sounds. This is the guardrail against
    # hallucination: a rationale is trusted only when it can point at real words actually
    # shown to the model, not the model's own memory of the syllabus.
    db = SessionLocal()
    install_fake("TEST.AUTORESOLVE.CF.B", fake_quote)
    resolution = resolve_blocked_family(
        db, api_key="test-key", model="claude-fake", effort=None,
        subject_codes=["TEST.AUTORESOLVE"], section="99.9", stem_text=stem_text,
        chapter=chapter, candidates=candidates,
    )
    assert resolution is None, "a quote that is not in any retrieved passage must not be trusted"
    db.close()


def test_auto_resolve_stage2_adds_semantic_retrieval_alongside_lexical(monkeypatch):
    """Stage 2 used to be lexical-only, which is exactly the wrong tool for a chapter
    whose sibling families all reuse the same vocabulary throughout (a civics chapter's
    sections all say "party", "election", "democracy") -- TF-IDF has nothing left to
    discriminate on, and can miss the one passage that actually settles a question while
    never even considering it a candidate. This fixture chunk shares zero words with the
    stem, so LexicalIndex alone never surfaces it at all (score > 0 requires overlap);
    only semantic retrieval (a fixed fake embedding, no real network call) finds it. The
    passages actually assembled for the judge are what this test inspects -- confirming
    the fix reaches the judge's evidence, not asserting anything about model judgement
    itself."""
    from sqlalchemy import select

    from app.db import SessionLocal, init_db
    from app.mapping.auto_resolve import _FamilyChoice, resolve_blocked_family
    from app.models import BookChunk, ConceptFamilyProposal, TaxonomyNode

    init_db()
    db = SessionLocal()
    chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "TEST.AUTORESOLVE2.CH"))
    if chapter is None:
        chapter = TaxonomyNode(
            kind="chapter", code="TEST.AUTORESOLVE2.CH", label="Fixture-only semantic chapter",
            path="TEST.AUTORESOLVE2.CH", curriculum_version="TEST-FIXTURE",
        )
        db.add(chapter)
        db.flush()
    candidates = []
    for code, label in [
        ("TEST.AUTORESOLVE2.CF.A", "Family sharing the stem's own words"),
        ("TEST.AUTORESOLVE2.CF.B", "Family the stem is actually about"),
    ]:
        node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
        if node is None:
            node = TaxonomyNode(
                kind="concept_family", code=code, label=label, parent_id=chapter.id,
                path=code, curriculum_version="TEST-FIXTURE",
            )
            db.add(node)
            db.flush()
            db.add(ConceptFamilyProposal(
                curriculum_version="TEST-FIXTURE", subject_code="TEST.AUTORESOLVE2",
                run_id="fixture-stage2-semantic", source="llm", model="fixture",
                code=code, label=label, chapter_id=chapter.id,
                evidence=[], from_sections=[],
            ))
        candidates.append(node)

    # chunk_wrong shares "reform measures party funding" with the stem below and would be
    # the only thing LexicalIndex ever returns; chunk_right shares no word with the stem
    # at all and is discoverable only by its (fixed, fake) embedding. Several unrelated
    # filler chunks too, so TF-IDF's idf does not go to zero for a term that would
    # otherwise be unique across a too-small corpus (see the stage-1 fixture's own note).
    chunk_wrong_text = "Reform measures for party funding are debated every election cycle."
    chunk_right_text = "Judges struck down laws letting candidates hide their donors."
    fixture_chunks = [
        ("TEST.AUTORESOLVE2.CHUNK.WRONG", chunk_wrong_text, [0.0, 1.0]),
        ("TEST.AUTORESOLVE2.CHUNK.RIGHT", chunk_right_text, [1.0, 0.0]),
        ("TEST.AUTORESOLVE2.CHUNK.F1", "The state assembly passed the annual budget bill.", None),
        ("TEST.AUTORESOLVE2.CHUNK.F2", "Local municipal wards elect their own councillors.", None),
        ("TEST.AUTORESOLVE2.CHUNK.F3", "The judiciary reviews laws referred by the president.", None),
    ]
    for code, text, embedding in fixture_chunks:
        if db.scalar(select(BookChunk).where(BookChunk.stem_hash == code)) is not None:
            continue
        db.add(BookChunk(
            curriculum_version="TEST-FIXTURE", subject_code="TEST.AUTORESOLVE2",
            node_id=chapter.id, bucket="T", reference=code, text=text,
            section_number=None, normalised=text.lower(), stem_hash=code,
            embedding=embedding,
        ))
    db.commit()
    db.close()

    stem_text = "What reform measures were proposed for party funding after the election?"

    def install_fake_judge(passages_seen: list[str]):
        import sys
        import types

        class _FakeMessages:
            def parse(self, **kwargs):
                passages_seen.append(kwargs["messages"][0]["content"])
                # Honestly say "none" -- this test is about what evidence reached the
                # judge, not about grading the judge's own choice.
                class _Response:
                    parsed_output = _FamilyChoice(
                        family_code="none", rationale="stub", quote="",
                    )
                return _Response()

        class _FakeAnthropic:
            def __init__(self, api_key):
                self.messages = _FakeMessages()

        mod = types.ModuleType("anthropic")
        mod.Anthropic = _FakeAnthropic
        monkeypatch.setitem(sys.modules, "anthropic", mod)

    class _FakeEmbedder:
        def __init__(self, api_key, *, model=None, dimensions=None):
            pass

        def embed_texts(self, texts, *, is_query=False):
            # The query lands exactly on chunk_right's fixed embedding, and nowhere near
            # chunk_wrong's -- cosine picks chunk_right first, every time.
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr("app.ingest.jina.JinaEmbedder", _FakeEmbedder)

    # Without a Jina key, stage 2 is lexical-only: only chunk_wrong (word overlap) is
    # ever assembled into the judge's passages -- chunk_right is invisible to it.
    db = SessionLocal()
    seen_without_semantic: list[str] = []
    install_fake_judge(seen_without_semantic)
    resolve_blocked_family(
        db, api_key="test-key", model="claude-fake", effort=None,
        subject_codes=["TEST.AUTORESOLVE2"], section="99.9", stem_text=stem_text,
        chapter=chapter, candidates=candidates,
    )
    assert chunk_wrong_text in seen_without_semantic[0]
    assert chunk_right_text not in seen_without_semantic[0], (
        "lexical-only stage 2 should never surface a passage sharing no words with the stem"
    )
    db.close()

    # With a Jina key configured, semantic retrieval runs alongside lexical and the
    # union reaches the judge -- chunk_right is now there too.
    db = SessionLocal()
    seen_with_semantic: list[str] = []
    install_fake_judge(seen_with_semantic)
    resolve_blocked_family(
        db, api_key="test-key", model="claude-fake", effort=None,
        subject_codes=["TEST.AUTORESOLVE2"], section="99.9", stem_text=stem_text,
        chapter=chapter, candidates=candidates,
        jina_api_key="test-jina-key", embedding_model="fake-model", embedding_dimensions=2,
    )
    assert chunk_right_text in seen_with_semantic[0], (
        "semantic retrieval should surface the passage lexical search alone missed entirely"
    )
    db.close()


def test_auto_resolve_semantic_family_stage_resolves_a_clear_lead_without_an_llm(monkeypatch):
    """The new Stage 0: when the judge names no curriculum_section at all (chronological
    order, Assertion-Reason, map-skill questions rarely cite one), choose_family() has
    nothing to disambiguate with and blocks -- but retrieval already has real semantic
    similarity between the stem and every family's own book text. When one family's text
    is clearly closer, this now resolves automatically, with the real chunk and its score
    recorded as evidence, no LLM call needed. A near-tie must still fall through and leave
    it for a person -- proven by the second case below with no configured margin lead."""
    from sqlalchemy import select

    from app.db import SessionLocal, init_db
    from app.mapping.auto_resolve import resolve_blocked_family
    from app.models import BookChunk, ConceptFamilyProposal, TaxonomyNode

    init_db()
    db = SessionLocal()
    chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "TEST.SEMFAM.CH"))
    if chapter is None:
        chapter = TaxonomyNode(
            kind="chapter", code="TEST.SEMFAM.CH", label="Fixture semantic-family chapter",
            path="TEST.SEMFAM.CH", curriculum_version="TEST-FIXTURE",
        )
        db.add(chapter)
        db.flush()
    candidates = []
    for code, label, section in [
        ("TEST.SEMFAM.CF.A", "Majoritarianism in Sri Lanka", "2"),
        ("TEST.SEMFAM.CF.B", "Accommodation in Belgium", "3"),
    ]:
        node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
        if node is None:
            node = TaxonomyNode(
                kind="concept_family", code=code, label=label, parent_id=chapter.id,
                path=code, curriculum_version="TEST-FIXTURE",
            )
            db.add(node)
            db.flush()
            db.add(ConceptFamilyProposal(
                curriculum_version="TEST-FIXTURE", subject_code="TEST.SEMFAM",
                run_id="fixture-semfam", source="book_map", model=None,
                code=code, label=label, chapter_id=chapter.id,
                evidence=[section], from_sections=[section],
            ))
        candidates.append(node)

    chunk_a = ("TEST.SEMFAM.CHUNK.A", "2", "Sri Lanka's constitution made Sinhala the "
               "only official language and favoured the Sinhala majority.", [1.0, 0.0])
    chunk_b = ("TEST.SEMFAM.CHUNK.B", "3", "Belgian leaders amended their constitution "
               "four times to share power between linguistic communities.", [0.0, 1.0])
    for code, section, text, embedding in [chunk_a, chunk_b]:
        if db.scalar(select(BookChunk).where(BookChunk.stem_hash == code)) is not None:
            continue
        db.add(BookChunk(
            curriculum_version="TEST-FIXTURE", subject_code="TEST.SEMFAM",
            node_id=chapter.id, bucket="T", reference=code, text=text,
            section_number=section, normalised=text.lower(), stem_hash=code,
            embedding=embedding,
        ))
    db.commit()
    db.close()

    # Case 1: a clear lead. The query embedding lands exactly on chunk_a's vector, far
    # from chunk_b's -- should auto-resolve to family A, no LLM needed (no api_key at all).
    class _EmbedderNearA:
        def __init__(self, api_key, *, model=None, dimensions=None):
            pass

        def embed_texts(self, texts, *, is_query=False):
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr("app.ingest.jina.JinaEmbedder", _EmbedderNearA)
    db = SessionLocal()
    resolution = resolve_blocked_family(
        db, api_key=None, model="unused", effort=None,
        subject_codes=["TEST.SEMFAM"], section=None,
        stem_text="Why did Sinhala-only language policy alienate Tamils in Sri Lanka?",
        chapter=chapter, candidates=candidates,
        jina_api_key="test-jina-key", embedding_model="fake-model", embedding_dimensions=2,
    )
    db.close()
    assert resolution is not None, "a clear semantic lead should resolve without an LLM"
    assert resolution.family.code == "TEST.SEMFAM.CF.A"
    assert resolution.grounded_in == "semantic_family"
    assert resolution.book_section == "2"
    assert "0." in resolution.rationale, "the real similarity score must be recorded as evidence"

    # Case 2: a near-tie. The query embedding lands equally close to both chunks -- must
    # NOT auto-resolve; it should fall through (no LLM configured here either) and leave
    # the question blocked for a person, same as before this stage existed.
    class _EmbedderTied:
        def __init__(self, api_key, *, model=None, dimensions=None):
            pass

        def embed_texts(self, texts, *, is_query=False):
            return [[0.7071, 0.7071] for _ in texts]

    monkeypatch.setattr("app.ingest.jina.JinaEmbedder", _EmbedderTied)
    db = SessionLocal()
    resolution = resolve_blocked_family(
        db, api_key=None, model="unused", effort=None,
        subject_codes=["TEST.SEMFAM"], section=None,
        stem_text="Compare power-sharing arrangements across two countries.",
        chapter=chapter, candidates=candidates,
        jina_api_key="test-jina-key", embedding_model="fake-model", embedding_dimensions=2,
    )
    db.close()
    assert resolution is None, "a near-tied semantic score must still be left for a person"


def test_mapping_refuses_when_no_book_is_loaded(client, school):
    r = client.post(
        "/assessments", headers=_auth(school),
        # 8, because that is what the fixture paper adds up to: confirming a scan whose
        # marks disagree with the paper's own total is refused, and this test is about the
        # book being absent, not about the totals.
        json={"subject_code": "X.SCI", "title": "No book", "total_marks": 8},
    )
    aid = r.json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=_auth(school), json={})
    out = _map(client, f"/assessments/{aid}/map", headers=_auth(school))
    assert out.status_code == 422
    assert "no book is loaded" in out.json()["detail"]


def test_rescanning_keeps_what_mapping_already_promoted(client, school, assessment):
    """A bad upload must be re-readable without unpicking the work already done."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    again = _upload(client, school, assessment, _paper_bytes(PAPER))
    assert again.status_code == 201
    assert again.json()["staged"] + again.json()["already_promoted"] == 2


def test_a_frozen_qmatrix_cannot_be_rescanned(client, school, assessment):
    _upload(client, school, assessment, _paper_bytes(PAPER))
    settings = get_settings()
    assert settings is not None
    client.post(f"/assessments/{assessment}/freeze", headers=_auth(school))
    r = _upload(client, school, assessment, _paper_bytes(PAPER))
    assert r.status_code == 409


def test_a_chapter_code_beginning_with_s_is_not_read_as_a_section():
    """X.MATH.SAV was read as section 'AV' and X.MATH.STATS as 'TATS'. Neither matched any
    concept family, so every question in those two chapters blocked -- on a rule that
    looked right and was checking only the first letter."""
    from app.api.marks import _section_number

    assert _section_number("X.MATH.STATS.S13_2") == "13.2"
    assert _section_number("X.SCI.LIGHT.S9_1") == "9.1"
    assert _section_number("X.MATH.SAV") is None
    assert _section_number("X.MATH.STATS") is None
    assert _section_number("X.MATH.CIRCLE") is None


# --- a person checks the extraction before anything treats it as fact ---------------------

def test_mapping_refuses_until_someone_has_confirmed_the_extraction(
    client, school, assessment, book
):
    """Everything after mapping treats these questions as what the paper says. An
    extraction nobody checked is not that -- it is a good guess that would become a mark on
    a child's report with no person in the loop."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    blocked = _map(client, f"/assessments/{assessment}/map", headers=_auth(school))
    assert blocked.status_code == 409
    assert "confirmed this extraction" in blocked.json()["detail"]

    ok = client.post(
        f"/assessments/{assessment}/scan/confirm", headers=_auth(school), json={"by": "Mrs Rani"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["confirmed_by"] == "Mrs Rani"

    mapped = _map(client, f"/assessments/{assessment}/map", headers=_auth(school))
    assert mapped.status_code == 200


def test_a_question_with_no_marks_cannot_be_confirmed_around(client, school, assessment):
    """A question worth nothing is a gap, not a question. Signing for it would put a name
    on something incomplete."""
    from app.db import SessionLocal
    from app.models import ScannedQuestion

    _upload(client, school, assessment, _paper_bytes(PAPER))
    db = SessionLocal()
    row = db.scalars(
        select(ScannedQuestion).where(ScannedQuestion.assessment_id == assessment)
    ).first()
    row.max_marks = None
    db.commit()
    address = row.address
    db.close()

    refused = client.post(f"/assessments/{assessment}/scan/confirm", headers=_auth(school), json={})
    assert refused.status_code == 422
    assert "carry no marks" in refused.json()["detail"]

    fixed = client.patch(
        f"/assessments/{assessment}/scan/{address}",
        headers=_auth(school), json={"max_marks": 3, "by": "Mrs Rani"},
    )
    assert fixed.status_code == 200
    assert fixed.json()["changed"] == ["max_marks"]

    assert client.post(
        f"/assessments/{assessment}/scan/confirm", headers=_auth(school), json={}
    ).status_code == 200


def test_a_row_the_extractor_invented_can_be_removed(client, school, assessment):
    """A heading read as a question is more common than any wrong field, and removing it
    is the edit a person reaches for first."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    before = client.get(f"/assessments/{assessment}/scan", headers=_auth(school)).json()
    victim = before["questions"][0]["address"]

    out = client.patch(
        f"/assessments/{assessment}/scan/{victim}", headers=_auth(school), json={"remove": True}
    )
    assert out.status_code == 200 and out.json()["removed"] is True

    after = client.get(f"/assessments/{assessment}/scan", headers=_auth(school)).json()
    assert after["staged"] == before["staged"] - 1


def test_editing_is_refused_once_the_extraction_is_confirmed(client, school, assessment):
    """Confirmation is a person putting their name to these rows. Editing afterwards would
    leave the record saying someone checked something they never saw."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    address = client.get(
        f"/assessments/{assessment}/scan", headers=_auth(school)
    ).json()["questions"][0]["address"]
    client.post(f"/assessments/{assessment}/scan/confirm", headers=_auth(school), json={})

    late = client.patch(
        f"/assessments/{assessment}/scan/{address}", headers=_auth(school), json={"max_marks": 9}
    )
    assert late.status_code == 409
    assert "already confirmed" in late.json()["detail"]


def test_rescanning_withdraws_the_previous_confirmation(client, school, assessment):
    """Whoever signed did not see these rows."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    client.post(f"/assessments/{assessment}/scan/confirm", headers=_auth(school), json={})
    assert client.get(
        f"/assessments/{assessment}/scan", headers=_auth(school)
    ).json()["confirmed_at"]

    _upload(client, school, assessment, _paper_bytes(PAPER))
    assert client.get(
        f"/assessments/{assessment}/scan", headers=_auth(school)
    ).json()["confirmed_at"] is None


def test_a_corrected_row_stays_distinguishable_from_one_the_machine_got_right(
    client, school, assessment
):
    """Different evidence about how well the extractor works. A system that cannot tell
    them apart cannot be improved."""
    _upload(client, school, assessment, _paper_bytes(PAPER))
    address = client.get(
        f"/assessments/{assessment}/scan", headers=_auth(school)
    ).json()["questions"][0]["address"]

    client.patch(
        f"/assessments/{assessment}/scan/{address}",
        headers=_auth(school), json={"max_marks": 4, "by": "Mrs Rani"},
    )
    read = client.get(f"/assessments/{assessment}/scan", headers=_auth(school)).json()
    assert read["edited"] == 1
    edited = [q for q in read["questions"] if q["edited_by"]]
    assert [q["edited_by"] for q in edited] == ["Mrs Rani"]


# --- one page or many, PDFs or photographs -------------------------------------------------

def _one_page_pdf(lines):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text in lines:
        page.insert_text((x, y), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def _png(colour=(255, 255, 255)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (595, 842), colour).save(buf, "PNG")
    return buf.getvalue()


def test_several_pdf_pages_are_read_as_one_paper(client, school, assessment):
    first = _one_page_pdf([
        (60, 90, "SECTION A"),
        (60, 130, "1. First question on the first page."), (MARK_X, 130, "2"),
    ])
    second = _one_page_pdf([
        (60, 90, "2. Second question, on a separate page."), (MARK_X, 90, "3"),
    ])
    r = _upload_many(client, school, assessment, [
        ("p1.pdf", first, "application/pdf"),
        ("p2.pdf", second, "application/pdf"),
    ])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["pages"] == 2
    assert body["questions"] == 2
    assert body["total_marks"] == 5.0


def test_the_order_sent_is_the_order_read_not_the_filename_order(client, school, assessment):
    """A phone names photographs by the second they were taken and a scanner by a counter
    that resets. Sorting by name reorders a paper silently, and a paper read out of order
    produces question numbers that look plausible and are wrong."""
    page_one = _one_page_pdf([
        (60, 90, "SECTION A"),
        (60, 130, "1. This is the first question."), (MARK_X, 130, "1"),
    ])
    page_two = _one_page_pdf([(60, 90, "2. This is the second question."), (MARK_X, 90, "1")])

    r = _upload_many(client, school, assessment, [
        ("zzz-taken-first.pdf", page_one, "application/pdf"),
        ("aaa-taken-second.pdf", page_two, "application/pdf"),
    ])
    assert r.status_code == 201, r.text
    read = client.get(f"/assessments/{assessment}/scan", headers=_auth(school)).json()
    assert [q["question_no"] for q in read["questions"]] == ["1", "2"]
    assert [q["page"] for q in read["questions"]] == [1, 2]


def test_a_photograph_is_accepted_and_routed_to_vision(client, school, assessment):
    """A teacher photographing a paper has JPEGs, not a PDF. The image is accepted and
    queued for a vision read rather than rejected outright -- which is a different
    outcome from 'wrong file type', and the difference matters to whoever is standing
    there. With no Anthropic key configured, that queued job then fails cleanly."""
    r = _upload_many(client, school, assessment, [("page1.png", _png(), "image/png")])
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    job = client.get(f"/assessments/{assessment}/scan/jobs/{job_id}", headers=_auth(school))
    assert job.status_code == 422, job.text
    assert "cannot be read" in job.text


def test_a_file_that_is_neither_says_which_one(client, school, assessment):
    r = _upload_many(
        client, school, assessment, [("notes.docx", b"PK\x03\x04zzz", "application/octet-stream")]
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "notes.docx" in detail and "not a PDF or an image" in detail


def test_an_empty_page_is_named_rather_than_silently_skipped(client, school, assessment):
    good = _one_page_pdf([(60, 90, "SECTION A"), (60, 130, "1. A question."), (MARK_X, 130, "1")])
    r = _upload_many(client, school, assessment, [
        ("good.pdf", good, "application/pdf"),
        ("blank.pdf", b"", "application/pdf"),
    ])
    assert r.status_code == 422
    assert "blank.pdf is empty" in r.json()["detail"]


# ----------------------------------------------------------------------------------------
# Sub-part marks, through HTTP
# ----------------------------------------------------------------------------------------
#: A case study: a paragraph of context, then parts worth 1, 1 and 2. Read as one question
#: it is worth 1, and the paper is four marks short with nothing on screen to show it.
CASE_STUDY = [[
    (60, 60, "Maximum Marks: 6"),
    (60, 90, "SECTION A"),
    (60, 120, "1. Find the mean of the grouped data by the"),
    (60, 134, "step-deviation method, assumed mean 200."),
    (MARK_X, 120, "2"),
    (60, 200, "SECTION E"),
    (60, 230, "2. A dairy packs milk in sealed vessels shaped like a cylinder"),
    (60, 244, "with two hemispherical ends of the same radius."),
    (60, 274, "(i) Find the length of the cylindrical portion."),
    (MARK_X, 274, "1"),
    (60, 304, "(ii) Find the curved surface area of the cylinder."),
    (MARK_X, 304, "1"),
    (60, 334, "(iii) Find the total surface area of the vessel."),
    (MARK_X, 334, "2"),
]]


@pytest.fixture
def case_study_assessment(client, school):
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Case study", "total_marks": 6},
    )
    return r.json()["assessment_id"]


def test_each_sub_part_is_staged_with_its_own_marks(client, school, case_study_assessment):
    out = _upload(client, school, case_study_assessment, _paper_bytes(CASE_STUDY))
    assert out.status_code == 201, out.text
    body = out.json()

    assert body["total_marks"] == 6
    assert body["declared"]["total_marks"] == 6
    assert body["sub_parts"] == 3
    assert body["problems"] == []

    read = client.get(
        f"/assessments/{case_study_assessment}/scan", headers=_auth(school)
    ).json()
    marks = {q["address"]: q["max_marks"] for q in read["questions"]}
    assert marks["E/2/i/"] == 1
    assert marks["E/2/ii/"] == 1
    assert marks["E/2/iii/"] == 2
    assert read["marks"] == {"read": 6.0, "declared": 6.0, "short_by": 0.0}


def test_a_shared_stem_does_not_block_the_scan_from_being_confirmed(
    client, school, case_study_assessment
):
    """The paragraph above (i), (ii), (iii) carries no marks and is not a gap."""
    _upload(client, school, case_study_assessment, _paper_bytes(CASE_STUDY))
    read = client.get(
        f"/assessments/{case_study_assessment}/scan", headers=_auth(school)
    ).json()
    assert read["marks_missing"] == 0
    context = [q for q in read["questions"] if q["is_context"]]
    assert [q["address"] for q in context] == ["E/2//"]

    out = client.post(
        f"/assessments/{case_study_assessment}/scan/confirm",
        headers=_auth(school), json={},
    )
    assert out.status_code == 200, out.text
    assert out.json()["total_marks"] == 6


def test_confirming_is_refused_while_the_marks_do_not_add_up(client, school):
    """The guardrail the totals exist for.

    Every row here is readable and looks right. The paper is simply short, because a
    sub-part's marks were never found -- and a report built on it would understate what
    the student was asked, silently.
    """
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Short", "total_marks": 80},
    )
    aid = r.json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(PAPER))

    out = client.post(f"/assessments/{aid}/scan/confirm", headers=_auth(school), json={})
    assert out.status_code == 422
    detail = out.json()["detail"]
    assert "worth 80 marks" in detail and "add up to 8" in detail
    assert "72 are missing" in detail
    # And it says where to look, because "the totals disagree" is not actionable.
    assert "(i), (ii), (iii)" in detail


def test_the_marks_a_person_corrects_are_what_the_total_is_held_to(client, school):
    """Editing a row's marks has to move the total, or the check cannot be satisfied."""
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Fixable", "total_marks": 10},
    )
    aid = r.json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(PAPER))
    assert client.post(
        f"/assessments/{aid}/scan/confirm", headers=_auth(school), json={}
    ).status_code == 422

    # The paper really is worth 10: question 2 is a 7-mark question read as 5.
    fix = client.patch(
        f"/assessments/{aid}/scan/A/2//", headers=_auth(school), json={"max_marks": 7},
    )
    assert fix.status_code == 200, fix.text

    out = client.post(f"/assessments/{aid}/scan/confirm", headers=_auth(school), json={})
    assert out.status_code == 200, out.text
    assert out.json()["total_marks"] == 10


def test_the_marks_a_student_was_asked_for_count_a_choice_once(client, school):
    """A question printed as "(a) ... OR ... (b)" is worth its marks once.

    Adding both halves doubled what the sheet said the student was asked for; counting
    only the (a) half lost the marks entirely when the student answered (b) and (a) was
    marked as not offered, which is the normal way round.
    """
    from app.api.marks import _available

    rows = [
        {"section": "B", "question_no": "22", "sub_part": None, "choice_alt": "a",
         "max_marks": 2.0, "state": "not_offered"},
        {"section": "B", "question_no": "22", "sub_part": None, "choice_alt": "b",
         "max_marks": 2.0, "state": "awarded"},
        {"section": "A", "question_no": "1", "sub_part": None, "choice_alt": None,
         "max_marks": 1.0, "state": "awarded"},
    ]
    assert _available(rows) == 3.0

    # Untouched, both halves still count the question once.
    for row in rows:
        row["state"] = None
    assert _available(rows) == 3.0

    # A question the student was not asked at all counts for nothing.
    rows[2]["state"] = "not_offered"
    assert _available(rows) == 2.0


# ----------------------------------------------------------------------------------------
# Chapter, topic, sub-topic
#
# A book chunk is stored against its chapter with the section recorded beside it, which is
# what the ingest writes. Recovering the section from the node the chunk hangs off worked
# in this suite and never in production, where every chunk hangs off its chapter.
# ----------------------------------------------------------------------------------------
STATS_PAPER = [[
    (60, 60, "Maximum Marks: 3"),
    (60, 100, "SECTION A"),
    (60, 130, "1. Find the mean of the grouped data by the step-deviation"),
    (60, 144, "method with an assumed mean of 200 and a class size h."),
    (MARK_X, 130, "3"),
]]


def test_a_mapped_question_gets_a_chapter_a_topic_and_a_sub_topic(client, school, book):
    """All three, and each from the book rather than from anybody's memory."""
    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Topics", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(STATS_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})

    out = _map(client, f"/assessments/{aid}/map", headers=h)
    assert out.status_code == 200, out.text
    assert out.json()["mapped"] == 1
    assert out.json()["with_topic"] == 1

    placed = client.get(f"/assessments/{aid}/scan", headers=h).json()["questions"][0]
    assert placed["blocked_reason"] is None
    assert placed["mapped_to"]["chapter"] == "Statistics"
    assert placed["mapped_to"]["curriculum_section"] == "13.2"
    assert placed["mapped_to"]["topic"] == "Mean of Grouped Data"
    assert placed["mapped_to"]["concept_family"] == "Mean by step-deviation"
    assert placed["mapped_to"]["board_unit"] == "Statistics & Probability"


def test_map_lets_the_topic_judge_choose_the_section_within_the_retrieved_chapter(
    client, school, book, monkeypatch
):
    """Chapter retrieval is unchanged; the topic within it is the judge's. Retrieval
    reads 'mean' and says 13.2, the judge (stubbed) says 13.3: the judge's section and
    heading land on the question, the family follows, and the disagreement is flagged."""
    h = _auth(school)
    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    class StubTopicJudge:
        def __init__(self, *a, **kw) -> None:
            pass

        def pick(self, stem, chapter_label, headings, passages):
            assert chapter_label == "Statistics"
            assert set(headings) >= {"13.2", "13.3"}

            class _Choice:
                section = "13.3"
                rationale = "the question is really about the mode"

            return _Choice()

    monkeypatch.setattr("app.classify.topic.TopicJudge", StubTopicJudge)

    # A family that claims the mode section, so the family can follow the judge's
    # section the way it does in production (where every section has one).
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import ConceptFamilyProposal, TaxonomyNode

    db = SessionLocal()
    try:
        stats = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.STATS"))
        if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.MODE")) is None:
            db.add(TaxonomyNode(
                kind="concept_family", code="X.MATH.CF.MODE", label="Mode of grouped data",
                parent_id=stats.id, path="X.MATH.CF.MODE",
                curriculum_version=stats.curriculum_version,
            ))
            db.add(ConceptFamilyProposal(
                curriculum_version=stats.curriculum_version, subject_code="X.MATH",
                run_id="fixture", source="llm", model="fixture",
                code="X.MATH.CF.MODE", label="Mode of grouped data",
                chapter_id=stats.id, evidence=["Section 13.3"], from_sections=["13.3"],
            ))
            db.commit()
    finally:
        db.close()

    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Judged topic", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(STATS_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})
    out = _map(client, f"/assessments/{aid}/map", headers=h)
    assert out.status_code == 200, out.text
    assert out.json()["mapped"] == 1

    placed = client.get(f"/assessments/{aid}/scan", headers=h).json()["questions"][0]
    assert placed["mapped_to"]["chapter"] == "Statistics"
    assert placed["mapped_to"]["curriculum_section"] == "13.3"
    assert placed["mapped_to"]["topic"] == "Mode of Grouped Data"
    assert placed["mapped_to"]["concept_family"] == "Mode of grouped data"
    assert placed["mapped_to"]["needs_review"] is True
    assert "Topic 13.3 (Mode of Grouped Data)" in placed["mapped_to"]["review_reason"]
    assert "pointed at section 13.2" in placed["mapped_to"]["review_reason"]


def test_the_topic_is_recorded_as_a_skill_so_the_report_can_group_by_it(
    client, school, book
):
    """Without this row a mapped question tested no sub-topic and every finding fell back
    to the chapter, which is too coarse to act on."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Question, QuestionSkill, TaxonomyNode

    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Skills", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(STATS_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})
    _map(client, f"/assessments/{aid}/map", headers=h)

    db = SessionLocal()
    try:
        question = db.scalar(select(Question).where(Question.assessment_id == aid))
        links = list(db.scalars(
            select(QuestionSkill).where(QuestionSkill.question_id == question.id)
        ))
        assert [db.get(TaxonomyNode, s.node_id).label for s in links] == [
            "Mean of Grouped Data"
        ]
        assert links[0].source == "retrieval"
    finally:
        db.close()


def test_the_cognitive_category_is_null_until_something_has_read_the_question(
    client, school, book
):
    """Which tier a question sits in is not visible in its address or its marks.

    Retrieval places a question in the book; it does not judge what the question asks a
    student to DO. Reporting a tier here would be inventing one, so the field stays null
    and the screen says it is not classified rather than showing a plausible letter.
    """
    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Tier", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(STATS_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})
    _map(client, f"/assessments/{aid}/map", headers=h)

    placed = client.get(f"/assessments/{aid}/scan", headers=h).json()["questions"][0]
    assert placed["mapped_to"]["tier"] is None
    assert placed["mapped_to"]["tier_label"] is None


def test_a_person_settling_a_tier_is_recorded_where_the_report_reads_it(
    client, school, book
):
    """The judge and a teacher both wrote the tier onto the placement, and every report
    reads it from the append-only tier row, so no tier ever reached a report."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Question, QuestionTier

    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Settle", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(STATS_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})
    _map(client, f"/assessments/{aid}/map", headers=h)

    db = SessionLocal()
    question_id = db.scalar(select(Question).where(Question.assessment_id == aid)).id
    db.close()

    out = client.post(
        f"/assessments/{aid}/review/{question_id}", headers=h,
        json={
            "chapter_code": "X.MATH.STATS",
            "curriculum_section": "13.2",
            "tier": "Applying",
            "reviewed_by": "Mrs Rani",
        },
    )
    assert out.status_code == 200, out.text

    db = SessionLocal()
    try:
        rows = list(db.scalars(
            select(QuestionTier).where(QuestionTier.question_id == question_id)
        ))
        # Stored as the short code, which is what the report groups by and all the column
        # has room for.
        assert [r.tier for r in rows] == ["AP"]
        assert rows[0].source == "human"
    finally:
        db.close()

    placed = client.get(f"/assessments/{aid}/scan", headers=h).json()["questions"][0]
    assert placed["mapped_to"]["tier"] == "AP"
    assert placed["mapped_to"]["tier_label"] == "Applying"


def test_a_tier_that_is_not_a_tier_is_refused(client, school, book):
    """The vocabulary is closed. A paraphrase of a tier is not a tier."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Question

    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Bad tier", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(STATS_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})
    _map(client, f"/assessments/{aid}/map", headers=h)

    db = SessionLocal()
    question_id = db.scalar(select(Question).where(Question.assessment_id == aid)).id
    db.close()

    out = client.post(
        f"/assessments/{aid}/review/{question_id}", headers=h,
        json={"chapter_code": "X.MATH.STATS", "tier": "hard", "reviewed_by": "x"},
    )
    assert out.status_code == 422
    assert "is not a tier" in out.json()["detail"]


# ----------------------------------------------------------------------------------------
# Choosing between the families a chapter has
# ----------------------------------------------------------------------------------------
def test_the_narrowest_family_claiming_the_section_is_taken_and_flagged(
    client, school, book
):
    """A run proposes many families per chapter and several draw on one section.

    Taking whichever came first was arbitrary and unstable: the same paper could map two
    ways. The family claiming fewest sections is the closest fit for a question in one of
    them, ties break on the code so a second run agrees with the first, and the placement
    says a person should settle it rather than presenting the pick as decided.
    """
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import ConceptFamilyProposal, QuestionPlacement, TaxonomyNode

    db = SessionLocal()
    stats = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.STATS"))
    # A second family for Statistics that also draws on 13.2, plus two others.
    for code, label, sections in [
        ("X.MATH.CF.CENTRAL_TENDENCY", "Measures of central tendency", ["13.2", "13.3"]),
        ("X.MATH.CF.MEAN_DIRECT", "Mean by the direct method", ["13.2"]),
    ]:
        db.add(TaxonomyNode(
            kind="concept_family", code=code, label=label, parent_id=stats.id,
            path=code, curriculum_version=stats.curriculum_version,
        ))
        db.add(ConceptFamilyProposal(
            curriculum_version=stats.curriculum_version, subject_code="X.MATH",
            run_id="t", source="llm", model="t", code=code, label=label,
            chapter_id=stats.id, evidence=[], from_sections=sections,
        ))
    db.commit()
    db.close()

    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Ambiguous", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(STATS_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})
    out = _map(client, f"/assessments/{aid}/map", headers=h)
    assert out.status_code == 200, out.text
    assert out.json()["mapped"] == 1

    placed = client.get(f"/assessments/{aid}/scan", headers=h).json()["questions"][0]

    db = SessionLocal()
    try:
        # Whatever else this shared database holds, the family taken has to be one that
        # actually claims the section the question was placed in.
        claimants = {
            db.scalar(
                select(TaxonomyNode).where(TaxonomyNode.code == row.code)
            ).label
            for row in db.scalars(select(ConceptFamilyProposal))
            if "13.2" in (row.from_sections or [])
        }
        assert placed["mapped_to"]["curriculum_section"] == "13.2"
        assert placed["mapped_to"]["concept_family"] in claimants

        placement = db.scalar(
            select(QuestionPlacement)
            .order_by(QuestionPlacement.created_at.desc())
        )
        assert placement.needs_review is True
        assert "draw on section 13.2" in placement.reasoning
        assert "a person should settle it" in placement.reasoning
    finally:
        db.close()


def test_applying_a_proposal_marks_it_applied_rather_than_copying_it(client, school):
    """A run can propose hundreds and nothing said which had been acted on."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import ConceptFamilyProposal, TaxonomyNode

    db = SessionLocal()
    chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.PROB"))
    db.add(ConceptFamilyProposal(
        curriculum_version=chapter.curriculum_version, subject_code="X.MATH",
        run_id="r", source="llm", model="m", code="X.MATH.CF.CLASSICAL_PROBABILITY",
        label="Classical probability formula", chapter_id=chapter.id,
        evidence=[], from_sections=["14.2"],
    ))
    db.commit()
    db.close()

    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = "families-test-key"
    out = client.post(
        "/platform/books/X.MATH/concept-families",
        headers={"X-Platform-Key": "families-test-key"},
        json={"families": [{
            "code": "X.MATH.CF.CLASSICAL_PROBABILITY",
            "label": "Classical probability formula",
            "chapter_code": "X.MATH.PROB",
            "from_sections": ["14.2"],
        }]},
    )
    settings.platform_admin_key = before
    assert out.status_code == 201, out.text
    assert out.json()["created"] == 1

    db = SessionLocal()
    try:
        rows = list(db.scalars(select(ConceptFamilyProposal).where(
            ConceptFamilyProposal.code == "X.MATH.CF.CLASSICAL_PROBABILITY"
        )))
        # One row, stamped -- not a second copy of what a run already worked out.
        assert len(rows) == 1
        assert rows[0].applied_at
        assert rows[0].source == "llm"
    finally:
        db.close()


def test_a_section_that_is_a_sentence_is_not_stored_as_a_section():
    """One run answered "Section on spherical mirror introduction". Kept, it would sit in
    the list forever matching nothing; guessed at, it would match the wrong thing."""
    from app.api.books import clean_sections

    assert clean_sections(["13.2", "Section on spherical mirror introduction"]) == ["13.2"]
    assert clean_sections(["4.3.1", "4.3.1", None, ""]) == ["4.3.1"]
    assert clean_sections([]) == []


def test_a_bare_section_number_is_kept_not_only_a_dotted_one():
    """The bug this fixes: a book whose chapters are not further subdivided (measured on
    a Tamil literature book -- every chapter is one section, numbered plainly "1", never
    NCERT's "1.1") had its section silently stripped to nothing, because the pattern used
    to require a dot. Every chunk in such a chapter, and every family proposed from it,
    lost its section this way -- indistinguishable downstream from a chapter that never
    had one, which is exactly what produced "N families exist and none claims section 1"
    on every single question, even though the model had read "1" correctly every time. A
    free-text answer must still be rejected, dot or no dot."""
    from app.api.books import clean_sections

    assert clean_sections(["1"]) == ["1"]
    assert clean_sections(["1", "13.2"]) == ["1", "13.2"]
    assert clean_sections(["Section on spherical mirror introduction"]) == []


# ----------------------------------------------------------------------------------------
# The judge's verdict settling the question
#
# The judge exists because retrieval cannot tell a question ABOUT a theorem from the
# theorem. Its answer was written only as a placement, and every report prefers what the
# question itself carries -- so the correction was recorded and then ignored.
# ----------------------------------------------------------------------------------------
def _place_with(monkeypatch, chapter: str, section: str | None, tier: str | None):
    """Run the classify step with a stub judge, so no request is made and no money spent."""
    from app.classify.judge import Classification

    class StubJudge:
        violations: list = []

        def __init__(self, *a, **kw) -> None:
            pass

        def classify(self, question, evidence):
            return Classification(
                chapter=chapter, curriculum_section=section, tier=tier,
                skill_required="reading a grouped frequency table",
                reasoning="the passage defines the modal class", confidence=0.9,
            )

    class AbstainingTopicJudge:
        """No request either: the chapter judge's own section then stands."""

        def __init__(self, *a, **kw) -> None:
            pass

        def pick(self, stem, chapter_label, headings, passages):
            class _Choice:
                section = "none"
                rationale = "stub"

            return _Choice()

    monkeypatch.setattr("app.classify.anthropic_judge.AnthropicJudge", StubJudge)
    monkeypatch.setattr("app.classify.topic.TopicJudge", AbstainingTopicJudge)
    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = "test-key"
    return settings, before


def test_the_judge_settles_the_chapter_topic_and_sub_topic_on_the_question(
    client, school, book, monkeypatch
):
    """All three land where the report reads them, not only in the placement history."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Question, TaxonomyNode

    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Judged", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(STATS_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})
    _map(client, f"/assessments/{aid}/map", headers=h)

    # The judge disagrees with retrieval: it says the mode section, not the mean section.
    settings, before = _place_with(monkeypatch, "Statistics", "13.3", "Applying")
    try:
        # Placement now queues a job rather than answering directly (a classifier call
        # per question would otherwise outrun a real request's timeout) -- but TestClient
        # runs the background task inline before handing back the 202, so a single poll
        # right after already sees "succeeded".
        out = client.post(f"/assessments/{aid}/place", headers=h)
        assert out.status_code == 202, out.text
        job = client.get(
            f"/assessments/{aid}/place/jobs/{out.json()['job_id']}", headers=h
        )
    finally:
        settings.anthropic_api_key = before
    assert job.status_code == 200, job.text
    body = job.json()
    assert body["status"] == "succeeded"
    assert body["labelled"] == 1
    assert body["tiers"] == 1

    db = SessionLocal()
    try:
        question = db.scalar(select(Question).where(Question.assessment_id == aid))
        # The question itself carries the judge's answer, which is what a report reads.
        assert question.curriculum_section == "13.3"
        assert db.get(TaxonomyNode, question.chapter_id).label == "Statistics"
        # And the sub-topic was re-chosen for the section the judge landed on, rather
        # than left pointing at the one retrieval had picked.
        family = db.get(TaxonomyNode, question.concept_family_id)
        assert "13.3" in _sections_for(db, family.code)
        assert question.skill_required == "reading a grouped frequency table"
    finally:
        db.close()

    # And the category reaches the screen.
    placed = client.get(f"/assessments/{aid}/scan", headers=h).json()["questions"][0]
    assert placed["mapped_to"]["tier"] == "AP"
    assert placed["mapped_to"]["tier_label"] == "Applying"


def _sections_for(db, code: str) -> set[str]:
    from sqlalchemy import select

    from app.models import ConceptFamilyProposal

    row = db.scalar(
        select(ConceptFamilyProposal).where(ConceptFamilyProposal.code == code)
    )
    return set(row.from_sections or []) if row else set()


def test_a_judge_that_abstains_on_the_tier_leaves_it_unset(
    client, school, book, monkeypatch
):
    """Abstaining is a legitimate answer and the only honest one when the evidence does
    not settle which tier a question belongs to. It must not read as a decided tier."""
    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Abstained", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(STATS_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})
    _map(client, f"/assessments/{aid}/map", headers=h)

    settings, before = _place_with(monkeypatch, "Statistics", "13.2", None)
    try:
        out = client.post(f"/assessments/{aid}/place", headers=h)
        assert out.status_code == 202, out.text
        job = client.get(
            f"/assessments/{aid}/place/jobs/{out.json()['job_id']}", headers=h
        )
    finally:
        settings.anthropic_api_key = before
    assert job.status_code == 200, job.text
    assert job.json()["tiers"] == 0

    scan = client.get(f"/assessments/{aid}/scan", headers=h).json()
    assert scan["questions"][0]["mapped_to"]["tier"] is None
    # Classify ran and simply abstained -- that must read differently from "classify was
    # never run at all", which is what the paper screen uses to decide whether it still
    # has to offer "Read and classify" on a paper someone reopens after leaving mid-flow.
    assert scan["classified"] is True


def test_the_classified_flag_is_false_until_a_classify_pass_has_actually_run(
    client, school, book, monkeypatch
):
    """Mapping alone -- placing a question in a chapter -- is not classifying it: the
    category comes from a separate reading, and reopening a paper that was only ever
    mapped must not claim classify already happened."""
    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Only mapped", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(STATS_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})
    _map(client, f"/assessments/{aid}/map", headers=h)

    assert client.get(f"/assessments/{aid}/scan", headers=h).json()["classified"] is False

    settings, before = _place_with(monkeypatch, "Statistics", "13.2", "Understanding")
    try:
        out = client.post(f"/assessments/{aid}/place", headers=h)
        client.get(f"/assessments/{aid}/place/jobs/{out.json()['job_id']}", headers=h)
    finally:
        settings.anthropic_api_key = before

    assert client.get(f"/assessments/{aid}/scan", headers=h).json()["classified"] is True


def test_classifying_is_refused_without_a_key_rather_than_guessing(client, school, book):
    """Retrieval places a question in the book; it does not judge what the question asks a
    student to do. Without the classifier there is no category, and saying so is the whole
    of the honest answer."""
    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "No key", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(STATS_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})
    _map(client, f"/assessments/{aid}/map", headers=h)

    settings = get_settings()
    before = settings.anthropic_api_key
    settings.anthropic_api_key = None
    try:
        out = client.post(f"/assessments/{aid}/place", headers=h)
    finally:
        settings.anthropic_api_key = before
    assert out.status_code == 409
    assert "no classifier key configured" in out.json()["detail"]


# ----------------------------------------------------------------------------------------
# Fix 1: the book_map's own real section numbering vs. a stale taxonomy_node subtopic that
# happens to claim the same small integer for a completely different heading.
# ----------------------------------------------------------------------------------------
POLITICAL_PARTIES_PAPER = [[
    (60, 60, "Maximum Marks: 3"),
    (60, 100, "SECTION A"),
    (60, 130, "1. Explain how the zamgani conclave reformed prazil selection using"),
    (60, 144, "the tovenoc quorum and the ravelston seniority rule."),
    (MARK_X, 130, "3"),
]]


@pytest.fixture
def political_parties_book_map(school):
    """A book_map-style seed for a private X.POL chapter: a real BookChunk at section "6"
    whose reference is the book's own heading, plus a STALE taxonomy_node(kind='subtopic')
    that also claims section "6" but under a different, unrelated label -- reproducing
    exactly the two disconnected numbering schemes the audit found colliding in
    production.

    Lives under its own chapter code, never a real X.POL.* chapter, so it cannot collide
    with the real "sst_polsci_political_parties.pdf" regression fixture another test in
    this same shared, session-scoped database may already have uploaded (real section
    numbers there are the book's own, not the "6" this fixture picks for the test).
    """
    from sqlalchemy import select

    from app.curriculum import X_POLITICAL_SCIENCE
    from app.curriculum.apply import apply as apply_curriculum
    from app.db import SessionLocal
    from app.models import BookChunk, ChapterBoardUnit, ConceptFamilyProposal, TaxonomyNode

    db = SessionLocal()
    apply_curriculum(db, X_POLITICAL_SCIENCE)
    db.commit()

    subject = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.POL"))
    unit = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.POL.U.WHOLE"))
    version = subject.curriculum_version

    chapter_code = "X.POL.TESTREFORM"
    chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == chapter_code))
    if chapter is None:
        chapter = TaxonomyNode(
            kind="chapter", code=chapter_code, label="Political Parties (test)",
            parent_id=subject.id, path=chapter_code, curriculum_version=version,
        )
        db.add(chapter)
        db.flush()
        db.add(ChapterBoardUnit(
            curriculum_version=version, chapter_id=chapter.id, board_unit_id=unit.id,
        ))

    other_code = "X.POL.TESTPOWERSHARING"
    other = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == other_code))
    if other is None:
        other = TaxonomyNode(
            kind="chapter", code=other_code, label="Power-sharing (test)",
            parent_id=subject.id, path=other_code, curriculum_version=version,
        )
        db.add(other)
        db.flush()
        db.add(ChapterBoardUnit(
            curriculum_version=version, chapter_id=other.id, board_unit_id=unit.id,
        ))

    # The real book_map chunk: section "6" of this chapter, reference is the book's own
    # heading -- exactly what import_book_map.py writes.
    # Deliberately invented vocabulary, not real NCERT text: this test must not compete
    # for retrieval against whatever real "Political Parties" content another test in
    # this same shared, session-scoped database may have uploaded from the real
    # regression fixture -- rare, unique tokens keep it unambiguously distinct.
    db.add(BookChunk(
        curriculum_version=version, subject_code="X.POL",
        node_id=chapter.id, bucket="T", reference="6 How the zamgani conclave reforms",
        section_number="6",
        text=(
            "The zamgani conclave reformed prazil selection by adopting the tovenoc "
            "quorum and the ravelston seniority rule, limiting how a prazil could be "
            "chosen without a full zamgani vote."
        ),
        normalised="zamgani conclave reform prazil tovenoc quorum ravelston seniority",
        stem_hash="polparties-testreform-s6-body",
    ))
    # A second, contrasting chunk in a different (private) chapter so lexical retrieval
    # has more than one chapter's worth of content to score against.
    db.add(BookChunk(
        curriculum_version=version, subject_code="X.POL",
        node_id=other.id, bucket="T", reference="3 Why the wenlarid accord is desirable",
        section_number="3",
        text=(
            "The wenlarid accord is desirable because it splits authority between "
            "different orlenna councils and keeps any one bloc from dominating the "
            "kestrilan assembly."
        ),
        normalised="wenlarid accord orlenna council kestrilan assembly authority",
        stem_hash="polpowersharing-testreform-s3-body",
    ))
    # A third, unrelated chunk so TF-IDF has more than two documents to score against --
    # with exactly two, every term unique to one document gets idf = log(2/2) = 0 and
    # nothing is retrievable at all.
    db.add(BookChunk(
        curriculum_version=version, subject_code="X.POL",
        node_id=other.id, bucket="T", reference="2 The dalvorn representation gap",
        section_number="2",
        text=(
            "The dalvorn representation gap describes how few makreth delegates sit in "
            "the kestrilan assembly compared to their share of the orlenna population."
        ),
        normalised="dalvorn representation makreth delegate kestrilan assembly orlenna",
        stem_hash="polgender-testreform-s2-body",
    ))

    # The stale, pre-book_map subtopic node: same chapter, same section number "6", but a
    # completely different, unrelated heading -- left behind because import_book_map.py
    # never touches taxonomy_node(kind='subtopic') rows (see its own module docstring).
    stale_code = f"{chapter_code}.S6"
    if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == stale_code)) is None:
        db.add(TaxonomyNode(
            kind="subtopic", code=stale_code, label="A STALE, UNRELATED HEADING",
            parent_id=chapter.id, path=stale_code, curriculum_version=version,
        ))

    if db.scalar(
        select(TaxonomyNode).where(TaxonomyNode.code == "X.POL.CF.TESTPARTY_REFORM")
    ) is None:
        family = TaxonomyNode(
            kind="concept_family", code="X.POL.CF.TESTPARTY_REFORM",
            label="Reforming political parties", parent_id=chapter.id,
            path="X.POL.CF.TESTPARTY_REFORM", curriculum_version=version,
        )
        db.add(family)
        db.add(ConceptFamilyProposal(
            curriculum_version=version, subject_code="X.POL",
            run_id="book_map_import_v1", source="book_map", model=None,
            code="X.POL.CF.TESTPARTY_REFORM", label="Reforming political parties",
            chapter_id=chapter.id, evidence=["6"], from_sections=["6"],
        ))
    db.commit()
    db.close()


def test_map_uses_the_books_own_heading_not_a_mismatched_stale_subtopic_number(
    client, school, political_parties_book_map, monkeypatch
):
    """Fix 1: book_chunk section "6" and taxonomy_node subtopic "...S6" are two different,
    unrelated numbering schemes that happen to collide on the same small integer. The
    topic must come from the book_map chunk's own real heading, never from the stale
    number-matched taxonomy_node.

    Retrieval itself (which chunk best matches a question's wording) is a separate
    concern from this bug and is already covered elsewhere in this file; a real chapter
    in this shared, session-scoped test database can carry hundreds of chunks uploaded by
    other tests (real regression-fixture PDFs, some badly OCR'd), so lexical scoring
    across the whole suite is not deterministic enough to assert an exact section on.
    `locate` is patched here to hand back the chapter and section this fixture set up,
    exactly the shape a real winning verdict has, so the assertions below are actually
    about the topic-lookup bug rather than about how retrieval happened to score today.
    """
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.ingest.probe import ChapterVerdict
    from app.models import TaxonomyNode

    db = SessionLocal()
    chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.POL.TESTREFORM"))
    chapter_id = chapter.id
    db.close()

    def fake_locate(question, indexes, **kwargs):
        return ChapterVerdict(
            node_id=chapter_id, score=1.0, margin=1.0, agreed=True,
            evidence=[], runners_up=[], section="6",
        )

    import app.ingest.probe as probe

    monkeypatch.setattr(probe, "locate", fake_locate)

    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.POL", "title": "Political Parties", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(POLITICAL_PARTIES_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})

    out = _map(client, f"/assessments/{aid}/map", headers=h)
    assert out.status_code == 200, out.text

    placed = client.get(f"/assessments/{aid}/scan", headers=h).json()["questions"][0]
    assert out.json()["mapped"] == 1, (placed["blocked_reason"], placed["stem_text"])
    assert placed["blocked_reason"] is None
    assert placed["mapped_to"]["chapter"] == "Political Parties (test)"
    assert placed["mapped_to"]["curriculum_section"] == "6"
    # Before the fix this was "A STALE, UNRELATED HEADING" -- the number-matched but
    # semantically unrelated taxonomy_node. After the fix it is the book's own words.
    assert placed["mapped_to"]["topic"] == "6 How the zamgani conclave reforms"
    assert placed["mapped_to"]["topic"] != "A STALE, UNRELATED HEADING"


# ----------------------------------------------------------------------------------------
# Fix 2: an X.SST question's retrieval is scoped to its own section's subject
#
# CBSE's Class X Social Science paper is a fixed board layout, not a per-paper one:
# Section A is always History, B is always Geography, C is always Political Science
# ("Democratic Politics"), D is always Economics -- see _SST_SECTION_SUBJECT in
# app.api.marks. Each staged question already carries its own printed section letter
# (ScannedQuestion.section). Without scoping, retrieval searches all four books' chapters
# for every question, which is exactly how the audit found a History question landing in
# the Political Science chapter "Power-sharing" on nothing but shared vocabulary.
# ----------------------------------------------------------------------------------------


def test_sst_retrieval_is_scoped_to_the_questions_own_section_subject(
    client, school, monkeypatch,
):
    """locate() is patched to simply record which subjects its candidate chunks came
    from, rather than asserting on TF-IDF outcomes (fragile in this shared, session-scoped
    test database). What matters is the *scope* handed to retrieval: a Section A question
    must only ever see X.HIST chunks, never the other three books in the X.SST group --
    and a question whose section is unknown must still see the whole group, never be
    silently dropped or forced into a guessed subject.
    """
    from sqlalchemy import select

    from app.curriculum import X_ECONOMICS, X_GEOGRAPHY, X_HISTORY, X_POLITICAL_SCIENCE
    from app.curriculum.apply import apply as apply_curriculum
    from app.db import SessionLocal
    from app.ingest.probe import ChapterVerdict
    from app.models import BookChunk, ScannedQuestion, TaxonomyNode

    db = SessionLocal()
    for curriculum in (X_HISTORY, X_GEOGRAPHY, X_POLITICAL_SCIENCE, X_ECONOMICS):
        apply_curriculum(db, curriculum)
    db.commit()

    for subject_code, chapter_code in [
        ("X.HIST", "X.HIST.NATIONALISM_EUROPE"),
        ("X.GEO", "X.GEO.RESOURCES"),
        ("X.POL", "X.POL.POWERSHARING"),
        ("X.ECO", "X.ECO.DEVELOPMENT"),
    ]:
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == chapter_code))
        if db.scalar(select(BookChunk).where(
            BookChunk.stem_hash == f"sst-scope-test-{subject_code}"
        )) is None:
            db.add(BookChunk(
                curriculum_version=chapter.curriculum_version, subject_code=subject_code,
                node_id=chapter.id, bucket="T", reference="Test",
                text=f"placeholder {subject_code} body text",
                section_number="1",
                normalised=f"placeholder {subject_code} body text",
                stem_hash=f"sst-scope-test-{subject_code}",
            ))
    db.commit()
    db.close()

    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.SST", "title": "SST scope test", "total_marks": 5,
    }).json()["assessment_id"]

    rows = [
        ("A", "1", "History question stem, section A."),
        ("B", "2", "Geography question stem, section B."),
        ("C", "3", "Political science question stem, section C."),
        ("D", "4", "Economics question stem, section D."),
        (None, "5", "No section printed at all on this one."),
    ]
    expected = {
        "History question stem, section A.": {"X.HIST"},
        "Geography question stem, section B.": {"X.GEO"},
        "Political science question stem, section C.": {"X.POL"},
        "Economics question stem, section D.": {"X.ECO"},
        # unknown section -- never silently dropped, never force-scoped to a guess
        "No section printed at all on this one.": {"X.HIST", "X.GEO", "X.POL", "X.ECO"},
    }

    db2 = SessionLocal()
    for section, qno, stem in rows:
        db2.add(ScannedQuestion(
            assessment_id=aid, address=f"{section or ''}/{qno}//", section=section,
            question_no=qno, max_marks=1, stem_text=stem, logical_page=1,
        ))
    db2.commit()
    db2.close()

    confirm = client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})
    assert confirm.status_code == 200, confirm.text

    captured: dict[str, set[str]] = {}

    def fake_locate(query, indexes, **kwargs):
        subjects = {
            chunk.subject_code
            for idx in indexes
            for chunk in getattr(idx, "chunks", [])
        }
        captured[query] = subjects
        return ChapterVerdict(
            node_id=None, score=0.0, margin=0.0, agreed=False, evidence=[], runners_up=[],
        )

    import app.ingest.probe as probe

    monkeypatch.setattr(probe, "locate", fake_locate)

    mapped = _map(client, f"/assessments/{aid}/map", headers=h)
    assert mapped.status_code == 200, mapped.text

    assert captured == expected, captured


# ----------------------------------------------------------------------------------------
# Fix 4: exercise-bucket (bucket='E') chunks never compete with teaching-text (bucket='T')
# chunks for BEING the primary retrieval match that decides a question's chapter/section.
# import_book_map.py loads an exercise chunk with section_number=None (an end-of-chapter
# exercise references the whole chapter, not one section), so an exercise chunk winning
# retrieval on shared surface vocabulary alone produces a topicless placement even when a
# real teaching-text passage elsewhere would have matched correctly.
# ----------------------------------------------------------------------------------------
RETRIEVAL_GUARD_PAPER = [[
    (60, 60, "Maximum Marks: 3"),
    (60, 100, "SECTION A"),
    (60, 130, "1. Explain the velunca method for tiling quaprastic panels using"),
    (60, 144, "distinctive coverage."),
    (MARK_X, 130, "3"),
]]


@pytest.fixture
def retrieval_guard_book(school):
    """The real audit scenario, reproduced with invented vocabulary unique to this test so
    real regression-fixture content elsewhere in this shared, session-scoped database
    cannot compete: the correct chapter carries the real teaching-text (bucket='T')
    passage, and an entirely DIFFERENT, unrelated chapter carries only an exercise
    (bucket='E') chunk that happens to share more surface vocabulary with the question
    (it is built to repeat literally every term of the stem, plus extras) -- exactly how
    an "Exercise Q8" chunk can outscore the real passage and hijack chapter selection on
    nothing but shared words, per the audit ("Women and Print" landing on an unrelated
    exercise chunk). The unrelated chapter is deliberately left with no ChapterBoardUnit,
    so a pre-fix win for it blocks the question rather than mis-filing it -- either way
    the wrong-chapter failure is visible, never silently correct-looking.

    Chapter-level voting sums each chapter's own best-scoring evidence (see
    ``probe.locate``'s ``CORROBORATION_DEPTH``), so putting the exercise chunk in its own
    chapter -- rather than alongside the teaching chunk in the same one -- is what actually
    exposes the bug: two same-chapter candidates can never change which chapter wins.
    """
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import (
        BookChunk, ChapterBoardUnit, ConceptFamilyProposal, TaxonomyNode,
    )

    db = SessionLocal()
    subject = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH"))
    unit = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.U.NUMBER"))
    version = subject.curriculum_version

    chapter_code = "X.MATH.TESTRETRIEVALGUARD"
    chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == chapter_code))
    if chapter is None:
        chapter = TaxonomyNode(
            kind="chapter", code=chapter_code, label="Retrieval Guard (test)",
            parent_id=subject.id, path=chapter_code, curriculum_version=version,
        )
        db.add(chapter)
        db.flush()
        db.add(ChapterBoardUnit(
            curriculum_version=version, chapter_id=chapter.id, board_unit_id=unit.id,
        ))

    # A second, unrelated chapter -- no ChapterBoardUnit, so if this chapter wins
    # unfiltered, the question is blocked rather than mis-filed under it.
    other_code = "X.MATH.TESTRETRIEVALGUARDEXERCISE"
    other = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == other_code))
    if other is None:
        other = TaxonomyNode(
            kind="chapter", code=other_code, label="Unrelated Exercise Chapter (test)",
            parent_id=subject.id, path=other_code, curriculum_version=version,
        )
        db.add(other)
        db.flush()

    subtopic_code = f"{chapter_code}.S9_3"
    if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == subtopic_code)) is None:
        db.add(TaxonomyNode(
            kind="subtopic", code=subtopic_code, label="The velunca method (test)",
            parent_id=chapter.id, path=subtopic_code, curriculum_version=version,
        ))

    # bucket='T': the real teaching text, in the correct chapter. Shares most, not all, of
    # the question's terms.
    if db.scalar(select(BookChunk).where(
        BookChunk.stem_hash == "retrieval-guard-test-teaching"
    )) is None:
        db.add(BookChunk(
            curriculum_version=version, subject_code="X.MATH", node_id=chapter.id,
            bucket="T", reference="9.3 The velunca method", section_number="9.3",
            text=(
                "The velunca method tiles quaprastic panels through distinctive "
                "coverage, proved by induction on the panel count."
            ),
            normalised="velunca method tile quaprastic panel distinctive coverage induction",
            stem_hash="retrieval-guard-test-teaching",
        ))
    # bucket='E': an end-of-chapter exercise, filed under the UNRELATED chapter -- exactly
    # how import_book_map.py stores one (section_number=None) -- with text engineered to
    # repeat literally every term of the question stem, so unfiltered TF-IDF scores it
    # above the teaching chunk and it hijacks chapter selection entirely.
    if db.scalar(select(BookChunk).where(
        BookChunk.stem_hash == "retrieval-guard-test-exercise"
    )) is None:
        db.add(BookChunk(
            curriculum_version=version, subject_code="X.MATH", node_id=other.id,
            bucket="E", reference="Exercise 9.3 Q8", section_number=None,
            text=(
                "Exercise 8. Explain the velunca method for tiling quaprastic panels "
                "using distinctive coverage. Show your full working."
            ),
            normalised=(
                "exercise explain velunca method tiling quaprastic panel using "
                "distinctive coverage show full working"
            ),
            stem_hash="retrieval-guard-test-exercise",
        ))
    # Two more unrelated chunks elsewhere so TF-IDF has four documents, not two, to score
    # against: the words the teaching and exercise chunks share (velunca, method,
    # quaprastic, panels, distinctive, coverage) sit in exactly two of the corpus's
    # documents, and idf = log(n / (1+df)) collapses to log(2/2) = 0 -- silencing that
    # overlap entirely -- unless n is large enough that df=2 still gets a positive score
    # (log(4/3) here). Same reasoning as political_parties_book_map's third chunk above,
    # just needing one extra document because this fixture's shared terms sit in two docs
    # rather than one.
    for suffix, section, text in [
        ("a", "9.1", "An unrelated passage about zolwina fractions and their kestrum sums."),
        ("b", "9.2", "A second unrelated passage about worvellan ratios and hesk triangles."),
    ]:
        stem_hash = f"retrieval-guard-test-filler-{suffix}"
        if db.scalar(select(BookChunk).where(BookChunk.stem_hash == stem_hash)) is None:
            db.add(BookChunk(
                curriculum_version=version, subject_code="X.MATH", node_id=chapter.id,
                bucket="T", reference=f"{section} Unrelated filler (test)",
                section_number=section, text=text, normalised=text.lower(),
                stem_hash=stem_hash,
            ))

    if db.scalar(
        select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.TESTRETRIEVALGUARD")
    ) is None:
        db.add(TaxonomyNode(
            kind="concept_family", code="X.MATH.CF.TESTRETRIEVALGUARD",
            label="The velunca method (test family)", parent_id=chapter.id,
            path="X.MATH.CF.TESTRETRIEVALGUARD", curriculum_version=version,
        ))
        db.add(ConceptFamilyProposal(
            curriculum_version=version, subject_code="X.MATH",
            run_id="fixture", source="llm", model="fixture",
            code="X.MATH.CF.TESTRETRIEVALGUARD", label="The velunca method (test family)",
            chapter_id=chapter.id, evidence=["9.3"], from_sections=["9.3"],
        ))
    db.commit()
    db.close()


def test_exercise_bucket_chunks_never_win_retrieval_over_teaching_text(
    client, school, retrieval_guard_book,
):
    """Fix 4: bucket='E' chunks are excluded from the pool that decides chapter/section --
    left in, the exercise chunk here (in an unrelated chapter, built to share every term
    of the stem) outscores the real teaching passage and hijacks chapter selection
    entirely (the unrelated chapter has no board unit, so pre-fix this question is
    blocked rather than placed at all). After the fix, retrieval never sees the exercise
    chunk and falls through to the real teaching-text chapter and section.
    """
    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Retrieval guard", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(RETRIEVAL_GUARD_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})

    out = _map(client, f"/assessments/{aid}/map", headers=h)
    assert out.status_code == 200, out.text
    assert out.json()["mapped"] == 1, out.json()

    placed = client.get(f"/assessments/{aid}/scan", headers=h).json()["questions"][0]
    assert placed["blocked_reason"] is None
    assert placed["mapped_to"]["chapter"] == "Retrieval Guard (test)"
    # Before the fix, the exercise chunk (no section_number) could win and this would be
    # None -- the exact topicless failure the audit found.
    assert placed["mapped_to"]["curriculum_section"] == "9.3"
    assert placed["mapped_to"]["topic"] == "The velunca method (test)"


def test_map_never_hands_retrieval_an_exercise_bucket_chunk(
    client, school, retrieval_guard_book, monkeypatch,
):
    """Same fixture, but locate() is patched to simply record which buckets its candidate
    indexes actually carried -- the direct assertion that /map's retrieval pool excludes
    bucket='E' entirely, independent of how TF-IDF happens to score any particular pair of
    chunks.
    """
    from app.ingest.probe import ChapterVerdict

    captured: list[set[str]] = []

    def fake_locate(query, indexes, **kwargs):
        buckets = {
            chunk.bucket for idx in indexes for chunk in getattr(idx, "chunks", [])
        }
        captured.append(buckets)
        return ChapterVerdict(None, 0.0, 0.0, False, [], [])

    import app.ingest.probe as probe

    monkeypatch.setattr(probe, "locate", fake_locate)

    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Retrieval guard pool", "total_marks": 3,
    }).json()["assessment_id"]
    _upload(client, school, aid, _paper_bytes(RETRIEVAL_GUARD_PAPER))
    client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={})

    mapped = _map(client, f"/assessments/{aid}/map", headers=h)
    assert mapped.status_code == 200, mapped.text

    assert captured, "locate() was never called"
    for buckets in captured:
        assert "E" not in buckets, buckets


# ----------------------------------------------------------------------------------------
# Fix 5: Assertion-Reason boilerplate is stripped from the retrieval query only
#
# Four real Assertion-Reason questions from one production paper (A5/B13/C23/D32) share
# this exact framing verbatim, differing only in the Assertion/Reason content itself. The
# lead-in sentence and the four-option "which of these is true" block carry no book
# content and are stripped only from what is sent to retrieval -- never from stem_text,
# never from anything stored or shown to a teacher.
# ----------------------------------------------------------------------------------------

_AR_LEADIN = (
    "Two statements labelled as Assertion (A) and Reason (R) are given below. Read both "
    "the statements carefully and choose the correct option : "
)
_AR_OPTIONS = (
    "Options : (A) Both Assertion (A) and Reason (R) are true and Reason (R) is the "
    "correct explanation of Assertion (A). (B) Both Assertion (A) and Reason (R) are "
    "true, but Reason (R) is not the correct explanation of Assertion (A). (C) Assertion "
    "(A) is true, but Reason (R) is false. (D) Assertion (A) is false, but Reason (R) is "
    "true."
)


def _ar_question(assertion: str, reason: str) -> str:
    return (
        f"{_AR_LEADIN}Assertion (A) : {assertion} Reason (R) : {reason} {_AR_OPTIONS}"
    )


def test_assertion_reason_boilerplate_is_stripped_from_the_retrieval_query():
    from app.ingest.probe import retrieval_query_text

    # A5, verbatim.
    a5 = _ar_question(
        "The Roman Catholic Church began keeping an Index of Prohibited Books from the "
        "middle of the sixteenth century.",
        "The Church feared that the wide circulation of printed books would spread ideas "
        "that questioned its authority.",
    )
    query = retrieval_query_text(a5)

    # (a) the fixed boilerplate is gone from what is sent to retrieval
    assert "Two statements labelled as Assertion" not in query
    assert "Read both the statements carefully" not in query
    assert "Options :" not in query
    assert "correct explanation of Assertion (A)" not in query
    assert "Reason (R) is false" not in query

    # (b) the real Assertion/Reason content survives
    assert "Roman Catholic Church" in query
    assert "Index of Prohibited Books" in query
    assert "wide circulation of printed books" in query
    assert "questioned its authority" in query

    # never touch the stored/shown stem itself -- retrieval_query_text is pure
    assert a5 == _ar_question(
        "The Roman Catholic Church began keeping an Index of Prohibited Books from the "
        "middle of the sixteenth century.",
        "The Church feared that the wide circulation of printed books would spread ideas "
        "that questioned its authority.",
    )


def test_assertion_reason_stripping_works_on_all_four_real_paper_sections():
    """B13 (Geography), C23 (Political Science) and D32 (Economics) -- same fixed framing,
    different content, from the same real paper as A5 above."""
    from app.ingest.probe import retrieval_query_text

    cases = [
        (
            "Heavy industries and thermal power stations in India are located on or "
            "near the coalfields.",
            "Coal is a bulky material which loses weight on use as it is reduced to ash.",
        ),
        (
            "The law against defection has made it more difficult for members of a "
            "legislature to express dissent within their own party.",
            "An MLA or MP who changes parties now loses his or her seat in the "
            "legislature.",
        ),
        (
            "In the past few decades there has not been much increase in the movement "
            "of people between countries.",
            "Countries have placed various restrictions on the movement of people "
            "across their borders.",
        ),
    ]
    for assertion, reason in cases:
        raw = _ar_question(assertion, reason)
        query = retrieval_query_text(raw)
        assert "Options :" not in query
        assert "Two statements labelled" not in query
        assert assertion in query
        assert reason in query


def test_a_normal_questions_stem_is_completely_untouched():
    """No false-positive stripping: a question that merely happens to mention 'options'
    or 'assertion' in passing, or an ordinary stem with neither word, must come back
    byte-for-byte identical."""
    from app.ingest.probe import retrieval_query_text

    ordinary = "Find the mean of the grouped data by the step-deviation method."
    assert retrieval_query_text(ordinary) == ordinary

    mentions_but_not_the_pattern = (
        "Which of the following options best explains the assertion made by the "
        "author in the passage above?"
    )
    assert retrieval_query_text(mentions_but_not_the_pattern) == (
        mentions_but_not_the_pattern
    )

    assert retrieval_query_text("") == ""
    assert retrieval_query_text(None) is None


def _map(client, url: str, headers: dict):
    """POST /map now queues a job (202) and the result is read from its job row -- the
    same shape /place has. Pre-check failures still come back inline."""
    out = client.post(url, headers=headers)
    if out.status_code != 202:
        return out
    return client.get(f"{url}/jobs/{out.json()['job_id']}", headers=headers)
