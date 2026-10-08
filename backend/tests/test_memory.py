"""Confirmed-question memory: recall, reuse, worked examples, and the observe-first mode.
Every judge is a stub; no paid API is called."""

from __future__ import annotations

from app.classify.judge import Classification, Evidence, build_prompt
from app.classify.memory import QuestionMemory, Remembered, demonstration_block, summarise
from app.classify.pipeline import PassOptions, place_paper
from app.ingest.probe import LexicalIndex

TANGENT = "Prove that the tangent at any point of a circle is perpendicular to the radius."
SECTOR = "Find the area of a sector of a circle with radius 7 cm and angle 60 degrees."


def _memory():
    return QuestionMemory([
        Remembered("a", TANGENT, "Circles", "10.2", "Analysing, Evaluating & Creating"),
        Remembered("b", SECTOR, "Areas Related to Circles", "11.2", "Applying"),
        Remembered("c", "State Euclid's division lemma.", "Real Numbers", "1.1"),
    ])


def test_a_rephrased_question_recalls_its_confirmed_twin():
    r = _memory().recall(
        "Prove that the tangent at any point of a circle is perpendicular to the radius "
        "through the point of contact.")
    assert r.best.entry.question_id == "a" and r.best.similarity > 0.85
    assert r.vote == "Circles" and r.unanimous
    assert r.reusable(0.8) is not None
    assert r.reusable(0.99) is None, "a stricter threshold refuses the same hit"


def test_an_unrelated_question_recalls_nothing():
    r = _memory().recall("Name the capital of France.")
    assert r.hits == () and r.vote is None and r.reusable(0.5) is None


def test_a_question_is_never_recalled_from_its_own_confirmation():
    r = _memory().recall(TANGENT, exclude="a")
    assert all(h.entry.question_id != "a" for h in r.hits)


def test_two_close_twins_in_different_chapters_are_not_reusable():
    memory = QuestionMemory([
        Remembered("a", TANGENT, "Circles", "10.2"),
        Remembered("b", TANGENT + " Hence find the length.", "Constructions", "11.1"),
    ])
    r = memory.recall(TANGENT)
    assert not r.unanimous and r.reusable(0.5) is None


def test_demonstrations_are_filtered_by_similarity_and_formatted_for_the_prompt():
    shown = _memory().demonstrations(
        "Find the area of a sector with radius 14 cm and angle 90 degrees.", 3,
        min_similarity=0.3)
    assert [h.entry.question_id for h in shown] == ["b"]
    block = demonstration_block(shown)
    assert "ALREADY PLACED" in block and "Areas Related to Circles, section 11.2" in block
    assert demonstration_block([]) == ""
    prompt = build_prompt("q", [Evidence(chapter="C", reference="r", section="1", text="t")],
                          examples=shown)
    assert prompt.rstrip().endswith("section 11.2")


# --- inside the pass ---------------------------------------------------------------------


class _Chunk:
    def __init__(self, cid, text, node):
        self.chunk_id = self.id = cid
        self.text = text
        self.reference = cid
        self.node_id = node
        self.bucket = "T"
        self.embedding = None
        self.section_number = None


NAMES = {"G1": "Circles", "H1": "Constructions"}


def _corpus():
    chunks = [
        _Chunk("g1a", "tangent circle radius perpendicular point of contact tangent", "G1"),
        _Chunk("g1b", "circle tangent radius theorem proof", "G1"),
        _Chunk("h1a", "construct triangle compass ruler", "H1"),
    ]
    return chunks + [_Chunk(f"pad{i}", f"unrelated filler topic {i}", f"X{i}") for i in range(20)]


class _Judge:
    def __init__(self):
        self.calls = []

    def classify(self, question, evidence, *, scoped=False, examples=None):
        self.calls.append(examples)
        return Classification(
            chapter="Circles", curriculum_section=None, tier=None, skill_required="",
            reasoning="stub", evidence=[], confidence=0.9, alternative_chapter=None,
        )


def _run(judge, **options):
    return place_paper(
        [("q", TANGENT.replace("Prove that", "Prove that,"), 3.0)],
        [LexicalIndex(_corpus()), LexicalIndex(_corpus())], judge,
        chapter_of=NAMES.get, unit_of=NAMES.get, section_of=lambda r: None,
        evidence_passages=4, evidence_chapters=1, options=PassOptions(**options),
    )


def test_observing_still_asks_the_judge_and_records_the_agreement():
    judge, log = _Judge(), {}
    out = _run(judge, memory=_memory(), memory_log=log)
    assert len(judge.calls) == 1 and not out.questions[0].memory_reused
    assert log["q"]["reusable"] and not log["q"]["reused"]
    assert log["q"]["judge_chapter"] == "Circles"
    report = summarise(log, 3)
    assert report["reusable"] == 1 and report["agreed_with_judge"] == 1


def test_reuse_skips_the_judge_and_carries_the_confirmed_section_and_tier():
    judge, log = _Judge(), {}
    out = _run(judge, memory=_memory(), memory_reuse=True, memory_log=log)
    q = out.questions[0]
    assert judge.calls == []
    assert q.chapter == "Circles" and q.curriculum_section == "10.2"
    assert q.tier == "Analysing, Evaluating & Creating"
    assert q.memory_reused and q.chapter_judge_skipped and q.confidence > 0.9
    assert log["q"]["reused"]


def test_reuse_is_refused_outside_the_questions_declared_scope():
    judge = _Judge()
    out = place_paper(
        [("q", TANGENT, 3.0)], [LexicalIndex(_corpus()), LexicalIndex(_corpus())], judge,
        chapter_of=NAMES.get, unit_of=NAMES.get, section_of=lambda r: None,
        evidence_passages=4, evidence_chapters=1, scope={"Constructions"},
        options=PassOptions(memory=_memory(), memory_reuse=True),
    )
    assert not out.questions[0].memory_reused


def test_demonstrations_reach_the_judge_only_when_there_are_some():
    judge = _Judge()
    _run(judge, memory=_memory(), memory_demos=2)
    assert judge.calls[0] and judge.calls[0][0].entry.question_id == "a"
    plain = _Judge()
    _run(plain, memory=QuestionMemory([]), memory_demos=2)
    assert plain.calls == [None], "no neighbours: the call carries no examples"


def test_no_memory_is_the_original_pass():
    judge, log = _Judge(), {}
    _run(judge, memory_log=log)
    assert len(judge.calls) == 1 and log == {}


# --- the loader, against the database -----------------------------------------------------


def _confirm(client, school, aid, qno_index=0, section="12.2"):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement

    db = SessionLocal()
    try:
        qid = db.scalars(
            select(Question).where(Question.assessment_id == aid).order_by(Question.address)
        ).all()[qno_index].id
        db.add(QuestionPlacement(question_id=qid, confidence=0.4, source="model", needs_review=True))
        db.commit()
    finally:
        db.close()
    r = client.post(
        f"/assessments/{aid}/review/{qid}", headers={"X-API-Key": school["api_key"]},
        json={"chapter_code": "X.MATH.SAV", "curriculum_section": section, "reviewed_by": "t"},
    )
    assert r.status_code == 200, r.text
    return qid


def test_the_loader_returns_only_what_a_person_confirmed_in_this_school(client, school):
    import uuid

    from app.classify.memory import load_confirmed
    from app.db import SessionLocal

    headers = {"X-API-Key": school["api_key"]}
    tag = uuid.uuid4().hex[:8]
    aid = client.post("/assessments", headers=headers, json={
        "subject_code": "X.MATH", "title": f"Memory {tag}", "total_marks": 4}).json()["assessment_id"]
    assert client.post(f"/assessments/{aid}/questions", headers=headers, json={"questions": [
        {"section": "A", "question_no": "1", "max_marks": 2,
         "stem_text": f"The slant height of a right circular cone {tag}",
         "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
         "concept_variant": f"cone {tag}"},
        {"section": "A", "question_no": "2", "max_marks": 2,
         "stem_text": f"Prove that root 5 is irrational {tag}",
         "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
         "concept_variant": f"irr {tag}"},
    ]}).status_code == 200
    confirmed = _confirm(client, school, aid, 0)

    db = SessionLocal()
    try:
        memory = load_confirmed(db, school_id=school["school_id"], subject_codes=["X.MATH"])
        ids = {e.question_id: e for e in memory.entries}
        assert confirmed in ids
        assert ids[confirmed].chapter == "Surface Areas and Volumes"
        assert ids[confirmed].section == "12.2"
        # the second question was never confirmed, so it is not remembered
        assert not any("irrational" in e.stem and tag in e.stem for e in memory.entries)
        # the paper being placed is excluded, and another school sees nothing of this one
        own = load_confirmed(db, school_id=school["school_id"], subject_codes=["X.MATH"],
                             exclude_assessment=aid)
        assert confirmed not in {e.question_id for e in own.entries}
        other = load_confirmed(db, school_id="no-such-school", subject_codes=["X.MATH"])
        assert len(other) == 0
    finally:
        db.close()


def test_a_confirmed_question_is_reused_end_to_end_with_no_model_call(
    client, school, book, monkeypatch,
):
    """The whole placement job: a near-identical question confirmed on an earlier paper
    takes its chapter, section and topic, and neither judge is asked."""
    import uuid

    from sqlalchemy import select

    from app.api.placement import _run_placement_job
    from app.classify import anthropic_judge as anthropic_judge_module
    from app.classify import topic as topic_module
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import PlacementJob, Question, QuestionPlacement

    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "memory_reuse", True)
    if hasattr(settings, "mapping_v2_subjects"):
        # a deployment that gates new mapping logic per subject must list the subject too
        monkeypatch.setattr(settings, "mapping_v2_subjects", [*settings.mapping_v2_subjects, "X.MATH"])
    headers = {"X-API-Key": school["api_key"]}
    tag = uuid.uuid4().hex[:8]

    def paper(stem, title):
        aid = client.post("/assessments", headers=headers, json={
            "subject_code": "X.MATH", "title": f"{title} {tag}", "total_marks": 3,
        }).json()["assessment_id"]
        added = client.post(f"/assessments/{aid}/questions", headers=headers, json={"questions": [{
            "section": "A", "question_no": "1", "max_marks": 3, "stem_text": stem,
            "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
            "concept_variant": f"{title} {tag}",
        }]})
        assert added.status_code == 200, added.json()
        return aid

    earlier = paper("Find the modal class and hence the mode of the frequency distribution "
                    "given below", "earlier")
    db = SessionLocal()
    try:
        qid = db.scalars(select(Question).where(Question.assessment_id == earlier)).first().id
        db.add(QuestionPlacement(question_id=qid, source="model", needs_review=True))
        db.commit()
    finally:
        db.close()
    r = client.post(f"/assessments/{earlier}/review/{qid}", headers=headers, json={
        "chapter_code": "X.MATH.STATS", "curriculum_section": "13.3", "reviewed_by": "t"})
    assert r.status_code == 200, r.text

    later = paper("Find the Modal Class, and hence the mode, of the frequency distribution "
                  "given below.", "later")

    class Refuses:
        def __init__(self, *a, **kw):
            pass

        def classify(self, *a, **kw):
            raise AssertionError("the chapter judge must not be asked")

        def pick(self, *a, **kw):
            raise AssertionError("the topic judge must not be asked")

    monkeypatch.setattr(anthropic_judge_module, "AnthropicJudge", Refuses)
    monkeypatch.setattr(topic_module, "TopicJudge", Refuses)

    db = SessionLocal()
    try:
        new_q = db.scalars(select(Question).where(Question.assessment_id == later)).first().id
        job = PlacementJob(school_id=school["school_id"], assessment_id=later)
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    _run_placement_job(job_id)

    db = SessionLocal()
    try:
        job = db.get(PlacementJob, job_id)
        assert job.status == "succeeded", job.error_detail
        assert job.result["memory"]["reused"] == 1
        assert job.result["spend"]["calls"] == 0
        assert db.get(Question, new_q).curriculum_section == "13.3"
        placement = db.scalars(
            select(QuestionPlacement).where(QuestionPlacement.question_id == new_q)
            .order_by(QuestionPlacement.created_at.desc())
        ).first()
        assert placement.curriculum_section == "13.3" and not placement.needs_review
    finally:
        db.close()


def test_confirmed_similar_questions_in_another_chapter_veto_the_gate():
    """The retrievers agree on Circles, but this school has confirmed close questions in
    Constructions: the gate does not pass, so the chapter judge reads it."""
    judge, log = _Judge(), {}
    memory = QuestionMemory([
        Remembered("a", TANGENT.replace("Prove that", "Construct"), "Constructions", "11.1"),
    ])
    _run(judge, memory=memory, gate=True, gate_log=log, gate_min_margin=0.0)
    assert not log["q"]["passed"] and "teachers placed similar questions" in log["q"]["reason"]
    assert len(judge.calls) == 1
