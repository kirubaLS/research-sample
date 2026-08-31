"""Proposing concept families by reading the chapter, not just its headings.

``app.curriculum.families`` proposes one family per section heading. That is honest and
free, and it is blind in one specific way: a heading is a division the authors chose for
*exposition*, and what a student can fail is a division of *practice*. NCERT sets "Mean of
Grouped Data" as one heading and then drills direct method, assumed-mean and
step-deviation as three separate exercise groups. A boy can be fine at the first and lost
in the third, and a report keyed on the heading averages that away.

A model reading the chapter's own exercises can see that split, because it is written in
the book. That is the entire job here: re-describe divisions the book already makes.
It is not asked to judge difficulty, invent a topic, or decide what matters.

Two guardrails, applied after the model answers and before anything is stored:

* **every family must cite chunks it was actually shown.** A citation the prompt did not
  contain is a fabrication, and the family is dropped rather than corrected -- there is
  nothing to correct it against.
* **a family that cites nothing is dropped.** With no evidence there is no way to tell a
  reading of the book from a memory of one.

Run once per subject. The output is a *proposal*, stored and never applied on its own:
renaming a family after a class has been tested breaks every trend that references it.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.curriculum.families import slugify

#: Enough of a chunk to tell what it is about. Whole chapters would work and cost more for
#: no gain: the task is topical, and the opening of an exercise or a worked example says
#: what it drills.
CHUNK_CHARS = 1200
#: A chapter that yields more than this has not been divided, it has been shredded. NCERT
#: chapters run to eight sections; a model returning fifteen families is describing
#: paragraphs.
MAX_PER_CHAPTER = 12


class FamilyProposal(BaseModel):
    """One proposed family. Every field is checkable against what the model was shown."""

    label: str = Field(description="Short name a teacher would recognise, e.g. 'Step-deviation method'")
    rationale: str = Field(description="Why this is one thing a student can be good or bad at")
    evidence: list[str] = Field(
        description="References of the passages this rests on, copied exactly as shown"
    )
    from_sections: list[str] = Field(
        default_factory=list, description="Section numbers it draws on, e.g. ['14.1']"
    )


class ChapterFamilies(BaseModel):
    families: list[FamilyProposal]


SYSTEM = """You divide a school textbook chapter into concept families.

A concept family is one thing a student can be separately good or bad at, and that a
teacher would reteach as a unit. It is the row label on a diagnostic report.

Rules, all of them absolute:
- Propose families ONLY for material in the passages you are shown. Never add a topic
  because you know the subject; if it is not in the passages, it does not exist here.
- Every family must cite the references of the passages it rests on, copied EXACTLY as
  they appear. Do not invent a reference. Do not cite a passage you were not shown.
- Prefer the chapter's own section headings. Split one only when the passages show the
  section drilling genuinely different procedures -- different worked methods, or
  exercises that require different steps. Say so in the rationale when you split.
- Merge two headings only when the passages show them requiring the same procedure.
- Do not propose a family for an introduction, a summary, or a list of formulae. A
  student is not weak at "Introduction".
- Do not judge difficulty, importance, or how often something is examined. You cannot
  know those from the book, and guessing them is the failure this task must avoid.

Return between 1 and 12 families. Fewer, well-chosen families are better than many."""


def build_prompt(chapter_label: str, passages: list[tuple[str, str, str]]) -> str:
    """``passages`` is (reference, section number, text).

    The reference is printed on its own line and the model is told to copy it: that is
    what makes a fabricated citation detectable rather than merely suspected.
    """
    parts = [
        f"Chapter: {chapter_label}",
        "",
        "Passages from this chapter. Cite by the reference shown in [brackets].",
        "",
    ]
    for reference, section, text in passages:
        body = text.strip()
        if len(body) > CHUNK_CHARS:
            body = body[:CHUNK_CHARS] + " ..."
        parts.append(f"[{reference}] (section {section or '?'})\n{body}\n")
    parts.append("Propose the concept families for this chapter.")
    return "\n".join(parts)


@dataclass
class Grounded:
    families: list[FamilyProposal]
    violations: list[str]


def ground(
    proposals: ChapterFamilies, shown: list[tuple[str, str, str]]
) -> Grounded:
    """Drop anything the passages cannot vouch for, and say what was dropped.

    Dropped, never repaired. A family whose citations do not exist is not a good family
    with a bad footnote -- there is no way to tell what it was actually based on.
    """
    references = {reference for reference, _, _ in shown}
    kept: list[FamilyProposal] = []
    violations: list[str] = []

    for family in proposals.families:
        label = family.label.strip()
        if not label:
            violations.append("dropped a family with no label")
            continue
        cited = [e for e in family.evidence if e in references]
        invented = [e for e in family.evidence if e not in references]
        if invented:
            violations.append(
                f"{label!r} cited passages that were not shown: {', '.join(sorted(invented))}"
            )
            continue
        if not cited:
            violations.append(f"{label!r} cited no passage, so nothing supports it")
            continue
        kept.append(family.model_copy(update={"label": label, "evidence": cited}))

    if len(kept) > MAX_PER_CHAPTER:
        violations.append(
            f"kept the first {MAX_PER_CHAPTER} of {len(kept)} families: more than that is "
            f"a description of paragraphs, not of learning areas"
        )
        kept = kept[:MAX_PER_CHAPTER]

    deduped: list[FamilyProposal] = []
    seen: set[str] = set()
    for family in kept:
        code = slugify(family.label)
        if code in seen:
            violations.append(f"{family.label!r} duplicates a family already proposed")
            continue
        seen.add(code)
        deduped.append(family)
    return Grounded(deduped, violations)


class AnthropicFamilyProposer:
    """One call per chapter. Haiku by default -- the task is reading, not reasoning."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5") -> None:
        if not api_key:
            raise ValueError(
                "no Anthropic API key. Set YAADHUM_ANTHROPIC_API_KEY. Without it the "
                "section headings are the only proposal available, which cannot see a "
                "heading that drills two different procedures."
            )
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.violations: list[tuple[str, list[str]]] = []

    def propose(self, chapter_label: str, passages: list[tuple[str, str, str]]) -> list[FamilyProposal]:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=4000,
            system=SYSTEM,
            messages=[{"role": "user", "content": build_prompt(chapter_label, passages)}],
            output_format=ChapterFamilies,
        )
        checked = ground(response.parsed_output, passages)
        if checked.violations:
            self.violations.append((chapter_label, checked.violations))
        return checked.families
