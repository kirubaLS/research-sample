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


def _chapter_recurrence(
    db: Session, assessment: Assessment, chapter_code: str,
    chapter_families: dict[str, list[str]], nodes_by_code: dict[str, TaxonomyNode],
) -> dict | None:
    """A real Board-recurrence line for this chapter, or None when the corpus has not
    been computed for any family this chapter tested (spec section 3.4 / R5: never a
    count without a stored corpus/version to audit it against -- see
    app.curriculum.board_frequency.recompute, which only ever writes a row once real
    Board papers for this subject have actually been placed).

    Picks the first family in the chapter with a calibrated row; a chapter usually maps
    to one family in a school test's worth of evidence, and this is a citation, not a
    ranking, so the first real one found is enough to say the chapter has Board history
    on file at all.
    """
    from app.curriculum.board_frequency import CURRENT_VERSION, frequency_rows, stream_of

    freq = frequency_rows(db, assessment.subject_code, CURRENT_VERSION, stream_of(assessment))
    if not freq:
        return None
    for family_code in chapter_families.get(chapter_code, []):
        family = nodes_by_code.get(family_code)
        row = freq.get(family.id) if family else None
        if row is not None:
            return render(
                "S1_BOARD_RECURRENCE", domain="{domain}",
                years_appeared=row.years_appeared, years_in_scope=row.years_eligible,
            )
    return None


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
    nodes_by_code: dict[str, TaxonomyNode],
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
    worst_skill_code = worst.key.split("|")[0]
    # A student reads "variant", never the taxonomy code it is keyed by -- the code is an
    # internal join key (app.models.assessment.QuestionSkill), not something a teacher,
    # principal or student was ever meant to see on a report.
    worst_skill_label = nodes_by_code[worst_skill_code].label if worst_skill_code in nodes_by_code else worst_skill_code
    return (
        render("S3_VARIANT_LOW", domain="{domain}", variant=worst_skill_label),
        "variant_low",
    )


def compose_boardx_report(
    db: Session, assessment: Assessment, student, rows: list[MarkRow],
) -> dict:
    """The full BoardX v2 composition for one student, one subject, one assessment
    (R2: one subject is one calculation boundary -- ``rows`` must already be scoped to
    this assessment's own subject, as every caller of this module already does).
    """
    from app.api.academics import _subject_label  # local: avoids a circular import at module load
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

    # Chapter -> the concept families this paper actually tested there, so both the
    # recurrence lookup below and section 3's pattern search (further down) can work
    # inside one chapter at a time rather than mixing evidence across unrelated topics.
    chapter_families: dict[str, list[str]] = {}
    for r in rows:
        if r.chapter and r.concept_family:
            chapter_families.setdefault(r.chapter, [])
            if r.concept_family not in chapter_families[r.chapter]:
                chapter_families[r.chapter].append(r.concept_family)

    # Section 1 -- lower band starts from marks scored (spec 5.SECTION-1 rule 5); upper
    # band keeps the same order by size of loss select_findings already ranks by.
    section1_order = (
        sorted(chapter_findings, key=lambda f: -f.earned) if band == "lower"
        else chapter_findings
    )
    section1 = []
    any_recurrence_shown = False
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
        lines = [line, board_line]
        recurrence_line = _chapter_recurrence(db, assessment, chapter_code, chapter_families, nodes_by_code)
        if recurrence_line is not None:
            recurrence_line["text"] = recurrence_line["text"].replace("{domain}", label)
            lines.append(recurrence_line)
            any_recurrence_shown = True
        section1.append({
            "domain": label, "domain_code": chapter_code,
            "scored": f.earned, "available": f.available,
            "not_scored": f.available - f.earned,
            "diagnosable": f.sufficient,
            "board_exposure": exposure_marks if verified else None,
            "board_total": int(BOARD_PAPER_TOTAL_MARKS) if verified else None,
            "board_exposure_verified": verified,
            "estimated_board_impact": "NOT_CALIBRATED",  # R6 -- see module docstring
            "lines": lines,
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
            crosstab, chapter_code, chapter_skills.get(chapter_code, set()), nodes_by_code,
        )
        if pattern_line is None:
            section3.append(render("S3_NO_PATTERN"))
            section4.append({
                "domain": label, "topic": None,
                "lines": [render("S4_NOT_LOCALISED"), render("S4_TEACHER_REVIEW")],
                "action": None,
            })
            continue

        resolved = _resolve_remediation(db, assessment.subject_code, chapter_code, finding_type)

        # R4: a finding whose remediation does not resolve is a different case from "no
        # pattern found" (S4_NOT_LOCALISED is about the latter, and saying it here would
        # be false -- a pattern WAS found). Upper assembly may still show it, without an
        # action; lower assembly must not show it at all, so a struggling student is never
        # handed a card naming a loss with nothing concrete to do about it.
        if resolved is None and band == "lower":
            continue

        pattern_line["text"] = pattern_line["text"].replace("{domain}", label)
        scope_line = render(
            "S3_SCOPE_LOSS",
            marks_available_in_scope=f.available, marks_not_scored_in_scope=f.available - f.earned,
            question_type=finding_type.replace("_", " "),
        )
        section3.extend([pattern_line, scope_line])

        card = {"domain": label, "topic": finding_type.replace("_", " "), "lines": [scope_line]}
        if resolved is not None:
            ref, action_text = resolved
            action_line = render("S4_ACTION", action_text=action_text)
            card["lines"].append(action_line)
            card["action"] = {"remediation_ref": ref, "text": action_text}
            section5_actions.append({"remediation_ref": ref, "text": action_text})
        else:
            # Upper assembly only reaches here: R4 permits showing the finding itself
            # without a resolved action.
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
    # Only when no chapter actually got a real recurrence line above -- once one has,
    # telling the student "this report does not say" about Board history is simply false.
    if not any_recurrence_shown:
        section6_lines.append(render("S6_UNCALIBRATED_BOARD_HISTORY"))

    report = {
        "assessment_id": assessment.id, "assessment_title": assessment.title,
        "subject_code": assessment.subject_code,
        "subject_label": _subject_label(assessment.subject_code),
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


def render_boardx_pdf(report: dict, *, roll_no: str, class_label: str, school_name: str) -> bytes:
    """The same composed report, laid out as an actual one-page PDF matching the AVAI
    BoardX visual design (navy header/footer bands, a 2x2 grid of white cards, colour-
    coded highlight boxes) -- nothing computed here, every figure and sentence is read
    straight off ``report`` (itself frozen-string output from
    :func:`compose_boardx_report`), the same "print exactly what was composed" rule
    ``app.analysis.report_pdf`` already follows for the plain student report. The layout
    is fixed; the content inside it is entirely dynamic -- nothing about a particular
    student, chapter or subject is hardcoded anywhere below.
    """
    from fpdf import FPDF

    NAVY = (23, 55, 87)
    PAGE_BG = (244, 246, 250)
    CARD_BORDER = (228, 231, 238)
    INK = (35, 40, 50)
    MUTED = (100, 106, 120)

    BADGE = {1: (23, 55, 87), 2: (30, 130, 118), 3: (196, 120, 30), 4: (46, 125, 79)}
    GREEN = ((227, 243, 234), (30, 100, 64))
    ORANGE = ((253, 240, 219), (168, 94, 14))
    BLUE = ((230, 238, 250), (30, 58, 95))
    TEAL = ((222, 242, 240), (18, 104, 95))
    GREY = ((242, 243, 246), (70, 74, 84))
    PALETTE = [ORANGE, TEAL, GREY, BLUE]

    def safe(text: object) -> str:
        return str(text if text is not None else "").encode("latin-1", "replace").decode("latin-1")

    def num(n: float) -> str:
        return f"{n:g}"

    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    pdf.set_fill_color(*PAGE_BG)
    pdf.rect(0, 0, 210, 297, style="F")

    # ---- a tiny retained-mode layout engine ------------------------------------------
    # A card's content length is different for every student and every paper (a lower-
    # band report has fewer findings than an upper-band one, a chapter list is 2 rows
    # for one paper and 6 for another), so nothing here can be a fixed box size. Each
    # `Card` records its text/box operations while measuring their height with fpdf2's
    # own dry-run pass; `draw_card` then draws the background at the right height
    # first, and replays the exact same operations (same fonts, same dry-run height
    # formula) on top -- measured and drawn heights can never disagree because both
    # come from the same multi_cell call.
    class Card:
        def __init__(self, x: float, w: float):
            self.x, self.w = x, w
            self.pad = 5.0
            self.ops: list[tuple] = []
            self.op_heights: list[float] = []
            self.height = 0.0

        def _add(self, op: tuple, h: float) -> None:
            self.ops.append(op)
            self.op_heights.append(h)
            self.height += h

        def text(self, text: str, *, size=10, style="", color=INK, line_h=5.0, gap=1.6, indent=0.0):
            inner_w = self.w - 2 * self.pad - indent
            pdf.set_font("Helvetica", style, size)
            h = pdf.multi_cell(inner_w, line_h, safe(text), dry_run=True, output="HEIGHT")
            self._add(("text", text, size, style, color, line_h, indent, gap), h + gap)

        def space(self, h: float):
            self._add(("space", h), h)

        def badge_title(self, n: int, title: str):
            self._add(("badge", n, title), 9.0)

        def box_start(self, bg: tuple):
            self._add(("box_start", bg), self.pad)

        def box_end(self):
            self._add(("box_end",), self.pad)

    def draw_card(card: Card, y: float) -> float:
        total_h = card.height + 2 * card.pad
        pdf.set_draw_color(*CARD_BORDER)
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(card.x, y, card.w, total_h, style="DF", round_corners=True, corner_radius=2.5)

        # A nested box's own fill has to be painted before its text, or the fill (drawn
        # once its true height is known) paints straight over text already on the page.
        # So its height is found by scanning ahead to the matching box_end first --
        # `op_heights` already carries the exact figure every op contributed when it was
        # measured, so this is a lookup, not a second measurement pass.
        box_end_height: dict[int, float] = {}
        stack: list[int] = []
        for idx, op in enumerate(card.ops):
            if op[0] == "box_start":
                stack.append(idx)
            elif op[0] == "box_end":
                start_idx = stack.pop()
                box_end_height[start_idx] = sum(card.op_heights[start_idx:idx + 1])

        cy = y + card.pad
        for idx, op in enumerate(card.ops):
            kind = op[0]
            if kind == "space":
                cy += op[1]
            elif kind == "badge":
                _, n, title = op
                bx, by = card.x + card.pad, cy
                pdf.set_fill_color(*BADGE.get(n, NAVY))
                pdf.ellipse(bx, by, 6, 6, style="F")
                pdf.set_xy(bx, by + 0.9)
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(255, 255, 255)
                pdf.cell(6, 5, safe(str(n)), align="C")
                pdf.set_text_color(*NAVY)
                pdf.set_font("Helvetica", "B", 12.5)
                pdf.set_xy(bx + 8, by - 0.3)
                pdf.cell(card.w - 2 * card.pad - 8, 6, safe(title))
                cy += 9.0
            elif kind == "box_start":
                _, bg = op
                box_h = box_end_height[idx]
                pdf.set_fill_color(*bg)
                pdf.rect(card.x + card.pad * 0.6, cy, card.w - card.pad * 1.2, box_h,
                          style="F", round_corners=True, corner_radius=1.6)
                cy += card.pad
            elif kind == "box_end":
                cy += card.pad
            elif kind == "text":
                _, text, size, style, color, line_h, indent, gap = op
                inner_w = card.w - 2 * card.pad - indent
                pdf.set_xy(card.x + card.pad + indent, cy)
                pdf.set_font("Helvetica", style, size)
                pdf.set_text_color(*color)
                pdf.multi_cell(inner_w, line_h, safe(text), new_x="LEFT", new_y="TOP")
                h = pdf.multi_cell(inner_w, line_h, safe(text), dry_run=True, output="HEIGHT")
                cy += h + gap
        pdf.set_text_color(*INK)
        return total_h

    # ---- header band -------------------------------------------------------------
    HEADER_H = 30.0
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, HEADER_H, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(8, 4)
    pdf.set_font("Helvetica", "B", 17)
    pdf.cell(0, 8, "AVAI BoardX")
    pdf.set_xy(8, 13)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, safe(f"{report['subject_label']}  |  Your One-Page Assessment Report"))
    pdf.set_xy(8, 21)
    pdf.set_font("Helvetica", "", 9.5)
    meta = safe(
        f"{report['student_name']}  |  {class_label} (Roll {roll_no})  |  "
        f"{report['assessment_title']}  |  {report['subject_label']}"
    )
    pdf.cell(0, 6, meta)
    pdf.set_text_color(*INK)

    col1_x, col2_x, col_w = 8.0, 109.0, 93.0
    row1_y = HEADER_H + 4.0

    # ---- section 1: where you stand -----------------------------------------------
    c1 = Card(col1_x, col_w)
    c1.badge_title(1, "Where you stand")
    c1.space(1)

    chapter_entries = [e for e in report["section1"] if "domain" in e]
    c1.text("Chapter   ·   You scored   ·   Not scored   ·   Board importance",
            size=7.6, style="B", color=MUTED, line_h=4.2, gap=1.0)
    exposure_total = 0.0
    for e in chapter_entries:
        scored = f"{num(e['scored'])} / {num(e['available'])}" if e["diagnosable"] else "Not enough evidence"
        not_scored = num(e["not_scored"]) if e["diagnosable"] else "—"
        if e["board_exposure_verified"]:
            board = f"{num(e['board_exposure'])} / {num(e['board_total'])}"
            exposure_total += e["board_exposure"]
        else:
            board = "Not calibrated"
        c1.text(e["domain"], size=9, style="B", line_h=4.6, gap=0.3)
        c1.text(f"Scored {scored}   ·   Not scored {not_scored}   ·   Board {board}",
                size=8.3, color=MUTED, line_h=4.2, gap=1.4)
    c1.space(1.5)

    board_total = next((e["board_total"] for e in chapter_entries if e["board_exposure_verified"]), None)
    c1.box_start(GREEN[0])
    c1.text("BOARD EXPOSURE", size=8, style="B", color=GREEN[1], line_h=4, gap=0.8)
    if board_total:
        c1.text(f"Affected chapters carry {num(exposure_total)} of the {num(board_total)} Board marks.",
                size=9.3, style="B", color=GREEN[1], line_h=4.6, gap=0)
    else:
        c1.text("Not calibrated for this subject yet.", size=9.3, style="B", color=GREEN[1], line_h=4.6, gap=0)
    c1.box_end()
    c1.space(2.5)

    impact_entry = next((e for e in report["section1"] if "domain" not in e), None)
    c1.box_start(ORANGE[0])
    c1.text("ESTIMATED BOARD-SCORE IMPACT", size=8, style="B", color=ORANGE[1], line_h=4, gap=0.8)
    if impact_entry is not None:
        for l in impact_entry["lines"]:
            c1.text(l["text"], size=9.3, style="B", color=ORANGE[1], line_h=4.6, gap=0)
    c1.box_end()

    h1 = draw_card(c1, row1_y)

    # ---- section 2: how you are handling questions ---------------------------------
    c2 = Card(col2_x, col_w)
    c2.badge_title(2, "How you are handling questions")
    c2.space(1)
    c2.text(report["section2"]["caption"]["text"], size=9, color=MUTED, line_h=4.6, gap=2.5)

    i = 0
    pairs: list[tuple[dict, dict | None]] = []
    for card in report["section4"]:
        if card["topic"] is None:
            pairs.append((report["section3"][i], None))
            i += 1
        else:
            pairs.append((report["section3"][i], report["section3"][i + 1]))
            i += 2
    pattern_pairs = [
        (card, pat) for card, (pat, _scope) in zip(report["section4"], pairs) if card["topic"] is not None
    ]

    if not pattern_pairs:
        c2.text(
            "This paper does not contain enough evidence to identify one repeated question pattern.",
            size=9.3, color=MUTED, line_h=4.6, gap=0,
        )
    for idx, (card, pattern) in enumerate(pattern_pairs):
        bg, fg = BLUE if idx % 2 == 0 else TEAL
        c2.box_start(bg)
        c2.text(f"PATTERN SEEN: {safe(card['topic']).upper()}", size=8, style="B", color=fg, line_h=4, gap=1.2)
        c2.text(pattern["text"], size=9.3, style="B", color=INK, line_h=4.6, gap=0)
        c2.box_end()
        if idx != len(pattern_pairs) - 1:
            c2.space(2.5)

    h2 = draw_card(c2, row1_y)

    row2_y = row1_y + max(h1, h2) + 6.0

    # ---- section 3: where the marks went -------------------------------------------
    c3 = Card(col1_x, col_w)
    c3.badge_title(3, "Where the marks went")
    c3.space(1)
    for idx, (card, _pair) in enumerate(zip(report["section4"], pairs)):
        bg, fg = PALETTE[idx % len(PALETTE)]
        c3.box_start(bg)
        c3.text(card["domain"], size=9.5, style="B", color=fg, line_h=4.8, gap=1.0)
        for l in card["lines"]:
            c3.text(l["text"], size=8.6, color=INK, line_h=4.2, gap=0.6)
        c3.box_end()
        if idx != len(report["section4"]) - 1:
            c3.space(2.5)
    if not report["section4"]:
        c3.text("Every chapter on this paper was scored in full.", size=9.3, color=MUTED, line_h=4.6, gap=0)

    h3 = draw_card(c3, row2_y)

    # ---- section 4: what you should do next ----------------------------------------
    c4 = Card(col2_x, col_w)
    c4.badge_title(4, "What you should do next")
    c4.space(1)
    actions = report["section5"]["actions"]
    if not actions:
        c4.box_start(BLUE[0])
        c4.text("Your answer script should be reviewed before a new practice task is selected.",
                size=9.3, style="B", color=BLUE[1], line_h=4.6, gap=0)
        c4.box_end()
    for idx, a in enumerate(actions):
        bg, fg = GREEN if idx % 2 == 0 else TEAL
        c4.box_start(bg)
        c4.text(a["line"]["text"], size=9.3, style="B", color=fg, line_h=4.6, gap=0)
        c4.box_end()
        if idx != len(actions) - 1:
            c4.space(2.5)

    h4 = draw_card(c4, row2_y)

    # ---- footer band -----------------------------------------------------------------
    # A thin bar pinned to the bottom of the page, not to the bottom of the content --
    # a lower-band report with only one or two findings should not drag a wall of navy
    # across most of the page just because it has less to say than an upper-band one.
    footer_h = max(10.0, len(report["section6"]) * 4.6 + 6.0)
    fy = 297 - footer_h
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, fy, 210, footer_h, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8.5)
    ty = fy + 3.0
    for l in report["section6"]:
        pdf.set_xy(8, ty)
        pdf.cell(0, 5, safe(l["text"]))
        ty += 4.6
    pdf.set_text_color(*INK)

    return bytes(pdf.output())

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
