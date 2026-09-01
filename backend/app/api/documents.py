"""Keeping and serving the pages that were scanned.

Everything a mark rests on is stored: the question paper as it was uploaded, and each
student's answer script. A report that says a boy lost three marks on question 14 is a
claim about a piece of paper, and a principal who forwards that report to a parent has to
be able to produce the paper.

Pages are served one at a time, by index, so a browser can show a script without pulling
twenty megabytes at once, and so a page can be replaced without touching the rest.
"""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_reader
from app.db import get_session
from app.models import Assessment, ScanDocument, ScanPage, School, StudentProfile
from app.storage import get_object_store

router = APIRouter(tags=["documents"])

#: A phone photograph of one page. Well above this is not a page.
MAX_PAGE_BYTES = 12 * 1024 * 1024

CONTENT_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "pdf": "application/pdf", "tif": "image/tiff",
    "tiff": "image/tiff",
}


def content_type_for(filename: str | None, declared: str | None) -> str:
    """What this upload is. One definition, so the paper route and the script route
    cannot disagree about what a .jpeg is."""
    suffix = (filename or "").rsplit(".", 1)[-1].lower()
    if suffix in CONTENT_TYPES:
        return CONTENT_TYPES[suffix]
    if declared and declared.startswith(("image/", "application/pdf")):
        return declared
    return "application/octet-stream"


def store_document(
    db: Session,
    *,
    school_id: str,
    assessment_id: str,
    kind: str,
    pages: list[tuple[bytes, str, dict | None]],
    student_id: str | None = None,
    uploaded_by: str = "",
) -> ScanDocument:
    """Write one document and its pages.

    A second upload of the same document supersedes the first rather than adding to it:
    re-scanning a paper is a correction, and two versions of the same script sitting side
    by side with no way to tell which the marks came from is worse than either.
    """
    digest = hashlib.sha256()
    for content, _, _ in pages:
        digest.update(content)

    existing = db.scalars(
        select(ScanDocument).where(
            ScanDocument.assessment_id == assessment_id,
            ScanDocument.kind == kind,
            ScanDocument.student_id.is_(None) if student_id is None
            else ScanDocument.student_id == student_id,
        )
    ).all()
    for old in existing:
        _forget_pages(old)
        db.delete(old)
    db.flush()

    document = ScanDocument(
        school_id=school_id, assessment_id=assessment_id, student_id=student_id,
        kind=kind, page_count=len(pages), sha256=digest.hexdigest(),
        uploaded_by=uploaded_by[:120],
    )
    db.add(document)
    db.flush()

    store = get_object_store()
    for index, (content, content_type, quality) in enumerate(pages):
        key = _page_key(document, index, content_type)
        stored = store.put(key, io.BytesIO(content), content_type=content_type)
        db.add(ScanPage(
            document_id=document.id, index=index, content_type=content_type,
            byte_size=len(content), quality=quality,
            storage_key=key, storage_uri=stored.uri, sha256=stored.sha256,
        ))
    db.flush()
    return document


def _page_key(document: ScanDocument, index: int, content_type: str) -> str:
    """Where a page lives in the store.

    Keyed by school first, so one school's work is one prefix: that is what makes a bucket
    policy, a lifecycle rule or a deletion request expressible without touching anything
    else. The document id is in the path, so a re-scan writes new objects rather than
    overwriting the ones a stored mark still refers to.
    """
    suffix = {v: k for k, v in CONTENT_TYPES.items()}.get(content_type, "bin")
    return (
        f"schools/{document.school_id}/assessments/{document.assessment_id}"
        f"/{document.kind}/{document.id}/{index:03d}.{suffix}"
    )


def _forget_pages(document: ScanDocument) -> None:
    """Best effort, on purpose.

    A page left in the store after its row is gone costs storage. An upload that fails
    because a delete failed costs a teacher their work, so the delete never gets to break
    the request that supersedes it.
    """
    store = get_object_store()
    for page in document.pages:
        if page.storage_key:
            try:
                store.delete(page.storage_key)
            except Exception:  # noqa: BLE001 - an orphan is safer than a failed upload
                continue


def _read_bytes(page: ScanPage) -> bytes:
    """The page, from wherever it was written.

    Two places, because pages written before the move to the object store are still in the
    database and rewriting a school's scripts to relocate them is a worse risk than
    reading both.

    A row that points at bytes which are not there is answered with 410 and a sentence
    saying so. It happens for one real reason -- a deployment whose object store does not
    survive a restart, which is what a free tier gives you -- and a 500 would send somebody
    hunting a bug in the reader instead of reading the sentence.
    """
    if page.storage_key:
        try:
            with get_object_store().open(page.storage_key) as handle:
                return handle.read()
        except Exception as exc:  # noqa: BLE001 - every store raises its own kind
            raise HTTPException(
                410,
                "this page is recorded but its image is no longer in storage. On a "
                "deployment without durable storage the pages do not survive a restart; "
                "the marks and the report are unaffected.",
            ) from exc
    if page.content:
        return page.content
    raise HTTPException(410, "this page is recorded but no image was ever stored for it.")


def _view(document: ScanDocument) -> dict:
    return {
        "document_id": document.id,
        "kind": document.kind,
        "assessment_id": document.assessment_id,
        "student_id": document.student_id,
        "page_count": document.page_count,
        "sha256": document.sha256,
        "uploaded_by": document.uploaded_by,
        "uploaded_at": document.created_at.isoformat() if document.created_at else None,
        "confirmed_at": document.confirmed_at.isoformat() if document.confirmed_at else None,
        "confirmed_by": document.confirmed_by,
        #: Every page addressable on its own, so a viewer can page through a script.
        "pages": [
            {
                "index": p.index,
                "content_type": p.content_type,
                "byte_size": p.byte_size,
                "quality": p.quality,
                "url": f"/documents/{document.id}/pages/{p.index}",
            }
            for p in document.pages
        ],
    }


@router.post("/assessments/{assessment_id}/answers/{student_id}/pages")
async def upload_answer_sheet(
    assessment_id: str,
    student_id: str,
    files: list[UploadFile] = File(...),
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    """One student's answer script, in the order the pages are sent.

    Stored against the paper as well as the student, because a script with no paper is a
    stack of photographs nobody can mark, and marks with no script are a claim nobody can
    check.
    """
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != school.id:
        raise HTTPException(404, "not found")
    student = db.get(StudentProfile, student_id)
    if student is None or student.school_id != school.id:
        raise HTTPException(404, "not found")
    if not files:
        raise HTTPException(422, "no pages were sent")

    pages: list[tuple[bytes, str, dict | None]] = []
    for upload in files:
        content = await upload.read()
        if not content:
            raise HTTPException(422, f"{upload.filename or 'a page'} is empty")
        if len(content) > MAX_PAGE_BYTES:
            raise HTTPException(
                413, f"{upload.filename or 'a page'} is larger than "
                     f"{MAX_PAGE_BYTES // 1024 // 1024} MB"
            )
        pages.append((content, content_type_for(upload.filename, upload.content_type), None))

    document = store_document(
        db, school_id=school.id, assessment_id=assessment.id, student_id=student.id,
        kind="answer_sheet", pages=pages,
    )
    db.commit()
    db.refresh(document)
    return _view(document)


@router.post("/documents/{document_id}/confirm")
def confirm_document(
    document_id: str,
    body: dict | None = None,
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    """A person says these are the right pages, in the right order.

    Kept separate from the upload: pages arriving is a fact about the network, and pages
    being correct is a judgement somebody has to make and be named for.
    """
    document = db.get(ScanDocument, document_id)
    if document is None or document.school_id != school.id:
        raise HTTPException(404, "not found")
    document.confirmed_at = datetime.now(UTC)
    document.confirmed_by = str((body or {}).get("by", ""))[:120] or None
    db.commit()
    db.refresh(document)
    return _view(document)


@router.get("/assessments/{assessment_id}/documents")
def list_documents(
    assessment_id: str,
    student_id: str | None = None,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != school.id:
        raise HTTPException(404, "not found")
    query = select(ScanDocument).where(ScanDocument.assessment_id == assessment.id)
    if student_id:
        query = query.where(ScanDocument.student_id == student_id)
    return {"documents": [_view(d) for d in db.scalars(query)]}


@router.get("/students/{student_id}/documents")
def list_student_documents(
    student_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """Every script this student has, newest first. What the student record shows."""
    student = db.get(StudentProfile, student_id)
    if student is None or student.school_id != school.id:
        raise HTTPException(404, "not found")
    documents = db.scalars(
        select(ScanDocument)
        .where(ScanDocument.student_id == student_id)
        .order_by(ScanDocument.created_at.desc())
    ).all()
    titles = {
        a.id: a.title for a in db.scalars(
            select(Assessment).where(
                Assessment.id.in_([d.assessment_id for d in documents] or [""])
            )
        )
    }
    return {
        "documents": [
            {**_view(d), "assessment_title": titles.get(d.assessment_id)} for d in documents
        ]
    }


@router.get("/documents/{document_id}/pages/{index}")
def read_page(
    document_id: str,
    index: int,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> Response:
    """One page, as it was scanned.

    Tenancy is checked on the document, not the page: a page id that leaked would
    otherwise be a way to read another school's script.
    """
    document = db.get(ScanDocument, document_id)
    if document is None or document.school_id != school.id:
        raise HTTPException(404, "not found")
    page = db.scalar(
        select(ScanPage).where(ScanPage.document_id == document.id, ScanPage.index == index)
    )
    if page is None:
        raise HTTPException(404, "no such page")
    return Response(
        content=_read_bytes(page),
        media_type=page.content_type,
        headers={
            # Immutable: replacing a page writes a new document, so a cached page can
            # never be a stale version of a different one.
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="page-{index + 1}"',
        },
    )
