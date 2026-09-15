"""Classify a question by reading the book, not by measuring distance to it.

Retrieval finds candidate passages; it cannot decide between them. The two failures on the
real 30(B) paper were both reasoning failures rather than retrieval failures:

* "in two triangles ABC and DEF, angle A = angle E and angle F = angle B, which of the
  following is NOT true" scored highest against a trigonometry passage. Similarity has no
  way to represent negation or angle correspondence -- it saw the word "angle".
* "slant height of a right circular cone, diameter 14, height 24" landed in Applications of
  Trigonometry, because that chapter is full of right triangles with a hypotenuse. It is
  the same geometry; only the context distinguishes them.

A model reading the retrieved passages can separate both. What it must not do is invent a
chapter: every answer is constrained to the candidates retrieval supplied, and the model is
required to name the evidence it used, so a wrong answer is inspectable rather than a
bare label.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

#: the board's own words, one field one name (app.models.assessment.TIERS)
TIERS = ("Remembering & Understanding", "Applying", "Analysing, Evaluating & Creating")


class Classification(BaseModel):
    """What the judge returns. Every field is checkable against something."""

    chapter: str | None = Field(
        description="Exactly one of the candidate chapter names supplied, or null for a "
        "genuinely skill-anchored question that has no content tie to any chapter"
    )
    curriculum_section: str | None = Field(
        default=None,
        description="The NCERT section number from the evidence, e.g. '12.2'. Null if the "
        "evidence does not pin one down -- do not guess.",
    )
    #: Not a free string: a paraphrase of a tier is not a tier, and the value is read by
    #: the report. Nullable because abstaining is a legitimate answer -- it is the only
    #: honest one when the evidence does not settle it.
    tier: str | None = Field(
        default=None, description="Exactly one of: " + "; ".join(TIERS) + ", or null"
    )
    #: what the student has to DO -- the schema's Skill Required, in the model's words
    skill_required: str = Field(max_length=200)
    #: 'the question asks which correspondence is invalid, which is the similarity criteria
    #: in Section 6.3' -- a reason a teacher can disagree with
    reasoning: str = Field(max_length=600)
    evidence: list[str] = Field(
        default_factory=list,
        description="References of the passages actually used, e.g. ['Theorem 6.3']",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    #: set when the question could legitimately sit in more than one chapter. Only
    #: meaningful when chapter is not null -- a skill-anchored question has no second
    #: guess to offer either, because it was never a content question in the first place.
    alternative_chapter: str | None = None


@dataclass(frozen=True)
class Evidence:
    chapter: str
    reference: str
    section: str
    text: str


SYSTEM = """You place CBSE Class X questions in the NCERT textbook.

You are given a question and passages retrieved from the book. Decide which chapter the
question belongs to, using only the chapters present in the passages -- never a chapter
you were not shown, even if you believe it fits better.

You have three honest answers, not two:

1. The question is ABOUT something in one of the candidate chapters (a theorem, a
   character, a grammar rule, a poem's theme). Pick that chapter.
2. The question is content-anchored -- it is clearly testing something from the book --
   but you cannot tell which of several candidate chapters from the evidence shown. Pick
   the closest one and say so in your reasoning, with confidence below 0.7 and the other
   candidate in alternative_chapter. This is still "the question is about a chapter",
   just an uncertain guess at which one.
3. The question is SKILL-ANCHORED: it has no content tie to any specific chapter because
   it is testing a general writing or language skill against a prompt invented for this
   paper -- a letter to a named recipient, an essay from a given outline, an unseen
   passage or picture composition, a notice or dialogue-writing task, a "rewrite in your
   own words" with no source text from the book. For these, set chapter to null and put
   what the student has to DO in skill_required (e.g. "write a formal letter requesting
   library books", "compose a narrative from a picture prompt"). This is a confident,
   correct answer, not a hedge: do not use a low confidence just because chapter is null,
   and do not force a chapter onto it merely because a passage was retrieved -- retrieval
   often returns the closest-sounding passage even when nothing in the book is what the
   question is actually asking for.

Case 3 is narrow. It is for a task that would be exactly the same question on a different
paper testing a different chapter -- the skill is what is being tested, not the content.
It is NOT an excuse to null out a question you are merely unsure about, or one that draws
on a specific chapter's vocabulary, characters, or grammar point even loosely -- that is
case 2. When in doubt whether a question has a content tie at all, prefer case 2: a
low-confidence guess that names real evidence is more useful to a teacher than an
abstention that turns out to have been avoidable.

Judge what the question ASKS, not which words it shares with a passage. A question about a
theorem is not the theorem. A question that asks which statement is NOT true is testing the
condition being violated. A question mentioning height and a right angle is not necessarily
trigonometry -- a cone's slant height is mensuration.

For the competency tier, use CBSE's own three:
- "Remembering & Understanding" -- recall a fact, state a definition, apply a formula the
  way it was taught
- "Applying" -- use a taught method in a situation that needs setting up first
- "Analysing, Evaluating & Creating" -- compare, justify, prove something not proved in the
  book, or work backwards from a result

Confidence is your own honest estimate that a CBSE teacher would agree with your answer --
the chapter you picked, or, for a null chapter, that the question really is skill-anchored
with no chapter to name. Use below 0.7 whenever a content-anchored question could
reasonably sit in another chapter, and name that chapter in alternative_chapter. A
low-confidence content guess costs a teacher a minute's review; a confident wrong chapter
goes into a report and is acted on -- and forcing a chapter onto a skill-anchored question
is exactly that failure, just dressed up as a guess."""


def build_prompt(
    question: str, evidence: list[Evidence], passage_chars: int = 1200
) -> str:
    """The question, and the book passages retrieval found for it."""
    chapters = sorted({e.chapter for e in evidence})
    lines = [
        "QUESTION",
        question.strip(),
        "",
        f"CANDIDATE CHAPTERS (choose exactly one): {', '.join(chapters)}",
        "",
        "PASSAGES FROM THE BOOK",
    ]
    for i, e in enumerate(evidence, 1):
        section = f" (section {e.section})" if e.section else ""
        # truncated: a whole exercise runs to 8500 characters and the useful signal is at
        # the start, while the tail is later questions that would pull the judge off
        lines.append(
            f"\n[{i}] {e.chapter} -- {e.reference}{section}\n{e.text[:passage_chars]}"
        )
    return "\n".join(lines)
