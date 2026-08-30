"""Inferring what a paper covers, and refusing to when the evidence cannot support it.

The argument for inference is that a paper's errors are independent and cancel: a chapter
twelve questions agree on is nearly certain, while one question alone in a chapter is more
likely a misplacement than a topic. Every test here is about the edge of that argument --
the cases where aggregation does not save you, and the system has to decline instead.
"""

from __future__ import annotations

from app.classify.scope import Vote, infer_scope


def _paper(spec: list[tuple[str, int, float, float]]) -> list[Vote]:
    """(chapter, how many questions, marks each, confidence) -> votes."""
    votes = []
    n = 0
    for chapter, count, marks, confidence in spec:
        for _ in range(count):
            n += 1
            votes.append(Vote(f"q{n}", chapter, marks, confidence))
    return votes


def test_a_cyclic_test_reveals_its_own_three_chapters():
    scope = infer_scope(_paper([
        ("Real Numbers", 4, 2.0, 0.90),
        ("Polynomials", 4, 2.0, 0.88),
        ("Triangles", 4, 3.0, 0.91),
    ]))
    assert scope.chapters == {"Real Numbers", "Polynomials", "Triangles"}
    assert scope.confident


def test_one_lonely_question_is_read_as_a_misplacement_not_a_fourth_topic():
    """The whole point. Twelve questions agree on three chapters; the thirteenth does not
    get to invent a fourth."""
    scope = infer_scope(_paper([
        ("Real Numbers", 5, 2.0, 0.92),
        ("Polynomials", 5, 2.0, 0.90),
        ("Triangles", 4, 2.0, 0.89),
        ("Probability", 1, 1.0, 0.71),      # the outlier
    ]))
    assert "Probability" not in scope.chapters
    assert "misplacement" in scope.rejected["Probability"]


def test_a_single_heavy_question_can_stand_as_a_topic():
    """A five-mark question is not an accident, even alone."""
    scope = infer_scope(_paper([
        ("Real Numbers", 8, 1.0, 0.90),
        ("Surface Areas and Volumes", 1, 5.0, 0.93),
    ]))
    assert "Surface Areas and Volumes" in scope.chapters


def test_an_unconfident_vote_cannot_create_a_topic():
    """It can be explained by a scope; it cannot admit one."""
    scope = infer_scope(_paper([
        ("Real Numbers", 8, 2.0, 0.91),
        ("Circles", 3, 2.0, 0.35),
    ]))
    assert "Circles" not in scope.chapters
    assert "no confident question" in scope.rejected["Circles"]


# --- the trap: a second pass entrenching a systematic error -------------------------------

def test_a_short_paper_will_not_have_a_scope_inferred_at_all():
    """A single misplacement IS the consensus on a three-question paper, and the second
    pass would then delete the right chapter -- worse than the misplacement it was fixing.
    This is the case that broke the pipeline test before the guard existed."""
    scope = infer_scope(_paper([("Applications of Trigonometry", 1, 1.0, 0.68)]))
    assert scope.chapters == set()
    assert not scope.confident
    assert "too few to infer" in scope.note


def test_a_scope_that_explains_only_part_of_the_paper_is_not_acted_on():
    """Admitting two chapters while a third of the marks fall outside them means the paper
    has not been understood. Acting on that scope would delete the rest."""
    votes = _paper([
        ("Real Numbers", 6, 2.0, 0.92),
        ("Polynomials", 2, 1.0, 0.88),
    ])
    # a scattering of low-confidence questions worth a lot of the paper
    votes += [Vote(f"x{i}", f"Chapter {i}", 3.0, 0.40) for i in range(4)]
    scope = infer_scope(votes)
    assert not scope.confident, "a partial scope must not be used to filter"


def test_a_systematically_biased_classifier_still_admits_the_right_chapter():
    """The reinforcement risk: if cone questions are consistently read as trigonometry,
    trigonometry looks in scope. It gets in -- there is no defeating a consistent bias from
    the inside -- but the chapters the paper is really about are admitted too, so the
    second pass narrows rather than deletes, and the tally shows a reviewer what happened.
    """
    scope = infer_scope(_paper([
        ("Surface Areas and Volumes", 6, 2.0, 0.88),
        ("Applications of Trigonometry", 3, 2.0, 0.70),   # the systematic error
    ]))
    assert "Surface Areas and Volumes" in scope.chapters
    assert "Applications of Trigonometry" in scope.chapters
    # the tally is what makes the bias visible rather than silent
    assert scope.tally["Applications of Trigonometry"][2] < scope.tally["Surface Areas and Volumes"][2]


def test_nothing_clearing_the_bar_is_reported_rather_than_guessed_at():
    scope = infer_scope([Vote(f"q{i}", f"Chapter {i}", 1.0, 0.30) for i in range(10)])
    assert scope.chapters == set()
    assert not scope.confident
    assert "no chapter cleared the bar" in scope.note


def test_the_tally_covers_every_chapter_that_voted_including_the_rejected():
    """A reviewer confirming a scope needs to see what was left out, not only what got in."""
    scope = infer_scope(_paper([
        ("Real Numbers", 8, 2.0, 0.90),
        ("Probability", 1, 1.0, 0.75),
    ]))
    assert set(scope.tally) == {"Real Numbers", "Probability"}
    assert scope.tally["Probability"][0] == 1
