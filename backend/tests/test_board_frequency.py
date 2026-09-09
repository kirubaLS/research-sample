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


# --- the four decisions the note leaves open ---------------------------------------------

def test_a_board_paper_is_registered_under_its_own_years_syllabus(client, school):
    """The 2024 exam closes 2023-24. Eligibility is read off which version carries a
    family, so a paper filed under the current version would answer the wrong question."""
    r = client.post("/board-papers", headers=_auth(school),
                    json={"subject_code": "X.MATH", "exam_year": 2024,
                          "paper_code": f"30/{uuid.uuid4().hex[:4]}"})
    assert r.status_code == 201
    assert r.json()["curriculum_version"] == "CBSE-2023-24"


def test_a_seeded_older_syllabus_decides_eligibility(client, school, four_board_years):
    """Seed 2022-23 without Volume: 2023 stops counting against it. 3 of 3, tight range
    -> 2.0, where the unseeded reading gave 3 of 4 -> 1.5. Eligibility source is recorded."""
    from app.config import get_settings

    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = "platform-test-key-freq"
    try:
        r = client.post("/platform/books/X.MATH/curriculum?version=CBSE-2022-23",
                        headers={"X-Platform-Key": "platform-test-key-freq"},
                        json={"exclude_families": ["X.MATH.CF.VOLUME"]})
    finally:
        settings.platform_admin_key = before
    assert r.status_code == 201, r.json()
    assert r.json()["excluded_families"] == ["X.MATH.CF.VOLUME"]

    client.post("/board-frequency/recompute?subject_code=X.MATH&window=4", headers=_auth(school))
    table = client.get("/board-frequency?subject_code=X.MATH", headers=_auth(school)).json()
    volume = {row["concept_family"]: row for row in table["families"]}["X.MATH.CF.VOLUME"]
    assert volume["years_eligible"] == 3
    assert volume["years_appeared"] == 3
    assert volume["multiplier"] == 2.0
    assert volume["eligibility"]["2023"] == "curriculum_version"
    assert volume["eligibility"]["2022"] == "appeared"
    # a family on a paper is eligible that year whatever the record says
    irrational = {row["concept_family"]: row for row in table["families"]}["X.MATH.CF.IRRATIONAL"]
    assert irrational["eligibility"]["2023"] == "appeared"


def test_sets_that_disagree_are_flagged_for_a_reviewer(client, school):
    """2019: set 1 carries Volume, set 2 does not. The median decides the marks; the
    disagreement is recorded rather than settled quietly."""
    _board_paper(client, school, 2019, 4, paper_code=f"30/1/{uuid.uuid4().hex[:4]}")
    r = client.post("/board-papers", headers=_auth(school),
                    json={"subject_code": "X.MATH", "exam_year": 2019,
                          "paper_code": f"30/2/{uuid.uuid4().hex[:4]}"})
    other = r.json()["assessment_id"]
    client.post(f"/assessments/{other}/questions", headers=_auth(school), json={"questions": [{
        "section": "A", "question_no": "1", "max_marks": 2, "stem_text": "Prove root 3 irrational",
        "board_unit": "X.MATH.U.NUMBER", "concept_family": "X.MATH.CF.IRRATIONAL",
        "concept_variant": f"irrational 2019 {uuid.uuid4().hex[:6]}",
    }]})
    client.post("/board-frequency/recompute?subject_code=X.MATH&window=10", headers=_auth(school))
    table = client.get("/board-frequency?subject_code=X.MATH", headers=_auth(school)).json()
    volume = {row["concept_family"]: row for row in table["families"]}["X.MATH.CF.VOLUME"]
    assert volume["sets_disagree"]["2019"] == {"with": 1, "without": 1}
    assert any(r["concept_family"] == "X.MATH.CF.VOLUME" for r in table["review"])


def test_basic_maths_never_pools_with_standard(client, school):
    """'30(B)' is the Basic paper. Filed as standard it is refused; filed as basic it
    builds its own table and leaves the standard one alone."""
    code = f"30(B)/{uuid.uuid4().hex[:4]}"
    wrong = client.post("/board-papers", headers=_auth(school),
                        json={"subject_code": "X.MATH", "exam_year": 2018, "paper_code": code})
    assert wrong.status_code == 422
    assert "basic" in wrong.json()["detail"].lower()

    right = client.post("/board-papers", headers=_auth(school),
                        json={"subject_code": "X.MATH", "exam_year": 2018, "paper_code": code,
                              "stream": "basic"})
    assert right.status_code == 201
    aid = right.json()["assessment_id"]
    client.post(f"/assessments/{aid}/questions", headers=_auth(school), json={"questions": [{
        "section": "C", "question_no": "30", "max_marks": 9,
        "stem_text": "A basic volume question", "board_unit": "X.MATH.U.MENSURATION",
        "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"basic {uuid.uuid4().hex[:6]}",
    }]})
    r = client.post("/board-frequency/recompute?subject_code=X.MATH&stream=basic&window=10",
                    headers=_auth(school))
    assert r.status_code == 200 and r.json()["stream"] == "basic"
    basic = client.get("/board-frequency?subject_code=X.MATH&stream=basic", headers=_auth(school)).json()
    standard = client.get("/board-frequency?subject_code=X.MATH", headers=_auth(school)).json()
    b = {row["concept_family"]: row for row in basic["families"]}["X.MATH.CF.VOLUME"]
    s = {row["concept_family"]: row for row in standard["families"]}["X.MATH.CF.VOLUME"]
    assert b["marks_by_year"].get("2018") == 9.0
    assert "2018" not in s["marks_by_year"]


def test_the_square_curve_matches_the_table_at_its_own_points_and_removes_the_cliff():
    from app.analysis.board_frequency import FrequencyConfig, base_multiplier

    square = FrequencyConfig(base_curve="square")
    table = FrequencyConfig()
    assert base_multiplier(4, 4, square) == 2.0 == base_multiplier(4, 4, table)
    assert base_multiplier(2, 4, square) == 1.25 == base_multiplier(2, 4, table)
    assert base_multiplier(3, 4, square) == 1.5625      # the table says 1.5
    # the cliff: 2/5 falls to 1.0 on the table but keeps a real share on the curve
    assert base_multiplier(2, 5, table) == 1.0
    assert base_multiplier(2, 5, square) == 1.16
    assert square.version == "v1-square" and table.version == "v1"


def test_recompute_can_be_asked_for_the_square_curve(client, school, four_board_years):
    r = client.post("/board-frequency/recompute?subject_code=X.MATH&window=4&base=square",
                    headers=_auth(school))
    assert r.status_code == 200
    assert r.json()["config_version"] == "v1-square"


# --- the report card ---------------------------------------------------------------------

def test_the_report_card_puts_the_recurring_topic_first_and_says_why(client, school, four_board_years):
    """A school test where the student lost the same share on Volume (Mensuration, 10%,
    asked 3 of 4 years) and Irrationality (Number Systems, 6%). Volume leads the focus
    list, and the line says how often the board has asked it."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import StudentProfile

    client.post("/board-frequency/recompute?subject_code=X.MATH&window=4", headers=_auth(school))

    tag = uuid.uuid4().hex[:6]
    aid = client.post("/assessments", headers=_auth(school),
                      json={"subject_code": "X.MATH", "title": f"Unit test {tag}", "total_marks": 8}
                      ).json()["assessment_id"]
    qs = []
    for no, fam, unit in (("1", "X.MATH.CF.VOLUME", "X.MATH.U.MENSURATION"),
                          ("2", "X.MATH.CF.VOLUME", "X.MATH.U.MENSURATION"),
                          ("3", "X.MATH.CF.IRRATIONAL", "X.MATH.U.NUMBER"),
                          ("4", "X.MATH.CF.IRRATIONAL", "X.MATH.U.NUMBER")):
        qs.append({"section": "A", "question_no": no, "max_marks": 2, "stem_text": f"q{no} {tag}",
                   "board_unit": unit, "concept_family": fam, "concept_variant": f"{no} {fam} {tag}"})
    assert client.post(f"/assessments/{aid}/questions", headers=_auth(school),
                       json={"questions": qs}).status_code == 200

    db = SessionLocal()
    try:
        student = db.scalar(select(StudentProfile).where(
            StudentProfile.section_id == school["section_id"], StudentProfile.roll_no == f"F{tag}",
        ))
        if student is None:
            student = StudentProfile(school_id=school["school_id"], section_id=school["section_id"],
                                     name="Frequency student", roll_no=f"F{tag}")
            db.add(student)
            db.commit()
        sid = student.id
    finally:
        db.close()

    # half marks on every question: both families fail equally
    r = client.post(f"/assessments/{aid}/answers/{sid}/confirm", headers=_auth(school),
                    json={"answers": [{"address": f"A/{n}//", "marks": 1} for n in "1234"],
                          "by": "teacher"})
    assert r.status_code == 200, r.json()

    body = client.get(f"/reports/student/{sid}", headers=_auth(school),
                      params={"assessment_id": aid}).json()
    focus = body["focus"]
    assert [f["key"] for f in focus][:2] == ["X.MATH.CF.VOLUME", "X.MATH.CF.IRRATIONAL"]
    # the report's numbers are the table's numbers, whatever earlier syllabus records in
    # this session made them (another test records 2022-23, which turns 3/4 into 3/3)
    table = client.get("/board-frequency?subject_code=X.MATH", headers=_auth(school)).json()
    stored = {row["concept_family"]: row for row in table["families"]}["X.MATH.CF.VOLUME"]
    volume = focus[0]["board"]
    assert volume["board_weight_pct"] == 10.0
    assert volume["frequency_multiplier"] == stored["multiplier"] >= 1.5
    assert volume["urgency"] == 10.0 * stored["multiplier"]
    n, of = stored["years_appeared"], stored["years_eligible"]
    assert volume["note"] == (
        f"asked in every one of the last {of} board exams" if n == of
        else f"asked in {n} of the last {of} board exams"
    )
    # the standalone urgency list agrees and is sorted the same way
    assert body["board_urgency"][0]["key"] == "X.MATH.CF.VOLUME"
