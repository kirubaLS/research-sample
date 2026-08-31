"""The model proposes; the passages decide what survives."""

from __future__ import annotations

import pytest

from app.curriculum.llm_families import (
    MAX_PER_CHAPTER,
    AnthropicFamilyProposer,
    ChapterFamilies,
    FamilyProposal,
    build_prompt,
    ground,
)

PASSAGES = [
    ("Section 14.1", "14.1", "The mean of grouped data can be found by the direct method."),
    ("Example 2", "14.1", "Find the mean using the assumed mean method."),
    ("EXERCISE 14.1", "14.1", "Q1. Find the mean by the step-deviation method."),
]


def _families(*specs) -> ChapterFamilies:
    return ChapterFamilies(
        families=[
            FamilyProposal(label=label, rationale="because", evidence=list(evidence))
            for label, evidence in specs
        ]
    )


def test_a_fabricated_citation_drops_the_family_rather_than_repairing_it():
    """There is nothing to repair it against: a family whose citations do not exist is not
    a good family with a bad footnote, it is a reading of something we never showed."""
    result = ground(
        _families(
            ("Direct method", ["Section 14.1"]),
            ("Median of grouped data", ["Section 14.3", "Theorem 14.2"]),
        ),
        PASSAGES,
    )
    assert [f.label for f in result.families] == ["Direct method"]
    assert result.violations == [
        "'Median of grouped data' cited passages that were not shown: "
        "Section 14.3, Theorem 14.2"
    ]


def test_a_family_citing_nothing_is_dropped():
    """With no evidence there is no way to tell a reading of the book from a memory."""
    result = ground(_families(("Ogives", [])), PASSAGES)
    assert result.families == []
    assert result.violations == ["'Ogives' cited no passage, so nothing supports it"]


def test_the_split_the_headings_cannot_see_is_allowed_through():
    """The whole reason for paying a model: one heading, three separately drilled methods,
    each citing a passage that really is in the chapter."""
    result = ground(
        _families(
            ("Direct method", ["Section 14.1"]),
            ("Assumed-mean method", ["Example 2"]),
            ("Step-deviation method", ["EXERCISE 14.1"]),
        ),
        PASSAGES,
    )
    assert [f.label for f in result.families] == [
        "Direct method", "Assumed-mean method", "Step-deviation method"
    ]
    assert result.violations == []


def test_two_labels_that_slug_the_same_are_not_proposed_twice():
    """'Mean of Grouped Data' and 'Mean of the grouped data' are one family with two
    spellings, and creating both would split a trend across two rows."""
    result = ground(
        _families(
            ("Mean of Grouped Data", ["Section 14.1"]),
            ("Mean of the grouped data", ["Example 2"]),
        ),
        PASSAGES,
    )
    assert [f.label for f in result.families] == ["Mean of Grouped Data"]
    assert result.violations == [
        "'Mean of the grouped data' duplicates a family already proposed"
    ]


def test_a_chapter_shredded_into_paragraphs_is_capped():
    """NCERT chapters run to eight sections. Fifteen families is a description of
    paragraphs, and every one of them would report insufficient evidence forever."""
    result = ground(
        _families(*[(f"Idea {n}", ["Section 14.1"]) for n in range(20)]), PASSAGES
    )
    assert len(result.families) == MAX_PER_CHAPTER
    assert any("more than that" in v for v in result.violations)


def test_the_prompt_shows_the_reference_the_model_must_copy():
    """A fabricated citation is detectable only because the reference was printed."""
    prompt = build_prompt("Statistics", PASSAGES)
    assert "[EXERCISE 14.1] (section 14.1)" in prompt
    assert "Chapter: Statistics" in prompt
    assert "step-deviation method" in prompt


def test_a_long_passage_is_truncated_not_dropped():
    """An 8500-character exercise must still reach the model as itself, shortened."""
    long_passage = [("EXERCISE 14.2", "14.2", "frequency table. " * 2000)]
    prompt = build_prompt("Statistics", long_passage)
    assert "[EXERCISE 14.2]" in prompt
    assert prompt.rstrip().endswith("Propose the concept families for this chapter.")
    assert len(prompt) < 3000


def test_the_proposer_refuses_to_start_without_a_key_rather_than_degrading_quietly():
    with pytest.raises(ValueError, match="YAADHUM_ANTHROPIC_API_KEY"):
        AnthropicFamilyProposer("")
