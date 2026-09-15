"""Suggesting a student from a handwritten name -- a hint about a misread roll, never a key."""

from __future__ import annotations

from dataclasses import dataclass

from app.extraction.names import normalise, similarity, suggest


@dataclass
class S:
    id: str
    name: str
    roll_no: str


ROSTER = [S("a", "Aarthi Selvaraj", "1"), S("b", "Abinaya Murugan", "2"),
          S("c", "Karthik Raja", "3"), S("d", "Priya Ramesh", "4"), S("e", "Priya Raman", "5")]


def test_names_are_compared_without_order_case_accents_or_punctuation():
    assert normalise("R. Priya") == ["r", "priya"]
    assert similarity("MURUGAN ABINAYA", "Abinaya Murugan") == 1.0
    assert similarity("Priyá Ramesh", "Priya Ramesh") == 1.0


def test_a_transliteration_variant_or_an_initial_still_fits():
    assert similarity("Kartik Raja", "Karthik Raja") > 0.85
    assert similarity("Karthick Raja", "Karthik Raja") > 0.85
    assert similarity("Raja K", "Karthik Raja") > 0.85


def test_one_clear_fit_is_suggested_with_a_reason_naming_the_roll():
    found = suggest("Abinaya M", ROSTER)
    assert found.student is not None and found.student.id == "b"
    assert "roll 2" in found.reason and "misread" in found.reason


def test_two_priyas_are_offered_not_picked():
    found = suggest("Priya R", ROSTER)
    assert found.student is None
    assert "more than one" in found.reason
    assert {s.id for s, _ in found.candidates} == {"d", "e"}


def test_a_name_that_fits_nobody_suggests_nobody():
    found = suggest("Not On Roster", ROSTER)
    assert found.student is None
    assert "no student" in found.reason


def test_a_blank_name_suggests_nobody():
    assert suggest("", ROSTER).student is None
