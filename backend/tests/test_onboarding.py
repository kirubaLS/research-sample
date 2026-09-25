"""The real /attend/onboarding 6-step wizard: POST /t/{class_code}/onboard.

Deliberately separate from test_api_end_to_end.py's RIASEC flow -- this endpoint never
creates a TestSession, and the RIASEC instrument stays independently testable and
untouched by anything here.
"""

from __future__ import annotations


def _full_payload(roll_no: str = "101") -> dict:
    return {
        "name": "Meera K",
        "roll_no": roll_no,
        "age": 15,
        "gender": "female",
        "dob": "2010-05-14",
        "board": "CBSE",
        "lives_in": "town",
        "decision_helper": "family",
        "responsibilities": "no",
        "subject_enjoy": "Mathematics",
        "subject_comfortable": "Science",
        "learning_type": "solving",
        "interests": ["tech", "sports", "music_dance"],
        "work_interest": "machines",
        "new_learning_style": "practical",
        "future_career": "Software engineer",
        "class11_group": "maths_cs",
        "group_reason": ["like_subjects", "career_match"],
        "confidence": 4,
    }


def test_full_submit_persists_every_field(client, school):
    r = client.post(f"/t/{school['section_id']}/onboard", json=_full_payload("101"))
    assert r.status_code == 200
    body = r.json()
    assert body["message"] == "saved"
    student_id = body["student_id"]

    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    try:
        row = db.get(StudentProfile, student_id)
        assert row is not None
        assert row.name == "Meera K"
        assert row.board == "CBSE"
        assert row.lives_in == "town"
        assert row.decision_helper == "family"
        assert row.responsibilities == "no"
        assert row.subject_enjoy == "Mathematics"
        assert row.subject_comfortable == "Science"
        assert row.learning_type == "solving"
        assert row.interests == ["tech", "sports", "music_dance"]
        assert row.work_interest == "machines"
        assert row.new_learning_style == "practical"
        assert row.future_career == "Software engineer"
        assert row.class11_group == "maths_cs"
        assert row.group_reason == ["like_subjects", "career_match"]
        assert row.confidence == 4
        assert row.dob is not None and row.dob.isoformat() == "2010-05-14"
    finally:
        db.close()


def test_resubmitting_the_same_roll_updates_in_place(client, school):
    first = client.post(f"/t/{school['section_id']}/onboard", json=_full_payload("102"))
    assert first.status_code == 200
    second_payload = _full_payload("102")
    second_payload["confidence"] = 2
    second_payload["future_career"] = "Doctor"
    second = client.post(f"/t/{school['section_id']}/onboard", json=second_payload)
    assert second.status_code == 200
    assert second.json()["student_id"] == first.json()["student_id"]

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import StudentProfile

    db = SessionLocal()
    try:
        row = db.scalar(
            select(StudentProfile).where(
                StudentProfile.section_id == school["section_id"], StudentProfile.roll_no == "102"
            )
        )
        assert row.confidence == 2
        assert row.future_career == "Doctor"
    finally:
        db.close()


def test_onboarding_never_creates_a_test_session(client, school):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import TestSession

    r = client.post(f"/t/{school['section_id']}/onboard", json=_full_payload("103"))
    student_id = r.json()["student_id"]
    db = SessionLocal()
    try:
        sessions = db.scalars(select(TestSession).where(TestSession.student_id == student_id)).all()
        assert sessions == []
    finally:
        db.close()


def test_confidence_must_be_1_to_5(client, school):
    payload = _full_payload("104")
    payload["confidence"] = 6
    r = client.post(f"/t/{school['section_id']}/onboard", json=payload)
    assert r.status_code == 422

    payload["confidence"] = 0
    r = client.post(f"/t/{school['section_id']}/onboard", json=payload)
    assert r.status_code == 422


def test_interests_capped_at_three(client, school):
    payload = _full_payload("105")
    payload["interests"] = ["tech", "sports", "music_dance", "reading_writing"]
    r = client.post(f"/t/{school['section_id']}/onboard", json=payload)
    assert r.status_code == 422


def test_group_reason_capped_at_two(client, school):
    payload = _full_payload("106")
    payload["group_reason"] = ["like_subjects", "career_match", "parents_suggested"]
    r = client.post(f"/t/{school['section_id']}/onboard", json=payload)
    assert r.status_code == 422


def test_unknown_class_code_404s(client, school):
    r = client.post("/t/does-not-exist/onboard", json=_full_payload("107"))
    assert r.status_code == 404


def test_minimal_submit_with_only_required_fields_works(client, school):
    r = client.post(
        f"/t/{school['section_id']}/onboard",
        json={"name": "Bare Minimum", "roll_no": "108"},
    )
    assert r.status_code == 200
