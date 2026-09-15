"""
Part F: frozen report-language strings, with substitution slots. Never
generated/paraphrased at runtime. The one exception is E10's composed count
line, implemented in promotion.py exactly as specified (F1, E10).

F2/F3 boundary tests are implemented as `check_boundaries`, called on every
frozen template at module load (see `_SELF_CHECK` at the bottom) and
available for tests to call directly.
"""
from __future__ import annotations

NOT_ISSUED = "NOT_ISSUED"

# ---------------------------------------------------------------------------
# F2 / F3 boundary tests
# ---------------------------------------------------------------------------

# NOTE (judgment call): "confidence" is deliberately NOT in this list. The
# spec's own G5 example string is "3 further Medium-confidence observations
# were not included" — "confidence" there names the engine's own statistical
# band (D2/D3), not a psychological state of the student. F2 bans the
# psychological sense ("has confidence in themselves"); the technical sense
# used throughout Part G's assembly strings is not what the boundary test is
# guarding against.
_PSYCHOLOGY_WORDS = [
    "understanding", "understands", "grasp", "effort",
    "ability", "motivation", "tried hard", "how hard",
]
_CAUSAL_PHRASES = ["because", "due to", "as a result of"]
_STRENGTH_WORDS = [
    "strong", "good grasp", "has mastered", "understands",
    "is secure in", "no weakness in", "performs well overall",
]
_PREDICTION_WORDS = [
    "would score", "could recover", "will improve", "recoverable",
    "on track for", "potential marks",
]

# Rows explicitly flagged as exceptions in the string table (F5.7 companion
# line uses "grasp" inside an enumeration of undecided explanations).
FLAGGED_EXCEPTION_KEYS: set[str] = {
    "E7_COMPANION_TEACHER",
    "E7_COMPANION_PARENT",
    "E7_COMPANION_STUDENT",
}


def check_boundaries(text: str, *, key: str = "") -> list[str]:
    """Returns a list of failure reasons; empty list means the string passes
    F2 and F3 (or is a flagged exception row)."""
    if text == NOT_ISSUED:
        return []
    failures: list[str] = []
    lower = text.lower()

    if key not in FLAGGED_EXCEPTION_KEYS:
        for word in _PSYCHOLOGY_WORDS:
            if word in lower:
                failures.append(f"F2 psychology word: '{word}'")

    for phrase in _CAUSAL_PHRASES:
        if phrase in lower:
            failures.append(f"F2 causal phrase: '{phrase}'")

    for word in _STRENGTH_WORDS:
        if word in lower:
            failures.append(f"F3 strength word: '{word}'")

    for word in _PREDICTION_WORDS:
        if word in lower:
            failures.append(f"F3 prediction word: '{word}'")

    return failures


# ---------------------------------------------------------------------------
# F5: the string table. Templates use str.format-style slots.
# ---------------------------------------------------------------------------

STRINGS: dict[str, str] = {
    # F5.1 Tier Gap
    "E1_TEACHER": (
        "Across this paper, {subject} answers direct recall questions correctly more "
        "often than questions requiring application. {marks_lost} of the "
        "{marks_available} marks available on application and analysis questions were "
        "not scored."
    ),
    "E1_PARENT": (
        "Across this paper, {student} does better on questions that ask them to state "
        "something they have learned than on questions that ask them to use it. Of the "
        "{marks_available} marks on the second kind, {marks_lost} were not scored."
    ),
    "E1_STUDENT": (
        "Across this paper, you scored higher on questions that asked you to state "
        "something than on questions that asked you to use it. Of the "
        "{marks_available} marks on the second kind, {marks_lost} were not scored."
    ),

    # F5.2 Reverse Tier Gap
    "E2_TEACHER": (
        "Across this paper {subject} answered questions requiring application correctly "
        "more often than direct recall questions. This is the opposite of the usual "
        "pattern. These results do not show why, and no conclusion about {subject} is "
        "drawn from it."
    ),

    # F5.3 Complexity Gap
    "E3_TEACHER": (
        "In {domain}, {subject} scores lower on questions requiring several steps than "
        "on single-step questions. {marks_lost} of the {marks_available} marks "
        "available on multi-step questions were not scored."
    ),
    "E3_PARENT": (
        "In {domain}, {student} is picking up the marks on short questions and losing "
        "them on the longer ones that take several steps. Of the {marks_available} "
        "marks on the longer questions, {marks_lost} were not scored."
    ),
    "E3_STUDENT": (
        "In {domain}, you are scoring on the short questions and losing marks on the "
        "ones that take several steps. Of the {marks_available} marks on those, "
        "{marks_lost} were not scored."
    ),

    # F5.4 Integration Gap
    "E4_TEACHER": (
        "In {domain}, {subject} scores lower on questions that combine more than one "
        "concept than on questions that stay within a single concept. {marks_lost} of "
        "the {marks_available} marks available on combined questions were not scored."
    ),
    "E4_PARENT": (
        "In {domain}, {student} handles questions about one topic at a time, and loses "
        "marks when a question needs two topics put together. Of the "
        "{marks_available} marks on that second kind, {marks_lost} were not scored."
    ),
    "E4_STUDENT": (
        "In {domain}, you lose more marks when a question needs two topics together "
        "than when it stays on one. Of the {marks_available} marks on those, "
        "{marks_lost} were not scored."
    ),

    # F5.5 Variant Weakness
    "E5_TEACHER": (
        "Within {domain}, {subject} scores lowest on questions involving {variant}. "
        "{marks_lost} of the {marks_available} marks on those questions were not "
        "scored."
    ),
    "E5_PARENT": (
        "Within {domain}, the marks are going mainly on one specific kind of question: "
        "{variant}. Of the {marks_available} marks on that kind, {marks_lost} were "
        "not scored."
    ),
    "E5_STUDENT": (
        "Within {domain}, your lowest scores are on {variant} questions. Of the "
        "{marks_available} marks on those, {marks_lost} were not scored."
    ),

    # F5.6 Self-comparison, four cells x three registers
    "E6_GAP_ABOVE_TEACHER": (
        "Across this paper, {subject} answers direct recall questions correctly more "
        "often than questions requiring application. Their score on application "
        "questions is above the class median."
    ),
    "E6_GAP_ABOVE_PARENT": (
        "Across this paper, {student} does better on questions asking them to state "
        "something than on questions asking them to use it. On the second kind they "
        "are still above the middle of the class."
    ),
    "E6_GAP_ABOVE_STUDENT": (
        "Across this paper, you scored higher on questions asking you to state "
        "something than on questions asking you to use it. On the second kind you are "
        "still above the middle of your class."
    ),
    "E6_GAP_BELOW_TEACHER": (
        "Across this paper, {subject}'s marks come mainly from direct recall "
        "questions. Their score on application questions is at or below the class "
        "median."
    ),
    "E6_GAP_BELOW_PARENT": (
        "Across this paper, {student}'s marks are coming mainly from questions asking "
        "them to state something they have learned. On questions asking them to use "
        "it, they are at or below the middle of the class."
    ),
    "E6_GAP_BELOW_STUDENT": (
        "Across this paper, your marks are coming mainly from questions asking you to "
        "state something. On questions asking you to use it, you are at or below the "
        "middle of your class."
    ),
    "E6_LEVEL_ABOVE_TEACHER": (
        "Across this paper, {subject} scores at a similar level on direct recall and "
        "on application questions, and above the class median on both."
    ),
    "E6_LEVEL_ABOVE_PARENT": (
        "Across this paper, {student} scores at a similar level on both kinds of "
        "question, and above the middle of the class on both."
    ),
    "E6_LEVEL_ABOVE_STUDENT": (
        "Across this paper, you scored at a similar level on both kinds of question, "
        "and above the middle of your class on both."
    ),
    "E6_LEVEL_BELOW_TEACHER": (
        "Across this paper, {subject} scores at a similar level on direct recall and "
        "on application questions, and at or below the class median on both."
    ),
    "E6_LEVEL_BELOW_PARENT": (
        "Across this paper, {student} scores at a similar level on both kinds of "
        "question, and at or below the middle of the class on both."
    ),
    "E6_LEVEL_BELOW_STUDENT": (
        "Across this paper, you scored at a similar level on both kinds of question, "
        "and at or below the middle of your class on both."
    ),
    "E6_MODIFIER_COMPRESSION_TEACHER": (
        "One of the two groups is at or near full marks on this paper, which narrows "
        "the difference this comparison is able to show."
    ),
    "E6_MODIFIER_COMPRESSION_PARENT": (
        "One of the two groups is at or near full marks, so this comparison can only "
        "show so much."
    ),
    "E6_MODIFIER_COMPRESSION_STUDENT": (
        "One of the two groups is at or near full marks, so this comparison can only "
        "show so much."
    ),

    # F5.7 Diffuse Signal
    "E7_TEACHER": (
        "In {domain}, {student} scored above zero and below full marks on {n} of {m} "
        "questions, and {x} percentage points below their own average across the rest "
        "of this paper. The losses are even across topics within the chapter, across "
        "question lengths, and across the class. This paper does not identify which "
        "part of the chapter the marks were lost on. The scripts need to be looked at "
        "before any practice is set."
    ),
    "E7_PARENT": (
        "In {domain}, {student} is picking up most of the marks on most questions but "
        "losing a small number on nearly all of them. The pattern is even right across "
        "the chapter, so this test does not tell us which part to work on. We have "
        "asked the teacher to look at the scripts before setting extra work."
    ),
    "E7_STUDENT": (
        "In {domain}, you are getting most of the marks on most questions but losing a "
        "few on nearly all of them. This paper does not show which part of the chapter "
        "they are coming from, so your teacher needs to look at your script before you "
        "start extra practice on it."
    ),
    "E7_COMPANION_TEACHER": (
        "This is an observation, not a diagnosis. Three explanations remain open: an "
        "even but shallow grasp of the chapter, a set of unrelated small errors, and "
        "one habit repeated across questions. They require different work, and this "
        "paper cannot tell them apart."
    ),
    "E7_COMPANION_PARENT": (
        "This is something we have noticed, not something we have explained. There "
        "are three possible reasons and they need different kinds of help. This test "
        "cannot tell us which one it is."
    ),
    "E7_COMPANION_STUDENT": (
        "This is something the paper shows, not something it explains. There are "
        "three possible reasons and they need different fixes, so it is worth waiting "
        "for your teacher to look before you pick one."
    ),

    # F5.8 Gap to Reference Band
    "E8_TEACHER": (
        "{student}'s total on this paper is {gap} marks below the combined average of "
        "the five highest scorers in this class. {conc} of those {gap} marks sit in "
        "two chapters: {chapter_a} and {chapter_b}."
    ),
    "E8_PARENT": (
        "{student}'s total on this paper is {gap} marks below the average of the five "
        "highest scorers in the class. Most of that difference, {conc} marks, comes "
        "from two chapters: {chapter_a} and {chapter_b}."
    ),
    "E8_STUDENT": (
        "Your total on this paper is {gap} marks below the average of the five highest "
        "scorers in your class. {conc} of those {gap} marks came from two chapters: "
        "{chapter_a} and {chapter_b}."
    ),
    "E8_MODIFIER_INCOMPLETE_TEACHER": (
        "Part of this difference is on questions that were not attempted rather than "
        "attempted and lost."
    ),
    "E8_MODIFIER_INCOMPLETE_PARENT": (
        "Some of this difference is on questions that were left blank rather than "
        "answered and marked down."
    ),
    "E8_MODIFIER_INCOMPLETE_STUDENT": (
        "Some of this difference is on questions you left blank rather than answered "
        "and lost marks on."
    ),

    # G3 shape statement
    "SHAPE_TEACHER": (
        "This paper asked {r} recall-tier questions and {n} questions requiring "
        "application or analysis, across {c} chapters. Results describe performance on "
        "the questions that were asked. Where a chapter did not carry enough questions "
        "of a given type, no conclusion of that type is drawn, and those chapters are "
        "listed at the end of this report."
    ),
    "SHAPE_PARENT": (
        "This test asked {r} questions that ask a student to state something learned, "
        "and {n} that ask them to use it, across {c} chapters. What follows describes "
        "how {student} did on the questions that were actually asked. Where a chapter "
        "did not have enough of one kind of question, we do not draw a conclusion about "
        "it, and those chapters are listed at the end."
    ),
    "SHAPE_STUDENT": (
        "This paper asked {r} questions that ask you to state something and {n} that "
        "ask you to use it, across {c} chapters. What follows is about the questions "
        "that were actually asked. Where a chapter did not carry enough of one kind, no "
        "conclusion is drawn about it, and those are listed at the end."
    ),

    # G4 priority watch list
    "PRIORITY_WATCH": (
        "Priority watch. These topics recur frequently on board papers and showed "
        "weaker patterns in this paper that the evidence does not support stating "
        "confidently: {families}."
    ),

    # G5 overflow
    "OVERFLOW": "{n} further {band}-confidence observations were not included.",

    # G6 marks summary block
    "MARKS_SUMMARY_TEACHER": (
        "Across the findings below, {total_lost} of the {total_available} marks "
        "available on the questions those findings cover were not scored. This counts "
        "each question once. It does not include chapters listed at the end of this "
        "report as not diagnosable, and it is not a figure for marks that could be "
        "recovered."
    ),
    "MARKS_SUMMARY_PARENT": (
        "Across the points below, {total_lost} of the {total_available} marks on the "
        "questions involved were not scored. Each question is counted once. It does "
        "not cover the chapters listed at the end, and it is not a prediction of what "
        "could be regained."
    ),
}


def render(key: str, **kwargs) -> str:
    return STRINGS[key].format(**kwargs)


def _self_check() -> None:
    for key, template in STRINGS.items():
        # Templates carry slots; check the raw template text minus braces content
        # is still meaningful to scan literally (slots themselves never contain
        # banned words in this table).
        failures = check_boundaries(template, key=key)
        if failures:
            raise AssertionError(f"Frozen string '{key}' fails boundary checks: {failures}")


_self_check()
