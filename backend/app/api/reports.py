"""Principal-only reporting. One findings computation, three read models over it."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.diagnostics import (
    MarkRow,
    board_weighted_indicator,
    by_tier,
    select_findings,
    skill_by_tier,
)
from app.analysis.paper_quality import cronbach_alpha, item_analysis, typology_alignment
from app.api.deps import require_admin
from app.db import get_session
from app.models import (
    Assessment,
    ChapterWeight,
    MarkEvent,
    ProfileResult,
    Question,
    QuestionSkill,
    QuestionTier,
    ScaleScore,
    School,
    StudentProfile,
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


def _rows(db: Session, assessment: Assessment) -> list[MarkRow]:
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

    rows: list[MarkRow] = []
    for (student_id, question_id), ev in _current_marks(db, assessment.id).items():
        q = questions.get(question_id)
        if q is None:
            continue
        codes = tuple(skills.get(question_id, ()))
        chapter = codes[0].rsplit(".", 1)[0] if codes else None
        rows.append(
            MarkRow(
                student_id=student_id, address=q.address,
                earned=float(ev.marks or 0.0), max_marks=float(q.max_marks),
                state=ev.state, skills=codes, tier=tiers.get(question_id), chapter=chapter,
            )
        )
    return rows


def _board_weights(db: Session, assessment: Assessment) -> dict[str, float]:
    out: dict[str, float] = {}
    for w in db.scalars(
        select(ChapterWeight).where(
            ChapterWeight.curriculum_version == assessment.curriculum_version
        )
    ):
        node = db.get(TaxonomyNode, w.chapter_id)
        if node:
            out[node.code] = float(w.weight_pct)
    return out


@router.get("/student/{student_id}")
def student_report(
    student_id: str,
    assessment_id: str,
    school: School = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict:
    a = db.get(Assessment, assessment_id)
    if a is None or a.school_id != school.id:
        raise HTTPException(404, "not found")
    rows = [r for r in _rows(db, a) if r.student_id == student_id]
    if not rows:
        raise HTTPException(404, "no marks for this student")

    weights = _board_weights(db, a)
    findings = skill_by_tier(rows)
    indicators, gaps = board_weighted_indicator(rows, weights)
    return {
        "assessment_id": a.id,
        "student_id": student_id,
        "tier_summary": [f.as_dict() for f in by_tier(rows)],
        "findings": [f.as_dict() for f in select_findings(findings, weights)],
        "all_crosstab": [f.as_dict() for f in findings],
        "board_weighted_indicators": indicators,
        "coverage_gaps": [g.__dict__ for g in gaps],
        "not_offered": [r.address for r in rows if r.state == "not_offered"],
    }


@router.get("/paper/{assessment_id}")
def paper_report(
    assessment_id: str, school: School = Depends(require_admin), db: Session = Depends(get_session)
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
    student_id: str, school: School = Depends(require_admin), db: Session = Depends(get_session)
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
