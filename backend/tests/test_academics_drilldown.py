"""Class -> student -> subject drill-down, and the Test tab: every number here traces
back to a real MarkEvent, grouped and filtered differently per screen."""

from __future__ import annotations

import uuid

import pytest


def _auth(school):
    return {"X-API-Key": school["api_key"]}


@pytest.fixture
def drilldown_paper(client, school):
    """One Maths paper, two chapters, two students -- enough to have a "strong" and a
    "weak" chapter for the same student, and a class with one on-track and one
    needs-attention student."""
    tag = uuid.uuid4().hex[:8]
    h = _auth(school)
    aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.MATH", "title": f"Drilldown Test {tag}", "total_marks": 20},
    ).json()["assessment_id"]
    out = client.post(
        f"/assessments/{aid}/questions", headers=h, json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 10, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"dd-{tag}-1",
             "chapter": "X.MATH.SAV", "curriculum_section": "13.1"},
            {"section": "A", "question_no": "2", "max_marks": 10, "board_unit": "X.MATH.U.STATSPROB",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"dd-{tag}-2",
             "chapter": "X.MATH.SAV", "curriculum_section": "13.1"},
        ]},
    )
    assert out.status_code == 200, out.text

    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    strong = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"], name=f"Strong {tag}", roll_no=f"{tag}-1",
    )
    weak = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"], name=f"Weak {tag}", roll_no=f"{tag}-2",
    )
    db.add_all([strong, weak])
    db.commit()
    ids = {"strong": strong.id, "weak": weak.id}
    db.close()

    # strong: 10/10 on Q1 (Mensuration/Volume), 8/10 on Q2 (Statistics/Mean) -- 90% overall
    # weak: 2/10 on Q1, 1/10 on Q2 -- 15% overall, and Q1 (Mensuration) is their weaker chapter
    for key, marks in (("strong", [10, 8]), ("weak", [2, 1])):
        for address, mark in zip(("A/1//", "A/2//"), marks):
            client.patch(
                f"/assessments/{aid}/answers/{ids[key]}/reading/{address}",
                headers=h, json={"marks": mark, "state": "awarded", "by": "test"},
            )
        client.post(f"/assessments/{aid}/answers/{ids[key]}/reading/confirm", headers=h, json={"by": "test"})

    return {"assessment_id": aid, "strong_id": ids["strong"], "weak_id": ids["weak"]}


def test_class_students_lists_status_and_top_improvement_area(client, school, drilldown_paper):
    r = client.get(f"/admin/academics/{school['section_id']}/students", headers=_auth(school))
    assert r.status_code == 200, r.text
    body = r.json()
    by_id = {s["student_id"]: s for s in body["students"]}
    strong = by_id[drilldown_paper["strong_id"]]
    weak = by_id[drilldown_paper["weak_id"]]
    assert strong["status"] == "on_track"
    assert weak["status"] == "requires_review"
    assert weak["top_improvement_area"] is not None
    # the filter options reflect the real subject/test this class has marks on
    assert any(s["subject_code"] == "X.MATH" for s in body["filters"]["subjects"])
    assert any(t["assessment_id"] == drilldown_paper["assessment_id"] for t in body["filters"]["tests"])


def test_class_students_status_filter_narrows_the_list(client, school, drilldown_paper):
    r = client.get(
        f"/admin/academics/{school['section_id']}/students",
        params={"status": "on_track"}, headers=_auth(school),
    )
    assert r.status_code == 200, r.text
    ids = {s["student_id"] for s in r.json()["students"]}
    assert drilldown_paper["strong_id"] in ids
    assert drilldown_paper["weak_id"] not in ids


def test_class_students_rejects_an_unknown_status(client, school, drilldown_paper):
    r = client.get(
        f"/admin/academics/{school['section_id']}/students",
        params={"status": "not-a-real-status"}, headers=_auth(school),
    )
    assert r.status_code == 422


def test_class_students_xlsx_and_pdf_download(client, school, drilldown_paper):
    xlsx = client.get(f"/admin/academics/{school['section_id']}/students.xlsx", headers=_auth(school))
    assert xlsx.status_code == 200
    pdf = client.get(f"/admin/academics/{school['section_id']}/students.pdf", headers=_auth(school))
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"


def test_student_overview_rolls_up_every_subject(client, school, drilldown_paper):
    r = client.get(f"/admin/academics/students/{drilldown_paper['strong_id']}", headers=_auth(school))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overall"]["status"] == "on_track"
    maths = next(s for s in body["subjects"] if s["subject_code"] == "X.MATH")
    assert maths["avg_score_pct"] == 90.0
    assert maths["tests_taken"] == 1


def test_student_subject_breakdown_shows_chapter_and_tier(client, school, drilldown_paper):
    r = client.get(
        f"/admin/academics/students/{drilldown_paper['weak_id']}/subjects/X.MATH", headers=_auth(school),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overall"]["status"] == "requires_review"
    assert isinstance(body["by_chapter"], list)
    assert isinstance(body["by_tier"], list)


def test_student_subject_breakdown_404s_for_a_subject_with_no_marks(client, school, drilldown_paper):
    r = client.get(
        f"/admin/academics/students/{drilldown_paper['weak_id']}/subjects/X.SCI", headers=_auth(school),
    )
    assert r.status_code == 404


def test_student_overview_and_subject_downloads(client, school, drilldown_paper):
    sid = drilldown_paper["strong_id"]
    xlsx = client.get(f"/admin/academics/students/{sid}.xlsx", headers=_auth(school))
    assert xlsx.status_code == 200
    pdf = client.get(f"/admin/academics/students/{sid}.pdf", headers=_auth(school))
    assert pdf.status_code == 200
    subj_pdf = client.get(f"/admin/academics/students/{sid}/subjects/X.MATH.pdf", headers=_auth(school))
    assert subj_pdf.status_code == 200


def test_a_student_in_another_school_is_refused(client, school, drilldown_paper):
    from app.db import SessionLocal
    from app.models import School as SchoolModel, Section, StudentProfile

    db = SessionLocal()
    other = SchoolModel(name="Other School", api_key=f"other-{uuid.uuid4().hex[:8]}", hidden_from_directory=False)
    db.add(other)
    db.flush()
    other_section = Section(school_id=other.id, grade=9, name="Z")
    db.add(other_section)
    db.flush()
    outsider = StudentProfile(school_id=other.id, section_id=other_section.id, name="Outsider", roll_no="1")
    db.add(outsider)
    db.commit()
    outsider_id = outsider.id
    db.close()

    r = client.get(f"/admin/academics/students/{outsider_id}", headers=_auth(school))
    assert r.status_code == 404


def test_tests_tab_lists_papers_with_marks_and_one_tests_own_summary(client, school, drilldown_paper):
    listed = client.get("/admin/academics/tests", headers=_auth(school))
    assert listed.status_code == 200, listed.text
    assert any(t["assessment_id"] == drilldown_paper["assessment_id"] for t in listed.json()["tests"])

    summary = client.get(f"/admin/academics/tests/{drilldown_paper['assessment_id']}", headers=_auth(school))
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["status_counts"]["on_track"] >= 1
    assert body["status_counts"]["requires_review"] >= 1

    xlsx = client.get(f"/admin/academics/tests/{drilldown_paper['assessment_id']}.xlsx", headers=_auth(school))
    assert xlsx.status_code == 200
    pdf = client.get(f"/admin/academics/tests/{drilldown_paper['assessment_id']}.pdf", headers=_auth(school))
    assert pdf.status_code == 200


def test_a_teacher_key_is_refused_every_generic_academics_route(client, school, drilldown_paper):
    created = client.post(
        "/admin/teachers", headers=_auth(school), json={"label": "Ms. Rao", "assignments": []},
    ).json()
    teacher_headers = {"X-API-Key": created["api_key"]}
    assert client.get(
        f"/admin/academics/{school['section_id']}/students", headers=teacher_headers
    ).status_code == 403
    assert client.get(
        f"/admin/academics/students/{drilldown_paper['strong_id']}", headers=teacher_headers
    ).status_code == 403
    assert client.get("/admin/academics/tests", headers=teacher_headers).status_code == 403
