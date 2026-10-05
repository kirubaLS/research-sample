from scripts.tune_gate import recommend, sweep


def _curve(n_good, n_bad, margin):
    return [[margin, True, True]] * n_good + [[margin, True, False]] * n_bad


def test_the_sweep_counts_only_questions_both_retrievers_agreed_on():
    rows = sweep([[0.5, True, True], [0.5, False, True], [0.1, True, False]], margins=(0.0, 0.3))
    assert rows[0]["settled"] == 2 and rows[0]["agreed"] == 1
    assert rows[1]["settled"] == 1 and rows[1]["agreement"] == 1.0


def test_the_recommendation_is_the_loosest_margin_that_clears_the_bar():
    curve = _curve(100, 0, 0.6) + _curve(60, 40, 0.1)     # a low margin is where it errs
    rows = sweep(curve, margins=(0.0, 0.3, 0.6))
    assert recommend(rows, 0.98)["margin"] == 0.6 or recommend(rows, 0.98)["margin"] == 0.3
    assert recommend(rows, 0.98)["settled"] == 100


def test_no_recommendation_without_enough_questions_or_agreement():
    assert recommend(sweep(_curve(10, 0, 0.6)), 0.98) is None
    assert recommend(sweep(_curve(50, 50, 0.6)), 0.98) is None
