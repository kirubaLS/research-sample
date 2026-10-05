"""Read a scanned paper with the cheap model first, and the strong one only if it must.

Every scanned page used to go to the strongest model. A paper prints its own checksums --
how many questions it has, its maximum marks -- and those equations are the cheap model's
exam: a read that reproduces both is very likely a read that did not drop or invent a
question. One that does not is re-read, whole, by the strong model.

What the checksums cannot see is a question whose wording was misread but whose marks were
right. That error survives the cheap read and reaches the mapper as a slightly wrong stem.
So this is OFF unless ``vision_cheap_model`` is set, and the first thing to do with it on is
read a few papers both ways and compare the stems, not only the totals.

A paper that prints neither checksum is unverifiable, and an unverifiable cheap read is
always escalated: nothing vouches for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.extraction.address import Address
from app.extraction.choice import group_choices
from app.extraction.paper import context_addresses

TOLERANCE = 0.01


@dataclass
class Consistency:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def read_total(questions) -> float:
    """What a read is worth, each choice counted once (the rule confirm_scan holds a paper
    to: never a naive sum of every row)."""
    context = context_addresses(questions)
    countable = [q for q in questions if q.address not in context and not q.is_context]
    grouped = [q for q in countable if q.attempt_required]
    ungrouped = [q for q in countable if not q.attempt_required]
    total = float(sum(float(q.max_marks or 0) for q in ungrouped if q.choice_alt in (None, "a")))
    if grouped:
        rows = [(Address(q.section, q.question_no, q.sub_part, q.choice_alt),
                 float(q.max_marks or 0)) for q in grouped]
        required = {Address(q.section, q.question_no, q.sub_part, q.choice_alt).key:
                    q.attempt_required for q in grouped}
        _, groups = group_choices(rows, required)
        keys = {a.key for g in groups for a in g.addresses}
        total += sum(g.marks for g in groups)
        total += sum(m for a, m in rows if a.key not in keys and a.choice_alt in (None, "a"))
    return total


def check(reading) -> Consistency:
    """Does this read reproduce what the paper says about itself?"""
    reasons: list[str] = []
    if reading.refused:
        return Consistency(False, [f"refused: {reading.refused[:80]}"])
    if reading.problems:
        reasons.append(f"{len(reading.problems)} page problem(s)")
    context = context_addresses(reading.questions)
    counted = [q for q in reading.questions if q.address not in context and not q.is_context]
    if any(q.max_marks is None for q in counted):
        reasons.append("a question was read with no marks")
    if any(not (q.stem_text or "").strip() for q in counted):
        reasons.append("a question was read with no text")
    if reading.declared_total is None and reading.declared_count is None:
        reasons.append("the paper declares no total or count to check against")
    if reading.declared_total is not None:
        got = read_total(reading.questions)
        if abs(got - float(reading.declared_total)) > TOLERANCE:
            reasons.append(f"marks add to {got:g}, the paper says {reading.declared_total:g}")
    if reading.declared_count is not None:
        numbers = {q.question_no for q in counted}
        if len(numbers) != int(reading.declared_count):
            reasons.append(f"{len(numbers)} questions read, the paper says {reading.declared_count}")
    return Consistency(not reasons, reasons)


def read_with_cascade(pages, *, cheap, strong, read, on_progress=None, **options):
    """``read(pages, model=..., on_progress=..., **options)`` with ``cheap`` first.

    Returns ``(reading, report)``. The report says which model's read was kept, why the
    cheap one was not trusted, and how many pages each model read -- what the cost saving
    is measured from.
    """
    first = read(pages, model=cheap, on_progress=on_progress, **options)
    verdict = check(first)
    report = {"cheap_model": cheap, "strong_model": strong, "escalated": not verdict.ok,
              "reasons": verdict.reasons, "pages": len(pages),
              "cheap_pages": len(pages), "strong_pages": 0}
    if verdict.ok:
        return first, report
    second = read(pages, model=strong, on_progress=on_progress, **options)
    report["strong_pages"] = len(pages)
    return second, report
