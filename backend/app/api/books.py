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
import uuid
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
    parse_toc_chapters,
    stem_hash,
    title_key,
    verify_against_toc,
    verify_structure,
)
from app.ingest.embed import classify_familiarity
from app.ingest.probe import LexicalIndex, SemanticIndex, locate
from app.models import (
    BookChunk,
    BookSource,
    CanonicalProcedure,
    ChapterBoardUnit,
    ConceptFamilyProposal,
    TaxonomyNode,
)

router = APIRouter(
    prefix="/platform/books", tags=["knowledge-base"],
    dependencies=[Depends(require_platform_admin)],
)

#: NCERT chapter PDFs run to about 3 MB; well above that is not a chapter
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

#: Below this gap to the runner-up, the top chapter won by a hair. On the 30(B) set the
#: single wrong answer had the smallest margin of any row, so this is where a question
#: should go to a human rather than into a report.
MIN_MARGIN = 0.002


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
        chapters = parse_toc_chapters(path)
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
            node.label,
            counts.get(node.parent_id, 0),
        )
        for node in nodes.values()
        if node.kind == "subtopic" and node.parent_id in chapters
    ]
    rows.sort(key=lambda r: (r[0], r[2]))

    existing = {n.code for n in nodes.values() if n.kind == "concept_family"}
    proposals = [
        {
            "code": p.code, "label": p.label,
            "chapter_code": p.chapter_code, "chapter_label": p.chapter_label,
            "from_section": p.from_section, "chunks": p.chunks,
            "already_exists": p.code in existing,
        }
        for p in propose(rows, subject)
    ]
    return {
        "subject": subject,
        "existing": len(existing),
        "proposed": len(proposals),
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
    """Create the reviewed families. Additive only: an existing one is never renamed."""
    nodes = {n.code: n for n in db.scalars(select(TaxonomyNode))}
    created, skipped, unknown = 0, 0, []

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
        created += 1
    db.commit()

    return {
        "created": created,
        "already_existed": skipped,
        "unknown_chapters": sorted(set(unknown)),
        "note": "Existing families are left alone; a rename would break past comparisons.",
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
    for chapter in chapters:
        passages = _chapter_passages(db, subject, chapter.id)
        if not passages:
            skipped.append(f"{chapter.label}: no chunks loaded")
            continue
        seen: set[str] = set()
        for family in proposer.propose(chapter.label, passages):
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
        "chapters_read": len(chapters) - len(skipped),
        "proposed": written,
        "skipped": skipped,
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
            if written == 0 and proposer.violations
            else None
        ),
        "next": (
            f"Review at GET /platform/books/{subject}/concept-families/proposals, then "
            f"POST the ones you want to /platform/books/{subject}/concept-families."
            if written
            else "Nothing was stored, so there is nothing to review."
        ),
    }
