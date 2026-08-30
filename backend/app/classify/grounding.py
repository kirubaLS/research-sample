"""Every field the model returns, checked against the knowledge base that produced it.

The report a teacher reads must be true. A model asked to classify a question will answer
even when it should not, and its wrong answers look exactly like its right ones -- same
tone, same confidence, same shape. So nothing it says is taken on trust: each field is
either traceable to something in the knowledge base, or it is removed.

Four things it could otherwise invent, none of which anything downstream would catch:

* **A chapter** that was never among the retrieved candidates.
* **A curriculum section** -- "12.2" is a plausible-looking string, and the taxonomy holds
  the real sections for every chapter, so an invented one is checkable and must be checked.
* **An evidence reference** -- citing "Theorem 99.9" makes a wrong placement look sourced.
* **A tier** outside CBSE's three, or a paraphrase of one of them.

What cannot be checked this way is judgement: `skill_required` and `reasoning` are the
model's own words, and no lookup can verify them. They are kept, because a reviewer needs
to see what the model thought, and they are marked as unverified so nothing downstream can
promote them into a claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.classify.judge import TIERS, Classification, Evidence

#: fields no lookup can verify. Shown to a reviewer, never stated as fact in a report.
JUDGEMENT_FIELDS = ("skill_required", "reasoning")


@dataclass
class Grounded:
    classification: Classification
    #: what was removed, and why -- so a silent correction is never silent
    violations: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.violations


def ground(
    result: Classification,
    evidence: list[Evidence],
    *,
    known_sections: dict[str, set[str]] | None = None,
) -> Grounded:
    """Strip anything the knowledge base cannot vouch for.

    ``known_sections`` maps a chapter name to the NCERT section numbers that actually exist
    for it, from the taxonomy the book ingest built. Omitted, section verification is
    skipped and that is recorded -- an unverified section must not read as a verified one.
    """
    violations: list[str] = []
    update: dict = {}

    # --- the chapter must be one that was actually offered ---
    allowed = {e.chapter for e in evidence}
    if result.chapter not in allowed:
        violations.append(
            f"chapter {result.chapter!r} was not among the candidates {sorted(allowed)}"
        )
        update["chapter"] = min(allowed, key=lambda c: c.lower()) if allowed else ""
        update["confidence"] = 0.0

    chapter = update.get("chapter", result.chapter)

    # --- the tier must be one of the board's three, exactly ---
    # None is not a violation: abstaining is the honest answer when the evidence does not
    # settle it, and treating it as a fault would push the model towards guessing.
    if result.tier is not None and result.tier not in TIERS:
        violations.append(
            f"tier {result.tier!r} is not one of CBSE's three; a paraphrase is not a tier"
        )
        update["tier"] = None

    # --- the section must exist in the taxonomy for that chapter ---
    if result.curriculum_section:
        if known_sections is None:
            violations.append(
                "curriculum section could not be verified: no section list was supplied"
            )
            update["curriculum_section"] = None
        elif result.curriculum_section not in known_sections.get(chapter, set()):
            violations.append(
                f"section {result.curriculum_section!r} does not exist in {chapter!r}"
            )
            update["curriculum_section"] = None

    # --- every citation must be a passage the model was actually shown ---
    shown = {e.reference for e in evidence}
    if result.evidence:
        invented = [ref for ref in result.evidence if ref not in shown]
        if invented:
            violations.append(
                f"cited passages that were never shown: {invented}. A citation is what "
                f"makes a placement checkable, so an invented one is worse than none."
            )
            update["evidence"] = [ref for ref in result.evidence if ref in shown]

    # A placement that had to be corrected is not one to act on unattended, whatever the
    # model's own confidence was -- it was confident about something untrue.
    if violations and "confidence" not in update:
        update["confidence"] = min(result.confidence, 0.4)

    return Grounded(
        classification=result.model_copy(update=update) if update else result,
        violations=violations,
    )


def sections_by_chapter(rows: list[tuple[str, str]]) -> dict[str, set[str]]:
    """(chapter name, section number) pairs -> the lookup ``ground`` expects."""
    out: dict[str, set[str]] = {}
    for chapter, section in rows:
        out.setdefault(chapter, set()).add(section)
    return out
