"""Science-only mapping rules.

Everything here acts for a paper of the subject ``X.SCI`` and for no other: each entry point
is gated by ``science_on``, which is False for any other subject whatever the flags say. The
flags (``science_section_scope``, ``science_instruction_rows``) default OFF and are not part
of the shared per-subject list in ``app.mapping.subject_scope``: turning one on changes
Science and nothing else, and nothing about Social Science, Mathematics or the languages.

**Section scope.** A Science paper's sections are often one discipline each (this school's
paper: A Biology, B Chemistry, C Physics) -- but not always (a board paper's sections are by
kind of question and mix all three). So the rule is read off the paper, never assumed: once a
paper's questions have a first chapter each, a section whose questions are overwhelmingly one
discipline (``MIN_SHARE`` of at least ``MIN_QUESTIONS``), or whose printed title names one,
may only be placed in that discipline's chapters. A mixed section is left alone.

**Instruction-only rows.** "For Questions 8 and 9, two statements are given ... Assertion (A)
... Reason (R)" with no assertion or reason after it, or "Attempt either option (a) or (b) :"
with nothing else, is a heading, not a question. Placing it by its words files it under
whatever chapter the boilerplate happens to resemble.
"""

from __future__ import annotations

import re
from collections import Counter

SCIENCE = "X.SCI"

BIOLOGY, CHEMISTRY, PHYSICS = "biology", "chemistry", "physics"
CHAPTER_DISCIPLINE = {
    "X.SCI.LIFEPROC": BIOLOGY, "X.SCI.CONTROL": BIOLOGY, "X.SCI.REPRO": BIOLOGY,
    "X.SCI.HEREDITY": BIOLOGY, "X.SCI.ENVIRONMENT": BIOLOGY,
    "X.SCI.CHEMRXN": CHEMISTRY, "X.SCI.ACIDS": CHEMISTRY, "X.SCI.METALS": CHEMISTRY,
    "X.SCI.CARBON": CHEMISTRY,
    "X.SCI.LIGHT": PHYSICS, "X.SCI.EYE": PHYSICS, "X.SCI.ELECTRICITY": PHYSICS,
    "X.SCI.MAGNETIC": PHYSICS,
}

#: a section is one discipline when at least this share of its questions are, and it has at
#: least this many questions (fewer is not enough to out-vote a single wrong first guess)
MIN_SHARE = 0.75
MIN_QUESTIONS = 4

_TITLE_WORDS = (
    (BIOLOGY, re.compile(r"\b(biology|life\s+science|botany|zoology)\b", re.I)),
    (CHEMISTRY, re.compile(r"\bchemi(stry|cal)\b", re.I)),
    (PHYSICS, re.compile(r"\bphysics\b", re.I)),
)


def science_on(settings, subject_code: str | None, flag: str) -> bool:
    """The flag is on AND the paper is a Science paper. Any other subject: False."""
    return bool(getattr(settings, flag, False)) and subject_code == SCIENCE


def chapters_of(discipline: str) -> frozenset[str]:
    return frozenset(code for code, d in CHAPTER_DISCIPLINE.items() if d == discipline)


def _letter(section: str | None) -> str:
    return (section or "").strip().upper()


def section_disciplines(
    first_chapters: list[tuple[str | None, str]], titles: dict[str, str] | None = None,
) -> dict[str, str]:
    """section letter -> discipline, for the sections that have one.

    ``first_chapters`` are (section letter, the chapter code each of its questions was first
    placed in). A printed section title naming a discipline wins; otherwise the vote."""
    out: dict[str, str] = {}
    for letter, title in (titles or {}).items():
        for discipline, pattern in _TITLE_WORDS:
            if title and pattern.search(title):
                out[_letter(letter)] = discipline
                break
    votes: dict[str, Counter] = {}
    for section, code in first_chapters:
        discipline = CHAPTER_DISCIPLINE.get(code)
        if discipline:
            votes.setdefault(_letter(section), Counter())[discipline] += 1
    for letter, tally in votes.items():
        if letter in out:
            continue
        total = sum(tally.values())
        discipline, count = tally.most_common(1)[0]
        if total >= MIN_QUESTIONS and count / total >= MIN_SHARE:
            out[letter] = discipline
    return out


def question_scopes(
    questions: list[tuple[str, str | None, str | None]],
    labels_by_code: dict[str, str],
    *,
    paper_scope: set[str] | None = None,
    titles: dict[str, str] | None = None,
) -> tuple[dict[str, set[str]], dict[str, str]]:
    """(question id -> the chapter LABELS it may be placed in, section letter -> discipline).

    ``questions`` are (id, section letter, first chapter code or None). A teacher's own
    paper-level scope (``paper_scope``, chapter labels) is respected: the discipline narrows
    within it, and when the two do not overlap the teacher's scope stands untouched."""
    sections = section_disciplines(
        [(s, c) for _, s, c in questions if c], titles,
    )
    out: dict[str, set[str]] = {}
    for qid, section, _ in questions:
        discipline = sections.get(_letter(section))
        if discipline is None:
            continue
        labels = {labels_by_code[c] for c in chapters_of(discipline) if c in labels_by_code}
        if paper_scope:
            labels = labels & paper_scope
        if labels:
            out[qid] = labels
    return out, sections


_AR_PREAMBLE = re.compile(r"two\s+statements\s+are\s+given", re.I)
_AR_STATEMENT = re.compile(r"assertion\s*\(\s*a\s*\)\s*[:：]\s*\S", re.I)
_EITHER_OR = re.compile(r"^\W*attempt\s+(either|any|one)\b[^.:?]{0,60}[:.]?\W*$", re.I)
_PASSAGE_ONLY = re.compile(r"^\W*read\s+the\s+following[^.:?]{0,80}(follow|below)\s*[:.]?\W*$", re.I)


def instruction_only(stem: str | None) -> str | None:
    """Why this row's text is an instruction and not a question, or None when it is one.

    Conservative on purpose: only the three printed boilerplates, and only when nothing of
    the question itself follows them."""
    text = " ".join((stem or "").split())
    if not text:
        return None
    if _AR_PREAMBLE.search(text) and not _AR_STATEMENT.search(text):
        return ("the assertion-and-reason instruction was read but not the assertion or the "
                "reason themselves, so there is nothing to place")
    if len(text) <= 120 and _EITHER_OR.match(text):
        return "an 'attempt either option' heading: the options are the rows after it"
    if len(text) <= 140 and _PASSAGE_ONLY.match(text):
        return "a 'read the following' heading with no passage read"
    return None


SKIP, BLOCK = "skip", "block"


def instruction_row_action(
    settings, subject_code: str | None, stem: str | None, siblings: int,
) -> tuple[str, str | None] | None:
    """What the map step does with a row, or None to treat it as an ordinary question.

    (SKIP, None): an instruction heading with rows after it -- its options -- left out like
    a case-study stem. (BLOCK, reason): an instruction standing alone, the question's own text
    not read -- blocked with the reason. Science papers with ``science_instruction_rows`` on,
    nobody else."""
    if not science_on(settings, subject_code, "science_instruction_rows"):
        return None
    reason = instruction_only(stem)
    if reason is None:
        return None
    return (SKIP, None) if siblings > 1 else (BLOCK, reason)
