"""BoardX student report v2: the composition and rule engine from
'AVAI BoardX Student Report -- Vision-Aligned Composition & Rule Engine v2'.

This module turns already-validated evidence (chapter marks, verified Board blueprint
weights, the existing R&U-tier crosstab, and the remediation catalogue) into the frozen,
STUDENT-register sentences boardx_strings.py defines. It computes nothing new about the
student -- every number here is read off app.analysis.diagnostics, which already computes
it for the existing /reports/student endpoint. What this module adds is composition:
picking which findings to show, in which order, worded from which frozen string, capped
by which band -- and refusing to render anything the spec's audit checks (section 6.2)
would reject.

R6 of the spec: 'estimated Board impact' (a student-specific projection of marks that
will be lost/gained on the Board exam) is disabled until a separate, approved,
subject-specific calibration model exists -- five conditions the spec lists, none of
which this codebase has built. So estimated_board_impact is always NOT_CALIBRATED here;
S1_BOARD_IMPACT_CALIBRATED is defined in boardx_strings.py, reviewed and ready, but never
called from this module. Do not wire it up from a plain proportion of marks lost -- that
is exactly the heuristic substitute R6 forbids.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.boardx_strings import KNOWN_STRING_IDS, TIER_QUESTION_TYPE, render
from app.analysis.diagnostics import (
    MarkRow,
    Finding,
    by_chapter,
    skill_by_tier,
)
from app.models import (
    Assessment,
    ChapterBoardUnit,
    RemediationRow,
    TaxonomyNode,
)

#: The assembly split (spec section 4): attainment across diagnosable chapters at or
#: above this uses "upper" assembly (fewer, higher-precision findings); below it uses
#: "lower" assembly (fewer still, every one action-backed, ordered from strength).
#: A stated product decision (spec Decision D), not a fitted constant -- validate on
#: cohort data before relying on it for anything higher-stakes than which findings show.
ATTAINMENT_BAND_SPLIT = 0.50

#: CBSE's Class X theory papers are 80 marks for every subject this product has loaded so
#: far (Mathematics, Social Science's four books, ...). Not read from anywhere per-subject
#: because nothing in this schema stores it; if a subject with a different board total is
#: ever loaded, this needs a real per-subject table, not a wider guess here.
BOARD_PAPER_TOTAL_MARKS = 80.0

UPPER_FINDING_CAP = 3
LOWER_FINDING_CAP = 2


@dataclass
class RenderedLine:
    id: str
    text: str


def _chapter_board_exposure(
    db: Session, assessment: Assessment, chapter_code: str, board_weights: dict[str, float],
) -> tuple[float | None, bool]:
    """(marks, verified) -- None/False when the chapter has no verified board-unit
    weight for this curriculum version. Never a number without ``verified`` being true;
    R6 draws exactly this line between a verified blueprint fact and an invented one."""
    chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == chapter_code))
    if chapter is None:
        return None, False
    link = db.scalar(
        select(ChapterBoardUnit).where(
            ChapterBoardUnit.curriculum_version == assessment.curriculum_version,
            ChapterBoardUnit.chapter_id == chapter.id,
        )
    )
    if link is None:
        return None, False
    unit = db.get(TaxonomyNode, link.board_unit_id)
    weight_pct = board_weights.get(unit.code) if unit else None
    # A weight of exactly 0 is this codebase's placeholder for "not populated yet" --
    # every subject but Mathematics and Science currently carries this placeholder on
    # every one of its board units (see app.curriculum's own BoardUnit rows). Treating it
    # as verified would print a misleading "0 of 80 Board marks" as if that were a real
    # CBSE blueprint fact, for every chapter in every one of those subjects.
    if weight_pct is None or weight_pct <= 0:
        return None, False
    return round(weight_pct / 100.0 * BOARD_PAPER_TOTAL_MARKS), True


def _resolve_remediation(
    db: Session, subject_code: str, domain_code: str, finding_type: str,
) -> tuple[str, str] | None:
    """An approved catalogue row for this exact (subject, chapter, finding shape), or
    None -- R4: a finding may show a practice recommendation only when this resolves."""
    row = db.scalar(
        select(RemediationRow).where(
            RemediationRow.subject_code == subject_code,
            RemediationRow.domain_code == domain_code,
            RemediationRow.finding_type == finding_type,
            RemediationRow.approved.is_(True),
        )
    )
    return (row.remediation_ref, row.student_action_text) if row is not None else None


def _pattern_for_chapter(
    crosstab: list[Finding], chapter_code: str, chapter_skills: set[str],
) -> tuple[dict | None, str | None]:
    """(S3 line, finding_type) for one chapter, from its own skill x tier crosstab rows.

    finding_type distinguishes the two shapes the spec names: a gap between two tiers on
    the SAME skill ('complexity_gap', the "knows the formula, cannot apply it" signature
    skill_by_tier's own docstring names) versus one sub-topic scoring lowest among several
    ('variant_low'). Returns finding_type=None when neither has enough evidence -- the
    caller renders S3_NO_PATTERN for that case, never a guess.
    """
    sufficient = [
        f for f in crosstab
        if f.sufficient and f.rate is not None and f.key.split("|")[0] in chapter_skills
    ]
    if not sufficient:
        return None, None

    by_skill_tier: dict[str, dict[str, Finding]] = {}
    for f in sufficient:
        skill, tier = f.key.split("|", 1)
        by_skill_tier.setdefault(skill, {})[tier] = f

    # A skill tested at two or more tiers, with a real gap between them, is the strongest
    # signal -- pick the one with the widest gap across every skill in the chapter.
    best_gap: tuple[float, str, Finding, Finding] | None = None
    for skill, tiers in by_skill_tier.items():
        names = list(tiers)
        for i, hi_name in enumerate(names):
            for lo_name in names[i + 1:]:
                hi, lo = tiers[hi_name], tiers[lo_name]
                if hi.rate < lo.rate:
                    hi, lo, hi_name, lo_name = lo, hi, lo_name, hi_name
                gap = hi.rate - lo.rate
                if gap > 0 and (best_gap is None or gap > best_gap[0]):
                    best_gap = (gap, skill, hi, lo)
    if best_gap is not None:
        _, _, hi, lo = best_gap
        hi_tier, lo_tier = hi.key.split("|", 1)[1], lo.key.split("|", 1)[1]
        stronger = TIER_QUESTION_TYPE.get(hi_tier, hi_tier)
        weaker = TIER_QUESTION_TYPE.get(lo_tier, lo_tier)
        return (
            render("S3_COMPLEXITY_GAP", domain="{domain}", stronger_question_type=stronger,
                   lower_question_type=weaker),
            "complexity_gap",
        )

    # No cross-tier gap on any one skill -- fall back to the lowest-scoring skill, if any.
    worst = min(sufficient, key=lambda f: f.rate)
    return (
        render("S3_VARIANT_LOW", domain="{domain}", variant=worst.key.split("|")[0]),
        "variant_low",
    )


def compose_boardx_report(
    db: Session, assessment: Assessment, student, rows: list[MarkRow],
) -> dict:
    """The full BoardX v2 composition for one student, one subject, one assessment
    (R2: one subject is one calculation boundary -- ``rows`` must already be scoped to
    this assessment's own subject, as every caller of this module already does).
    """
    from app.api.reports import _board_weights  # local: avoids a circular import at module load

    nodes_by_code = {n.code: n for n in db.scalars(select(TaxonomyNode))}
    board_weights = _board_weights(db, assessment)
    chapter_findings = sorted(
        by_chapter(rows), key=lambda f: -f.earned,
    )  # diagnosable-or-not, every chapter the paper actually tested

    counted_diagnosable = [f for f in chapter_findings if f.sufficient]
    scored = sum(f.earned for f in counted_diagnosable)
    available = sum(f.available for f in counted_diagnosable)
    attainment = (scored / available) if available else 0.0
    band = "upper" if attainment >= ATTAINMENT_BAND_SPLIT else "lower"
    cap = UPPER_FINDING_CAP if band == "upper" else LOWER_FINDING_CAP

    # Section 1 -- lower band starts from marks scored (spec 5.SECTION-1 rule 5); upper
    # band keeps the same order by size of loss select_findings already ranks by.
    section1_order = (
        sorted(chapter_findings, key=lambda f: -f.earned) if band == "lower"
        else chapter_findings
    )
    section1 = []
    for f in section1_order:
        chapter_code = f.key
        label = nodes_by_code[chapter_code].label if chapter_code in nodes_by_code else chapter_code
        scored_i, available_i = int(f.earned) if f.earned == int(f.earned) else f.earned, (
            int(f.available) if f.available == int(f.available) else f.available
        )
        line = (
            render("S1_ATTAINMENT", domain=label, scored=scored_i, available=available_i)
            if f.sufficient else
            render("S1_NON_DIAGNOSABLE", domain=label, scored=scored_i, available=available_i)
        )
        exposure_marks, verified = _chapter_board_exposure(db, assessment, chapter_code, board_weights)
        board_line = (
            render("S1_BOARD_EXPOSURE", domain=label,
                   board_exposure=exposure_marks, board_total=int(BOARD_PAPER_TOTAL_MARKS))
            if verified else render("S1_BOARD_NOT_CALIBRATED")
        )
        section1.append({
            "domain": label, "domain_code": chapter_code,
            "scored": f.earned, "available": f.available,
            "not_scored": f.available - f.earned,
            "diagnosable": f.sufficient,
            "board_exposure": exposure_marks if verified else None,
            "board_total": int(BOARD_PAPER_TOTAL_MARKS) if verified else None,
            "board_exposure_verified": verified,
            "estimated_board_impact": "NOT_CALIBRATED",  # R6 -- see module docstring
            "lines": [line, board_line],
        })
    section1.append({"lines": [render("S1_BOARD_IMPACT_NOT_CALIBRATED")]})

    # Section 2 -- the R&U crosstab this codebase already computes live (product decision:
    # rendered as data here, not a separately-issued screenshot; see session notes).
    crosstab = skill_by_tier(rows)
    section2 = {
        "caption": render("S2_ANALYTICS_CAPTION"),
        "crosstab": [f.as_dict() for f in crosstab],
    }

    # Chapter -> its own skill codes, so section 3's pattern search stays inside one
    # chapter at a time rather than mixing tiers across unrelated topics.
    chapter_skills: dict[str, set[str]] = {}
    for r in rows:
        if r.chapter:
            chapter_skills.setdefault(r.chapter, set()).update(r.skills)

    # Sections 3-5 walk the same ranked findings together, one chapter at a time, since
    # section 4's drill-down and section 5's action list are built from section 3's own
    # pattern -- rendering them separately risked the three disagreeing about which
    # chapter's pattern was even being discussed.
    #
    # Ranked by marks actually lost, largest first: select_findings' own priority
    # mechanism is built for subtopic/concept-family findings ranked against a board UNIT
    # weight map, a different scope than chapter-level findings need, and reusing it here
    # would have silently fallen back to its flat default weight for every chapter (no
    # chapter code is ever a board-unit code). Only chapters with something actually lost
    # are candidates -- a chapter scored in full has nothing for sections 3-5 to say.
    ranked = sorted(
        (f for f in chapter_findings if f.sufficient and f.available > f.earned),
        key=lambda f: -(f.available - f.earned),
    )[:cap]

    section3, section4, section5_actions = [], [], []
    for f in ranked:
        chapter_code = f.key
        label = nodes_by_code[chapter_code].label if chapter_code in nodes_by_code else chapter_code
        pattern_line, finding_type = _pattern_for_chapter(
            crosstab, chapter_code, chapter_skills.get(chapter_code, set()),
        )
        if pattern_line is None:
            section3.append(render("S3_NO_PATTERN"))
            section4.append({
                "domain": label, "topic": None,
                "lines": [render("S4_NOT_LOCALISED"), render("S4_TEACHER_REVIEW")],
                "action": None,
            })
            continue

        pattern_line["text"] = pattern_line["text"].replace("{domain}", label)
        scope_line = render(
            "S3_SCOPE_LOSS",
            marks_available_in_scope=f.available, marks_not_scored_in_scope=f.available - f.earned,
            question_type=finding_type.replace("_", " "),
        )
        section3.extend([pattern_line, scope_line])

        resolved = _resolve_remediation(db, assessment.subject_code, chapter_code, finding_type)
        card = {"domain": label, "topic": finding_type.replace("_", " "), "lines": [scope_line]}
        if resolved is not None:
            ref, action_text = resolved
            action_line = render("S4_ACTION", action_text=action_text)
            card["lines"].append(action_line)
            card["action"] = {"remediation_ref": ref, "text": action_text}
            section5_actions.append({"remediation_ref": ref, "text": action_text})
        else:
            card["lines"].append(render("S4_NOT_LOCALISED"))
            card["action"] = None
        section4.append(card)

    section5 = {"actions": []}
    for i, action in enumerate(section5_actions):
        if band == "lower" and i == 0:
            section5["actions"].append({
                **action, "line": render("S5_START_HERE", action_text=action["text"]),
            })
        else:
            section5["actions"].append({
                **action, "line": render("S4_ACTION", action_text=action["text"]),
            })

    overflow_count = max(0, len(chapter_findings) - len(ranked) - 1)
    section6_lines = [render("S6_ONE_TEST")]
    if overflow_count:
        section6_lines.append(render("S6_OVERFLOW", n=overflow_count))
    section6_lines.append(render("S6_UNCALIBRATED_BOARD_HISTORY"))

    report = {
        "assessment_id": assessment.id, "assessment_title": assessment.title,
        "subject_code": assessment.subject_code,
        "student_id": student.id, "student_name": student.name,
        "assembly_band": band,  # never printed to the student -- spec section 4
        "section1": section1,
        "section2": section2,
        "section3": section3,
        "section4": section4,
        "section5": section5,
        "section6": section6_lines,
    }
    _audit(report)
    return report


class BoardXAuditError(Exception):
    """A composed report failed one of the spec's section 6.2 audit checks. Never caught
    silently -- a report that cannot pass its own audit must not reach a student."""


def _all_lines(report: dict) -> list[dict]:
    out: list[dict] = []
    for entry in report["section1"]:
        out.extend(entry.get("lines", []))
    out.append(report["section2"]["caption"])
    out.extend(report["section3"])
    for card in report["section4"]:
        out.extend(card["lines"])
    for action in report["section5"]["actions"]:
        out.append(action["line"])
    out.extend(report["section6"])
    return out


def _audit(report: dict) -> None:
    """Checks 4, 5 and 9 of spec section 6.2 -- the ones composition can actually violate.
    (Checks 1/2/3/6/7/8/10 are enforced by construction: this module never aggregates
    across subjects, never renders a recurrence/impact number without its own verified/
    NOT_CALIBRATED gate, never addresses the student in third person, never shows a class
    comparison, never uses a banned word, and every lower-band card carries an action or
    the explicit not-localised pair -- so there is nothing left for a runtime check to
    catch there without re-deriving the whole engine a second time.)
    """
    for line in _all_lines(report):
        if line["id"] not in KNOWN_STRING_IDS:
            raise BoardXAuditError(f"{line['id']!r} is not a known frozen string")
    for entry in report["section1"]:
        if not entry.get("diagnosable", True) and any(
            "S1_ATTAINMENT" == line["id"] for line in entry.get("lines", [])
        ):
            raise BoardXAuditError(
                f"{entry.get('domain')!r} is not diagnosable but emitted a diagnostic finding"
            )
    if report["assembly_band"] == "lower":
        for card in report["section4"]:
            if card["action"] is None and not any(
                line["id"] == "S4_NOT_LOCALISED" for line in card["lines"]
            ):
                raise BoardXAuditError("a lower-band finding has no action and no explicit refusal")
