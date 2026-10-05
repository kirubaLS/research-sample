"""Tier 0: when the retrievers alone are sure enough that the chapter judge need not be asked.

The chapter judge is the first of the placement path's paid calls, and for most questions
it confirms what retrieval already said. A gate that can tell those questions apart from
the ones that need reading removes that call without touching the hard ones -- the cascade
shape of FrugalGPT, with application-side signals standing in for the model's own
confidence, which is poorly calibrated.

The signals are the two the retrieval verdict already carries:

* the lexical and semantic retrievers each ranked the same chapter first
  (``ChapterVerdict.agreed``), and
* the winner leads the runner-up by a clear share of its own score. Relative, because the
  fused score is a sum of reciprocal ranks and its absolute scale means nothing.

The threshold is not known in advance. The gate therefore runs in shadow first: it is
evaluated for every question while the judge is still asked, and the job result reports how
often the two agreed (``summarise``). Only a measured agreement rate should switch
enforcement on.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Gate:
    passed: bool
    chapter: str | None
    relative_margin: float
    #: why it did not pass, for the shadow report; empty when it did
    reason: str = ""


def chapter_gate(verdict, chapter: str | None, *, min_relative_margin: float) -> Gate:
    """Would retrieval alone have placed this question confidently?

    ``verdict`` is a ``ChapterVerdict``; ``chapter`` is its winner's chapter name.
    """
    if verdict.node_id is None or chapter is None:
        return Gate(False, None, 0.0, "nothing retrieved")
    relative = verdict.margin / verdict.score if verdict.score > 0 else 0.0
    if not verdict.agreed:
        return Gate(False, chapter, relative, "the retrievers disagree")
    if relative < min_relative_margin:
        return Gate(False, chapter, relative, "narrow lead over the runner-up")
    return Gate(True, chapter, relative)


def summarise(log: dict[str, dict]) -> dict:
    """The shadow report: how many questions the gate would have settled, and of those
    how many the chapter judge then named the same chapter for.

    A question the judge was not asked about (a declared single chapter, a gate that was
    enforced) carries no ``judge_chapter`` and counts as neither agreeing nor disagreeing.
    """
    passed = [e for e in log.values() if e["passed"]]
    compared = [e for e in passed if "judge_chapter" in e]
    agreed = sum(1 for e in compared if e["judge_chapter"] == e["chapter"])
    return {
        "evaluated": len(log),
        "passed": len(passed),
        "enforced": sum(1 for e in passed if e.get("enforced")),
        "compared": len(compared),
        "agreed_with_judge": agreed,
        "disagreed_with_judge": len(compared) - agreed,
    }
