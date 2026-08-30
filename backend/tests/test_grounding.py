"""Nothing the model says reaches a report unless the knowledge base can vouch for it.

The report a teacher reads has to be true, and a model's wrong answers look exactly like
its right ones: same tone, same confidence, same shape. So each field is either traceable
to the knowledge base or removed. These tests are the escape routes, one per test.
"""

from __future__ import annotations

from app.classify.grounding import ground, sections_by_chapter
from app.classify.judge import Classification, Evidence

EVIDENCE = [
    Evidence("Surface Areas and Volumes", "Example 3", "12.2", "A cone of radius..."),
    Evidence("Circles", "Theorem 10.1", "10.1", "The tangent at any point..."),
]
SECTIONS = sections_by_chapter([
    ("Surface Areas and Volumes", "12.1"),
    ("Surface Areas and Volumes", "12.2"),
    ("Circles", "10.1"),
])


def _call(**kw) -> Classification:
    base = dict(
        chapter="Surface Areas and Volumes",
        tier="Applying",
        skill_required="mensuration formula",
        reasoning="a cone",
        confidence=0.9,
    )
    base.update(kw)
    return Classification(**base)


def test_a_grounded_answer_passes_through_untouched():
    checked = ground(
        _call(curriculum_section="12.2", evidence=["Example 3"]), EVIDENCE,
        known_sections=SECTIONS,
    )
    assert checked.clean
    assert checked.classification.curriculum_section == "12.2"


# --- the four escape routes -------------------------------------------------------------

def test_an_invented_chapter_is_replaced_and_the_confidence_destroyed():
    checked = ground(_call(chapter="Quantum Mechanics"), EVIDENCE, known_sections=SECTIONS)
    assert checked.classification.chapter in {"Surface Areas and Volumes", "Circles"}
    assert checked.classification.confidence == 0.0
    assert "not among the candidates" in checked.violations[0]


def test_an_invented_section_is_removed_rather_than_reported():
    """'12.9' is a plausible-looking string, and the taxonomy knows the real sections."""
    checked = ground(
        _call(curriculum_section="12.9"), EVIDENCE, known_sections=SECTIONS
    )
    assert checked.classification.curriculum_section is None
    assert "does not exist" in checked.violations[0]


def test_a_section_belonging_to_a_different_chapter_is_removed():
    """10.1 is real, but not in Surface Areas and Volumes."""
    checked = ground(
        _call(curriculum_section="10.1"), EVIDENCE, known_sections=SECTIONS
    )
    assert checked.classification.curriculum_section is None


def test_a_citation_that_was_never_shown_is_dropped():
    """A citation is what makes a placement checkable, so an invented one is worse than
    none: it makes a wrong answer look sourced."""
    checked = ground(
        _call(evidence=["Example 3", "Theorem 99.9"]), EVIDENCE, known_sections=SECTIONS
    )
    assert checked.classification.evidence == ["Example 3"]
    assert "never shown" in checked.violations[0]


def test_a_tier_that_is_not_one_of_the_three_is_removed():
    """A paraphrase of a tier is not a tier. The report reads this field."""
    checked = ground(
        _call(tier="Deep Conceptual Mastery"), EVIDENCE, known_sections=SECTIONS
    )
    assert checked.classification.tier is None
    assert "not one of CBSE's three" in checked.violations[0]


def test_abstaining_on_the_tier_is_allowed():
    """The only honest answer when the evidence does not settle it."""
    checked = ground(_call(tier=None), EVIDENCE, known_sections=SECTIONS)
    assert checked.clean


# --- what happens to a corrected answer ---------------------------------------------------

def test_a_corrected_answer_cannot_keep_a_high_confidence():
    """It was confident about something untrue, so it is not one to act on unattended."""
    checked = ground(
        _call(confidence=0.99, curriculum_section="12.9"), EVIDENCE,
        known_sections=SECTIONS,
    )
    assert checked.classification.confidence <= 0.4


def test_an_unverifiable_section_is_removed_not_assumed_correct():
    """With no section list, the section cannot be checked -- and an unverified value must
    not read as a verified one."""
    checked = ground(_call(curriculum_section="12.2"), EVIDENCE, known_sections=None)
    assert checked.classification.curriculum_section is None
    assert "could not be verified" in checked.violations[0]


def test_several_violations_are_all_reported_not_just_the_first():
    """A reviewer deciding whether to trust the next paper needs the whole picture."""
    checked = ground(
        _call(chapter="Astrology", curriculum_section="99.9", tier="Vibes",
              evidence=["Theorem 404"]),
        EVIDENCE, known_sections=SECTIONS,
    )
    assert len(checked.violations) == 4


def test_judgement_fields_survive_because_a_reviewer_needs_to_see_them():
    """skill_required and reasoning cannot be checked against anything. They are kept for
    a human to read and are never promoted into a report claim."""
    checked = ground(
        _call(skill_required="visual-spatial learning style",
              reasoning="the student appears to be a kinaesthetic learner"),
        EVIDENCE, known_sections=SECTIONS,
    )
    assert checked.clean, "unverifiable is not the same as wrong"
    assert checked.classification.skill_required == "visual-spatial learning style"
