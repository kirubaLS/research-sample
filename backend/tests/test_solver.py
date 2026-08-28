"""The arithmetic oracle. These are the tests that matter most."""

from __future__ import annotations

from app.mapping.solver import Constraint, QuestionDist, solve


def _dists():
    return [
        QuestionDist("Q4", 1, 1.0, {1.0: 0.94, 0.0: 0.06}),
        QuestionDist("Q12", 2, 1.0, {2.0: 0.88, 1.0: 0.10, 0.0: 0.02}),
        QuestionDist("Q19", 3, 1.0, {3.0: 0.52, 1.0: 0.44, 2.0: 0.03, 0.0: 0.01}),
        QuestionDist("Q26", 3, 1.0, {0.0: 0.91, 1.0: 0.06, 2.0: 0.02, 3.0: 0.01}),
        QuestionDist("Q30", 3, 1.0, {1.0: 0.83, 2.0: 0.15, 0.0: 0.01, 3.0: 0.01}),
    ]


def test_solver_repairs_a_confident_misread():
    """Per-crop the model prefers 3 on Q19; the cover total says 5. Arithmetic wins."""
    dists = _dists()
    naive = {d.question_id: max(d.probs, key=d.probs.get) for d in dists}
    assert sum(naive.values()) == 7.0

    res = solve(dists, [Constraint("cover_total", frozenset(range(5)), 5.0)])
    assert res.feasible
    assert sum(res.assignment.values()) == 5.0
    assert res.assignment["Q19"] == 1.0          # corrected from the naive 3
    assert res.assignment["Q4"] == 1.0           # confident reads untouched
    assert res.assignment["Q26"] == 0.0


def test_nested_section_and_paper_constraints():
    d = [QuestionDist(f"S{i}", 3, 1.0, {0.0: 0.1, 1.0: 0.3, 2.0: 0.3, 3.0: 0.3}) for i in range(4)]
    res = solve(
        d,
        [
            Constraint("secA", frozenset({0, 1}), 4.0),
            Constraint("secB", frozenset({2, 3}), 5.0),
            Constraint("paper", frozenset({0, 1, 2, 3}), 9.0),
        ],
    )
    assert res.feasible
    assert res.assignment["S0"] + res.assignment["S1"] == 4.0
    assert res.assignment["S2"] + res.assignment["S3"] == 5.0


def test_infeasible_is_flagged_not_guessed():
    res = solve(_dists(), [Constraint("cover_total", frozenset(range(5)), 99.0)])
    assert not res.feasible
    assert res.failed_constraint == "cover_total"
    assert not res.assignment


def test_half_marks_lattice():
    d = [
        QuestionDist("A", 2, 0.5, {0.5: 0.4, 1.0: 0.4, 1.5: 0.2}),
        QuestionDist("B", 2, 0.5, {1.5: 0.6, 2.0: 0.4}),
    ]
    res = solve(d, [Constraint("t", frozenset({0, 1}), 3.0)])
    assert res.feasible
    assert sum(res.assignment.values()) == 3.0
    assert all(v * 2 == int(v * 2) for v in res.assignment.values())


def test_likelihood_floor_rejects_an_implausible_reconciliation():
    d = [QuestionDist("A", 3, 1.0, {0.0: 0.98, 3.0: 0.005, 1.0: 0.01, 2.0: 0.005})]
    res = solve(d, [Constraint("t", frozenset({0}), 3.0)], likelihood_floor=-1.0)
    assert not res.feasible
    assert "below floor" in res.detail
