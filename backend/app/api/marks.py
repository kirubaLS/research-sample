"""Use case 2 routes: assessment ingest, the Q-matrix, marks, and reconciliation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    Staff,
    current_staff,
    require_admin,
    require_marks_scope_for_student,
    require_paper_scope,
    require_reader,
    require_scanner,
    school_in_scope,
)
from app.api.documents import content_type_for, store_document
from app.api.schemas import (
    AssessmentIn,
    DuplicateDecisionIn,
    MarkBatchIn,
    QuestionBatchIn,
    ReconcileIn,
)
from app.api.upload import pages_to_pdf
from app.config import get_settings
from app.db import get_session
from app.extraction.address import Address, AddressResolver
from app.extraction.choice import group_choices
from app.extraction.verification import verify_paper
from app.ingest.book import stem_hash
from app.llm import estimate_usd
from app.mapping.family import Choice
from app.mapping.solver import Constraint, QuestionDist, solve
from app.mapping.topic_node import (
    BOOK_MAP_SUBJECTS,
    assert_topic_matches_section,
    book_map_topic_label,
    major_view,
    primary_order,
    section_number,
    set_question_topic,
    topic_headings,
    topic_node,
)
from app.models import (
    MARK_STATES,
    SOURCE_PRECEDENCE,
    AnalysisRun,
    Assessment,
    BookChunk,
    ChapterBoardUnit,
    ConceptFamilyProposal,
    DataQualityFlag,
    GridSheetJob,
    GridSheetRow,
    LogicalPage,
    MarkEvent,
    PaperScanJob,
    PlacementJob,
    ProposedMark,
    Question,
    QuestionJudgment,
    QuestionPlacement,
    QuestionSkill,
    QuestionTier,
    ScanDocument,
    ScannedQuestion,
    School,
    StudentProfile,
    StudentReport,
    TaxonomyNode,
)
from app.models.assessment import TIER_ALIASES
from app.taxonomy.variants import ServedVariant, VariantReuseError, enforce, variant_hash

router = APIRouter(prefix="/assessments", tags=["marks-engine"])
logger = logging.getLogger(__name__)


def _get_assessment(db: Session, school: School, assessment_id: str) -> Assessment:
    a = db.get(Assessment, assessment_id)
    if a is None or a.school_id != school.id:
        raise HTTPException(404, "not found")   # never confirm another school's data exists
    return a


@router.post("")
def create_assessment(
    body: AssessmentIn,
    staff: Staff = Depends(current_staff),
    x_school_id: str | None = Header(default=None, alias="X-School-Id"),
    db: Session = Depends(get_session),
) -> dict:
    from app.curriculum import CURRICULA

    if staff.is_teacher:
        # Paper authoring is open to every teacher key for every subject this deployment
        # carries, exam cell or not -- see require_paper_scope, which gives the same
        # every-subject right once an assessment_id exists to check it against. A
        # teacher's subject *assignment* still governs marks entry and class/section
        # visibility elsewhere; it grants nothing extra here and its absence refuses
        # nothing here either.
        assert staff.home is not None
        school = staff.home
    else:
        school = school_in_scope(staff, x_school_id, db)

    is_group_code = any(c.group_code == body.subject_code for c in CURRICULA.values())
    if body.subject_code not in CURRICULA and not is_group_code:
        raise HTTPException(
            422,
            f"{body.subject_code!r} is not a subject or subject group this deployment "
            f"carries. Use GET /admin/subjects to see what exists.",
        )
    # A group_code (e.g. "X.ENG") is exactly what a single real exam paper draws on when a
    # subject is more than one book -- see app.curriculum.group_subjects. Stored as-is on
    # the assessment; /place resolves it back to every book in the group.
    if body.paper_kind != "school" and body.exam_year is None:
        raise HTTPException(
            422,
            f"a {body.paper_kind} paper needs exam_year: the frequency layer groups by "
            f"the year the board set it, and a board paper of no year counts for nothing.",
        )
    if body.exam_id is not None:
        from app.models import Exam

        exam = db.get(Exam, body.exam_id)
        if exam is None or exam.school_id != school.id:
            raise HTTPException(404, "no such exam")
    if body.class_section_id is not None:
        from app.models import Section

        section = db.get(Section, body.class_section_id)
        if section is None or section.school_id != school.id:
            raise HTTPException(404, "no such class section")
    scope: list[str] | None = None
    if body.syllabus_scope:
        # A chapter the curriculum defines is a valid scope whether or not its book has
        # been loaded into the taxonomy yet: the Create-test screen offers the
        # curriculum's chapters (GET /admin/subjects/{code}/chapters), and a test can be
        # scheduled before its book is ingested. Placement reads the scope against the
        # taxonomy at run time, so a not-yet-loaded chapter simply does not narrow it.
        curricular = {
            ch.code for c in CURRICULA.values() for ch in c.chapters
        }
        known = {
            n.code for n in db.scalars(select(TaxonomyNode).where(
                TaxonomyNode.kind == "chapter", TaxonomyNode.code.in_(body.syllabus_scope),
            ))
        } | curricular
        unknown = sorted(set(body.syllabus_scope) - known)
        if unknown:
            raise HTTPException(422, f"not chapters in the taxonomy: {unknown}")
        scope = sorted(set(body.syllabus_scope))
    a = Assessment(
        school_id=school.id, subject_code=body.subject_code, title=body.title,
        paper_code=body.paper_code, total_marks=body.total_marks,
        curriculum_version=body.curriculum_version, declared=body.declared,
        paper_kind=body.paper_kind, exam_year=body.exam_year, exam_id=body.exam_id,
        syllabus_scope=scope, class_section_id=body.class_section_id,
    )
    db.add(a)
    db.flush()
    return {"assessment_id": a.id, "status": a.status}


def assessment_summaries(db: Session, assessments: list[Assessment]) -> list[dict]:
    """The list row every /assessments listing shares -- the principal's own (unscoped)
    and the teacher's own (subject-filtered, app.api.admin's teacher_papers) alike, so the
    two screens can never quietly drift into showing different stages for the same paper.
    """
    from app.api.academics import _subject_label  # local: avoids a circular import at module load
    from app.extraction.duplicates import held_by

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
    # The question paper's own upload (student_id null), newest first: what kind of file
    # and how many pages, so the papers screen can name the file it holds rather than
    # only counting the questions read from it.
    documents: dict[str, dict] = {}
    if ids:
        for doc in db.scalars(
            select(ScanDocument)
            .where(ScanDocument.assessment_id.in_(ids), ScanDocument.student_id.is_(None))
            .order_by(ScanDocument.created_at.desc())
        ):
            documents.setdefault(doc.assessment_id, {
                "id": doc.id, "kind": doc.kind, "page_count": doc.page_count,
                "uploaded_at": doc.created_at.isoformat() if doc.created_at else None,
            })

    # What the model calls on this paper cost, from the latest succeeded map and
    # classify jobs' own token counts (see placement.py's "spend"): the papers screen
    # shows it beside the counts, so a re-run is a decision with a price on it.
    spend: dict[str, dict] = {}
    if ids:
        for job in db.scalars(
            select(PlacementJob).where(
                PlacementJob.assessment_id.in_(ids), PlacementJob.status == "succeeded",
            ).order_by(PlacementJob.created_at.desc())
        ):
            kind = job.kind or "place"
            entry = spend.setdefault(a_id := job.assessment_id, {"seen": set()})
            if kind in entry["seen"] or not isinstance(job.result, dict):
                continue
            entry["seen"].add(kind)
            part = job.result.get("spend") or {}
            for key in ("calls", "input_tokens", "output_tokens", "cache_read_tokens", "estimated_usd"):
                entry[key] = round(entry.get(key, 0) + (part.get(key) or 0), 4)
            del a_id

    rows = []
    for a in assessments:
        n_questions = questions.get(a.id, 0)
        n_mapped = mapped.get(a.id, 0)
        paper_spend = spend.get(a.id)
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
            "subject_label": _subject_label(a.subject_code),
            "paper_code": a.paper_code,
            "total_marks": float(a.total_marks) if a.total_marks else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            #: Which exam day this paper is grouped under, if any (see app.api.exams) --
            #: real, not derived, so the Question Papers screen can group a teacher's own
            #: papers by test without a second round trip per paper.
            "exam_id": a.exam_id,
            #: duplicate_upload_check: the matched papers while the hold lasts -- the
            #: teacher has not chosen "open existing" or "keep as new" and the paper has
            #: not been mapped (by hand); None otherwise, so the list's label goes away
            "duplicates_pending": held_by(a, stage),
            "stage": stage,
            "scanned_questions": scanned.get(a.id, 0),
            "document": documents.get(a.id),
            #: model calls and their estimated cost across the latest map and classify
            #: runs; None before either has run
            "spend": (
                {k: v for k, v in paper_spend.items() if k != "seen"} if paper_spend else None
            ),
            "questions": n_questions,
            "mapped_questions": n_mapped,
            "students_with_marks": marked.get(a.id, 0),
            #: What the answer-sheet screen needs to know before it offers this paper.
            "ready_for_answer_sheets": n_questions > 0,
        })
    return rows


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
    return {"assessments": assessment_summaries(db, assessments)}


class AssessmentEditIn(BaseModel):
    """Rename a paper, or correct what was typed when it was created.

    Never the questions, marks or mapping -- those come from a re-scan or a re-map, which
    keep their own history. This is metadata a person can simply have gotten wrong.
    """

    title: str | None = None
    paper_code: str | None = None
    total_marks: float | None = None


@router.patch("/{assessment_id}")
def edit_assessment(
    assessment_id: str, body: AssessmentEditIn,
    school: School = Depends(require_paper_scope), db: Session = Depends(get_session),
) -> dict:
    a = _get_assessment(db, school, assessment_id)
    if a.scan_confirmed_at:
        # Once a person has signed off the extraction, every report downstream treats the
        # paper's identity as fact. Renaming it after that would leave old reports
        # pointing at a title or paper code that no longer matches what was confirmed.
        raise HTTPException(
            409,
            "this paper's scan has already been confirmed; re-scan it to change its "
            "identity rather than editing it in place",
        )
    changed = []
    for field_name in ("title", "paper_code", "total_marks"):
        value = getattr(body, field_name)
        if value is None:
            continue
        setattr(a, field_name, value)
        changed.append(field_name)
    db.commit()
    return {"assessment_id": a.id, "changed": changed}


@router.delete("/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assessment(
    assessment_id: str,
    school: School = Depends(require_paper_scope), db: Session = Depends(get_session),
) -> None:
    """Remove a paper and everything staged, scanned, mapped or marked under it.

    Hard delete, like every other removal in this API (a re-upload replaces its old scan
    document the same way) -- there is no soft-delete column on any of these tables to
    honour instead. Same authority as every other paper-authoring route
    (require_paper_scope): a principal reaches any paper in their school; a subject-
    assigned teacher reaches only a paper in their own subject, the same scope that let
    them create, scan and map it in the first place. A class-only teacher, who never
    holds paper-authoring rights at all, still can't reach this.
    """
    a = _get_assessment(db, school, assessment_id)
    from sqlalchemy.exc import IntegrityError

    # The per-question tables (skill, tier, placement, judgment) are keyed on question_id
    # with no cascade. They are deleted by a subquery on the paper's questions, not from
    # a list of ids read beforehand, and immediately before Question itself: a "Read and
    # classify" job still running on this paper commits new placement/tier rows in the
    # background, and a snapshot of ids taken a statement earlier missed exactly the rows
    # it inserted in between -- the Question delete then failed on a foreign key
    # violation as a bare 500. If the job lands a row inside even that window, the whole
    # cleanup is retried; a paper the job keeps writing to is refused with a reason
    # rather than an internal error.
    own_questions = select(Question.id).where(Question.assessment_id == assessment_id)
    for attempt in range(3):
        try:
            with db.begin_nested():
                for model in (QuestionSkill, QuestionTier, QuestionPlacement, QuestionJudgment):
                    db.execute(model.__table__.delete().where(
                        model.question_id.in_(own_questions)
                    ))
                _delete_assessment_rows(db, assessment_id)
            break
        except IntegrityError:
            if attempt == 2:
                raise HTTPException(
                    409,
                    "a background job (Read and classify, or a scan) is still writing to "
                    "this paper. Wait for it to finish, then delete the paper again.",
                ) from None
    db.delete(a)
    db.commit()


def _delete_assessment_rows(db: Session, assessment_id: str) -> None:
    """Everything keyed on assessment.id, in an order the foreign keys allow."""
    for model in (
        # ScannedQuestion and MarkEvent both go before Question: ScannedQuestion.question_id
        # is a nullable FK onto Question, set once a scanned row is promoted, and
        # MarkEvent.question_id is a hard (non-nullable) one -- a real mark always names
        # the question it was awarded on. Either one still existing when Question is
        # deleted rejects the whole delete with a bare foreign key violation; a paper that
        # had ever had a mark entered against it (i.e. almost any real paper) could never
        # actually be deleted until MarkEvent was moved ahead of Question here.
        ScannedQuestion, MarkEvent, Question, LogicalPage, DataQualityFlag, AnalysisRun,
        StudentReport, ProposedMark,
        # The background-job tables each scan/grid-sheet/placement step writes -- each one
        # carries its own hard FK onto assessment.id, and none of them was ever cleaned up
        # here, so a paper that had gone through a scan, a grid-sheet read, or "Read and
        # classify" (i.e. any real paper, not a freshly-created empty one) could never
        # actually be deleted: the delete failed on a foreign key violation with no
        # explanation a person reading "can't delete this paper" would ever guess.
        # GridSheetRow/GridSheetJob before ScanDocument below would also work via that
        # table's own ON DELETE CASCADE, but deleting them explicitly here does not depend
        # on that cascade still being the case tomorrow.
        GridSheetRow, GridSheetJob, PaperScanJob, PlacementJob,
    ):
        db.execute(model.__table__.delete().where(model.assessment_id == assessment_id))
    # ScanDocument's own `pages` relationship cascades to ScanPage in the ORM, so this one
    # goes through db.delete rather than a bulk table delete.
    for document in db.scalars(
        select(ScanDocument).where(ScanDocument.assessment_id == assessment_id)
    ):
        db.delete(document)
    # Flushed separately from the assessment's own delete: ScanDocument's cascade to its
    # ScanPage/GridSheetRow rows is an ORM-level delete the unit of work only orders
    # correctly against the bulk, Core-level deletes above (and against the assessment row
    # itself) once it has actually run, not merely been queued.
    db.flush()


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
            .where(
                Assessment.school_id == school.id, Assessment.id != a.id,
                # a board paper on file was never put in front of this class; it is a
                # record of the exam, not a cycle the class sat
                Assessment.paper_kind == "school",
            )
        ).all()
    ]
    incoming = [
        (q.question_no, node_id(q.concept_family, "concept family"), variant_hash(q.concept_variant))
        for q in body.questions
    ]
    # The guard protects a class from seeing the same variant twice. A board paper is not
    # served to a class, so registering one that overlaps a school test is not a reuse.
    if a.paper_kind == "school":
        try:
            enforce(incoming, served)
        except VariantReuseError as exc:
            raise HTTPException(409, str(exc)) from exc

    rows: list[tuple[Address, float]] = []
    created = 0
    attempt_required: dict[str, int] = {}
    for q in body.questions:
        addr = Address(q.section, q.question_no, q.sub_part, q.choice_alt)
        rows.append((addr, q.max_marks))
        if q.attempt_required:
            attempt_required[addr.key] = q.attempt_required
        existing = db.scalar(
            select(Question).where(
                Question.assessment_id == a.id, Question.address == addr.key
            )
        )
        if existing is None:
            row = Question(
                assessment_id=a.id, address=addr.key, section=q.section,
                question_no=q.question_no, sub_part=q.sub_part, choice_alt=q.choice_alt,
                attempt_required=q.attempt_required,
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

    mapping, groups = group_choices(rows, attempt_required)
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
    attempt_required = {
        Address(q.section, q.question_no, q.sub_part, q.choice_alt).key: q.attempt_required
        for q in questions
        if q.attempt_required
    }
    _, groups = group_choices(rows, attempt_required)
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
def _scanned_effective_total(rows, context: set[str]) -> float:
    """What these staged rows are worth, counting each mark exactly once.

    Shared by the scan-review GET and confirm_scan so the number a person checks before
    confirming is the same one confirm_scan itself holds the paper to.

    Binary OR is filtered directly on (None, 'a') rather than through
    app.extraction.choice.group_choices, matching both extraction routes' own convention
    (paper.py's docstring and paper_vision.py's SYSTEM prompt both leave the first half's
    choice_alt blank, only the second half is lettered) -- group_choices' OR-bucketing
    needs both halves lettered, so handing it these rows as-is would leave every real
    OR-pair ungrouped and double-counted. 'Attempt any N of M' groups (attempt_required)
    have no such quirk and do reuse group_choices. Never a naive sum of every row, which
    is exactly the double-count that produced a 111-mark read on an 80-mark paper.
    """
    countable = [r for r in rows if r.address not in context]
    grouped = [r for r in countable if r.attempt_required]
    ungrouped = [r for r in countable if not r.attempt_required]

    # float() per row: a row read back from the database carries a Decimal, a row just
    # filled in this session a float, and the two do not add
    total = float(sum(
        float(r.max_marks or 0) for r in ungrouped if r.choice_alt in (None, "a")
    ))

    if grouped:
        addr_rows = [
            (Address(r.section, r.question_no, r.sub_part, r.choice_alt), float(r.max_marks or 0))
            for r in grouped
        ]
        attempt_required = {
            Address(r.section, r.question_no, r.sub_part, r.choice_alt).key: r.attempt_required
            for r in grouped
        }
        _, groups = group_choices(addr_rows, attempt_required)
        grouped_keys = {a.key for g in groups for a in g.addresses}
        total += sum(g.marks for g in groups)
        total += sum(
            m for a, m in addr_rows
            if a.key not in grouped_keys and a.choice_alt in (None, "a")
        )
    return total


#: How far the read total may sit from the paper's own declared total before the text
#: route's read is distrusted. A flat floor for a small paper (a 2-mark tolerance on an
#: 8-mark quiz would swallow a whole quarter of it) and a percentage for a large one (a
#: fixed 2 marks on a 100-question board paper is too tight for the odd half-mark
#: rounding a real paper's own printed total sometimes carries) -- whichever is larger.
#: 2% is chosen so a single missed sub-part (rarely worth less than a couple of marks)
#: still trips it, while accumulated half-mark rounding across many sections does not.
TEXT_ROUTE_MARK_TOLERANCE_FLOOR = 2.0
TEXT_ROUTE_MARK_TOLERANCE_PCT = 0.02


def _text_route_is_confident(extract) -> bool:
    """Should a route='text' extraction be trusted, or is it worth paying for a vision
    re-read instead?

    Self-comparison only -- nothing here looks at the paper again, it only asks whether
    the read paper.py already produced is internally consistent. Reuses
    PaperExtract.total_marks (the same OR/choice-group-aware, count-once summation
    _scanned_effective_total above applies to staged rows) rather than a naive sum, for
    the same reason that function exists: a naive sum double-counts an internal choice
    and calls a correctly-read paper unreliable.

    No declared total on the paper (``_declared`` found no "Maximum Marks: N" line, or
    whatever printed it does not match that pattern) means there is nothing to compare
    the read against -- this returns True rather than False. Falling back whenever a
    paper simply prints its total in an unrecognised way would trigger a paid vision
    read on every such paper, not just the broken ones, which is exactly the routine
    cost this check exists to avoid; a paper this route reads with no other problems is
    still the best information available, so it ships.
    """
    if extract.declared_total is None:
        return True
    tolerance = max(
        TEXT_ROUTE_MARK_TOLERANCE_FLOOR, TEXT_ROUTE_MARK_TOLERANCE_PCT * extract.declared_total
    )
    if abs(extract.declared_total - extract.total_marks) > tolerance:
        return False
    # A leaf question or sub-part with no mark label at all -- not a context stem, whose
    # marks legitimately live on its sub-parts (_mark_context_rows) -- is a row the parser
    # gave up on. The totals check above can still pass by coincidence (two missed marks
    # offsetting two extra ones elsewhere), so this is checked independently rather than
    # folded into the same tolerance.
    return not any(q.max_marks is None and not q.is_context for q in extract.questions)


def _supersede_pending_paper_jobs(
    db: Session, assessment_id: str, *, except_job_id: str | None = None,
) -> None:
    """A fresh read of this paper -- the synchronous text route, or the job just queued
    for the vision route -- is what a person is about to see and confirm against. Any
    other PaperScanJob still pending for the same assessment was started before this one
    and, left alone, would write its now-stale result over this one whenever its own slow
    vision call happens to finish (a person can dislike a scan and re-scan long before the
    first read comes back). Flipped to failed here, at the moment the newer attempt
    begins, so _run_paper_scan_job's own status re-check sees itself superseded and skips
    its write instead of clobbering what the newer attempt already produced.
    """
    query = select(PaperScanJob).where(
        PaperScanJob.assessment_id == assessment_id, PaperScanJob.status == "pending",
    )
    if except_job_id:
        query = query.where(PaperScanJob.id != except_job_id)
    for stale in db.scalars(query):
        stale.status = "failed"
        stale.error_status = 409
        stale.error_detail = (
            "a newer scan of this paper was read before this one finished; this read's "
            "result was discarded so it could not overwrite the newer one"
        )
        stale.finished_at = datetime.now(UTC)


def _finish_paper_scan(
    db: Session, school: School, assessment: Assessment, extract, originals, source_sha: str,
) -> dict:
    """Write a paper's extracted questions and return the same response body regardless
    of which route (text or vision) produced ``extract`` -- everything from here on is
    one pipeline, exactly as the module docstrings for paper.py and paper_vision.py say.
    """
    from app.extraction.paper import context_addresses, dedupe_addresses

    # A duplicate address is a database uniqueness violation, not just a data-quality
    # complaint -- see dedupe_addresses's own docstring for the shape of vision read that
    # produces one. Caught and resolved here rather than left to the INSERT below, whose
    # failure took every other question read off the same paper down with it in the same
    # transaction.
    extract.questions, dedupe_problems = dedupe_addresses(extract.questions)
    extract.problems = [*extract.problems, *dedupe_problems]

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
            attempt_required=question.attempt_required,
        ))
        written += 1

    # A new read of the paper invalidates the old signature: whoever confirmed did not see
    # these rows.
    assessment.scan_confirmed_at = None
    assessment.scan_confirmed_by = None
    assessment.route = extract.route
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
    if get_settings().paper_capture_structure:
        # Additive keys: every reader of "sections" (marks per letter) is unchanged.
        assessment.declared = {
            **assessment.declared,
            "section_titles": dict(getattr(extract, "section_titles", None) or {}) or None,
            "syllabus_lines": list(getattr(extract, "syllabus_lines", None) or []) or None,
        }

    # The paper itself, kept exactly as it arrived. Storing only what we read off it left
    # every later question -- "is that really what question 14 said?" -- unanswerable.
    store_document(
        db, school_id=school.id, assessment_id=assessment.id, kind="question_paper",
        pages=[(content, content_type, None) for content, content_type, _ in originals],
    )
    duplicates = None
    if get_settings().duplicate_upload_check:
        # Before any model call is spent on mapping: is this a paper the school already
        # has? Shown to the teacher, never acted on -- see app.extraction.duplicates.
        from app.extraction.duplicates import find_duplicates

        duplicates = find_duplicates(
            db, assessment, stems=[q.stem_text for q in extract.questions],
            hashes=assessment.source_file_hashes,
        )
        assessment.duplicate_check = (
            {"candidates": duplicates, "decision": None} if duplicates else None
        )
    db.commit()

    context = context_addresses(extract.questions)
    return {
        "assessment_id": assessment.id,
        #: duplicate_upload_check: existing papers this one matches (file hash, or at
        #: least 70% of its question stems), most similar first. While any are listed
        #: and the teacher has not chosen (POST .../duplicates/decision), nothing is
        #: mapped or classified by itself.
        **({"duplicates": duplicates} if duplicates is not None else {}),
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


def _finish_paper_scan_job(
    job_id: str, *, status_value: str, result: dict | None = None,
    error_status: int | None = None, error_detail: str | None = None,
) -> None:
    """Write a job's outcome in its own short-lived session -- see _run_paper_scan_job's
    docstring for why a session is never held open across the vision call itself."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        job = db.get(PaperScanJob, job_id)
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


def _report_paper_scan_progress(job_id: str, done: int, total: int) -> None:
    """Commit one page's worth of real progress -- called from inside
    ``read_paper_vision``'s as_completed loop, after each page's own vision call
    completes (see AnthropicPaperVisionReader._read_all). A short-lived session of its
    own, opened and closed just for this write, the same "never one held open across the
    slow call" discipline _run_paper_scan_job's own docstring gives -- this fires *during*
    that call, potentially many times, not just once after it.

    Never raises: a failure writing progress is not a failure of the scan itself, and
    must not abort a read that is otherwise succeeding just because one progress commit
    could not land.
    """
    from app.db import SessionLocal

    try:
        db = SessionLocal()
        try:
            job = db.get(PaperScanJob, job_id)
            if job is not None:
                job.progress_done = done
                job.progress_total = total
                db.commit()
        finally:
            db.close()
    except Exception:  # noqa: BLE001 -- a progress write must never sink the real read
        logger.exception("paper scan job %s: failed to write progress %s/%s", job_id, done, total)


def _run_paper_scan_job(job_id: str) -> None:
    """The slow part of reading a scanned question paper, run after the request that
    queued it has already returned.

    Two short-lived sessions, never one held open across the vision call -- the same
    lesson IngestJob's and GridSheetJob's own docstrings give: a session kept open while a
    slow external call runs sits idle-in-transaction for however long that takes, and
    Postgres enforces its own idle-in-transaction timeout regardless of what this process
    is doing.

    Never raises: every failure is caught and written to the job row, because that row is
    the only place left a failure can be seen once the request that would have shown it
    has already returned.
    """
    import tempfile
    from pathlib import Path

    from app.db import SessionLocal
    from app.extraction.paper_vision import rasterize_pdf, read_paper_vision

    db = SessionLocal()
    try:
        job = db.get(PaperScanJob, job_id)
        if job is None:
            return
        pdf_bytes, school_id, assessment_id = job.pdf_bytes, job.school_id, job.assessment_id
    finally:
        db.close()  # released BEFORE the slow vision call below, not held across it

    try:
        handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        handle.write(pdf_bytes)
        handle.close()
        path = Path(handle.name)
        try:
            pages = rasterize_pdf(path)
        finally:
            path.unlink(missing_ok=True)

        settings = get_settings()
        _report_paper_scan_progress(job_id, 0, len(pages))
        structure = {"capture_structure": True} if settings.paper_capture_structure else {}
        reading = read_paper_vision(
            pages, api_key=settings.anthropic_api_key, model=settings.model_high_stakes,
            page_concurrency=settings.vision_page_concurrency,
            on_progress=lambda done, total: _report_paper_scan_progress(job_id, done, total),
            **structure,
        )
        if reading.refused:
            _finish_paper_scan_job(
                job_id, status_value="failed", error_status=422, error_detail=reading.refused,
            )
            return

        from app.extraction.paper import PaperExtract

        extract = PaperExtract(
            route="vision", page_count=len(pages), questions=reading.questions,
            declared_sections=reading.declared_sections, declared_count=reading.declared_count,
            declared_total=reading.declared_total, problems=reading.problems,
            section_titles=dict(getattr(reading, "section_titles", None) or {}),
            syllabus_lines=list(getattr(reading, "syllabus_lines", None) or []),
        )
        check_db = SessionLocal()
        try:
            db_assessment = check_db.get(Assessment, assessment_id)
            refusal = (
                check_paper_subject(check_db, db_assessment, extract) if db_assessment else None
            )
        finally:
            check_db.close()
        if refusal:
            _finish_paper_scan_job(job_id, status_value="failed", error_status=422, error_detail=refusal)
            return
    except Exception as exc:  # noqa: BLE001 -- see docstring: this must never escape.
        # This covers the rasterize/vision-read half of the job, the same way the
        # try/except below already covered the database-write half -- previously a
        # failure here (a 413 from too large a request, a rate limit, a network drop)
        # propagated all the way out as an uncaught background-task exception, which
        # crashed silently and left the job at "pending" forever with nothing left
        # running to ever mark it failed.
        _finish_paper_scan_job(
            job_id, status_value="failed", error_status=500,
            error_detail=f"{type(exc).__name__}: {exc}",
        )
        return

    db = SessionLocal()
    try:
        # Locked and re-read fresh, not the `job` loaded at the top of this function
        # before the (possibly minutes-long) vision call: a newer scan of this same
        # paper may have started and finished entirely while this job was in flight,
        # flipping this row to "failed" via _supersede_pending_paper_jobs. The lock
        # closes the window between that check and this job's own write below.
        current = db.get(PaperScanJob, job_id, with_for_update=True)
        if current is None or current.status != "pending":
            return
        school = db.get(School, school_id)
        assessment = db.get(Assessment, assessment_id)
        if school is None or assessment is None:
            _finish_paper_scan_job(
                job_id, status_value="failed", error_status=404,
                error_detail="the school or the paper this scan belonged to was removed",
            )
            return
        source_sha = __import__("hashlib").sha256(pdf_bytes).hexdigest()
        originals = [(pdf_bytes, "application/pdf", "scan.pdf")]
        result = _finish_paper_scan(db, school, assessment, extract, originals, source_sha)
    except Exception as exc:  # noqa: BLE001 -- see docstring: this must never escape
        _finish_paper_scan_job(
            job_id, status_value="failed", error_status=500,
            error_detail=f"{type(exc).__name__}: {exc}",
        )
        return
    finally:
        db.close()

    auto: dict | None = None
    if get_settings().auto_pipeline and not result.get("duplicates"):
        db = SessionLocal()
        try:
            auto = _queue_auto_pipeline(db, school_id, assessment_id)
        finally:
            db.close()
        result = {**result, "auto": auto}
    _finish_paper_scan_job(job_id, status_value="succeeded", result=result)
    if auto is not None and not auto.get("already_queued"):
        _run_auto_pipeline(assessment_id, auto)


@router.post("/{assessment_id}/scan", status_code=status.HTTP_201_CREATED, response_model=None)
async def scan_paper(
    assessment_id: str,
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
    school: School = Depends(require_paper_scope),
    db: Session = Depends(get_session),
) -> dict | JSONResponse:
    """Read a question paper -- PDF or photograph -- into staged questions.

    Writes to scanned_question, not to question: a question row needs a board unit and a
    concept family, and neither is knowable from the paper. They come from the book, in
    the mapping step that follows.

    Re-scanning replaces the staged rows for questions that have not been promoted yet, so
    a paper can be re-read after a bad upload without unpicking what mapping already did.

    A PDF with a text layer is read here, directly, and returns its result the way it
    always has. A scan or a photograph -- no text layer at all -- cannot be read inside
    this request: it needs a vision call, which can run past Render's own request
    timeout, so it is queued as a PaperScanJob and this returns 202 instead. Poll
    GET .../scan/jobs/{job_id} for the result this endpoint used to refuse to produce.
    """
    from app.extraction.paper import extract_paper

    assessment = _get_assessment(db, school, assessment_id)
    if assessment.qmatrix_frozen_at:
        raise HTTPException(409, "the Q-matrix is frozen; create a new version to re-scan")

    # This request is about to produce the newest read of this paper, whether it writes
    # synchronously below or queues a job to do it -- either way any earlier vision job
    # still pending for this paper is now stale and must not be allowed to write over
    # what this request produces once it eventually finishes.
    _supersede_pending_paper_jobs(db, assessment.id)
    db.commit()

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
    if get_settings().duplicate_upload_check:
        # each original file, before pages_to_pdf merges them: the merged PDF's bytes
        # differ between uploads of the very same pages
        from app.extraction.duplicates import file_hashes

        assessment.source_file_hashes = file_hashes(originals)

    path = await pages_to_pdf(files)
    try:
        extract = extract_paper(path, subject_code=assessment.subject_code)
        raw_bytes = path.read_bytes()
        source_sha = __import__("hashlib").sha256(raw_bytes).hexdigest()
    finally:
        path.unlink(missing_ok=True)

    # Another subject's paper is refused here, before a page or a row is stored: read
    # against this subject's book it would only ever be filed wrongly.
    refusal = check_paper_subject(db, assessment, extract)
    if refusal:
        raise HTTPException(422, refusal)

    # The text route ran and produced something, but its own marks don't add up against
    # what the paper declares for itself -- see _text_route_is_confident. One shot only:
    # this never re-checks the vision route's own result the same way. A paper hard
    # enough to beat both reads is a genuinely hard paper, and chaining another fallback
    # onto vision would just be guessing again, on the vision pipeline's own dime.
    unreliable_text = extract.route == "text" and not _text_route_is_confident(extract)

    if extract.route == "vision" or unreliable_text:
        assessment.route = "vision"
        assessment.pdf_page_count = extract.page_count
        job = PaperScanJob(school_id=school.id, assessment_id=assessment.id, pdf_bytes=raw_bytes)
        db.add(job)
        db.commit()
        background_tasks.add_task(_run_paper_scan_job, job.id)
        content = {
            "job_id": job.id, "status": "pending",
            "next": f"Poll GET /assessments/{assessment.id}/scan/jobs/{job.id} for the result.",
        }
        if unreliable_text:
            # A native PDF is normally read synchronously and this 202 is otherwise only
            # ever seen for a photograph -- without saying why, a person scanning a plain
            # PDF sees an unexplained wait where they expect an instant result.
            content["detail"] = (
                "the fast read of this paper looked unreliable, so it is being re-read "
                "more carefully with the vision model instead."
            )
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=content)

    result = _finish_paper_scan(db, school, assessment, extract, originals, source_sha)
    if get_settings().auto_pipeline and not result.get("duplicates"):
        # The text route answers inline; the rest of the pipeline (confirm, map,
        # classify) still runs by itself, after this response has gone back.
        auto = _queue_auto_pipeline(db, school.id, assessment.id)
        result = {**result, "auto": auto}
        if auto.get("already_queued"):
            pass
        elif background_tasks is not None:
            background_tasks.add_task(_run_auto_pipeline, assessment.id, auto)
        else:
            _run_auto_pipeline(assessment.id, auto)
    return result


#: No legitimate scan sits in "pending" this long -- rasterizing a paper and reading it
#: with the vision model is a matter of tens of seconds to a few minutes, even for a long
#: paper. A job still pending past this is one whose worker process died mid-task (an
#: OOM-kill, a deploy that restarted the instance): a process kill bypasses the try/except
#: in _run_paper_scan_job entirely, so nothing ever writes "failed" to that row, and
#: without this check the frontend would poll it forever. Chosen well above the ~10
#: minutes the client itself gives up polling at, so a job that is merely slow is never
#: mistaken for one that is stuck.
PAPER_SCAN_JOB_STALE_AFTER = timedelta(minutes=15)


@router.get("/{assessment_id}/scan/jobs/{job_id}")
def get_paper_scan_job(
    assessment_id: str,
    job_id: str,
    school: School = Depends(require_paper_scope),
    db: Session = Depends(get_session),
) -> dict:
    """Poll for the result of a scanned paper's vision read -- see PaperScanJob and
    scan_paper. A failed job carries the same status code and detail a synchronous scan
    would have raised, not a bare 'failed'."""
    job = db.get(PaperScanJob, job_id)
    if job is None or job.assessment_id != assessment_id or job.school_id != school.id:
        raise HTTPException(404, f"no job {job_id!r} for this paper")
    created_at = job.created_at if job.created_at.tzinfo else job.created_at.replace(tzinfo=UTC)
    if job.status == "pending" and datetime.now(UTC) - created_at > PAPER_SCAN_JOB_STALE_AFTER:
        job.status = "failed"
        job.error_status = 504
        job.error_detail = (
            "the scan never finished -- the server likely restarted while reading it. "
            "Please retake or resubmit the pages."
        )
        job.finished_at = datetime.now(UTC)
        db.commit()
    if job.status == "failed":
        raise HTTPException(job.error_status or 500, job.error_detail or "the job failed")
    if job.status != "succeeded":
        return {
            "job_id": job.id, "status": job.status,
            "progress_done": job.progress_done, "progress_total": job.progress_total,
        }
    return {
        "job_id": job.id, "status": "succeeded",
        "progress_done": job.progress_done, "progress_total": job.progress_total,
        **(job.result or {}),
    }


#: A sub-part's own printed letter, in the order CBSE actually uses it: lowercase roman
#: up to xv (every group we've measured stays well under that), or a plain a/b/c/d style
#: on the papers that use one instead -- plain string order already agrees with roman
#: order up to "v" by coincidence (shared prefixes sort short-before-long), which is
#: exactly why a paper with only i-v sub-parts never surfaced this: it silently breaks
#: past that ("ix" < "viii" as plain strings, backwards), which papers with a "vi" or
#: later sub-part would eventually hit.
_ROMAN_SUB_PARTS = {
    r: n for n, r in enumerate(
        ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
         "xi", "xii", "xiii", "xiv", "xv"],
        start=1,
    )
}


def _sub_part_sort_key(sub_part: str | None) -> tuple[int, int | str]:
    if not sub_part:
        return (0, "")  # a context stem (no sub-part) sorts before its own sub-parts
    s = sub_part.strip().lower()
    if s in _ROMAN_SUB_PARTS:
        return (1, _ROMAN_SUB_PARTS[s])
    return (2, s)  # a/b/c-style papers: plain alphabetical is already correct


def _question_no_sort_key(question_no: str) -> tuple[int, int | str]:
    no = (question_no or "").strip()
    try:
        return (0, int(no))
    except ValueError:
        return (1, no)  # not purely numeric (rare) -- falls back to plain string order


@router.get("/{assessment_id}/scan")
def read_scan(
    assessment_id: str,
    school: School = Depends(require_paper_scope),
    db: Session = Depends(get_session),
) -> dict:
    """The staged questions, and what is stopping each one becoming a real question."""
    assessment = _get_assessment(db, school, assessment_id)
    rows = list(db.scalars(
        select(ScannedQuestion)
        .where(ScannedQuestion.assessment_id == assessment.id)
        .order_by(ScannedQuestion.section, ScannedQuestion.logical_page)
    ))
    # The DB query above only guarantees section and the page a row happened to be read
    # from -- which page a continuation landed on says nothing about where it belongs in
    # the paper (that's the whole reason last_question_no carries it forward at all), and
    # even an ordinary page mixes several questions top to bottom. A reviewer needs the
    # paper's own order, not whichever order the reads happened to come back in.
    rows.sort(key=lambda r: (
        r.section or "", _question_no_sort_key(r.question_no),
        _sub_part_sort_key(r.sub_part), r.choice_alt or "",
    ))
    questions = {q.id: q for q in db.scalars(
        select(Question).where(Question.assessment_id == assessment.id)
    )}
    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode))}

    skills: dict[str, list[str]] = {}
    # heaviest first: the Topic column shows the primary, a secondary (the other section
    # a part of a multi-part question is answered in) never displaces it; equal weights
    # by id, so the column never depends on the database's row order
    for link in sorted(
        db.scalars(select(QuestionSkill).where(
            QuestionSkill.question_id.in_([r.question_id for r in rows if r.question_id] or [""])
        )),
        key=primary_order,
    ):
        node = nodes.get(link.node_id)
        if node is not None:
            skills.setdefault(link.question_id, []).append(node.label)
    from app.classify.current_tier import current_tiers

    # the newest row that names a tier wins. classified_question_ids is every question a
    # classify pass actually looked at, whether or not it settled on a tier -- place()
    # writes one QuestionTier row per question it processes even when the tier itself
    # comes back None (an abstain is still a verdict), so this is the honest signal for
    # "has classify run on this paper", not "did it agree every time".
    tiers, classified_question_ids = current_tiers(db, [r.question_id for r in rows])

    # QuestionPlacement is append-only, so the newest row per question is the current
    # verdict and its reasoning -- including a family the judge could not settle, which
    # was recorded and then invisible everywhere except a count on the /place response.
    review: dict[str, tuple[bool, str | None]] = {}
    for row_placement in db.scalars(
        select(QuestionPlacement)
        .where(QuestionPlacement.question_id.in_(
            [r.question_id for r in rows if r.question_id] or [""]
        ))
        .order_by(QuestionPlacement.created_at)
    ):
        review[row_placement.question_id] = (
            row_placement.needs_review, row_placement.reasoning or None
        )

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
            #: the latest placement's own verdict on itself -- a family the reading could
            #: not settle, or one it moved the question to a chapter that cannot place it,
            #: was recorded on every run and readable nowhere except a bare count.
            "needs_review": (review.get(question.id) or (False, None))[0],
            "review_reason": (review.get(question.id) or (False, None))[1],
        }

    from app.extraction.paper import context_addresses

    context = context_addresses(rows)
    read_total = _scanned_effective_total(rows, context)
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
        #: A real fact from the classify pass itself (see classified_question_ids above),
        #: not inferred from whether any question happens to carry a tier -- an abstain is
        #: still a verdict. This is what lets the paper screen tell "never classified" apart
        #: from "classified, and every question abstained" when someone reopens the paper
        #: after leaving mid-flow, without re-running anything to find out.
        "classified": any(
            r.question_id in classified_question_ids for r in rows if r.question_id
        ),
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
        #: What the paper's own cover/instructions page states about itself, read once at
        #: scan time and stored on the assessment rather than only ever returned by that
        #: one POST /scan response -- otherwise reopening a paper mid-flow had no way to
        #: show these again short of re-reading the pages.
        "declared": {
            "questions": (assessment.declared or {}).get("question_count"),
            "sections": (assessment.declared or {}).get("sections"),
            "total_marks": float(declared_total) if declared_total is not None else None,
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
def _section_number(code: str) -> str | None:
    """'X.MATH.STATS.S13_2' -> '13.2'. None when the code carries no section."""
    return section_number(code)


#: Fixed CBSE Class X Social Science paper convention, not something any one paper's cover
#: page needs to declare and not inferred from anything: Section A is always History,
#: Section B is always Geography, Section C is always Political Science ("Democratic
#: Politics" in the syllabus), Section D is always Economics. Confirmed against
#: X_HISTORY/X_GEOGRAPHY/X_POLITICAL_SCIENCE/X_ECONOMICS in app.curriculum, all of which
#: share group_code "X.SST" -- this mapping only ever applies within that one group and is
#: never inferred for any other subject group.
_SST_SECTION_SUBJECT = {"A": "X.HIST", "B": "X.GEO", "C": "X.POL", "D": "X.ECO"}

#: see app.mapping.topic_node -- the helpers live there now so classify and review can
#: write a topic the same way map does.
_BOOK_MAP_SUBJECTS = BOOK_MAP_SUBJECTS
_book_map_topic_label = book_map_topic_label
_book_map_topic_node = topic_node


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
    school: School = Depends(require_paper_scope),
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


#: how many of a paper's questions must be read before its subject is judged at all,
#: and how lopsided the tally must be before the paper is refused as another subject's
SUBJECT_CHECK_MIN_QUESTIONS = 5
SUBJECT_CHECK_OTHER_SHARE = 0.6
SUBJECT_CHECK_OWN_SHARE = 0.35


def check_paper_subject(db: Session, assessment: Assessment, extract) -> str | None:
    """Is this the subject's own paper? The reason to refuse it if not, else None.

    Every question stem is matched against every book this deployment has loaded, and
    the subject each stem lands in is tallied. A paper whose questions overwhelmingly
    land in another subject's book -- while hardly any land in this one -- is that
    subject's paper, uploaded under the wrong test, and forcing it onto this subject's
    chapters would file every mark under the wrong topic. It is refused before anything
    is stored, so nothing has to be undone.

    Decided only when there is something to decide with: at least a handful of readable
    questions, this subject's own book loaded, and at least one other subject's book to
    tell it apart from. A deployment with one book cannot tell subjects apart by content
    and does not pretend to.
    """
    from app.curriculum import CURRICULA
    from app.ingest.probe import LexicalIndex, content_chunks, locate, retrieval_query_text

    def group_of(subject_code: str) -> str:
        c = CURRICULA.get(subject_code)
        return c.group_code if c else subject_code

    def label_of(group: str) -> str:
        for c in CURRICULA.values():
            if c.group_code == group:
                return c.group_label or c.subject_label
        return group

    expected = group_of(assessment.subject_code)
    stems = [
        q.stem_text for q in extract.questions
        if not q.is_context and len((q.stem_text or "").split()) >= 4
    ]
    if len(stems) < SUBJECT_CHECK_MIN_QUESTIONS:
        return None
    chunks = list(db.scalars(
        select(BookChunk).where(BookChunk.curriculum_version == assessment.curriculum_version)
    ))
    groups_loaded = {group_of(c.subject_code) for c in chunks}
    if expected not in groups_loaded or len(groups_loaded) < 2:
        return None
    pool = content_chunks(chunks)
    group_by_chunk = {c.id: group_of(c.subject_code) for c in pool}
    index = LexicalIndex(pool)
    tally: dict[str, int] = {}
    judged = 0
    for stem in stems:
        verdict = locate(retrieval_query_text(stem), [index], depth=6, evidence_passages=1)
        if not verdict.evidence:
            continue
        group = group_by_chunk.get(verdict.evidence[0].chunk_id)
        if group is None:
            continue
        tally[group] = tally.get(group, 0) + 1
        judged += 1
    if judged < SUBJECT_CHECK_MIN_QUESTIONS:
        return None
    leader, count = max(tally.items(), key=lambda kv: kv[1])
    own = tally.get(expected, 0)
    lopsided = count / judged >= SUBJECT_CHECK_OTHER_SHARE and own / judged <= SUBJECT_CHECK_OWN_SHARE
    if leader != expected and lopsided:
        return (
            f"This looks like a {label_of(leader)} paper, not {label_of(expected)}: "
            f"{count} of {judged} questions match the {label_of(leader)} book and only "
            f"{own} match {label_of(expected)}. Nothing was extracted or mapped. Upload it "
            f"under {label_of(leader)}, or check that the right file was chosen."
        )
    return None


def _fill_missing_marks(rows: list, context: set[str]) -> list[str]:
    """Give every question row whose mark label was not read the mark its own paper
    implies, and return the addresses filled. Each fill is recorded on the row
    (edited_by "auto").

    In order: the other half of an internal choice ("attempt either (a) or (b)") is
    worth the same, so a half whose marks were all read prices the half whose were
    not, spread evenly over its unmarked parts; else the marks of a sibling sub-part
    of the same question; else the most common mark among the rows of its section;
    else 1.
    """
    from collections import Counter

    filled: list[str] = []
    by_question: dict[tuple[str | None, str], list] = {}
    by_section: dict[str | None, Counter] = {}
    for r in rows:
        if r.address in context:
            continue
        by_question.setdefault((r.section, r.question_no), []).append(r)
        if r.max_marks is not None:
            by_section.setdefault(r.section, Counter())[float(r.max_marks)] += 1

    def fill(r, marks: float) -> None:
        r.max_marks = marks
        r.edited_at = datetime.now(UTC).isoformat()
        r.edited_by = "auto"
        filled.append(r.address)

    # 1. The halves of an internal choice are worth the same.
    for group in by_question.values():
        halves: dict[str | None, list] = {}
        for r in group:
            halves.setdefault(r.choice_alt, []).append(r)
        if len(halves) < 2:
            continue
        priced = [
            sum(float(r.max_marks) for r in half)
            for half in halves.values() if all(r.max_marks is not None for r in half)
        ]
        if not priced:
            continue
        worth = Counter(priced).most_common(1)[0][0]
        for half in halves.values():
            unmarked = [r for r in half if r.max_marks is None]
            if not unmarked:
                continue
            left = worth - sum(float(r.max_marks) for r in half if r.max_marks is not None)
            if left <= 0:
                continue
            each = round(left / len(unmarked), 2)
            for r in unmarked:
                fill(r, each)

    # 2. A sibling sub-part's marks; 3. the section's usual mark; 4. one.
    for r in rows:
        if r.address in context or r.max_marks is not None:
            continue
        siblings = [
            float(s.max_marks) for s in by_question[(r.section, r.question_no)]
            if s.max_marks is not None
        ]
        if siblings:
            guess = Counter(siblings).most_common(1)[0][0]
        elif by_section.get(r.section):
            guess = by_section[r.section].most_common(1)[0][0]
        else:
            guess = 1.0
        fill(r, guess)
    return filled


def auto_confirm_scan(db: Session, assessment: Assessment) -> dict:
    """Confirm the extraction without a person, filling what a person would have typed.

    A row whose mark label was not read gets the mark its own paper implies: the marks of
    a sibling sub-part of the same question, else the most common mark among the rows of
    its section, else 1. Each fill is recorded on the row (edited_by "auto"). The paper's
    declared total is compared and the difference reported, never used to refuse -- the
    marks that were read still teach more than a paper nobody could get past this step.
    """
    from app.extraction.paper import context_addresses

    rows = list(db.scalars(
        select(ScannedQuestion).where(ScannedQuestion.assessment_id == assessment.id)
    ))
    context = context_addresses(rows)
    filled = _fill_missing_marks(rows, context)

    read_total = _scanned_effective_total(rows, set(context))
    declared_total = (assessment.declared or {}).get("total_marks")
    if declared_total is None and assessment.total_marks is not None:
        declared_total = float(assessment.total_marks)
    assessment.scan_confirmed_at = datetime.now(UTC).isoformat()
    assessment.scan_confirmed_by = "auto"
    db.commit()
    return {
        "confirmed_by": "auto",
        "questions": len(rows),
        "marks_filled": filled,
        "total_marks": read_total,
        "declared_total": declared_total,
        "total_difference": (
            round(float(declared_total) - read_total, 2) if declared_total is not None else None
        ),
    }


def _queue_auto_pipeline(db: Session, school_id: str, assessment_id: str) -> dict:
    """Create the map and classify job rows up front so the screen can follow them.

    auto_pipeline_dedupe: while a map or classify job is already pending for this paper
    (a re-scan, a second tab, a retried upload), no second pair is queued -- the pending
    jobs are returned with ``already_queued`` and the caller starts nothing. Two pairs
    racing on one paper each spent a full set of model calls and appended a second set
    of placements."""
    if get_settings().auto_pipeline_dedupe:
        live_map = running_job(db, assessment_id, "map")
        live_place = running_job(db, assessment_id, "place")
        if live_map is not None or live_place is not None:
            return {
                "map_job_id": live_map.id if live_map else None,
                "place_job_id": live_place.id if live_place else None,
                "already_queued": True,
            }
    map_job = PlacementJob(school_id=school_id, assessment_id=assessment_id, kind="map")
    place_job = PlacementJob(school_id=school_id, assessment_id=assessment_id, kind="place")
    db.add_all([map_job, place_job])
    db.commit()
    return {"map_job_id": map_job.id, "place_job_id": place_job.id}


def _run_auto_pipeline(assessment_id: str, jobs: dict) -> None:
    """Scan is read: confirm it, map it, classify it, with nobody in the loop. Every
    stage records its own job row, so a browser that comes back can watch it, and a
    stage that fails leaves the next one failed with the reason rather than pending
    forever."""
    from app.db import SessionLocal

    def fail_place(reason: str) -> None:
        session = SessionLocal()
        try:
            job = session.get(PlacementJob, jobs["place_job_id"])
            if job is not None and job.status == "pending":
                job.status, job.error_status, job.error_detail = "failed", 409, reason
                job.finished_at = datetime.now(UTC)
                session.commit()
        finally:
            session.close()

    try:
        db = SessionLocal()
        try:
            assessment = db.get(Assessment, assessment_id)
            if assessment is None:
                fail_place("the paper was removed before it could be processed")
                return
            auto_confirm_scan(db, assessment)
        finally:
            db.close()
        _run_map_job(jobs["map_job_id"])
        db = SessionLocal()
        try:
            map_job = db.get(PlacementJob, jobs["map_job_id"])
            ok = map_job is not None and map_job.status == "succeeded"
            detail = (map_job.error_detail if map_job is not None else None) or "mapping did not finish"
        finally:
            db.close()
        if not ok:
            fail_place(f"not classified because mapping failed: {detail}")
            return
        from app.api.placement import _run_placement_job

        _run_placement_job(jobs["place_job_id"])
    except Exception as exc:  # noqa: BLE001 -- the scan itself succeeded; this must never undo that
        logger.exception("auto pipeline failed for assessment %s", assessment_id)
        # the cause on the job row itself: the screen is where it is looked for, and a
        # server log is not something a school has
        fail_place(f"the automatic pipeline hit an error: {type(exc).__name__}: {exc}"[:900])


@router.post("/{assessment_id}/duplicates/decision")
def decide_duplicate(
    assessment_id: str,
    body: DuplicateDecisionIn,
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
    school: School = Depends(require_paper_scope),
    db: Session = Depends(get_session),
) -> dict:
    """The teacher's answer when an upload matched a paper the school already has
    (duplicate_upload_check). Nothing is decided for them, and nothing is deleted:

    * ``open_existing`` -- they open the matched paper instead. The new upload is left as
      it is (unmapped; they can delete it), and the response names the paper to open.
    * ``keep_new`` -- it really is a new paper. The automatic pipeline the match held
      back now runs, exactly as it would have after the scan.
    """
    a = _get_assessment(db, school, assessment_id)
    check = a.duplicate_check or {}
    candidates = check.get("candidates") or []
    if not candidates:
        raise HTTPException(409, "no duplicate match is waiting for a decision on this paper")
    earlier = check.get("decision")
    if earlier:
        # Already answered (a double-click, a second tab, a retry after a timeout): say
        # so and start nothing -- a second keep_new must not queue a second pipeline.
        return {
            "assessment_id": a.id, "already_decided": True, "decision": earlier,
            **({"open": earlier.get("assessment_id")} if earlier.get("choice") == "open_existing"
               else {}),
        }
    if body.choice == "open_existing" and body.assessment_id not in {
        c["assessment_id"] for c in candidates
    }:
        raise HTTPException(422, "open_existing needs the id of one of the matched papers")
    a.duplicate_check = {**check, "decision": {
        "choice": body.choice,
        "assessment_id": body.assessment_id if body.choice == "open_existing" else None,
        "at": datetime.now(UTC).isoformat(),
    }}
    db.commit()
    if body.choice == "open_existing":
        return {"assessment_id": a.id, "open": body.assessment_id}

    auto = None
    staged = db.scalar(
        select(ScannedQuestion.id).where(ScannedQuestion.assessment_id == a.id).limit(1)
    )
    if get_settings().auto_pipeline and staged is not None:
        auto = _queue_auto_pipeline(db, school.id, a.id)
        if not auto.get("already_queued"):
            if background_tasks is not None:
                background_tasks.add_task(_run_auto_pipeline, a.id, auto)
            else:
                _run_auto_pipeline(a.id, auto)
    return {"assessment_id": a.id, "auto": auto}


@router.post("/{assessment_id}/scan/confirm")
def confirm_scan(
    assessment_id: str,
    body: ConfirmIn,
    school: School = Depends(require_paper_scope),
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
    # Zero-touch: nobody is going to type the missing marks in, and this button is only
    # ever pressed in the moments before the server's own confirmation lands (or after
    # it failed). It then does exactly what the automatic confirmation does -- fills the
    # marks the paper implies, reports the total rather than refusing over it -- so a
    # teacher who presses it is never told to do a job that is not theirs.
    filled: list[str] = []
    if get_settings().auto_pipeline:
        filled = _fill_missing_marks(rows, set(context))
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

    read_total = _scanned_effective_total(rows, set(context))
    declared_total = (assessment.declared or {}).get("total_marks")
    if declared_total is None and assessment.total_marks is not None:
        declared_total = float(assessment.total_marks)
    if (
        declared_total is not None and abs(float(declared_total) - read_total) > 0.01
        and not get_settings().auto_pipeline
    ):
        short = float(declared_total) - read_total
        raise HTTPException(
            422,
            f"the paper is worth {float(declared_total):g} marks and the questions here "
            f"add up to {read_total:g}"
            + (
                f", so {short:g} are missing. Two usual causes: a question whose "
                "sub-parts are worth different marks (open the ones with parts (i), "
                "(ii), (iii) and check each part carries its own marks), or a group of "
                "sub-parts that was split across a page break in the original scan (the "
                "later parts would be missing from this list entirely, not just missing "
                "their marks -- check the paper for a question whose lettered parts stop "
                "partway through)."
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
        "marks_filled": filled,
        "total_marks": read_total,
        "declared_total": declared_total,
        "total_difference": (
            round(float(declared_total) - read_total, 2) if declared_total is not None else None
        ),
        "next": f"POST /assessments/{assessment.id}/map",
    }


def _ensure_family(
    db: Session, chapter: TaxonomyNode, section: str | None, heading: str | None,
    families: dict[str, list[TaxonomyNode]], sections_of: dict[str, set[str]],
    subject_codes: list[str],
) -> TaxonomyNode:
    """The concept family for ``section`` of ``chapter``, created from the book's own
    heading when none exists -- the same one-family-per-section-heading shape the book
    screen proposes, made without waiting for anyone to press its button. Recorded as
    claiming its section so every later paper resolves to it directly."""
    from app.mapping.auto_resolve import record_family_section

    tail = f"S{section.replace('.', '_')}" if section else "CHAPTER"
    code = f"{chapter.code}.CF.AUTO_{tail}"
    label = (heading or (section and f"Section {section}") or chapter.label).strip()
    node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
    if node is None:
        node = TaxonomyNode(
            kind="concept_family", code=code, label=label, parent_id=chapter.id,
            path=code, curriculum_version=chapter.curriculum_version,
        )
        db.add(node)
        db.flush()
    if node not in families.setdefault(chapter.id, []):
        families[chapter.id].append(node)
    if section:
        proposals = list(db.scalars(
            select(ConceptFamilyProposal).where(
                ConceptFamilyProposal.subject_code.in_(subject_codes),
                ConceptFamilyProposal.code == node.code,
            )
        ))
        record_family_section(
            db, winner=node, chapter=chapter, section=section, subject_codes=subject_codes,
            proposals=proposals, model="auto", source="auto_pipeline",
            rationale=f"created from the book's own heading {label!r} while mapping",
        )
        sections_of.setdefault(node.code, set()).add(section)
    return node


def _map_inputs(db: Session, assessment: Assessment) -> tuple[list, list]:
    """What map needs before it can start: a confirmed scan, staged rows, a loaded book.
    Checked inline when the job is queued (so the person who clicked learns why in the
    same second) and again by the job itself."""
    from app.curriculum import group_subjects

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
        select(BookChunk).where(BookChunk.subject_code.in_(group_subjects(assessment.subject_code)))
    ))
    if not chunks:
        raise HTTPException(
            422,
            f"no book is loaded for {assessment.subject_code}, so there is nothing to map "
            f"against. Upload the chapters first.",
        )
    return staged, chunks


@router.post("/{assessment_id}/map", status_code=status.HTTP_202_ACCEPTED)
def map_paper_to_book(
    assessment_id: str,
    background_tasks: BackgroundTasks,
    school: School = Depends(require_paper_scope),
    db: Session = Depends(get_session),
) -> JSONResponse:
    """Queue the map step (see _map_paper) and answer with a job to poll.

    Map used to run inside this request. With the topic judge reading every question
    against its chapter's sections it is now a model call per question, and a request
    the browser must keep open for minutes is lost the moment the tab is closed or the
    reverse proxy times out -- the same reason /place and /scan already run as jobs.
    Poll GET .../map/jobs/{job_id}; the pre-checks still fail inline.
    """
    assessment = _get_assessment(db, school, assessment_id)
    _map_inputs(db, assessment)
    # One map job per paper at a time. A second one queued while the first still runs
    # (a double click, or the browser's resume-on-return firing beside a fresh click)
    # promoted the same staged rows in two transactions and deadlocked Postgres on
    # scanned_question. The caller gets the running job to poll, not a new one.
    running = running_job(db, assessment.id, "map")
    if running is not None:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "job_id": running.id, "status": "pending", "already_running": True,
                "next": f"Poll GET /assessments/{assessment.id}/map/jobs/{running.id} for the result.",
            },
        )
    job = PlacementJob(school_id=school.id, assessment_id=assessment.id, kind="map")
    db.add(job)
    db.commit()
    background_tasks.add_task(_run_map_job, job.id)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "job_id": job.id, "status": "pending",
            "next": f"Poll GET /assessments/{assessment.id}/map/jobs/{job.id} for the result.",
        },
    )


#: A map/classify job still "pending" this long after it was queued did not survive its
#: process (a redeploy mid-run): it is failed rather than left blocking every later run.
PLACEMENT_JOB_STALE_AFTER = timedelta(minutes=45)
#: a classify job served by the Batches API (app.llm_batch) can legitimately run for
#: hours; its stale window is the batch's own deadline plus a margin
PLACEMENT_JOB_STALE_AFTER_BATCHED = timedelta(hours=4)


def _stale_after() -> timedelta:
    return PLACEMENT_JOB_STALE_AFTER_BATCHED if get_settings().batch_classify else PLACEMENT_JOB_STALE_AFTER


def running_job(db: Session, assessment_id: str, kind: str) -> PlacementJob | None:
    """The pending job of this kind on this paper, or None. A stale one is marked failed
    on the way, so a crashed run cannot hold a paper hostage."""
    pending = list(db.scalars(
        select(PlacementJob).where(
            PlacementJob.assessment_id == assessment_id, PlacementJob.kind == kind,
            PlacementJob.status == "pending",
        ).order_by(PlacementJob.created_at.desc())
    ))
    live: PlacementJob | None = None
    for job in pending:
        created = job.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created is not None and datetime.now(UTC) - created > _stale_after():
            job.status = "failed"
            job.error_status = 500
            job.error_detail = "the job did not finish; the service restarted while it ran"
            continue
        if live is None:
            live = job
    if pending:
        db.commit()
    return live


@router.get("/{assessment_id}/map/jobs/{job_id}")
def get_map_job(
    assessment_id: str,
    job_id: str,
    school: School = Depends(require_paper_scope),
    db: Session = Depends(get_session),
) -> dict:
    """Poll for the result of a queued map run. A failed job carries the status code and
    detail the synchronous handler used to raise, not a bare 'failed'."""
    job = db.get(PlacementJob, job_id)
    if (
        job is None or job.kind != "map" or job.assessment_id != assessment_id
        or job.school_id != school.id
    ):
        raise HTTPException(404, f"no job {job_id!r} for this paper")
    if job.status == "failed":
        raise HTTPException(job.error_status or 500, job.error_detail or "the job failed")
    if job.status != "succeeded":
        return {
            "job_id": job.id, "status": job.status,
            "progress_done": job.progress_done, "progress_total": job.progress_total,
        }
    return {
        "job_id": job.id, "status": "succeeded",
        "progress_done": job.progress_done, "progress_total": job.progress_total,
        **(job.result or {}),
    }


def _run_map_job(job_id: str) -> None:
    """The map step, after the request that queued it has returned. Never raises: the
    job row is the only place a failure can be seen once that request is gone."""
    from datetime import UTC, datetime

    from app.db import SessionLocal

    def finish(status_value: str, *, result: dict | None = None,
               error_status: int | None = None, error_detail: str | None = None) -> None:
        session = SessionLocal()
        try:
            job = session.get(PlacementJob, job_id)
            if job is not None:
                job.status, job.result = status_value, result
                job.error_status, job.error_detail = error_status, error_detail
                job.finished_at = datetime.now(UTC)
                session.commit()
        finally:
            session.close()

    def progress(done: int, total: int) -> None:
        try:
            session = SessionLocal()
            try:
                job = session.get(PlacementJob, job_id)
                if job is not None:
                    job.progress_done, job.progress_total = done, total
                    session.commit()
            finally:
                session.close()
        except Exception:  # noqa: BLE001 -- a progress write must never sink the run
            pass

    db = SessionLocal()
    try:
        job = db.get(PlacementJob, job_id)
        if job is None:
            return
        assessment = db.get(Assessment, job.assessment_id)
        if assessment is None:
            finish("failed", error_status=404, error_detail="the paper this job belonged to was removed")
            return
        result = _map_paper(db, assessment, on_progress=progress)
    except HTTPException as exc:
        db.rollback()
        finish("failed", error_status=exc.status_code, error_detail=str(exc.detail))
        return
    except Exception as exc:  # noqa: BLE001 -- see docstring
        db.rollback()
        finish("failed", error_status=500, error_detail=f"{type(exc).__name__}: {exc}")
        return
    finally:
        db.close()
    finish("succeeded", result=result)


def _no_cap(section):
    return section


def _section_cap(chapter: TaxonomyNode):
    """The collapse for ``chapter``'s subject (topic_depth_cap), or the identity."""
    from app.curriculum.depth import collapse_section, is_capped

    if not is_capped(chapter.code):
        return _no_cap
    return lambda section: collapse_section(None, section, chapter_code=chapter.code)


def capped_pick(pick, cap, headings):
    from app.classify.topic import capped

    return capped(pick, cap, headings)


def _write_topic(db: Session, question_id: str, chapter: TaxonomyNode, topic: TaxonomyNode,
                 section, pick) -> None:
    """The map step's topic: ``topic`` (the node for ``section``) at weight 1.0, and the
    judge's other sections at SECONDARY_WEIGHT -- through set_question_topic, the one
    writer every step uses, so earlier machine rows are replaced the same way everywhere.
    A secondary rides along only when the pick's primary is the section written, never
    with a fallback the judge did not make."""
    secondaries = (
        pick.secondaries if pick is not None and pick.section is not None and pick.section == section
        else ()
    )
    set_question_topic(
        db, question_id, chapter, section, topic.label, source="retrieval",
        secondaries=secondaries, node=topic,
    )

def _map_review(settings, pick, deferred: bool, *, family_unsettled: bool, old: bool) -> dict:
    """needs_review and review_reason for a map-step placement. review_flag_rule: only
    the six reasons (app.classify.review_rule) the map step has inputs for -- the family,
    and the topic pick unless the classify job queued behind this map decides the topic
    (a provisional topic is not a doubt). There is no chapter judge here. Off: ``old``."""
    if not settings.review_flag_rule:
        return {"needs_review": old}
    from app.classify.review_rule import ReviewInputs, reason_code, review_reasons

    topic = pick is not None and not deferred
    reasons = review_reasons(ReviewInputs(
        family_unsettled=family_unsettled,
        topic_section=pick.section if topic else None,
        retrieval_section=pick.retrieval_section if topic else None,
        topic_verified=pick.verified if topic else None,
        topic_source=pick.source if topic else None,
    ))
    return {"needs_review": bool(reasons), "review_reason": reason_code(reasons)}


def _map_paper(db: Session, assessment: Assessment, on_progress=None) -> dict:
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
    from app.curriculum import group_subjects
    from app.extraction.paper import context_addresses
    from app.ingest.probe import (
        LexicalIndex,
        SemanticIndex,
        content_chunks,
        locate,
        retrieval_query_text,
    )
    from app.mapping.auto_resolve import resolve_blocked_family
    from app.mapping.family import choose_family

    settings = get_settings()
    staged, chunks = _map_inputs(db, assessment)
    book_subject_codes = group_subjects(assessment.subject_code)
    is_book_map_subject = bool(_BOOK_MAP_SUBJECTS.intersection(book_subject_codes))

    # Exercise-bucket chunks (bucket='E') never carry a section_number -- see
    # import_book_map.py, which loads them with section_number=None because an
    # end-of-chapter exercise references the whole chapter, not one section -- and they
    # share only surface vocabulary with a question, not what the question is actually
    # about. Left in the retrieval pool they can outscore the real teaching-text passage
    # (an "Exercise Q8" chunk beating the actual "Women and Print" section on shared
    # words) and, because they carry no section, that win also produces a topicless
    # result even when real teaching text elsewhere in the chapter would have matched.
    # Excluded here, from the pool that DECIDES chapter/section/topic, not from the book
    # data itself -- chunks stays the full set for _book_map_topic_label below. A bare
    # pie-chart-legend fragment ("Gujarat", "9%", one word lifted from a chart caption)
    # fails the same way an exercise chunk does -- it shares a word with the question, not
    # what the question is about, and its short length makes TF-IDF's own normalization
    # score it *higher* than the real teaching-text passage on the same topic. See
    # content_chunks.
    retrieval_chunks = content_chunks(chunks)
    indexes: list = [LexicalIndex(retrieval_chunks)]
    mode = "lexical"
    if any(c.embedding for c in retrieval_chunks) and settings.jina_api_key:
        from app.ingest.jina import JinaEmbedder

        indexes.append(SemanticIndex(retrieval_chunks, JinaEmbedder(
            settings.jina_api_key, model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )))
        mode = "hybrid"

    # X.SST papers group four books (History/Geography/Political Science/Economics) under
    # one subject_code, so retrieval above searches all four for every question -- that is
    # how a History question can land in the Political Science chapter "Power-sharing" on
    # nothing but shared vocabulary. Each staged question already carries the section
    # letter the paper itself printed (ScannedQuestion.section, read off the paper's own
    # "SECTION A" headers -- see app.extraction.paper_vision), and CBSE's Class X SST
    # section-to-subject layout is fixed board convention (_SST_SECTION_SUBJECT above), so
    # when both are known retrieval for that one question is narrowed to just its own
    # subject's chunks instead of the whole group. Built lazily, one index per subject
    # actually needed, and cached because chunks/indexes are pure in-memory objects here.
    from app.curriculum import CURRICULA

    subject_curriculum = CURRICULA.get(assessment.subject_code)
    is_sst_group = (
        subject_curriculum.group_code if subject_curriculum else assessment.subject_code
    ) == "X.SST"
    _subject_index_cache: dict[str, tuple[list, str]] = {}

    def _indexes_for_subject(subject_code: str) -> tuple[list, str] | None:
        cached = _subject_index_cache.get(subject_code)
        if cached is not None:
            return cached
        sub_chunks = [c for c in chunks if c.subject_code == subject_code]
        if not sub_chunks:
            return None
        # Same exclusion as the whole-group indexes above, scoped to this one subject.
        sub_retrieval_chunks = content_chunks(sub_chunks)
        sub_indexes: list = [LexicalIndex(sub_retrieval_chunks)]
        sub_mode = "lexical"
        if any(c.embedding for c in sub_retrieval_chunks) and settings.jina_api_key:
            from app.ingest.jina import JinaEmbedder

            sub_indexes.append(SemanticIndex(sub_retrieval_chunks, JinaEmbedder(
                settings.jina_api_key, model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
            )))
            sub_mode = "hybrid"
        _subject_index_cache[subject_code] = (sub_indexes, sub_mode)
        return _subject_index_cache[subject_code]

    # sst_unified_scope: one rule for map and place (app.classify.question_scope). The
    # retrieval pool for a row is the chunks of the chapters its scope allows, one index
    # per distinct scope, built lazily like the per-subject indexes above.
    paper_scope = None
    if settings.sst_unified_scope:
        from app.classify.question_scope import paper_scope_for

        paper_scope = paper_scope_for(db, assessment, book_subject_codes)
    chapter_id_of_code = {
        n.code: n.id for n in db.scalars(select(TaxonomyNode).where(TaxonomyNode.kind == "chapter"))
    }
    _scope_index_cache: dict[frozenset[str], tuple[list, str] | None] = {}

    def _indexes_for_chapters(chapter_codes: frozenset[str]) -> tuple[list, str] | None:
        if chapter_codes in _scope_index_cache:
            return _scope_index_cache[chapter_codes]
        ids = {chapter_id_of_code[c] for c in chapter_codes if c in chapter_id_of_code}
        sub_retrieval_chunks = content_chunks([c for c in chunks if c.node_id in ids])
        built: tuple[list, str] | None = None
        if sub_retrieval_chunks:
            sub_indexes: list = [LexicalIndex(sub_retrieval_chunks)]
            sub_mode = "lexical"
            if any(c.embedding for c in sub_retrieval_chunks) and settings.jina_api_key:
                from app.ingest.jina import JinaEmbedder

                sub_indexes.append(SemanticIndex(sub_retrieval_chunks, JinaEmbedder(
                    settings.jina_api_key, model=settings.embedding_model,
                    dimensions=settings.embedding_dimensions,
                )))
                sub_mode = "hybrid"
            built = (sub_indexes, sub_mode)
        _scope_index_cache[chapter_codes] = built
        return built

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
            ConceptFamilyProposal.subject_code.in_(book_subject_codes)
        ))
    }
    # book_map_only_subtopics: a family's sections are the union over its rows;
    # topic_depth_cap: cut to major topics, and families that are not one are never
    # picked for a new placement (app.mapping.family_sections)
    family_table = None
    if settings.book_map_only_subtopics or settings.topic_depth_cap:
        from app.mapping import family_sections

        family_table = family_sections.build(
            db.scalars(select(ConceptFamilyProposal).where(
                ConceptFamilyProposal.subject_code.in_(book_subject_codes)
            )),
            union=settings.book_map_only_subtopics,
            chapter_code_of={
                f.code: nodes[f.parent_id].code
                for fams in families.values() for f in fams if f.parent_id in nodes
            } if settings.topic_depth_cap else None,
        )
        sections_of = family_table.sections_of

    context = context_addresses(staged)
    # The topic within the chapter is decided by the closed-set topic judge (see
    # app.classify.topic) rather than by which passage happened to score highest: the
    # chapter's own section headings, every one of them, with the judge choosing among
    # them and retrieval within the chapter as the check. Without a classifier key the
    # judge cannot be asked and the retrieval section stands, as it always did.
    from app.classify.topic import TopicJudge, choose_topic, topic_lexical_index

    # Once, not twice. The classify step that follows a zero-touch upload decides the
    # topic again from scratch (placement.py's topic_picks), so a map step that runs
    # the whole-chapter judge too pays for every question's reads twice and keeps the
    # second answer. When a classify job is already queued behind this map, the judge
    # is left to it and retrieval's section stands in the meantime; a map run on its
    # own (the manual button, no classify queued) still judges, as before.
    deferred_to_classify = running_job(db, assessment.id, "place") is not None
    topic_judge = None
    if settings.anthropic_api_key and not deferred_to_classify:
        try:
            topic_judge = TopicJudge(
                settings.anthropic_api_key, settings.model_classifier,
                effort=settings.model_effort, passage_chars=settings.classifier_passage_chars,
                **({"major_only": True} if settings.topic_major_only_document else {}),
            )
        except Exception:  # noqa: BLE001 -- the retrieval section then stands
            topic_judge = None
    topic_embedder = None
    if settings.jina_api_key and any(c.embedding for c in retrieval_chunks):
        from app.ingest.jina import JinaEmbedder

        topic_embedder = JinaEmbedder(
            settings.jina_api_key, model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    headings_of: dict[str, dict[str, str]] = {}
    topic_index = topic_lexical_index(retrieval_chunks)
    passage_of: dict[tuple[str | None, str], str] = {
        (r.section, r.question_no): (r.stem_text or "").strip()
        for r in staged if r.address in context and (r.stem_text or "").strip()
    }

    def decide_topic(row, chapter: TaxonomyNode, section: str | None):
        """The section this question tests within ``chapter``, and its heading. A
        sub-part of a source-based question is judged together with its passage.
        With the judge deferred to the classify job behind this map, the section is
        provisional -- retrieval's, kept until classify decides -- and says so, rather
        than reading as a disagreement a person should look at."""
        if chapter.id not in headings_of:
            headings_of[chapter.id] = topic_headings(chunks, chapter, nodes)
        text = row.stem_text or ""
        passage = passage_of.get((row.section, row.question_no)) if row.sub_part else None
        if passage and passage not in text:
            text = f"{passage}\n\nQUESTION ON THE PASSAGE ABOVE:\n{text}"
        pick = choose_topic(
            text, chapter.id, chapter.label, retrieval_chunks, headings_of[chapter.id],
            topic_judge, fallback_section=section, embedder=topic_embedder,
            evidence_passages=settings.classifier_evidence_passages,
            passage_chars=settings.classifier_passage_chars,
            lexical_index=topic_index,
            card_mode=settings.topic_card_mode,
            **({"major": view} if (view := major_view(chapter)) is not None else {}),
        )
        if deferred_to_classify:
            import dataclasses

            pick = dataclasses.replace(
                pick, agreed=True,
                rationale="provisional: the classify step queued behind this map decides the topic",
            )
        return pick
    # A case study's sub-parts all read the same source passage, which is not in the book
    # at all (an unseen extract, invented for this paper) -- so raw retrieval can easily
    # find real evidence for one sub-part (a shared word with some unrelated chapter) and
    # none for another, even though a person would place every sub-part of the same
    # question identically. Rather than block the unlucky sub-part outright -- which
    # would leave it with no Question row at all, invisible to marks entry and every
    # report downstream, unlike the standalone skill-anchored path the judge in /place
    # handles -- a sub-part with no evidence of its own borrows whichever chapter/family a
    # sibling sub-part of the *same* case study already earned, flagged for review rather
    # than force-fit with confidence. Only a real question. sub_part within a case study
    # group qualifies; an ordinary standalone question with no chapter match is still
    # genuinely unplaceable and stays blocked.
    case_study_question_nos = {r.question_no for r in staged if r.address in context}
    group_placement: dict[str, dict] = {}
    deferred: list = []
    mapped, blocked, context_kept, with_topic = 0, [], 0, 0
    topic_written: list[str] = []
    for done, row in enumerate(staged, start=1):
        if on_progress is not None:
            on_progress(done, len(staged))
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

        row_indexes, row_mode = indexes, mode
        if paper_scope is not None:
            decision = paper_scope.for_section(row.section)
            if decision.chapter_codes is not None:
                scoped = _indexes_for_chapters(decision.chapter_codes)
                if scoped is not None:
                    row_indexes, row_mode = scoped
        elif is_sst_group and row.section:
            target_subject = _SST_SECTION_SUBJECT.get(row.section.strip().upper())
            if target_subject and target_subject in book_subject_codes:
                scoped = _indexes_for_subject(target_subject)
                if scoped is not None:
                    row_indexes, row_mode = scoped

        verdict = locate(retrieval_query_text(row.stem_text), row_indexes)
        chapter = _chapter_of(verdict.node_id, nodes)
        if chapter is None:
            if row.question_no in case_study_question_nos:
                # A sibling sub-part of this same case study may still rescue it -- later
                # in this loop, or already have, since sub-parts are read in order. Held
                # back rather than blocked immediately.
                deferred.append(row)
                continue
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
        # the retrieval landed on. Both are the book's, never a guess -- and both are only
        # the fallback: the topic judge reads the question against every section of the
        # chapter and its answer, when it gives one, is the section.
        section = verdict.section or (_section_number(landed.code) if landed else None)
        # topic_depth_cap: every section decided here is cut to the subject's depth
        # ("4.1.2" -> "4.1", a box to its parent); the judge's own answer is kept as
        # curriculum_section_fine on the placement.
        cap = _section_cap(chapter)
        fine_section = section
        section = cap(section)
        pick = decide_topic(row, chapter, section)
        if cap is not _no_cap:
            pick = capped_pick(pick, cap, headings_of.get(chapter.id))
            fine_section = pick.fine_section or pick.section or fine_section
        if pick.section:
            section = pick.section
        topic = None
        if section and pick.section == section and pick.heading and pick.heading != section:
            topic = _book_map_topic_node(db, chapter, section, pick.heading)
        if topic is None and section and is_book_map_subject:
            book_map_label = _book_map_topic_label(chunks, chapter.id, section)
            if book_map_label is None and cap is not _no_cap:
                # a major topic with no text of its own ("4.1 Conventional Sources of
                # Energy") still has the book map's printed heading
                from app.curriculum.book_map import heading_label, unit_by_number

                unit = unit_by_number(chapter.code).get(section)
                book_map_label = heading_label(section, unit.title) if unit else None
            if book_map_label:
                topic = _book_map_topic_node(db, chapter, section, book_map_label)
        if topic is None and section and not (
            settings.book_map_only_subtopics and is_book_map_subject
        ):
            # book_map_only_subtopics: an ingest-created node of a book-map subject is a
            # different numbering, never a fallback topic
            topic = topics.get((chapter.id, section))

        # The family is what every trend groups by and it is deliberately required, so a
        # question whose family cannot be settled is left staged rather than placed under
        # a guess. What changed is that the choice can now actually be made: the section
        # comes from the winning passages, and a family created from the book records the
        # section it came from, so the two can be matched.
        candidates = families.get(chapter.id, [])
        if family_table is not None:
            candidates = family_table.candidates(candidates)
        if not candidates and not settings.auto_pipeline:
            row.blocked_reason = (
                f"no concept family exists for {chapter.label}. Open the book screen for "
                f"this subject and create the families it proposes from the chapter's own "
                f"section headings."
            )
            blocked.append(row.address)
            continue
        choice = choose_family(
            candidates, sections_of, section, chapter.label,
            prefer_label=pick.heading if pick.section else None,
            **({"exact_sections_of": family_table.exact_of} if family_table is not None else {}),
        ) if candidates else Choice(None, blocked="no family yet")
        family, ambiguous = choice.family, choice.unsettled
        auto_resolved: str | None = None
        if family is None and choice.blocked is not None and candidates:
            resolution = resolve_blocked_family(
                db,
                api_key=settings.anthropic_api_key,
                model=settings.model_classifier,
                effort=settings.model_effort,
                subject_codes=book_subject_codes,
                section=section,
                stem_text=row.stem_text,
                chapter=chapter,
                candidates=candidates,
                jina_api_key=settings.jina_api_key,
                embedding_model=settings.embedding_model,
                embedding_dimensions=settings.embedding_dimensions,
            )
            if resolution is not None:
                family = resolution.family
                auto_resolved = f"[{resolution.grounded_in}] {resolution.rationale}"
                if resolution.book_section:
                    sections_of.setdefault(family.code, set()).add(resolution.book_section)
        if family is None and settings.auto_pipeline:
            # Nobody will come to create the family, so it is created from the book: one
            # family per section heading, exactly what the book screen proposes.
            family = _ensure_family(
                db, chapter, section, pick.heading if pick.section else None,
                families, sections_of, book_subject_codes,
            )
            auto_resolved = f"[auto_family] created {family.label!r} for section {section or 'the chapter'}"
        if family is None:
            row.blocked_reason = choice.blocked
            blocked.append(row.address)
            continue

        question = Question(
            assessment_id=assessment.id, address=row.address, section=row.section,
            question_no=row.question_no, sub_part=row.sub_part, choice_alt=row.choice_alt,
            attempt_required=row.attempt_required,
            max_marks=row.max_marks, stem_text=row.stem_text,
            stem_hash=stem_hash(row.stem_text), logical_page=row.logical_page,
            board_unit_id=unit_id, chapter_id=chapter.id, curriculum_section=section,
            concept_family_id=family.id,
            concept_variant=row.stem_text[:200],
            variant_hash=variant_hash(row.stem_text[:200]),
            verified_against=f"retrieval:{row_mode}",
        )
        db.add(question)
        db.flush()
        db.add(QuestionPlacement(
            question_id=question.id, chapter_id=chapter.id, board_unit_id=unit_id,
            curriculum_section=section, confidence=verdict.score,
            curriculum_section_fine=(
                fine_section if fine_section and fine_section != section else None
            ),
            # A question whose family could not be settled is one for a person to look at,
            # which is what this flag is for. It is not a reason to refuse the placement.
            # An auto-resolved one gets the same flag: the classifier read the book and
            # made a real choice, not a guess, but it is still a machine's first answer
            # rather than a person's, on a family this chapter never claimed before.
            source="model",
            **_map_review(
                settings, pick, deferred_to_classify, family_unsettled=ambiguous is not None,
                old=(
                    not verdict.agreed
                    or (pick.section is not None and not pick.agreed)
                    or ambiguous is not None
                    or (auto_resolved is not None and not pick.agreed)
                ),
            ),
            reasoning=(
                f"{row_mode} retrieval, margin {verdict.margin:.3f}"
                + (
                    f". Topic {pick.section} ({pick.heading}): {pick.rationale}"
                    if pick.section else ""
                )
                + (f". {ambiguous}" if ambiguous else "")
                + (f". Auto-resolved: {auto_resolved}" if auto_resolved else "")
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
            _write_topic(db, question.id, chapter, topic, section, pick)
            topic_written.append(question.id)
            with_topic += 1
        row.question_id = question.id
        row.blocked_reason = None
        mapped += 1

        if row.question_no in case_study_question_nos:
            group_placement.setdefault(row.question_no, {
                "chapter": chapter, "unit_id": unit_id, "section": section, "topic": topic,
            })

    for row in deferred:
        borrowed = group_placement.get(row.question_no)
        if borrowed is None:
            # No sub-part of this case study found any evidence at all; there is nothing
            # left to borrow, and it stays a real gap rather than a guess.
            row.blocked_reason = "no chapter in the book matched this question"
            blocked.append(row.address)
            continue

        chapter, unit_id, section, topic = (
            borrowed["chapter"], borrowed["unit_id"], borrowed["section"], borrowed["topic"],
        )
        pick = decide_topic(row, chapter, section)
        cap = _section_cap(chapter)
        if cap is not _no_cap:
            pick = capped_pick(pick, cap, headings_of.get(chapter.id))
        if pick.section:
            if pick.section != section:
                # the borrowed topic is the sibling's section, not this one's
                topic = None
            section = pick.section
            if pick.heading and pick.heading != section:
                topic = _book_map_topic_node(db, chapter, section, pick.heading)
            elif is_book_map_subject and (label := _book_map_topic_label(chunks, chapter.id, section)):
                topic = _book_map_topic_node(db, chapter, section, label)
            elif not (settings.book_map_only_subtopics and is_book_map_subject):
                topic = topics.get((chapter.id, section))
        candidates = families.get(chapter.id, [])
        if family_table is not None:
            candidates = family_table.candidates(candidates)
        choice = choose_family(
            candidates, sections_of, section, chapter.label,
            prefer_label=pick.heading if pick.section else None,
            **({"exact_sections_of": family_table.exact_of} if family_table is not None else {}),
        ) if candidates else Choice(None, blocked="no family yet")
        family = choice.family
        if family is None and settings.auto_pipeline:
            family = _ensure_family(
                db, chapter, section, pick.heading if pick.section else None,
                families, sections_of, book_subject_codes,
            )
        if family is None:
            row.blocked_reason = choice.blocked or (
                f"no concept family exists for {chapter.label}."
            )
            blocked.append(row.address)
            continue

        question = Question(
            assessment_id=assessment.id, address=row.address, section=row.section,
            question_no=row.question_no, sub_part=row.sub_part, choice_alt=row.choice_alt,
            attempt_required=row.attempt_required,
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
            curriculum_section=section, confidence=0.0,
            source="model",
            **_map_review(
                settings, pick, deferred_to_classify,
                family_unsettled=choice.unsettled is not None, old=True,
            ),
            reasoning=(
                "no book evidence of its own -- placed under the same chapter as another "
                "sub-part of this same case-study question, and needs a person's check."
            ),
            evidence=[],
            candidates=[],
        ))
        if topic is not None:
            _write_topic(db, question.id, chapter, topic, section, pick)
            topic_written.append(question.id)
            with_topic += 1
        row.question_id = question.id
        row.blocked_reason = None
        mapped += 1

    # the Topic column always shows the section the question carries
    db.flush()
    assert_topic_matches_section(db, topic_written)
    db.commit()

    # A mapped board paper is new evidence about the exam, so the frequency table for
    # the subject is rebuilt now rather than left for someone to remember. The rebuild
    # reads every mapped board paper on the curriculum, this one included.
    frequency = None
    if assessment.paper_kind == "board" and mapped:
        from app.curriculum.board_frequency import recompute as recompute_frequency
        from app.curriculum.board_frequency import stream_of

        frequency = recompute_frequency(
            db, assessment.subject_code, stream=stream_of(assessment),
        )

    return {
        "assessment_id": assessment.id,
        "retrieval": mode,
        "mapped": mapped,
        #: set when this was a board paper: what the frequency table was rebuilt from
        "board_frequency": frequency,
        "blocked": len(blocked),
        #: shared stems that were deliberately left unplaced, not failures
        "context_stems": context_kept,
        #: placed, with a topic from the book. The rest sit in a chapter and no finer.
        "with_topic": with_topic,
        #: the topic judge was left to the classify job queued behind this map
        "topics_deferred_to_classify": deferred_to_classify,
        "spend": {
            "model": settings.model_classifier,
            "calls": getattr(topic_judge, "calls", 0),
            "input_tokens": getattr(topic_judge, "input_tokens", 0),
            "output_tokens": getattr(topic_judge, "output_tokens", 0),
            "cache_read_tokens": getattr(topic_judge, "cache_read_tokens", 0),
            "estimated_usd": estimate_usd(
                settings.model_classifier,
                getattr(topic_judge, "input_tokens", 0),
                getattr(topic_judge, "output_tokens", 0),
                getattr(topic_judge, "cache_read_tokens", 0),
            ),
        },
        "blocked_addresses": blocked[:20],
        #: printed section titles the teacher's scope overruled (sst_unified_scope)
        **({"scope_warnings": paper_scope.warnings()} if paper_scope is not None else {}),
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
    school: School = Depends(require_marks_scope_for_student),
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
    school: School = Depends(require_marks_scope_for_student),
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
