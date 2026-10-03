"""Phase 1.3-1.4 (and the format checks of 6.3): one scope rule for map and place, read
from what the paper prints, never from a bare section letter.

Formats covered:
  F1  sections by subject, a chapter named in each header
  F2  board pattern: sections by question type, all four books mixed, nothing named
  F3  a periodic test whose cover lists its syllabus, sections by type
  F4  no usable headers at all
No paid API is called: retrieval and the judges are stubbed.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.classify.question_scope import (
    GROUP,
    SECTION_TITLE,
    SYLLABUS,
    TEACHER,
    PaperScope,
)
from app.config import get_settings

SST = ["X.HIST", "X.GEO", "X.POL", "X.ECO"]
ALIASES = {"X.ECO.GLOBALISATION": ["Globalisation"], "X.GEO.MINERALSENERGY": ["Minerals"]}
ALL_GEO = {
    "X.GEO.RESOURCES", "X.GEO.FORESTWILDLIFE", "X.GEO.WATER", "X.GEO.AGRICULTURE",
    "X.GEO.MINERALSENERGY", "X.GEO.MANUFACTURING", "X.GEO.LIFELINES",
}


def _scope(declared=None, teacher=None):
    return PaperScope(SST, teacher_scope=teacher, declared=declared, aliases=ALIASES)


# --- the rule itself, per format ----------------------------------------------------------


def test_f1_a_section_title_naming_a_chapter_scopes_to_that_chapter():
    scope = _scope({"section_titles": {
        "A": "History : Print Culture and the Modern World",
        "B": "Geography : Minerals and Energy Resources",
        "C": "Political Science : Political Parties",
        "D": "Economics : Globalisation and the Indian Economy",
    }})
    assert scope.for_section("A").chapter_codes == {"X.HIST.PRINTCULTURE"}
    assert scope.for_section("b").chapter_codes == {"X.GEO.MINERALSENERGY"}
    assert scope.for_section("C").single_chapter == "X.POL.PARTIES"
    assert scope.for_section("D").source == SECTION_TITLE
    # a section the paper printed no title for falls back to the whole group
    assert scope.for_section("E").chapter_codes is None


def test_f1_a_subject_only_title_scopes_to_every_chapter_of_that_subject():
    scope = _scope({"section_titles": {"B": "Geography"}})
    decision = scope.for_section("B")
    assert decision.chapter_codes == ALL_GEO and decision.source == SECTION_TITLE


@pytest.mark.parametrize("titles", [
    {"A": "Multiple Choice Questions", "B": "Very Short Answer Questions",
     "C": "Short Answer Questions", "D": "Long Answer Questions",
     "E": "Case Based Questions", "F": "Map Skill Based Question"},
    {},
])
def test_f2_and_f4_a_type_title_or_no_title_never_narrows_by_letter(titles):
    """A board paper's Section A is MCQs from all four books; it must never be History."""
    scope = _scope({"section_titles": titles} if titles else None)
    for letter in "ABCDEF":
        decision = scope.for_section(letter)
        assert decision.chapter_codes is None and decision.source == GROUP
    assert scope.for_section(None).chapter_codes is None


def test_f2_a_bilingual_type_title_never_narrows():
    scope = _scope({"section_titles": {"A": "बहुविकल्पीय प्रश्न / Multiple Choice Questions"}})
    assert scope.for_section("A").chapter_codes is None


def test_a_bilingual_subject_title_resolves():
    scope = _scope({"section_titles": {"B": "खंड ख — भूगोल / Geography"}})
    assert scope.for_section("B").chapter_codes == ALL_GEO


def test_f3_syllabus_lines_scope_every_question_when_sections_are_by_type():
    scope = _scope({
        "section_titles": {"A": "MCQs", "B": "Short Answer"},
        "syllabus_lines": ["Syllabus: History Ch 1-2", "Geography Ch 1, 3"],
    })
    expected = {"X.HIST.NATIONALISM_EUROPE", "X.HIST.NATIONALISM_INDIA",
                "X.GEO.RESOURCES", "X.GEO.WATER"}
    for letter in ("A", "B", None):
        decision = scope.for_section(letter)
        assert decision.chapter_codes == expected and decision.source == SYLLABUS
    assert scope.paper_level().chapter_codes == expected


def test_a_section_title_narrows_within_the_syllabus():
    scope = _scope({
        "section_titles": {"B": "Geography"},
        "syllabus_lines": ["History Ch 1, Geography Ch 3"],
    })
    assert scope.for_section("B").chapter_codes == {"X.GEO.WATER"}
    assert scope.for_section("A").chapter_codes == {"X.HIST.NATIONALISM_EUROPE", "X.GEO.WATER"}


def test_a_section_title_outranks_a_syllabus_line_that_does_not_list_it():
    scope = _scope({
        "section_titles": {"B": "Geography : Minerals and Energy Resources"},
        "syllabus_lines": ["History Ch 1"],
    })
    assert scope.for_section("B").chapter_codes == {"X.GEO.MINERALSENERGY"}


def test_the_teacher_scope_is_never_overruled_only_narrowed():
    teacher = ["X.GEO.MINERALSENERGY", "X.POL.PARTIES"]
    scope = _scope({"section_titles": {
        "B": "Geography", "C": "Economics : Globalisation and the Indian Economy",
    }}, teacher=teacher)
    assert scope.for_section("B").chapter_codes == {"X.GEO.MINERALSENERGY"}
    # a header naming a chapter outside the teacher's scope does not widen it
    decision = scope.for_section("C")
    assert decision.chapter_codes == set(teacher) and decision.source == TEACHER
    assert scope.for_section(None).chapter_codes == set(teacher)


def test_a_teacher_scope_outside_the_group_is_ignored():
    scope = _scope(teacher=["X.MATH.STATS"])
    assert scope.paper_level().chapter_codes is None


def test_an_unclear_title_leaves_the_scope_to_the_next_source():
    scope = _scope({
        "section_titles": {"A": "Print"},              # below the threshold
        "syllabus_lines": ["Economics Ch 4"],
    })
    assert scope.for_section("A").chapter_codes == {"X.ECO.GLOBALISATION"}
    assert scope.for_section("A").source == SYLLABUS


def test_the_old_declared_shape_is_still_read():
    """A paper scanned before the flag has only {"sections": {letter: marks}}."""
    scope = _scope({"sections": {"A": 20.0, "B": 20.0}, "total_marks": 80})
    assert scope.for_section("A").chapter_codes is None


# --- the rule reaches map and place -------------------------------------------------------

CHAPTERS = {
    "X.HIST.PRINTCULTURE": "printing press manuscripts readers",
    "X.HIST.NATIONALISM_EUROPE": "nation state unification europe",
    "X.GEO.MINERALSENERGY": "iron ore coal petroleum minerals",
    "X.GEO.RESOURCES": "soil resource planning land",
    "X.POL.PARTIES": "political party election functions",
    "X.ECO.GLOBALISATION": "multinational corporations foreign trade",
}


@pytest.fixture
def sst_world(school):
    from app.curriculum import X_ECONOMICS, X_GEOGRAPHY, X_HISTORY, X_POLITICAL_SCIENCE
    from app.curriculum.apply import apply as apply_curriculum
    from app.db import SessionLocal
    from app.models import BookChunk, TaxonomyNode

    db = SessionLocal()
    for curriculum in (X_HISTORY, X_GEOGRAPHY, X_POLITICAL_SCIENCE, X_ECONOMICS):
        apply_curriculum(db, curriculum)
    db.commit()
    for code, text in CHAPTERS.items():
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
        tag = f"scope-test-{code}"
        if db.scalar(select(BookChunk).where(BookChunk.stem_hash == tag)) is None:
            db.add(BookChunk(
                curriculum_version=chapter.curriculum_version, subject_code=code[:code.rindex(".")],
                node_id=chapter.id, bucket="T", reference="1 Test", text=f"{text} body text",
                section_number="1", normalised=f"{text} body text", stem_hash=tag,
            ))
        family = f"{code}.CF.SCOPE_TEST"
        if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == family)) is None:
            db.add(TaxonomyNode(kind="concept_family", code=family, label=f"{code} family",
                                parent_id=chapter.id, path=family,
                                curriculum_version=chapter.curriculum_version))
    db.commit()
    db.close()


def _auth(school):
    return {"X-API-Key": school["api_key"]}


ROWS = [
    ("A", "1", "History question stem, section A."),
    ("B", "2", "Geography question stem, section B."),
    ("C", "3", "Political science question stem, section C."),
    ("D", "4", "Economics question stem, section D."),
    (None, "5", "No section printed at all on this one."),
]


def _sst_paper(client, school, declared):
    from app.db import SessionLocal
    from app.models import Assessment, ScannedQuestion

    h = _auth(school)
    aid = client.post("/assessments", headers=h, json={
        "subject_code": "X.SST", "title": f"Scope {uuid.uuid4().hex[:6]}", "total_marks": 5,
    }).json()["assessment_id"]
    db = SessionLocal()
    db.get(Assessment, aid).declared = declared
    for section, qno, stem in ROWS:
        db.add(ScannedQuestion(
            assessment_id=aid, address=f"{section or ''}/{qno}//", section=section,
            question_no=qno, max_marks=1, stem_text=stem, logical_page=1,
        ))
    db.commit()
    db.close()
    assert client.post(f"/assessments/{aid}/scan/confirm", headers=h, json={}).status_code == 200
    return aid


def _map_capturing_scope(client, school, aid, monkeypatch):
    """Run the map step with locate() recording which chapters each row could reach."""
    import app.ingest.probe as probe
    from app.db import SessionLocal
    from app.ingest.probe import ChapterVerdict
    from app.models import TaxonomyNode

    db = SessionLocal()
    code_of = {n.id: n.code for n in db.scalars(select(TaxonomyNode))}
    db.close()
    captured: dict[str, set[str]] = {}

    def fake_locate(query, indexes, **kwargs):
        captured[query] = {
            code_of[chunk.node_id] for idx in indexes for chunk in getattr(idx, "chunks", [])
        } & set(CHAPTERS)
        return ChapterVerdict(None, 0.0, 0.0, False, [], [])

    monkeypatch.setattr(probe, "locate", fake_locate)
    h = _auth(school)
    out = client.post(f"/assessments/{aid}/map", headers=h)
    if out.status_code == 202:
        client.get(f"/assessments/{aid}/map/jobs/{out.json()['job_id']}", headers=h)
    return captured


def test_map_with_the_flag_on_reads_section_titles_not_letters(client, school, sst_world, monkeypatch):
    monkeypatch.setattr(get_settings(), "sst_unified_scope", True)
    aid = _sst_paper(client, school, {"section_titles": {
        "A": "Geography : Minerals and Energy Resources",   # deliberately not History
        "B": "Multiple Choice Questions",
        "C": "Political Science",
    }})
    captured = _map_capturing_scope(client, school, aid, monkeypatch)
    every = set(CHAPTERS)
    assert captured["History question stem, section A."] == {"X.GEO.MINERALSENERGY"}
    assert captured["Geography question stem, section B."] == every, "a type title narrows nothing"
    assert captured["Political science question stem, section C."] == {"X.POL.PARTIES"}
    assert captured["Economics question stem, section D."] == every, "a bare letter means nothing"
    assert captured["No section printed at all on this one."] == every


def test_map_with_the_flag_on_never_forces_a_board_section_a_into_history(
    client, school, sst_world, monkeypatch,
):
    monkeypatch.setattr(get_settings(), "sst_unified_scope", True)
    aid = _sst_paper(client, school, None)
    captured = _map_capturing_scope(client, school, aid, monkeypatch)
    assert captured["History question stem, section A."] == set(CHAPTERS)


def test_map_with_the_flag_off_keeps_the_letter_convention(client, school, sst_world, monkeypatch):
    monkeypatch.setattr(get_settings(), "sst_unified_scope", False)
    aid = _sst_paper(client, school, {"section_titles": {"A": "Economics"}})
    captured = _map_capturing_scope(client, school, aid, monkeypatch)
    assert captured["History question stem, section A."] == {
        "X.HIST.PRINTCULTURE", "X.HIST.NATIONALISM_EUROPE",
    }


def test_map_with_the_flag_on_honours_the_teacher_scope(client, school, sst_world, monkeypatch):
    from app.db import SessionLocal
    from app.models import Assessment

    monkeypatch.setattr(get_settings(), "sst_unified_scope", True)
    aid = _sst_paper(client, school, {"section_titles": {"B": "Geography"}})
    db = SessionLocal()
    db.get(Assessment, aid).syllabus_scope = ["X.GEO.RESOURCES", "X.POL.PARTIES"]
    db.commit()
    db.close()
    captured = _map_capturing_scope(client, school, aid, monkeypatch)
    assert captured["Geography question stem, section B."] == {"X.GEO.RESOURCES"}
    assert captured["History question stem, section A."] == {"X.GEO.RESOURCES", "X.POL.PARTIES"}


#: words each place-job stem carries, so stub retrieval has something to find
PLACE_WORDS = {
    "A": "printing press manuscripts readers",
    "B": "coal minerals iron ore political party election",
    "C": "political party election functions",
    "D": "multinational corporations foreign trade",
    None: "nation state unification europe",
}


def _placed_paper(school, declared):
    """An X.SST assessment with question rows already written, as map leaves them."""
    from app.db import SessionLocal
    from app.models import Assessment, Question, TaxonomyNode
    from app.taxonomy.variants import variant_hash

    db = SessionLocal()
    a = Assessment(school_id=school["school_id"], subject_code="X.SST",
                   title=f"Place scope {uuid.uuid4().hex[:6]}", declared=declared)
    db.add(a)
    db.flush()
    unit = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.HIST.U.WHOLE"))
    family = db.scalar(select(TaxonomyNode).where(
        TaxonomyNode.code == "X.HIST.PRINTCULTURE.CF.SCOPE_TEST"))
    ids = {}
    for section, qno, stem in ROWS:
        variant = f"{stem} {uuid.uuid4().hex}"
        q = Question(
            assessment_id=a.id, address=f"{section or ''}/{qno}//", section=section,
            question_no=qno, max_marks=1, stem_text=f"{stem} {PLACE_WORDS[section]}",
            board_unit_id=unit.id,
            concept_family_id=family.id, concept_variant=variant[:200],
            variant_hash=variant_hash(variant[:200]),
        )
        db.add(q)
        db.flush()
        ids[stem] = q.id
    db.commit()
    aid = a.id
    db.close()
    return aid, ids


def _place_capturing_scope(school, aid, monkeypatch):
    import app.api.placement as placement
    from app.api.placement import _run_placement_job
    from app.classify.pipeline import PaperPlacement
    from app.db import SessionLocal
    from app.models import PlacementJob

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    seen: dict = {}

    def fake_place_paper(stems, indexes, judge, **kwargs):
        seen["scope"] = kwargs.get("scope")
        seen["scope_of"] = {qid: kwargs["scope_of"](qid) for qid, _, _ in stems}
        return PaperPlacement([], True, "", {}, 0)

    monkeypatch.setattr(placement, "place_paper", fake_place_paper)
    db = SessionLocal()
    job = PlacementJob(school_id=school["school_id"], assessment_id=aid)
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()
    _run_placement_job(job_id)
    return seen


def test_place_with_the_flag_on_scopes_each_question_by_its_title(school, sst_world, monkeypatch):
    monkeypatch.setattr(get_settings(), "sst_unified_scope", True)
    aid, ids = _placed_paper(school, {"section_titles": {
        "A": "Short Answer Questions", "B": "Geography : Minerals and Energy Resources",
    }})
    seen = _place_capturing_scope(school, aid, monkeypatch)
    assert seen["scope"] is None, "nothing paper-wide was declared, so inference may run"
    assert seen["scope_of"][ids["Geography question stem, section B."]] == {
        "Minerals and Energy Resources"}
    assert seen["scope_of"][ids["History question stem, section A."]] is None


def test_place_with_the_flag_on_passes_syllabus_lines_as_the_paper_scope(
    school, sst_world, monkeypatch,
):
    monkeypatch.setattr(get_settings(), "sst_unified_scope", True)
    aid, ids = _placed_paper(school, {"syllabus_lines": ["Political Science Ch 4, Economics Ch 4"]})
    seen = _place_capturing_scope(school, aid, monkeypatch)
    expected = {"Political Parties", "Globalisation and the Indian Economy"}
    assert seen["scope"] == expected
    assert all(v == expected for v in seen["scope_of"].values())


def test_place_with_the_flag_off_keeps_the_letter_convention(school, sst_world, monkeypatch):
    monkeypatch.setattr(get_settings(), "sst_unified_scope", False)
    aid, ids = _placed_paper(school, {"section_titles": {"A": "Economics"}})
    seen = _place_capturing_scope(school, aid, monkeypatch)
    history = seen["scope_of"][ids["History question stem, section A."]]
    assert "Print Culture and the Modern World" in history
    assert "Globalisation and the Indian Economy" not in history


# --- 1.6-1.7 through the place job -----------------------------------------------------------


def _stub_judges(monkeypatch, *, answerable_unless=None, wide_chapter="Political Parties"):
    """Chapter and topic judges that answer from fixed rules and record what they saw."""
    import app.classify.anthropic_judge as anthropic_judge_module
    import app.classify.topic as topic_module
    from app.classify.judge import Classification

    seen = {"chapter": [], "topic": []}

    class ChapterJudge:
        batched = False
        calls = input_tokens = output_tokens = cache_read_tokens = 0

        def __init__(self, *a, **kw):
            pass

        def classify(self, question, evidence, **kw):
            seen["chapter"].append((question, {e.chapter for e in evidence}))
            chapters = {e.chapter for e in evidence}
            chapter = wide_chapter if wide_chapter in chapters else sorted(chapters)[0]
            return Classification(chapter=chapter, tier="Applying", skill_required="x",
                                  reasoning="stub", confidence=0.9)

    class TopicJudge:
        batched = False
        calls = input_tokens = output_tokens = cache_read_tokens = 0

        def __init__(self, *a, **kw):
            pass

        def pick_from_document(self, stem, chapter_label, headings, document, candidates=None,
                               mode="answer", exclude=None, with_tier=False):
            seen["topic"].append((stem, chapter_label, mode, with_tier))

            class C:
                pass

            c = C()
            c.section = "none" if exclude else next(iter(headings))
            c.quote, c.rationale, c.answer, c.quotes, c.also = "", "stub", "", [], []
            c.tier = "Remembering & Understanding" if with_tier else None
            return c

        def answerable(self, stem, chapter_label, headings, document, section, sub_sections=None):
            class V:
                pass

            v = V()
            ok = not (answerable_unless and answerable_unless in stem)
            v.answerable, v.reason = ok, "stub"
            v.quotes = [document.split("\n")[1]] if ok else []
            return v

    monkeypatch.setattr(anthropic_judge_module, "AnthropicJudge", ChapterJudge)
    monkeypatch.setattr(topic_module, "TopicJudge", TopicJudge)
    return seen


def _run_place(school, aid, monkeypatch):
    from app.api.placement import _run_placement_job
    from app.db import SessionLocal
    from app.models import PlacementJob

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    db = SessionLocal()
    job = PlacementJob(school_id=school["school_id"], assessment_id=aid)
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()
    _run_placement_job(job_id)
    db = SessionLocal()
    try:
        return db.get(PlacementJob, job_id)
    finally:
        db.close()


def _latest(model, question_id):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        return db.scalars(select(model).where(model.question_id == question_id)
                          .order_by(model.created_at.desc())).first()
    finally:
        db.close()


TITLED = {"section_titles": {
    "A": "History : Print Culture and the Modern World",
    "B": "Geography : Minerals and Energy Resources",
    "C": "Political Science : Political Parties",
    "D": "Economics : Globalisation and the Indian Economy",
}}


def test_place_skips_the_chapter_judge_for_a_single_chapter_and_takes_the_topic_judges_tier(
    school, sst_world, monkeypatch,
):
    from app.models import QuestionPlacement, QuestionTier

    for flag in ("sst_unified_scope", "skip_single_chapter_judge"):
        monkeypatch.setattr(get_settings(), flag, True)
    seen = _stub_judges(monkeypatch)
    aid, ids = _placed_paper(school, TITLED)
    job = _run_place(school, aid, monkeypatch)
    assert job.status == "succeeded", job.error_detail

    judged_stems = {stem.split(".")[0] for stem, _ in seen["chapter"]}
    assert judged_stems == {"No section printed at all on this one"}, (
        "only the question with no single-chapter scope reaches the chapter judge")
    geo = ids["Geography question stem, section B."]
    placement = _latest(QuestionPlacement, geo)
    assert placement.source == "scope" and not placement.needs_review
    assert placement.tier == "Remembering & Understanding"
    assert _latest(QuestionTier, geo).tier == "R&U"
    tiered = [t for t in seen["topic"] if t[0].startswith("Geography") and t[2] == "answer"]
    assert tiered and tiered[0][3] is True
    assert job.result["spend"]["calls"] >= 0


def test_place_moves_an_unanswerable_single_chapter_question_out_of_scope_and_says_so(
    school, sst_world, monkeypatch,
):
    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement, TaxonomyNode

    for flag in ("sst_unified_scope", "skip_single_chapter_judge", "cross_scope_fallback"):
        monkeypatch.setattr(get_settings(), flag, True)
    seen = _stub_judges(monkeypatch, answerable_unless="Geography")
    aid, ids = _placed_paper(school, TITLED)
    job = _run_place(school, aid, monkeypatch)
    assert job.status == "succeeded", job.error_detail

    geo = ids["Geography question stem, section B."]
    placement = _latest(QuestionPlacement, geo)
    assert placement.cross_scope is True and placement.review_reason == "cross_scope"
    assert placement.needs_review
    db = SessionLocal()
    parties = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.POL.PARTIES"))
    assert placement.chapter_id == parties.id
    assert db.get(Question, geo).chapter_id == parties.id
    db.close()
    # the re-read searched the whole Social Science group, nothing else
    wide = [shown for stem, shown in seen["chapter"] if stem.startswith("Geography")]
    assert wide and all(
        label in {"Print Culture and the Modern World", "The Rise of Nationalism in Europe",
                  "Minerals and Energy Resources", "Resources and Development",
                  "Political Parties", "Globalisation and the Indian Economy"}
        for label in wide[0]
    )
    # every other single-chapter question stayed where its title put it, unflagged
    other = _latest(QuestionPlacement, ids["Political science question stem, section C."])
    assert not other.cross_scope and not other.needs_review


def test_place_with_every_new_flag_off_writes_no_new_columns(school, sst_world, monkeypatch):
    from app.models import QuestionPlacement

    seen = _stub_judges(monkeypatch)
    aid, ids = _placed_paper(school, TITLED)
    job = _run_place(school, aid, monkeypatch)
    assert job.status == "succeeded", job.error_detail
    assert len(seen["chapter"]) == len(ROWS), "every question went to the chapter judge"
    for qid in ids.values():
        row = _latest(QuestionPlacement, qid)
        assert row.cross_scope is None and row.review_reason is None and row.source == "model"
