"""Resolving a written question label against a paper's own Q-matrix.

Shared by every reading path that turns a label like ``Q4`` or ``B/4//`` into a real
``Question`` -- a single student's file (``reading.py``) and a class mark-entry sheet
(``gridsheets.py`` ) alike -- so the two cannot drift into disagreeing about what a label
means.
"""

from __future__ import annotations

from app.extraction.address import Address
from app.models import Question


def match_address(questions: list[Question], raw: str | None) -> tuple[Question | None, str | None]:
    """Resolve a parsed address against the paper. The paper is the vocabulary.

    A sheet often writes ``Q4`` where the paper says ``B/4//``. Matching on the question
    number alone is right when it is unambiguous and wrong the moment two sections both
    have a question 4 -- so an ambiguous label is reported as ambiguous rather than
    resolved to whichever came first.
    """
    if not raw:
        return None, "no question number"
    exact = [q for q in questions if q.address == raw]
    if exact:
        return exact[0], None

    parsed = Address.parse(raw.replace("/", " ")) if "/" in raw else None
    parts = raw.split("/")
    number = parts[1] if len(parts) == 4 and parts[1] else (parsed.question_no if parsed else None)
    sub = parts[2] if len(parts) == 4 and parts[2] else None
    alt = parts[3] if len(parts) == 4 and parts[3] else None
    if not number:
        return None, f"{raw!r} is not a question on this paper"

    candidates = [
        q for q in questions
        if q.question_no == number
        and (q.sub_part or "") == (sub or "")
        and (q.choice_alt or "") == (alt or "")
    ]
    if len(candidates) == 1:
        return candidates[0], None
    if not candidates:
        return None, f"this paper has no question {number}"
    return None, (
        f"question {number} is ambiguous: the paper has it in "
        + ", ".join(sorted({c.section or "no section" for c in candidates}))
        + ". Write the section too, as B/" + number + "."
    )
