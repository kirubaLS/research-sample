"""Principal-only reporting. One findings computation, three read models over it."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.whatsapp import WhatsAppAPIError, WhatsAppClient

from app.analysis.diagnostics import (
    MarkRow,
    board_weighted_indicator,
    by_chapter,
    by_concept_family,
    by_skill,
    by_tier,
    confidence_tier,
    select_findings,
    select_strengths,
    skill_by_tier,
    wilson_interval,
)
from app.analysis.paper_quality import (
    cronbach_alpha,
    diagnostic_strength_tier,
    item_analysis,
    typology_alignment,
)
from app.analysis.report_pdf import render_student_report_pdf
from app.api.deps import Staff, current_staff, require_reader, require_teacher_read_scope
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
    Section,
    StudentProfile,
    StudentReport,
    TaxonomyNode,
    TestSession,
    WhatsAppSend,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])
webhook_router = APIRouter(tags=["whatsapp-webhook"])


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


def _capped_skill_code(code: str) -> str:
    """A subtopic code cut to its subject's depth (topic_depth_cap), so a row written
    before the cap -- 'X.GEO.MINERALSENERGY.S4_1_2' -- groups with its major topic
    'X.GEO.MINERALSENERGY.S4_1'. Any other code, or an uncapped subject, is unchanged."""
    from app.curriculum.depth import collapse_section, is_capped
    from app.mapping.topic_node import section_number

    chapter_code, _, tail = code.rpartition(".")
    section = section_number(code)
    if not section or not chapter_code or not is_capped(chapter_code):
        return code
    cut = collapse_section(None, section, chapter_code=chapter_code)
    return f"{chapter_code}.S{cut.replace('.', '_')}" if cut else code


def _capped_section(q: Question, codes: dict[str, str]) -> str | None:
    """The question's section cut to its subject's depth (topic_depth_cap)."""
    code = codes.get(q.chapter_id) if q.chapter_id else None
    if not q.curriculum_section or not code:
        return q.curriculum_section
    from app.curriculum.depth import collapse_section

    return collapse_section(None, q.curriculum_section, chapter_code=code)


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
            code = _capped_skill_code(node.code)
            held = skills.setdefault(qs.question_id, [])
            if code not in held:
                held.append(code)
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
        "curriculum_section": _capped_section(q, codes),
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


def _board_urgency(
    db: Session, assessment: Assessment, rows: list[MarkRow],
) -> tuple[list[dict], dict[str, float]]:
    """Urgency per concept family this paper tested: board weight x frequency multiplier.

    Returns the list a report shows, and the priority map the focus ranking uses: every
    family AND sub-topic code on the paper, resolved to its unit's weight through the
    question's own board unit, times the family's multiplier. That resolution is the
    point -- the ranking used to look a family code up in a table keyed by unit code,
    never match, and fall back to a flat default, so board weight ranked nothing.

    The multiplier comes from the materialised table built off real board papers
    (app.curriculum.board_frequency). A family with no row gets 1.0, the floor, so a
    subject nobody has loaded board papers for ranks on plain board weight -- never less.
    """
    from app.analysis.board_frequency import urgency
    from app.curriculum.board_frequency import (
        CURRENT_VERSION,
        frequency_note,
        frequency_rows,
        stream_of,
        urgency_tier,
    )

    freq = frequency_rows(db, assessment.subject_code, CURRENT_VERSION, stream_of(assessment))
    weights = _board_weights(db, assessment)
    nodes = {n.code: n for n in db.scalars(select(TaxonomyNode))}
    shown: dict[str, dict] = {}
    priority: dict[str, float] = {}
    for r in rows:
        if not r.counts:
            continue
        weight = weights.get(r.board_unit or "")
        fam = nodes.get(r.concept_family) if r.concept_family else None
        row = freq.get(fam.id) if fam else None
        mult = float(row.multiplier) if row else 1.0
        score = urgency(weight, mult) if weight is not None else None
        if score is not None:
            if r.concept_family:
                priority[r.concept_family] = score
            for sk in r.skills:
                priority.setdefault(sk, score)
        if r.concept_family and r.concept_family not in shown:
            shown[r.concept_family] = {
                "key": r.concept_family,
                "label": fam.label if fam else r.concept_family,
                "board_unit": r.board_unit,
                "board_weight_pct": weight,
                "frequency_multiplier": mult,
                "urgency": score,
                #: same VERY HIGH/HIGH/MEDIUM/LOW badge as GET /board-frequency, keyed to
                #: the same share-of-eligible-years the multiplier itself came from -- a
                #: family with no row (row is None) has nothing to badge, same as note.
                "urgency_tier": urgency_tier(row.years_appeared, row.years_eligible) if row else None,
                "years_appeared": row.years_appeared if row else None,
                "years_eligible": row.years_eligible if row else None,
                "note": frequency_note(row) if row else None,
            }
    ordered = sorted(shown.values(), key=lambda d: -(d["urgency"] or 0.0))
    return ordered, priority


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


def _empty_bands() -> dict[str, int]:
    return {"full_mastery": 0, "band_80_89": 0, "band_60_79": 0, "below_60": 0}


def _band_of(pct: float) -> str:
    """The cohort report's four score bands -- one definition, used for the paper-wide
    band_counts and every subject's own band_counts alike."""
    if pct >= 90:
        return "full_mastery"
    if pct >= 80:
        return "band_80_89"
    if pct >= 60:
        return "band_60_79"
    return "below_60"


def _band_counts_by_student(rows: list[MarkRow]) -> dict[str, int]:
    """How many students land in each band on one paper's counted rows."""
    earned: dict[str, float] = {}
    available: dict[str, float] = {}
    for r in rows:
        if not r.counts:
            continue
        earned[r.student_id] = earned.get(r.student_id, 0.0) + r.earned
        available[r.student_id] = available.get(r.student_id, 0.0) + r.max_marks
    out = _empty_bands()
    for sid, mx in available.items():
        if mx > 0:
            out[_band_of(earned[sid] / mx * 100)] += 1
    return out


@router.get("/cohort/{assessment_id}")
def cohort_report(
    assessment_id: str,
    section_id: str | None = None,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """How the whole class did on one paper -- the principal/admin view, every section.
    See _cohort_report_payload for what this actually computes."""
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != school.id:
        raise HTTPException(404, "not found")
    return _cohort_report_payload(db, school, assessment, section_id)


@router.get("/teacher/cohort/{assessment_id}")
def teacher_cohort_report(
    assessment_id: str,
    section_id: str,
    staff: Staff = Depends(current_staff),
    db: Session = Depends(get_session),
) -> dict:
    """The same real findings a principal's own cohort report shows, scoped down to one
    teacher key's own section -- require_reader refuses every teacher key outright (this
    surface has no section/subject filter of its own), so a teacher never had a route to
    this data at all until now. section_id is required here, not optional like the
    principal route's, because a teacher's read is always scoped to one class they
    actually hold -- there is no "every section" view for a key that was never issued one.
    """
    if not staff.is_teacher:
        raise HTTPException(403, "this route is for teacher keys; use /reports/cohort/{id}")
    assert staff.home is not None, "a teacher key always names its school"
    school = staff.home
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.school_id != school.id:
        raise HTTPException(404, "not found")
    require_teacher_read_scope(staff, db, section_id, assessment.subject_code)
    return _cohort_report_payload(db, school, assessment, section_id)


def _cohort_report_payload(
    db: Session, school: School, assessment: Assessment, section_id: str | None,
) -> dict:
    """How the whole class did on one paper, not just one student.

    ``_rows`` already reads every (student, question) mark on this assessment in one
    call -- the per-student report just happened to filter it down to one student before
    now. Every figure below is that same data, grouped differently: never a fabricated
    cohort number standing in for one this deployment cannot actually compute.

    Three real aggregations, one honest approximation:
      * performance bands and section averages -- exact, from this paper's own marks
      * marks lost per concept family, reusing the same board-urgency scoring a
        per-student report already computes -- exact
      * "Performance by Subject" -- there is no schema concept of several subjects'
        papers belonging to one shared "test occasion" (a Unit Test spanning Maths,
        Physics, Chemistry...), so this compares each subject's own *most recent* graded
        assessment for the same section(s) instead, and says so in the response rather
        than implying a shared sitting that was never recorded.

    ``section_id`` narrows every figure above to one class's own students -- the same
    real aggregation, just over a smaller ``rows``, so a Class detail screen can show
    this class's own top losses rather than the whole school's. Omitted, this behaves
    exactly as it always has.
    """
    rows = _rows(db, assessment)
    if section_id:
        in_section = set(db.scalars(
            select(StudentProfile.id).where(
                StudentProfile.school_id == school.id, StudentProfile.section_id == section_id,
            )
        ))
        rows = [r for r in rows if r.student_id in in_section]
    if not rows:
        raise HTTPException(404, "no marks entered for this assessment yet")

    by_student: dict[str, list[MarkRow]] = {}
    for r in rows:
        by_student.setdefault(r.student_id, []).append(r)

    section_of = dict(db.execute(
        select(StudentProfile.id, StudentProfile.section_id)
        .where(StudentProfile.id.in_(by_student))
    ).all())
    sections = {
        s.id: s for s in db.scalars(
            select(Section).where(Section.id.in_(set(section_of.values())))
        )
    }

    band_counts = _empty_bands()
    section_totals: dict[str, list[float]] = {}
    student_pct: dict[str, float] = {}
    for sid, srows in by_student.items():
        counted = [r for r in srows if r.counts]
        total_max = sum(r.max_marks for r in counted)
        if total_max <= 0:
            continue
        pct = sum(r.earned for r in counted) / total_max * 100
        student_pct[sid] = pct
        band_counts[_band_of(pct)] += 1
        sec_id = section_of.get(sid)
        if sec_id:
            section_totals.setdefault(sec_id, []).append(pct)

    students_analysed = len(student_pct)
    band_pct = {
        k: round(v / students_analysed * 100) if students_analysed else 0
        for k, v in band_counts.items()
    }

    section_bars = sorted(
        (
            {
                "section_id": sec_id,
                "label": f"{sections[sec_id].grade}-{sections[sec_id].name}" if sec_id in sections else "?",
                "pct": round(sum(vals) / len(vals), 1),
                "students": len(vals),
            }
            for sec_id, vals in section_totals.items()
        ),
        key=lambda r: r["label"],
    )

    # Marks lost per concept family, across every student who sat this paper -- the same
    # board-urgency scoring _board_urgency already gives a single student's report, here
    # summed across the whole cohort instead of read for one.
    nodes_by_code = {n.code: n for n in db.scalars(select(TaxonomyNode))}
    lost_by_family: dict[str, dict] = {}
    for r in rows:
        if not r.counts or not r.concept_family:
            continue
        lost = r.max_marks - r.earned
        entry = lost_by_family.setdefault(
            r.concept_family, {"lost": 0.0, "students": set(), "board_unit": r.board_unit}
        )
        entry["lost"] += lost
        if lost > 0:
            entry["students"].add(r.student_id)

    urgency_by_family = {row["key"]: row for row in _board_urgency(db, assessment, rows)[0]}

    def _loss_confidence(affected: int, analysed: int) -> str:
        # Same evidence floor and Wilson interval this module already uses for a single
        # student's own findings (see confidence_tier's own docstring): under 2 students
        # affected is "insufficient evidence in this paper", never a percentage dressed up
        # as a tier.
        sufficient = affected >= 2 and analysed > 0
        ci = wilson_interval(affected, analysed) if sufficient else None
        return confidence_tier(sufficient, ci)

    top_losses = sorted(
        (
            {
                "concept_family": fam_code,
                "label": nodes_by_code[fam_code].label if fam_code in nodes_by_code else fam_code,
                "students_affected": len(entry["students"]),
                "avg_marks_lost": round(entry["lost"] / len(entry["students"]), 1),
                "board_urgency": (urgency_by_family.get(fam_code) or {}).get("urgency_tier"),
                "confidence": _loss_confidence(len(entry["students"]), students_analysed),
            }
            for fam_code, entry in lost_by_family.items() if entry["students"]
        ),
        key=lambda d: -(d["avg_marks_lost"] * d["students_affected"]),
    )

    # "Performance by Subject": no shared "test occasion" exists in this schema linking
    # several subjects' papers as one sitting, so this is each subject's own most recent
    # graded assessment for the same section(s) -- a real number, just not the same thing
    # a school's own internal "Unit Test 2" label would mean.
    from app.api.academics import _subject_label  # local: avoids a circular import at module load

    subject_bars = [{
        "subject_code": assessment.subject_code,
        "subject_label": _subject_label(assessment.subject_code),
        "assessment_id": assessment.id,
        "assessment_title": assessment.title,
        "pct": round(sum(student_pct.values()) / students_analysed, 1) if students_analysed else 0,
        # The same four bands as the paper-wide band_counts above, for this subject --
        # here literally the same students, so these always equal band_counts.
        "band_counts": dict(band_counts),
    }]
    if section_totals:
        cohort_ids = set(db.scalars(
            select(StudentProfile.id).where(StudentProfile.section_id.in_(section_totals))
        ))
        seen_subjects = {assessment.subject_code}
        for sibling in db.scalars(
            select(Assessment)
            .where(Assessment.school_id == school.id, Assessment.id != assessment.id)
            .order_by(Assessment.created_at.desc())
        ):
            if sibling.subject_code in seen_subjects:
                continue
            sibling_rows = [
                r for r in _rows(db, sibling) if r.student_id in cohort_ids and r.counts
            ]
            total_max = sum(r.max_marks for r in sibling_rows)
            if total_max <= 0:
                continue
            subject_bars.append({
                "subject_code": sibling.subject_code,
                "subject_label": _subject_label(sibling.subject_code),
                "assessment_id": sibling.id,
                "assessment_title": sibling.title,
                "pct": round(sum(r.earned for r in sibling_rows) / total_max * 100, 1),
                "band_counts": _band_counts_by_student(sibling_rows),
            })
            seen_subjects.add(sibling.subject_code)
    subject_bars.sort(key=lambda d: d["subject_code"])

    return {
        "assessment_id": assessment.id,
        "assessment_title": assessment.title,
        "students_analysed": students_analysed,
        "band_counts": band_counts,
        "band_pct": band_pct,
        "section_bars": section_bars,
        "subject_bars": subject_bars,
        "top_losses": top_losses[:5],
        "subject_bars_note": (
            "Each subject's own most recent graded assessment for the same section(s) -- "
            "this schema has no concept of several subjects sharing one test occasion."
        ),
    }


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

    from app.api.academics import _subject_label  # local: avoids a circular import at module load

    return {
        "student": {"id": student.id, "name": student.name, "roll_no": student.roll_no},
        "assessments": [
            {
                "assessment_id": aid,
                "title": title,
                "subject_code": subject,
                "subject_label": _subject_label(subject),
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
    board_urgency, priority = _board_urgency(db, a, rows)
    by_family = {u["key"]: u for u in board_urgency}

    counted = [r for r in rows if r.counts]
    earned = sum(r.earned for r in counted)
    available = sum(r.max_marks for r in counted)

    # A finding is keyed by a taxonomy code, which is what makes it stable across cycles
    # and useless to a reader. The label travels with it so a screen never has to guess a
    # name from a code, and never shows the code to a teacher.
    all_nodes = list(db.scalars(select(TaxonomyNode)))
    labels = {n.code: n.label for n in all_nodes}
    nodes_by_code = {n.code: n for n in all_nodes}
    nodes_by_id = {n.id: n for n in all_nodes}

    def _chapter_of(code: str) -> str | None:
        """Which chapter a topic/concept-family/sub-topic belongs to, so a finding never
        names a concept with no book context to place it in -- "Finding the mean of
        ungrouped data" means nothing to a parent without "Statistics" in front of it.
        Walks the taxonomy's own parent chain rather than guessing from the code's
        dotted prefix, which is the codes' internal shape, not a promise about depth."""
        node = nodes_by_code.get(code.split("|")[0])
        seen = set()
        while node is not None and node.id not in seen:
            if node.kind == "chapter":
                return node.label
            seen.add(node.id)
            node = nodes_by_id.get(node.parent_id) if node.parent_id else None
        return None

    def named(findings, *, why: bool = False) -> list[dict]:
        out = []
        for f in findings:
            row = f.as_dict()
            row["label"] = labels.get(row["key"], row["key"])
            row["chapter"] = _chapter_of(row["key"])
            if why:
                # Why this topic is on the focus list, in the teacher's terms: the unit's
                # weight, and how often the board has actually asked it.
                u = by_family.get(row["key"].split("|")[0])
                row["board"] = {
                    "board_unit": u["board_unit"], "board_weight_pct": u["board_weight_pct"],
                    "frequency_multiplier": u["frequency_multiplier"], "urgency": u["urgency"],
                    #: VERY HIGH/HIGH/MEDIUM/LOW, the same badge GET /board-frequency and
                    #: the cohort report already show -- the raw `urgency` score above is
                    #: not itself a label a principal should read off a screen.
                    "urgency_tier": u["urgency_tier"], "note": u["note"],
                } if u else None
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
        # Ranked by board urgency: a topic the board asks every year outranks one it
        # asked once, when the student lost the same share of marks on both.
        "focus": named(select_findings(topics, weights, priority=priority), why=True),
        "tier_summary": named(by_tier(rows)),
        "findings": named(select_findings(crosstab, weights, priority=priority), why=True),
        "all_crosstab": named(crosstab),
        "board_weighted_indicators": [
            {**i, "label": labels.get(i["board_unit"], i["board_unit"])} for i in indicators
        ],
        "coverage_gaps": [
            {**g.__dict__, "label": labels.get(g.board_unit, g.board_unit)} for g in gaps
        ],
        # Board urgency per family: the unit's published weight times how often the
        # family has actually come up on real board papers. Empty until board papers
        # have been mapped for this subject, and never a number below the plain weight.
        "board_urgency": board_urgency,
        "not_offered": [r.address for r in rows if r.state == "not_offered"],
    }


@router.get("/student/{student_id}/boardx")
def student_boardx_report(
    student_id: str,
    assessment_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """The BoardX v2 one-page student report: 'AVAI BoardX Student Report -- Vision-
    Aligned Composition & Rule Engine v2'. Composed entirely from the same evidence
    student_report() above already computes -- see app.analysis.boardx_report for the
    frozen-string composition and the audit pass every report is checked against before
    it is returned.
    """
    from app.analysis.boardx_report import compose_boardx_report

    a = db.get(Assessment, assessment_id)
    if a is None or a.school_id != school.id:
        raise HTTPException(404, "not found")
    student = db.get(StudentProfile, student_id)
    if student is None or student.school_id != school.id:
        raise HTTPException(404, "not found")
    rows = [r for r in _rows(db, a) if r.student_id == student_id]
    if not rows:
        raise HTTPException(404, "no marks for this student")
    return compose_boardx_report(db, a, student, rows)


@router.get("/student/{student_id}/boardx.pdf")
def student_boardx_pdf(
    student_id: str,
    assessment_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> Response:
    """The same BoardX v2 one-pager, rendered as an actual PDF file -- for a principal or
    teacher to hand a parent, same "print exactly what was composed" rule the plain
    issued-report PDF already follows."""
    from app.analysis.boardx_report import compose_boardx_report, render_boardx_pdf

    a = db.get(Assessment, assessment_id)
    if a is None or a.school_id != school.id:
        raise HTTPException(404, "not found")
    student = db.get(StudentProfile, student_id)
    if student is None or student.school_id != school.id:
        raise HTTPException(404, "not found")
    rows = [r for r in _rows(db, a) if r.student_id == student_id]
    if not rows:
        raise HTTPException(404, "no marks for this student")
    report = compose_boardx_report(db, a, student, rows)

    section = db.get(Section, student.section_id)
    class_label = f"Class {section.grade}-{section.name}" if section else ""
    pdf_bytes = render_boardx_pdf(
        report, roll_no=student.roll_no, class_label=class_label, school_name=school.name,
    )
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{student.name}-boardx.pdf"'},
    )


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


def _report_pdf_bytes(record: StudentReport, student: StudentProfile, school: School) -> bytes:
    """The one real PDF generator for an issued report, shared by the HTTP download route
    and the WhatsApp send path below -- so a report a parent gets over WhatsApp is byte-
    for-byte the same PDF the download button would have handed a principal, never a
    second, drifting rendering of the same payload.
    """
    try:
        return render_student_report_pdf(
            record, student_name=student.name, roll_no=student.roll_no, school_name=school.name,
        )
    except ModuleNotFoundError as exc:
        raise HTTPException(
            501, "PDF generation is not available on this deployment (fpdf2 is not installed)",
        ) from exc


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

    pdf_bytes = _report_pdf_bytes(record, student, school)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="report-{student.roll_no}-{record.id[:8]}.pdf"',
            "Cache-Control": "private, max-age=3600",
        },
    )


def _run_whatsapp_send(send_id: str) -> None:
    """The slow part of a WhatsApp send, run after the request that queued it has
    already returned -- same shape as _run_gridsheet_job: two short-lived sessions, never
    one held open across the network calls, and every failure caught and written to the
    row rather than allowed to strand it at 'pending' forever.

    Never fabricates a result: whatever Meta's real API genuinely returns -- a message id
    on success, or a real structured error -- is what this writes. With placeholder
    credentials this will genuinely call Meta and genuinely fail with Meta's own error
    (e.g. an invalid access token), which is correct, not a bug, until Meta Business
    verification and a real WhatsApp Business number exist.
    """
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        send = db.get(WhatsAppSend, send_id)
        if send is None:
            return
        record = db.get(StudentReport, send.report_id)
        if record is None:
            send.status, send.error_detail = "failed", "the report this send was for no longer exists"
            send.status_updated_at = datetime.now(UTC)
            db.commit()
            return
        student = db.get(StudentProfile, record.student_id)
        school = db.get(School, record.school_id)
        if student is None or school is None:
            send.status = "failed"
            send.error_detail = "the student or school this report belonged to no longer exists"
            send.status_updated_at = datetime.now(UTC)
            db.commit()
            return
        pdf_bytes = _report_pdf_bytes(record, student, school)
        assessment = db.get(Assessment, record.assessment_id)
        test_title = record.payload.get("assessment_title") or (assessment.title if assessment else "test")
        to = send.parent_whatsapp
        settings = get_settings()
        template_name, language = settings.whatsapp_template_name, settings.whatsapp_template_language
    finally:
        db.close()  # released before the slow HTTP calls below, not held across them

    try:
        client = WhatsAppClient(
            phone_number_id=settings.whatsapp_phone_number_id or "",
            access_token=settings.whatsapp_access_token or "",
        )
        media_id = client.upload_media(pdf_bytes, f"report-{student.roll_no}.pdf")
        response = client.send_document_template(
            to=to, media_id=media_id, template_name=template_name, language=language,
            params={
                "parent_name": "Parent/Guardian",
                "school_name": school.name,
                "student_name": student.name,
                "test_title": test_title,
            },
        )
        message_id = (response.get("messages") or [{}])[0].get("id")
        if not message_id:
            raise WhatsAppAPIError(f"Meta accepted the send but returned no message id: {response!r}")
    except (WhatsAppAPIError, ValueError, Exception) as exc:  # noqa: BLE001 -- never strand at pending
        logger.exception("whatsapp send %s: failed", send_id)
        db = SessionLocal()
        try:
            send = db.get(WhatsAppSend, send_id)
            if send is not None:
                send.status = "failed"
                send.error_detail = str(exc)
                send.status_updated_at = datetime.now(UTC)
                db.commit()
        finally:
            db.close()
        return

    db = SessionLocal()
    try:
        send = db.get(WhatsAppSend, send_id)
        if send is not None:
            send.status = "sent"
            send.meta_message_id = message_id
            send.sent_at = datetime.now(UTC)
            send.status_updated_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()


def _whatsapp_send_view(send: WhatsAppSend) -> dict:
    return {
        "send_id": send.id,
        "report_id": send.report_id,
        "status": send.status,
        "meta_message_id": send.meta_message_id,
        "error_detail": send.error_detail,
        "sent_at": send.sent_at.isoformat() if send.sent_at else None,
        "status_updated_at": send.status_updated_at.isoformat() if send.status_updated_at else None,
    }


@router.post("/issued/{report_id}/whatsapp", status_code=202)
def send_issued_report_whatsapp(
    report_id: str,
    background_tasks: BackgroundTasks,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """Send this issued report's PDF to the student's parent over WhatsApp, via Meta's
    Cloud API direct (no BSP -- see app.integrations.whatsapp). Additive to, and separate
    from, share_pin_hash's student-facing sharing above: this is a parent notification.

    Real, not simulated: this queues a background task that genuinely calls Meta's Media
    Upload and Messages APIs and genuinely surfaces whatever Meta's own API returns --
    including a real, honest failure if this deployment's Meta credentials are still
    placeholder (pre Business-verification). Never a fabricated 'sent'.

    422s, rather than queuing a job that will predictably fail later, when there is no
    parent WhatsApp number on file at all -- the one condition this endpoint can already
    know is hopeless before ever calling Meta.
    """
    record = db.get(StudentReport, report_id)
    if record is None or record.school_id != school.id:
        raise HTTPException(404, "not found")
    student = db.get(StudentProfile, record.student_id)
    if student is None:
        raise HTTPException(404, "the student this report was issued for no longer exists")
    if not student.parent_whatsapp:
        raise HTTPException(
            422, "no parent WhatsApp number is on file for this student -- add one first",
        )

    send = WhatsAppSend(
        school_id=school.id, report_id=record.id, parent_whatsapp=student.parent_whatsapp,
        status="pending",
    )
    db.add(send)
    db.commit()
    db.refresh(send)
    background_tasks.add_task(_run_whatsapp_send, send.id)
    return {
        **_whatsapp_send_view(send),
        "next": f"Poll GET /reports/issued/{report_id}/whatsapp for the result.",
    }


@router.get("/issued/{report_id}/whatsapp")
def get_issued_report_whatsapp_status(
    report_id: str,
    school: School = Depends(require_reader),
    db: Session = Depends(get_session),
) -> dict:
    """The most recent WhatsApp send attempted for this report -- what the frontend polls
    after send_issued_report_whatsapp queues one."""
    record = db.get(StudentReport, report_id)
    if record is None or record.school_id != school.id:
        raise HTTPException(404, "not found")
    send = db.scalar(
        select(WhatsAppSend)
        .where(WhatsAppSend.report_id == report_id, WhatsAppSend.school_id == school.id)
        .order_by(WhatsAppSend.created_at.desc())
    )
    if send is None:
        raise HTTPException(404, "no WhatsApp send has been attempted for this report yet")
    return _whatsapp_send_view(send)


@webhook_router.get("/webhooks/whatsapp")
def verify_whatsapp_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
) -> PlainTextResponse:
    """Meta's own one-time verification handshake, required when this URL is first
    registered as a webhook in the Meta App Dashboard: Meta calls this with a random
    challenge and a verify token, and expects the challenge echoed back verbatim, but
    only if the token matches what this deployment configured (YAADHUM_WHATSAPP_
    WEBHOOK_VERIFY_TOKEN) -- otherwise anyone could point Meta's own webhook registration
    at a URL of their choosing.
    """
    settings = get_settings()
    expected = settings.whatsapp_webhook_verify_token
    if hub_mode != "subscribe" or not expected or hub_verify_token != expected:
        raise HTTPException(403, "verification token mismatch")
    return PlainTextResponse(hub_challenge)


def _verify_whatsapp_signature(body: bytes, header_signature: str, app_secret: str) -> bool:
    """Real HMAC-SHA256 verification of Meta's X-Hub-Signature-256 header -- Meta signs
    every webhook delivery with the app secret so a receiver can tell a real Meta call
    from anyone else's forged POST to the same public URL. hmac.compare_digest, not `==`,
    so this cannot be timed to leak the correct signature byte by byte.
    """
    if not header_signature.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_signature[len("sha256="):])


@webhook_router.post("/webhooks/whatsapp")
async def receive_whatsapp_webhook(request: Request, db: Session = Depends(get_session)) -> dict:
    """Meta's delivery/read-status callback for a message this deployment sent. Updates
    the matching WhatsAppSend row (by meta_message_id) to 'delivered' or 'read' -- never
    forward-guessed, only ever what Meta's own payload actually claims.

    Rejects (401) any payload whose signature does not verify -- an unverified webhook
    would let anyone forge a delivery-status update for any message id they could guess
    or observe, which is exactly the kind of ungrounded status this codebase's zero-
    fabrication rule exists to prevent.
    """
    settings = get_settings()
    body = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    if not settings.whatsapp_app_secret or not _verify_whatsapp_signature(
        body, signature, settings.whatsapp_app_secret,
    ):
        raise HTTPException(401, "signature verification failed")

    payload = json.loads(body)
    updated = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for status_update in change.get("value", {}).get("statuses", []):
                message_id = status_update.get("id")
                meta_status = status_update.get("status")  # sent/delivered/read/failed
                if not message_id or meta_status not in ("delivered", "read", "failed"):
                    continue
                send = db.scalar(select(WhatsAppSend).where(WhatsAppSend.meta_message_id == message_id))
                if send is None:
                    continue
                send.status = meta_status
                if meta_status == "failed":
                    errors = status_update.get("errors") or []
                    send.error_detail = "; ".join(
                        e.get("title", "") for e in errors
                    ) or "Meta reported this message failed to deliver"
                send.status_updated_at = datetime.now(UTC)
                updated += 1
    db.commit()
    return {"updated": updated}


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
    alpha = cronbach_alpha(scores, sorted(maxes))
    alignment = typology_alignment(marks_by_tier)
    return {
        "assessment_id": a.id,
        "students": len(scores),
        "items": [s.__dict__ for s in stats],
        "flagged_items": [s.address for s in stats if s.flag],
        "cronbach_alpha": alpha,
        "typology_alignment": alignment.as_dict(),
        #: STRONG/MODERATE/LIMITED, and the two application/higher-order shares a
        #: principal actually asks for -- both read straight off typology_alignment's own
        #: `observed` tier shares (AP = Applying, AEC = Analysing/Evaluating/Creating), so
        #: this can never disagree with the verdict text sitting right next to it.
        "diagnostic_strength": diagnostic_strength_tier(alignment.alignment_score, alpha),
        "application_share": alignment.observed.get("AP"),
        "higher_order_share": alignment.observed.get("AEC"),
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
