"""A real English/Hindi exam paper draws on several NCERT books at once, so creating an
Assessment must accept the group as a whole (subject_code="X.ENG") as well as a single
book, and /admin/subjects must show the group structure to the screen that offers it.
"""

from __future__ import annotations


def _auth(school):
    return {"X-API-Key": school["api_key"]}


def test_admin_subjects_groups_english_and_leaves_math_alone(client, school):
    r = client.get("/admin/subjects", headers=_auth(school))
    assert r.status_code == 200
    groups = {g["group_code"]: g for g in r.json()["subjects"]}

    english = groups["X.ENG"]
    assert english["group_label"] == "Class X English"
    assert [b["subject_code"] for b in english["books"]] == [
        "X.ENG.FF", "X.ENG.FWF", "X.ENG.WB",
    ]
    assert english["chapters"] == sum(b["chapters"] for b in english["books"])

    hindi = groups["X.HIN"]
    assert len(hindi["books"]) == 4

    math = groups["X.MATH"]
    assert len(math["books"]) == 1
    assert math["books"][0]["subject_code"] == "X.MATH"
    # single-book group keeps top-level back-compat fields identical to the one book
    assert math["subject_code"] == "X.MATH"
    assert math["chapters"] == math["books"][0]["chapters"]


def test_creating_an_assessment_with_a_group_subject_code_succeeds(client, school):
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.ENG", "title": "English Unit Test", "total_marks": 40},
    )
    assert r.status_code == 200, r.json()


def test_creating_an_assessment_with_a_book_level_subject_code_still_works(client, school):
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.ENG.FF", "title": "First Flight Test", "total_marks": 20},
    )
    assert r.status_code == 200, r.json()


def test_creating_an_assessment_with_an_unknown_subject_is_refused(client, school):
    r = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.NOPE", "title": "Bad", "total_marks": 10},
    )
    assert r.status_code == 422
    assert "X.NOPE" in r.json()["detail"]
