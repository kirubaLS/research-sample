"""The frozen student-facing sentences BoardX v2 reports are built from.

R3 of the composition spec: every student-facing sentence must resolve to one of these,
filled in with approved variables, never paraphrased or generated at runtime. Each
constant's name is the frozen-string ID the spec's own audit trail (section 6.2, check 4)
expects every rendered line to be traceable to -- ``compose()`` in ``boardx_report.py``
carries that ID alongside the text it produced so the audit pass can check it.
"""

from __future__ import annotations

#: R&U (Remembering & Understanding) / AP (Application) / AEC (Analysing, Evaluating,
#: Creating) are this codebase's existing CBSE tier codes (see CBSE_TIER_TARGET in
#: app.models). Spelled out here once, in the second person, for the one place a tier
#: code becomes a sentence a student reads.
TIER_QUESTION_TYPE = {
    "R&U": "questions asking you to state something",
    "AP": "questions asking you to use it",
    "AEC": "questions asking you to analyse or evaluate",
}

S1_ATTAINMENT = "{domain} — you scored {scored} of the {available} marks."
S1_NON_DIAGNOSABLE = (
    "{domain} — you scored {scored} of the {available} marks. This paper did not "
    "carry enough questions in this chapter to say anything more about it."
)
S1_BOARD_EXPOSURE = "{domain} carries {board_exposure} of the {board_total} marks in the Board blueprint."
S1_BOARD_NOT_CALIBRATED = (
    "The Board exposure for this chapter has not been calibrated in this report, so no "
    "number is shown."
)
S1_BOARD_IMPACT_NOT_CALIBRATED = (
    "This report does not convert marks from this test into marks you will lose or gain "
    "in the Board exam."
)
#: Disabled per R6 until an approved subject-specific calibration model exists -- see
#: boardx_report.py's own docstring. Kept here, unused, as the spec asks: the string is
#: reviewed and ready, not invented later under deadline pressure.
S1_BOARD_IMPACT_CALIBRATED = (
    "Using the approved {model_version} calibration, the current evidence corresponds to "
    "an estimated Board-impact range of {impact_low} to {impact_high} marks out of "
    "{board_total}."
)
#: Spec section 3.4 / R5: a real, auditable count from the Board-paper corpus, rendered
#: only when app.curriculum.board_frequency has actually computed one for this chapter's
#: concept family -- never a guess, and never the same as S1_BOARD_EXPOSURE (a weightage
#: fact), which is what a chapter is WORTH rather than how often it has actually appeared.
S1_BOARD_RECURRENCE = "{domain} has appeared in {years_appeared} of the last {years_in_scope} Board years."

S2_ANALYTICS_CAPTION = "This panel shows the Reading and Understanding Analytics issued for this paper."

S3_COMPLEXITY_GAP = (
    "In {domain}, you scored more marks on {stronger_question_type} than on "
    "{lower_question_type}."
)
S3_VARIANT_LOW = "Within {domain}, your lowest scores are on questions asking for {variant}."
S3_SCOPE_LOSS = (
    "Of the {marks_available_in_scope} marks on {question_type} questions, "
    "{marks_not_scored_in_scope} were not scored."
)
S3_NO_PATTERN = "This paper does not contain enough evidence to identify one repeated question pattern here."

S4_ACTION = "Next practice: {action_text}"
S4_NOT_LOCALISED = (
    "Marks were not scored in this chapter, but this paper does not identify one question "
    "type or topic that explains the pattern."
)
S4_TEACHER_REVIEW = "Your answer script should be reviewed before a new practice task is selected for this chapter."

S5_START_HERE = "Start here: {action_text}"

S6_ONE_TEST = "Only one test has been analysed. Nothing here says what will happen in the Board exam."
S6_OVERFLOW = "{n} other things showed up in this paper. Your teacher has the full list."
S6_UNCALIBRATED_BOARD_HISTORY = (
    "How often these chapters appear in Board papers has not been counted yet, so this "
    "report does not say."
)

#: Every frozen-string ID this module defines, for the audit pass (check 4: "a sentence
#: has no frozen-string ID") to check a rendered line's id against.
KNOWN_STRING_IDS = frozenset({
    "S1_ATTAINMENT", "S1_NON_DIAGNOSABLE", "S1_BOARD_EXPOSURE", "S1_BOARD_NOT_CALIBRATED",
    "S1_BOARD_IMPACT_NOT_CALIBRATED", "S1_BOARD_IMPACT_CALIBRATED", "S1_BOARD_RECURRENCE",
    "S2_ANALYTICS_CAPTION",
    "S3_COMPLEXITY_GAP", "S3_VARIANT_LOW", "S3_SCOPE_LOSS", "S3_NO_PATTERN",
    "S4_ACTION", "S4_NOT_LOCALISED", "S4_TEACHER_REVIEW",
    "S5_START_HERE",
    "S6_ONE_TEST", "S6_OVERFLOW", "S6_UNCALIBRATED_BOARD_HISTORY",
})

_TEMPLATES = {
    "S1_ATTAINMENT": S1_ATTAINMENT,
    "S1_NON_DIAGNOSABLE": S1_NON_DIAGNOSABLE,
    "S1_BOARD_EXPOSURE": S1_BOARD_EXPOSURE,
    "S1_BOARD_NOT_CALIBRATED": S1_BOARD_NOT_CALIBRATED,
    "S1_BOARD_IMPACT_NOT_CALIBRATED": S1_BOARD_IMPACT_NOT_CALIBRATED,
    "S1_BOARD_IMPACT_CALIBRATED": S1_BOARD_IMPACT_CALIBRATED,
    "S1_BOARD_RECURRENCE": S1_BOARD_RECURRENCE,
    "S2_ANALYTICS_CAPTION": S2_ANALYTICS_CAPTION,
    "S3_COMPLEXITY_GAP": S3_COMPLEXITY_GAP,
    "S3_VARIANT_LOW": S3_VARIANT_LOW,
    "S3_SCOPE_LOSS": S3_SCOPE_LOSS,
    "S3_NO_PATTERN": S3_NO_PATTERN,
    "S4_ACTION": S4_ACTION,
    "S4_NOT_LOCALISED": S4_NOT_LOCALISED,
    "S4_TEACHER_REVIEW": S4_TEACHER_REVIEW,
    "S5_START_HERE": S5_START_HERE,
    "S6_ONE_TEST": S6_ONE_TEST,
    "S6_OVERFLOW": S6_OVERFLOW,
    "S6_UNCALIBRATED_BOARD_HISTORY": S6_UNCALIBRATED_BOARD_HISTORY,
}


def render(string_id: str, **variables: object) -> dict:
    """A frozen string, filled in -- {"id": ..., "text": ...}, always both together, so a
    rendered line can never be shown without the ID the audit pass checks it against."""
    if string_id not in _TEMPLATES:
        raise KeyError(f"{string_id!r} is not a known frozen string")
    return {"id": string_id, "text": _TEMPLATES[string_id].format(**variables)}
