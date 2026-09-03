"""Loading a subject's book through the browser.

Same extraction, same verification, same refusal to write a chapter that disagrees with
the contents page as `scripts.ingest_book` -- this is a second entry point to one pipeline,
not a second pipeline. It exists because a deployment without shell access still has to be
able to load a book, and the alternative was asking a school to run Python.

Order is enforced: the contents page first, because it is the oracle every chapter is
checked against, and a chapter accepted without it would be accepted on trust.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from sqlalchemy.orm import Session

from app.api.deps import require_platform_admin
from app.api.upload import to_tempfile
from app.config import get_settings
from app.curriculum import CURRICULA, chapter_title
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
from app.ingest.embed import classify_familiarity
from app.ingest.probe import LexicalIndex, SemanticIndex, locate
from app.models import (
    BookChunk,
    BookSource,
    CanonicalProcedure,
    ChapterBoardUnit,
    ConceptFamilyProposal,
    IngestJob,
    TaxonomyNode,
)

router = APIRouter(
    prefix="/platform/books", tags=["knowledge-base"],
    dependencies=[Depends(require_platform_admin)],
)

#: Below this gap to the runner-up, the top chapter won by a hair. On the 30(B) set the
#: single wrong answer had the smallest margin of any row, so this is where a question
#: should go to a human rather than into a report.
MIN_MARGIN = 0.002


_to_tempfile = to_tempfile

#: One subject code per physical Hindi book -- Kshitij, Kritika, Sparsh, Sanchayan -- same
#: reasoning as Social Science and English's X.ENG.* prefix.
HINDI_SUBJECT_PREFIX = "X.HIN"


def _hindi_text(pdf_bytes: bytes) -> str:
    """The book's real Unicode text, for a subject whose own PDF text layer decodes as
    mojibake (see app.ingest.hindi_ocr for why).

    Prefers Tesseract when this deployment can run it (see app.ingest.hindi_text) --
    local, no network round trip, and the accuracy this project needs. Falls back to
    Gemini otherwise. Either failure is raised as a 409 or 502, never a bare 500: a
    missing key/binary is an operator setup step, not a broken upload, and a network
    failure already survived its own retries before reaching here.
    """
    settings = get_settings()
    try:
        return hindi_read_text(
            pdf_bytes, gemini_api_key=settings.gemini_api_key, gemini_model=settings.gemini_model,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
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


def _run_ingest_job(job_id: str) -> None:
    """The slow part of a Hindi upload, run after the request that queued it has already
    returned. Opens its own session -- BackgroundTasks runs after the request-scoped one
    passed to the endpoint has been closed, not before, so reusing it would operate on a
    dead connection.

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
        try:
            if job.kind == "contents":
                result = _process_contents(
                    db, job.subject_code, job.curriculum_version, job.pdf_bytes, job.edition,
                )
            else:
                result = _process_chapter(
                    db, job.subject_code, job.curriculum_version, job.filename, job.pdf_bytes,
                )
            job.status = "succeeded"
            job.result = result
        except HTTPException as exc:
            job.status = "failed"
            job.error_status = exc.status_code
            job.error_detail = str(exc.detail)
        except Exception as exc:  # noqa: BLE001 -- see docstring: this must never escape
            job.status = "failed"
            job.error_status = 500
            job.error_detail = f"{type(exc).__name__}: {exc}"
        job.finished_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def _source(db: Session, subject: str, version: str) -> BookSource | None:
    return db.scalar(
        select(BookSource).where(
            BookSource.subject_code == subject, BookSource.curriculum_version == version
        )
    )


@router.post("/{subject}/curriculum", status_code=status.HTTP_201_CREATED)
def setup_curriculum(subject: str, db: Session = Depends(get_session)) -> dict:
    """Board units, their weightage, and the chapter mapping -- before any book.

    This layer does not come from the book: CBSE publishes weightage per unit, and a unit
    may span several chapters or exist where none does. It was previously only reachable
    through `scripts.seed`, which a deployment without shell access cannot run -- so the
    console could load a book into a taxonomy that had nowhere to put it.

    Idempotent: re-running adds only what is missing.
    """
    curriculum = CURRICULA.get(subject)
    if curriculum is None:
        raise HTTPException(
            422,
            f"no curriculum defined for {subject!r}. Known: {sorted(CURRICULA)}. "
            f"Board weightage comes from the CBSE syllabus, not the book, so it has to be "
            f"defined before a book can be loaded.",
        )
    created = apply_curriculum(db, curriculum)
    return {
        "subject": subject,
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
) -> dict:
    """Everything upload_contents does once it has the bytes -- shared by the synchronous
    endpoint (every subject but Hindi) and _run_ingest_job (Hindi, backgrounded because a
    Gemini call cannot finish inside Render's request timeout). Raises HTTPException on a
    real problem with the upload; both callers let that propagate to where it belongs --
    the response for a synchronous upload, the job row for a backgrounded one.
    """
    if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == subject)) is None:
        raise HTTPException(
            422,
            f"subject {subject!r} is not in the taxonomy yet. Set up the curriculum first "
            f"-- the board units a chapter's marks count towards come from the syllabus, "
            f"not from the book.",
        )

    is_hindi = subject.startswith(HINDI_SUBJECT_PREFIX)
    text = _hindi_text(pdf_bytes) if is_hindi else None
    path = _bytes_to_tempfile(pdf_bytes)
    try:
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
        # re-uploading the contents page replaces the oracle but keeps what is loaded
        source.expected_sections = expected
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


def _process_chapter(
    db: Session, subject: str, version: str, name: str, pdf_bytes: bytes,
) -> dict:
    """Everything upload_chapter does once it has the bytes -- see _process_contents for
    why this is split out from the route handler.
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
    text_override = _hindi_text(pdf_bytes) if is_hindi else None
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
        # Scoped by subject code, not guessed from what the normal section detection
        # happens to find on a given file.
        extract = extract_chapter(
            path, number=number, name=name,
            title=chapter_title(subject, number) or "",
            single_section=subject.startswith("X.ENG") or is_hindi,
            body_bucket="E" if subject == "X.ENG.WB" else "T",
            text_override=text_override,
        )
        toc = {
            int(k): [Section(s["number"], s["title"]) for s in v]
            for k, v in source.expected_sections.items()
        }
        expected_title = (source.expected_chapters or {}).get(str(number))
        if toc:
            verify_against_toc(extract, toc)
            extract.verified_against = source.edition or "contents page"
        else:
            # No section list published for this subject. Check what the contents page
            # does say -- that this is the chapter the book calls `number` -- then check
            # the chapter's own numbering for gaps, and leave it marked unverified.
            if expected_title and title_key(expected_title) != title_key(extract.title):
                extract.problems.append(
                    f"the contents page calls chapter {number} "
                    f"{expected_title!r}, not {extract.title!r}"
                )
            verify_structure(extract)
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
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
    db: Session = Depends(get_session),
) -> dict:
    """One chapter PDF, verified against the contents page before anything is written.

    See upload_contents: a Hindi subject is backgrounded the same way.
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

    return _process_chapter(db, subject, version, name, pdf_bytes)


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
        elif chunk.section and not existing.section_number:
            # A passage loaded before the section was recorded. Re-uploading the file was
            # the obvious way to fix that and did nothing at all: a chunk is written only
            # when its hash is absent, and the same file hashes the same, so every chunk
            # already existed and the run reported nothing written. Filling the gap in
            # place touches neither the text nor the vector, so the book does not have to
            # be embedded again to gain the topics it always had.
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


#: '13.2', '4.3.1'. What a section number looks like, so a proposal that answered with a
#: sentence -- one run returned "Section on spherical mirror introduction" -- is dropped
#: rather than stored as a section nothing will ever match.
SECTION_NUMBER = re.compile(r"^\d{1,2}(?:\.\d{1,2}){1,2}$")


def clean_sections(values) -> list[str]:
    """Only the entries that are section numbers, in the order given, without repeats."""
    out: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if SECTION_NUMBER.match(text) and text not in out:
            out.append(text)
    return out


class FamiliesIn(BaseModel):
    """The families to create. Reviewed, not accepted wholesale."""

    families: list[dict] = Field(min_length=1, max_length=200)


@router.get("/{subject}/concept-families")
def propose_families(subject: str, db: Session = Depends(get_session)) -> dict:
    """Candidate families from the book's own section headings.

    A proposal, never applied automatically: renaming a family after a class has been
    tested breaks every trend that references it, so the list is a commitment and a
    commitment is a person's to make.
    """
    from app.curriculum.families import propose

    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
    chapters = {n.id: n for n in nodes.values() if n.kind == "chapter"}

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

    existing = {n.code for n in nodes.values() if n.kind == "concept_family"}

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
    #: a chapter a run has already covered does not need its headings suggesting as well
    covered = {row["chapter_code"] for row in stored}
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
        if p.chapter_code not in covered
    ]
    proposals.sort(key=lambda r: (r["chapter_label"], r["label"]))
    return {
        "subject": subject,
        "existing": len(existing),
        "proposed": len(proposals),
        #: proposals that name no section a question could be matched against. They can
        #: still be created; they just cannot be chosen by section afterwards.
        "without_a_section": sum(1 for p in proposals if not p["from_sections"]),
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
    created, skipped, unknown = 0, 0, []
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
        "note": "Existing families are left alone; a rename would break past comparisons.",
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
    vectors = embedder.embed_texts([c.text for c in pending])
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

    Sections come from the subtopic nodes the chunks hang off, so the number shown to the
    model is the one the taxonomy holds -- not one re-derived from the text, which could
    disagree with what a later placement is checked against.
    """
    sections = {
        n.id: n.code.rsplit(".S", 1)[-1].replace("_", ".")
        for n in db.scalars(
            select(TaxonomyNode).where(TaxonomyNode.parent_id == chapter_id)
        )
    }
    out: list[tuple[str, str, str]] = []
    for chunk in db.scalars(
        select(BookChunk)
        .where(BookChunk.subject_code == subject)
        .where(BookChunk.node_id.in_([chapter_id, *sections]))
        .order_by(BookChunk.id)
    ):
        out.append((chunk.reference or "?", sections.get(chunk.node_id, ""), chunk.text))
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
            code = f"{subject}.CF.{slugify(family.label)}"
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
