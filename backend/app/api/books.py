"""Loading a subject's book through the browser.

Same extraction, same verification, same refusal to write a chapter that disagrees with
the contents page as `scripts.ingest_book` -- this is a second entry point to one pipeline,
not a second pipeline. It exists because a deployment without shell access still has to be
able to load a book, and the alternative was asking a school to run Python.

Order is enforced: the contents page first, because it is the oracle every chapter is
checked against, and a chapter accepted without it would be accepted on trust.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_admin
from app.config import get_settings
from app.curriculum import CURRICULA, chapter_title
from app.curriculum.apply import apply as apply_curriculum
from app.db import get_session
from app.ingest.book import (
    Section,
    chapter_number,
    extract_chapter,
    parse_toc,
    stem_hash,
    verify_against_toc,
)
from app.ingest.embed import classify_familiarity
from app.ingest.probe import LexicalIndex, SemanticIndex
from app.models import (
    BookChunk,
    BookSource,
    CanonicalProcedure,
    ChapterBoardUnit,
    TaxonomyNode,
)

router = APIRouter(
    prefix="/platform/books", tags=["knowledge-base"],
    dependencies=[Depends(require_platform_admin)],
)

#: NCERT chapter PDFs run to about 3 MB; well above that is not a chapter
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


async def _to_tempfile(upload: UploadFile) -> Path:
    if not (upload.filename or "").lower().endswith(".pdf"):
        raise HTTPException(422, "expected a PDF")
    data = await upload.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"file is larger than {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
    if not data:
        raise HTTPException(422, "the file is empty")
    handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    handle.write(data)
    handle.close()
    return Path(handle.name)


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
    if source is None:
        return {
            "subject": subject,
            "curriculum_ready": subject_ready,
            "contents_uploaded": False,
            "expected_chapters": 0, "loaded_chapters": 0,
            "chunks": chunks or 0, "embedded": embedded or 0,
            "embeddings_configured": bool(settings.jina_api_key),
            "next": (
                "Set up the curriculum first -- board units and their weightage come from "
                "the syllabus, not the book." if not subject_ready else
                "Upload the contents page (00-contents.pdf) first -- every chapter is "
                "checked against it."
            ),
        }

    expected = {int(k) for k in source.expected_sections}
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
        "files": source.files,
        "next": (
            f"Upload chapters {missing}" if missing
            else "All chapters loaded -- embed them so familiarity stops collapsing to "
                 "exact match." if (chunks or 0) > (embedded or 0)
            else "Loaded and embedded."
        ),
    }


@router.post("/{subject}/contents", status_code=status.HTTP_201_CREATED)
async def upload_contents(
    subject: str,
    file: UploadFile = File(...),
    edition: str | None = None,
    db: Session = Depends(get_session),
) -> dict:
    """The prelims file. Parsed for its table of contents, which becomes the oracle."""
    version = "CBSE-2026-27"
    if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == subject)) is None:
        raise HTTPException(
            422,
            f"subject {subject!r} is not in the taxonomy yet. Set up the curriculum first "
            f"-- the board units a chapter's marks count towards come from the syllabus, "
            f"not from the book.",
        )

    path = await _to_tempfile(file)
    try:
        toc = parse_toc(path)
    finally:
        path.unlink(missing_ok=True)

    if not toc:
        raise HTTPException(
            422,
            "no table of contents found. This should be the prelims file -- NCERT names it "
            "jemh1ps.pdf for Maths -- not a chapter.",
        )

    expected = {
        str(chapter): [{"number": s.number, "title": s.title} for s in sections]
        for chapter, sections in toc.items()
    }
    source = _source(db, subject, version)
    if source is None:
        source = BookSource(
            curriculum_version=version, subject_code=subject,
            edition=edition, expected_sections=expected, files={},
        )
        db.add(source)
    else:
        # re-uploading the contents page replaces the oracle but keeps what is loaded
        source.expected_sections = expected
        if edition:
            source.edition = edition
    db.commit()

    return {
        "subject": subject,
        "chapters_expected": len(expected),
        "sections_expected": sum(len(v) for v in expected.values()),
        "next": f"Upload the {len(expected)} chapter files.",
    }


@router.post("/{subject}/chapters", status_code=status.HTTP_201_CREATED)
async def upload_chapter(
    subject: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
) -> dict:
    """One chapter PDF, verified against the contents page before anything is written."""
    version = "CBSE-2026-27"
    source = _source(db, subject, version)
    if source is None:
        raise HTTPException(
            409,
            "upload the contents page first -- it is what makes a chapter checkable rather "
            "than merely plausible",
        )

    name = file.filename or ""
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

    path = await _to_tempfile(file)
    try:
        # An NCERT-coded filename carries no title, so take it from the curriculum, which
        # is the authority for chapter identity anyway -- it holds the board-unit mapping.
        extract = extract_chapter(
            path, number=number, name=name,
            title=chapter_title(subject, number) or "",
        )
        toc = {
            int(k): [Section(s["number"], s["title"]) for s in v]
            for k, v in source.expected_sections.items()
        }
        verify_against_toc(extract, toc)
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
        "sections": len(extract.sections), **written,
    }


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

    written = {"chunks": 0, "procedures": 0}
    for chunk in extract.chunks:
        if db.scalar(
            select(BookChunk).where(
                BookChunk.stem_hash == chunk.stem_hash,
                BookChunk.curriculum_version == version,
            )
        ) is None:
            db.add(BookChunk(
                curriculum_version=version, subject_code=subject, node_id=chapter.id,
                bucket=chunk.bucket, reference=chunk.reference,
                text=chunk.text, normalised=chunk.text, stem_hash=chunk.stem_hash,
            ))
            written["chunks"] += 1
        if chunk.kind in ("theorem", "example") and db.scalar(
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

    if embedded and settings.jina_api_key:
        from app.ingest.jina import JinaEmbedder

        index: SemanticIndex | LexicalIndex = SemanticIndex(
            chunks,
            JinaEmbedder(
                settings.jina_api_key, model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
            ),
        )
        mode = "semantic"
    else:
        index = LexicalIndex(chunks)
        mode = "lexical"

    rows = []
    hits = 0
    for question in body.questions:
        found = index.search(question.stem, k=3)
        top = found[0] if found else None
        retrieved = labels.get(top.node_id, "?") if top else None

        verbatim = db.scalar(
            select(CanonicalProcedure).where(
                CanonicalProcedure.stem_hash == stem_hash(question.stem)
            )
        )
        if verbatim:
            familiarity, similarity, why = "T_VERBATIM", 1.0, "exact match"
        elif mode == "semantic" and top:
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
            "runners_up": [
                {"reference": c.reference, "chapter": labels.get(c.node_id, "?"),
                 "similarity": round(c.score, 3)}
                for c in found[1:]
            ],
        })

    graded = sum(1 for r in rows if r["hit"] is not None)
    return {
        "mode": mode,
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
