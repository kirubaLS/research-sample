"""E10 (class-wide) and E12 (school-wide) promotion."""
from __future__ import annotations

from .insight import (
    InsightObject, InsightType, SubjectScope, Band, MarksAtStake, ReportLanguage,
    Action,
)
from . import constants as C


def class_wide_promote(
    student_objects: list[InsightObject],
    students_who_sat: list[str],
    class_id: str,
) -> InsightObject | None:
    """`student_objects`: the student-scope objects of one insight_type on one
    domain/variant, across a class. Not eligible: Diffuse Signal (E7.7)."""
    if not student_objects:
        return None
    insight_type = student_objects[0].insight_type
    if insight_type == InsightType.DIFFUSE_SIGNAL:
        return None  # not promotable

    n_sat = len(students_who_sat)
    if n_sat < C.MIN_CLASS_SIZE:
        return None

    contributing_ids = {o.subject_id for o in student_objects}
    m = len(contributing_ids)
    share = m / n_sat
    if share < C.CLASS_WIDE_THRESHOLD:
        return None

    absent = 0  # students_who_sat already excludes absentees per B4
    absence_rate = 0.0

    obs_bands = [o.confidence.observation for o in student_objects]
    order = {Band.HIGH: 3, Band.MEDIUM: 2, Band.LOW: 1, Band.NONE: 0}
    worst = min(obs_bands, key=lambda b: order[b])
    # Class scope lifts the student-scope cap: may reach HIGH, so use the
    # strongest common signal rather than re-deriving caps here — take the
    # modal/best band actually observed, capped only by absence.
    band = max(obs_bands, key=lambda b: order[b])
    if absence_rate > C.MAX_ABSENCE_RATE:
        band = Band.MEDIUM if order[band] > order[Band.MEDIUM] else band

    base = student_objects[0]

    def compose(register_text: str) -> str:
        if register_text == "NOT_ISSUED":
            return register_text
        line = f" {m} of the {n_sat} students who sat this paper show this pattern."
        if absence_rate > C.MAX_ABSENCE_RATE:
            line += f" {absent} students were absent and are excluded from both figures."
        return register_text + line

    total_lost = 0
    total_available = 0
    all_int = True
    for o in student_objects:
        if isinstance(o.marks_at_stake.lost, int):
            total_lost += o.marks_at_stake.lost
            total_available += o.marks_at_stake.available
        else:
            all_int = False
        # constituent student objects are set aggregable=false (E10)
        o.marks_at_stake = MarksAtStake(o.marks_at_stake.lost, o.marks_at_stake.available,
                                         o.marks_at_stake.basis, aggregable=False)

    marks = MarksAtStake(
        total_lost if all_int else "NOT_APPLICABLE",
        total_available if all_int else "NOT_APPLICABLE",
        f"Summed across the {m} contributing students.",
        aggregable=True,
    )

    reason = base.confidence.reason + f" Class-wide: {m} of {n_sat} students ({share:.0%})."

    promoted = InsightObject(
        insight_type=insight_type,
        subject_scope=SubjectScope.CLASS,
        analytical_scope=base.analytical_scope,
        domain=base.domain,
        subject_id=class_id,
        evidence=base.evidence,
        coverage=base.coverage,
        confidence=type(base.confidence)(band, base.confidence.attribution, reason),
        priority=base.priority,
        marks_at_stake=marks,
        alternative_explanations=base.alternative_explanations,
        action=base.action,
        report_language=ReportLanguage(
            compose(base.report_language.teacher),
            compose(base.report_language.parent),
            compose(base.report_language.student),
        ),
        variant=base.variant,
    )
    return promoted


def school_wide_promote(
    class_objects: list[InsightObject],
    classes_in_grade: list[str],
    grade_id: str,
) -> InsightObject | None:
    """`class_objects`: CLASS-scope objects of one insight_type on one domain,
    one per class, across a grade. No cross-subject pooling (M4)."""
    if not class_objects:
        return None
    insight_type = class_objects[0].insight_type
    if insight_type == InsightType.DIFFUSE_SIGNAL:
        return None

    if len(classes_in_grade) < C.MIN_CLASSES_FOR_SCHOOL:
        return None
    share = len(class_objects) / len(classes_in_grade)
    if share < C.SCHOOL_WIDE_THRESHOLD:
        return None

    base = class_objects[0]
    total_lost = 0
    total_available = 0
    all_int = True
    for o in class_objects:
        if isinstance(o.marks_at_stake.lost, int):
            total_lost += o.marks_at_stake.lost
            total_available += o.marks_at_stake.available
        else:
            all_int = False
        o.marks_at_stake = MarksAtStake(o.marks_at_stake.lost, o.marks_at_stake.available,
                                         o.marks_at_stake.basis, aggregable=False)

    marks = MarksAtStake(
        total_lost if all_int else "NOT_APPLICABLE",
        total_available if all_int else "NOT_APPLICABLE",
        f"Summed across the {len(class_objects)} contributing classes.",
        aggregable=True,
    )

    # No attribution: required companion line, teacher only.
    companion = (
        " This pattern is shared across classes in this grade. No cause is "
        "attributed to it."
    )
    teacher = base.report_language.teacher + companion

    reason = base.confidence.reason + (
        f" School-wide: fired at CLASS scope in {len(class_objects)} of "
        f"{len(classes_in_grade)} classes ({share:.0%})."
    )

    return InsightObject(
        insight_type=insight_type,
        subject_scope=SubjectScope.SCHOOL,
        analytical_scope=base.analytical_scope,
        domain=base.domain,
        subject_id=grade_id,
        evidence=base.evidence,
        coverage=base.coverage,
        confidence=type(base.confidence)(base.confidence.observation,
                                          base.confidence.attribution, reason),
        priority=base.priority,
        marks_at_stake=marks,
        alternative_explanations=base.alternative_explanations,
        action=Action.NONE,
        report_language=ReportLanguage(teacher, "NOT_ISSUED", "NOT_ISSUED"),
        variant=base.variant,
    )
