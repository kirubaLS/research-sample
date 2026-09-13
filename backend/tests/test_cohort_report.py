"""The cohort-wide read of one assessment: how the whole class did, not just one student.

Every number here is _rows() (already reading every student's marks on the assessment)
grouped differently -- band counts, a per-section average, marks lost per concept family
-- never an invented cohort figure standing in for one this deployment cannot compute.
"""

from __future__ import annotations

import uuid

import pytest


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@pytest.fixture
def cohort_paper(client, school):
    """Two students, two questions, one concept family -- enough to separate a full-marks
    student from one who lost marks on the same family, and to populate one section bar."""
    tag = uuid.uuid4().hex[:8]
    h = _auth(school)
    aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.MATH", "title": f"Cohort Test {tag}", "total_marks": 10},
    ).json()["assessment_id"]
    out = client.post(
        f"/assessments/{aid}/questions", headers=h, json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 5, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"cohort-{tag}-1"},
            {"section": "A", "question_no": "2", "max_marks": 5, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"cohort-{tag}-2"},
        ]},
    )
    assert out.status_code == 200, out.text

    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    top = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name=f"Full Marks {tag}", roll_no=f"{tag}-1",
    )
    weak = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name=f"Lost Marks {tag}", roll_no=f"{tag}-2",
    )
    db.add_all([top, weak])
    db.commit()
    ids = {"top": top.id, "weak": weak.id}
    db.close()

    for student_key, marks in (("top", [5, 5]), ("weak", [1, 2])):
        for address, mark in zip(("A/1//", "A/2//"), marks):
            r = client.patch(
                f"/assessments/{aid}/answers/{ids[student_key]}/reading/{address}",
                headers=h, json={"marks": mark, "state": "awarded", "by": "test"},
            )
            assert r.status_code == 200, r.text
        confirmed = client.post(
            f"/assessments/{aid}/answers/{ids[student_key]}/reading/confirm",
            headers=h, json={"by": "test"},
        )
        assert confirmed.status_code == 200, confirmed.text

    return aid, ids


def test_cohort_report_bands_and_section_average(client, school, cohort_paper):
    aid, ids = cohort_paper
    r = client.get(f"/reports/cohort/{aid}", headers=_auth(school))
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["students_analysed"] == 2
    # 10/10 = full mastery; 3/10 = below 60.
    assert body["band_counts"]["full_mastery"] == 1
    assert body["band_counts"]["below_60"] == 1
    assert body["band_counts"]["band_80_89"] == 0
    assert body["band_counts"]["band_60_79"] == 0

    assert len(body["section_bars"]) == 1
    bar = body["section_bars"][0]
    assert bar["students"] == 2
    assert bar["pct"] == pytest.approx((100 + 30) / 2, abs=0.1)


def test_cohort_report_marks_lost_per_family(client, school, cohort_paper):
    aid, ids = cohort_paper
    body = client.get(f"/reports/cohort/{aid}", headers=_auth(school)).json()

    assert len(body["top_losses"]) == 1
    loss = body["top_losses"][0]
    assert loss["concept_family"] == "X.MATH.CF.VOLUME"
    # Only the weak student actually lost marks (4 + 3 = 7 lost, over 1 affected student).
    assert loss["students_affected"] == 1
    assert loss["avg_marks_lost"] == pytest.approx(7.0)
    # Fewer than 2 affected students is this module's own evidence floor.
    assert loss["confidence"] == "EMERGING"


def test_cohort_report_refuses_an_assessment_with_no_marks(client, school):
    aid = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Empty cohort test", "total_marks": 10},
    ).json()["assessment_id"]
    r = client.get(f"/reports/cohort/{aid}", headers=_auth(school))
    assert r.status_code == 404
