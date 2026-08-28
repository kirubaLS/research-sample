"""The Question Intelligence schema's load-bearing rules, as tests.

Each of these guards a rule whose violation is silent: a wrong number rather than an
error. That is why they are tests and not documentation.
"""

from __future__ import annotations

import pytest

from app.analysis import board_impact, difficulty
from app.taxonomy import judgment, variants

# --- Concept Variant: the guard that makes "improved" mean learning -------------------

def test_reusing_a_variant_blocks_the_paper():
    served = [
        variants.ServedVariant(
            family_id="CF.VOLUME", variant_hash=variants.variant_hash("Cone + Hemisphere r=3.5"),
            assessment_id="a1", assessment_title="Unit Test I", question_no="12",
        )
    ]
    paper = [("21", "CF.VOLUME", variants.variant_hash("Cone + Hemisphere r=3.5"))]

    with pytest.raises(variants.VariantReuseError) as exc:
        variants.enforce(paper, served)
    # the message has to name the question and the earlier paper, or it cannot be fixed
    assert "Q21" in str(exc.value)
    assert "Unit Test I" in str(exc.value)


def test_same_family_different_variant_is_exactly_what_should_pass():
    """The point of the family/variant split: measure the same thing, ask a new question."""
    served = [
        variants.ServedVariant(
            "CF.VOLUME", variants.variant_hash("Cone + Hemisphere r=3.5"),
            "a1", "Unit Test I", "12",
        )
    ]
    paper = [("21", "CF.VOLUME", variants.variant_hash("Cylinder + Hemisphere h=10"))]
    variants.enforce(paper, served)  # must not raise


def test_presentation_differences_do_not_disguise_a_reused_question():
    a = variants.variant_hash("Cone + Hemisphere, r = 3.5 cm")
    b = variants.variant_hash("cone  +  hemisphere;  r = 3.5 cm ")
    assert a == b, "whitespace, case and punctuation must not create a false new variant"


def test_the_numbers_in_a_stem_are_what_make_it_a_new_variant():
    assert variants.variant_hash("r = 3.5 cm") != variants.variant_hash("r = 7 cm")


def test_a_paper_repeating_itself_is_caught_too():
    """Two identical questions inflate that family's weight in the diagnosis silently."""
    h = variants.variant_hash("Cone + Hemisphere")
    with pytest.raises(variants.VariantReuseError):
        variants.enforce([("21", "CF.VOLUME", h), ("24", "CF.VOLUME", h)], [])


# --- Layer 2B: two reviewers, resolved before shipping --------------------------------

def _j(field, value, reviewer, **kw):
    return judgment.Judgment(field=field, value=value, reviewer_id=reviewer, **kw)


def test_one_reviewer_is_not_agreement():
    gate = judgment.gate([
        _j("skill_required", "Spatial reasoning", "r1"),
        _j("complexity", "MULTI_STEP", "r1"),
        _j("dependency_level", "MULTI_CONCEPT", "r1"),
    ])
    assert not gate.shippable
    assert all("second independent read" in b for b in gate.blockers())


def test_the_same_reviewer_twice_is_one_opinion_twice():
    gate = judgment.gate(
        [_j("complexity", "MULTI_STEP", "r1"), _j("complexity", "MULTI_STEP", "r1")],
        required=("complexity",),
    )
    assert not gate.shippable


def test_two_agreeing_reviewers_ship():
    gate = judgment.gate(
        [_j("complexity", "MULTI_STEP", "r1"), _j("complexity", "MULTI_STEP", "r2")],
        required=("complexity",),
    )
    assert gate.shippable
    assert gate.fields["complexity"].value == "MULTI_STEP"


def test_disagreement_blocks_until_resolved():
    disputed = [_j("complexity", "MULTI_STEP", "r1"), _j("complexity", "SINGLE_STEP", "r2")]
    assert not judgment.gate(disputed, required=("complexity",)).shippable

    resolved = judgment.gate(
        [*disputed, _j("complexity", "MULTI_STEP", "r3", is_resolution=True)],
        required=("complexity",),
    )
    assert resolved.shippable
    assert resolved.fields["complexity"].state == "RESOLVED"


def test_kappa_is_none_rather_than_misleading_when_undefined():
    """Everyone answering the same way tells you nothing about whether the field discriminates."""
    assert judgment.cohens_kappa([("A", "A")] * 10) is None
    assert judgment.cohens_kappa([("A", "A")]) is None


def test_kappa_separates_real_agreement_from_chance():
    perfect = judgment.cohens_kappa([("A", "A"), ("B", "B"), ("A", "A"), ("B", "B")])
    assert perfect == pytest.approx(1.0)
    none_at_all = judgment.cohens_kappa([("A", "B"), ("B", "A"), ("A", "B"), ("B", "A")])
    assert none_at_all is not None and none_at_all < 0


# --- Board Impact ----------------------------------------------------------------------

def test_a_question_never_offered_is_not_a_mark_lost():
    """The choice-group rule: an unchosen alternative must not become a penalty."""
    marks = [
        board_impact.QuestionMarks("q1", "U.MENS", 5.0, 3.0),
        board_impact.QuestionMarks("q2", "U.MENS", 5.0, None, state="NOT_OFFERED"),
    ]
    [unit] = board_impact.compute(marks, {"U.MENS": 10.0})
    assert unit.marks_available == 5.0, "only the offered question counts"
    assert unit.marks_lost == 2.0
    assert unit.impact == pytest.approx(0.4 * 10.0)


def test_a_unit_not_tested_is_omitted_not_reported_as_zero():
    """A zero would read as 'no problem here'; nothing was tested, so nothing is known."""
    marks = [board_impact.QuestionMarks("q1", "U.MENS", 5.0, 5.0)]
    units = board_impact.compute(marks, {"U.MENS": 10.0, "U.ALGEBRA": 20.0})
    assert [u.board_unit_id for u in units] == ["U.MENS"]


def test_units_are_ranked_by_impact_not_by_marks_lost():
    """The whole point of weighting: a small loss in a heavy unit outranks a big one in a light unit."""
    marks = [
        board_impact.QuestionMarks("q1", "U.ALGEBRA", 10.0, 8.0),   # lost 2 of 10, weight 20
        board_impact.QuestionMarks("q2", "U.PROB", 10.0, 5.0),      # lost 5 of 10, weight 2
    ]
    units = board_impact.compute(marks, {"U.ALGEBRA": 20.0, "U.PROB": 2.0})
    assert units[0].board_unit_id == "U.ALGEBRA"
    assert units[0].marks_lost < units[1].marks_lost


# --- Difficulty: absent, never estimated ----------------------------------------------

def test_difficulty_is_withheld_during_a_single_school_pilot():
    attempts = [difficulty.Attempt("school-1", 3.0, 5.0) for _ in range(200)]
    result = difficulty.compute("q1", attempts)
    assert not result.available
    assert result.facility is None, "a provisional difficulty is the number everyone quotes"
    assert "one school" in result.unavailable_reason


def test_difficulty_needs_volume_as_well_as_a_second_school():
    attempts = [difficulty.Attempt(f"school-{i % 2}", 3.0, 5.0) for i in range(10)]
    assert not difficulty.compute("q1", attempts).available


def test_difficulty_appears_once_both_thresholds_are_met():
    attempts = [difficulty.Attempt(f"school-{i % 2}", 3.0, 5.0) for i in range(60)]
    result = difficulty.compute("q1", attempts)
    assert result.available
    assert result.facility == pytest.approx(0.6)


# --- Competency Tier: the blueprint is the authority ----------------------------------

def _decision(tier):
    """A TierDecision carrying just what reconciliation reads."""
    from app.taxonomy.tier import TierDecision, TierSignals

    return TierDecision(
        tier=tier, fused={}, conformal_set=[], confidence=0.0,
        signals=TierSignals(structural={}, action={}, familiarity={}, model={}),
    )


def test_the_blueprint_wins_and_the_derivation_becomes_a_cross_check():
    from app.taxonomy.tier import disagreements, reconcile_with_blueprint

    decisions = {"q1": _decision("AP"), "q2": _decision("R&U")}
    rec = reconcile_with_blueprint(decisions, {"q1": "AEC", "q2": "R&U"})
    by_id = {r.question_id: r for r in rec}

    # declared value is stored, in the board's own words
    assert by_id["q1"].tier == "Analysing, Evaluating & Creating"
    assert by_id["q1"].source == "blueprint"
    # and the disagreement is surfaced rather than discarded
    assert by_id["q1"].disagreement
    assert not by_id["q2"].disagreement
    assert [d.question_id for d in disagreements(rec)] == ["q1"]


def test_the_derivation_still_decides_when_nothing_is_declared():
    from app.taxonomy.tier import reconcile_with_blueprint

    rec = reconcile_with_blueprint({"q1": _decision("AP")}, {})
    assert rec[0].source == "derived"
    assert rec[0].tier == "Applying"


def test_an_abstention_stays_an_abstention():
    from app.taxonomy.tier import reconcile_with_blueprint

    rec = reconcile_with_blueprint({"q1": _decision(None)}, {})
    assert rec[0].tier is None
    assert rec[0].source == "abstained"


# --- The conditional-Chapter rule, enforced by the database ---------------------------

def test_a_half_filled_chapter_pair_is_rejected(tmp_path):
    """Chapter without section, or section without chapter, is the force-fitting the rule forbids."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import IntegrityError

    from app.models import Base, Question

    # CHECK constraints are enforced by default; foreign keys are deliberately left off so
    # this exercises the pairing rule alone, without needing a whole taxonomy behind it.
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path}/ck.db")
    Base.metadata.create_all(engine)

    from sqlalchemy.orm import Session

    def make(**kw):
        return Question(
            assessment_id="a1", address="B/21//", question_no="21", max_marks=2,
            board_unit_id="u1", concept_family_id="f1",
            concept_variant="v", variant_hash="h", **kw,
        )

    with Session(engine) as db:
        db.add(make(chapter_id="c1"))            # chapter, no section
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    with Session(engine) as db:
        db.add(make(curriculum_section="12.2"))  # section, no chapter
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    # both filled (content-anchored) and both blank (skill-anchored) are the legal states
    with Session(engine) as db:
        db.add(make(chapter_id="c1", curriculum_section="12.2"))
        db.add(Question(
            assessment_id="a1", address="A/1//", question_no="1", max_marks=1,
            board_unit_id="u-reading", concept_family_id="f-modal-verbs",
            concept_variant="Modal verbs, gap fill 3", variant_hash="h2",
        ))
        db.commit()
        assert db.query(Question).count() == 2

    with Session(engine) as db:
        assert db.execute(text("select count(*) from question")).scalar() == 2
