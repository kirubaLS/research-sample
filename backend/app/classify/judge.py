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

    chapter: str = Field(description="Exactly one of the candidate chapter names supplied")
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
    #: set when the question could legitimately sit in more than one chapter
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
you were not shown, even if you believe it fits better. If none of the passages fits, pick
the closest and say so in your reasoning with a low confidence.

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

Confidence is your own honest estimate that a CBSE teacher would agree with the chapter.
Use below 0.7 whenever the question could reasonably sit in another chapter, and name that
chapter in alternative_chapter. An abstention costs a minute of a teacher's time; a
confident wrong answer goes into a report and is acted on."""


def build_prompt(question: str, evidence: list[Evidence]) -> str:
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
        lines.append(f"\n[{i}] {e.chapter} -- {e.reference}{section}\n{e.text[:1200]}")
    return "\n".join(lines)
