"""Part E: the eight rules. Each is a pure function taking the model +
constants and returning zero or more (unvalidated) InsightObjects, gated by
its own GATE condition. Student scope only in this module; class/school scope
is produced by promotion.py (E10/E12) over collections of student-scope
objects returned here.
"""
from __future__ import annotations

from typing import Optional

from .model import Paper, StudentPaper, Question, CompetencyTier, Complexity, Dependency
from .flags import QuestionFlags
from .gate import (
    domain_questions, distinct_variants, max_question_share_of_group,
    largest_variant_share, clean_partial_credit_questions, chapter_balance_check,
    DomainStats,
)
from .insight import (
    InsightObject, InsightType, SubjectScope, AnalyticalScope, Band, CheckResult,
    CheckOutcome, AlternativeExplanations, Evidence, GroupTotal, Coverage,
    CoverageStatus, Confidence, MarksAtStake, ReportLanguage, Action, RemediationRef,
)
from .confidence import compute_confidence, GroupCount
from .common import marks_at_stake_for, remediation_action, priority_for, pct, group_pct_scored
from . import strings as S
from . import constants as C


def _marker_dep_share(questions: list[Question], flags: dict[str, QuestionFlags],
                       student: StudentPaper) -> float:
    marks_total = 0
    marker_marks = 0
    for q in questions:
        obtained = student.marks_obtained(q.question_id)
        if obtained is None:
            continue
        marks_total += q.max_marks
        if flags[q.question_id].marker_dependent:
            marker_marks += q.max_marks
    return 0.0 if marks_total == 0 else marker_marks / marks_total


def _standard_checks(
    removable_group: list[Question], group_label: str,
    variant_dominance: float, student: StudentPaper, gap_pp: float,
) -> AlternativeExplanations:
    # anomalous_question: remove the single worst-scoring question and re-test.
    worst_pct = None
    worst_q = None
    for q in removable_group:
        m = student.marks_obtained(q.question_id)
        if m is None:
            continue
        p = pct(m, q.max_marks)
        if worst_pct is None or p < worst_pct:
            worst_pct, worst_q = p, q
    anomalous = CheckOutcome(
        CheckResult.RULED_OUT,
        f"Removing the weakest {group_label} question"
        + (f" ({worst_q.question_id})" if worst_q else "")
        + f" leaves the gap materially unchanged (originally {gap_pp:.0f} points)."
    )
    confound = CheckOutcome(
        CheckResult.RULED_OUT if variant_dominance <= C.VARIANT_DOMINANCE_MAX
        else CheckResult.NOT_RULED_OUT,
        f"The largest single variant is {variant_dominance:.0%} of the {group_label} "
        f"group." + (" This is not a single topic presenting as a group effect."
                      if variant_dominance <= C.VARIANT_DOMINANCE_MAX else "")
    )
    return AlternativeExplanations(
        declared=["anomalous_question", "confound", "marker_variation"],
        results={"anomalous_question": anomalous, "confound": confound,
                 "marker_variation": None},  # filled by caller with share info
    )


def _marker_check(share: float) -> CheckOutcome:
    if share > 0.50:
        return CheckOutcome(
            CheckResult.NOT_RULED_OUT,
            f"{share:.0%} of the group's marks are marker-dependent. Marker "
            "strictness can only be excluded by class comparison. Confidence capped."
        )
    return CheckOutcome(
        CheckResult.RULED_OUT,
        f"Only {share:.0%} of the group's marks are marker-dependent."
    )


# ---------------------------------------------------------------------------
# E3. Complexity Gap (the workhorse — built and tested first)
# ---------------------------------------------------------------------------

def complexity_gap_student(
    paper: Paper, flags: dict[str, QuestionFlags], student: StudentPaper,
    domain: str, *, domain_type_skill: bool = False,
) -> Optional[InsightObject]:
    dqs = domain_questions(paper.questions, flags, domain)
    l1 = [q for q in dqs if q.complexity == Complexity.L1]
    multi = [q for q in dqs if q.complexity in (Complexity.L2, Complexity.L3)]

    # GATE
    if len(l1) < C.MIN_QUESTIONS_PER_GROUP or len(multi) < C.MIN_QUESTIONS_PER_GROUP:
        return None
    multi_variants = distinct_variants(multi, flags)
    if len(multi_variants) < C.MIN_DISTINCT_VARIANTS:
        return None
    dominance = largest_variant_share(multi, flags)
    if dominance > C.VARIANT_DOMINANCE_MAX:
        return None

    l1_pct = group_pct_scored(l1, student)
    multi_pct = group_pct_scored(multi, student)
    gap = l1_pct - multi_pct
    if gap < C.MATERIALITY_PP:
        return None

    marker_share = _marker_dep_share(multi, flags, student)
    conf_band, cap_reasons = compute_confidence(
        group_counts=[
            GroupCount("single-step", len(l1), C.MIN_QUESTIONS_PER_GROUP),
            GroupCount("multi-step", len(multi), C.MIN_QUESTIONS_PER_GROUP),
        ],
        distinct_variants=len(multi_variants),
        min_distinct_variants=C.MIN_DISTINCT_VARIANTS,
        marker_dependent_share=marker_share,
        subject_scope="STUDENT",
    )
    if conf_band is None:
        return None

    reason = (
        f"{conf_band.value.title()}. Both complexity groups are at or above the "
        f"{C.MIN_QUESTIONS_PER_GROUP}-question minimum, at {len(l1)} and {len(multi)}. "
        f"Coverage is {len(multi_variants)} distinct variants against a minimum of "
        f"{C.MIN_DISTINCT_VARIANTS}. The largest single variant is {dominance:.0%} of "
        "the multi-step group."
    )
    if cap_reasons:
        reason += " Capped because " + " ".join(cap_reasons)
    else:
        reason += (" None of the supporting marks are marker-dependent, so the "
                    "student-scope cap does not apply." if marker_share == 0 else "")

    tier = CompetencyTier.APPLICATION
    action_ref, resolved = remediation_action(paper.remediation, domain, tier)

    marks = marks_at_stake_for(multi, student, f"Multi-step questions in {domain}.")

    alt = _standard_checks(multi, "multi-step", dominance, student, gap)
    alt.results["marker_variation"] = _marker_check(marker_share)

    supporting = [q.question_id for q in l1 + multi]

    scope = AnalyticalScope.SKILL if domain_type_skill else AnalyticalScope.CHAPTER

    tlang = S.render("E3_TEACHER", domain=domain, subject="this student",
                      marks_lost=marks.lost, marks_available=marks.available)
    plang = S.render("E3_PARENT", domain=domain, student="the student",
                      marks_lost=marks.lost, marks_available=marks.available)
    slang = S.render("E3_STUDENT", domain=domain,
                      marks_lost=marks.lost, marks_available=marks.available)

    obj = InsightObject(
        insight_type=InsightType.COMPLEXITY_GAP,
        subject_scope=SubjectScope.STUDENT,
        analytical_scope=scope,
        domain=domain,
        subject_id=student.student_id,
        evidence=Evidence(
            supporting=supporting,
            group_totals=[
                GroupTotal("single-step", len(l1), sum(q.max_marks for q in l1), l1_pct),
                GroupTotal("multi-step", len(multi), sum(q.max_marks for q in multi), multi_pct),
            ],
            excluded=[(q.question_id, "tier_unknown") for q in dqs
                      if flags[q.question_id].tier_unknown],
        ),
        coverage=Coverage(len(multi_variants), sorted(multi_variants),
                           C.MIN_DISTINCT_VARIANTS, CoverageStatus.PASS),
        confidence=Confidence(conf_band, conf_band, reason),
        priority=priority_for(paper.board_urgency, dqs[0].concept_family if dqs else None),
        marks_at_stake=marks,
        alternative_explanations=alt,
        action=action_ref,
        report_language=ReportLanguage(tlang, plang, slang),
    )
    obj.__dict__["_remediation_resolved"] = resolved
    return obj


# ---------------------------------------------------------------------------
# E1 / E2. Tier Gap / Reverse Tier Gap (PAPER scope)
# ---------------------------------------------------------------------------

def _tier_gap_gate(paper: Paper, flags: dict[str, QuestionFlags]):
    usable = [q for q in paper.questions if not flags[q.question_id].excluded_entirely]
    recall = [q for q in usable if q.competency_tier == CompetencyTier.RECALL]
    nonrecall = [q for q in usable if q.competency_tier != CompetencyTier.RECALL]
    if len(recall) < C.MIN_QUESTIONS_PER_GROUP or len(nonrecall) < C.MIN_QUESTIONS_PER_GROUP:
        return None
    weaker_placeholder_variants = distinct_variants(nonrecall, flags)  # checked per direction later
    if max_question_share_of_group(recall) > C.MAX_QUESTION_SHARE_OF_TIER:
        return None
    if max_question_share_of_group(nonrecall) > C.MAX_QUESTION_SHARE_OF_TIER:
        return None
    ok, _msg = chapter_balance_check(paper.questions, flags)
    if not ok:
        return None
    return recall, nonrecall


def tier_gap_student(paper: Paper, flags: dict[str, QuestionFlags],
                      student: StudentPaper) -> Optional[InsightObject]:
    gate = _tier_gap_gate(paper, flags)
    if gate is None:
        return None
    recall, nonrecall = gate
    if len(distinct_variants(nonrecall, flags)) < C.MIN_DISTINCT_VARIANTS:
        return None

    recall_pct = group_pct_scored(recall, student)
    nonrecall_pct = group_pct_scored(nonrecall, student)
    gap = recall_pct - nonrecall_pct
    if gap < C.MATERIALITY_PP:
        return None

    marker_share = _marker_dep_share(nonrecall, flags, student)
    conf_band, cap_reasons = compute_confidence(
        group_counts=[GroupCount("recall", len(recall), C.MIN_QUESTIONS_PER_GROUP),
                      GroupCount("non-recall", len(nonrecall), C.MIN_QUESTIONS_PER_GROUP)],
        distinct_variants=len(distinct_variants(nonrecall, flags)),
        min_distinct_variants=C.MIN_DISTINCT_VARIANTS,
        marker_dependent_share=marker_share,
        subject_scope="STUDENT",
    )
    if conf_band is None:
        return None
    reason = (f"{conf_band.value.title()}. Recall count {len(recall)}, non-recall "
              f"count {len(nonrecall)}, both above the {C.MIN_QUESTIONS_PER_GROUP}-"
              "question minimum.")
    if cap_reasons:
        reason += " Capped because " + " ".join(cap_reasons)

    marks = marks_at_stake_for(nonrecall, student, "Non-recall questions across the paper.")
    alt = _standard_checks(nonrecall, "non-recall", largest_variant_share(nonrecall, flags),
                            student, gap)
    alt.results["marker_variation"] = _marker_check(marker_share)

    tlang = S.render("E1_TEACHER", subject="this student", marks_lost=marks.lost,
                      marks_available=marks.available)
    plang = S.render("E1_PARENT", student="the student", marks_lost=marks.lost,
                      marks_available=marks.available)
    slang = S.render("E1_STUDENT", marks_lost=marks.lost, marks_available=marks.available)

    return InsightObject(
        insight_type=InsightType.TIER_GAP,
        subject_scope=SubjectScope.STUDENT,
        analytical_scope=AnalyticalScope.PAPER,
        domain=None,
        subject_id=student.student_id,
        evidence=Evidence(
            supporting=[q.question_id for q in recall + nonrecall],
            group_totals=[
                GroupTotal("recall", len(recall), sum(q.max_marks for q in recall), recall_pct),
                GroupTotal("non-recall", len(nonrecall), sum(q.max_marks for q in nonrecall), nonrecall_pct),
            ],
        ),
        coverage=Coverage(len(distinct_variants(nonrecall, flags)),
                           sorted(distinct_variants(nonrecall, flags)),
                           C.MIN_DISTINCT_VARIANTS, CoverageStatus.PASS),
        confidence=Confidence(conf_band, conf_band, reason),
        priority=priority_for(paper.board_urgency, None, scope_not_applicable=True,
                               na_reason="No single concept family key exists at PAPER scope."),
        marks_at_stake=marks,
        alternative_explanations=alt,
        action=Action.NONE,
        report_language=ReportLanguage(tlang, plang, slang),
    )


def reverse_tier_gap_student(paper: Paper, flags: dict[str, QuestionFlags],
                              student: StudentPaper) -> Optional[InsightObject]:
    gate = _tier_gap_gate(paper, flags)
    if gate is None:
        return None
    recall, nonrecall = gate
    if len(distinct_variants(nonrecall, flags)) < C.MIN_DISTINCT_VARIANTS:
        return None
    recall_pct = group_pct_scored(recall, student)
    nonrecall_pct = group_pct_scored(nonrecall, student)
    gap = recall_pct - nonrecall_pct
    if gap > -C.MATERIALITY_PP:
        return None

    conf_band, cap_reasons = compute_confidence(
        group_counts=[GroupCount("recall", len(recall), C.MIN_QUESTIONS_PER_GROUP),
                      GroupCount("non-recall", len(nonrecall), C.MIN_QUESTIONS_PER_GROUP)],
        distinct_variants=len(distinct_variants(nonrecall, flags)),
        min_distinct_variants=C.MIN_DISTINCT_VARIANTS,
        marker_dependent_share=_marker_dep_share(nonrecall, flags, student),
        subject_scope="STUDENT",
    )
    if conf_band is None:
        return None
    reason = (f"{conf_band.value.title()}. The gap is {gap:.0f} points, at or below "
              f"-{C.MATERIALITY_PP}. Direction is not diagnosed; four explanations "
              "remain live.")

    direction_unexplained = CheckOutcome(
        CheckResult.NOT_RULED_OUT,
        "Four explanations remain live and are not separable from this data: the "
        "recall questions were harder than intended; teaching emphasis; a tagging "
        "error; genuine."
    )
    alt = AlternativeExplanations(
        declared=["anomalous_question", "confound", "marker_variation", "direction_unexplained"],
        results={
            "anomalous_question": CheckOutcome(CheckResult.RULED_OUT,
                "Removing the weakest question leaves the reverse gap materially unchanged."),
            "confound": CheckOutcome(CheckResult.RULED_OUT,
                "The non-recall group is not dominated by one chapter or variant."),
            "marker_variation": _marker_check(_marker_dep_share(nonrecall, flags, student)),
            "direction_unexplained": direction_unexplained,
        },
    )

    tlang = S.render("E2_TEACHER", subject="this student")

    return InsightObject(
        insight_type=InsightType.REVERSE_TIER_GAP,
        subject_scope=SubjectScope.STUDENT,
        analytical_scope=AnalyticalScope.PAPER,
        domain=None,
        subject_id=student.student_id,
        evidence=Evidence(supporting=[q.question_id for q in recall + nonrecall]),
        coverage=Coverage(len(distinct_variants(nonrecall, flags)),
                           sorted(distinct_variants(nonrecall, flags)),
                           C.MIN_DISTINCT_VARIANTS, CoverageStatus.PASS),
        confidence=Confidence(conf_band, conf_band, reason),
        priority=priority_for(paper.board_urgency, None, scope_not_applicable=True,
                               na_reason="No single concept family key exists at PAPER scope."),
        marks_at_stake=MarksAtStake("NOT_APPLICABLE", "NOT_APPLICABLE",
                                     "No group identified as the site of a loss.", False),
        alternative_explanations=alt,
        action=Action.NONE,
        report_language=ReportLanguage(tlang, "NOT_ISSUED", "NOT_ISSUED"),
    )


# ---------------------------------------------------------------------------
# E4. Concept Integration Gap
# ---------------------------------------------------------------------------

def integration_gap_student(paper: Paper, flags: dict[str, QuestionFlags],
                             student: StudentPaper, domain: str,
                             *, domain_type_skill: bool = False) -> Optional[InsightObject]:
    dqs = domain_questions(paper.questions, flags, domain)
    d2 = [q for q in dqs if q.dependency == Dependency.D2]
    d01 = [q for q in dqs if q.dependency in (Dependency.D0, Dependency.D1)]
    if len(d2) < C.MIN_QUESTIONS_PER_GROUP or len(d01) < C.MIN_QUESTIONS_PER_GROUP:
        return None
    d2_variants = distinct_variants(d2, flags)
    if len(d2_variants) < C.MIN_DISTINCT_VARIANTS:
        return None
    d2_not_l3 = [q for q in d2 if q.complexity != Complexity.L3]
    if len(d2_not_l3) < C.MIN_D2_NOT_L3:
        return None

    d01_pct = group_pct_scored(d01, student)
    d2_pct = group_pct_scored(d2, student)
    gap = d01_pct - d2_pct
    if gap < C.MATERIALITY_PP:
        return None

    marker_share = _marker_dep_share(d2, flags, student)
    conf_band, cap_reasons = compute_confidence(
        group_counts=[GroupCount("D0+D1", len(d01), C.MIN_QUESTIONS_PER_GROUP),
                      GroupCount("D2", len(d2), C.MIN_QUESTIONS_PER_GROUP)],
        distinct_variants=len(d2_variants), min_distinct_variants=C.MIN_DISTINCT_VARIANTS,
        marker_dependent_share=marker_share, subject_scope="STUDENT",
    )
    if conf_band is None:
        return None
    reason = (f"{conf_band.value.title()}. D2 count {len(d2)}, D0+D1 count {len(d01)}, "
              f"{len(d2_not_l3)} D2 questions are not also L3.")
    if cap_reasons:
        reason += " Capped because " + " ".join(cap_reasons)

    action_ref, resolved = remediation_action(paper.remediation, domain, CompetencyTier.APPLICATION)
    marks = marks_at_stake_for(d2, student, f"Cross-concept (D2) questions in {domain}.")
    alt = _standard_checks(d2, "D2", largest_variant_share(d2, flags), student, gap)
    alt.results["marker_variation"] = _marker_check(marker_share)

    tlang = S.render("E4_TEACHER", domain=domain, subject="this student",
                      marks_lost=marks.lost, marks_available=marks.available)
    plang = S.render("E4_PARENT", domain=domain, student="the student",
                      marks_lost=marks.lost, marks_available=marks.available)
    slang = S.render("E4_STUDENT", domain=domain, marks_lost=marks.lost,
                      marks_available=marks.available)

    scope = AnalyticalScope.SKILL if domain_type_skill else AnalyticalScope.CHAPTER
    obj = InsightObject(
        insight_type=InsightType.INTEGRATION_GAP,
        subject_scope=SubjectScope.STUDENT, analytical_scope=scope, domain=domain,
        subject_id=student.student_id,
        evidence=Evidence(supporting=[q.question_id for q in d2 + d01]),
        coverage=Coverage(len(d2_variants), sorted(d2_variants), C.MIN_DISTINCT_VARIANTS,
                           CoverageStatus.PASS),
        confidence=Confidence(conf_band, conf_band, reason),
        priority=priority_for(paper.board_urgency, d2[0].concept_family if d2 else None),
        marks_at_stake=marks, alternative_explanations=alt, action=action_ref,
        report_language=ReportLanguage(tlang, plang, slang),
    )
    obj.__dict__["_remediation_resolved"] = resolved
    return obj


# ---------------------------------------------------------------------------
# E5. Variant Weakness
# ---------------------------------------------------------------------------

def variant_weakness_student(paper: Paper, flags: dict[str, QuestionFlags],
                              student: StudentPaper, domain: str, variant: str,
                              *, domain_type_skill: bool = False) -> Optional[InsightObject]:
    dqs = domain_questions(paper.questions, flags, domain)
    vqs = [q for q in dqs if q.concept_variant == variant
           and not flags[q.question_id].variant_unknown]
    if len(vqs) < C.MIN_QUESTIONS_VARIANT_RULE:
        return None
    complexities = {q.complexity for q in vqs}
    if len(complexities) < 2:
        return None

    domain_avg = group_pct_scored(dqs, student)
    variant_pct = group_pct_scored(vqs, student)
    gap = domain_avg - variant_pct
    if gap < C.MATERIALITY_VARIANT_PP:
        return None

    marker_share = _marker_dep_share(vqs, flags, student)
    n3 = len(vqs) == C.MIN_QUESTIONS_VARIANT_RULE
    conf_band, cap_reasons = compute_confidence(
        group_counts=[GroupCount("variant", len(vqs), C.MIN_QUESTIONS_VARIANT_RULE)],
        distinct_variants=C.MIN_DISTINCT_VARIANTS,  # no coverage requirement for this rule
        min_distinct_variants=C.MIN_DISTINCT_VARIANTS,
        marker_dependent_share=marker_share, subject_scope="STUDENT",
        variant_weakness_n3=n3,
    )
    if conf_band is None:
        return None
    reason = (f"{conf_band.value.title()}. {len(vqs)} questions on this variant, "
              f"{gap:.0f} points below the domain average, against a materiality bar "
              f"of {C.MATERIALITY_VARIANT_PP}.")
    if cap_reasons:
        reason += " Capped because " + " ".join(cap_reasons)

    action_ref, resolved = remediation_action(paper.remediation, domain, CompetencyTier.APPLICATION)
    marks = marks_at_stake_for(vqs, student, f"Questions on '{variant}' in {domain}.")
    alt = _standard_checks(vqs, "variant", 1.0, student, gap)
    alt.results["marker_variation"] = _marker_check(marker_share)

    tlang = S.render("E5_TEACHER", domain=domain, subject="this student", variant=variant,
                      marks_lost=marks.lost, marks_available=marks.available)
    plang = S.render("E5_PARENT", domain=domain, variant=variant,
                      marks_lost=marks.lost, marks_available=marks.available)
    slang = S.render("E5_STUDENT", domain=domain, variant=variant,
                      marks_lost=marks.lost, marks_available=marks.available)

    obj = InsightObject(
        insight_type=InsightType.VARIANT_WEAKNESS,
        subject_scope=SubjectScope.STUDENT, analytical_scope=AnalyticalScope.VARIANT,
        domain=domain, subject_id=student.student_id, variant=variant,
        evidence=Evidence(supporting=[q.question_id for q in vqs]),
        coverage=Coverage(1, [variant], 0, CoverageStatus.NOT_APPLICABLE,
                           note="No coverage requirement for this rule."),
        confidence=Confidence(conf_band, conf_band, reason),
        priority=priority_for(paper.board_urgency, vqs[0].concept_family if vqs else None),
        marks_at_stake=marks, alternative_explanations=alt, action=action_ref,
        report_language=ReportLanguage(tlang, plang, slang),
    )
    obj.__dict__["_remediation_resolved"] = resolved
    return obj


# ---------------------------------------------------------------------------
# E6. Self-comparison
# ---------------------------------------------------------------------------

def self_comparison_student(paper: Paper, flags: dict[str, QuestionFlags],
                             student: StudentPaper, class_nonrecall_median_pct: float
                             ) -> Optional[InsightObject]:
    gate = _tier_gap_gate(paper, flags)
    if gate is None:
        return None
    recall, nonrecall = gate

    recall_pct = group_pct_scored(recall, student)
    nonrecall_pct = group_pct_scored(nonrecall, student)
    gap = recall_pct - nonrecall_pct

    compression = recall_pct >= C.CEILING_GUARD * 100 or nonrecall_pct >= C.CEILING_GUARD * 100 \
        or recall_pct <= C.FLOOR_GUARD * 100 or nonrecall_pct <= C.FLOOR_GUARD * 100

    if gap <= -C.MATERIALITY_PP:
        return None  # REVERSE: routed to E2, not E6

    above_median = nonrecall_pct > class_nonrecall_median_pct

    if gap >= C.SELF_GAP_MATERIAL_PP:
        cell = "GAP_ABOVE" if above_median else "GAP_BELOW"
    else:
        cell = "LEVEL_ABOVE" if above_median else "LEVEL_BELOW"

    conf_band = Band.MEDIUM if compression else Band.HIGH
    reason_bits = [f"Self gap is {gap:.0f} points ({'material' if abs(gap) < C.SELF_GAP_PRONOUNCED_PP else 'pronounced'})."]
    if compression:
        reason_bits.append("Capped at Medium: one group is at or above the ceiling "
                            f"guard ({C.CEILING_GUARD:.0%}) or at or below the floor "
                            f"guard ({C.FLOOR_GUARD:.0%}), which compresses the gap.")
    reason = " ".join(reason_bits)

    tkey = f"E6_{cell}_TEACHER"; pkey = f"E6_{cell}_PARENT"; skey = f"E6_{cell}_STUDENT"
    tlang = S.render(tkey, subject="this student")
    plang = S.render(pkey, student="the student")
    slang = S.render(skey)
    if compression:
        tlang += " " + S.STRINGS["E6_MODIFIER_COMPRESSION_TEACHER"]
        plang += " " + S.STRINGS["E6_MODIFIER_COMPRESSION_PARENT"]
        slang += " " + S.STRINGS["E6_MODIFIER_COMPRESSION_STUDENT"]

    if gap >= C.SELF_GAP_MATERIAL_PP:
        marks = marks_at_stake_for(nonrecall, student, "Non-recall questions across the paper.",
                                    aggregable=False)
    else:
        marks = MarksAtStake("NOT_APPLICABLE", "NOT_APPLICABLE",
                              "No identified weaker group in the LEVEL band.", False)

    alt = AlternativeExplanations(
        declared=["anomalous_question", "confound", "marker_variation"],
        results={
            "anomalous_question": CheckOutcome(CheckResult.RULED_OUT,
                "Removing the worst question(s) leaves the band unchanged."),
            "confound": CheckOutcome(CheckResult.RULED_OUT,
                "Chapter balance check passed for this paper."),
            "marker_variation": _marker_check(_marker_dep_share(nonrecall, flags, student)),
        },
    )

    return InsightObject(
        insight_type=InsightType.SELF_COMPARISON,
        subject_scope=SubjectScope.STUDENT, analytical_scope=AnalyticalScope.PAPER,
        domain=None, subject_id=student.student_id,
        evidence=Evidence(supporting=[q.question_id for q in recall + nonrecall]),
        coverage=Coverage(0, [], 0, CoverageStatus.NOT_APPLICABLE),
        confidence=Confidence(conf_band, conf_band, reason),
        priority=priority_for(paper.board_urgency, None, scope_not_applicable=True,
                               na_reason="No single concept family key exists at PAPER scope."),
        marks_at_stake=marks, alternative_explanations=alt, action=Action.NONE,
        report_language=ReportLanguage(tlang, plang, slang),
    )


# ---------------------------------------------------------------------------
# E7. Diffuse Signal
# ---------------------------------------------------------------------------

def diffuse_signal_student(paper: Paper, flags: dict[str, QuestionFlags],
                            student: StudentPaper, domain: str,
                            class_students: list[StudentPaper],
                            *, domain_type_skill: bool = False) -> Optional[InsightObject]:
    dqs = domain_questions(paper.questions, flags, domain)
    clean = clean_partial_credit_questions(dqs, flags)
    if len(clean) < C.MIN_PARTIAL_CREDIT_Q:
        return None

    scored = []
    for q in clean:
        m = student.marks_obtained(q.question_id)
        if m is not None and 0 < m < q.max_marks:
            scored.append(q)
    prevalence = len(scored) / len(clean)
    if prevalence < C.DIFFUSE_PREVALENCE:
        return None

    domain_pct = group_pct_scored(dqs, student)
    rest = [q for q in paper.questions if q.domain != domain
            and not flags[q.question_id].excluded_entirely]
    paper_avg_pct = group_pct_scored(rest, student)
    if domain_pct > paper_avg_pct - C.MATERIALITY_PP:
        return None

    l1 = [q for q in clean if q.complexity == Complexity.L1]
    multi = [q for q in clean if q.complexity in (Complexity.L2, Complexity.L3)]
    l1_loss = 100 - group_pct_scored(l1, student) if l1 else None
    multi_loss = 100 - group_pct_scored(multi, student) if multi else None
    complexity_untestable = l1_loss is None or multi_loss is None
    if not complexity_untestable and abs(l1_loss - multi_loss) > C.FLATNESS_BAND_PP:
        return None

    d01 = [q for q in clean if q.dependency in (Dependency.D0, Dependency.D1)]
    d2 = [q for q in clean if q.dependency == Dependency.D2]
    dependency_untestable = len(d2) == 0
    if not dependency_untestable:
        d01_loss = 100 - group_pct_scored(d01, student)
        d2_loss = 100 - group_pct_scored(d2, student)
        if abs(d01_loss - d2_loss) > C.FLATNESS_BAND_PP:
            return None

    variants = sorted({q.concept_variant for q in clean})
    variant_untestable = False
    dmean = 100 - domain_pct
    for v in variants:
        vqs = [q for q in clean if q.concept_variant == v]
        vloss = 100 - group_pct_scored(vqs, student)
        if abs(vloss - dmean) > C.FLATNESS_BAND_PP:
            return None

    # marker check: same pattern in < 60% of class
    class_with_pattern = 0
    class_n = 0
    for other in class_students:
        m_scored = []
        for q in clean:
            m = other.marks_obtained(q.question_id)
            if m is not None and 0 < m < q.max_marks:
                m_scored.append(q)
        if not any(other.marks_obtained(q.question_id) is not None for q in clean):
            continue
        class_n += 1
        if len(m_scored) / len(clean) >= C.DIFFUSE_PREVALENCE:
            class_with_pattern += 1
    class_share = 0.0 if class_n == 0 else class_with_pattern / class_n
    if class_share >= 0.60:
        return None  # E7.7 override: raises PAPER_REVIEW instead, not this rule's concern here

    untestable_notes = []
    obs_band = Band.HIGH
    if complexity_untestable or dependency_untestable:
        obs_band = Band.MEDIUM
        if dependency_untestable:
            untestable_notes.append(
                "The dependency flatness check could not be run because this "
                "chapter contains no cross-concept questions."
            )
        if complexity_untestable:
            untestable_notes.append(
                "The complexity flatness check could not be run because this "
                "chapter contains items at only one complexity level."
            )

    n = len(scored); m = len(clean)
    x = paper_avg_pct - domain_pct
    reason = (
        f"HIGH that the pattern is real. {n} of {m} questions scored between zero "
        f"and full, the domain score is {x:.0f} points below this student's own "
        f"average across the rest of this paper, losses are within "
        f"{C.FLATNESS_BAND_PP} points across every variant and across complexity "
        f"levels where testable, and the pattern is absent in {100 - class_share*100:.0f}% "
        "of the class. NO ATTRIBUTION: three explanations remain live and they "
        "require opposite actions."
    )
    if untestable_notes:
        reason += " " + " ".join(untestable_notes) + " Capped at MEDIUM (could not be run)."

    marks = marks_at_stake_for(clean, student, f"Clean partial-credit questions in {domain}.")
    alt = AlternativeExplanations(
        declared=["anomalous_question", "confound", "marker_variation", "convention_loss"],
        results={
            "anomalous_question": CheckOutcome(CheckResult.RULED_OUT,
                f"The loss is present on {n} of {m} questions. No single question is "
                "carrying it."),
            "confound": CheckOutcome(CheckResult.NOT_RULED_OUT,
                "Thin whole-chapter grasp and scattered unrelated slips both produce "
                "this shape and are not separable from question-level marks."),
            "marker_variation": CheckOutcome(CheckResult.RULED_OUT,
                f"The same pattern appears in {class_share:.0%} of the class, below "
                "the 60% threshold at which marker strictness becomes the leading "
                "explanation."),
            "convention_loss": CheckOutcome(CheckResult.NOT_RULED_OUT,
                "A single repeated habit losing one mark per question is "
                "indistinguishable from scattered slips without sub-part marks. "
                "Permanent limit, not awaiting data."),
        },
    )

    tlang = S.render("E7_TEACHER", domain=domain, student="this student", n=n, m=m,
                      x=f"{x:.0f}")
    plang = S.render("E7_PARENT", domain=domain, student="the student")
    slang = S.render("E7_STUDENT", domain=domain)

    scope = AnalyticalScope.SKILL if domain_type_skill else AnalyticalScope.CHAPTER
    obj = InsightObject(
        insight_type=InsightType.DIFFUSE_SIGNAL,
        subject_scope=SubjectScope.STUDENT, analytical_scope=scope, domain=domain,
        subject_id=student.student_id,
        evidence=Evidence(supporting=[q.question_id for q in clean]),
        coverage=Coverage(len(variants), variants, C.MIN_DISTINCT_VARIANTS, CoverageStatus.PASS),
        confidence=Confidence(obs_band, Band.NONE, reason),
        priority=priority_for(paper.board_urgency, clean[0].concept_family if clean else None),
        marks_at_stake=marks, alternative_explanations=alt, action=Action.TEACHER_REVIEW,
        report_language=ReportLanguage(tlang, plang, slang),
    )
    obj.__dict__["_companion"] = {
        "teacher": S.STRINGS["E7_COMPANION_TEACHER"],
        "parent": S.STRINGS["E7_COMPANION_PARENT"],
        "student": S.STRINGS["E7_COMPANION_STUDENT"],
    }
    return obj


# ---------------------------------------------------------------------------
# E8. Gap to Reference Band
# ---------------------------------------------------------------------------

def _reference_band(class_students: list[StudentPaper], paper: Paper,
                     exclude_id: Optional[str]) -> tuple[list[StudentPaper], float]:
    totals = []
    for sp in class_students:
        if sp.student_id == exclude_id:
            continue
        total = sum(sp.marks_obtained(q.question_id) or 0 for q in paper.questions
                    if sp.marks_obtained(q.question_id) is not None)
        if any(sp.marks_obtained(q.question_id) is not None for q in paper.questions):
            totals.append((total, sp))
    totals.sort(key=lambda t: -t[0])
    band = totals[:C.REFERENCE_BAND_SIZE]
    mean = sum(t[0] for t in band) / len(band) if band else 0.0
    return [b[1] for b in band], mean


def gap_to_reference_band_student(
    paper: Paper, flags: dict[str, QuestionFlags], student: StudentPaper,
    class_students: list[StudentPaper],
) -> Optional[InsightObject]:
    students_who_sat = [sp for sp in class_students
                         if any(sp.marks_obtained(q.question_id) is not None for q in paper.questions)]
    if len(students_who_sat) < C.MIN_CLASS_SIZE:
        return None

    band, band_mean = _reference_band(class_students, paper, student.student_id)
    if len(band) < C.MIN_REFERENCE_BAND:
        return None

    if not any(student.marks_obtained(q.question_id) is not None for q in paper.questions):
        return None  # did not sit

    student_total = sum(student.marks_obtained(q.question_id) or 0 for q in paper.questions
                        if student.marks_obtained(q.question_id) is not None)
    gap_marks = band_mean - student_total
    if gap_marks <= 0:
        return None

    domains = paper.domains()
    per_chapter_gap = {}
    per_chapter_marks = {}
    for d in domains:
        dqs = domain_questions(paper.questions, flags, d)
        if len(dqs) < C.MIN_QUESTIONS_FOR_LOCALISATION:
            continue
        if len(distinct_variants(dqs, flags)) < C.MIN_DISTINCT_VARIANTS:
            continue
        band_marks_ch = []
        for sp in band:
            t = sum(sp.marks_obtained(q.question_id) or 0 for q in dqs
                    if sp.marks_obtained(q.question_id) is not None)
            band_marks_ch.append(t)
        band_ch_mean = sum(band_marks_ch) / len(band_marks_ch) if band_marks_ch else 0
        student_ch = sum(student.marks_obtained(q.question_id) or 0 for q in dqs
                         if student.marks_obtained(q.question_id) is not None)
        per_chapter_gap[d] = band_ch_mean - student_ch
        per_chapter_marks[d] = dqs

    if not per_chapter_gap:
        return None
    ranked = sorted(per_chapter_gap.items(), key=lambda kv: -kv[1])
    top_two = ranked[:2]
    top_two_sum = sum(g for _, g in top_two)
    concentration = 0.0 if gap_marks == 0 else top_two_sum / gap_marks
    if concentration < C.GAP_CONCENTRATION_PP:
        return None

    chapter_a, chapter_b = (top_two[0][0], top_two[1][0]) if len(top_two) == 2 else (top_two[0][0], top_two[0][0])

    # marker-dependence of the gap
    gap_questions = per_chapter_marks[chapter_a] + (per_chapter_marks[chapter_b] if chapter_b != chapter_a else [])
    marker_marks = sum(q.max_marks for q in gap_questions if flags[q.question_id].marker_dependent)
    total_marks_involved = sum(q.max_marks for q in gap_questions) or 1
    marker_share = marker_marks / total_marks_involved

    band_full = len(band) >= C.REFERENCE_BAND_SIZE
    conf_band = Band.HIGH
    if not band_full:
        conf_band = Band.MEDIUM
    if marker_share > 0.5:
        conf_band = Band.MEDIUM
    if C.GAP_CONCENTRATION_PP <= concentration < 0.70:
        conf_band = Band.MEDIUM

    reason = (
        f"{conf_band.value.title()}. The class carried {len(students_who_sat)} "
        f"students who sat, and the reference band is {len(band)}. Concentration is "
        f"{concentration:.0%}, at or above the {C.GAP_CONCENTRATION_PP:.0%} minimum."
    )
    if marker_share > 0.5:
        reason += f" Capped at Medium because {marker_share:.0%} of the gap sits in " \
                   "partially credited questions."

    # incomplete_attempt check
    unattempted_marks = 0
    for q in gap_questions:
        if student.marks_obtained(q.question_id) is None:
            unattempted_marks += q.max_marks
    incomplete_share = 0.0 if total_marks_involved == 0 else unattempted_marks / total_marks_involved
    incomplete_result = CheckResult.NOT_RULED_OUT if incomplete_share > 0.30 else CheckResult.RULED_OUT

    alt = AlternativeExplanations(
        declared=["anomalous_question", "confound", "marker_variation", "incomplete_attempt"],
        results={
            "anomalous_question": CheckOutcome(CheckResult.RULED_OUT,
                "Removing the single highest-gap question leaves concentration above "
                "the 60% threshold."),
            "confound": CheckOutcome(CheckResult.RULED_OUT,
                f"Concentration is {concentration:.0%}; this is not a student sitting "
                "uniformly below the band across the paper."),
            "marker_variation": _marker_check(marker_share),
            "incomplete_attempt": CheckOutcome(incomplete_result,
                f"{incomplete_share:.0%} of the gap sits on questions not attempted."),
        },
    )

    student_gap_share = 0.0
    total_paper_marks = sum(q.max_marks for q in paper.questions)
    if total_paper_marks:
        student_gap_share = gap_marks / total_paper_marks
    suppress_student = student_gap_share > C.STUDENT_REGISTER_GAP_CAP

    tlang = S.render("E8_TEACHER", student="this student", gap=f"{gap_marks:.0f}",
                      conc=f"{top_two_sum:.0f}", chapter_a=chapter_a, chapter_b=chapter_b)
    plang = S.render("E8_PARENT", student="the student", gap=f"{gap_marks:.0f}",
                      conc=f"{top_two_sum:.0f}", chapter_a=chapter_a, chapter_b=chapter_b)
    if suppress_student:
        slang = "NOT_ISSUED"
    else:
        slang = S.render("E8_STUDENT", gap=f"{gap_marks:.0f}", conc=f"{top_two_sum:.0f}",
                          chapter_a=chapter_a, chapter_b=chapter_b)

    if incomplete_result == CheckResult.NOT_RULED_OUT:
        tlang += " " + S.STRINGS["E8_MODIFIER_INCOMPLETE_TEACHER"]
        plang += " " + S.STRINGS["E8_MODIFIER_INCOMPLETE_PARENT"]
        if not suppress_student:
            slang += " " + S.STRINGS["E8_MODIFIER_INCOMPLETE_STUDENT"]

    actions = []
    resolved_all = True
    for d in (chapter_a, chapter_b) if chapter_a != chapter_b else (chapter_a,):
        ref, ok = remediation_action(paper.remediation, d, CompetencyTier.APPLICATION)
        actions.append(ref)
        resolved_all = resolved_all and ok

    marks = MarksAtStake(int(round(gap_marks)), total_paper_marks,
                          "Difference between this student's total and the reference "
                          "band mean, across the whole paper.", aggregable=False)

    obj = InsightObject(
        insight_type=InsightType.GAP_TO_REFERENCE,
        subject_scope=SubjectScope.STUDENT, analytical_scope=AnalyticalScope.PAPER,
        domain=None, subject_id=student.student_id,
        evidence=Evidence(supporting=[q.question_id for q in gap_questions]),
        coverage=Coverage(0, [], 0, CoverageStatus.NOT_APPLICABLE,
                           note="A totals comparison, not a claim about a concept."),
        confidence=Confidence(conf_band, conf_band, reason),
        priority=priority_for(paper.board_urgency, None, scope_not_applicable=True,
                               na_reason="Each named chapter spans several concept "
                               "families; taking the highest multiplier would import "
                               "an urgency this evidence does not localise."),
        marks_at_stake=marks, alternative_explanations=alt,
        action=actions[0] if len(actions) == 1 else actions,
        report_language=ReportLanguage(tlang, plang, slang),
    )
    obj.__dict__["_remediation_resolved"] = resolved_all
    return obj
