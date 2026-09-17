"""Academic performance, rolled up from the same marks the rest of the API already
trusts -- a principal drills Overview -> Class -> Student -> Subject, and every number
on every one of those screens is derived straight from ``MarkEvent``/``Question``/
``TaxonomyNode``, using the same evidence-floor and chapter/tier machinery
``app.analysis.diagnostics`` already provides for a single-assessment report, run here
across however many assessments and students a screen asks for.

Deliberately does not carry an "aspiration", "action plan" or "recheck" -- this
deployment has no data model for any of those, and a screen that shows them anyway
would be showing a promise nobody can act on.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.diagnostics import Finding, MarkRow, by_chapter, by_tier
from app.api.deps import require_reader
from app.curriculum import CURRICULA
from app.db import get_session
from app.models import (
    Assessment,
    MarkEvent,
    Question,
    QuestionTier,
    School,
    Section,
    StudentProfile,
    TaxonomyNode,
)

router = APIRouter(prefix="/admin/academics", tags=["academics"])

#: Below this rate a student is "requires_review"; below the higher one, "needs_attention";
#: at or above it, "on_track". Same three-band shape the BoardX report already uses for
#: upper/lower assembly, picked for consistency rather than re-derived per screen.
_REVIEW_BELOW = 0.50
_ATTENTION_BELOW = 0.75

STATUS_LABELS = {
    "on_track": "On Track",
    "needs_attention": "Needs Attention",
    "requires_review": "Requires Review",
    "not_assessed": "Not Yet Assessed",
}

#: The three CBSE tiers a question is classified into (app.models.assessment.TIERS),
#: spelled out for a screen the way app.analysis.boardx_strings.TIER_QUESTION_TYPE
#: already does for the student-facing report -- one place these are named in full.
TIER_LABELS = {
    "R&U": "Remembering & Understanding",
    "AP": "Applying",
    "AEC": "Analysing, Evaluating & Creating",
}


def _subject_label(subject_code: str) -> str:
    curriculum = CURRICULA.get(subject_code)
    return curriculum.subject_label if curriculum else subject_code


def _status_for(earned: float, available: float) -> str:
    if available <= 0:
        return "not_assessed"
    rate = earned / available
    if rate < _REVIEW_BELOW:
        return "requires_review"
    if rate < _ATTENTION_BELOW:
        return "needs_attention"
    return "on_track"


@dataclass
class TaggedRow:
    """One resolved mark, still carrying which assessment (and so which subject) it came
    from -- ``MarkRow`` itself only knows the question, not the paper."""

    assessment_id: str
    subject_code: str
    assessment_title: str
    row: MarkRow


@dataclass
class _Accum:
    earned: float = 0.0
    available: float = 0.0
    assessment_ids: set = field(default_factory=set)
    rows: list = field(default_factory=list)


def resolved_rows(
    db: Session, school: School, *,
    student_ids: list[str] | None = None,
    subject_code: str | None = None,
    assessment_id: str | None = None,
) -> list[TaggedRow]:
    """Every resolved mark matching the given filters, in this school.

    One query per table rather than one per assessment: this is the same append-only-log
    projection ``app.api.reports._current_marks`` uses for a single assessment, run once
    across however many assessments a screen's filters select. ``student_ids=None`` means
    every student in the school; an empty list is deliberately treated the same as "no
    filter" would be wrong, so callers pass ``None`` rather than `[]` to mean "everyone".
    """
    from app.models.marks import SOURCE_PRECEDENCE

    rank = {s: i for i, s in enumerate(SOURCE_PRECEDENCE)}

    aq = select(Assessment).where(Assessment.school_id == school.id)
    if subject_code:
        aq = aq.where(Assessment.subject_code == subject_code)
    if assessment_id:
        aq = aq.where(Assessment.id == assessment_id)
    assessments = {a.id: a for a in db.scalars(aq)}
    if not assessments:
        return []
    assessment_ids = list(assessments)

    questions = {
        q.id: q for q in db.scalars(select(Question).where(Question.assessment_id.in_(assessment_ids)))
    }
    if not questions:
        return []
    tiers = {
        t.question_id: t.tier
        for t in db.scalars(select(QuestionTier).where(QuestionTier.question_id.in_(list(questions))))
    }
    chapter_ids = {q.chapter_id for q in questions.values() if q.chapter_id}
    chapter_codes = {
        n.id: n.code for n in db.scalars(select(TaxonomyNode).where(TaxonomyNode.id.in_(chapter_ids)))
    } if chapter_ids else {}

    evq = select(MarkEvent).where(MarkEvent.assessment_id.in_(assessment_ids))
    if student_ids is not None:
        evq = evq.where(MarkEvent.student_id.in_(student_ids))

    resolved: dict[tuple[str, str, str], MarkEvent] = {}
    for ev in db.scalars(evq):
        key = (ev.assessment_id, ev.student_id, ev.question_id)
        prev = resolved.get(key)
        if (
            prev is None
            or rank.get(ev.source, -1) > rank.get(prev.source, -1)
            or (ev.source == prev.source and ev.created_at >= prev.created_at)
        ):
            resolved[key] = ev

    out: list[TaggedRow] = []
    for (aid, student_id, qid), ev in resolved.items():
        q = questions.get(qid)
        if q is None:
            continue
        a = assessments[aid]
        out.append(TaggedRow(
            assessment_id=aid, subject_code=a.subject_code, assessment_title=a.title,
            row=MarkRow(
                student_id=student_id, address=q.address, earned=float(ev.marks or 0.0),
                max_marks=float(q.max_marks), state=ev.state,
                tier=tiers.get(qid), chapter=chapter_codes.get(q.chapter_id) if q.chapter_id else None,
            ),
        ))
    return out


def _chapter_labels(db: Session, codes: set[str]) -> dict[str, str]:
    if not codes:
        return {}
    return {n.code: n.label for n in db.scalars(select(TaxonomyNode).where(TaxonomyNode.code.in_(codes)))}


def _findings_view(findings: list[Finding], labels: dict[str, str]) -> list[dict]:
    return [
        {
            "key": f.key,
            "label": labels.get(f.key, f.key),
            "earned": f.earned,
            "available": f.available,
            "rate": f.rate,
            "questions": f.questions,
            "sufficient": f.sufficient,
            "message": f.message,
        }
        for f in findings
    ]


# ------------------------------------------------------------------------------------
# Page 1: Overview -- every class, rolled up
# ------------------------------------------------------------------------------------

def _class_summaries(db: Session, school: School) -> list[dict]:
    tagged = resolved_rows(db, school)
    by_student: dict[str, _Accum] = {}
    for t in tagged:
        acc = by_student.setdefault(t.row.student_id, _Accum())
        acc.assessment_ids.add(t.assessment_id)
        if t.row.counts:
            acc.earned += t.row.earned
            acc.available += t.row.max_marks

    sections = list(
        db.scalars(select(Section).where(Section.school_id == school.id).order_by(Section.grade, Section.name))
    )
    out = []
    for section in sections:
        students = list(
            db.scalars(select(StudentProfile).where(StudentProfile.section_id == section.id))
        )
        counts = {k: 0 for k in STATUS_LABELS}
        earned_sum = available_sum = 0.0
        assessment_ids: set[str] = set()
        for student in students:
            acc = by_student.get(student.id)
            counts[_status_for(acc.earned if acc else 0.0, acc.available if acc else 0.0)] += 1
            if acc is not None:
                earned_sum += acc.earned
                available_sum += acc.available
                assessment_ids |= acc.assessment_ids
        out.append({
            "section_id": section.id,
            "label": f"Class {section.grade}-{section.name}",
            "grade": section.grade,
            "name": section.name,
            "student_count": len(students),
            "status_counts": counts,
            "avg_score_pct": round(earned_sum / available_sum * 100, 1) if available_sum else None,
            "test_count": len(assessment_ids),
        })
    return out


@router.get("")
def academics_overview(
    school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> dict:
    """Every class, its status split and its average score -- the landing screen for
    "which classes need attention today"."""
    return {
        "school": {"id": school.id, "name": school.name},
        "classes": _class_summaries(db, school),
    }


def _overview_rows(db: Session, school: School) -> tuple[list[str], list[list[object]]]:
    header = [
        "Class", "Students", "On Track", "Needs Attention", "Requires Review",
        "Not Yet Assessed", "Avg Score %", "Tests With Marks",
    ]
    rows = [
        [
            c["label"], c["student_count"],
            c["status_counts"]["on_track"], c["status_counts"]["needs_attention"],
            c["status_counts"]["requires_review"], c["status_counts"]["not_assessed"],
            c["avg_score_pct"] if c["avg_score_pct"] is not None else "",
            c["test_count"],
        ]
        for c in _class_summaries(db, school)
    ]
    return header, rows


@router.get("/overview.xlsx")
def academics_overview_xlsx(
    school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> Response:
    header, rows = _overview_rows(db, school)
    return _xlsx_response(header, rows, "Class Overview", f"{school.name}-class-overview.xlsx")


@router.get("/overview.pdf")
def academics_overview_pdf(
    school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> Response:
    header, rows = _overview_rows(db, school)
    return _pdf_response(
        f"{school.name} -- Class Overview", header, rows, f"{school.name}-class-overview.pdf",
    )


# ------------------------------------------------------------------------------------
# Page 2: Class -> student list, filterable by subject / test / status
# ------------------------------------------------------------------------------------

def _class_students(
    db: Session, school: School, section: Section,
    *, subject_code: str | None, assessment_id: str | None, status: str | None,
) -> list[dict]:
    students = list(
        db.scalars(
            select(StudentProfile).where(StudentProfile.section_id == section.id).order_by(StudentProfile.roll_no)
        )
    )
    student_ids = [s.id for s in students]
    tagged = resolved_rows(
        db, school, student_ids=student_ids, subject_code=subject_code, assessment_id=assessment_id,
    )
    by_student: dict[str, list[TaggedRow]] = {sid: [] for sid in student_ids}
    for t in tagged:
        by_student.setdefault(t.row.student_id, []).append(t)

    chapter_labels_needed: set[str] = set()
    rows_out = []
    for student in students:
        entries = by_student.get(student.id, [])
        earned = sum(t.row.earned for t in entries if t.row.counts)
        available = sum(t.row.max_marks for t in entries if t.row.counts)
        this_status = _status_for(earned, available)
        chapter_findings = by_chapter([t.row for t in entries])
        worst = min(
            (f for f in chapter_findings if f.sufficient and f.rate is not None),
            key=lambda f: f.rate, default=None,
        )
        if worst is not None:
            chapter_labels_needed.add(worst.key)
        rows_out.append({
            "student_id": student.id, "name": student.name, "roll_no": student.roll_no,
            "status": this_status,
            "avg_score_pct": round(earned / available * 100, 1) if available else None,
            "tests_taken": len({t.assessment_id for t in entries}),
            "_worst_chapter_code": worst.key if worst else None,
            "_worst_chapter_rate": round(worst.rate * 100, 1) if worst and worst.rate is not None else None,
        })

    labels = _chapter_labels(db, chapter_labels_needed)
    for row in rows_out:
        code = row.pop("_worst_chapter_code")
        rate = row.pop("_worst_chapter_rate")
        row["top_improvement_area"] = (
            {"chapter": labels.get(code, code), "rate": rate} if code else None
        )

    if status:
        rows_out = [r for r in rows_out if r["status"] == status]
    return rows_out


def _section_filters(db: Session, school: School, section_id: str) -> dict:
    students = list(db.scalars(select(StudentProfile.id).where(StudentProfile.section_id == section_id)))
    tagged = resolved_rows(db, school, student_ids=list(students))
    subjects = sorted({t.subject_code for t in tagged})
    tests = sorted(
        {(t.assessment_id, t.assessment_title) for t in tagged}, key=lambda x: x[1],
    )
    return {
        "subjects": [{"subject_code": s, "label": _subject_label(s)} for s in subjects],
        "tests": [{"assessment_id": aid, "title": title} for aid, title in tests],
    }


def _get_section(db: Session, school: School, section_id: str) -> Section:
    section = db.get(Section, section_id)
    if section is None or section.school_id != school.id:
        raise HTTPException(404, "no such class")
    return section


@router.get("/{section_id}/students")
def class_students(
    section_id: str,
    subject_code: str | None = None, assessment_id: str | None = None, status: str | None = None,
    school: School = Depends(require_reader), db: Session = Depends(get_session),
) -> dict:
    """Every student in this class, their overall status and their weakest chapter --
    optionally narrowed to one subject, one test, or one status band."""
    section = _get_section(db, school, section_id)
    if status is not None and status not in STATUS_LABELS:
        raise HTTPException(422, f"status must be one of {', '.join(STATUS_LABELS)}")
    return {
        "section": {"id": section.id, "label": f"Class {section.grade}-{section.name}"},
        "filters": _section_filters(db, school, section_id),
        "students": _class_students(
            db, school, section, subject_code=subject_code, assessment_id=assessment_id, status=status,
        ),
    }


def _class_students_rows(students: list[dict]) -> tuple[list[str], list[list[object]]]:
    header = ["Roll No", "Name", "Status", "Avg Score %", "Tests Taken", "Top Area to Improve"]
    rows = [
        [
            s["roll_no"], s["name"], STATUS_LABELS[s["status"]],
            s["avg_score_pct"] if s["avg_score_pct"] is not None else "",
            s["tests_taken"],
            s["top_improvement_area"]["chapter"] if s["top_improvement_area"] else "",
        ]
        for s in students
    ]
    return header, rows


@router.get("/{section_id}/students.xlsx")
def class_students_xlsx(
    section_id: str,
    subject_code: str | None = None, assessment_id: str | None = None, status: str | None = None,
    school: School = Depends(require_reader), db: Session = Depends(get_session),
) -> Response:
    section = _get_section(db, school, section_id)
    students = _class_students(
        db, school, section, subject_code=subject_code, assessment_id=assessment_id, status=status,
    )
    header, rows = _class_students_rows(students)
    return _xlsx_response(
        header, rows, f"Class {section.grade}-{section.name}", f"class-{section.grade}{section.name}-students.xlsx",
    )


@router.get("/{section_id}/students.pdf")
def class_students_pdf(
    section_id: str,
    subject_code: str | None = None, assessment_id: str | None = None, status: str | None = None,
    school: School = Depends(require_reader), db: Session = Depends(get_session),
) -> Response:
    section = _get_section(db, school, section_id)
    students = _class_students(
        db, school, section, subject_code=subject_code, assessment_id=assessment_id, status=status,
    )
    header, rows = _class_students_rows(students)
    return _pdf_response(
        f"Class {section.grade}-{section.name}", header, rows,
        f"class-{section.grade}{section.name}-students.pdf",
    )


# ------------------------------------------------------------------------------------
# Page 3: Student -> every subject they have marks in
# ------------------------------------------------------------------------------------

def _get_student(db: Session, school: School, student_id: str) -> StudentProfile:
    student = db.get(StudentProfile, student_id)
    if student is None or student.school_id != school.id:
        raise HTTPException(404, "no such student")
    return student


def _student_subjects(db: Session, school: School, student_id: str) -> dict[str, list[TaggedRow]]:
    tagged = resolved_rows(db, school, student_ids=[student_id])
    by_subject: dict[str, list[TaggedRow]] = {}
    for t in tagged:
        by_subject.setdefault(t.subject_code, []).append(t)
    return by_subject


def _student_overview(db: Session, school: School, student: StudentProfile) -> dict:
    section = db.get(Section, student.section_id)
    by_subject = _student_subjects(db, school, student.id)

    chapter_labels_needed: set[str] = set()
    subject_rows = []
    total_earned = total_available = 0.0
    all_assessment_ids: set[str] = set()
    for subject_code, entries in sorted(by_subject.items()):
        rows = [t.row for t in entries]
        earned = sum(r.earned for r in rows if r.counts)
        available = sum(r.max_marks for r in rows if r.counts)
        total_earned += earned
        total_available += available
        all_assessment_ids |= {t.assessment_id for t in entries}
        chapters = by_chapter(rows)
        strengths = sorted(
            (f for f in chapters if f.sufficient and f.rate is not None), key=lambda f: -f.rate,
        )[:3]
        weak = sorted(
            (f for f in chapters if f.sufficient and f.rate is not None), key=lambda f: f.rate,
        )[:3]
        for f in (*strengths, *weak):
            chapter_labels_needed.add(f.key)
        subject_rows.append({
            "subject_code": subject_code,
            "label": _subject_label(subject_code),
            "avg_score_pct": round(earned / available * 100, 1) if available else None,
            "tests_taken": len({t.assessment_id for t in entries}),
            "status": _status_for(earned, available),
            "_strengths": [f.key for f in strengths],
            "_improve": [f.key for f in weak],
        })

    labels = _chapter_labels(db, chapter_labels_needed)
    for row in subject_rows:
        row["strengths"] = [labels.get(c, c) for c in row.pop("_strengths")]
        row["improve"] = [labels.get(c, c) for c in row.pop("_improve")]

    return {
        "student": {
            "id": student.id, "name": student.name, "roll_no": student.roll_no,
            "section_id": student.section_id,
            "section_label": f"Class {section.grade}-{section.name}" if section else None,
        },
        "overall": {
            "avg_score_pct": round(total_earned / total_available * 100, 1) if total_available else None,
            "status": _status_for(total_earned, total_available),
            "tests_taken": len(all_assessment_ids),
        },
        "subjects": subject_rows,
    }


def _student_rows(overview: dict) -> tuple[list[str], list[list[object]]]:
    header = ["Subject", "Avg Score %", "Tests Taken", "Status", "Strengths", "Areas to Improve"]
    rows = [
        [
            s["label"], s["avg_score_pct"] if s["avg_score_pct"] is not None else "",
            s["tests_taken"], STATUS_LABELS[s["status"]],
            "; ".join(s["strengths"]), "; ".join(s["improve"]),
        ]
        for s in overview["subjects"]
    ]
    return header, rows


# The .xlsx/.pdf routes are registered before the bare "/students/{student_id}" route
# below, deliberately: Starlette matches routes in registration order, and
# "{student_id}" alone would otherwise swallow a request for ".../abc123.xlsx" whole
# (binding student_id="abc123.xlsx") before the more specific route ever gets a look,
# turning every download into a 404 "no such student". Same reasoning applies to every
# other suffixed pair below.
@router.get("/students/{student_id}.xlsx")
def student_overview_xlsx(
    student_id: str, school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> Response:
    student = _get_student(db, school, student_id)
    overview = _student_overview(db, school, student)
    header, rows = _student_rows(overview)
    return _xlsx_response(header, rows, student.name[:31], f"{student.name}-overview.xlsx")


@router.get("/students/{student_id}.pdf")
def student_overview_pdf(
    student_id: str, school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> Response:
    student = _get_student(db, school, student_id)
    overview = _student_overview(db, school, student)
    header, rows = _student_rows(overview)
    return _pdf_response(
        f"{student.name} (Roll {student.roll_no}) -- Overview", header, rows,
        f"{student.name}-overview.pdf",
    )


@router.get("/students/{student_id}")
def student_overview(
    student_id: str, school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> dict:
    """One student, every subject they have marks in: an overall status plus, per
    subject, an average score and the chapters they are strongest and weakest in."""
    student = _get_student(db, school, student_id)
    return _student_overview(db, school, student)


# ------------------------------------------------------------------------------------
# Page 4: Student -> one subject, chapter and tier breakdown
# ------------------------------------------------------------------------------------

def _subject_breakdown(db: Session, school: School, student: StudentProfile, subject_code: str) -> dict:
    tagged = resolved_rows(db, school, student_ids=[student.id], subject_code=subject_code)
    if not tagged:
        raise HTTPException(404, "no marks for this student in this subject")
    rows = [t.row for t in tagged]
    earned = sum(r.earned for r in rows if r.counts)
    available = sum(r.max_marks for r in rows if r.counts)

    chapters = by_chapter(rows)
    tiers = by_tier(rows)
    labels = _chapter_labels(db, {f.key for f in chapters})

    return {
        "student": {"id": student.id, "name": student.name, "roll_no": student.roll_no},
        "subject": {"subject_code": subject_code, "label": _subject_label(subject_code)},
        "overall": {
            "earned": earned, "available": available,
            "avg_score_pct": round(earned / available * 100, 1) if available else None,
            "status": _status_for(earned, available),
            "tests_taken": len({t.assessment_id for t in tagged}),
        },
        "by_chapter": _findings_view(chapters, labels),
        "by_tier": [
            {**v, "label": TIER_LABELS.get(v["key"], v["key"])}
            for v in _findings_view(tiers, {})
        ],
        # Every test this rollup drew from, so a screen can offer the one-page BoardX
        # report (app.analysis.boardx_report) for a specific paper -- that report is
        # scoped to one assessment, not a subject's whole history, so it needs a real
        # assessment_id to render against.
        "tests": [
            {"assessment_id": aid, "title": title}
            for aid, title in sorted({(t.assessment_id, t.assessment_title) for t in tagged}, key=lambda x: x[1])
        ],
    }


def _subject_rows(detail: dict) -> tuple[list[str], list[list[object]]]:
    header = ["Section", "Chapter / Tier", "Earned", "Available", "Score %", "Questions"]
    rows = []
    for f in detail["by_chapter"]:
        rows.append([
            "Chapter", f["label"], f["earned"], f["available"],
            round(f["rate"] * 100, 1) if f["rate"] is not None else "", f["questions"],
        ])
    for f in detail["by_tier"]:
        rows.append([
            "Tier", f["label"], f["earned"], f["available"],
            round(f["rate"] * 100, 1) if f["rate"] is not None else "", f["questions"],
        ])
    return header, rows


@router.get("/students/{student_id}/subjects/{subject_code}.xlsx")
def student_subject_xlsx(
    student_id: str, subject_code: str,
    school: School = Depends(require_reader), db: Session = Depends(get_session),
) -> Response:
    student = _get_student(db, school, student_id)
    detail = _subject_breakdown(db, school, student, subject_code)
    header, rows = _subject_rows(detail)
    return _xlsx_response(
        header, rows, _subject_label(subject_code)[:31],
        f"{student.name}-{subject_code}.xlsx",
    )


@router.get("/students/{student_id}/subjects/{subject_code}.pdf")
def student_subject_pdf(
    student_id: str, subject_code: str,
    school: School = Depends(require_reader), db: Session = Depends(get_session),
) -> Response:
    student = _get_student(db, school, student_id)
    detail = _subject_breakdown(db, school, student, subject_code)
    header, rows = _subject_rows(detail)
    return _pdf_response(
        f"{student.name} -- {_subject_label(subject_code)}", header, rows,
        f"{student.name}-{subject_code}.pdf",
    )


@router.get("/students/{student_id}/subjects/{subject_code}")
def student_subject_breakdown(
    student_id: str, subject_code: str,
    school: School = Depends(require_reader), db: Session = Depends(get_session),
) -> dict:
    """One student, one subject: chapter-wise and tier-wise (Remembering & Understanding /
    Applying / Analysing, Evaluating & Creating) marks, from the same evidence-floored
    findings machinery a BoardX report uses."""
    student = _get_student(db, school, student_id)
    return _subject_breakdown(db, school, student, subject_code)


# ------------------------------------------------------------------------------------
# Test tab: every test, and one test's own student-by-student summary
# ------------------------------------------------------------------------------------

@router.get("/tests")
def academics_tests(
    school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> dict:
    """Every paper with at least one resolved mark, newest first -- the list the Test tab
    picks one from."""
    tagged = resolved_rows(db, school)
    by_assessment: dict[str, dict] = {}
    for t in tagged:
        entry = by_assessment.setdefault(t.assessment_id, {
            "assessment_id": t.assessment_id, "title": t.assessment_title,
            "subject_code": t.subject_code, "label": _subject_label(t.subject_code),
            "students": set(),
        })
        entry["students"].add(t.row.student_id)
    out = [
        {**{k: v for k, v in e.items() if k != "students"}, "students_marked": len(e["students"])}
        for e in by_assessment.values()
    ]
    out.sort(key=lambda e: e["title"])
    return {"tests": out}


def _test_summary(db: Session, school: School, assessment: Assessment) -> dict:
    tagged = resolved_rows(db, school, assessment_id=assessment.id)
    by_student: dict[str, list[MarkRow]] = {}
    for t in tagged:
        by_student.setdefault(t.row.student_id, []).append(t.row)

    student_ids = list(by_student)
    students = {
        s.id: s for s in db.scalars(select(StudentProfile).where(StudentProfile.id.in_(student_ids)))
    } if student_ids else {}

    rows = []
    counts = {k: 0 for k in STATUS_LABELS}
    for student_id, marks in by_student.items():
        student = students.get(student_id)
        earned = sum(r.earned for r in marks if r.counts)
        available = sum(r.max_marks for r in marks if r.counts)
        status = _status_for(earned, available)
        counts[status] += 1
        rows.append({
            "student_id": student_id,
            "name": student.name if student else student_id,
            "roll_no": student.roll_no if student else "",
            "earned": earned, "available": available,
            "avg_score_pct": round(earned / available * 100, 1) if available else None,
            "status": status,
        })
    rows.sort(key=lambda r: r["roll_no"])

    return {
        "assessment": {
            "id": assessment.id, "title": assessment.title,
            "subject_code": assessment.subject_code, "subject_label": _subject_label(assessment.subject_code),
        },
        "status_counts": counts,
        "students": rows,
    }


def _test_rows(summary: dict) -> tuple[list[str], list[list[object]]]:
    header = ["Roll No", "Name", "Earned", "Available", "Score %", "Status"]
    rows = [
        [
            s["roll_no"], s["name"], s["earned"], s["available"],
            s["avg_score_pct"] if s["avg_score_pct"] is not None else "",
            STATUS_LABELS[s["status"]],
        ]
        for s in summary["students"]
    ]
    return header, rows


@router.get("/tests/{assessment_id}.xlsx")
def academics_test_xlsx(
    assessment_id: str, school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> Response:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != school.id:
        raise HTTPException(404, "no such test")
    summary = _test_summary(db, school, assessment)
    header, rows = _test_rows(summary)
    return _xlsx_response(header, rows, assessment.title[:31], f"{assessment.title}-results.xlsx")


@router.get("/tests/{assessment_id}.pdf")
def academics_test_pdf(
    assessment_id: str, school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> Response:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != school.id:
        raise HTTPException(404, "no such test")
    summary = _test_summary(db, school, assessment)
    header, rows = _test_rows(summary)
    return _pdf_response(assessment.title, header, rows, f"{assessment.title}-results.pdf")


@router.get("/tests/{assessment_id}")
def academics_test_summary(
    assessment_id: str, school: School = Depends(require_reader), db: Session = Depends(get_session)
) -> dict:
    """One test, every student who has a mark on it, and the same status bands the rest
    of this screen family uses."""
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != school.id:
        raise HTTPException(404, "no such test")
    return _test_summary(db, school, assessment)


# ------------------------------------------------------------------------------------
# xlsx / pdf rendering, shared by every route above
# ------------------------------------------------------------------------------------

def _xlsx_response(header: list[str], rows: list[list[object]], sheet_title: str, filename: str) -> Response:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = (sheet_title or "Sheet")[:31] or "Sheet"
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(row)
    for i, col in enumerate(header, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(14, len(col) + 2)

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _pdf_response(
    title: str, header: list[str], rows: list[list[object]], filename: str,
) -> Response:
    from fpdf import FPDF

    def safe(text: object) -> str:
        return str(text if text is not None else "").encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF(format="A4", orientation="L")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, safe(title), new_x="LMARGIN", new_y="NEXT")

    usable_width = pdf.w - 2 * pdf.l_margin
    col_width = usable_width / max(1, len(header))
    pdf.set_font("Helvetica", "B", 9)
    for col in header:
        pdf.cell(col_width, 8, safe(col), border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for row in rows:
        for val in row:
            pdf.cell(col_width, 7, safe(val), border=1)
        pdf.ln()

    return Response(
        content=bytes(pdf.output()),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
