"""Principal-only reporting. One findings computation, three read models over it."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.diagnostics import (
    MarkRow,
    board_weighted_indicator,
    by_chapter,
    by_concept_family,
    by_skill,
    by_tier,
    select_findings,
    select_strengths,
    skill_by_tier,
)
from app.analysis.paper_quality import cronbach_alpha, item_analysis, typology_alignment
from app.analysis.report_pdf import render_student_report_pdf
from app.api.deps import require_reader
from app.db import get_session
from app.models import (
    Assessment,
    BoardUnitWeight,
    MarkEvent,
    ProfileResult,
    Question,
    QuestionPlacement,
    QuestionSkill,
    QuestionTier,
    ScaleScore,
    School,
    StudentProfile,
    StudentReport,
    TaxonomyNode,
    TestSession,
)

router = APIRouter(prefix="/reports", tags=["reports"])


def _current_marks(db: Session, assessment_id: str) -> dict[tuple[str, str], MarkEvent]:
    """Projection over the append-only event log, resolved by source precedence."""
    from app.models.marks import SOURCE_PRECEDENCE

    rank = {s: i for i, s in enumerate(SOURCE_PRECEDENCE)}
    out: dict[tuple[str, str], MarkEvent] = {}
    for ev in db.scalars(select(MarkEvent).where(MarkEvent.assessment_id == assessment_id)):
        key = (ev.student_id, ev.question_id)
        prev = out.get(key)
        if (
            prev is None
            or rank.get(ev.source, -1) > rank.get(prev.source, -1)
            or (ev.source == prev.source and ev.created_at >= prev.created_at)
        ):
            out[key] = ev
    return out


def _latest_placements(db: Session, question_ids: list[str]) -> dict[str, QuestionPlacement]:
    """Append-only log; the current placement is the last row written for the question."""
    out: dict[str, QuestionPlacement] = {}
    if not question_ids:
        return out
    for p in db.scalars(
        select(QuestionPlacement)
        .where(QuestionPlacement.question_id.in_(question_ids))
        .order_by(QuestionPlacement.created_at)
    ):
        out[p.question_id] = p
    return out


def _rows(db: Session, assessment: Assessment) -> list[MarkRow]:
    """Read the curriculum columns the question actually carries.

    This previously derived the chapter by trimming the last dotted segment off a skill
    code, and never set board_unit or concept_family at all. The consequences were not
    cosmetic: with every row's board_unit null, board_weighted_indicator aggregated
    nothing, returned no indicators, and reported *every* board unit as a coverage gap --
    a report stating the paper carries no marks for units it plainly tested. The values
    are on the row; read them.
    """
    questions = {
        q.id: q for q in db.scalars(select(Question).where(Question.assessment_id == assessment.id))
    }
    skills: dict[str, list[str]] = {}
    for qs in db.scalars(
        select(QuestionSkill).where(QuestionSkill.question_id.in_(list(questions)))
    ):
        node = db.get(TaxonomyNode, qs.node_id)
        if node:
            skills.setdefault(qs.question_id, []).append(node.code)
    tiers: dict[str, str] = {}
    for t in db.scalars(select(QuestionTier).where(QuestionTier.question_id.in_(list(questions)))):
        if t.tier:
            tiers[t.question_id] = t.tier

    placements = _latest_placements(db, list(questions))
    wanted: set[str] = set()
    for q in questions.values():
        wanted.update(i for i in (q.board_unit_id, q.chapter_id, q.concept_family_id) if i)
    for p in placements.values():
        wanted.update(i for i in (p.board_unit_id, p.chapter_id) if i)
    codes = {
        n.id: n.code
        for n in db.scalars(select(TaxonomyNode).where(TaxonomyNode.id.in_(wanted)))
    } if wanted else {}

    rows: list[MarkRow] = []
    for (student_id, question_id), ev in _current_marks(db, assessment.id).items():
        q = questions.get(question_id)
        if q is None:
            continue
        # The Q-matrix import fills these in; the placement pipeline writes a separate
        # append-only row instead. Prefer the question, fall back to its latest placement,
        # and leave it null when neither knows -- never guess one from the other.
        p = placements.get(question_id)
        board_unit = codes.get(q.board_unit_id) if q.board_unit_id else None
        if board_unit is None and p is not None and p.board_unit_id:
            board_unit = codes.get(p.board_unit_id)
        chapter = codes.get(q.chapter_id) if q.chapter_id else None
        if chapter is None and p is not None and p.chapter_id:
            chapter = codes.get(p.chapter_id)
        family = codes.get(q.concept_family_id) if q.concept_family_id else None

        rows.append(
            MarkRow(
                student_id=student_id, address=q.address,
                earned=float(ev.marks or 0.0), max_marks=float(q.max_marks),
                state=ev.state, skills=tuple(skills.get(question_id, ())),
                tier=tiers.get(question_id), chapter=chapter,
                board_unit=board_unit, concept_family=family,
                proof=_proof(q, p, ev, codes),
            )
        )
    return rows


def _proof(
    q: Question, p: QuestionPlacement | None, ev: MarkEvent, codes: dict[str, str]
) -> dict:
    """What a teacher needs to check one mark without being told to trust anything.

    Three separate things, kept separate on purpose:
      * the question, as it was read off the paper -- so the number is checkable by hand
        against the mark sheet
      * where it was placed, and the section title from the textbook
      * who placed it and on what -- the model, the blueprint, the declared or inferred
        scope, or a person -- with the book passages the decision rested on, and whether
        it is still flagged for review

    The last one is the point. A placement a person confirmed and a placement the model
    guessed at 0.41 produce the same label, and a report that shows only the label makes
    them indistinguishable. Here they are not.
    """
    return {
        "question_no": q.question_no,
        "section": q.section,
        "sub_part": q.sub_part,
        "choice_alt": q.choice_alt,
        "question_type": q.question_type,
        "stem_text": q.stem_text,
        "logical_page": q.logical_page,
        "curriculum_section": q.curriculum_section,
        "curriculum_section_title": q.curriculum_section_title,
        "concept_variant": q.concept_variant,
        "mark_source": ev.source,
        "placement": (
            {
                "source": p.source,
                "confidence": p.confidence,
                "needs_review": p.needs_review,
                "reviewed_by": p.reviewed_by,
                "reasoning": p.reasoning,
                # The book passages the decision rested on. Grounding has already checked
                # these are passages actually shown to the model, not ones it named.
                "book_evidence": p.evidence or [],
                "candidates": p.candidates or [],
                "chapter": codes.get(p.chapter_id) if p.chapter_id else None,
            }
            if p is not None
            # Imported straight from a Q-matrix: a person typed it, and saying so is more
            # honest than reporting no provenance at all.
            else {
                "source": "import",
                "confidence": None,
                "needs_review": False,
                "reviewed_by": None,
                "reasoning": None,
                "book_evidence": [],
                "candidates": [],
                "chapter": codes.get(q.chapter_id) if q.chapter_id else None,
            }
        ),
        "verified_against": q.verified_against,
        "verified_at": q.verified_at,
    }


def _board_weights(db: Session, assessment: Assessment) -> dict[str, float]:
    """Keyed on the board unit, which is the only thing CBSE publishes weightage for.

    Read from the chapter previously, which computed board impact against a scale the
    board does not use: a unit may span several chapters, or exist where none does.
    """
    out: dict[str, float] = {}
    for w in db.scalars(
        select(BoardUnitWeight).where(
            BoardUnitWeight.curriculum_version == assessment.curriculum_version
        )
    ):
        node = db.get(TaxonomyNode, w.board_unit_id)
        if node:
            out[node.code] = float(w.weight_pct)
    return out


def _topic_axis(rows: list[MarkRow]) -> tuple[str, list]:
    """The finest axis this paper can actually support, named in the output.

    Concept family first -- it is present on every question and is what a later trend
    across papers groups by. If the paper's questions do not all carry one, fall back to
    the sub-topic, then to the chapter. Mixing axes in one list would put a family and a
    chapter side by side as if they were comparable, so the axis is chosen once, for the
    whole report, and stated.
    """
    counted = [r for r in rows if r.counts]
    if counted and all(r.concept_family for r in counted):
        return "concept_family", by_concept_family(rows)
    if counted and all(r.skills for r in counted):
        return "subtopic", by_skill(rows)
    return "chapter", by_chapter(rows)


@router.get("/student/{student_id}/assessments")
def student_assessments(
    student_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """The papers this student has marks for, newest first.

    A report needs a paper as well as a student, and a screen cannot offer that choice
    honestly without knowing which papers have anything on them. Listing every paper the
    school owns would offer tests this student never sat.
    """
    student = db.get(StudentProfile, student_id)
    if student is None or student.school_id != school.id:
        raise HTTPException(404, "not found")

    rows = db.execute(
        select(
            Assessment.id, Assessment.title, Assessment.subject_code,
            Assessment.created_at, func.count(func.distinct(MarkEvent.question_id)),
        )
        .join(MarkEvent, MarkEvent.assessment_id == Assessment.id)
        .where(MarkEvent.student_id == student_id, Assessment.school_id == school.id)
        .group_by(Assessment.id)
        .order_by(Assessment.created_at.desc())
    ).all()

    return {
        "student": {"id": student.id, "name": student.name, "roll_no": student.roll_no},
        "assessments": [
            {
                "assessment_id": aid,
                "title": title,
                "subject_code": subject,
                "created_at": created.isoformat() if created else None,
                "questions_marked": marked,
            }
            for aid, title, subject, created, marked in rows
        ],
    }


@router.get("/student/{student_id}")
def student_report(
    student_id: str,
    assessment_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    a = db.get(Assessment, assessment_id)
    if a is None or a.school_id != school.id:
        raise HTTPException(404, "not found")
    rows = [r for r in _rows(db, a) if r.student_id == student_id]
    if not rows:
        raise HTTPException(404, "no marks for this student")

    weights = _board_weights(db, a)
    crosstab = skill_by_tier(rows)
    axis, topics = _topic_axis(rows)
    indicators, gaps = board_weighted_indicator(rows, weights)

    counted = [r for r in rows if r.counts]
    earned = sum(r.earned for r in counted)
    available = sum(r.max_marks for r in counted)

    # A finding is keyed by a taxonomy code, which is what makes it stable across cycles
    # and useless to a reader. The label travels with it so a screen never has to guess a
    # name from a code, and never shows the code to a teacher.
    labels = {n.code: n.label for n in db.scalars(select(TaxonomyNode))}

    def named(findings) -> list[dict]:
        out = []
        for f in findings:
            row = f.as_dict()
            row["label"] = labels.get(row["key"], row["key"])
            out.append(row)
        return out

    return {
        "assessment_id": a.id,
        "assessment_title": a.title,
        "student_id": student_id,
        "total": {
            "earned": earned, "available": available,
            "rate": round(earned / available, 4) if available else None,
            "questions": len(counted),
        },
        # One axis for the whole report, named so nobody reads a family as a chapter.
        "topic_axis": axis,
        "topics": named(topics),
        "strengths": named(select_strengths(topics)),
        "focus": named(select_findings(topics, weights)),
        "tier_summary": named(by_tier(rows)),
        "findings": named(select_findings(crosstab, weights)),
        "all_crosstab": named(crosstab),
        "board_weighted_indicators": [
            {**i, "label": labels.get(i["board_unit"], i["board_unit"])} for i in indicators
        ],
        "coverage_gaps": [
            {**g.__dict__, "label": labels.get(g.board_unit, g.board_unit)} for g in gaps
        ],
        "not_offered": [r.address for r in rows if r.state == "not_offered"],
    }


class IssueIn(BaseModel):
    assessment_id: str
    by: str = ""


@router.post("/student/{student_id}/issue", status_code=201)
def issue_student_report(
    student_id: str,
    body: IssueIn,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """Keep this report, exactly as it reads now, and name who issued it.

    The diagnosis is regenerable from the marks until a mark is corrected or the book is
    reloaded, after which the same request returns something else. A parent holding a
    sheet from last term must still be able to have it explained, so what was issued is
    stored rather than recomputed.

    A principal may do this, unlike everything else that writes. Sending a report to a
    parent is their job, and this changes no mark -- it records which figures went out,
    under whose name. Refusing it would have left the button on their screen doing nothing.
    """
    payload = student_report(student_id, body.assessment_id, school, db)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    record = StudentReport(
        school_id=school.id, assessment_id=body.assessment_id, student_id=student_id,
        issued_by=body.by[:120], sha256=hashlib.sha256(canonical).hexdigest(),
        earned=payload["total"]["earned"], available=payload["total"]["available"],
        payload=payload,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _issued_view(record)


def _issued_view(record: StudentReport, *, full: bool = False) -> dict:
    out = {
        "report_id": record.id,
        "assessment_id": record.assessment_id,
        "student_id": record.student_id,
        "issued_by": record.issued_by,
        "issued_at": record.created_at.isoformat() if record.created_at else None,
        "sha256": record.sha256,
        "earned": float(record.earned),
        "available": float(record.available),
        "assessment_title": record.payload.get("assessment_title"),
    }
    if full:
        out["payload"] = record.payload
    return out


@router.get("/student/{student_id}/issued")
def list_issued_reports(
    student_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """Every report issued for this student, newest first."""
    records = db.scalars(
        select(StudentReport)
        .where(StudentReport.student_id == student_id, StudentReport.school_id == school.id)
        .order_by(StudentReport.created_at.desc())
    ).all()
    return {"reports": [_issued_view(r) for r in records]}


@router.get("/issued/{report_id}")
def read_issued_report(
    report_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """A stored report, returned as it was issued and never recomputed."""
    record = db.get(StudentReport, report_id)
    if record is None or record.school_id != school.id:
        raise HTTPException(404, "not found")
    return _issued_view(record, full=True)


@router.get("/issued/{report_id}/pdf")
def download_issued_report_pdf(
    report_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> Response:
    """The same issued report, as an actual PDF file -- something a principal can hand a
    parent or keep on file, rather than only ever a screen. Renders the exact payload
    that was frozen at issue time; nothing is recomputed and nothing here can drift from
    what read_issued_report returns.
    """
    record = db.get(StudentReport, report_id)
    if record is None or record.school_id != school.id:
        raise HTTPException(404, "not found")
    student = db.get(StudentProfile, record.student_id)
    if student is None:
        raise HTTPException(404, "the student this report was issued for no longer exists")

    try:
        pdf_bytes = render_student_report_pdf(
            record, student_name=student.name, roll_no=student.roll_no, school_name=school.name,
        )
    except ModuleNotFoundError as exc:
        raise HTTPException(
            501, "PDF generation is not available on this deployment (fpdf2 is not installed)",
        ) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="report-{student.roll_no}-{record.id[:8]}.pdf"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/paper/{assessment_id}")
def paper_report(
    assessment_id: str, school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> dict:
    a = db.get(Assessment, assessment_id)
    if a is None or a.school_id != school.id:
        raise HTTPException(404, "not found")
    rows = _rows(db, a)
    if not rows:
        raise HTTPException(404, "no marks recorded")

    scores: dict[str, dict[str, float]] = {}
    maxes: dict[str, float] = {}
    marks_by_tier: dict[str, float] = {}
    for r in rows:
        if r.state != "awarded":
            continue
        scores.setdefault(r.student_id, {})[r.address] = r.earned
        maxes[r.address] = r.max_marks
    for r in {r.address: r for r in rows}.values():
        if r.tier:
            marks_by_tier[r.tier] = marks_by_tier.get(r.tier, 0.0) + r.max_marks

    stats = item_analysis(scores, maxes)
    return {
        "assessment_id": a.id,
        "students": len(scores),
        "items": [s.__dict__ for s in stats],
        "flagged_items": [s.address for s in stats if s.flag],
        "cronbach_alpha": cronbach_alpha(scores, sorted(maxes)),
        "typology_alignment": typology_alignment(marks_by_tier).as_dict(),
    }


@router.get("/interest/{student_id}")
def interest_report(
    student_id: str, school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> dict:
    """The RIASEC profile — principal and admin only. Never returned to a student route."""
    student = db.get(StudentProfile, student_id)
    if student is None or student.school_id != school.id:
        raise HTTPException(404, "not found")
    session = db.scalar(
        select(TestSession)
        .where(TestSession.student_id == student_id)
        .order_by(TestSession.created_at.desc())
    )
    if session is None:
        raise HTTPException(404, "no session")
    result = db.scalar(select(ProfileResult).where(ProfileResult.session_id == session.id))
    scales = list(db.scalars(select(ScaleScore).where(ScaleScore.session_id == session.id)))
    return {
        "student": {"id": student.id, "name": student.name, "roll_no": student.roll_no},
        "validity": session.validity,
        "validity_detail": session.validity_detail,
        "scales": [
            {"scale": s.scale, "raw": s.raw, "centered": round(s.centered, 3),
             "percentile": round(s.percentile, 1), "ci": [round(s.ci_low, 1), round(s.ci_high, 1)]}
            for s in scales
        ],
        "holland_code": result.holland_code if result else None,
        "differentiation": result.differentiation if result else None,
        "consistency": result.consistency if result else None,
        "stream_fit": result.stream_fit if result else None,
        "recommendation_withheld": result.recommendation_withheld if result else True,
        "withheld_reason": result.withheld_reason if result else "no result computed",
    }
