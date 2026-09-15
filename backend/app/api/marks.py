"""Use case 2 routes: assessment ingest, the Q-matrix, marks, and reconciliation."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.api.schemas import (
    AssessmentIn,
    AssessmentPatchIn,
    MarkBatchIn,
    QuestionBatchIn,
    ReconcileIn,
)
from app.db import get_session
from app.extraction.address import Address, AddressResolver
from app.extraction.choice import group_choices
from app.extraction.verification import verify_paper
from app.mapping.solver import Constraint, QuestionDist, solve
from app.models import (
    Assessment,
    AnalysisRun,
    DataQualityFlag,
    LogicalPage,
    MarkEvent,
    Question,
    QuestionJudgment,
    QuestionPlacement,
    QuestionSkill,
    QuestionTier,
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


@router.get("")
def list_assessments(
    subject_code: str | None = None,
    status_: str | None = None,
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    """Every paper this school has, newest first. A principal's inbox, not a report."""
    query = select(Assessment).where(Assessment.school_id == school.id)
    if subject_code:
        query = query.where(Assessment.subject_code == subject_code)
    if status_:
        query = query.where(Assessment.status == status_)
    rows = db.scalars(query.order_by(Assessment.created_at.desc())).all()
    return {
        "assessments": [
            {
                "assessment_id": a.id,
                "subject_code": a.subject_code,
                "title": a.title,
                "paper_code": a.paper_code,
                "status": a.status,
                "total_marks": float(a.total_marks) if a.total_marks is not None else None,
                "created_at": a.created_at,
            }
            for a in rows
        ],
        "count": len(rows),
    }


@router.get("/{assessment_id}")
def get_assessment(
    assessment_id: str, school: School = Depends(require_admin), db: Session = Depends(get_session)
) -> dict:
    a = _get_assessment(db, school, assessment_id)
    question_count = db.scalar(
        select(func.count(Question.id)).where(Question.assessment_id == a.id)
    )
    marked_students = db.scalar(
        select(func.count(func.distinct(MarkEvent.student_id))).where(
            MarkEvent.assessment_id == a.id
        )
    )
    return {
        "assessment_id": a.id,
        "subject_code": a.subject_code,
        "curriculum_version": a.curriculum_version,
        "title": a.title,
        "paper_code": a.paper_code,
        "total_marks": float(a.total_marks) if a.total_marks is not None else None,
        "declared": a.declared,
        "syllabus_scope": a.syllabus_scope,
        "status": a.status,
        "qmatrix_frozen_at": a.qmatrix_frozen_at,
        "qmatrix_version": a.qmatrix_version,
        "question_count": question_count,
        "students_with_marks": marked_students,
        "created_at": a.created_at,
    }


@router.patch("/{assessment_id}")
def update_assessment(
    assessment_id: str,
    body: AssessmentPatchIn,
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    """Correct the paper's own metadata -- title, paper code, declared blueprint. Never
    subject or curriculum version: see AssessmentPatchIn."""
    a = _get_assessment(db, school, assessment_id)
    if body.title is not None:
        a.title = body.title
    if body.paper_code is not None:
        a.paper_code = body.paper_code
    if body.total_marks is not None:
        a.total_marks = body.total_marks
    if body.declared is not None:
        a.declared = body.declared
    db.flush()
    return {"assessment_id": a.id, "title": a.title, "paper_code": a.paper_code}


@router.delete("/{assessment_id}")
def delete_assessment(
    assessment_id: str,
    force: bool = False,
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    """Remove a paper and everything derived from it.

    Refused once real marks have been posted, unless ``force=true``: a paper that students
    have already been scored against is no longer just a mistaken upload, and deleting it
    silently would make every report that already cited it inexplicable. An empty or
    wrongly-created paper -- the common case, a wrong subject or a duplicate upload caught
    before marking -- deletes outright.
    """
    a = _get_assessment(db, school, assessment_id)
    question_ids = list(
        db.scalars(select(Question.id).where(Question.assessment_id == a.id))
    )
    marked = db.scalar(
        select(func.count(MarkEvent.id)).where(MarkEvent.assessment_id == a.id)
    )
    if marked and not force:
        raise HTTPException(
            409,
            f"{marked} mark(s) already posted against this paper. Pass force=true to "
            "delete anyway -- every report that cites this paper will lose its source.",
        )

    if question_ids:
        db.query(QuestionPlacement).filter(
            QuestionPlacement.question_id.in_(question_ids)
        ).delete(synchronize_session=False)
        db.query(QuestionTier).filter(
            QuestionTier.question_id.in_(question_ids)
        ).delete(synchronize_session=False)
        db.query(QuestionJudgment).filter(
            QuestionJudgment.question_id.in_(question_ids)
        ).delete(synchronize_session=False)
        db.query(QuestionSkill).filter(
            QuestionSkill.question_id.in_(question_ids)
        ).delete(synchronize_session=False)
    db.query(MarkEvent).filter(MarkEvent.assessment_id == a.id).delete(synchronize_session=False)
    db.query(DataQualityFlag).filter(
        DataQualityFlag.assessment_id == a.id
    ).delete(synchronize_session=False)
    db.query(AnalysisRun).filter(
        AnalysisRun.assessment_id == a.id
    ).delete(synchronize_session=False)
    db.query(LogicalPage).filter(
        LogicalPage.assessment_id == a.id
    ).delete(synchronize_session=False)
    db.query(Question).filter(Question.assessment_id == a.id).delete(synchronize_session=False)
    db.delete(a)
    db.commit()

    return {
        "assessment_id": assessment_id,
        "deleted": True,
        "questions_removed": len(question_ids),
        "marks_removed": marked,
        "forced": bool(marked and force),
    }


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
