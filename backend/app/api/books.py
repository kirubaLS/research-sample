"""Loading a subject's book through the browser.

Same extraction, same verification, same refusal to write a chapter that disagrees with
the contents page as `scripts.ingest_book` -- this is a second entry point to one pipeline,
not a second pipeline. It exists because a deployment without shell access still has to be
able to load a book, and the alternative was asking a school to run Python.

Order is enforced: the contents page first, because it is the oracle every chapter is
checked against, and a chapter accepted without it would be accepted on trust.
"""

from __future__ import annotations

import difflib
import re
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from sqlalchemy.orm import Session

from app.api.deps import require_platform_admin
from app.api.upload import to_tempfile
from app.config import get_settings
from app.curriculum import CURRICULA, chapter_title, subject_groups
from app.curriculum.apply import apply as apply_curriculum
from app.db import get_session
from app.ingest.book import (
    Section,
    chapter_number,
    extract_chapter,
    parse_toc,
    parse_toc_chapters,
    stem_hash,
    title_key,
    verify_against_toc,
    verify_structure,
)
from app.ingest.hindi_text import hindi_read_text
from sarvamai.core.api_error import ApiError as SarvamApiError
from app.ingest.embed import classify_familiarity
from app.ingest.probe import LexicalIndex, SemanticIndex, locate
from app.ingest.tamil_text import tamil_read_text, tamil_text_is_corrupted
from app.models import (
    BookChunk,
    BookSource,
    CanonicalProcedure,
    ChapterBoardUnit,
    ConceptFamilyProposal,
    IngestJob,
    SyllabusVersion,
    TaxonomyAlias,
    TaxonomyNode,
)

router = APIRouter(
    prefix="/platform/books", tags=["knowledge-base"],
    dependencies=[Depends(require_platform_admin)],
)


@router.get("")
@router.get("/")
def list_subjects(db: Session = Depends(get_session)) -> dict:
    """The subjects this deployment carries, and how far each one is loaded -- the
    console's own subject dropdown asks this, not a list written into the screen (see
    that screen's own comment on why).

    A near-duplicate of GET /admin/subjects, which this console used to call instead:
    that route requires `current_staff` (a real school's api_key, or a StaffKey), which a
    bare platform operator key was never one of, and never had to be until an unrelated
    fix (see app.api.deps.current_staff's own comment: "The operator key now opens only
    require_platform_admin") revoked the operator key's access to it -- silently
    breaking this exact screen's dropdown for a platform-only deployment with no school
    yet created. Its own docstring even promises "so the operator console isn't shut
    out", a promise that fix broke without anyone noticing here. A platform-scoped
    version, under this router's own require_platform_admin, doesn't have that
    dependency to break out from under it.
    """
    out = []
    for group in subject_groups():
        books = []
        group_chapters = group_board_units = group_chunks = group_embedded = 0
        for curriculum in group.members:
            chunks = db.scalar(
                select(func.count(BookChunk.id)).where(
                    BookChunk.subject_code == curriculum.subject_code
                )
            ) or 0
            embedded = db.scalar(
                select(func.count(BookChunk.id)).where(
                    BookChunk.subject_code == curriculum.subject_code,
                    BookChunk.embedding.isnot(None),
                )
            ) or 0
            books.append({
                "subject_code": curriculum.subject_code,
                "label": curriculum.subject_label,
                "grade": curriculum.grade,
                "chapters": len(curriculum.chapters),
                "board_units": len(curriculum.units),
                "book_loaded": embedded > 0,
                "chunks": chunks,
                "chunks_embedded": embedded,
            })
            group_chapters += len(curriculum.chapters)
            group_board_units += len(curriculum.units)
            group_chunks += chunks
            group_embedded += embedded
        out.append({
            "group_code": group.group_code,
            "group_label": group.group_label,
            "subject_code": group.group_code,
            "label": group.group_label,
            "grade": group.members[0].grade,
            "chapters": group_chapters,
            "board_units": group_board_units,
            "book_loaded": group_embedded > 0,
            "chunks": group_chunks,
            "chunks_embedded": group_embedded,
            "books": books,
        })
    return {"subjects": out}


def _subjects_with_families(db: Session) -> list[str]:
    """Every subject prefix that has at least one concept family: 'X.MATH.CF.X' -> 'X.MATH'."""
    out: set[str] = set()
    for n in db.scalars(select(TaxonomyNode).where(TaxonomyNode.kind == "concept_family")):
        head, sep, _ = n.code.partition(".CF.")
        if sep:
            out.add(head)
    return sorted(out)


# Declared before the /{subject} routes so 'audit' is never read as a subject code.
@router.get("/audit")
def audit_all_families(db: Session = Depends(get_session)) -> dict:
    """The family audit for every subject that has families, in one read."""
    reports = [_audit_families(db, subject) for subject in _subjects_with_families(db)]
    return {
        "subjects": [
            {
                "subject": r["subject"], "families": r["families"],
                "wrong_subject": len(r["wrong_subject"]), "empty_code": len(r["empty_code"]),
                "duplicates": len(r["duplicates"]), "removable": r["removable"],
                "kept_because_used": len(r["kept_because_used"]),
            }
            for r in reports
        ],
        "removable": sum(r["removable"] for r in reports),
    }


@router.post("/audit/apply")
def apply_all_family_audits(db: Session = Depends(get_session)) -> dict:
    """Apply the audit for every subject at once. Same rules as per subject: only
    wrong-subject and empty-code families that no question references are removed;
    duplicates are never touched."""
    results = [apply_family_audit(subject, db) for subject in _subjects_with_families(db)]
    return {
        "subjects": [
            {"subject": r["subject"], "removed": r["removed"],
             "kept_because_used": len(r["kept_because_used"]),
             "duplicates_left_for_review": r["duplicates_left_for_review"]}
            for r in results
        ],
        "removed": sum(r["removed"] for r in results),
    }

#: Below this gap to the runner-up, the top chapter won by a hair. On the 30(B) set the
#: single wrong answer had the smallest margin of any row, so this is where a question
#: should go to a human rather than into a report.
MIN_MARGIN = 0.002


_to_tempfile = to_tempfile

#: One subject code per physical Hindi book -- Kshitij, Kritika, Sparsh, Sanchayan -- same
#: reasoning as Social Science and English's X.ENG.* prefix.
HINDI_SUBJECT_PREFIX = "X.HIN"

#: Tamil (www.cbsetamil.com's own book) is not a second Hindi -- its PDF text layer is
#: genuine Unicode, just with a font-level glyph-repeat artifact app.ingest.tamil_text
#: corrects locally (see that module's own docstring). No OCR backend, no network round
#: trip, no multi-minute call to hold a DB session across -- it stays on the same
#: synchronous path Math/Science/English use, never IngestJob's 202/background path.
TAMIL_SUBJECT_PREFIX = "X.TAM"


def _hindi_text(pdf_bytes: bytes) -> str:
    """The book's real Unicode text, for a subject whose own PDF text layer decodes as
    mojibake (see app.ingest.hindi_ocr for why).

    Prefers Sarvam (Indic-specialised OCR) when a key is configured, then Tesseract when
    this deployment can run it, then Gemini -- see app.ingest.hindi_text for the full
    reasoning. Any failure is raised as a 409 or 502, never a bare 500: a missing
    key/binary is an operator setup step, not a broken upload, and a network failure
    already survived its own retries (Gemini's; Sarvam's own job API has no request-level
    retry to survive, so its errors reach here directly) before reaching here.
    """
    settings = get_settings()
    try:
        return hindi_read_text(
            pdf_bytes, gemini_api_key=settings.gemini_api_key, gemini_model=settings.gemini_model,
            sarvam_api_key=settings.sarvam_api_key, sarvam_language=settings.sarvam_language,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except SarvamApiError as exc:
        raise HTTPException(
            502, f"Sarvam could not read this file: {exc.status_code} {exc.body}",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            502, f"Gemini could not read this file: {exc.response.status_code} "
                 f"{exc.response.text[:300]}",
        ) from exc
    except httpx.TransportError as exc:
        # gemini_read_text already retried a transport failure and a 429/5xx three times
        # before giving up -- this is what "Could not reach the API" was, surfaced with
        # the real reason instead of a bare unhandled-exception 500.
        raise HTTPException(502, f"Gemini could not be reached: {exc}") from exc
    except RuntimeError as exc:
        # either gemini_read_text's own retry-exhausted RuntimeError, or Tesseract
        # actually running and failing on a page (ocr_read_text) -- both real failures in
        # the chosen backend, not a network-reachability problem, so a different message
        # from the TransportError case above.
        raise HTTPException(502, f"Hindi OCR failed: {exc}") from exc


def _finish_ingest_job(
    job_id: str, *, status_value: str, result: dict | None = None,
    error_status: int | None = None, error_detail: str | None = None,
) -> None:
    """Write a job's outcome in its own short-lived session, opened only for this update.

    A separate function, not inlined at each call site, because there are two places a
    job can finish (OCR itself failing, or _process_contents/_process_chapter failing
    after OCR succeeded) and both need the identical brief-session treatment -- see
    _run_ingest_job's docstring for why a long-lived one is the actual bug being avoided.
    """
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        job = db.get(IngestJob, job_id)
        if job is None:
            return
        job.status = status_value
        job.result = result
        job.error_status = error_status
        job.error_detail = error_detail
        job.finished_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def _run_ingest_job(job_id: str) -> None:
    """The slow part of a Hindi upload, run after the request that queued it has already
    returned.

    Three short-lived sessions, never one held open across the OCR call: a session kept
    open while OCR runs sits idle-in-transaction for however long that takes (minutes, on
    the real files -- confirmed on the deployed service by
    ``psycopg.errors.IdleInTransactionSessionTimeout`` killing the connection before the
    job's own final commit could run, losing the result OCR had already produced).
    Postgres enforces its own idle-in-transaction timeout regardless of what this process
    is doing, the same lesson `_hindi_text`'s retries and IngestJob's own 202 exist for
    with Render's *request* timeout -- do not hold a resource open across slow, unrelated
    work, whichever layer enforces the limit.

    Never raises: every failure, including one this function's own bugs would otherwise
    let escape as an unhandled exception in a background task (which FastAPI logs and
    then silently drops -- the job would sit at 'pending' forever with no visible cause),
    is caught and written to the job row, because that row is the only place left a
    failure can be seen once the request that would have shown it has already returned.
    """
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        job = db.get(IngestJob, job_id)
        if job is None:
            return
        kind, subject_code, curriculum_version = job.kind, job.subject_code, job.curriculum_version
        filename, edition, pdf_bytes = job.filename, job.edition, job.pdf_bytes
    finally:
        db.close()  # released BEFORE the slow OCR call below, not held across it

    is_hindi = subject_code.startswith(HINDI_SUBJECT_PREFIX)
    try:
        hindi_text = _hindi_text(pdf_bytes) if is_hindi else None
    except HTTPException as exc:
        _finish_ingest_job(
            job_id, status_value="failed", error_status=exc.status_code, error_detail=str(exc.detail),
        )
        return
    except Exception as exc:  # noqa: BLE001 -- see docstring: this must never escape
        _finish_ingest_job(
            job_id, status_value="failed", error_status=500,
            error_detail=f"{type(exc).__name__}: {exc}",
        )
        return

    db = SessionLocal()
    try:
        if kind == "contents":
            result = _process_contents(
                db, subject_code, curriculum_version, pdf_bytes, edition, hindi_text=hindi_text,
            )
        else:
            result = _process_chapter(
                db, subject_code, curriculum_version, filename, pdf_bytes, hindi_text=hindi_text,
            )
        status_value, error_status, error_detail = "succeeded", None, None
    except HTTPException as exc:
        result, status_value, error_status, error_detail = None, "failed", exc.status_code, str(exc.detail)
    except Exception as exc:  # noqa: BLE001 -- see docstring: this must never escape
        result = None
        status_value, error_status = "failed", 500
        error_detail = f"{type(exc).__name__}: {exc}"
    finally:
        db.close()

    _finish_ingest_job(
        job_id, status_value=status_value, result=result,
        error_status=error_status, error_detail=error_detail,
    )


def _source(db: Session, subject: str, version: str) -> BookSource | None:
    return db.scalar(
        select(BookSource).where(
            BookSource.subject_code == subject, BookSource.curriculum_version == version
        )
    )


class OlderSyllabusIn(BaseModel):
    """What was NOT in the syllabus under an older version, by family code."""

    exclude_families: list[str] = Field(default_factory=list)
    source_doc_url: str | None = Field(default=None, max_length=500)


@router.post("/{subject}/curriculum", status_code=status.HTTP_201_CREATED)
def setup_curriculum(
    subject: str,
    version: str = Query(default="CBSE-2026-27", max_length=32),
    body: OlderSyllabusIn | None = None,
    db: Session = Depends(get_session),
) -> dict:
    """Board units, their weightage, and the chapter mapping -- before any book.

    This layer does not come from the book: CBSE publishes weightage per unit, and a unit
    may span several chapters or exist where none does. It was previously only reachable
    through `scripts.seed`, which a deployment without shell access cannot run -- so the
    console could load a book into a taxonomy that had nowhere to put it.

    With ``version`` naming an OLDER syllabus ('CBSE-2021-22'), nothing is written to the
    tree. What is recorded is the difference: the current families that did not exist
    under that version (``exclude_families``), one row per revision and subject. That is
    how the board-frequency layer learns a family was not in the syllabus in 2022, and it
    is one call per revision rather than a date to maintain on every family. An empty
    list is still worth recording -- it says the year was checked.

    Idempotent: re-running adds only what is missing, or replaces the older record.
    """
    curriculum = CURRICULA.get(subject)
    if curriculum is None:
        raise HTTPException(
            422,
            f"no curriculum defined for {subject!r}. Known: {sorted(CURRICULA)}. "
            f"Board weightage comes from the CBSE syllabus, not the book, so it has to be "
            f"defined before a book can be loaded.",
        )
    if version != "CBSE-2026-27":
        from datetime import UTC, datetime

        exclude = sorted(set(body.exclude_families if body else []))
        known = {
            n.code for n in db.scalars(select(TaxonomyNode).where(
                TaxonomyNode.kind == "concept_family",
            )) if n.code.startswith(subject + ".")
        }
        unknown = set(exclude) - known
        if unknown:
            raise HTTPException(
                422,
                f"exclude_families names families the current syllabus does not have: "
                f"{sorted(unknown)}",
            )
        record = db.scalar(select(SyllabusVersion).where(
            SyllabusVersion.curriculum_version == version,
            SyllabusVersion.subject_code == subject,
        )) or SyllabusVersion(curriculum_version=version, subject_code=subject)
        record.excluded_families = exclude
        record.source_doc_url = (body.source_doc_url if body else None) or curriculum.source_doc_url
        record.seeded_at = datetime.now(UTC).isoformat()
        db.add(record)
        db.commit()
        return {
            "subject": subject,
            "version": version,
            "label": curriculum.subject_label,
            "excluded_families": exclude,
            "next": f"POST /board-frequency/recompute?subject_code={subject} to use it.",
        }
    created = apply_curriculum(db, curriculum)
    return {
        "subject": subject,
        "version": version,
        "label": curriculum.subject_label,
        "board_units": len(curriculum.units),
        "chapters": len(curriculum.chapters),
        "created": created,
        "next": "Now upload the contents page.",
    }


@router.get("/{subject}")
def status_for(subject: str, db: Session = Depends(get_session)) -> dict:
    """What has been loaded, and what is still missing."""
    settings = get_settings()
    source = _source(db, subject, "CBSE-2026-27")
    chunks = db.scalar(
        select(func.count(BookChunk.id)).where(BookChunk.subject_code == subject)
    )
    embedded = db.scalar(
        select(func.count(BookChunk.id)).where(
            BookChunk.subject_code == subject, BookChunk.embedding.isnot(None)
        )
    )
    subject_ready = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == subject)) is not None

    # Coverage chapter by chapter. A whole-book total hides the thing that matters: a
    # chapter with no passages behind it can never be matched, so every question from it
    # comes back "no chapter in the book matched" however healthy the total looks.
    parent = aliased(TaxonomyNode)
    coverage = [
        {
            "chapter_code": code,
            "chapter": label,
            "chunks": n or 0,
            "embedded": embedded_n or 0,
            "with_a_section": sectioned or 0,
        }
        for code, label, n, embedded_n, sectioned in db.execute(
            select(
                TaxonomyNode.code,
                TaxonomyNode.label,
                func.count(BookChunk.id),
                func.count(BookChunk.embedding),
                func.count(BookChunk.section_number),
            )
            .select_from(TaxonomyNode)
            .join(BookChunk, BookChunk.node_id == TaxonomyNode.id, isouter=True)
            .join(parent, parent.id == TaxonomyNode.parent_id)
            .where(TaxonomyNode.kind == "chapter", parent.code == subject)
            .group_by(TaxonomyNode.code, TaxonomyNode.label)
            .order_by(func.count(BookChunk.id), TaxonomyNode.code)
        ).all()
    ]
    empty_chapters = [c["chapter"] for c in coverage if not c["chunks"]]

    if source is None:
        return {
            "subject": subject,
            "curriculum_ready": subject_ready,
            "contents_uploaded": False,
            "expected_chapters": 0, "loaded_chapters": 0,
            "chunks": chunks or 0, "embedded": embedded or 0,
            "embeddings_configured": bool(settings.jina_api_key),
            "coverage": coverage,
            "chapters_with_nothing_behind_them": empty_chapters,
            "next": (
                "Set up the curriculum first -- board units and their weightage come from "
                "the syllabus, not the book." if not subject_ready else
                "Upload the contents page (00-contents.pdf) first -- every chapter is "
                "checked against it."
            ),
        }

    # expected_sections is the chapter.section list -- only Maths publishes one.
    # Every other subject's contents page stops at chapter titles (expected_chapters),
    # which upload_contents already falls back to for its own "N chapters expected"
    # count; this endpoint hadn't, so every subject but Maths showed "0 expected" here
    # -- read by the frontend as falsy and displayed as "?" instead of the real total.
    expected = {int(k) for k in source.expected_sections} or {
        int(k) for k in (source.expected_chapters or {})
    }
    loaded = {int(v["chapter"]) for v in source.files.values() if "chapter" in v}
    missing = sorted(expected - loaded)
    return {
        "subject": subject,
        "curriculum_ready": subject_ready,
        "contents_uploaded": True,
        "edition": source.edition,
        "expected_chapters": len(expected),
        "loaded_chapters": len(loaded),
        "missing_chapters": missing,
        "chunks": chunks or 0,
        "embedded": embedded or 0,
        "embeddings_configured": bool(settings.jina_api_key),
        #: per chapter, because a healthy total hides an empty chapter
        "coverage": coverage,
        "chapters_with_nothing_behind_them": empty_chapters,
        "files": source.files,
        "next": (
            f"Upload chapters {missing}" if missing
            else "All chapters loaded -- embed them so familiarity stops collapsing to "
                 "exact match." if (chunks or 0) > (embedded or 0)
            else "Loaded and embedded."
        ),
    }


def _process_contents(
    db: Session, subject: str, version: str, pdf_bytes: bytes, edition: str | None,
    *, hindi_text: str | None = None,
) -> dict:
    """Everything upload_contents does once it has the bytes -- shared by the synchronous
    endpoint (every subject but Hindi) and _run_ingest_job (Hindi, backgrounded because
    OCR cannot finish inside Render's request timeout). Raises HTTPException on a real
    problem with the upload; both callers let that propagate to where it belongs -- the
    response for a synchronous upload, the job row for a backgrounded one.

    ``hindi_text`` lets _run_ingest_job hand in text it already OCR'd *before* opening
    this function's ``db`` session -- see that function's own docstring for why holding a
    session open across a multi-minute OCR call is itself a bug, not just slow. Computing
    it here instead, as a fallback, keeps this function usable on its own (a direct call,
    a future synchronous Hindi path) without forcing every caller to pre-OCR.
    """
    if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == subject)) is None:
        raise HTTPException(
            422,
            f"subject {subject!r} is not in the taxonomy yet. Set up the curriculum first "
            f"-- the board units a chapter's marks count towards come from the syllabus, "
            f"not from the book.",
        )

    is_hindi = subject.startswith(HINDI_SUBJECT_PREFIX)
    is_tamil = subject.startswith(TAMIL_SUBJECT_PREFIX)
    text = (
        hindi_text if hindi_text is not None
        else _hindi_text(pdf_bytes) if is_hindi
        else tamil_read_text(pdf_bytes) if is_tamil
        else None
    )
    path = _bytes_to_tempfile(pdf_bytes)
    try:
        # Tamil's own contents page has no chapter label at all -- see
        # _tamil_toc_chapters_by_position -- so parse_toc_chapters needs the real PDF on
        # disk to read word positions from, not just its text. parse_toc, by contrast,
        # only ever finds a section-number oracle on a book that numbers its own sections
        # (Maths, Science), which Tamil's literature chapters do not -- toc stays empty
        # and every Tamil chapter is checked for identity and gaps only, same as Hindi.
        toc = parse_toc(path, text=text)
        chapters = parse_toc_chapters(path, text=text)
    finally:
        path.unlink(missing_ok=True)

    if not toc and not chapters:
        raise HTTPException(
            422,
            "no table of contents found. This should be the prelims file -- NCERT names it "
            "jemh1ps.pdf for Maths, jesc1ps.pdf for Science -- not a chapter.",
        )

    expected = {
        str(chapter): [{"number": s.number, "title": s.title} for s in sections]
        for chapter, sections in toc.items()
    }
    expected_chapters = {str(n): t for n, t in chapters.items()}
    source = _source(db, subject, version)
    if source is None:
        source = BookSource(
            curriculum_version=version, subject_code=subject,
            edition=edition, expected_sections=expected,
            expected_chapters=expected_chapters, files={},
        )
        db.add(source)
    else:
        # Re-uploading the contents page updates only the chapters THIS page itself
        # supplies a section oracle for (Maths, Science) -- it must never wipe out a
        # hand-typed oracle a chapter already has from set_expected_sections, which is
        # exactly what a flat replace used to do. Political Science's own contents page
        # lists chapter titles only, no section numbers at all (`expected` comes back
        # {}), so a flat `source.expected_sections = expected` here silently erased
        # every X.POL chapter's hand-typed list on the next contents-page re-upload --
        # a real production bug, discovered when chapters that had just been verified
        # started coming back "no expected section list is set" again with no upload,
        # edit, or error in between to explain it.
        merged_sections = dict(source.expected_sections)
        merged_sections.update(expected)
        source.expected_sections = merged_sections
        source.expected_chapters = expected_chapters
        if edition:
            source.edition = edition
    db.commit()

    count = len(expected) or len(expected_chapters)
    return {
        "subject": subject,
        "chapters_expected": count,
        "sections_expected": sum(len(v) for v in expected.values()),
        # Said plainly rather than left to be inferred from a zero. Science publishes no
        # section list, so its chapters can only be checked for structure, and a user who
        # is not told that will read a Science load as being as verified as a Maths one.
        "section_oracle": bool(expected),
        "verification": (
            "Each chapter will be checked section by section against this page."
            if expected
            else "This contents page lists chapters only, with no section numbers. "
                 "Chapters will be checked for chapter identity and for gaps in their own "
                 "numbering, and their section numbers will be recorded as unverified."
        ),
        "next": f"Upload the {count} chapter files.",
    }


class ExpectedSectionIn(BaseModel):
    number: str = Field(max_length=16)
    title: str = Field(max_length=200)


class ExpectedSectionsIn(BaseModel):
    """A hand-typed section list for chapters this book's own contents page cannot supply
    one for -- every Social Science book except Maths/Science. Keyed by chapter number,
    a string because JSON object keys always are.
    """

    chapters: dict[str, list[ExpectedSectionIn]] = Field(min_length=1, max_length=40)


@router.post("/{subject}/expected-sections", status_code=status.HTTP_201_CREATED)
def set_expected_sections(
    subject: str, body: ExpectedSectionsIn, db: Session = Depends(get_session),
) -> dict:
    """Give a chapter a real verification oracle by hand, for a book whose own contents
    page cannot supply one -- Geography, Political Science and Economics publish chapter
    titles only, and Social Science's own book codes (X.HIST, X.GEO, X.POL, X.ECO) share
    one group but are four separate subject_codes, each needing this called once per book.

    Maths and Science get this for free from `_process_contents` parsing their own
    contents page (`parse_toc`); every other subject falls back to `verify_structure`'s
    weaker heuristics -- real, but unable to catch a heading the extractor never saw at
    all, which is exactly the shape every bug found against the real Economics, Political
    Science and History chapters took. Once a chapter's sections are set here,
    `_process_chapter` checks a real upload against this list with `verify_against_toc`,
    the same hard check Maths already gets: a missing or extra section rejects the
    upload instead of loading silently.

    Additive per chapter, like `create_families`: a chapter named here replaces only its
    OWN entry in `expected_sections`, never another chapter's, so setting up chapter 4
    cannot accidentally wipe out chapter 1's list from an earlier call.

    The numbers given must be exactly what the extractor itself would find for this
    subject's own convention -- History's own bare '1', '2', decimal '2.1' (see
    BOOK_NUMBERED_SECTION), or plain reading-order '1', '2', '3'... for a book with no
    numbering of its own at all (Geography, Political Science, Economics -- see
    `_sections_by_boldness`). A number invented to match some other scheme (the book's own
    printed numbering, say) will never match what gets extracted and every chapter will
    permanently fail verification against its own true content.
    """
    curriculum = CURRICULA.get(subject)
    if curriculum is None:
        raise HTTPException(
            422,
            f"no curriculum defined for {subject!r}. Known: {sorted(CURRICULA)}. Set up "
            f"the curriculum first -- POST /platform/books/{subject}/curriculum.",
        )
    version = "CBSE-2026-27"
    source = _source(db, subject, version)
    if source is None:
        source = BookSource(
            curriculum_version=version, subject_code=subject,
            expected_sections={}, expected_chapters={}, files={},
        )
        db.add(source)

    expected = dict(source.expected_sections)
    for chapter_number, sections in body.chapters.items():
        expected[chapter_number] = [
            {"number": s.number, "title": s.title} for s in sections
        ]
    source.expected_sections = expected
    db.commit()

    return {
        "subject": subject,
        "chapters_set": sorted(body.chapters, key=int),
        "sections_set": {k: len(v) for k, v in body.chapters.items()},
        "next": (
            "Upload each chapter now (or re-upload one already loaded): it will be "
            "checked against this list with verify_against_toc instead of the weaker "
            "structural heuristics, and a missing or mismatched section will reject the "
            "upload instead of loading silently."
        ),
    }


def _process_chapter(
    db: Session, subject: str, version: str, name: str, pdf_bytes: bytes,
    *, hindi_text: str | None = None, locate_known_sections: bool = False,
) -> dict:
    """Everything upload_chapter does once it has the bytes -- see _process_contents for
    why this is split out from the route handler, and for what ``hindi_text`` is for.
    """
    source = _source(db, subject, version)
    if source is None:
        raise HTTPException(
            409,
            "upload the contents page first -- it is what makes a chapter checkable rather "
            "than merely plausible",
        )

    number = chapter_number(name)
    if number is None or number == 0:
        raise HTTPException(
            422,
            f"{name!r} is not a chapter file. Both naming conventions work: NCERT's own "
            f"(jemh101.pdf) or NN-slug.pdf (12-surface-areas-and-volumes.pdf). The "
            f"contents page, the answers and the appendices are deliberately not loadable "
            f"here -- the answers file matches EXERCISE 31 times and would load the answer "
            f"key as practice content.",
        )

    is_hindi = subject.startswith(HINDI_SUBJECT_PREFIX)
    is_tamil = subject.startswith(TAMIL_SUBJECT_PREFIX)
    text_override = (
        hindi_text if hindi_text is not None
        else _hindi_text(pdf_bytes) if is_hindi
        else tamil_read_text(pdf_bytes) if is_tamil
        else None
    )
    path = _bytes_to_tempfile(pdf_bytes)
    try:
        # An NCERT-coded filename carries no title, so take it from the curriculum, which
        # is the authority for chapter identity anyway -- it holds the board-unit mapping.
        # English has no chapter-scoped subsections at all -- a story or poem is one
        # continuous piece, broken only by fixed-name checkpoints, never a heading. The
        # Workbook's units are not taught-then-drilled content either: the unit body IS
        # the exercise. Hindi is the same shape as English -- a story or poem, no
        # font/boldness metadata available at all once the text has come from OCR/Gemini
        # rather than the PDF's own (unusable) text layer -- so it gets single_section too.
        # Tamil's chapters are poems/prose/grammar sections the same way, with no numbered
        # subheadings on the page to detect, so it gets single_section too -- what its own
        # exercise/drilled-content marker looks like is not yet confirmed against a real
        # chapter file (see extract_chunks), the same open question Hindi's HINDI_DRILL_LABEL
        # started as before a real upload disagreed with it.
        # Scoped by subject code, not guessed from what the normal section detection
        # happens to find on a given file.
        # An explicit opt-in, never a silent replacement for the usual typographic
        # detection -- see extract_chapter's own note on known_section_titles for why:
        # it only runs where a chapter's own real headings are already typed up as an
        # oracle AND the typographic passes have already been tried and shown not to work
        # for this book (Geography's own "Resources and Development", confirmed against
        # the real file -- boldness, size and colour each fail to separate a real heading
        # from a diagram caption, a table cell or the chapter's own body prose somewhere
        # in the chapter).
        known_titles = None
        if locate_known_sections:
            stored = source.expected_sections.get(str(number))
            if not stored:
                raise HTTPException(
                    422,
                    f"locate_known_sections was requested but no expected section list "
                    f"is set for {subject} chapter {number} -- POST "
                    f"/{subject}/expected-sections first.",
                )
            known_titles = [s["title"] for s in stored]

        extract = extract_chapter(
            path, number=number, name=name,
            title=chapter_title(subject, number) or "",
            single_section=subject.startswith("X.ENG") or is_hindi or is_tamil,
            # History numbers its own headings independently of the chapter (a bare '1',
            # or a decimal subsection under it) -- see extract_chapter's own docstring on
            # bare_headings for the real chapter this coincidentally broke: extract_sections
            # scoped to chapter 4 quietly matched chapter 4's own unrelated heading "4.1",
            # returning a wrong non-empty result that skipped the boldness fallback outright.
            bare_headings=subject.startswith("X.HIST"),
            body_bucket="E" if subject == "X.ENG.WB" else "T",
            text_override=text_override,
            known_section_titles=known_titles,
        )
        toc = {
            int(k): [Section(s["number"], s["title"]) for s in v]
            for k, v in source.expected_sections.items()
        }
        expected_title = (source.expected_chapters or {}).get(str(number))
        if locate_known_sections:
            # verify_against_toc compares by NUMBER, assigned by the position each title
            # was TYPED at -- but _locate_known_sections renumbers by the position each
            # title was actually FOUND at, which can legitimately differ (confirmed on
            # the real "Resources and Development" chapter: "Land Resources" is typed
            # before "Land Utilisation" but printed after it in the book). Comparing
            # those two numberings would flag a real, correctly-found chapter as
            # disagreeing with itself. known_titles' own "all requested titles were
            # found" check (already in extract.problems) is this mode's verification.
            extract.verified_against = source.edition or "contents page (by known titles)"
        elif toc:
            verify_against_toc(extract, toc)
            extract.verified_against = source.edition or "contents page"
        else:
            # No section list published for this subject. Check what the contents page
            # does say -- that this is the chapter the book calls `number` -- then check
            # the chapter's own numbering for gaps, and leave it marked unverified.
            #
            # Hindi's expected_title came from OCR (see app.ingest.hindi_ocr/hindi_text),
            # which is not reliable down to the exact character -- the real Kritika
            # contents page OCR'd chapter 1's title as 'माता का अआँचल ।' (an inserted extra
            # vowel sign in the middle of the word, a trailing danda where the page number
            # should be) against the clean 'माता का अँचल' this file's own curriculum entry
            # carries. Neither an exact match nor a substring one survives an insertion
            # mid-string, so this falls back to a similarity ratio (difflib, stdlib, no
            # new dependency) rather than rejecting a chapter that is correctly identified
            # by number over nothing but OCR noise. 0.6 is loose enough to absorb a few
            # inserted/dropped characters but still catches a genuinely wrong chapter,
            # which shares almost no character runs with what OCR read at all.
            #
            # Tamil's own contents page is not OCR'd, but _tamil_toc_chapters_by_position
            # reads it by word position rather than by a numbered line, and a font-level
            # word-boundary quirk splits a single visual word into two PDF word objects
            # sometimes ('பாய்ச்சல்' back as 'பாய்ச்ச ல்', confirmed against the real
            # jhtl107-equivalent contents page) -- an exact match would reject a correctly
            # identified chapter over a stray space, the same shape of harmless noise
            # Hindi's own fuzzy match already exists to absorb.
            titles_disagree = (
                title_key(expected_title) != title_key(extract.title)
                if not (is_hindi or is_tamil)
                else difflib.SequenceMatcher(
                    None, title_key(expected_title), title_key(extract.title),
                ).ratio() < 0.6
            )
            if expected_title and titles_disagree:
                extract.problems.append(
                    f"the contents page calls chapter {number} "
                    f"{expected_title!r}, not {extract.title!r}"
                )
            verify_structure(extract, exercises_required=not (is_hindi or is_tamil or subject.startswith("X.ENG")))
            extract.verified_against = None
    finally:
        path.unlink(missing_ok=True)

    if not extract.ok:
        raise HTTPException(
            422,
            "this chapter disagrees with the contents page, so nothing was written: "
            + "; ".join(extract.problems),
        )

    written = _load(db, extract, subject, version)
    files = dict(source.files)
    files[name] = {
        "chapter": extract.number, "sha256": extract.sha256,
        "chunks": len(extract.chunks), "loaded_at": datetime.now(UTC).isoformat(),
    }
    source.files = files
    db.commit()

    return {
        "chapter": extract.number, "title": extract.title,
        "sections": len(extract.sections),
        "verified_against": extract.verified_against,
        "warnings": extract.warnings,
        **written,
    }


def _bytes_to_tempfile(pdf_bytes: bytes):
    import tempfile
    from pathlib import Path

    handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    handle.write(pdf_bytes)
    handle.close()
    return Path(handle.name)


@router.post("/{subject}/contents", status_code=status.HTTP_201_CREATED)
async def upload_contents(
    subject: str,
    file: UploadFile = File(...),
    edition: str | None = None,
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
    db: Session = Depends(get_session),
) -> dict:
    """The prelims file. Parsed for its table of contents, which becomes the oracle.

    A Hindi subject cannot finish this inside one request -- see IngestJob -- so it writes
    a job and returns 202 instead of doing the work here; poll GET .../jobs/{id} for the
    result this endpoint returns directly for every other subject.
    """
    version = "CBSE-2026-27"
    path = await _to_tempfile(file)
    pdf_bytes = path.read_bytes()
    path.unlink(missing_ok=True)

    if subject.startswith(HINDI_SUBJECT_PREFIX):
        job = IngestJob(
            subject_code=subject, curriculum_version=version, kind="contents",
            filename=file.filename or "contents.pdf", edition=edition, pdf_bytes=pdf_bytes,
        )
        db.add(job)
        db.commit()
        background_tasks.add_task(_run_ingest_job, job.id)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "job_id": job.id, "status": "pending",
                "next": f"Poll GET /platform/books/{subject}/jobs/{job.id} for the result.",
            },
        )

    return _process_contents(db, subject, version, pdf_bytes, edition)


@router.post("/{subject}/chapters", status_code=status.HTTP_201_CREATED)
async def upload_chapter(
    subject: str,
    file: UploadFile = File(...),
    locate_known_sections: bool = False,
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
    db: Session = Depends(get_session),
) -> dict:
    """One chapter PDF, verified against the contents page before anything is written.

    See upload_contents: a Hindi subject is backgrounded the same way.

    ``locate_known_sections``: an explicit opt-in for a book whose real headings cannot
    be told apart from everything else on the page by boldness, size or colour (see
    extract_chapter's own note on ``known_section_titles``). Requires this chapter's
    expected section list to already be set via POST /expected-sections -- refused
    with 422 otherwise, not silently ignored.
    """
    version = "CBSE-2026-27"
    name = file.filename or ""
    path = await _to_tempfile(file)
    pdf_bytes = path.read_bytes()
    path.unlink(missing_ok=True)

    if subject.startswith(HINDI_SUBJECT_PREFIX):
        job = IngestJob(
            subject_code=subject, curriculum_version=version, kind="chapter",
            filename=name, pdf_bytes=pdf_bytes,
        )
        db.add(job)
        db.commit()
        background_tasks.add_task(_run_ingest_job, job.id)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "job_id": job.id, "status": "pending",
                "next": f"Poll GET /platform/books/{subject}/jobs/{job.id} for the result.",
            },
        )

    return _process_chapter(
        db, subject, version, name, pdf_bytes, locate_known_sections=locate_known_sections,
    )


@router.get("/{subject}/jobs/{job_id}")
def get_ingest_job(subject: str, job_id: str, db: Session = Depends(get_session)) -> dict:
    """Poll for the result of a backgrounded upload -- see IngestJob and upload_contents/
    upload_chapter. A failed job carries the same status code and detail a synchronous
    upload would have raised, not a bare 'failed'.
    """
    job = db.get(IngestJob, job_id)
    if job is None or job.subject_code != subject:
        raise HTTPException(404, f"no job {job_id!r} for subject {subject!r}")
    if job.status == "failed":
        raise HTTPException(job.error_status or 500, job.error_detail or "the job failed")
    if job.status != "succeeded":
        return {"job_id": job.id, "status": job.status}
    return {"job_id": job.id, "status": "succeeded", **(job.result or {})}


def _load(db: Session, extract, subject: str, version: str) -> dict:
    """Identical to scripts.ingest_book.load -- see the note there on matching by title."""
    subject_node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == subject))
    chapter = db.scalar(
        select(TaxonomyNode).where(
            TaxonomyNode.kind == "chapter",
            func.lower(TaxonomyNode.label) == extract.title.lower(),
        )
    )
    chapter_code = chapter.code if chapter else f"{subject}.CH{extract.number:02d}"
    if chapter is None:
        chapter = TaxonomyNode(
            kind="chapter", code=chapter_code, label=extract.title,
            parent_id=subject_node.id, path=chapter_code, curriculum_version=version,
        )
        db.add(chapter)
        db.flush()

    for section in extract.sections:
        code = f"{chapter_code}.S{section.number.replace('.', '_')}"
        if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code)) is None:
            db.add(TaxonomyNode(
                kind="subtopic", code=code, label=section.title,
                parent_id=chapter.id, path=code, curriculum_version=version,
            ))

    written = {"chunks": 0, "procedures": 0, "sections_filled": 0}
    for chunk in extract.chunks:
        existing = db.scalar(
            select(BookChunk).where(
                BookChunk.stem_hash == chunk.stem_hash,
                BookChunk.curriculum_version == version,
            )
        )
        if existing is None:
            db.add(BookChunk(
                curriculum_version=version, subject_code=subject, node_id=chapter.id,
                bucket=chunk.bucket, reference=chunk.reference,
                # The section the extraction attributed this passage to. It was worked out
                # and then dropped here, which is why no question could be given a topic.
                section_number=(chunk.section or None),
                text=chunk.text, normalised=chunk.text, stem_hash=chunk.stem_hash,
            ))
            written["chunks"] += 1
        elif chunk.section and existing.section_number != chunk.section:
            # A passage loaded before the section was recorded, OR recorded wrong the
            # first time -- a chapter this extractor could only read as one giant
            # single_section block on an earlier pass (a script's headings undetectable,
            # a Tamil or Hindi chapter whose heading regex assumed Latin script) stores
            # every one of its chunks under the same placeholder section "1", and a
            # later pass that DOES read the real headings correctly used to leave that
            # wrong "1" in place forever: a chunk is written only when its hash is
            # absent, the same file hashes the same, so every chunk already existed and
            # `not existing.section_number` is false once anything, right or wrong, has
            # ever been stored -- so re-uploading after fixing the heading detection
            # silently changed nothing. Correcting it in place, whenever the freshly
            # read section actually disagrees, touches neither the text nor the vector,
            # so the book does not have to be embedded again to gain the topics it
            # always had.
            existing.section_number = chunk.section
            written["sections_filled"] += 1
        if chunk.kind in ("theorem", "activity", "example") and db.scalar(
            select(CanonicalProcedure).where(
                CanonicalProcedure.stem_hash == chunk.stem_hash,
                CanonicalProcedure.curriculum_version == version,
            )
        ) is None:
            db.add(CanonicalProcedure(
                curriculum_version=version, subject_code=subject, chapter_id=chapter.id,
                name=chunk.reference, reference=chunk.reference,
                canonical_stem=chunk.text, stem_hash=chunk.stem_hash, taught_verbatim=True,
            ))
            written["procedures"] += 1

    unmapped = db.scalar(
        select(func.count(ChapterBoardUnit.id)).where(
            ChapterBoardUnit.chapter_id == chapter.id
        )
    )
    written["board_unit_mapped"] = bool(unmapped)
    return written


class ProbeQuestion(BaseModel):
    q: str = Field(max_length=16)                  # the question number on the paper
    stem: str = Field(min_length=10, max_length=2000)
    chapter: str | None = None                     # the chapter you expect, if you know it


class ProbeIn(BaseModel):
    questions: list[ProbeQuestion] = Field(min_length=1, max_length=50)


@router.post("/{subject}/probe")
def probe(subject: str, body: ProbeIn, db: Session = Depends(get_session)) -> dict:
    """Push real questions through the knowledge base and report what resolves.

    The check the schema's closing line asks for -- run real questions through and see what
    breaks -- against the loaded data rather than a description of it. A knowledge base
    that loads cleanly and then cannot place a question has failed at the only thing it
    exists for, and the ingest summary says nothing about that.
    """
    settings = get_settings()
    chunks = db.scalars(select(BookChunk).where(BookChunk.subject_code == subject)).all()
    if not chunks:
        raise HTTPException(409, f"no book loaded for {subject}")

    labels = {n.id: n.label for n in db.scalars(select(TaxonomyNode)).all()}
    embedded = [c for c in chunks if c.embedding]

    # Both retrievers, always, when vectors exist. They fail on DIFFERENT questions:
    # "cone, slant height" is a literal-word match that meaning-similarity missed, and
    # "bells ringing at 48, 72 and 108 seconds" is a meaning match with no shared
    # vocabulary at all. Fusing their rankings gets the union of what each knows.
    indexes: list = [LexicalIndex(chunks)]
    mode = "lexical"
    if embedded and settings.jina_api_key:
        from app.ingest.jina import JinaEmbedder

        indexes.append(
            SemanticIndex(
                chunks,
                JinaEmbedder(
                    settings.jina_api_key, model=settings.embedding_model,
                    dimensions=settings.embedding_dimensions,
                ),
            )
        )
        mode = "hybrid"

    rows = []
    hits = 0
    for question in body.questions:
        verdict = locate(question.stem, indexes)
        retrieved = labels.get(verdict.node_id, "?") if verdict.node_id else None
        top = verdict.evidence[0] if verdict.evidence else None

        verbatim = db.scalar(
            select(CanonicalProcedure).where(
                CanonicalProcedure.stem_hash == stem_hash(question.stem)
            )
        )
        if verbatim:
            familiarity, similarity, why = "T_VERBATIM", 1.0, "exact match"
        elif mode == "hybrid" and top:
            call = classify_familiarity(top.score, top.reference, top.bucket)
            familiarity, similarity, why = call.level, call.similarity, call.reason
        else:
            familiarity, similarity, why = None, top.score if top else 0.0, (
                "undecidable without vectors"
            )

        ok = bool(question.chapter and retrieved
                  and question.chapter.lower() == retrieved.lower())
        hits += ok
        rows.append({
            "q": question.q,
            "expected": question.chapter,
            "retrieved": retrieved,
            "hit": ok if question.chapter else None,
            "nearest": top.reference if top else None,
            "similarity": round(similarity, 3),
            "familiarity": familiarity,
            "why": why,
            "margin": round(verdict.margin, 4),
            "agreed": verdict.agreed,
            "confident": verdict.agreed and verdict.margin >= MIN_MARGIN,
            "runners_up": [
                {"reference": labels.get(node, "?"), "chapter": labels.get(node, "?"),
                 "similarity": round(score, 4)}
                for node, score in verdict.runners_up
            ],
        })

    graded = sum(1 for r in rows if r["hit"] is not None)
    return {
        "mode": mode,
        "confident": sum(1 for r in rows if r["confident"]),
        "chunks": len(chunks),
        "embedded": len(embedded),
        "graded": graded,
        "hits": hits,
        "rows": rows,
        "note": (
            "Familiarity thresholds are provisional until measured on real papers; a call "
            "near a boundary abstains rather than guessing."
            if mode == "semantic" else
            "Lexical retrieval: only T_VERBATIM is decidable, so three of the four "
            "familiarity levels collapse."
        ),
    }


#: '13.2', '4.3.1', or a bare '1' -- a book whose chapters are not further subdivided
#: (measured on a Tamil literature book: every chapter is one section, numbered plainly
#: "1", never "1.1") has a section number just as real as NCERT's dotted "13.2", and the
#: dot used to be required: every chunk in such a chapter, and every family proposed from
#: it, was silently stripped to no section at all, which is indistinguishable downstream
#: from a chapter that never had one -- "N families exist and none claims section 1" on
#: every question, even though the model had correctly read "1" off the book every time.
#: What is still rejected is a sentence -- one run returned "Section on spherical mirror
#: introduction" -- which this pattern never matches either way.
#:
#: '2.4-2' -- the disambiguated form _pick_sections's own numbered-heading dedup mints
#: when a book reuses one printed number for two different real headings (confirmed on
#: the real History chapter "The Making of a Global World": '2.4' is printed twice, for
#: two different headings, both genuine). Without the trailing '-\d+' here, that section
#: number itself read as an invalid, non-section value and got silently stripped from
#: its own family's from_sections -- reported as still uncovered even though a proposal
#: for it existed and named it correctly right up until this filter ran.
SECTION_NUMBER = re.compile(r"^\d{1,2}(?:\.\d{1,2}){0,2}(?:-\d+)?$")


def clean_sections(values) -> list[str]:
    """Only the entries that are section numbers, in the order given, without repeats."""
    out: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if SECTION_NUMBER.match(text) and text not in out:
            out.append(text)
    return out


#: two labels under one chapter at least this alike are probably one idea twice
DUPLICATE_LABEL_SCORE = 0.8
#: words that make two labels differ without making them different ideas
_LABEL_FILLER = re.compile(
    r"\b(?:finding|find|solving|solve|calculating|calculate|computing|compute|determining|"
    r"determine|using|use|understanding|understand|the|a|an|of|for|to|and|in|with|by)\b",
    re.IGNORECASE,
)


def _label_key(label: str) -> str:
    return " ".join(_LABEL_FILLER.sub(" ", label or "").lower().split())


def _dedupe_and_flag(proposals: list[dict]) -> list[dict]:
    """One entry per code, and a ``similar_to`` on any label that reads as another
    proposal's idea under the same chapter -- 'Area of a sector' beside 'Finding the area
    of a sector'. Nothing is merged: which of two names survives is a person's call, and
    the flag is what puts it in front of them."""
    from app.extraction.names import similarity

    by_code: dict[str, dict] = {}
    for p in proposals:
        if not p.get("code") or p["code"].endswith("."):
            continue
        if p["code"] in by_code:
            have = by_code[p["code"]]
            have["from_sections"] = sorted(
                set(have.get("from_sections") or []) | set(p.get("from_sections") or [])
            )
            continue
        by_code[p["code"]] = dict(p)
    out = list(by_code.values())
    by_chapter: dict[str, list[dict]] = {}
    for p in out:
        by_chapter.setdefault(p["chapter_code"], []).append(p)
    for group in by_chapter.values():
        for i, p in enumerate(group):
            a = _label_key(p["label"])
            for q in group[:i]:
                b = _label_key(q["label"])
                if a == b or similarity(a, b) >= DUPLICATE_LABEL_SCORE:
                    p["similar_to"] = q["code"]
                    break
    return out


class FamiliesIn(BaseModel):
    """The families to create. Reviewed, not accepted wholesale."""

    families: list[dict] = Field(min_length=1, max_length=200)


@router.get("/{subject}/concept-families/applied")
def list_applied_families(subject: str, db: Session = Depends(get_session)) -> dict:
    """Every concept family that actually exists under this subject, across every run.

    GET /concept-families/proposals only ever shows the LATEST proposal run -- a family
    applied from an earlier run (or a PATCH/edit made after the fact) has no code visible
    anywhere else, which makes a family spotted as wrong in the review screen (a chapter
    or topic label that is nonsense, or in the wrong language entirely) impossible to
    find and act on without reading the database directly. This lists what is actually
    live right now, regardless of which run proposed it.
    """
    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
    families = [
        n for n in nodes.values()
        if n.kind == "concept_family" and n.code.startswith(f"{subject}.")
    ]
    from app.models import Question

    used = dict(db.execute(
        select(Question.concept_family_id, func.count(Question.id))
        .where(Question.concept_family_id.in_([f.id for f in families]))
        .group_by(Question.concept_family_id)
    ).all()) if families else {}
    proposed = {
        p.code: p for p in db.scalars(select(ConceptFamilyProposal).where(
            ConceptFamilyProposal.subject_code == subject
        ))
    }
    return {
        "subject": subject,
        "families": [
            {
                "code": n.code, "label": n.label,
                "chapter": nodes[n.parent_id].label if n.parent_id in nodes else None,
                "chapter_code": nodes[n.parent_id].code if n.parent_id in nodes else None,
                "from_sections": proposed[n.code].from_sections if n.code in proposed else [],
                "questions": used.get(n.id, 0),
            }
            for n in sorted(families, key=lambda f: (nodes.get(f.parent_id).label if f.parent_id in nodes else "", f.label))
        ],
    }


@router.get("/{subject}/concept-families")
def propose_families(subject: str, db: Session = Depends(get_session)) -> dict:
    """Candidate families from the book's own section headings.

    A proposal, never applied automatically: renaming a family after a class has been
    tested breaks every trend that references it, so the list is a commitment and a
    commitment is a person's to make.
    """
    from app.curriculum.families import propose

    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
    # This subject's chapters only. Taking every chapter in the tree proposed English
    # stories and Science sections as Maths families, coded X.MATH.CF.*, and some were
    # created that way -- a Maths frequency table then carried "A Letter to God".
    chapters = {
        n.id: n for n in nodes.values()
        if n.kind == "chapter" and n.code.startswith(f"{subject}.")
    }

    counts: dict[str, int] = {}
    for chunk in db.scalars(
        select(BookChunk).where(BookChunk.subject_code == subject)
    ):
        counts[chunk.node_id] = counts.get(chunk.node_id, 0) + 1

    rows = [
        (
            chapters[node.parent_id].code,
            chapters[node.parent_id].label,
            # The section number, off the node's own code: 'X.MATH.CIRCLE.S10_1' -> '10.1'.
            # This is what a question's section is matched against, so it has to be the
            # number and not the heading.
            node.code.rsplit(".", 1)[-1][1:].replace("_", "."),
            node.label,
            counts.get(node.parent_id, 0),
        )
        for node in nodes.values()
        if node.kind == "subtopic"
        and node.parent_id in chapters
        and node.code.rsplit(".", 1)[-1].startswith("S")
    ]
    rows.sort(key=lambda r: (r[0], r[2]))

    existing = {
        n.code for n in nodes.values()
        if n.kind == "concept_family" and n.parent_id in chapters
    }

    # What a proposal run has already worked out, which is better than a bare heading: it
    # names the learning area rather than the section it sits in, and it says which
    # sections it draws on. These were being ignored entirely -- a run could propose
    # hundreds and this route would still suggest the headings, so the work sat unused.
    stored = [
        {
            "code": row.code,
            "label": row.label,
            "chapter_code": chapters[row.chapter_id].code if row.chapter_id in chapters else "",
            "chapter_label": chapters[row.chapter_id].label if row.chapter_id in chapters else "",
            "from_sections": clean_sections(row.from_sections),
            "source": row.source,
            "rationale": row.rationale,
            "chunks": counts.get(row.chapter_id, 0),
            "already_exists": row.code in existing,
        }
        for row in db.scalars(
            select(ConceptFamilyProposal)
            .where(ConceptFamilyProposal.subject_code == subject)
            .order_by(ConceptFamilyProposal.label)
        )
        if row.chapter_id in chapters
    ]
    # A section a stored run has already covered does not need its heading suggesting as
    # well -- but a SECTION, not the whole chapter. This used to skip a chapter entirely
    # the moment it had even one stored proposal, on the assumption that a run covers a
    # chapter completely or not at all. Confirmed wrong on a real deployment: History's
    # five chapters each had a handful of stored proposals from an earlier, narrower
    # extraction pass (a handful of sub-headings, e.g. section '2.2' of one chapter), and
    # once the extractor was fixed to find dozens more real sections per chapter, every
    # one of those new sections stayed permanently invisible here -- "28 proposed, 28
    # existing, 0 new" on every re-check, no matter how many real uncovered_sections
    # GET .../concept-families went on to report, because the chapter-level skip never
    # let the heading-based fallback even look at them.
    covered_sections = {
        (row["chapter_code"], section)
        for row in stored
        for section in row["from_sections"]
    }
    proposals = stored + [
        {
            "code": p.code, "label": p.label,
            "chapter_code": p.chapter_code, "chapter_label": p.chapter_label,
            "from_sections": clean_sections([p.from_section]),
            "source": "headings",
            "rationale": "the chapter's own section heading",
            "chunks": p.chunks,
            "already_exists": p.code in existing,
        }
        for p in propose(rows, subject)
        if (p.chapter_code, p.from_section) not in covered_sections
    ]
    proposals = _dedupe_and_flag(proposals)
    proposals.sort(key=lambda r: (r["chapter_label"], r["label"]))

    # A section the book was actually chunked into (chunk.section_number, set at
    # ingestion) that no family -- applied or proposed -- claims in its from_sections.
    # This is exactly the gap a question can silently fail to map against: mapping
    # cannot choose a family for a section nothing on this list names, and until now
    # nobody found out until a teacher's paper came back unmapped. Computed from the
    # book's own chunks, not from the heading list `propose()` walks, so it also catches
    # a section whose heading detection failed at ingestion but whose text still landed
    # under the chapter (see `_load`'s note on section_number reconciliation) -- that
    # text would otherwise sit invisible to every family a proposal run ever offers.
    chunk_sections: dict[str, set[str]] = {}
    for chapter_id, chapter in chapters.items():
        for chunk in db.scalars(
            select(BookChunk.section_number)
            .where(BookChunk.subject_code == subject)
            .where(BookChunk.node_id == chapter_id)
        ):
            if chunk:
                chunk_sections.setdefault(chapter.code, set()).add(chunk)
    claimed_sections: dict[str, set[str]] = {}
    for row in stored + proposals:
        claimed_sections.setdefault(row["chapter_code"], set()).update(row["from_sections"])
    uncovered = [
        {"chapter_code": chapter_code, "sections": sorted(sections - claimed_sections.get(chapter_code, set()))}
        for chapter_code, sections in chunk_sections.items()
        if sections - claimed_sections.get(chapter_code, set())
    ]

    return {
        "subject": subject,
        "existing": len(existing),
        "proposed": len(proposals),
        #: proposals whose label reads as the same idea as another under the same chapter
        "possible_duplicates": sum(1 for p in proposals if p.get("similar_to")),
        #: proposals that name no section a question could be matched against. They can
        #: still be created; they just cannot be chosen by section afterwards.
        "without_a_section": sum(1 for p in proposals if not p["from_sections"]),
        #: sections the book was actually loaded with that no family, existing or
        #: proposed, claims -- a question landing here has nothing to be mapped to no
        #: matter how the family list is reviewed. See the note above computing this.
        "uncovered_sections": uncovered,
        "families": proposals,
        "note": (
            "A family is the axis a report compares against itself over time. Chapter is "
            "too coarse to act on and section numbers move when the book is reprinted, "
            "which would break every historical comparison. Review these, merge the ones "
            "that are one idea, and drop the ones that are not learning areas."
        ),
    }


@router.post("/{subject}/concept-families", status_code=status.HTTP_201_CREATED)
def create_families(
    subject: str, body: FamiliesIn, db: Session = Depends(get_session)
) -> dict:
    """Create the reviewed families. Additive only: an existing one is never renamed.

    A proposal that already exists is stamped as applied rather than copied. A run can
    propose hundreds of families and nothing marked which of them had been acted on, so
    there was no way to tell a reviewed proposal from an untouched one.
    """
    nodes = {n.code: n for n in db.scalars(select(TaxonomyNode))}
    proposals = {
        row.code: row
        for row in db.scalars(
            select(ConceptFamilyProposal).where(
                ConceptFamilyProposal.subject_code == subject
            )
        )
    }
    created, skipped, unknown, wrong_subject = 0, 0, [], []
    run_id = uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()

    for entry in body.families:
        code = str(entry.get("code", "")).strip()
        label = str(entry.get("label", "")).strip()
        chapter_code = str(entry.get("chapter_code", "")).strip()
        if not code or not label:
            continue
        chapter = nodes.get(chapter_code)
        if chapter is None or chapter.kind != "chapter":
            unknown.append(chapter_code)
            continue
        if not chapter.code.startswith(f"{subject}.") or code.endswith("."):
            # A Science chapter's family coded X.MATH.CF.* would sit in the Maths
            # frequency table and every Maths report. Filed under the wrong subject is
            # not a family; it is a mistake with a stable identifier.
            wrong_subject.append(f"{code} -> {chapter_code}")
            continue
        if code in nodes:
            # Never rename: a family is held constant across cycles, and changing one
            # after a class has been tested breaks every trend that references it.
            skipped += 1
            continue
        db.add(TaxonomyNode(
            kind="concept_family", code=code, label=label,
            parent_id=chapter.id, path=code,
            curriculum_version=chapter.curriculum_version,
        ))
        # Which sections of the chapter this family covers, kept alongside it. Without this
        # a chapter with two families had no way to say which of them a question in
        # section 13.2 belongs to, so every question in that chapter was refused for want
        # of a choice nothing had the information to make.
        existing = proposals.get(code)
        if existing is not None:
            existing.applied_at = now
        else:
            sections = clean_sections(
                entry.get("from_sections") or [entry.get("from_section")]
            )
            db.add(ConceptFamilyProposal(
                curriculum_version=chapter.curriculum_version, subject_code=subject,
                run_id=run_id, source="headings", model=None,
                code=code, label=label, chapter_id=chapter.id,
                rationale="proposed from the chapter's own section heading",
                evidence=sections, from_sections=sections, applied_at=now,
            ))
        created += 1
    db.commit()

    return {
        "created": created,
        "already_existed": skipped,
        "unknown_chapters": sorted(set(unknown)),
        #: refused: the chapter belongs to another subject, or the code is empty
        "wrong_subject": wrong_subject,
        "note": "Existing families are left alone; a rename would break past comparisons.",
    }


class FamilySectionsIn(BaseModel):
    """Correcting which sections of the book a family covers -- never its label or
    chapter, which is what "a family is never renamed" protects."""

    from_sections: list[str] = Field(min_length=0, max_length=50)


@router.patch("/{subject}/concept-families/{code}")
def edit_family_sections(
    subject: str, code: str, body: FamilySectionsIn, db: Session = Depends(get_session),
) -> dict:
    """Correct which sections of the chapter an existing family covers.

    Everything about a family except this is permanent (see create_families: a code is
    never renamed, a chapter never moved, because a report's trend depends on the family
    meaning the same thing across every cycle it was ever used in). Which sections it
    covers is different -- it is metadata about where mapping should look for this
    family, not the family's own identity, and it is exactly the field a proposing model
    can get wrong without the label or the chapter being wrong at all: a chapter that is
    genuinely one whole section ("1", not NCERT's "1.1") produced families that all cited
    a question number instead ("30.1") because that was the only digit-shaped thing near
    the passage the model was shown. The family itself -- its name, its chapter -- was
    right; only the section it was filed under was not, and there was no way to fix that
    without deleting and recreating it under a new code, which would have broken every
    trend already keyed on the old one.
    """
    node = db.scalar(
        select(TaxonomyNode).where(
            TaxonomyNode.code == code, TaxonomyNode.kind == "concept_family",
        )
    )
    if node is None:
        raise HTTPException(404, f"no concept family {code!r} under {subject}")
    if not node.code.startswith(f"{subject}."):
        raise HTTPException(404, f"{code!r} does not belong to {subject}")

    proposal = db.scalar(
        select(ConceptFamilyProposal).where(ConceptFamilyProposal.code == code)
    )
    sections = clean_sections(body.from_sections)
    if proposal is not None:
        proposal.from_sections = sections
    else:
        # A family created before any proposal tracked it (the oldest ones, or one typed
        # in by hand) has no row to correct -- add one, so this and every future read of
        # "what sections does this family cover" has somewhere to answer from.
        db.add(ConceptFamilyProposal(
            curriculum_version=node.curriculum_version, subject_code=subject,
            run_id=uuid.uuid4().hex, source="manual", model=None,
            code=code, label=node.label, chapter_id=node.parent_id,
            rationale="section corrected by hand", evidence=sections,
            from_sections=sections, applied_at=datetime.now(UTC).isoformat(),
        ))
    db.commit()

    return {"code": code, "from_sections": sections}


@router.delete("/{subject}/concept-families/{code}")
def delete_family(subject: str, code: str, db: Session = Depends(get_session)) -> dict:
    """Remove a family nobody has used yet.

    The audit route already deletes families this way for two specific, mechanically
    detectable problems (wrong subject, an empty slug). This is the same safety check --
    refused the moment any Question references the family, because deleting a family a
    mark is already filed under would orphan it -- for every OTHER way a proposing model
    can produce a family that should never have been created: an answer in the wrong
    language entirely (a Tamil chapter can get a Hindi or English label the model
    happened to slip into), a hallucinated topic, or anything else a reviewer catches by
    reading rather than by a rule this code could check for itself. Bulk-applying a run's
    proposals without reading each one first is exactly how one of these gets through --
    see FamiliesIn's own docstring, "reviewed, not accepted wholesale" -- and this is the
    undo for that.
    """
    from app.models import Question

    node = db.scalar(
        select(TaxonomyNode).where(
            TaxonomyNode.code == code, TaxonomyNode.kind == "concept_family",
        )
    )
    if node is None:
        raise HTTPException(404, f"no concept family {code!r} under {subject}")
    if not node.code.startswith(f"{subject}."):
        raise HTTPException(404, f"{code!r} does not belong to {subject}")

    used = db.scalar(select(func.count(Question.id)).where(
        Question.concept_family_id == node.id
    ))
    if used:
        raise HTTPException(
            409,
            f"{used} question(s) are already filed under {code!r}; deleting it would "
            f"orphan their marks. Use POST /concept-families/merge to move them to "
            f"another family first.",
        )

    for p in db.scalars(select(ConceptFamilyProposal).where(ConceptFamilyProposal.code == code)):
        db.delete(p)
    # A family that survived a merge (POST /concept-families/merge) carries a
    # TaxonomyAlias row for every family folded into it, recording what it used to be
    # called -- taxonomy_alias.node_id is a foreign key with no cascade, so deleting the
    # node while one of these still points at it violates that constraint at the DB level
    # and surfaces as an unhandled 500, not the 404/409 this route otherwise returns.
    # Confirmed on a real merge survivor (X.ECO.CF.NOTES_FOR_TEACHERS, kept over
    # X.ECO.CF.NOTES_FOR_TEACHER) that itself turned out to need deleting afterwards.
    for a in db.scalars(select(TaxonomyAlias).where(TaxonomyAlias.node_id == node.id)):
        db.delete(a)
    db.delete(node)
    db.commit()
    return {"code": code, "deleted": True}


def _family_label_is_corrupted(label: str) -> bool:
    """Whether an APPLIED concept_family's ``label`` shows the broken-ToUnicode-CMap
    defect described in app.ingest.tamil_text's module docstring.

    The original (pre-fix) X.TAM proposer run read this defect straight out of corrupted
    ``book_chunk`` text, so every family it proposed inherited the same corruption in its
    label: missing pulli marks throughout, and in the worse cases a run of Bengali,
    Devanagari or even Thai characters spliced in where the model's ToUnicode-mangled
    input pointed it at the wrong glyphs entirely.

    Reused rather than reinvented: ``tamil_text_is_corrupted`` already carries three
    independent signals for exactly this defect, verified against real production
    passages (see that function's own docstring). The one thing worth calling out is
    which of those three signals actually fires on a *label* rather than a paragraph.
    Its pulli-ratio check is gated behind >=20 Tamil consonants because a short string
    can legitimately have zero pulli-bearing consonants by chance -- and a family label
    ('பாககளின் ஓசை வகைகள்', 40-odd characters) is exactly the regime that gate exists
    for: most labels never reach 20 consonants, so the ratio check quietly does nothing
    on them. That is fine here, not a gap to work around, because the other two signals
    are both length-independent and both are exactly what a spot check of the real 458
    corrupted rows found: a non-Tamil Indic script appearing at all
    (X.TAM.CF.SOCIAL_BACKGROUND_HISTORICAL_CONTEXT's label is almost entirely Bengali),
    or a Latin letter fused into a Tamil run with no space. A label that does happen to
    be long enough for the pulli-ratio gate still gets that check for free, at no extra
    cost -- this function makes no threshold decision of its own to defend.
    """
    return tamil_text_is_corrupted(label)


def _family_question_counts(db: Session, family_ids: list[str]) -> dict[str, int]:
    """How many real ``Question`` rows point at each family, keyed by taxonomy_node id."""
    from app.models import Question

    if not family_ids:
        return {}
    return dict(db.execute(
        select(Question.concept_family_id, func.count(Question.id))
        .where(Question.concept_family_id.in_(family_ids))
        .group_by(Question.concept_family_id)
    ).all())


@router.post("/{subject}/concept-families/repair-corrupted")
def repair_corrupted_families(
    subject: str, dry_run: bool = True, db: Session = Depends(get_session),
) -> dict:
    """Fix an APPLIED family's corrupted ``label`` in place, from a clean re-proposal.

    This is the cleanup for a specific production incident, not a general tool: X.TAM's
    original LLM proposer run read the book through a font whose ToUnicode CMap was
    broken (app.ingest.tamil_text), so the families it produced back then have labels
    with the same corruption baked in -- missing pulli marks, and in the worse cases
    whole runs of the wrong script spliced in (see _family_label_is_corrupted). The book
    has since been re-ingested through the fix and re-proposed cleanly
    (POST .../propose-llm?force=true), but those clean proposals were never applied --
    doing so naively would create a SECOND family per chapter concept and leave the
    corrupted originals in place, and worse, any corrupted family a real Question already
    references (Question.concept_family_id is required, non-nullable) cannot simply be
    deleted and replaced without orphaning real marks.

    So this only ever does one thing to existing data: UPDATE a corrupted family's
    ``label`` column to a clean proposal's label. ``code``, ``id``, and every existing FK
    reference (Question.concept_family_id included) are never touched -- a label is
    display text, not identity, exactly the same reasoning edit_family_sections already
    relies on for `from_sections`.

    A "confident match" is deliberately narrow, because a false positive here corrupts
    real data a second time: the corrupted family's chapter must have exactly one OTHER
    corrupted family under it (i.e. this is the only broken family in that chapter) and
    exactly one clean proposal under it from the latest propose-llm run. Where a chapter's
    old family count and its new proposal count don't line up 1:1 -- the "one family
    became five" case found for ASIRIYAPPA_GRAMMAR/poetry-types -- this deliberately does
    not guess which proposal it maps to; it is left for a human, in `flagged_for_review`.

    ``dry_run`` (default true) reports what WOULD happen and writes nothing. Pass
    ``dry_run=false`` to actually write the matched labels. Idempotent either way: a
    family already fixed (by this route or by hand) reads as clean on the next call and
    is neither reported nor touched again.
    """
    version = "CBSE-2026-27"
    nodes_by_id = {n.id: n for n in db.scalars(select(TaxonomyNode))}
    families = [
        n for n in nodes_by_id.values()
        if n.kind == "concept_family" and n.code.startswith(f"{subject}.CF.")
    ]
    corrupted = [f for f in families if _family_label_is_corrupted(f.label)]
    question_counts = _family_question_counts(db, [f.id for f in corrupted])

    # Only the latest run's clean proposals are candidates -- an older run may itself
    # carry the same corruption this route exists to fix, so it is never a source of
    # truth here, only the run made after tamil_text.py's fix went in.
    proposal_rows = list(
        db.scalars(
            select(ConceptFamilyProposal)
            .where(ConceptFamilyProposal.subject_code == subject)
            .where(ConceptFamilyProposal.curriculum_version == version)
            .order_by(ConceptFamilyProposal.created_at)
        )
    )
    latest_run = proposal_rows[-1].run_id if proposal_rows else None
    latest_proposals = [p for p in proposal_rows if p.run_id == latest_run]

    proposals_by_chapter: dict[str, list[ConceptFamilyProposal]] = {}
    for p in latest_proposals:
        if p.chapter_id:
            proposals_by_chapter.setdefault(p.chapter_id, []).append(p)

    corrupted_by_chapter: dict[str, list[TaxonomyNode]] = {}
    for f in corrupted:
        if f.parent_id:
            corrupted_by_chapter.setdefault(f.parent_id, []).append(f)

    def chapter_label(chapter_id: str | None) -> str | None:
        chapter = nodes_by_id.get(chapter_id) if chapter_id else None
        return chapter.label if chapter else None

    would_fix: list[dict] = []
    flagged_for_review: list[dict] = []
    unreferenced: list[dict] = []
    matches: dict[str, ConceptFamilyProposal] = {}  # family.id -> matched proposal

    for f in sorted(corrupted, key=lambda n: n.code):
        candidates = proposals_by_chapter.get(f.parent_id or "", [])
        siblings = corrupted_by_chapter.get(f.parent_id or "", [])
        confident = (
            f.parent_id is not None
            and len(siblings) == 1
            and len(candidates) == 1
        )
        if confident:
            matches[f.id] = candidates[0]
            would_fix.append({
                "code": f.code, "old_label": f.label, "new_label": candidates[0].label,
                "chapter": chapter_label(f.parent_id),
            })
            continue

        count = question_counts.get(f.id, 0)
        entry = {
            "code": f.code, "old_label": f.label,
            "chapter": chapter_label(f.parent_id),
            "candidate_labels": [c.label for c in candidates],
            "question_count": count,
        }
        if count == 0:
            unreferenced.append(entry)
        else:
            flagged_for_review.append(entry)

    applied = 0
    if not dry_run and matches:
        for family_id, proposal in matches.items():
            nodes_by_id[family_id].label = proposal.label
            applied += 1
        db.commit()
        for entry in would_fix:
            entry["applied"] = True
    else:
        for entry in would_fix:
            entry["applied"] = False

    return {
        "subject": subject,
        "dry_run": dry_run,
        "corrupted_found": len(corrupted),
        "would_fix": would_fix,
        "flagged_for_review": flagged_for_review,
        "unreferenced": unreferenced,
        "applied": applied,
        "note": (
            "unreferenced families have zero Question rows pointing at them and no "
            "confident clean match -- safe to remove outright, but this route never "
            "deletes anything; use DELETE /concept-families/{code} yourself for those."
        ),
    }


def _audit_families(db: Session, subject: str) -> dict:
    """What is wrong with the families that exist under this subject's prefix."""
    from app.models import Question

    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
    families = [
        n for n in nodes.values()
        if n.kind == "concept_family" and n.code.startswith(f"{subject}.CF.")
    ]
    used = dict(db.execute(
        select(Question.concept_family_id, func.count(Question.id))
        .where(Question.concept_family_id.in_([f.id for f in families]))
        .group_by(Question.concept_family_id)
    ).all()) if families else {}

    def view(n: TaxonomyNode, problem: str) -> dict:
        chapter = nodes.get(n.parent_id) if n.parent_id else None
        return {
            "code": n.code, "label": n.label,
            "chapter_code": chapter.code if chapter else None,
            "questions": used.get(n.id, 0),
            "problem": problem,
        }

    wrong_subject, empty_code, duplicates = [], [], []
    seen_labels: dict[tuple[str, str], TaxonomyNode] = {}
    for n in sorted(families, key=lambda f: f.code):
        chapter = nodes.get(n.parent_id) if n.parent_id else None
        if chapter is None or not chapter.code.startswith(f"{subject}."):
            wrong_subject.append(
                view(n, f"chapter belongs to {chapter.code if chapter else 'nothing'}")
            )
            continue
        if n.code.endswith("."):
            empty_code.append(view(n, "empty code: the label's script cannot be slugified"))
            continue
        key = (chapter.id, _label_key(n.label))
        if key in seen_labels:
            duplicates.append(view(n, f"same idea as {seen_labels[key].code}"))
        else:
            seen_labels[key] = n
    removable = [f for f in wrong_subject + empty_code if f["questions"] == 0]
    return {
        "subject": subject,
        "families": len(families),
        "wrong_subject": wrong_subject,
        "empty_code": empty_code,
        "duplicates": duplicates,
        "removable": len(removable),
        "kept_because_used": [
            f for f in wrong_subject + empty_code if f["questions"] > 0
        ],
    }


@router.get("/{subject}/concept-families/audit")
def audit_families(subject: str, db: Session = Depends(get_session)) -> dict:
    """Families under this subject's prefix that should not be there, and what applying
    the audit would remove. Read-only.

    Three findings. ``wrong_subject``: coded X.MATH.CF.* but hanging off a Science or
    English chapter, which the proposal route used to produce for every chapter in the
    tree. ``empty_code``: a Hindi or Tamil heading whose slug is empty, so every such
    family shares one code. ``duplicates``: two families under one chapter whose labels
    read as one idea -- listed for a person, never removed here, because which name
    survives and which questions move is their call.
    """
    return _audit_families(db, subject)


@router.post("/{subject}/concept-families/audit/apply")
def apply_family_audit(subject: str, db: Session = Depends(get_session)) -> dict:
    """Remove the wrong-subject and empty-code families that no question references.

    A family any question points at is kept and named in the response: removing it would
    orphan marks. Duplicates are never touched here. Proposals for a removed family go
    with it, so the proposal screen stops offering it as already existing.
    """
    audit = _audit_families(db, subject)
    codes = {
        f["code"] for f in audit["wrong_subject"] + audit["empty_code"] if f["questions"] == 0
    }
    removed = 0
    if codes:
        for n in db.scalars(select(TaxonomyNode).where(TaxonomyNode.code.in_(codes))):
            for p in db.scalars(
                select(ConceptFamilyProposal).where(ConceptFamilyProposal.code == n.code)
            ):
                db.delete(p)
            db.delete(n)
            removed += 1
    db.commit()
    return {
        "subject": subject,
        "removed": removed,
        "kept_because_used": audit["kept_because_used"],
        "duplicates_left_for_review": len(audit["duplicates"]),
        "next": (
            f"POST /board-frequency/recompute?subject_code={subject} so the table drops "
            f"the removed rows." if removed else "nothing to remove"
        ),
    }


class MergeFamiliesIn(BaseModel):
    """Fold one or more duplicate families into the one that survives."""

    keep: str = Field(max_length=80)
    remove: list[str] = Field(min_length=1, max_length=20)


@router.post("/{subject}/concept-families/merge")
def merge_families(subject: str, body: MergeFamiliesIn, db: Session = Depends(get_session)) -> dict:
    """Merge duplicate families: every question, placement and proposal on a removed
    family is re-pointed at ``keep``, then the removed family is deleted.

    The survivor is a person's choice, which is why this is not part of the audit. A
    removed family's questions keep every mark they carry; only the family they roll up
    to changes, so a trend keyed on the survivor now sees both histories as one -- which
    is the point of merging.

    Refused unless every family named is under this subject and hangs off the same
    chapter as ``keep``: merging across chapters would file a question's marks under a
    chapter it was never about.
    """
    from app.models import Question, QuestionPlacement

    nodes = {n.code: n for n in db.scalars(select(TaxonomyNode).where(
        TaxonomyNode.kind == "concept_family"
    ))}
    keep = nodes.get(body.keep)
    if keep is None or not keep.code.startswith(f"{subject}.CF."):
        raise HTTPException(422, f"{body.keep!r} is not a concept family of {subject}")
    losers = []
    for code in body.remove:
        n = nodes.get(code)
        if n is None or not n.code.startswith(f"{subject}.CF."):
            raise HTTPException(422, f"{code!r} is not a concept family of {subject}")
        if n.id == keep.id:
            raise HTTPException(422, f"{code!r} is the family being kept")
        if n.parent_id != keep.parent_id:
            raise HTTPException(
                422,
                f"{code!r} is under a different chapter from {body.keep!r}; a merge across "
                f"chapters would file questions under a chapter they were never about",
            )
        losers.append(n)

    moved_questions = moved_placements = 0
    for n in losers:
        for q in db.scalars(select(Question).where(Question.concept_family_id == n.id)):
            q.concept_family_id = keep.id
            moved_questions += 1
        for p in db.scalars(select(QuestionPlacement).where(
            QuestionPlacement.chapter_id == n.id
        )):
            p.chapter_id = keep.id
            moved_placements += 1
        for prop in db.scalars(select(ConceptFamilyProposal).where(
            ConceptFamilyProposal.code == n.code
        )):
            db.delete(prop)
        for row in db.scalars(select(TaxonomyAlias).where(TaxonomyAlias.node_id == n.id)):
            row.node_id = keep.id
        db.add(TaxonomyAlias(node_id=keep.id, alias=n.label, locale="en"))
        db.delete(n)
    db.commit()
    return {
        "kept": keep.code,
        "removed": [n.code for n in losers],
        "questions_moved": moved_questions,
        "placements_moved": moved_placements,
        "next": (
            f"POST /board-frequency/recompute?subject_code={subject} if any board paper "
            f"was mapped to a removed family."
        ),
    }


def _merge_duplicate_families(candidates: list[dict]) -> list[dict]:
    """Collapse a proposal run's near-duplicates: same code twice, or the same idea
    named twice under a chapter with different codes. `from_sections` is unioned so
    neither copy's section evidence is lost.
    """
    by_code: dict[str, dict] = {}
    order: list[str] = []
    for fam in candidates:
        code = fam["code"]
        if code not in by_code:
            by_code[code] = dict(fam)
            order.append(code)
        else:
            existing = by_code[code]
            existing["from_sections"] = sorted(
                set(existing.get("from_sections") or []) | set(fam.get("from_sections") or [])
            )

    by_key: dict[tuple[str, str], str] = {}
    merged: dict[str, dict] = {}
    for code in order:
        fam = by_code[code]
        key = (fam["chapter_code"], fam["label"].strip().lower())
        canonical = by_key.get(key)
        if canonical is None:
            by_key[key] = code
            merged[code] = fam
        else:
            target = merged[canonical]
            target["from_sections"] = sorted(
                set(target.get("from_sections") or []) | set(fam.get("from_sections") or [])
            )
    return list(merged.values())


@router.post("/{subject}/concept-families/auto-apply")
def auto_apply_families(
    subject: str, dry_run: bool = True, db: Session = Depends(get_session)
) -> dict:
    """Propose, dedupe, and create concept families in one call -- for a deployment with
    no shell to run `scripts.apply_concept_families` from.

    `dry_run` defaults true on purpose: this still creates dozens to hundreds of families
    in one call, and a family is never renamed afterwards (see `create_families`), so the
    default is to show what would be created, not create it. Pass `?dry_run=false` once
    the list has been read.
    """
    proposed = propose_families(subject, db)
    candidates = [f for f in proposed["families"] if not f["already_exists"]]
    merged = _merge_duplicate_families(candidates)

    report = {
        "subject": subject,
        "existing": proposed["existing"],
        "proposed": proposed["proposed"],
        "candidates": len(candidates),
        "after_merge": len(merged),
        "duplicates_merged": len(candidates) - len(merged),
        "without_a_section": sum(1 for f in merged if not f["from_sections"]),
    }
    if dry_run:
        report["dry_run"] = True
        report["would_create"] = [
            {"chapter_label": f["chapter_label"], "label": f["label"], "code": f["code"]}
            for f in merged
        ]
        return report

    # FamiliesIn caps a single call at 200 -- the same limit `create_families` enforces
    # on a human posting from the review screen. A proposal run routinely clears that
    # (229 raw, well over 200 even after merging), so this has to go in batches or the
    # very first real subject trips a validation error the caller never gets to see as
    # anything but a bare 500.
    created = already_existed = 0
    unknown: list[str] = []
    batch_size = 200
    for i in range(0, len(merged), batch_size):
        batch = merged[i : i + batch_size]
        result = create_families(subject, FamiliesIn(families=batch), db)
        created += result["created"]
        already_existed += result["already_existed"]
        unknown.extend(result["unknown_chapters"])

    return {
        **report,
        "dry_run": False,
        "created": created,
        "already_existed": already_existed,
        "unknown_chapters": sorted(set(unknown)),
    }


@router.post("/{subject}/embed")
def embed_batch(
    subject: str,
    limit: int = 32,
    db: Session = Depends(get_session),
) -> dict:
    """Embed up to `limit` chunks and report what is left.

    Batched deliberately: a single request that embedded all 213 chunks would sit for a
    minute or more, which a platform proxy is entitled to cut off halfway. The caller loops
    until `remaining` is zero, and a dropped request costs one batch rather than the lot.
    """
    from app.ingest.jina import JinaEmbedder

    settings = get_settings()
    if not settings.jina_api_key:
        raise HTTPException(
            409,
            "no embedding key configured. Set YAADHUM_JINA_API_KEY on the API service. "
            "Without it only exact matches resolve, so PRACTISED, ADAPTED and NOVEL all "
            "collapse and Competency Tier falls back to the paper's blueprint.",
        )

    pending = db.scalars(
        select(BookChunk)
        .where(BookChunk.subject_code == subject, BookChunk.embedding.is_(None))
        .limit(max(1, min(limit, 64)))
    ).all()
    if not pending:
        return {"embedded": 0, "remaining": 0, "done": True}

    embedder = JinaEmbedder(
        settings.jina_api_key, model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    try:
        vectors = embedder.embed_texts([c.text for c in pending])
    except RuntimeError as exc:
        # surfaced as a clean 502 with Jina's own reason, not a raw traceback -- the
        # request itself already retries what's worth retrying (see JinaEmbedder), so
        # anything that reaches here is either a real outage or a bad chunk to look at.
        raise HTTPException(502, str(exc)) from exc
    if len(vectors) != len(pending):
        raise HTTPException(
            502,
            f"provider returned {len(vectors)} vectors for {len(pending)} chunks; "
            f"refusing to write a misaligned index",
        )
    for chunk, vector in zip(pending, vectors, strict=True):
        chunk.embedding = vector
    db.commit()

    remaining = db.scalar(
        select(func.count(BookChunk.id)).where(
            BookChunk.subject_code == subject, BookChunk.embedding.is_(None)
        )
    )
    return {"embedded": len(pending), "remaining": remaining or 0, "done": not remaining}


# --------------------------------------------------------------------------------------
# Reading the chapter, rather than only its headings
# --------------------------------------------------------------------------------------
def _chapter_passages(
    db: Session, subject: str, chapter_id: str
) -> list[tuple[str, str, str]]:
    """(reference, section number, text) for one chapter, in the book's own order.

    The section number is the chunk's own ``section_number`` -- the exact field mapping
    reads at placement time (see ``app.ingest.probe``'s ``Candidate.section``) -- not one
    re-derived here a second, different way. It used to be looked up through the chapter's
    subtopic nodes instead (matching ``BookChunk.node_id`` against those nodes' own ids),
    which never once matched anything: every chunk is filed under the CHAPTER's node_id,
    not any subtopic's (see ``_load`` above), so every passage this shows a proposing model
    carried an empty section regardless of what the book's own contents actually say. A
    model asked to state which sections a family draws on with no real section ever shown
    to it has nothing to answer from but its own guess -- so every ``from_sections`` it
    wrote answered to a number retrieval would never independently produce, and mapping
    could never find a family that claimed the section a question actually landed in.
    """
    out: list[tuple[str, str, str]] = []
    for chunk in db.scalars(
        select(BookChunk)
        .where(BookChunk.subject_code == subject)
        .where(BookChunk.node_id == chapter_id)
        .order_by(BookChunk.id)
    ):
        out.append((chunk.reference or "?", chunk.section_number or "", chunk.text))
    return out


@router.get("/{subject}/concept-families/proposals")
def read_proposals(subject: str, db: Session = Depends(get_session)) -> dict:
    """What the last run proposed, whether or not any of it was applied."""
    version = "CBSE-2026-27"
    rows = list(
        db.scalars(
            select(ConceptFamilyProposal)
            .where(ConceptFamilyProposal.subject_code == subject)
            .where(ConceptFamilyProposal.curriculum_version == version)
            .order_by(ConceptFamilyProposal.created_at)
        )
    )
    if not rows:
        return {"subject": subject, "runs": [], "proposed": 0, "families": []}

    # Both, not just the label: applying a proposal at POST /concept-families is keyed on
    # chapter_code, so returning only a human label made the review-then-apply round trip
    # impossible without a second lookup nobody would guess they needed.
    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
    latest = rows[-1].run_id
    current = [r for r in rows if r.run_id == latest]
    return {
        "subject": subject,
        "run_id": latest,
        "runs": sorted({r.run_id for r in rows}),
        "model": current[0].model,
        "source": current[0].source,
        "proposed": len(current),
        "applied": sum(1 for r in current if r.applied_at),
        "families": [
            {
                "code": r.code, "label": r.label,
                "chapter": nodes[r.chapter_id].label if r.chapter_id in nodes else None,
                "chapter_code": nodes[r.chapter_id].code if r.chapter_id in nodes else None,
                "rationale": r.rationale,
                "evidence": r.evidence or [],
                "from_sections": r.from_sections or [],
                "applied_at": r.applied_at,
            }
            for r in current
        ],
    }


@router.post("/{subject}/concept-families/propose-llm", status_code=status.HTTP_201_CREATED)
def propose_families_with_a_model(
    subject: str,
    force: bool = False,
    db: Session = Depends(get_session),
) -> dict:
    """Read every loaded chapter of a subject and propose its families. One-time.

    Refuses to run a second time unless ``force=true``: the pass costs real money, and a
    silent re-run would also produce a second set of proposals for the same subject with
    nothing saying which one a person actually looked at. A forced re-run is stored under
    a new run id beside the first rather than replacing it.

    Nothing is applied. The proposals are stored and reviewed, because renaming a family
    after a class has been tested breaks every trend that references it.
    """
    version = "CBSE-2026-27"
    settings = get_settings()

    existing = db.scalar(
        select(func.count(ConceptFamilyProposal.id))
        .where(ConceptFamilyProposal.subject_code == subject)
        .where(ConceptFamilyProposal.curriculum_version == version)
    )
    if existing and not force:
        raise HTTPException(
            409,
            f"{subject} already has {existing} stored proposals -- read them at "
            f"GET /platform/books/{subject}/concept-families/proposals. Pass force=true "
            f"to run again; the new run is stored beside the old one, not over it.",
        )

    chapters = [
        n for n in db.scalars(
            select(TaxonomyNode)
            .where(TaxonomyNode.kind == "chapter")
            .where(TaxonomyNode.code.startswith(f"{subject}."))
            .order_by(TaxonomyNode.path)
        )
    ]
    if not chapters:
        raise HTTPException(422, f"no chapters loaded for {subject}")

    from app.curriculum.families import slugify
    from app.curriculum.llm_families import AnthropicFamilyProposer

    try:
        proposer = AnthropicFamilyProposer(
            settings.anthropic_api_key or "",
            model=settings.model_high_volume,
            effort=settings.model_effort,
        )
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc

    run_id = str(uuid.uuid4())
    written = 0
    skipped: list[str] = []
    failed: list[dict] = []
    for chapter in chapters:
        passages = _chapter_passages(db, subject, chapter.id)
        if not passages:
            skipped.append(f"{chapter.label}: no chunks loaded")
            continue
        # One chapter at a time, committed as it completes. Without this a failure on
        # chapter seven threw away the six already paid for and returned a bare 500: the
        # money was spent, the work was done, and nothing was kept or explained.
        try:
            proposed = proposer.propose(chapter.label, passages)
        except Exception as exc:  # noqa: BLE001 -- the reason is reported, not swallowed
            db.rollback()
            failed.append({
                "chapter": chapter.label,
                "error": f"{type(exc).__name__}: {exc}"[:400],
            })
            continue

        seen: set[str] = set()
        for family in proposed:
            code = f"{subject}.CF.{slugify(family.code_label or family.label)}"
            if code in seen:
                continue
            seen.add(code)
            db.add(
                ConceptFamilyProposal(
                    curriculum_version=version, subject_code=subject, run_id=run_id,
                    source="llm", model=proposer.model,
                    code=code, label=family.label, chapter_id=chapter.id,
                    rationale=family.rationale, evidence=family.evidence,
                    from_sections=family.from_sections,
                )
            )
            written += 1
        db.commit()

    return {
        "subject": subject,
        "run_id": run_id,
        "model": proposer.model,
        "chapters_read": len(chapters) - len(skipped) - len(failed),
        "proposed": written,
        "skipped": skipped,
        #: chapters whose model call raised. The run keeps going and keeps what it has;
        #: re-running with force=true retries them in a new run.
        "failed": failed,
        # Every field the knowledge base could not vouch for, kept rather than logged
        # away: how often the model has to be corrected is the measure of whether its
        # reading can be trusted at all.
        "corrections": [
            {"chapter": chapter, "dropped": violations}
            for chapter, violations in proposer.violations
        ],
        # Zero survivors is not "no families in this book" -- it means the guardrail
        # rejected every one, which is a fault in the prompt or the citation format, not a
        # finding about the subject. It read as an ordinary empty result the first time and
        # cost a paid run to notice.
        "warning": (
            "Every proposed family was dropped. Nothing was stored and this is not a "
            "result about the book -- read `corrections` and fix the cause before "
            "re-running."
            if written == 0 and proposer.violations and not failed
            else (
                f"{len(failed)} of {len(chapters)} chapters failed -- see `failed`. What "
                f"succeeded is stored; re-run with force=true to retry."
                if failed
                else None
            )
        ),
        "next": (
            f"Review at GET /platform/books/{subject}/concept-families/proposals, then "
            f"POST the ones you want to /platform/books/{subject}/concept-families."
            if written
            else "Nothing was stored, so there is nothing to review."
        ),
    }
