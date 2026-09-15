"""M11 explicit test #2: passing a concept_family with multiplier 2.0 into the
confidence calculation must leave confidence bands unchanged. board_urgency is
structurally not an input to compute_confidence — this test proves it via the
actual call path (rules.py), not just by inspecting the function signature."""
import inspect

from app.insights.confidence import compute_confidence
from app.insights.flags import compute_flags
from app.insights.rules import complexity_gap_student
from app.insights.model import BoardUrgencyTable, BoardUrgencyRow
from .fixtures import statistics_paper


def test_confidence_function_signature_has_no_board_urgency_parameter():
    sig = inspect.signature(compute_confidence)
    assert "board_urgency" not in sig.parameters
    assert "priority" not in sig.parameters
    assert "multiplier" not in sig.parameters


def test_high_multiplier_does_not_change_confidence_bands():
    paper, questions, stu = statistics_paper()
    flags = compute_flags(questions)

    obj_uncalibrated = complexity_gap_student(paper, flags, stu, "Statistics")

    # Now populate board_urgency with a 2.0 multiplier (4 of 4 years) for the
    # exact concept family this insight is about, and re-run.
    paper.board_urgency.put(BoardUrgencyRow(
        concept_family="Central tendency, mean",
        appearances_last_4_years=4,
        frequency_band="Very high",
    ))
    obj_calibrated = complexity_gap_student(paper, flags, stu, "Statistics")

    assert obj_calibrated.priority.multiplier == 2.0
    assert obj_uncalibrated.priority.multiplier == "NOT_CALIBRATED"

    # Confidence bands must be identical regardless of the multiplier.
    assert obj_calibrated.confidence.observation == obj_uncalibrated.confidence.observation
    assert obj_calibrated.confidence.attribution == obj_uncalibrated.confidence.attribution
