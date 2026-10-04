"""When a placement needs a person (review_flag_rule).

A flag is a request for someone's time, so it must mean something. A row is flagged for
one of seven reasons only, and the reason is stored on it (question_placement.review_reason)
so the review screen, the evaluation and a teacher can all see why:

``judge_failed``      the chapter judge could not be asked about this question
``cross_scope``       the placement left the scope the paper declares for the question
``blueprint_overruled`` the paper's declared blueprint (its marks per chapter) moved the
                      question to a chapter other than the chapter judge's
``family``            the concept family is unsettled (several claim the section) or blocked
``low_confidence``    the chapter judge was below 0.7 with more than one chapter to choose
``topic_differs``     the topic judge's section differs from in-chapter retrieval's, and
                      answerability did not verify the judge's section
``topic_unverified``  the topic judge verified nothing: no section of the chapter could
                      answer the question on its own, or the judge gave no answer at all

A citation problem is not one of them (see grounding.resolve_citations), and neither is a
disagreement that answerability settled, nor a thin margin between the judge's top two
chapters.
"""

from __future__ import annotations

from dataclasses import dataclass

#: in priority order -- the order they are stored in
REASONS = (
    "judge_failed", "cross_scope", "blueprint_overruled", "family", "low_confidence", "topic_differs",
    "topic_unverified",
)
#: the chapter judge's own confidence below which a choice among chapters is doubted
LOW_CONFIDENCE = 0.7
#: question_placement.review_reason's width
REASON_WIDTH = 64


@dataclass(frozen=True)
class ReviewInputs:
    judge_failed: bool = False
    cross_scope: bool = False
    blueprint_overruled: bool = False
    family_unsettled: bool = False
    family_blocked: bool = False
    #: the chapter judge's own confidence; None when it was not asked
    chapter_confidence: float | None = None
    #: how many chapters the chapter judge chose among
    chapters_shown: int = 0
    #: the topic pick: its section, in-chapter retrieval's section, whether answerability
    #: verified it (True / False / None = never checked), and who decided ("judge",
    #: "retrieval" when the topic judge gave no answer, "none" when the chapter has no
    #: section text); all None when no topic was picked
    topic_section: str | None = None
    retrieval_section: str | None = None
    topic_verified: bool | None = None
    topic_source: str | None = None


def _related(a: str | None, b: str | None) -> bool:
    from app.classify.topic import _related as related

    return related(a, b)


def review_reasons(i: ReviewInputs) -> list[str]:
    """The reasons this placement needs a person, in priority order; [] for none."""
    out: list[str] = []
    if i.judge_failed:
        out.append("judge_failed")
    if i.cross_scope:
        out.append("cross_scope")
    if i.blueprint_overruled:
        out.append("blueprint_overruled")
    if i.family_unsettled or i.family_blocked:
        out.append("family")
    if (i.chapter_confidence is not None and i.chapter_confidence < LOW_CONFIDENCE
            and i.chapters_shown > 1):
        out.append("low_confidence")
    if (i.topic_source == "judge" and i.topic_section is not None
            and i.retrieval_section is not None
            and not _related(i.topic_section, i.retrieval_section)
            and i.topic_verified is not True):
        out.append("topic_differs")
    if i.topic_verified is False or i.topic_source == "retrieval":
        out.append("topic_unverified")
    return out


def reason_code(reasons: list[str]) -> str | None:
    """The reasons as stored: comma-joined in priority order, whole codes only, within
    the column's width. None for no reason."""
    kept: list[str] = []
    for r in reasons:
        if len(",".join([*kept, r])) > REASON_WIDTH:
            break
        kept.append(r)
    return ",".join(kept) or None
