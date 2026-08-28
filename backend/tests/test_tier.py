"""The action x familiarity table — the fix for the verb-lexicon trap."""

from __future__ import annotations

from app.taxonomy.familiarity import CorpusEntry, FamiliarityIndex
from app.taxonomy.lexicon import primary_action
from app.taxonomy.tier import (
    CBSE_TIER_TARGET,
    apply_blueprint_tiebreak,
    classify_tier,
    familiarity_level,
)


def _index() -> FamiliarityIndex:
    return FamiliarityIndex(
        [
            CorpusEntry("Theorem 1.3", "Prove that root 5 is irrational", "T",
                        "X.MATH.REAL", canonical=True),
            CorpusEntry("Ex 1.2 Q3", "Prove that 3 + 2 root 5 is irrational", "E", "X.MATH.REAL"),
            CorpusEntry("Example 7", "Two cubes each of edge 12 cm are joined; find the "
                        "surface area of the resulting cuboid", "T", "X.MATH.SAV", canonical=True),
        ]
    )


def test_lexicon_emits_an_action_never_a_tier():
    assert primary_action("Prove that root 5 is an irrational number.") == "PROVE"
    assert primary_action("Find the value of tan 60 degrees.") == "EXECUTE"
    assert primary_action("Justify your answer with reasons.") == "ANALYSE_EVALUATE_CREATE"
    assert primary_action("सिद्ध कीजिए कि 5 एक अपरिमेय संख्या है।") == "PROVE"


def test_the_root_five_trap():
    """'Prove' reads as Applying, but this is Theorem 1.3 in the chapter body: R&U."""
    idx = _index()
    stem = "Prove that root 5 is an irrational number."
    fam = idx.score(stem)
    assert fam.bucket == "T"
    assert familiarity_level(fam) == "T_VERBATIM"

    d = classify_tier(stem, question_type="SA", max_marks=3, familiarity=fam,
                      model_votes={"R&U": 0.6, "AP": 0.4, "AEC": 0.0})
    assert d.tier == "R&U"


def test_the_same_verb_on_a_practised_exercise_is_applying():
    """3 + 2 root 5 is Exercise 1.2 — the student carried the procedure out themselves."""
    idx = _index()
    stem = "Prove that 3 + 2 root 5 is an irrational number."
    fam = idx.score(stem)
    assert fam.bucket == "E"
    assert familiarity_level(fam) == "PRACTISED"

    d = classify_tier(stem, question_type="SA", max_marks=3, familiarity=fam,
                      model_votes={"R&U": 0.3, "AP": 0.7, "AEC": 0.0})
    assert d.tier == "AP"


def test_a_novel_proof_is_aec():
    idx = _index()
    stem = "Prove that a parallelogram circumscribing a circle is a rhombus."
    fam = idx.score(stem)
    assert familiarity_level(fam) == "NOVEL"
    d = classify_tier(stem, question_type="LA", max_marks=5, familiarity=fam,
                      model_votes={"R&U": 0.0, "AP": 0.4, "AEC": 0.6})
    assert d.tier == "AEC"


def test_recall_stays_recall_regardless_of_familiarity():
    idx = _index()
    stem = "Write the formula for the curved surface area of a cone."
    d = classify_tier(stem, question_type="VSA", max_marks=1, familiarity=idx.score(stem),
                      model_votes={"R&U": 0.95, "AP": 0.05, "AEC": 0.0})
    assert d.tier == "R&U"


def test_disagreement_abstains_rather_than_guessing():
    """A stem with no recognisable action verb and a split model vote must not be forced."""
    idx = _index()
    stem = "The value of x in the given figure is:"
    assert primary_action(stem) is None          # nothing for the lexicon to grip
    d = classify_tier(stem, question_type="MCQ", max_marks=1, familiarity=idx.score(stem),
                      model_votes={"R&U": 0.45, "AP": 0.45, "AEC": 0.10},
                      conformal_threshold=0.85)
    assert d.abstained
    assert set(d.conformal_set) == {"R&U", "AP"}


def test_school_override_wins():
    idx = _index()
    stem = "Prove that root 5 is an irrational number."
    d = classify_tier(stem, question_type="SA", max_marks=3, familiarity=idx.score(stem),
                      school_override="AP")
    assert d.tier == "AP" and d.overridden


def test_blueprint_tiebreak_only_moves_abstained_items():
    idx = _index()
    confident = classify_tier("Write the formula for the area of a circle.",
                              question_type="VSA", max_marks=1,
                              familiarity=idx.score("Write the formula for the area of a circle."),
                              model_votes={"R&U": 0.95, "AP": 0.05, "AEC": 0.0})
    ambiguous = "The value of x in the given figure is:"
    abstained = classify_tier(ambiguous, question_type="MCQ", max_marks=1,
                              familiarity=idx.score(ambiguous),
                              model_votes={"R&U": 0.45, "AP": 0.45, "AEC": 0.10},
                              conformal_threshold=0.85)
    assert abstained.abstained
    decisions = {"q1": confident, "q2": abstained}
    marks = {"q1": 1.0, "q2": 1.0}

    adj = apply_blueprint_tiebreak(decisions, marks, declares_blueprint=True)
    assert adj.applied
    assert [qid for qid, _ in adj.moved] == ["q2"]      # the confident item is untouched

    # a school unit test must never be adjusted: the deviation IS the finding
    none_adj = apply_blueprint_tiebreak(decisions, marks, declares_blueprint=False)
    assert not none_adj.applied
    assert "finding" in none_adj.reason


def test_cbse_target_shares_sum_to_one():
    assert abs(sum(CBSE_TIER_TARGET.values()) - 1.0) < 1e-9
