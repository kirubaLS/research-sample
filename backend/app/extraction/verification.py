"""The four gates a question paper must pass.

Every equation comes from the paper itself — CBSE prints all of them on page 1 and in the
section headers, which is what makes extraction verifiable rather than merely probable.

  G1  extracted question count      == declared question count
  G2  per-section marks             == declared section marks   (after choice-grouping)
  G3  printed section arithmetic    'a x b = c' holds
  G4  sum over sections             == 'Maximum Marks : 80'

A failure blocks the paper and names the equation that broke. It never guesses.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from app.extraction.address import Address
from app.extraction.choice import ChoiceGroup, effective_total

TOLERANCE = 1e-6


@dataclass
class GateResult:
    gate: str
    passed: bool
    expected: float | int | None = None
    actual: float | int | None = None
    detail: str = ""


@dataclass
class VerificationReport:
    results: list[GateResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failures(self) -> list[GateResult]:
        return [r for r in self.results if not r.passed]

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "gates": [
                {
                    "gate": r.gate,
                    "passed": r.passed,
                    "expected": r.expected,
                    "actual": r.actual,
                    "detail": r.detail,
                }
                for r in self.results
            ],
        }


def verify_paper(
    rows: list[tuple[Address, float]],
    groups: list[ChoiceGroup],
    declared: dict,
    *,
    section_arithmetic: dict[str, tuple[int, float, float]] | None = None,
) -> VerificationReport:
    """``declared`` carries what the paper printed:

    ``{'question_count': 38, 'total_marks': 80, 'sections': {'A': 20, 'B': 20, ...}}``

    ``section_arithmetic`` carries any printed ``a x b = c`` per section.
    """
    report = VerificationReport()
    grouped_keys = {a.key for g in groups for a in g.addresses}

    # --- G1: question count. Distinct question numbers, choice alternatives counted once.
    distinct_questions = {(a.section, a.question_no) for a, _ in rows}
    expected_count = declared.get("question_count")
    if expected_count is not None:
        report.results.append(
            GateResult(
                "G1_question_count",
                len(distinct_questions) == expected_count,
                expected_count,
                len(distinct_questions),
                "distinct (section, question_no) pairs after de-duplication",
            )
        )

    # --- G2: per-section marks, with each choice group counted once
    per_section: dict[str, float] = defaultdict(float)
    for a, m in rows:
        if a.key in grouped_keys:
            continue
        per_section[a.section or ""] += m
    for g in groups:
        per_section[g.addresses[0].section or ""] += g.marks

    for sec, expected in (declared.get("sections") or {}).items():
        actual = per_section.get(sec, 0.0)
        report.results.append(
            GateResult(
                f"G2_section_marks[{sec}]",
                abs(actual - expected) < TOLERANCE,
                expected,
                actual,
                "section total after choice-grouping and language de-duplication",
            )
        )

    # --- G3: printed section arithmetic
    for sec, (n, per, total) in (section_arithmetic or {}).items():
        report.results.append(
            GateResult(
                f"G3_section_arithmetic[{sec}]",
                abs(n * per - total) < TOLERANCE,
                total,
                n * per,
                f"paper prints {n} x {per} = {total}",
            )
        )

    # --- G4: paper total
    expected_total = declared.get("total_marks")
    if expected_total is not None:
        actual_total = effective_total(rows, groups)
        report.results.append(
            GateResult(
                "G4_paper_total",
                abs(actual_total - expected_total) < TOLERANCE,
                expected_total,
                actual_total,
                "sum over sections after de-duplication and choice-grouping",
            )
        )

    return report
