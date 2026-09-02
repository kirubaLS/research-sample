"""Use case 2 routes: assessment ingest, the Q-matrix, marks, and reconciliation."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_reader, require_scanner
from app.api.documents import content_type_for, store_document
from app.api.schemas import (
    AssessmentIn,
    MarkBatchIn,
    QuestionBatchIn,
    ReconcileIn,
)
from app.api.upload import pages_to_pdf
from app.db import get_session
from app.extraction.address import Address, AddressResolver
from app.extraction.choice import group_choices
from app.extraction.verification import verify_paper
from app.ingest.book import stem_hash
from app.mapping.solver import Constraint, QuestionDist, solve
from app.models.assessment import TIER_ALIASES
from app.models import (
    MARK_STATES,
    SOURCE_PRECEDENCE,
    Assessment,
    BookChunk,
    ChapterBoardUnit,
    ConceptFamilyProposal,
    DataQualityFlag,
    MarkEvent,
    Question,
    QuestionPlacement,
    QuestionSkill,
    QuestionTier,
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
    body: AssessmentIn, school: School = Depends(require_scanner), db: Session = Depends(get_session)
) -> dict:
    a = Assessment(
        school_id=school.id, subject_code=body.subject_code, title=body.title,
        paper_code=body.paper_code, total_marks=body.total_marks,
        curriculum_version=body.curriculum_version, declared=body.declared,
    )
    db.add(a)
    db.flush()
    return {"assessment_id": a.id, "status": a.status}


@router.get("")
def list_assessments(
    school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> dict:
    """Every paper this school has, and how far each one has got.

    The stage is derived from what is actually stored rather than from a status column
    somebody has to remember to update: a paper is mapped when its questions carry
    chapters, confirmed when the extraction has been signed off, scanned when pages were
    read, and otherwise empty. Only a mapped paper can take an answer sheet, and the list
    says so instead of letting someone find out at the point of entry.
    """
    assessments = list(db.scalars(
        select(Assessment)
        .where(Assessment.school_id == school.id)
        .order_by(Assessment.created_at.desc())
    ))
    ids = [a.id for a in assessments]

    scanned = dict(db.execute(
        select(ScannedQuestion.assessment_id, func.count())
        .where(ScannedQuestion.assessment_id.in_(ids))
        .group_by(ScannedQuestion.assessment_id)
    ).all()) if ids else {}
    questions = dict(db.execute(
        select(Question.assessment_id, func.count())
        .where(Question.assessment_id.in_(ids))
        .group_by(Question.assessment_id)
    ).all()) if ids else {}
    mapped = dict(db.execute(
        select(Question.assessment_id, func.count())
        .where(Question.assessment_id.in_(ids), Question.chapter_id.is_not(None))
        .group_by(Question.assessment_id)
    ).all()) if ids else {}
    marked = dict(db.execute(
        select(MarkEvent.assessment_id, func.count(func.distinct(MarkEvent.student_id)))
        .where(MarkEvent.assessment_id.in_(ids))
        .group_by(MarkEvent.assessment_id)
    ).all()) if ids else {}

    rows = []
    for a in assessments:
        n_questions = questions.get(a.id, 0)
        n_mapped = mapped.get(a.id, 0)
        if n_mapped:
            stage = "mapped"
        elif n_questions:
            stage = "confirmed"
        elif scanned.get(a.id):
            stage = "scanned"
        else:
            stage = "empty"
        rows.append({
            "id": a.id,
            "title": a.title,
            "subject_code": a.subject_code,
            "paper_code": a.paper_code,
            "total_marks": float(a.total_marks) if a.total_marks else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "stage": stage,
            "scanned_questions": scanned.get(a.id, 0),
            "questions": n_questions,
            "mapped_questions": n_mapped,
            "students_with_marks": marked.get(a.id, 0),
            #: What the answer-sheet screen needs to know before it offers this paper.
            "ready_for_answer_sheets": n_questions > 0,
        })
    return {"assessments": rows}


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
    files: list[UploadFile] = File(...),
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """Read a question paper PDF into staged questions.

    Writes to scanned_question, not to question: a question row needs a board unit and a
    concept family, and neither is knowable from the paper. They come from the book, in
    the mapping step that follows.

    Re-scanning replaces the staged rows for questions that have not been promoted yet, so
    a paper can be re-read after a bad upload without unpicking what mapping already did.
    """
    from app.extraction.paper import context_addresses, extract_paper

    assessment = _get_assessment(db, school, assessment_id)
    if assessment.qmatrix_frozen_at:
        raise HTTPException(409, "the Q-matrix is frozen; create a new version to re-scan")

    # One page or twenty, PDFs or photographs, in the order the caller sent them.
    #: Read once, before pages_to_pdf consumes the uploads, because the pages are kept:
    #: a report is a claim about a piece of paper, and the paper has to survive the read.
    originals = [
        (await f.read(), content_type_for(f.filename, f.content_type), f.filename)
        for f in files
    ]
    for upload, (content, _, _) in zip(files, originals, strict=True):
        await upload.seek(0)
        if not content:
            raise HTTPException(422, f"{upload.filename or 'a file'} is empty")

    path = await pages_to_pdf(files)
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

    # A new read of the paper invalidates the old signature: whoever confirmed did not see
    # these rows.
    assessment.scan_confirmed_at = None
    assessment.scan_confirmed_by = None
    assessment.route = "text"
    assessment.pdf_page_count = extract.page_count
    assessment.source_sha256 = source_sha
    assessment.declared = {
        **(assessment.declared or {}),
        "sections": extract.declared_sections or None,
        "question_count": extract.declared_count,
        #: what the cover says the paper is worth. Kept so the confirm step can hold the
        #: reading to it long after this response has scrolled away.
        "total_marks": extract.declared_total,
    }

    # The paper itself, kept exactly as it arrived. Storing only what we read off it left
    # every later question -- "is that really what question 14 said?" -- unanswerable.
    store_document(
        db, school_id=school.id, assessment_id=assessment.id, kind="question_paper",
        pages=[(content, content_type, None) for content, content_type, _ in originals],
    )
    db.commit()

    context = context_addresses(extract.questions)
    return {
        "assessment_id": assessment.id,
        "route": extract.route,
        "pages": extract.page_count,
        #: a question is a number on the paper, counted once however many halves and
        #: sub-parts it prints as
        "questions": len({q.question_no for q in extract.questions}),
        "sub_parts": sum(1 for q in extract.questions if q.sub_part),
        "choice_alternatives": sum(1 for q in extract.questions if q.choice_alt == "b"),
        "context_stems": len(context),
        "total_marks": extract.total_marks,
        "staged": written,
        "already_promoted": kept,
        "declared": {
            "questions": extract.declared_count,
            "sections": extract.declared_sections or None,
            "total_marks": extract.declared_total,
        },
        #: Every disagreement between the extraction and what the paper says about itself.
        #: Empty means the two agree, which is the only evidence the read is right.
        "problems": extract.problems,
        "next": f"Review at GET /assessments/{assessment.id}/scan, then POST /map.",
    }


@router.get("/{assessment_id}/scan")
def read_scan(
    assessment_id: str,
    school: School = Depends(require_reader),
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

    skills: dict[str, list[str]] = {}
    for link in db.scalars(select(QuestionSkill).where(
        QuestionSkill.question_id.in_([r.question_id for r in rows if r.question_id] or [""])
    )):
        node = nodes.get(link.node_id)
        if node is not None:
            skills.setdefault(link.question_id, []).append(node.label)
    tiers: dict[str, str] = {}
    for row_tier in db.scalars(select(QuestionTier).where(
        QuestionTier.question_id.in_([r.question_id for r in rows if r.question_id] or [""])
    )):
        if row_tier.tier:
            tiers[row_tier.question_id] = row_tier.tier

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
            #: the book's own heading for that section -- the topic, in its words
            "topic": (skills.get(question.id) or [None])[0],
            "concept_family": family.label if family else None,
            "board_unit": unit.label if unit else None,
            #: R&U, AP or AEC. Null until the classifier has read the question: which
            #: cognitive tier a question sits in is not visible in its address or its
            #: marks, and a tier nobody worked out must not read as one that was.
            "tier": tiers.get(question.id),
            "tier_label": TIER_ALIASES.get(tiers.get(question.id) or ""),
        }

    from app.extraction.paper import context_addresses

    context = context_addresses(rows)
    read_total = float(sum(
        r.max_marks or 0 for r in rows
        if r.choice_alt in (None, "a") and r.address not in context
    ))
    declared_total = (assessment.declared or {}).get("total_marks")
    if declared_total is None and assessment.total_marks is not None:
        declared_total = float(assessment.total_marks)

    return {
        "assessment_id": assessment.id,
        "route": assessment.route,
        "staged": len(rows),
        "confirmed_at": assessment.scan_confirmed_at,
        "confirmed_by": assessment.scan_confirmed_by,
        "edited": sum(1 for r in rows if r.edited_at),
        "mapped": sum(1 for r in rows if r.question_id),
        "marks_missing": sum(
            1 for r in rows if r.max_marks is None and r.address not in context
        ),
        #: The reading against what the paper says it is worth. A sub-part whose label was
        #: missed costs marks that nothing else notices, because every row that was read
        #: looks perfectly fine on its own.
        "marks": {
            "read": read_total,
            "declared": float(declared_total) if declared_total is not None else None,
            "short_by": (
                round(float(declared_total) - read_total, 2)
                if declared_total is not None else None
            ),
        },
        "questions": [
            {
                "address": r.address, "section": r.section, "question_no": r.question_no,
                "sub_part": r.sub_part,
                "choice_alt": r.choice_alt,
                "max_marks": float(r.max_marks) if r.max_marks is not None else None,
                "is_context": r.address in context,
                "stem_text": r.stem_text, "page": r.logical_page,
                "edited_by": r.edited_by,
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


class ScanEditIn(BaseModel):
    """What a person may change about a staged question. Everything is optional."""

    question_no: str | None = Field(default=None, max_length=12)
    section: str | None = Field(default=None, max_length=8)
    max_marks: float | None = Field(default=None, ge=0, le=100)
    stem_text: str | None = Field(default=None, max_length=4000)
    #: A row the extractor invented -- a heading read as a question, a duplicate. Removing
    #: it is an edit like any other, and more common than any field change.
    remove: bool = False
    by: str = Field(default="teacher", max_length=64)


@router.patch("/{assessment_id}/scan/{address:path}")
def edit_scanned_question(
    assessment_id: str,
    address: str,
    body: ScanEditIn,
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """Correct what the extractor read, before it becomes fact.

    Refused once the extraction has been confirmed: confirmation is a person putting their
    name to these rows, and silently editing them afterwards would leave the record saying
    someone checked something they never saw. Re-open by scanning again.
    """
    assessment = _get_assessment(db, school, assessment_id)
    if assessment.scan_confirmed_at:
        raise HTTPException(
            409,
            "this extraction was already confirmed; re-scan the paper to change it",
        )

    row = db.scalar(
        select(ScannedQuestion).where(
            ScannedQuestion.assessment_id == assessment.id,
            ScannedQuestion.address == address,
        )
    )
    if row is None:
        raise HTTPException(404, f"no staged question at {address!r}")
    if row.question_id:
        raise HTTPException(409, "this question has already been mapped; re-scan to change it")

    now = datetime.now(UTC).isoformat()
    if body.remove:
        db.delete(row)
        db.commit()
        return {"address": address, "removed": True}

    changed: list[str] = []
    for field_name in ("question_no", "section", "max_marks", "stem_text"):
        value = getattr(body, field_name)
        if value is None:
            continue
        if getattr(row, field_name) != value:
            setattr(row, field_name, value)
            changed.append(field_name)

    if "question_no" in changed or "section" in changed:
        # The address is derived from these, so it has to move with them or the row would
        # answer to a name that no longer describes it.
        row.address = "/".join([
            row.section or "", row.question_no, row.sub_part or "", row.choice_alt or ""
        ])

    if changed:
        row.edited_at, row.edited_by = now, body.by
        row.blocked_reason = None
    db.commit()
    return {"address": row.address, "changed": changed, "edited_by": row.edited_by}


class ConfirmIn(BaseModel):
    by: str = Field(default="teacher", max_length=64)


@router.post("/{assessment_id}/scan/confirm")
def confirm_scan(
    assessment_id: str,
    body: ConfirmIn,
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """A person states that these questions are what the paper says.

    Refused while any question still lacks a mark, because a question worth nothing is
    not a question anyone read -- it is a gap, and confirming around it would put a
    signature on something incomplete.

    Refused too while the marks read do not add up to what the paper says it is worth.
    Every row can look right and the paper still be short: a sub-part whose label was
    missed takes its marks with it and leaves nothing behind to notice. The total is the
    only place that shows.
    """
    assessment = _get_assessment(db, school, assessment_id)
    rows = list(db.scalars(
        select(ScannedQuestion).where(ScannedQuestion.assessment_id == assessment.id)
    ))
    if not rows:
        raise HTTPException(422, "nothing has been scanned for this assessment")

    from app.extraction.paper import context_addresses

    # A case study's opening paragraph is the stem its sub-parts share. It is worth
    # nothing on its own and is not a gap.
    context = context_addresses(rows)
    missing = [
        r.address for r in rows if r.max_marks is None and r.address not in context
    ]
    if missing:
        raise HTTPException(
            422,
            f"{len(missing)} question(s) still carry no marks: {', '.join(missing[:8])}"
            + (" ..." if len(missing) > 8 else "")
            + ". Set them, or remove the rows that are not questions.",
        )

    read_total = float(sum(
        r.max_marks or 0 for r in rows
        if r.choice_alt in (None, "a") and r.address not in context
    ))
    declared_total = (assessment.declared or {}).get("total_marks")
    if declared_total is None and assessment.total_marks is not None:
        declared_total = float(assessment.total_marks)
    if declared_total is not None and abs(float(declared_total) - read_total) > 0.01:
        short = float(declared_total) - read_total
        raise HTTPException(
            422,
            f"the paper is worth {float(declared_total):g} marks and the questions here "
            f"add up to {read_total:g}"
            + (
                f", so {short:g} are missing. A question whose sub-parts are worth "
                "different marks is the usual cause: open the ones with parts (i), (ii), "
                "(iii) and check that each part carries its own marks."
                if short > 0 else
                f", so {-short:g} are counted twice. A question with an internal choice "
                "is the usual cause: only one half of a choice counts."
            ),
        )

    assessment.scan_confirmed_at = datetime.now(UTC).isoformat()
    assessment.scan_confirmed_by = body.by
    db.commit()
    return {
        "assessment_id": assessment.id,
        "confirmed_at": assessment.scan_confirmed_at,
        "confirmed_by": assessment.scan_confirmed_by,
        "questions": len(rows),
        "edited": sum(1 for r in rows if r.edited_at),
        "total_marks": read_total,
        "next": f"POST /assessments/{assessment.id}/map",
    }


@router.post("/{assessment_id}/map")
def map_paper_to_book(
    assessment_id: str,
    school: School = Depends(require_scanner),
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
    from app.api.books import clean_sections
    from app.config import get_settings
    from app.extraction.paper import context_addresses
    from app.ingest.probe import LexicalIndex, SemanticIndex, locate

    assessment = _get_assessment(db, school, assessment_id)
    settings = get_settings()

    if not assessment.scan_confirmed_at:
        raise HTTPException(
            409,
            "nobody has confirmed this extraction yet. Everything after this treats the "
            "questions as what the paper says, so a person checks them first: "
            f"POST /assessments/{assessment.id}/scan/confirm",
        )

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
    #: (chapter id, section number) -> the book's own heading for that section. This is
    #: the topic, and it is the book's words rather than anybody's summary of them.
    topics: dict[tuple[str, str], TaxonomyNode] = {}
    for node in nodes.values():
        if node.kind != "subtopic" or not node.parent_id:
            continue
        tail = node.code.rsplit(".", 1)[-1]
        if tail.startswith("S"):
            topics[(node.parent_id, tail[1:].replace("_", "."))] = node

    families: dict[str, list[TaxonomyNode]] = {}
    for node in nodes.values():
        if node.kind == "concept_family" and node.parent_id:
            families.setdefault(node.parent_id, []).append(node)
    #: family code -> the sections the run said it draws on, so a family can be chosen by
    #: the section the book put the question in rather than by name similarity
    sections_of = {
        row.code: set(clean_sections(row.from_sections))
        for row in db.scalars(select(ConceptFamilyProposal).where(
            ConceptFamilyProposal.subject_code == assessment.subject_code
        ))
    }

    context = context_addresses(staged)
    mapped, blocked, context_kept, with_topic = 0, [], 0, 0
    for row in staged:
        if row.address in context:
            # The shared stem of a case study. Its sub-parts are the questions and they
            # map on their own; placing the paragraph too would file the same marks twice.
            row.blocked_reason = None
            context_kept += 1
            continue
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
        # The section the winning passages came from, and only then the code of whatever
        # the retrieval landed on. Both are the book's, never a guess.
        section = verdict.section or (_section_number(landed.code) if landed else None)
        topic = topics.get((chapter.id, section)) if section else None

        # The family is what every trend groups by and it is deliberately required, so a
        # question whose family cannot be settled is left staged rather than placed under
        # a guess. What changed is that the choice can now actually be made: the section
        # comes from the winning passages, and a family created from the book records the
        # section it came from, so the two can be matched.
        candidates = families.get(chapter.id, [])
        if not candidates:
            row.blocked_reason = (
                f"no concept family exists for {chapter.label}. Open the book screen for "
                f"this subject and create the families it proposes from the chapter's own "
                f"section headings."
            )
            blocked.append(row.address)
            continue
        # Every family of this chapter that claims the section the book put the question
        # in. A run proposes many families per chapter and several legitimately draw on one
        # section, so more than one claimant is normal rather than an error.
        claimants = [
            f for f in candidates
            if section and section in sections_of.get(f.code, set())
        ]
        ambiguous = None
        if len(claimants) == 1:
            family = claimants[0]
        elif claimants:
            # Deterministic, and stated as unsettled. The family claiming the fewest
            # sections is the closest fit for a question in one of them; the code breaks
            # ties so that mapping the same paper twice gives the same answer. Picking
            # whichever happened to come first was neither.
            family = min(
                claimants, key=lambda f: (len(sections_of.get(f.code, ())), f.code)
            )
            ambiguous = (
                f"{len(claimants)} families of {chapter.label} draw on section {section}; "
                f"the narrowest was taken and a person should settle it"
            )
        elif len(candidates) == 1:
            family = candidates[0]
        else:
            family = None
        if family is None:
            row.blocked_reason = (
                f"{len(candidates)} families exist for {chapter.label} and none claims "
                + (
                    f"section {section}, which is where the book puts this question"
                    if section
                    else "a section, and the passages that matched name no section either"
                )
                + ". Settle it in review, or re-create the families from the book so each "
                "one records the section it covers."
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
            # A question whose family could not be settled is one for a person to look at,
            # which is what this flag is for. It is not a reason to refuse the placement.
            source="model", needs_review=not verdict.agreed or ambiguous is not None,
            reasoning=(
                f"{mode} retrieval, margin {verdict.margin:.3f}"
                + (f". {ambiguous}" if ambiguous else "")
            ),
            # The chunk references, not the Candidate objects: JSON has to hold what a
            # reviewer reads, and the objects are not serialisable anyway.
            evidence=[c.reference for c in verdict.evidence if c.reference][:6],
            candidates=[
                nodes[n].label for n, _ in verdict.runners_up if n in nodes
            ][:4],
        ))
        # The topic is a skill the question tests, which is what the report reads to group
        # findings by sub-topic. Without this row a mapped question contributed to no topic
        # at all and the report fell back to the chapter.
        if topic is not None:
            db.add(QuestionSkill(
                question_id=question.id, node_id=topic.id, source="retrieval",
            ))
            with_topic += 1
        row.question_id = question.id
        row.blocked_reason = None
        mapped += 1

    db.commit()
    return {
        "assessment_id": assessment.id,
        "retrieval": mode,
        "mapped": mapped,
        "blocked": len(blocked),
        #: shared stems that were deliberately left unplaced, not failures
        "context_stems": context_kept,
        #: placed, with a topic from the book. The rest sit in a chapter and no finer.
        "with_topic": with_topic,
        "blocked_addresses": blocked[:20],
        "needs_review": db.scalar(select(func.count(QuestionPlacement.id)).where(
            QuestionPlacement.needs_review.is_(True),
            QuestionPlacement.question_id.in_(
                select(Question.id).where(Question.assessment_id == assessment.id)
            ),
        )) or 0,
        "next": f"Review at GET /assessments/{assessment.id}/scan.",
    }


# --------------------------------------------------------------------------------------
# The answer sheet: one student, against the paper already scanned and mapped
# --------------------------------------------------------------------------------------
class AnswerIn(BaseModel):
    address: str = Field(max_length=40)
    marks: float | None = Field(default=None, ge=0, le=100)
    #: 'awarded' | 'absent' | 'not_offered'. not_offered is the unattempted half of a
    #: choice pair and is excluded from every denominator -- absence of evidence, not
    #: evidence of weakness.
    state: str = Field(default="awarded", max_length=16)


class AnswerSheetIn(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1, max_length=400)
    by: str = Field(default="teacher", max_length=64)


def _student_for(db: Session, school: School, student_id: str) -> StudentProfile:
    student = db.get(StudentProfile, student_id)
    if student is None or student.school_id != school.id:
        raise HTTPException(404, "not found")
    return student


@router.get("/{assessment_id}/answers/{student_id}")
def read_answer_sheet(
    assessment_id: str,
    student_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """Every question on the paper, with this student's mark if one has been recorded.

    Driven by the paper rather than by the marks: a question with no mark yet must appear,
    because the gap is the thing the person entering them is looking for. A screen built
    from the marks alone shows a complete-looking list that is missing exactly what needs
    attention.
    """
    assessment = _get_assessment(db, school, assessment_id)
    student = _student_for(db, school, student_id)

    questions = list(db.scalars(
        select(Question).where(Question.assessment_id == assessment.id).order_by(Question.address)
    ))
    if not questions:
        raise HTTPException(
            422,
            "this paper has no mapped questions yet. Scan it, confirm the extraction and "
            "map it to the book first.",
        )

    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}
    latest: dict[str, MarkEvent] = {}
    rank = {s: i for i, s in enumerate(SOURCE_PRECEDENCE)}
    for event in db.scalars(
        select(MarkEvent).where(
            MarkEvent.assessment_id == assessment.id, MarkEvent.student_id == student.id
        )
    ):
        seen = latest.get(event.question_id)
        if (
            seen is None
            or rank.get(event.source, -1) > rank.get(seen.source, -1)
            or (event.source == seen.source and event.created_at >= seen.created_at)
        ):
            latest[event.question_id] = event

    rows = []
    for question in questions:
        event = latest.get(question.id)
        family = nodes.get(question.concept_family_id or "")
        chapter = nodes.get(question.chapter_id or "")
        rows.append({
            "address": question.address,
            "section": question.section,
            "question_no": question.question_no,
            "sub_part": question.sub_part,
            "choice_alt": question.choice_alt,
            "max_marks": float(question.max_marks),
            "stem_text": question.stem_text,
            "chapter": chapter.label if chapter else None,
            "concept_family": family.label if family else None,
            "marks": float(event.marks) if event and event.marks is not None else None,
            "state": event.state if event else None,
            "source": event.source if event else None,
        })

    entered = [r for r in rows if r["marks"] is not None or r["state"] == "absent"]
    return {
        "assessment": {
            "id": assessment.id, "title": assessment.title,
            "subject_code": assessment.subject_code,
            "total_marks": float(assessment.total_marks) if assessment.total_marks else None,
        },
        "student": {"id": student.id, "name": student.name, "roll_no": student.roll_no},
        "questions": rows,
        "entered": len(entered),
        "remaining": len(rows) - len(entered),
        "scored": sum(r["marks"] or 0.0 for r in rows if r["state"] != "not_offered"),
        "available": _available(rows),
    }


def _available(rows: list[dict]) -> float:
    """What this student was asked, counting every question exactly once.

    An internal choice prints twice and is worth its marks once, so the two halves are one
    question here. Summing both doubled it; counting only the (a) half lost it entirely
    whenever the student answered the (b) half and (a) was marked as not offered -- which
    is the normal way round, so the figure was wrong on any sheet with a choice in it.
    """
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row["section"], row["question_no"], row["sub_part"])
        groups.setdefault(key, []).append(row)

    total = 0.0
    for members in groups.values():
        offered = [m for m in members if m["state"] != "not_offered"]
        if not offered:
            continue
        # The halves of a choice are worth the same; max rather than sum so that a sheet
        # where neither half has been touched yet still counts the question once.
        total += max(float(m["max_marks"]) for m in offered)
    return total


@router.post("/{assessment_id}/answers/{student_id}/confirm")
def confirm_answer_sheet(
    assessment_id: str,
    student_id: str,
    body: AnswerSheetIn,
    school: School = Depends(require_scanner),
    db: Session = Depends(get_session),
) -> dict:
    """A person puts their name to this student's marks.

    Written as 'teacher', which outranks every automatic source, so a confirmation always
    supersedes whatever a scan proposed and never the other way round. Nothing is
    overwritten -- the earlier reading stays in the log, because how a mark was arrived at
    is part of being able to defend it later.

    A mark above what the question is worth is refused rather than clamped. Clamping would
    turn a typo into a plausible number nobody would ever question again.
    """
    assessment = _get_assessment(db, school, assessment_id)
    student = _student_for(db, school, student_id)

    questions = {
        q.address: q for q in db.scalars(
            select(Question).where(Question.assessment_id == assessment.id)
        )
    }
    written, rejected = 0, []
    for answer in body.answers:
        question = questions.get(answer.address)
        if question is None:
            rejected.append({"address": answer.address, "reason": "no such question on this paper"})
            continue
        if answer.state not in MARK_STATES:
            rejected.append({"address": answer.address, "reason": f"unknown state {answer.state!r}"})
            continue
        if answer.state == "awarded":
            if answer.marks is None:
                rejected.append({"address": answer.address, "reason": "awarded but no marks given"})
                continue
            if answer.marks > float(question.max_marks):
                rejected.append({
                    "address": answer.address,
                    "reason": f"{answer.marks:g} is more than the {float(question.max_marks):g} "
                              f"this question is worth",
                })
                continue

        db.add(MarkEvent(
            assessment_id=assessment.id, student_id=student.id, question_id=question.id,
            state=answer.state,
            marks=answer.marks if answer.state == "awarded" else None,
            source="teacher", confidence=1.0, actor_id=body.by[:36],
            provenance={"confirmed_by": body.by},
        ))
        written += 1
    db.commit()

    sheet = read_answer_sheet(assessment.id, student.id, school, db)
    return {
        "written": written,
        "rejected": rejected,
        "scored": sheet["scored"],
        "available": sheet["available"],
        "remaining": sheet["remaining"],
        #: Said rather than assumed: a sheet with questions still unmarked is not finished,
        #: and a total computed over a partial sheet reads exactly like a low score.
        "complete": sheet["remaining"] == 0,
    }
