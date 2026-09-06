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


def test_the_prompt_tags_every_passage_and_asks_for_tags():
    """A fabricated citation is detectable only because each passage carries a handle the
    model can copy exactly. Asking it to copy the human reference did not work."""
    prompt = build_prompt("Statistics", PASSAGES)
    assert "[P3] EXERCISE 14.1 (section 14.1)" in prompt
    assert "Chapter: Statistics" in prompt
    assert "step-deviation method" in prompt
    assert '"evidence": ["P3", "P7"]' in prompt


def test_a_long_passage_is_truncated_not_dropped():
    """An 8500-character exercise must still reach the model as itself, shortened."""
    long_passage = [("EXERCISE 14.2", "14.2", "frequency table. " * 2000)]
    prompt = build_prompt("Statistics", long_passage)
    assert "[P1] EXERCISE 14.2" in prompt
    assert prompt.rstrip().endswith("in its evidence list.")
    assert len(prompt) < 3200


def test_the_proposer_refuses_to_start_without_a_key_rather_than_degrading_quietly():
    with pytest.raises(ValueError, match="YAADHUM_ANTHROPIC_API_KEY"):
        AnthropicFamilyProposer("")


# --- request options ------------------------------------------------------------------

def test_effort_is_not_sent_to_a_model_that_rejects_it():
    """Haiku 4.5 is the default for both LLM callers because it is the cheapest, and it
    returns 400 if an effort parameter is sent. The keyword is dropped, not sent empty."""
    from app.llm import output_config, supports_effort

    assert supports_effort("claude-haiku-4-5") is False
    assert output_config("claude-haiku-4-5", "low") is None
    assert output_config("claude-opus-5", "low") == {"effort": "low"}
    assert output_config("claude-sonnet-5", "low") == {"effort": "low"}


def test_no_effort_configured_means_no_output_config():
    from app.llm import output_config

    assert output_config("claude-opus-5", None) is None
    assert output_config("claude-opus-5", "") is None


def test_an_unknown_effort_level_fails_loudly_rather_than_at_the_api():
    """A typo in configuration should not become a paid 400 in production."""
    import pytest

    from app.llm import output_config

    with pytest.raises(ValueError, match="unknown effort"):
        output_config("claude-opus-5", "lowest")
    with pytest.raises(ValueError, match="does not accept effort"):
        output_config("claude-opus-4-5", "max")


def test_an_unknown_model_gets_no_effort_rather_than_a_guess():
    """An allowlist, not a denylist: a model we have never heard of works without effort,
    where guessing the other way would break every request to it."""
    from app.llm import output_config

    assert output_config("claude-something-new", "low") is None


# --- what the first real run over Class X Maths actually returned -------------------------
#
# Every one of the hundred-odd families proposed was dropped, because the model cited
# passage TEXT where the prompt wanted the reference label. The reading itself was right --
# it found the three separately-drilled methods for the mean of grouped data, which is the
# exact split the section headings cannot see. These are its real citations, verbatim.

MATHS_PASSAGES = [
    ("Section 5.2", "5.2",
     "A given list of numbers a1, a2, a3, . . . is an AP, if the differences a2 - a1, "
     "a3 - a2, a4 - a3, . . ., give the same value."),
    ("EXERCISE 5.1", "5.1",
     "1. In which of the following situations, does the list of numbers involved make an "
     "arithmetic progression, and why?"),
    ("Example 2", "5.2",
     "Example 2: Which of the following list of numbers form an AP? If they form an AP, "
     "write the next two terms."),
]


def test_a_citation_that_quotes_the_passage_is_accepted():
    """Verbatim from the run: the model quoted the body text of Section 5.2. A quote long
    enough to be found in a passage shown is a stricter proof than a label, not a weaker
    one -- a fabricated quote is not in the corpus at all."""
    result = ground(
        _families(("Identifying arithmetic progressions", [
            "A given list of numbers a1, a2, a3, . . . is an AP, if the differences "
            "a2 - a1, a3 - a2, a4 - a3, . . ., give the same value.",
        ])),
        MATHS_PASSAGES,
    )
    assert result.violations == []
    [family] = result.families
    # Stored as the reference, so the proof points at a real chunk rather than at whatever
    # the model happened to type.
    assert family.evidence == ["Section 5.2"]


def test_a_citation_that_appends_the_question_to_the_label_is_accepted():
    """Also verbatim: it copied 'EXERCISE 5.1' as told, then kept going into the question."""
    result = ground(
        _families(("Recognising APs from situations", [
            "EXERCISE 5.1: Which of the following situations, does the list of numbers "
            "involved make an arithmetic progression, and why?",
        ])),
        MATHS_PASSAGES,
    )
    assert result.violations == []
    assert result.families[0].evidence == ["EXERCISE 5.1"]


def test_the_tag_the_prompt_now_asks_for_is_accepted():
    result = ground(_families(("First term and common difference", ["P2"])), MATHS_PASSAGES)
    assert result.violations == []
    assert result.families[0].evidence == ["EXERCISE 5.1"]


def test_two_citations_resolving_to_one_passage_are_not_stored_twice():
    result = ground(
        _families(("Identifying APs", ["P2", "EXERCISE 5.1"])), MATHS_PASSAGES
    )
    assert result.families[0].evidence == ["EXERCISE 5.1"]


def test_a_fabricated_quote_is_still_rejected():
    """The relaxation must not become 'any text passes'. This sentence is plausible, is
    about the right chapter, and is in no passage that was shown."""
    result = ground(
        _families(("Sum of an infinite AP", [
            "The sum of an infinite arithmetic progression converges when the common "
            "difference is negative and the first term is positive.",
        ])),
        MATHS_PASSAGES,
    )
    assert result.families == []
    assert "cited passages that were not shown" in result.violations[0]


def test_a_quote_too_short_to_prove_anything_is_rejected():
    """'the same value' appears in the corpus, and proves nothing -- two common words are
    in every chapter."""
    result = ground(_families(("Common difference", ["the same"])), MATHS_PASSAGES)
    assert result.families == []
    assert "cited passages that were not shown" in result.violations[0]


def test_a_tag_beyond_the_passages_shown_is_rejected():
    result = ground(_families(("Invented", ["P99"])), MATHS_PASSAGES)
    assert result.families == []


def test_the_correction_message_stays_readable_when_the_citation_is_a_paragraph():
    """The first run produced correction lines thousands of characters long, because each
    dropped citation was a full quoted passage. Unreadable is unusable."""
    result = ground(_families(("Nonsense", ["x" * 4000])), MATHS_PASSAGES)
    assert result.families == []
    assert len(result.violations[0]) < 200
