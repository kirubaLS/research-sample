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


def test_a_lower_band_finding_with_no_resolvable_remediation_is_dropped_not_shown(client, school):
    """R4: when remediation does not resolve, lower assembly must not show that finding
    at all -- a struggling student should never see a card naming a real loss with
    nothing concrete attached to it. (Upper assembly's different rule -- show the finding
    anyway, without an action -- is covered separately.)

    A different chapter from every other test in this file, on purpose: the catalogue is
    a shared platform-wide table, so a row another test approved for
    X.MATH.SAV/complexity_gap would otherwise resolve here too and this test would only
    be checking test order, not the actual drop behaviour."""
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
    assert body["assembly_band"] == "lower"  # 2 of 12 scored -- well under the 50% split
    assert not any(c["domain"] == "Areas Related to Circles" for c in body["section4"])
    # Nothing about this chapter's unresolved pattern leaks into section 3 either.
    assert not any("Areas Related to Circles" in line["text"] for line in body["section3"])


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


def test_a_subject_with_no_real_board_weight_yet_never_prints_a_fake_zero(client, school):
    """Every subject but Mathematics and Science currently carries a 0.0 placeholder
    weight on every one of its board units (app.curriculum's own BoardUnit rows -- not
    yet populated with real CBSE blueprint data). Composing a report for one of them
    must say NOT_CALIBRATED, never a verified-looking '0 of 80 Board marks' -- the same
    dynamic path X.MATH goes through, proving the engine is not Mathematics-specific."""
    from sqlalchemy import select

    from app.curriculum import X_HISTORY
    from app.curriculum.apply import apply as apply_curriculum
    from app.db import SessionLocal
    from app.models import Question, QuestionSkill, QuestionTier, StudentProfile, TaxonomyNode

    tag = uuid.uuid4().hex[:8]
    h = _auth(school)

    db = SessionLocal()
    apply_curriculum(db, X_HISTORY)
    chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.HIST.PRINTCULTURE"))
    family_code = "X.HIST.CF.PRINTCULTURE_TEST"
    if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == family_code)) is None:
        db.add(TaxonomyNode(
            kind="concept_family", code=family_code, label="Print culture test family",
            parent_id=chapter.id, path=family_code,
        ))
        db.commit()
    skill_node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == family_code))
    db.close()

    aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.HIST", "title": f"BoardX History {tag}", "total_marks": 12},
    ).json()["assessment_id"]
    out = client.post(
        f"/assessments/{aid}/questions", headers=h, json={"questions": [
            {"section": "A", "question_no": n, "max_marks": m, "board_unit": "X.HIST.U.WHOLE",
             "concept_family": family_code, "concept_variant": f"bx-hist-{tag}-{n}",
             "chapter": "X.HIST.PRINTCULTURE", "curriculum_section": "5.1"}
            for n, m in (("1", 2), ("2", 2), ("3", 4), ("4", 4))
        ]},
    )
    assert out.status_code == 200, out.text

    db = SessionLocal()
    student = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name=f"History Student {tag}", roll_no=f"{tag}-hist",
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

    seed = client.post(
        "/platform/remediation", headers=_platform_auth(), json={
            "remediation_ref": f"TEST-RM-HIST-PRINTCULTURE-{tag}",
            "subject_code": "X.HIST", "domain_code": "X.HIST.PRINTCULTURE",
            "finding_type": "complexity_gap",
            "student_action_text": "Practise the approved Print Culture problem set.",
            "approved": True, "by": "test",
        },
    )
    assert seed.status_code == 201, seed.text

    r = client.get(
        f"/reports/student/{student_id}/boardx", params={"assessment_id": aid}, headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subject_code"] == "X.HIST"

    chapter_row = next(e for e in body["section1"] if e.get("domain_code") == "X.HIST.PRINTCULTURE")
    assert chapter_row["board_exposure_verified"] is False
    assert chapter_row["board_exposure"] is None
    ids = {line["id"] for entry in body["section1"] for line in entry["lines"]}
    assert "S1_BOARD_NOT_CALIBRATED" in ids
    assert "S1_BOARD_EXPOSURE" not in ids

    # And the same complexity-gap pattern search that worked for X.MATH works here too --
    # nothing in sections 3-4 is Mathematics-specific. Remediation was seeded above so
    # this lower-band finding is not dropped (see R4's lower-band rule).
    card = next(c for c in body["section4"] if c["domain"] == "Print Culture and the Modern World")
    assert any(line["id"] == "S4_ACTION" for line in card["lines"])


def test_an_upper_band_finding_with_no_resolvable_remediation_is_shown_without_an_action(
    client, school,
):
    """R4's other half: upper assembly MAY show a finding whose remediation does not
    resolve, just without an action line -- unlike lower assembly, which drops it."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Question, QuestionSkill, QuestionTier, StudentProfile, TaxonomyNode

    tag = uuid.uuid4().hex[:8]
    h = _auth(school)

    db = SessionLocal()
    chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.TRIANGLE"))
    family_code = "X.MATH.CF.TRIANGLE_UPPERBAND_TEST"
    if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == family_code)) is None:
        db.add(TaxonomyNode(
            kind="concept_family", code=family_code, label="Triangle upper-band test",
            parent_id=chapter.id, path=family_code,
        ))
        db.commit()
    skill_node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == family_code))
    db.close()

    aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.MATH", "title": f"BoardX Upper Band {tag}", "total_marks": 12},
    ).json()["assessment_id"]
    out = client.post(
        f"/assessments/{aid}/questions", headers=h, json={"questions": [
            {"section": "A", "question_no": n, "max_marks": m, "board_unit": "X.MATH.U.GEOMETRY",
             "concept_family": family_code, "concept_variant": f"bx-ub-{tag}-{n}",
             "chapter": "X.MATH.TRIANGLE", "curriculum_section": "6.1"}
            for n, m in (("1", 2), ("2", 2), ("3", 4), ("4", 4))
        ]},
    )
    assert out.status_code == 200, out.text

    db = SessionLocal()
    student = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name=f"Upper Band Student {tag}", roll_no=f"{tag}-ub",
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

    # 8 of 12 = 67%, comfortably above the 50% split -- upper band. Full marks on the
    # R&U pair, half on the AP pair: a real complexity gap, with 4 marks genuinely lost.
    for address, mark in zip(("A/1//", "A/2//", "A/3//", "A/4//"), [2, 2, 4, 0]):
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
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assembly_band"] == "upper"

    card = next(c for c in body["section4"] if c["domain"] == "Triangles")
    assert card["action"] is None
    # Not S4_NOT_LOCALISED either -- a real pattern WAS found, just no approved practice
    # text for it yet.
    assert not any(line["id"] == "S4_NOT_LOCALISED" for line in card["lines"])
    assert any(line["id"] == "S3_SCOPE_LOSS" for line in card["lines"])


def test_board_recurrence_renders_when_the_corpus_has_been_computed(client, school):
    """A real, calibrated Board-recurrence count (spec section 3.4 / R5), read from
    app.curriculum.board_frequency -- not the always-on NOT_CALIBRATED disclaimer this
    engine used to print regardless of whether real data existed."""
    from sqlalchemy import select

    from app.curriculum.board_frequency import CURRENT_VERSION
    from app.db import SessionLocal
    from app.models import FamilyBoardFrequency, TaxonomyNode

    db = SessionLocal()
    family = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.VOLUME"))
    # Upsert, not skip-if-exists: another test file's own real board_frequency.recompute()
    # run can leave a row for this same family/version/stream already on file (a shared
    # session-scoped database), and this test must assert against the exact numbers it
    # seeds, not whatever a different test happened to compute first.
    existing = db.scalar(
        select(FamilyBoardFrequency).where(
            FamilyBoardFrequency.concept_family_id == family.id,
            FamilyBoardFrequency.curriculum_version == CURRENT_VERSION,
            FamilyBoardFrequency.stream == "standard",
        )
    )
    row = existing or FamilyBoardFrequency(
        concept_family_id=family.id, curriculum_version=CURRENT_VERSION, stream="standard",
    )
    row.subject_code = "X.MATH"
    row.window_years = [2021, 2022, 2023, 2024]
    row.years_eligible = 4
    row.years_appeared = 3
    row.marks_by_year = {"2022": 4.0, "2023": 4.0, "2024": 4.0}
    row.marks_range = 0.0
    row.base_multiplier = 1.5
    row.multiplier = 1.5
    row.adjustments = []
    row.papers_used = 4
    row.config_version = "v1"
    row.computed_at = "2026-01-01T00:00:00"
    if existing is None:
        db.add(row)
    db.commit()
    db.close()

    tag = uuid.uuid4().hex[:8]
    h = _auth(school)
    aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.MATH", "title": f"BoardX Recurrence {tag}", "total_marks": 4},
    ).json()["assessment_id"]
    out = client.post(
        f"/assessments/{aid}/questions", headers=h, json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 4, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"bx-rec-{tag}-1",
             "chapter": "X.MATH.SAV", "curriculum_section": "12.1"},
        ]},
    )
    assert out.status_code == 200, out.text

    from app.models import StudentProfile

    db = SessionLocal()
    student = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name=f"Recurrence Student {tag}", roll_no=f"{tag}-rec",
    )
    db.add(student)
    db.commit()
    student_id = student.id
    db.close()

    r = client.patch(
        f"/assessments/{aid}/answers/{student_id}/reading/A/1//",
        headers=h, json={"marks": 4, "state": "awarded", "by": "test"},
    )
    assert r.status_code == 200, r.text
    confirmed = client.post(
        f"/assessments/{aid}/answers/{student_id}/reading/confirm", headers=h, json={"by": "test"},
    )
    assert confirmed.status_code == 200, confirmed.text

    r = client.get(
        f"/reports/student/{student_id}/boardx", params={"assessment_id": aid}, headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    chapter_row = next(e for e in body["section1"] if e.get("domain_code") == "X.MATH.SAV")
    recurrence_lines = [l for l in chapter_row["lines"] if l["id"] == "S1_BOARD_RECURRENCE"]
    assert len(recurrence_lines) == 1
    assert "3 of the last 4 Board years" in recurrence_lines[0]["text"]

    # A real recurrence line for this chapter means the blanket "not counted yet"
    # disclaimer would be false, so it must not appear.
    assert not any(line["id"] == "S6_UNCALIBRATED_BOARD_HISTORY" for line in body["section6"])
