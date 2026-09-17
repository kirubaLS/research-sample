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


def test_class_students_top_filter_keeps_only_the_highest_scorers(client, school, drilldown_paper):
    # Scoped to this one assessment too: `school`'s section is a session-scoped fixture
    # shared by every test file, so ranking "top scorers" across the *whole* class would
    # be comparing this test's two students against however many other tests have added
    # to the same section by the time this runs. Narrowing to this paper keeps every
    # other test file's students out of the running (no marks here -> not_assessed ->
    # excluded from ranking), the same way a principal narrows to one test on screen.
    r = client.get(
        f"/admin/academics/{school['section_id']}/students",
        params={"top": 1, "assessment_id": drilldown_paper["assessment_id"]}, headers=_auth(school),
    )
    assert r.status_code == 200, r.text
    ids = [s["student_id"] for s in r.json()["students"]]
    assert ids == [drilldown_paper["strong_id"]]


def test_class_students_top_filter_is_reflected_in_the_downloads_too(client, school, drilldown_paper):
    """The whole point of a server-side `top` filter: the screen and its Excel/PDF
    downloads can never disagree about which students "top scorers" means, unlike a
    client-side-only slice that the download request never knew about."""
    xlsx = client.get(
        f"/admin/academics/{school['section_id']}/students.xlsx",
        params={"top": 1, "assessment_id": drilldown_paper["assessment_id"]}, headers=_auth(school),
    )
    assert xlsx.status_code == 200
    from openpyxl import load_workbook
    import io

    wb = load_workbook(io.BytesIO(xlsx.content))
    ws = wb.active
    # header row + exactly one data row (the top scorer only)
    assert ws.max_row == 2


def test_class_students_rejects_a_non_positive_top(client, school, drilldown_paper):
    r = client.get(
        f"/admin/academics/{school['section_id']}/students",
        params={"top": 0}, headers=_auth(school),
    )
    assert r.status_code == 422


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


def test_student_overview_subject_filter_narrows_the_table_but_not_the_overall_tile(
    client, school, drilldown_paper,
):
    """A subject filter on the student page narrows which subject rows the table (and
    its download) lists -- it must never change what "overall" means, since that tile
    is not the thing the dropdown claims to filter."""
    student_id = drilldown_paper["strong_id"]

    # A second subject for the same student, reusing the same taxonomy fixture codes
    # (subject_code is what resolved_rows groups by; it does not cross-check that a
    # question's board_unit/concept_family actually belong to that subject's own book).
    h = _auth(school)
    other_aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.SCI", "title": "Science Cycle Test", "total_marks": 10},
    ).json()["assessment_id"]
    client.post(
        f"/assessments/{other_aid}/questions", headers=h, json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 10, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": "sci-test-1",
             "chapter": "X.MATH.SAV", "curriculum_section": "13.1"},
        ]},
    )
    client.patch(
        f"/assessments/{other_aid}/answers/{student_id}/reading/A/1//",
        headers=h, json={"marks": 5, "state": "awarded", "by": "test"},
    )
    client.post(f"/assessments/{other_aid}/answers/{student_id}/reading/confirm", headers=h, json={"by": "test"})

    unfiltered = client.get(f"/admin/academics/students/{student_id}", headers=h).json()
    subjects = {s["subject_code"] for s in unfiltered["subjects"]}
    assert subjects == {"X.MATH", "X.SCI"}
    overall_before = unfiltered["overall"]

    filtered = client.get(
        f"/admin/academics/students/{student_id}.xlsx", params={"subject_code": "X.SCI"}, headers=h,
    )
    assert filtered.status_code == 200
    from openpyxl import load_workbook
    import io

    sci_label = next(s["label"] for s in unfiltered["subjects"] if s["subject_code"] == "X.SCI")
    ws = load_workbook(io.BytesIO(filtered.content)).active
    assert ws.max_row == 2  # header + exactly the one X.SCI row
    assert ws.cell(row=2, column=1).value == sci_label

    # filtering the download to one subject must not have changed the whole-student
    # overall figures -- re-fetch the (always unfiltered) JSON view to prove it.
    still_unfiltered = client.get(f"/admin/academics/students/{student_id}", headers=h).json()
    assert still_unfiltered["overall"] == overall_before


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


def test_tests_tab_list_itself_downloads_as_excel_and_pdf(client, school, drilldown_paper):
    xlsx = client.get("/admin/academics/tests.xlsx", headers=_auth(school))
    assert xlsx.status_code == 200, xlsx.text
    assert xlsx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    pdf = client.get("/admin/academics/tests.pdf", headers=_auth(school))
    assert pdf.status_code == 200, pdf.text
    assert pdf.content[:4] == b"%PDF"

    from openpyxl import load_workbook
    import io

    ws = load_workbook(io.BytesIO(xlsx.content)).active
    titles_in_file = {ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)}
    listed_titles = {
        t["title"] for t in client.get("/admin/academics/tests", headers=_auth(school)).json()["tests"]
    }
    # every test the JSON list carries is in the downloaded file too -- no silent truncation
    assert listed_titles.issubset(titles_in_file)


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
