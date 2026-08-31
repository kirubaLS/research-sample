"""Use case 2 routes: assessment ingest, the Q-matrix, marks, and reconciliation."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.api.schemas import (
    AssessmentIn,
    MarkBatchIn,
    QuestionBatchIn,
    ReconcileIn,
)
from app.api.upload import to_tempfile
from app.db import get_session
from app.extraction.address import Address, AddressResolver
from app.extraction.choice import group_choices
from app.extraction.verification import verify_paper
from app.ingest.book import stem_hash
from app.mapping.solver import Constraint, QuestionDist, solve
from app.models import (
    Assessment,
    BookChunk,
    ChapterBoardUnit,
    ConceptFamilyProposal,
    DataQualityFlag,
    MarkEvent,
    Question,
    QuestionPlacement,
    QuestionSkill,
    ScannedQuestion,
    School,
    StudentProfile,
    TaxonomyNode,
)
from app.taxonomy.variants import ServedVariant, VariantReuseError, enforce, variant_hash

router = APIRouter(prefix="/assessments", tags=["marks-engine"])


def _get_assessment(db: Session, school: School, assessment_id: str) -> Assessment:
    a = db.get(Assessment, assessment_id)
    if a is None or a.school_id != school.id:
        raise HTTPException(404, "not found")   # never confirm another school's data exists
    return a


@router.post("")
def create_assessment(
    body: AssessmentIn, school: School = Depends(require_admin), db: Session = Depends(get_session)
) -> dict:
    a = Assessment(
        school_id=school.id, subject_code=body.subject_code, title=body.title,
        paper_code=body.paper_code, total_marks=body.total_marks,
        curriculum_version=body.curriculum_version, declared=body.declared,
    )
    db.add(a)
    db.flush()
    return {"assessment_id": a.id, "status": a.status}


@router.post("/{assessment_id}/questions")
def add_questions(
    assessment_id: str,
    body: QuestionBatchIn,
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    a = _get_assessment(db, school, assessment_id)
    if a.qmatrix_frozen_at:
        raise HTTPException(409, "Q-matrix is frozen; create a new version to change it")

    def node_id(code: str, kind: str) -> str:
        node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
        if node is None:
            raise HTTPException(422, f"unknown {kind}: {code!r}")
        return node.id

    # The variant guard, before anything is written. Reusing a variant does not error on
    # its own -- the class simply scores better next time, and the improvement is
    # indistinguishable from learning by the time it reaches a report.
    served = [
        ServedVariant(
            family_id=row.concept_family_id, variant_hash=row.variant_hash,
            assessment_id=row.assessment_id, assessment_title=title,
            question_no=row.question_no,
        )
        for row, title in db.execute(
            select(Question, Assessment.title)
            .join(Assessment, Assessment.id == Question.assessment_id)
            .where(Assessment.school_id == school.id, Assessment.id != a.id)
        ).all()
    ]
    incoming = [
        (q.question_no, node_id(q.concept_family, "concept family"), variant_hash(q.concept_variant))
        for q in body.questions
    ]
    try:
        enforce(incoming, served)
    except VariantReuseError as exc:
        raise HTTPException(409, str(exc)) from exc

    rows: list[tuple[Address, float]] = []
    created = 0
    for q in body.questions:
        addr = Address(q.section, q.question_no, q.sub_part, q.choice_alt)
        rows.append((addr, q.max_marks))
        existing = db.scalar(
            select(Question).where(
                Question.assessment_id == a.id, Question.address == addr.key
            )
        )
        if existing is None:
            row = Question(
                assessment_id=a.id, address=addr.key, section=q.section,
                question_no=q.question_no, sub_part=q.sub_part, choice_alt=q.choice_alt,
                max_marks=q.max_marks, mark_step=q.mark_step, question_type=q.question_type,
                stem_text=q.stem_text, logical_page=q.logical_page,
                board_unit_id=node_id(q.board_unit, "board unit"),
                concept_family_id=node_id(q.concept_family, "concept family"),
                concept_variant=q.concept_variant,
                variant_hash=variant_hash(q.concept_variant),
                chapter_id=node_id(q.chapter, "chapter") if q.chapter else None,
                curriculum_section=q.curriculum_section,
                curriculum_section_title=q.curriculum_section_title,
                verified_against=q.verified_against,
            )
            db.add(row)
            db.flush()
            created += 1
            for code in q.skills:
                node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
                if node is not None:
                    db.add(QuestionSkill(question_id=row.id, node_id=node.id, source="import"))

    mapping, groups = group_choices(rows)
    for key, gid in mapping.items():
        row = db.scalar(
            select(Question).where(Question.assessment_id == a.id, Question.address == key)
        )
        if row is not None:
            row.choice_group_id = gid
    db.flush()
    return {
        "created": created,
        "total_addresses": len(rows),
        "choice_groups": len(groups),
    }


@router.post("/{assessment_id}/verify")
def verify(
    assessment_id: str,
    section_arithmetic: dict[str, list[float]] | None = None,
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    """The four gates. A failure blocks the paper and names the equation that broke."""
    a = _get_assessment(db, school, assessment_id)
    questions = list(db.scalars(select(Question).where(Question.assessment_id == a.id)))
    rows = [
        (Address(q.section, q.question_no, q.sub_part, q.choice_alt), float(q.max_marks))
        for q in questions
    ]
    _, groups = group_choices(rows)
    arithmetic = (
        {k: (int(v[0]), float(v[1]), float(v[2])) for k, v in section_arithmetic.items()}
        if section_arithmetic
        else None
    )
    report = verify_paper(rows, groups, a.declared or {}, section_arithmetic=arithmetic)

    db.query(DataQualityFlag).filter(
        DataQualityFlag.assessment_id == a.id,
        DataQualityFlag.rule.like("G%"),
        DataQualityFlag.status == "open",
    ).delete(synchronize_session=False)
    for failure in report.failures:
        db.add(
            DataQualityFlag(
                assessment_id=a.id, rule=failure.gate, severity="blocking",
                detail=f"expected {failure.expected}, got {failure.actual}. {failure.detail}",
            )
        )
    a.status = "verified" if report.passed else "blocked"
    db.flush()
    return report.as_dict()


@router.post("/{assessment_id}/freeze")
def freeze(
    assessment_id: str, school: School = Depends(require_admin), db: Session = Depends(get_session)
) -> dict:
    a = _get_assessment(db, school, assessment_id)
    open_flags = list(
        db.scalars(
            select(DataQualityFlag).where(
                DataQualityFlag.assessment_id == a.id,
                DataQualityFlag.status == "open",
                DataQualityFlag.severity == "blocking",
            )
        )
    )
    if open_flags:
        raise HTTPException(409, f"{len(open_flags)} blocking flag(s) open; resolve before freezing")
    a.qmatrix_frozen_at = datetime.now(UTC).isoformat()
    a.qmatrix_version += 1
    a.status = "frozen"
    db.flush()
    return {"frozen_at": a.qmatrix_frozen_at, "version": a.qmatrix_version}


@router.post("/{assessment_id}/marks")
def post_marks(
    assessment_id: str,
    body: MarkBatchIn,
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    """Append-only. A correction is a new row; nothing is ever updated in place."""
    a = _get_assessment(db, school, assessment_id)
    questions = {
        q.address: q for q in db.scalars(select(Question).where(Question.assessment_id == a.id))
    }
    resolver = AddressResolver(list(questions))

    written, rejected = 0, []
    for m in body.marks:
        addr, reason = resolver.resolve(m.address, section_hint=body.section)
        if addr is None:
            rejected.append({"address": m.address, "reason": reason})
            continue
        q = questions[addr.key]
        student = db.scalar(
            select(StudentProfile).where(
                StudentProfile.school_id == school.id, StudentProfile.roll_no == m.student_roll
            )
        )
        if student is None:
            rejected.append({"address": m.address, "reason": "unknown_student"})
            continue
        if m.state == "awarded" and (m.marks is None or m.marks < 0 or m.marks > float(q.max_marks)):
            rejected.append({"address": m.address, "reason": "out_of_range"})
            continue
        db.add(
            MarkEvent(
                assessment_id=a.id, student_id=student.id, question_id=q.id,
                state=m.state, marks=m.marks, source=m.source, confidence=m.confidence,
            )
        )
        written += 1
    db.flush()
    return {"written": written, "rejected": rejected}


@router.post("/{assessment_id}/reconcile")
def reconcile(
    assessment_id: str,
    body: ReconcileIn,
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    """Run the constraint solver over one student's per-question distributions."""
    a = _get_assessment(db, school, assessment_id)
    questions = {
        q.address: q for q in db.scalars(select(Question).where(Question.assessment_id == a.id))
    }

    dists: list[QuestionDist] = []
    index_by_address: dict[str, int] = {}
    for address, probs in body.distributions.items():
        q = questions.get(address)
        if q is None:
            raise HTTPException(422, f"unknown address {address}")
        index_by_address[address] = len(dists)
        dists.append(
            QuestionDist(
                question_id=address, max_marks=float(q.max_marks), step=float(q.mark_step),
                probs={float(k): float(v) for k, v in probs.items()},
            )
        )

    constraints: list[Constraint] = []
    for section, total in (body.section_totals or {}).items():
        idx = frozenset(
            i for addr, i in index_by_address.items() if questions[addr].section == section
        )
        if idx:
            constraints.append(Constraint(f"section_{section}", idx, total))
    if body.grand_total is not None:
        constraints.append(
            Constraint("grand_total", frozenset(range(len(dists))), body.grand_total)
        )

    result = solve(dists, constraints)
    return {
        "feasible": result.feasible,
        "assignment": result.assignment,
        "mean_logp": None if result.mean_logp == float("-inf") else round(result.mean_logp, 4),
        "failed_constraint": result.failed_constraint,
        "detail": result.detail,
    }


# --------------------------------------------------------------------------------------
# Scanning a question paper
# --------------------------------------------------------------------------------------
@router.post("/{assessment_id}/scan", status_code=status.HTTP_201_CREATED)
async def scan_paper(
    assessment_id: str,
    file: UploadFile = File(...),
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    """Read a question paper PDF into staged questions.

    Writes to scanned_question, not to question: a question row needs a board unit and a
    concept family, and neither is knowable from the paper. They come from the book, in
    the mapping step that follows.

    Re-scanning replaces the staged rows for questions that have not been promoted yet, so
    a paper can be re-read after a bad upload without unpicking what mapping already did.
    """
    from app.extraction.paper import extract_paper

    assessment = _get_assessment(db, school, assessment_id)
    if assessment.qmatrix_frozen_at:
        raise HTTPException(409, "the Q-matrix is frozen; create a new version to re-scan")

    path = await to_tempfile(file)
    try:
        extract = extract_paper(path)
        source_sha = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    finally:
        path.unlink(missing_ok=True)

    if extract.route == "vision":
        assessment.route = "vision"
        assessment.pdf_page_count = extract.page_count
        db.commit()
        raise HTTPException(
            422,
            "; ".join(extract.problems)
            + " Upload a PDF that carries a text layer, or wait for the vision route.",
        )

    promoted = {
        row.address
        for row in db.scalars(
            select(ScannedQuestion).where(ScannedQuestion.assessment_id == assessment.id)
        )
        if row.question_id
    }
    for row in db.scalars(
        select(ScannedQuestion).where(ScannedQuestion.assessment_id == assessment.id)
    ):
        if row.address not in promoted:
            db.delete(row)
    db.flush()

    written, kept = 0, 0
    for question in extract.questions:
        if question.address in promoted:
            kept += 1
            continue
        db.add(ScannedQuestion(
            assessment_id=assessment.id, address=question.address,
            section=question.section, question_no=question.question_no,
            sub_part=question.sub_part, choice_alt=question.choice_alt,
            max_marks=question.max_marks, stem_text=question.stem_text,
            logical_page=question.logical_page,
        ))
        written += 1

    assessment.route = "text"
    assessment.pdf_page_count = extract.page_count
    assessment.source_sha256 = source_sha
    assessment.declared = {
        **(assessment.declared or {}),
        "sections": extract.declared_sections or None,
        "question_count": extract.declared_count,
    }
    db.commit()

    primaries = [q for q in extract.questions if q.choice_alt is None]
    return {
        "assessment_id": assessment.id,
        "route": extract.route,
        "pages": extract.page_count,
        "questions": len(primaries),
        "choice_alternatives": len(extract.questions) - len(primaries),
        "total_marks": extract.total_marks,
        "staged": written,
        "already_promoted": kept,
        "declared": {
            "questions": extract.declared_count,
            "sections": extract.declared_sections or None,
        },
        #: Every disagreement between the extraction and what the paper says about itself.
        #: Empty means the two agree, which is the only evidence the read is right.
        "problems": extract.problems,
        "next": f"Review at GET /assessments/{assessment.id}/scan, then POST /map.",
    }


@router.get("/{assessment_id}/scan")
def read_scan(
    assessment_id: str,
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    """The staged questions, and what is stopping each one becoming a real question."""
    assessment = _get_assessment(db, school, assessment_id)
    rows = list(db.scalars(
        select(ScannedQuestion)
        .where(ScannedQuestion.assessment_id == assessment.id)
        .order_by(ScannedQuestion.section, ScannedQuestion.logical_page)
    ))
    questions = {q.id: q for q in db.scalars(
        select(Question).where(Question.assessment_id == assessment.id)
    )}
    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}

    def mapped(row: ScannedQuestion) -> dict | None:
        question = questions.get(row.question_id or "")
        if question is None:
            return None
        chapter = nodes.get(question.chapter_id or "")
        family = nodes.get(question.concept_family_id or "")
        unit = nodes.get(question.board_unit_id or "")
        return {
            "chapter": chapter.label if chapter else None,
            "curriculum_section": question.curriculum_section,
            "concept_family": family.label if family else None,
            "board_unit": unit.label if unit else None,
        }

    return {
        "assessment_id": assessment.id,
        "route": assessment.route,
        "staged": len(rows),
        "mapped": sum(1 for r in rows if r.question_id),
        "marks_missing": sum(1 for r in rows if r.max_marks is None),
        "questions": [
            {
                "address": r.address, "section": r.section, "question_no": r.question_no,
                "choice_alt": r.choice_alt,
                "max_marks": float(r.max_marks) if r.max_marks is not None else None,
                "stem_text": r.stem_text, "page": r.logical_page,
                "mapped_to": mapped(r),
                "blocked_reason": r.blocked_reason,
            }
            for r in rows
        ],
    }


def _chapter_of(node_id: str | None, nodes: dict[str, TaxonomyNode]) -> TaxonomyNode | None:
    """Walk up to the chapter. Retrieval lands on whichever node the winning chunk hangs
    off, which is a sub-topic as often as a chapter."""
    seen: set[str] = set()
    current = nodes.get(node_id or "")
    while current is not None and current.id not in seen:
        if current.kind == "chapter":
            return current
        seen.add(current.id)
        current = nodes.get(current.parent_id or "")
    return None


#: 'S13_2' -> section 13.2. Anchored and digits-only after the S, because chapter codes
#: begin with S too: X.MATH.SAV read as section "AV" and X.MATH.STATS as "TATS", which
#: then matched no concept family and blocked every question in those chapters.
_SECTION_CODE = re.compile(r"^S(\d+(?:_\d+)*)$")


def _section_number(code: str) -> str | None:
    """'X.MATH.STATS.S13_2' -> '13.2'. None when the code carries no section."""
    match = _SECTION_CODE.match(code.rsplit(".", 1)[-1])
    return match.group(1).replace("_", ".") if match else None


@router.post("/{assessment_id}/map")
def map_paper_to_book(
    assessment_id: str,
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    """Place every staged question against the book, and promote what can be placed.

    This is the join the whole product rests on: a mark is only diagnostic because the
    question it was scored on is known to belong to a chapter, a section and a concept
    family, and all three come from the book rather than from anyone's memory.

    A question that cannot be placed is left staged with the reason recorded. That is not
    a failure to hide -- an unplaceable question is a real fact about the paper or about
    how much of the curriculum has been reviewed, and forcing it into a chapter to keep
    the numbers tidy is exactly the invention this pipeline exists to refuse.
    """
    from app.config import get_settings
    from app.ingest.probe import LexicalIndex, SemanticIndex, locate

    assessment = _get_assessment(db, school, assessment_id)
    settings = get_settings()

    staged = [
        row for row in db.scalars(
            select(ScannedQuestion).where(ScannedQuestion.assessment_id == assessment.id)
        )
        if row.question_id is None
    ]
    if not staged:
        raise HTTPException(422, "nothing staged to map; scan the paper first")

    chunks = list(db.scalars(
        select(BookChunk).where(BookChunk.subject_code == assessment.subject_code)
    ))
    if not chunks:
        raise HTTPException(
            422,
            f"no book is loaded for {assessment.subject_code}, so there is nothing to map "
            f"against. Upload the chapters first.",
        )

    indexes: list = [LexicalIndex(chunks)]
    mode = "lexical"
    if any(c.embedding for c in chunks) and settings.jina_api_key:
        from app.ingest.jina import JinaEmbedder

        indexes.append(SemanticIndex(chunks, JinaEmbedder(
            settings.jina_api_key, model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )))
        mode = "hybrid"

    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
    units = {
        row.chapter_id: row.board_unit_id
        for row in db.scalars(select(ChapterBoardUnit).where(
            ChapterBoardUnit.curriculum_version == assessment.curriculum_version
        ))
    }
    families: dict[str, list[TaxonomyNode]] = {}
    for node in nodes.values():
        if node.kind == "concept_family" and node.parent_id:
            families.setdefault(node.parent_id, []).append(node)
    #: family code -> the sections the run said it draws on, so a family can be chosen by
    #: the section the book put the question in rather than by name similarity
    sections_of = {
        row.code: set(row.from_sections or [])
        for row in db.scalars(select(ConceptFamilyProposal).where(
            ConceptFamilyProposal.subject_code == assessment.subject_code
        ))
    }

    mapped, blocked = 0, []
    for row in staged:
        if not (row.stem_text or "").strip():
            row.blocked_reason = "no stem text was extracted, so there is nothing to place"
            blocked.append(row.address)
            continue
        if row.max_marks is None:
            row.blocked_reason = "no mark label was read; supply the marks before mapping"
            blocked.append(row.address)
            continue

        verdict = locate(row.stem_text, indexes)
        chapter = _chapter_of(verdict.node_id, nodes)
        if chapter is None:
            row.blocked_reason = "no chapter in the book matched this question"
            blocked.append(row.address)
            continue

        unit_id = units.get(chapter.id)
        if unit_id is None:
            row.blocked_reason = (
                f"{chapter.label} is not mapped to a board unit, so its marks have "
                f"nowhere to count"
            )
            blocked.append(row.address)
            continue

        landed = nodes.get(verdict.node_id or "")
        section = _section_number(landed.code) if landed else None

        candidates = families.get(chapter.id, [])
        if not candidates:
            row.blocked_reason = (
                f"no concept family has been applied for {chapter.label}. Review the "
                f"proposals for this subject and create the families first."
            )
            blocked.append(row.address)
            continue
        family = next(
            (f for f in candidates if section and section in sections_of.get(f.code, set())),
            candidates[0] if len(candidates) == 1 else None,
        )
        if family is None:
            row.blocked_reason = (
                f"{len(candidates)} families exist for {chapter.label} and none of them "
                f"claims section {section or '?'}; a person must choose"
            )
            blocked.append(row.address)
            continue

        question = Question(
            assessment_id=assessment.id, address=row.address, section=row.section,
            question_no=row.question_no, sub_part=row.sub_part, choice_alt=row.choice_alt,
            max_marks=row.max_marks, stem_text=row.stem_text,
            stem_hash=stem_hash(row.stem_text), logical_page=row.logical_page,
            board_unit_id=unit_id, chapter_id=chapter.id, curriculum_section=section,
            concept_family_id=family.id,
            concept_variant=row.stem_text[:200],
            variant_hash=variant_hash(row.stem_text[:200]),
            verified_against=f"retrieval:{mode}",
        )
        db.add(question)
        db.flush()
        db.add(QuestionPlacement(
            question_id=question.id, chapter_id=chapter.id, board_unit_id=unit_id,
            curriculum_section=section, confidence=verdict.score,
            source="model", needs_review=not verdict.agreed,
            reasoning=f"{mode} retrieval, margin {verdict.margin:.3f}",
            # The chunk references, not the Candidate objects: JSON has to hold what a
            # reviewer reads, and the objects are not serialisable anyway.
            evidence=[c.reference for c in verdict.evidence if c.reference][:6],
            candidates=[
                nodes[n].label for n, _ in verdict.runners_up if n in nodes
            ][:4],
        ))
        row.question_id = question.id
        row.blocked_reason = None
        mapped += 1

    db.commit()
    return {
        "assessment_id": assessment.id,
        "retrieval": mode,
        "mapped": mapped,
        "blocked": len(blocked),
        "blocked_addresses": blocked[:20],
        "needs_review": db.scalar(select(func.count(QuestionPlacement.id)).where(
            QuestionPlacement.needs_review.is_(True),
            QuestionPlacement.question_id.in_(
                select(Question.id).where(Question.assessment_id == assessment.id)
            ),
        )) or 0,
        "next": f"Review at GET /assessments/{assessment.id}/scan.",
    }
