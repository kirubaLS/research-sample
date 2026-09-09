"""Board frequency and urgency: the design note's two worked examples, then the route.

The note is explicit that every threshold is a starting proposal. What these tests pin
down is the shape -- frequency as the base, stability as a check on it, a confidence cap
for thin history, a floor of 1.0 that nothing crosses -- and that the numbers it gives
for its own examples come out of the code unchanged.
"""

from __future__ import annotations

import uuid

import pytest

from app.analysis.board_frequency import (
    PaperQuestion,
    YearEvidence,
    marks_by_family,
    marks_for_year,
    multiplier,
    urgency,
)


def _years(*rows: tuple[int, bool, float | None]) -> list[YearEvidence]:
    return [YearEvidence(y, e, m) for y, e, m in rows]


# --- Step 3, worked through exactly as the note does ------------------------------------

def test_the_notes_first_example_volume_of_composite_solids():
    """3 of 4 years, marks 4/3/5 (range 2): base 1.5, tight range, no cap -> 1.5."""
    m = multiplier(_years((2022, True, 4), (2023, True, None), (2024, True, 3), (2025, True, 5)))
    assert m.years_eligible == 4 and m.years_appeared == 3
    assert m.base == 1.5
    assert m.marks_range == 2
    assert m.value == 1.5


def test_the_notes_second_example_a_genuinely_new_topic():
    """2 of 2 eligible years, marks 3/6 (range 3): base 2.0, halved to 1.5, then capped at
    1.5 for having under three years -> 1.5, for a different reason than example one."""
    m = multiplier(_years((2022, False, None), (2023, False, None), (2024, True, 3), (2025, True, 6)))
    assert m.years_eligible == 2 and m.years_appeared == 2
    assert m.base == 2.0
    assert m.value == 1.5
    assert any("low confidence" in a for a in m.adjustments)
    assert any("halfway" in a for a in m.adjustments)


def test_ineligible_years_do_not_count_against_a_family():
    """Dividing by a fixed window would make 2/2 look like 2/4. The note calls this out."""
    new_topic = multiplier(_years((2022, False, None), (2023, False, None), (2024, True, 4), (2025, True, 4)))
    old_topic = multiplier(_years((2022, True, None), (2023, True, None), (2024, True, 4), (2025, True, 4)))
    assert new_topic.base == 2.0      # 2 of 2
    assert old_topic.base == 1.25     # 2 of 4


def test_urgency_is_weight_times_multiplier():
    """The note's closing figure: an 8-mark unit at 1.5 is urgency 12."""
    assert urgency(8, 1.5) == 12.0


# --- the stability check and the floor -------------------------------------------------

def test_a_wide_range_caps_the_multiplier_however_often_it_appears():
    """Every year, but at 2, 9, 3, 8 marks: same frequency, far less trust."""
    m = multiplier(_years((2022, True, 2), (2023, True, 9), (2024, True, 3), (2025, True, 8)))
    assert m.base == 2.0
    assert m.value == 1.25


def test_a_moderate_range_pulls_halfway_back_toward_one():
    m = multiplier(_years((2022, True, 3), (2023, True, 6), (2024, True, 4), (2025, True, 5)))
    assert m.base == 2.0 and m.marks_range == 3
    assert m.value == 1.5


def test_the_multiplier_never_goes_below_one():
    """Rare or absent means 'do not boost', never 'suppress'."""
    never = multiplier(_years((2022, True, None), (2023, True, None), (2024, True, None), (2025, True, None)))
    once = multiplier(_years((2022, True, None), (2023, True, None), (2024, True, None), (2025, True, 2)))
    nothing = multiplier([])
    assert never.value == 1.0 and once.value == 1.0 and nothing.value == 1.0


def test_shares_between_the_notes_rows_fall_to_the_row_they_reach():
    """The note tabulates a 4-year window. With five years 4/5 = 0.8 reaches the 0.75 row
    and 3/5 = 0.6 reaches the 0.5 row -- 'or above', not exact match."""
    four_of_five = multiplier(_years(*[(2021 + i, True, 4.0 if i else None) for i in range(5)]))
    three_of_five = multiplier(_years(*[(2021 + i, True, 4.0 if i > 1 else None) for i in range(5)]))
    assert four_of_five.base == 1.5
    assert three_of_five.base == 1.25


# --- from a paper's questions to a year's marks ---------------------------------------

def test_an_internal_choice_counts_a_family_once_not_twice():
    """'27(a) tests X for 3 OR 27(b) tests X for 3' is 3 marks of X, not 6."""
    marks = marks_by_family([
        PaperQuestion("X", 3, "g1"), PaperQuestion("X", 3, "g1"),
        PaperQuestion("X", 2, None),
    ])
    assert marks == {"X": 5.0}


def test_an_internal_choice_across_two_families_credits_both():
    """'27(a) tests X OR 27(b) tests Y': both families appeared; a student could sit either."""
    marks = marks_by_family([PaperQuestion("X", 3, "g1"), PaperQuestion("Y", 3, "g1")])
    assert marks == {"X": 3.0, "Y": 3.0}


def test_several_sets_of_one_year_give_that_years_median():
    assert marks_for_year([3.0, 5.0, 4.0]) == 4.0
    assert marks_for_year([4.0]) == 4.0


# --- the route, end to end through the API ----------------------------------------------

def _auth(school):
    return {"X-API-Key": school["api_key"]}


def _board_paper(client, school, year: int, marks: float, paper_code: str | None = None) -> str:
    """Register a board paper for ``year`` with one Volume question worth ``marks``.

    Questions go in through the existing /questions route, which is what /map produces
    from a scan; the frequency layer reads the result, not the route that made it.
    """
    r = client.post("/board-papers", headers=_auth(school), json={
        "subject_code": "X.MATH", "exam_year": year, "total_marks": 80,
        "paper_code": paper_code or f"30/{uuid.uuid4().hex[:4]}",
    })
    assert r.status_code == 201, r.json()
    aid = r.json()["assessment_id"]
    added = client.post(f"/assessments/{aid}/questions", headers=_auth(school), json={"questions": [{
        "section": "C", "question_no": "27", "max_marks": marks,
        "stem_text": "A cone is mounted on a hemisphere; find the total volume.",
        "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
        "concept_variant": f"composite volume {year} {uuid.uuid4().hex[:6]}",
    }]})
    assert added.status_code == 200, added.json()
    return aid


@pytest.fixture
def four_board_years(client, school):
    """The note's first example, as real rows: 2022 (4), 2023 absent, 2024 (3), 2025 (5).

    2023 is registered and mapped with a question in a different family, so the year is
    in the window and Volume genuinely did not appear -- rather than the year missing.
    """
    ids = [_board_paper(client, school, 2022, 4), _board_paper(client, school, 2024, 3),
           _board_paper(client, school, 2025, 5)]
    r = client.post("/board-papers", headers=_auth(school), json={
        "subject_code": "X.MATH", "exam_year": 2023, "paper_code": f"30/{uuid.uuid4().hex[:4]}",
    })
    aid = r.json()["assessment_id"]
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import TaxonomyNode

    db = SessionLocal()
    try:
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.REAL"))
        if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.IRRATIONAL")) is None:
            db.add(TaxonomyNode(
                kind="concept_family", code="X.MATH.CF.IRRATIONAL", label="Irrationality Proofs",
                parent_id=chapter.id, path="X.MATH.CF.IRRATIONAL",
            ))
            db.commit()
    finally:
        db.close()
    client.post(f"/assessments/{aid}/questions", headers=_auth(school), json={"questions": [{
        "section": "A", "question_no": "1", "max_marks": 2,
        "stem_text": "Prove that root 5 is irrational",
        "board_unit": "X.MATH.U.NUMBER", "concept_family": "X.MATH.CF.IRRATIONAL",
        "concept_variant": f"irrational 2023 {uuid.uuid4().hex[:6]}",
    }]})
    return ids + [aid]


def test_a_board_paper_needs_a_year(client, school):
    r = client.post("/assessments", headers=_auth(school), json={
        "subject_code": "X.MATH", "title": "no year", "paper_kind": "board",
    })
    assert r.status_code == 422
    assert "exam_year" in r.json()["detail"]


def test_the_same_set_of_the_same_year_is_registered_once(client, school):
    code = f"30/1/{uuid.uuid4().hex[:4]}"
    first = client.post("/board-papers", headers=_auth(school),
                        json={"subject_code": "X.MATH", "exam_year": 2021, "paper_code": code})
    again = client.post("/board-papers", headers=_auth(school),
                        json={"subject_code": "X.MATH", "exam_year": 2021, "paper_code": code})
    assert first.status_code == 201
    assert again.status_code == 409
    assert first.json()["assessment_id"] in again.json()["detail"]


def test_the_table_reproduces_the_notes_example_from_real_rows(client, school, four_board_years):
    r = client.post("/board-frequency/recompute?subject_code=X.MATH&window=4", headers=_auth(school))
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["years"] == [2022, 2023, 2024, 2025]
    assert body["papers_used"] == 4

    table = client.get("/board-frequency?subject_code=X.MATH", headers=_auth(school)).json()
    by_code = {row["concept_family"]: row for row in table["families"]}
    volume = by_code["X.MATH.CF.VOLUME"]
    assert volume["years_eligible"] == 4
    assert volume["years_appeared"] == 3
    assert volume["marks_by_year"] == {"2022": 4.0, "2024": 3.0, "2025": 5.0}
    assert volume["marks_range"] == 2
    assert volume["multiplier"] == 1.5
    # Mensuration is 10% in the seeded curriculum: urgency = 10 x 1.5
    assert volume["board_weight_pct"] == 10.0
    assert volume["urgency"] == 15.0
    # every adjustment is stated, so a principal can follow the number
    assert any("3 of 4" in a for a in volume["adjustments"])

    # a family that never appeared gets a row at the floor, not no row
    assert by_code["X.MATH.CF.IRRATIONAL"]["years_appeared"] == 1
    for row in table["families"]:
        assert row["multiplier"] >= 1.0


def test_recompute_refuses_when_there_is_nothing_to_read(client, school):
    r = client.post("/board-frequency/recompute?subject_code=X.NOSUCH", headers=_auth(school))
    assert r.status_code == 409
    assert "POST /board-papers" in r.json()["detail"]


def test_board_papers_are_listed_with_whether_they_count(client, school, four_board_years):
    r = client.get("/board-papers?subject_code=X.MATH", headers=_auth(school))
    assert r.status_code == 200
    rows = {p["assessment_id"]: p for p in r.json()["papers"]}
    for aid in four_board_years:
        assert rows[aid]["counts_toward_frequency"] is True
        assert rows[aid]["questions_mapped"] == 1


def test_a_board_paper_does_not_trip_the_variant_reuse_guard(client, school):
    """A board paper on file was never served to a class. Registering the same question in a
    school test afterwards is not a reuse, and vice versa."""
    stem = f"Find the volume of a cone of radius 7 {uuid.uuid4().hex[:6]}"
    board = client.post("/board-papers", headers=_auth(school),
                        json={"subject_code": "X.MATH", "exam_year": 2020,
                              "paper_code": f"30/{uuid.uuid4().hex[:4]}"}).json()["assessment_id"]
    q = {"section": "B", "question_no": "5", "max_marks": 2, "stem_text": stem,
         "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
         "concept_variant": stem}
    assert client.post(f"/assessments/{board}/questions", headers=_auth(school),
                       json={"questions": [q]}).status_code == 200
    test = client.post("/assessments", headers=_auth(school),
                       json={"subject_code": "X.MATH", "title": "Unit test", "total_marks": 2}).json()
    r = client.post(f"/assessments/{test['assessment_id']}/questions", headers=_auth(school),
                    json={"questions": [q]})
    assert r.status_code == 200, r.json()
