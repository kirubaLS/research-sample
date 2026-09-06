"""The seven-layer script pipeline.

The claim these layers exist to support is that the system is more accurate than any of
its parts, and the mechanism is L6: a crop the recogniser read wrongly is repaired by the
teacher's own totals. That is the test that matters here, and it runs without a model.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.mapping.association import Anchor
from app.mapping.solver import Constraint
from app.scanning import read_script
from app.scanning.adjudicate import adjudicate
from app.scanning.recognise import abstains, clamp, flat
from app.vision.localise import (
    Component,
    components,
    find_mark_candidates,
    find_total_candidates,
    looks_like_a_numeral,
)

# --- L3: localisation ------------------------------------------------------------------

def _page(shapes: list[tuple[int, int, np.ndarray]], size=(400, 300)) -> np.ndarray:
    mask = np.zeros(size, dtype=bool)
    for top, left, block in shapes:
        mask[top:top + block.shape[0], left:left + block.shape[1]] |= block
    return mask


def _digit(h=14, w=9) -> np.ndarray:
    """A solid-ish blob: what a handwritten numeral looks like to a shape filter."""
    block = np.ones((h, w), dtype=bool)
    block[2:-2, 2:-2] = True
    return block


def _tick(size=16) -> np.ndarray:
    """Two thin diagonal strokes across a big box -- fills very little of it."""
    block = np.zeros((size, size), dtype=bool)
    for i in range(size // 2):
        block[size // 2 + i, i] = True
    for i in range(size):
        block[size - 1 - i, i] = True
    return block


def _strike(h=3, w=40) -> np.ndarray:
    return np.ones((h, w), dtype=bool)


def test_connected_components_use_eight_connectivity():
    """A handwritten digit routinely joins only at a diagonal. Four-connectivity splits it
    into pieces that are each too small to survive the area filter."""
    mask = np.zeros((10, 10), dtype=bool)
    mask[2, 2] = mask[3, 3] = True          # touching only at a corner
    assert len(components(mask)) == 1


def test_a_tick_and_a_strike_are_not_numerals():
    """They are in the same red ink and outnumber the marks. A recogniser forced to read a
    tick as a digit will return one, so they must be removed before it is asked."""
    [tick] = components(_page([(20, 20, _tick())]))
    [strike] = components(_page([(20, 20, _strike())]))
    [digit] = components(_page([(20, 20, _digit())]))

    assert not looks_like_a_numeral(tick), f"extent {tick.extent:.2f}"
    assert not looks_like_a_numeral(strike), f"aspect {strike.aspect:.2f}"
    assert looks_like_a_numeral(digit)


def test_mark_candidates_are_found_and_furniture_is_not():
    mask = _page([(30, 40, _digit()), (60, 40, _tick()), (90, 20, _strike()), (120, 200, _digit())])
    found = find_mark_candidates(mask, page=1)
    assert len(found) == 2
    assert all(c.value is None and c.confidence == 0.0 for c in found), "L3 must not read"


def test_a_total_is_kept_apart_from_the_marks():
    """A total is not a mark for any question. Letting one into the assignment would steal
    a binding AND corrupt the sum L6 checks the rest against."""
    mask = _page([(30, 40, _digit()), (370, 250, _digit())])   # one high, one at the foot
    totals = find_total_candidates(mask, page=1)
    assert [t.candidate_id for t in totals] == ["p1-t0"]


def test_component_shape_statistics():
    c = Component(label=1, x=5, y=5, x0=0, y0=0, x1=10, y1=20, area=100)
    assert c.width == 10 and c.height == 20
    assert c.aspect == 0.5
    assert c.extent == 0.5


# --- L4: recognition contract ----------------------------------------------------------

def test_an_illegal_value_does_not_reach_the_solver():
    """A recogniser asked for a mark out of 3 can still answer 5. Passing that through puts
    an impossible value into the assignment; dropping it silently leaves the question with
    no distribution at all."""
    assert clamp({5.0: 0.9}, [0.0, 1.0, 2.0, 3.0]) == flat([0.0, 1.0, 2.0, 3.0])
    assert clamp({2.0: 0.8, 5.0: 0.2}, [0.0, 1.0, 2.0, 3.0]) == {2.0: 0.8}


# --- L7: adjudication ------------------------------------------------------------------

def test_an_unreconcilable_script_is_flagged_whole_not_queued_mark_by_mark():
    """Sending a reviewer to check twenty digits when the fault is a missing page wastes
    the one human pass the design budgets for."""
    out = adjudicate(
        {"1": 2.0, "2": 3.0}, {"1": 0.99, "2": 0.99},
        threshold=0.97, feasible=False, infeasible_reason="grand total not reachable",
    )
    assert out.flagged and out.review_load == 0
    assert all(f.route == "flagged" for f in out.facts)


def test_only_what_clears_the_threshold_is_accepted():
    out = adjudicate(
        {"1": 2.0, "2": 3.0}, {"1": 0.99, "2": 0.40},
        threshold=0.97, feasible=True,
    )
    assert [f.address for f in out.accepted] == ["1"]
    assert [f.address for f in out.queued] == ["2"]
    assert "below 0.97" in out.queued[0].reason


# --- L2 to L7 end to end ---------------------------------------------------------------

class _Recognizer:
    """A recogniser that is confidently wrong about one crop, as real ones are.

    1 and 3 are the classic confusion on an Indian script, which is why the solver carries
    a confusable prior at all.
    """

    def __init__(self, wrong_about: str | None = None):
        self.wrong_about = wrong_about
        self.calls: list[list[float]] = []

    def predict(self, crop, legal_values):
        self.calls.append(legal_values)
        if crop == self.wrong_about:
            return {3.0: 0.80, 1.0: 0.20}
        return {legal_values[-1]: 0.95}


def _red_page(marks: list[tuple[int, int]]) -> np.ndarray:
    """A white page with red blobs where the teacher wrote."""
    page = np.full((400, 300, 3), 245, dtype=np.uint8)
    for top, left in marks:
        page[top:top + 14, left:left + 9] = (200, 30, 30)
    return page


def test_the_totals_repair_a_confident_misread():
    """The claim the whole design rests on. The recogniser prefers 3 for question 2 at 80%
    confidence. The teacher's grand total says the script is worth 4. Only 3 + 1 reaches 4,
    so L6 overrules the crop -- and the accuracy of the system exceeds the accuracy of its
    recogniser."""
    anchors = [
        Anchor(address="1", page=1, x=40.0, y=36.0, max_marks=3.0, step=1.0),
        Anchor(address="2", page=1, x=40.0, y=96.0, max_marks=3.0, step=1.0),
    ]
    recognizer = _Recognizer(wrong_about="p1-m1")

    out = read_script(
        [_red_page([(30, 40), (90, 40)])],
        anchors,
        recognizer,
        constraints=[Constraint(name="grand", indices=frozenset({0, 1}), total=4.0)],
        crops={"p1-m0": "p1-m0", "p1-m1": "p1-m1"},
    )

    assert out.solution is not None and out.solution.feasible, out.solution
    assert sum(out.solution.assignment.values()) == 4.0
    assert out.solution.assignment["2"] == 1.0, "the total must overrule the crop"


def test_recognition_is_asked_only_for_values_the_question_allows():
    """Asking for a mark out of 3 and accepting a 7 is how an impossible script is built."""
    anchors = [Anchor(address="1", page=1, x=40.0, y=36.0, max_marks=2.0, step=1.0)]
    recognizer = _Recognizer()
    read_script([_red_page([(30, 40)])], anchors, recognizer)
    assert recognizer.calls, "the recogniser was never asked"
    assert all(values == [0.0, 1.0, 2.0] for values in recognizer.calls)


def test_a_script_with_no_totals_still_reads_and_says_so():
    """Most cyclic tests carry no page total. Reconciliation then has nothing to check
    against, which is a weaker result -- not a refusal."""
    anchors = [Anchor(address="1", page=1, x=40.0, y=36.0, max_marks=2.0, step=1.0)]
    out = read_script([_red_page([(30, 40)])], anchors, _Recognizer())
    assert out.solution is not None and out.solution.feasible
    assert out.adjudication is not None and not out.adjudication.flagged


def test_a_blank_page_produces_no_candidates_and_says_so():
    anchors = [Anchor(address="1", page=1, x=40.0, y=36.0, max_marks=2.0, step=1.0)]
    out = read_script([np.full((400, 300, 3), 245, dtype=np.uint8)], anchors, _Recognizer())
    assert any("no mark candidates" in n for n in out.notes)


@pytest.mark.parametrize("threshold", [0.5, 0.97])
def test_the_review_queue_grows_as_the_threshold_rises(threshold):
    anchors = [Anchor(address="1", page=1, x=40.0, y=36.0, max_marks=2.0, step=1.0)]
    out = read_script([_red_page([(30, 40)])], anchors, _Recognizer(), threshold=threshold)
    assert out.adjudication is not None
    assert out.adjudication.review_load in (0, 1)


# --- never assert a digit nobody could read --------------------------------------------

def test_a_coin_toss_between_two_digits_is_not_a_reading():
    """0.50 for 3 against 0.48 for 1 is not a reading of a 3. A recogniser asked for a
    digit will always name one -- the question forces it -- so the refusal cannot live
    inside the model."""
    from app.scanning.recognise import abstains

    assert abstains({3.0: 0.50, 1.0: 0.48})
    assert abstains({3.0: 0.40, 1.0: 0.30, 2.0: 0.30})   # best below the floor
    assert not abstains({3.0: 0.90, 1.0: 0.10})


def test_an_unreadable_crop_carries_no_value_and_is_not_guessed():
    """The abstention has to reach the pipeline, not just exist as a helper."""
    anchors = [Anchor(address="1", page=1, x=40.0, y=36.0, max_marks=3.0, step=1.0)]

    class Unsure:
        def predict(self, crop, legal_values):
            return {3.0: 0.34, 1.0: 0.33, 2.0: 0.33}

    out = read_script([_red_page([(30, 40)])], anchors, Unsure())
    assert all(c.value is None for c in out.candidates), "a guess reached the assignment"
    assert any("too uncertain to read" in n for n in out.notes)


def test_the_totals_can_still_pin_a_mark_nobody_could_read():
    """An abstention is not a loss. The crop was unreadable and the answer is still exact,
    because the teacher's total leaves only one possibility."""
    anchors = [
        Anchor(address="1", page=1, x=40.0, y=36.0, max_marks=2.0, step=1.0),
        Anchor(address="2", page=1, x=40.0, y=96.0, max_marks=2.0, step=1.0),
    ]

    class OneUnreadable:
        def predict(self, crop, legal_values):
            if crop == "p1-m1":
                return {0.0: 0.34, 1.0: 0.33, 2.0: 0.33}      # abstains
            return {2.0: 0.97, 1.0: 0.03}

    out = read_script(
        [_red_page([(30, 40), (90, 40)])], anchors, OneUnreadable(),
        constraints=[Constraint(name="grand", indices=frozenset({0, 1}), total=3.0)],
        crops={"p1-m0": "p1-m0", "p1-m1": "p1-m1"},
    )
    assert out.solution is not None and out.solution.feasible
    assert out.solution.assignment == {"1": 2.0, "2": 1.0}


def test_two_recognisers_that_disagree_assert_nothing():
    """The failure mode of one model is systematic: it will be confidently wrong about the
    same badly-formed 1 every time, and asking it twice does not help. Averaging the two
    would manufacture a distribution moderately sure of something, which is the one thing
    this must never produce."""
    from app.scanning.recognise import Ensemble

    class Says3:
        def predict(self, crop, legal_values):
            return {3.0: 0.85, 1.0: 0.15}

    class Says1:
        def predict(self, crop, legal_values):
            return {1.0: 0.85, 3.0: 0.15}

    legal = [0.0, 1.0, 2.0, 3.0]
    disagreeing = Ensemble(Says3(), Says1()).predict(None, legal)
    assert abstains(disagreeing), disagreeing

    agreeing = Ensemble(Says3(), Says3()).predict(None, legal)
    assert not abstains(agreeing)
    assert max(agreeing, key=lambda v: agreeing[v]) == 3.0
