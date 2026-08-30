from __future__ import annotations

from app.analysis.diagnostics import (
    MarkRow,
    board_weighted_indicator,
    by_tier,
    skill_by_tier,
    wilson_interval,
)
from app.analysis.paper_quality import cronbach_alpha, item_analysis, typology_alignment

#: board unit and concept family, kept short so the fixtures stay readable
MENS, VOL = "U.MENSURATION", "CF.VOLUME"


def _rows(student: str = "s1") -> list[MarkRow]:
    return [
        MarkRow(student, "A/4//", 1, 1, "awarded", ("cone",), "R&U", "SAV", MENS, VOL),
        MarkRow(student, "A/12//", 2, 2, "awarded", ("cylinder",), "R&U", "SAV", MENS, VOL),
        MarkRow(student, "A/19//", 1, 3, "awarded", ("composite",), "AP", "SAV", MENS, VOL),
        MarkRow(student, "A/26//", 0, 3, "awarded", ("composite",), "AP", "SAV", MENS, VOL),
        MarkRow(student, "A/30//", 1, 3, "awarded", ("composite",), "AP", "SAV", MENS, VOL),
        MarkRow(student, "A/31//a", 0, 5, "not_offered", ("stats",), "AP", "STATS", "U.STATSPROB", "CF.MEAN"),
    ]


def test_not_offered_is_excluded_from_every_denominator():
    """The unattempted half of a choice pair is absence of evidence, not weakness."""
    findings = {f.key: f for f in by_tier(_rows())}
    assert findings["AP"].available == 9.0      # 3 + 3 + 3, NOT 14 — the 5-mark alt is excluded
    assert findings["R&U"].rate == 1.0


def test_evidence_floor_suppresses_a_number_it_cannot_support():
    thin = [MarkRow("s1", "A/1//", 0, 1, "awarded", ("cone",), "R&U", "SAV", MENS, VOL)]
    f = by_tier(thin)[0]
    assert not f.sufficient and f.rate is None
    assert "Insufficient evidence" in f.message


def test_the_crosstab_is_the_diagnosis():
    findings = {f.key: f for f in skill_by_tier(_rows())}
    assert "composite|AP" in findings
    assert findings["composite|AP"].rate is not None
    assert findings["composite|AP"].rate < 0.3     # weak on application of composite solids


def test_a_board_unit_with_no_marks_is_a_coverage_gap_not_a_zero():
    _, gaps = board_weighted_indicator(
        _rows(), {"U.MENSURATION": 10.0, "U.TRIG": 12.0}
    )
    assert [g.board_unit for g in gaps] == ["U.TRIG"]
    assert "no information" in gaps[0].message


def test_indicator_carries_an_interval_and_a_share():
    indicators, _ = board_weighted_indicator(_rows(), {"U.MENSURATION": 10.0})
    row = indicators[0]
    assert row["indicator_ci"][0] < row["indicator"] < row["indicator_ci"][1]
    assert abs(row["share"] - 1.0) < 1e-9


def test_wilson_is_sane_at_tiny_denominators():
    lo, hi = wilson_interval(0, 1)
    assert lo == 0.0 and 0.5 < hi < 1.0       # 0 of 1 is weak evidence, not 0% mastery


def test_item_analysis_flags_a_broken_item():
    """Five items track ability; one is mis-keyed so the strong students get it wrong."""
    scores = {}
    for i in range(1, 21):
        able = i > 10
        row = {f"q{j}": (1.0 if able else 0.0) for j in range(5)}
        row["broken"] = 0.0 if able else 1.0
        scores[f"s{i}"] = row
    maxes = {f"q{j}": 1.0 for j in range(5)} | {"broken": 1.0}
    stats = {s.address: s for s in item_analysis(scores, maxes)}
    assert stats["broken"].flag == "negative_discrimination"
    assert stats["broken"].discrimination < 0
    assert stats["q0"].discrimination > 0.5


def test_cronbach_alpha_is_high_on_a_coherent_test():
    scores = {f"s{i}": {f"q{j}": float(min(i % 5, 3)) for j in range(6)} for i in range(1, 25)}
    assert (cronbach_alpha(scores, [f"q{j}" for j in range(6)]) or 0) > 0.9


def test_typology_alignment_reports_a_recall_heavy_paper():
    rep = typology_alignment({"R&U": 57, "AP": 15, "AEC": 8})
    assert rep.alignment_score < 0.85
    assert "R&U-heavy" in rep.verdict and "AEC under-represented" in rep.verdict


def test_typology_alignment_passes_a_balanced_paper():
    rep = typology_alignment({"R&U": 43.2, "AP": 19.2, "AEC": 17.6})
    assert rep.alignment_score > 0.95
    assert "well aligned" in rep.verdict


def test_strengths_rank_on_the_interval_not_the_point_estimate():
    """2/2 on one question is not stronger evidence than 11/12, and must not outrank it."""
    from app.analysis.diagnostics import MarkRow, by_concept_family, select_strengths

    rows = [
        MarkRow("s", "1", 2.0, 2.0, concept_family="TINY"),
        MarkRow("s", "2", 2.0, 2.0, concept_family="TINY"),
        *[MarkRow("s", f"{i}", 1.0, 1.0, concept_family="SOLID") for i in range(3, 14)],
        MarkRow("s", "14", 0.0, 1.0, concept_family="SOLID"),
        *[MarkRow("s", f"{i}", 1.0, 4.0, concept_family="WEAK") for i in range(15, 19)],
    ]
    strengths = [f.key for f in select_strengths(by_concept_family(rows))]
    assert strengths == ["SOLID", "TINY"]
    assert "WEAK" not in strengths


def test_proof_distinguishes_a_confirmed_placement_from_a_guessed_one():
    """Same chapter label, very different standing -- the report must not hide that."""
    from types import SimpleNamespace as NS

    from app.api.reports import _proof

    q = NS(question_no="17", section="C", sub_part=None, choice_alt=None,
           question_type="LA", stem_text="A cone surmounted on a hemisphere...",
           logical_page=3, curriculum_section="12.2",
           curriculum_section_title="Volume of a Combination of Solids",
           concept_variant="cone on hemisphere r=3.5", chapter_id="ch-sav",
           verified_against="NCERT Reprint 2026-27", verified_at="2026-08-30")
    ev = NS(source="scan")
    codes = {"ch-sav": "X.MATH.SAV"}

    guessed = _proof(q, NS(source="model", confidence=0.41, needs_review=True,
                           reviewed_by=None, reasoning="closest match",
                           evidence=["Example 4"], candidates=["X.MATH.SAV", "X.MATH.AOT"],
                           chapter_id="ch-sav"), ev, codes)
    confirmed = _proof(q, NS(source="human", confidence=1.0, needs_review=False,
                             reviewed_by="teacher-7", reasoning=None,
                             evidence=["Example 4"], candidates=[],
                             chapter_id="ch-sav"), ev, codes)

    assert guessed["placement"]["chapter"] == confirmed["placement"]["chapter"]
    assert guessed["placement"]["needs_review"] is True
    assert guessed["placement"]["candidates"] == ["X.MATH.SAV", "X.MATH.AOT"]
    assert confirmed["placement"]["reviewed_by"] == "teacher-7"
    # The book passage the decision rested on travels with the finding, both times.
    assert guessed["placement"]["book_evidence"] == ["Example 4"]
