"""Zero-touch: a teacher uploads and closes the window. Nothing below waits on a person.

Scan -> confirm -> map -> classify runs by itself after the upload is read; a mark the
extractor missed is filled from the paper's own pattern; a chapter with no concept family
gets one from the book's heading; an answer sheet's resolved rows are confirmed with
unreadable cells excused rather than blocking the student.
"""

from __future__ import annotations

from sqlalchemy import select

from test_scan_and_map import MARK_X, STATS_PAPER, _auth, _paper_bytes, _upload


def test_auto_confirm_fills_a_missing_mark_from_the_papers_own_pattern(client, school):
    from app.api.marks import auto_confirm_scan
    from app.db import SessionLocal
    from app.models import Assessment, ScannedQuestion

    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Missing marks", "total_marks": 7,
    }).json()["assessment_id"]
    db = SessionLocal()
    try:
        rows = [
            ScannedQuestion(assessment_id=aid, address="A/1//a", section="A", question_no="1",
                            sub_part="a", max_marks=2, stem_text="first part"),
            ScannedQuestion(assessment_id=aid, address="A/1//b", section="A", question_no="1",
                            sub_part="b", max_marks=None, stem_text="second part, label missed"),
            ScannedQuestion(assessment_id=aid, address="A/2", section="A", question_no="2",
                            max_marks=None, stem_text="whole question, label missed"),
            ScannedQuestion(assessment_id=aid, address="A/3", section="A", question_no="3",
                            max_marks=3, stem_text="three marks"),
        ]
        db.add_all(rows)
        db.commit()
        out = auto_confirm_scan(db, db.get(Assessment, aid))
        got = {r.address: (float(r.max_marks), r.edited_by) for r in db.scalars(
            select(ScannedQuestion).where(ScannedQuestion.assessment_id == aid)
        )}
        assert got["A/1//b"] == (2.0, "auto"), "a sub-part takes its sibling's marks"
        assert got["A/2"][1] == "auto" and got["A/2"][0] in (2.0, 3.0), "else the section's usual mark"
        assert got["A/3"] == (3.0, None)
        assert out["confirmed_by"] == "auto" and set(out["marks_filled"]) == {"A/1//b", "A/2"}
        assert db.get(Assessment, aid).scan_confirmed_by == "auto"
    finally:
        db.close()


def test_an_upload_runs_confirm_map_and_classify_by_itself(client, school, book, monkeypatch):
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import Assessment, PlacementJob, Question

    monkeypatch.setattr(get_settings(), "auto_pipeline", True)
    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Zero touch", "total_marks": 3,
    }).json()["assessment_id"]
    out = _upload(client, school, aid, _paper_bytes(STATS_PAPER))
    assert out.status_code in (200, 201, 202), out.text

    db = SessionLocal()
    try:
        a = db.get(Assessment, aid)
        assert a.scan_confirmed_by == "auto", "nobody pressed Confirm"
        jobs = {j.kind: j for j in db.scalars(select(PlacementJob).where(PlacementJob.assessment_id == aid))}
        assert jobs["map"].status == "succeeded", jobs["map"].error_detail
        assert jobs["map"].result["mapped"] == 1
        # classify needs the classifier key; without one the chain records why rather
        # than leaving the job pending forever
        assert jobs["place"].status in ("succeeded", "failed")
        if jobs["place"].status == "failed":
            assert "classifier key" in (jobs["place"].error_detail or "")
        q = db.scalars(select(Question).where(Question.assessment_id == aid)).first()
        assert q is not None and q.chapter_id is not None, "the question was mapped without a click"
    finally:
        db.close()


def test_map_creates_the_family_from_the_books_heading_when_the_chapter_has_none(
    client, school, book, monkeypatch,
):
    """Circles has a chunk but no concept family in the fixture. Zero-touch cannot wait
    for someone to create one, so map makes it from the section heading and records the
    section it claims."""
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import ConceptFamilyProposal, Question, TaxonomyNode

    monkeypatch.setattr(get_settings(), "auto_pipeline", True)
    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Circles", "total_marks": 2,
    }).json()["assessment_id"]
    paper = [[
        (60, 60, "Maximum Marks: 2"),
        (60, 100, "SECTION A"),
        (60, 130, "1. Prove that the tangent at any point of a circle is perpendicular"),
        (60, 144, "to the radius through the point of contact."),
        (MARK_X, 130, "2"),
    ]]
    out = _upload(client, school, aid, _paper_bytes(paper))
    assert out.status_code in (200, 201, 202), out.text

    db = SessionLocal()
    try:
        q = db.scalars(select(Question).where(Question.assessment_id == aid)).first()
        assert q is not None, "placed, not blocked on a missing family"
        family = db.get(TaxonomyNode, q.concept_family_id)
        assert family.code.startswith("X.MATH.CIRCLE.CF.AUTO_")
        assert family.label == "Tangent to a Circle"
        proposal = db.scalar(select(ConceptFamilyProposal).where(ConceptFamilyProposal.code == family.code))
        assert proposal is not None and "10.1" in proposal.from_sections
    finally:
        db.close()


def test_auto_confirm_excuses_an_unreadable_cell_instead_of_blocking_the_student(client, school, book):
    from app.api.gridsheets import _confirm_grid_rows
    from app.db import SessionLocal
    from app.models import (
        Assessment, GridSheetRow, MarkEvent, ProposedMark, Question, ScanDocument, StudentProfile,
    )

    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.MATH", "title": "Grid", "total_marks": 2,
    }).json()["assessment_id"]
    client.post(f"/assessments/{aid}/questions", headers=h, json={"questions": [
        {"section": "A", "question_no": "1", "max_marks": 1, "stem_text": "one",
         "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME", "concept_variant": "g1"},
        {"section": "A", "question_no": "2", "max_marks": 1, "stem_text": "two",
         "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME", "concept_variant": "g2"},
    ]})
    db = SessionLocal()
    try:
        a = db.get(Assessment, aid)
        student = StudentProfile(school_id=school["school_id"], section_id=school["section_id"],
                                 name="Grid Student", roll_no="77")
        db.add(student)
        db.flush()
        qs = {q.question_no: q for q in db.scalars(select(Question).where(Question.assessment_id == aid))}
        doc = ScanDocument(school_id=school["school_id"], assessment_id=aid, kind="answer_sheet",
                           page_count=1, sha256="x" * 64)
        db.add(doc)
        db.flush()
        row = GridSheetRow(school_id=school["school_id"], assessment_id=aid, section_id=school["section_id"],
                           document_id=doc.id, roll_no=student.roll_no, name_as_written=student.name,
                           student_id=student.id, status="clean", cells=[])
        db.add(row)
        db.add_all([
            ProposedMark(school_id=school["school_id"], assessment_id=aid, student_id=student.id,
                         address=qs["1"].address, marks=1, state="awarded", raw_value="1"),
            ProposedMark(school_id=school["school_id"], assessment_id=aid, student_id=student.id,
                         address=qs["2"].address, marks=None, state="awarded", raw_value="?",
                         problem="could not read this cell"),
        ])
        db.commit()

        confirmed, skipped = _confirm_grid_rows(db, a, [row], by="auto", excuse_problems=True)
        db.commit()
        assert confirmed == [student.roll_no] and skipped == []
        events = {
            e.question_id: e
            for e in db.scalars(select(MarkEvent).where(MarkEvent.assessment_id == aid))
        }
        assert float(events[qs["1"].id].marks) == 1.0 and events[qs["1"].id].source == "auto"
        assert events[qs["2"].id].state == "not_offered" and events[qs["2"].id].marks is None
        assert events[qs["2"].id].provenance["excused"] is True

        # the person-in-the-loop path still refuses the same row
        db.add(ProposedMark(school_id=school["school_id"], assessment_id=aid, student_id=student.id,
                            address=qs["2"].address, marks=None, state="awarded", raw_value="?",
                            problem="could not read this cell"))
        db.commit()
        confirmed, skipped = _confirm_grid_rows(db, a, [row], by="Mr. Iyer")
        assert confirmed == [] and "problem" in skipped[0]["reason"]
    finally:
        db.close()
