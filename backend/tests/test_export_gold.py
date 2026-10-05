from scripts.export_gold import build_gold

ROWS = [
    {"address": "A/1//", "chapter": "X.HIST.PRINT", "label": "Print Culture", "section": "2"},
    {"address": "A/2//", "chapter": "X.HIST.PRINT", "label": "Print Culture", "section": "3.1"},
    {"address": "A/3//", "chapter": "X.HIST.NATION", "label": "Nationalism", "section": "1"},
    {"address": "B/4//", "chapter": "X.GEO.MIN", "label": "Minerals", "section": "2.2"},
]


def test_a_section_letters_chapter_is_the_one_most_of_its_questions_sit_in():
    gold = build_gold(ROWS, paper="p")
    assert gold["section_chapters"]["A"] == {
        "subject": "X.HIST", "chapter": "X.HIST.PRINT", "label": "Print Culture"}
    assert gold["section_chapters"]["B"]["chapter"] == "X.GEO.MIN"


def test_a_question_in_another_chapter_carries_its_own():
    q = build_gold(ROWS)["questions"]
    assert "chapter" not in q["A/1//"] and q["A/3//"]["chapter"] == "X.HIST.NATION"
    assert q["A/2//"]["exact"] == ["3.1"] and q["A/1//"]["partial"] == []


def test_the_shape_is_what_eval_mapping_reads():
    gold = build_gold(ROWS)
    assert set(gold) >= {"paper", "section_chapters", "targets", "questions"}
    assert gold["targets"]["chapter_correct"] == 4


def test_the_exporter_reads_only_a_questions_newest_confirmed_placement(client, school):
    import uuid

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement
    from scripts.export_gold import confirmed_rows

    headers = {"X-API-Key": school["api_key"]}
    tag = uuid.uuid4().hex[:8]
    aid = client.post("/assessments", headers=headers, json={
        "subject_code": "X.MATH", "title": f"Gold {tag}", "total_marks": 2}).json()["assessment_id"]
    client.post(f"/assessments/{aid}/questions", headers=headers, json={"questions": [{
        "section": "A", "question_no": "1", "max_marks": 2, "stem_text": f"cone {tag}",
        "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
        "concept_variant": f"v {tag}"}]})
    db = SessionLocal()
    try:
        qid = db.scalars(select(Question).where(Question.assessment_id == aid)).first().id
        db.add(QuestionPlacement(question_id=qid, source="model", needs_review=True))
        db.commit()
        assert confirmed_rows(db, aid) == [], "a machine placement is not a label"
    finally:
        db.close()
    r = client.post(f"/assessments/{aid}/review/{qid}", headers=headers, json={
        "chapter_code": "X.MATH.SAV", "curriculum_section": "12.2", "reviewed_by": "t"})
    assert r.status_code == 200
    db = SessionLocal()
    try:
        [row] = confirmed_rows(db, aid)
        assert row["chapter"] == "X.MATH.SAV" and row["section"] == "12.2"
    finally:
        db.close()
