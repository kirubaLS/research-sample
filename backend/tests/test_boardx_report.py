"""The BoardX v2 one-page student report -- composition and rule engine.

Reuses the same real-curriculum fixture (X.MATH, chapter X.MATH.SAV, board unit
X.MATH.U.MENSURATION at 10% weight) every other reports test builds on, so a real Board
blueprint weight is on file and section 1's exposure line has something to verify against.
"""

from __future__ import annotations

import uuid

import pytest

from app.config import get_settings

PLATFORM_KEY = "boardx-test-platform-key"


def _auth(school):
    return {"X-API-Key": school["api_key"]}


def _platform_auth():
    return {"X-Platform-Key": PLATFORM_KEY}


@pytest.fixture(autouse=True)
def _enable_platform():
    settings = get_settings()
    before = settings.platform_admin_key
    settings.platform_admin_key = PLATFORM_KEY
    yield
    settings.platform_admin_key = before


@pytest.fixture
def boardx_paper(client, school):
    """Four questions in one chapter (Surface Areas and Volumes), enough marks lost on
    one of them that the chapter shows up as a finding, and a second, well-scored
    question so the chapter is not a total loss."""
    tag = uuid.uuid4().hex[:8]
    h = _auth(school)
    aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.MATH", "title": f"BoardX Test {tag}", "total_marks": 12},
    ).json()["assessment_id"]
    out = client.post(
        f"/assessments/{aid}/questions", headers=h, json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 2, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"bx-{tag}-1",
             "chapter": "X.MATH.SAV", "curriculum_section": "12.1"},
            {"section": "A", "question_no": "2", "max_marks": 2, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"bx-{tag}-2",
             "chapter": "X.MATH.SAV", "curriculum_section": "12.1"},
            {"section": "A", "question_no": "3", "max_marks": 4, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"bx-{tag}-3",
             "chapter": "X.MATH.SAV", "curriculum_section": "12.1"},
            {"section": "A", "question_no": "4", "max_marks": 4, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"bx-{tag}-4",
             "chapter": "X.MATH.SAV", "curriculum_section": "12.1"},
        ]},
    )
    assert out.status_code == 200, out.text

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Question, QuestionSkill, QuestionTier, StudentProfile, TaxonomyNode

    db = SessionLocal()
    student = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name=f"BoardX Student {tag}", roll_no=f"{tag}-bx",
    )
    db.add(student)

    # Two questions tagged R&U, two tagged AP, all under the same skill -- enough evidence
    # (the 2-mark, 2-question floor) at both tiers for skill_by_tier to find a genuine
    # complexity gap between them, which is what section 3 is meant to detect.
    skill_node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.VOLUME"))
    questions = {
        q.address: q for q in db.scalars(select(Question).where(Question.assessment_id == aid))
    }
    for address, tier in (("A/1//", "R&U"), ("A/2//", "R&U"), ("A/3//", "AP"), ("A/4//", "AP")):
        q = questions[address]
        db.add(QuestionSkill(question_id=q.id, node_id=skill_node.id))
        db.add(QuestionTier(question_id=q.id, tier=tier))
    db.commit()
    student_id = student.id
    db.close()

    # 2 of 12 scored: well below the chapter's own marks, and comfortably clears the
    # evidence floor (4 questions, 12 marks), so the chapter is both diagnosable and a
    # real finding worth showing in sections 3-5.
    for address, mark in zip(("A/1//", "A/2//", "A/3//", "A/4//"), [2, 0, 0, 0]):
        r = client.patch(
            f"/assessments/{aid}/answers/{student_id}/reading/{address}",
            headers=h, json={"marks": mark, "state": "awarded", "by": "test"},
        )
        assert r.status_code == 200, r.text
    confirmed = client.post(
        f"/assessments/{aid}/answers/{student_id}/reading/confirm",
        headers=h, json={"by": "test"},
    )
    assert confirmed.status_code == 200, confirmed.text

    return aid, student_id


def test_section1_shows_scored_available_and_verified_board_exposure(
    client, school, boardx_paper,
):
    aid, student_id = boardx_paper
    r = client.get(
        f"/reports/student/{student_id}/boardx", params={"assessment_id": aid}, headers=_auth(school),
    )
    assert r.status_code == 200, r.text
    body = r.json()

    chapter_row = next(e for e in body["section1"] if e.get("domain_code") == "X.MATH.SAV")
    assert chapter_row["scored"] == 2.0
    assert chapter_row["available"] == 12.0
    assert chapter_row["not_scored"] == 10.0
    assert chapter_row["diagnosable"] is True
    # X.MATH.U.MENSURATION carries 10% in the fixture curriculum -- a verified blueprint
    # fact, not a guess, and rounds to 8 of 80.
    assert chapter_row["board_exposure_verified"] is True
    assert chapter_row["board_exposure"] == 8
    assert chapter_row["board_total"] == 80
    # R6: never a calibrated impact number without an approved model.
    assert chapter_row["estimated_board_impact"] == "NOT_CALIBRATED"

    ids = {line["id"] for entry in body["section1"] for line in entry["lines"]}
    assert "S1_BOARD_IMPACT_NOT_CALIBRATED" in ids


def test_section3_to_5_resolve_a_remediation_row_end_to_end(client, school, boardx_paper):
    aid, student_id = boardx_paper

    seed = client.post(
        "/platform/remediation", headers=_platform_auth(), json={
            "remediation_ref": "TEST-RM-SAV-SCOPE-01",
            "subject_code": "X.MATH", "domain_code": "X.MATH.SAV",
            "finding_type": "complexity_gap",
            "student_action_text": "Practise the approved Surface Areas and Volumes problem set.",
            "approved": True, "by": "test",
        },
    )
    assert seed.status_code == 201, seed.text

    r = client.get(
        f"/reports/student/{student_id}/boardx", params={"assessment_id": aid}, headers=_auth(school),
    )
    body = r.json()

    card = next(c for c in body["section4"] if c["domain"] == "Surface Areas and Volumes")
    assert card["action"] is not None
    assert card["action"]["remediation_ref"] == "TEST-RM-SAV-SCOPE-01"
    assert any(line["id"] == "S4_ACTION" for line in card["lines"])

    actions = body["section5"]["actions"]
    assert any(a["remediation_ref"] == "TEST-RM-SAV-SCOPE-01" for a in actions)


def test_a_chapter_with_no_resolvable_remediation_says_so_not_localised(client, school):
    """A different chapter from every other test in this file, on purpose: the
    catalogue is a shared platform-wide table, so a row another test approved for
    X.MATH.SAV/complexity_gap would otherwise resolve here too and this test would only
    be checking test order, not the actual not-localised behaviour."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Question, QuestionSkill, QuestionTier, StudentProfile, TaxonomyNode

    tag = uuid.uuid4().hex[:8]
    h = _auth(school)

    db = SessionLocal()
    chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.AREAS"))
    if db.scalar(
        select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.AREAS_LOCALISATION_TEST")
    ) is None:
        db.add(TaxonomyNode(
            kind="concept_family", code="X.MATH.CF.AREAS_LOCALISATION_TEST",
            label="Areas localisation test", parent_id=chapter.id,
            path="X.MATH.CF.AREAS_LOCALISATION_TEST",
        ))
        db.commit()
    skill_node = db.scalar(
        select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.AREAS_LOCALISATION_TEST")
    )
    db.close()

    aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.MATH", "title": f"BoardX No-Remediation {tag}", "total_marks": 12},
    ).json()["assessment_id"]
    out = client.post(
        f"/assessments/{aid}/questions", headers=h, json={"questions": [
            {"section": "A", "question_no": n, "max_marks": m, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.AREAS_LOCALISATION_TEST", "concept_variant": f"bx-nl-{tag}-{n}",
             "chapter": "X.MATH.AREAS", "curriculum_section": "11.1"}
            for n, m in (("1", 2), ("2", 2), ("3", 4), ("4", 4))
        ]},
    )
    assert out.status_code == 200, out.text

    db = SessionLocal()
    student = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name=f"No Remediation Student {tag}", roll_no=f"{tag}-nl",
    )
    db.add(student)
    questions = {
        q.address: q for q in db.scalars(select(Question).where(Question.assessment_id == aid))
    }
    for address, tier in (("A/1//", "R&U"), ("A/2//", "R&U"), ("A/3//", "AP"), ("A/4//", "AP")):
        q = questions[address]
        db.add(QuestionSkill(question_id=q.id, node_id=skill_node.id))
        db.add(QuestionTier(question_id=q.id, tier=tier))
    db.commit()
    student_id = student.id
    db.close()

    for address, mark in zip(("A/1//", "A/2//", "A/3//", "A/4//"), [2, 0, 0, 0]):
        r = client.patch(
            f"/assessments/{aid}/answers/{student_id}/reading/{address}",
            headers=h, json={"marks": mark, "state": "awarded", "by": "test"},
        )
        assert r.status_code == 200, r.text
    confirmed = client.post(
        f"/assessments/{aid}/answers/{student_id}/reading/confirm", headers=h, json={"by": "test"},
    )
    assert confirmed.status_code == 200, confirmed.text

    r = client.get(
        f"/reports/student/{student_id}/boardx", params={"assessment_id": aid}, headers=h,
    )
    body = r.json()
    card = next(c for c in body["section4"] if c["domain"] == "Areas Related to Circles")
    assert card["action"] is None
    assert any(line["id"] == "S4_NOT_LOCALISED" for line in card["lines"])


def test_frozen_strings_never_mention_the_student_in_third_person(client, school, boardx_paper):
    """R1/audit check 6: STUDENT register only, everywhere."""
    aid, student_id = boardx_paper
    r = client.get(
        f"/reports/student/{student_id}/boardx", params={"assessment_id": aid}, headers=_auth(school),
    )
    body = r.json()
    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    name = db.get(StudentProfile, student_id).name
    db.close()

    all_text = " ".join(
        line["text"]
        for entry in body["section1"] for line in entry["lines"]
    ) + " ".join(line["text"] for line in body["section3"])
    assert name not in all_text
    # "will lose or gain" legitimately appears inside the approved NOT_CALIBRATED
    # disclaimer itself (S1_BOARD_IMPACT_NOT_CALIBRATED) to say exactly that this report
    # does *not* make that claim -- so only the labelling words are checked here.
    for banned in ("weak", "slow learner", "poor performer", "failing student"):
        assert banned not in all_text.lower()
