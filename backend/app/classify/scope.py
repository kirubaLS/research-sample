"""Work out what a paper covers, from the paper.

Asking a teacher to declare the scope pushes work onto a human that the paper already
answers. And inferring it is an easier problem than classifying any single question: a
cyclic test carries twenty to forty questions, each voting independently for a chapter, so
even at eighty-five percent per-question accuracy a chapter that twelve questions agree on
is nearly certain, while a chapter one question lands in alone is far more likely to be a
misplacement than a fourth topic. Errors are independent; the signal aggregates.

**The trap, and why the guards below exist.** Two-pass placement makes confident mistakes
stickier. If the classifier systematically reads cone questions as trigonometry, then
trigonometry looks in scope, and the second pass -- now told trigonometry is allowed --
repeats the error with more conviction. So a chapter earns a place in the scope only on
evidence a single systematic bias cannot manufacture: several questions, a real share of
the marks, and confidence the classifier itself was willing to stand behind.

The output is a proposal. A teacher confirming "this test covers Real Numbers, Polynomials
and Triangles" is one glance; confirming thirty-eight placements is an afternoon. Getting
the scope right is worth more than getting any question right, because it constrains all of
them.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Vote:
    """One question's opinion about which chapter it belongs to."""

    question_id: str
    chapter: str
    marks: float
    confidence: float


@dataclass
class InferredScope:
    chapters: set[str] = field(default_factory=set)
    #: chapter -> (questions, marks, mean confidence) for everything that voted
    tally: dict[str, tuple[int, float, float]] = field(default_factory=dict)
    #: chapters that voted but did not clear the bar, and why
    rejected: dict[str, str] = field(default_factory=dict)
    confident: bool = False
    note: str = ""


#: A chapter needs at least this many questions to count as a topic of the test. One
#: question is what a misplacement looks like.
MIN_QUESTIONS = 2
#: ...or this share of the paper's marks, which lets a single heavy question stand as a
#: topic in its own right -- a five-mark question is not an accident.
MIN_MARK_SHARE = 0.10
#: votes below this are not evidence of anything
MIN_VOTE_CONFIDENCE = 0.60
#: Below this many questions there is nothing to aggregate, and the whole argument for
#: inferring a scope was that errors are independent and cancel. On a three-question paper
#: a single misplacement IS the consensus -- and then the second pass deletes the right
#: chapter, which is worse than the misplacement it was meant to fix.
MIN_PAPER_QUESTIONS = 8


def infer_scope(
    votes: list[Vote],
    *,
    min_questions: int = MIN_QUESTIONS,
    min_mark_share: float = MIN_MARK_SHARE,
    min_confidence: float = MIN_VOTE_CONFIDENCE,
    min_paper_questions: int = MIN_PAPER_QUESTIONS,
) -> InferredScope:
    """Which chapters this paper is about, from how its questions fall.

    Only confident votes count towards admitting a chapter. An unconfident vote cannot
    create a topic; it can only be explained by one.
    """
    if not votes:
        return InferredScope(note="no questions to infer a scope from")
    if len(votes) < min_paper_questions:
        return InferredScope(
            note=(
                f"only {len(votes)} question(s): too few to infer a scope from. Errors "
                f"cancel across a paper, not across a handful, and a scope inferred from "
                f"a handful would delete the chapters it got wrong."
            )
        )

    total_marks = sum(v.marks for v in votes) or 1.0
    grouped: dict[str, list[Vote]] = defaultdict(list)
    for vote in votes:
        grouped[vote.chapter].append(vote)

    tally: dict[str, tuple[int, float, float]] = {}
    chapters: set[str] = set()
    rejected: dict[str, str] = {}

    for chapter, group in grouped.items():
        strong = [v for v in group if v.confidence >= min_confidence]
        marks = sum(v.marks for v in strong)
        share = marks / total_marks
        mean_confidence = (
            sum(v.confidence for v in group) / len(group) if group else 0.0
        )
        tally[chapter] = (len(group), sum(v.marks for v in group), round(mean_confidence, 3))

        if not strong:
            rejected[chapter] = (
                f"no confident question placed here (best {max(v.confidence for v in group):.2f})"
            )
        elif len(strong) >= min_questions or share >= min_mark_share:
            chapters.add(chapter)
        else:
            rejected[chapter] = (
                f"only {len(strong)} confident question worth {marks:g} mark(s), "
                f"{share:.0%} of the paper -- more likely a misplacement than a topic"
            )

    covered = sum(
        sum(v.marks for v in grouped[c]) for c in chapters
    ) / total_marks

    return InferredScope(
        chapters=chapters,
        tally=tally,
        rejected=rejected,
        # A scope that explains most of the paper is one to act on. A scope that leaves a
        # third of the marks outside it has not understood the paper, whatever it admitted.
        confident=bool(chapters) and covered >= 0.80,
        note=(
            f"{len(chapters)} chapter(s) account for {covered:.0%} of the marks"
            if chapters else
            "no chapter cleared the bar -- the paper may cover more topics than it has "
            "questions, or the placements are too weak to infer anything from"
        ),
    )
