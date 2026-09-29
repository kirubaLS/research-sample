"""The topic within a chapter: a closed-set choice, checked against retrieval.

Before this, the Topic column was retrieval's section guess from map time, and nothing
later -- not the judge naming the right section in its reasoning, not a teacher settling
the row -- ever changed it. These tests pin down the three things that fix that: the
topic judge answers only from the chapter's own sections, its disagreement with retrieval
is what flags a row, and both classify and review write the topic the column reads.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import select

from app.classify.topic import TopicPick, choose_topic, normalise_section
from app.mapping.family import choose_family


@dataclass
class _Chunk:
    id: str
    reference: str
    node_id: str
    text: str
    section_number: str | None
    bucket: str = "T"
    embedding: list | None = None


STATS = "chapter-stats"
CHUNKS = [
    _Chunk("c1", "13.1 Introduction", STATS, "Statistics deals with data collected from "
           "a survey and its presentation in tables.", "13.1"),
    _Chunk("c2", "13.2 Mean of Grouped Data", STATS, "The mean of grouped data by the "
           "step-deviation method uses an assumed mean and a class size.", "13.2"),
    _Chunk("c3", "13.3 Mode of Grouped Data", STATS, "The modal class is the class with "
           "the greatest frequency and the mode is found from the frequencies either side.",
           "13.3"),
    _Chunk("c4", "13.4 Median of Grouped Data", STATS, "The median class is found from "
           "the cumulative frequency and the median from the formula.", "13.4"),
    _Chunk("c9", "Exercise", "chapter-other", "Find the mode of the data.", "9.1"),
]
HEADINGS = {
    "13.1": "Introduction", "13.2": "Mean of Grouped Data",
    "13.3": "Mode of Grouped Data", "13.4": "Median of Grouped Data",
}


class _Judge:
    def __init__(self, answer, *, raises=False):
        self.answer, self.raises, self.prompts = answer, raises, []

    def pick(self, stem, chapter_label, headings, passages):
        self.prompts.append((stem, chapter_label, dict(headings), list(passages)))
        if self.raises:
            raise RuntimeError("network")

        class _Choice:
            section = self.answer
            rationale = "because"

        return _Choice()


# --- the answer is one of the chapter's sections, however the model spells it ---------

@pytest.mark.parametrize("answer, expected", [
    ("13.3", "13.3"), ("13.3.", "13.3"), ("section 13.3", "13.3"),
    ("13.3 Mode of Grouped Data", "13.3"), ("Mode of Grouped Data", "13.3"),
    ("none", None), ("", None), ("14.1", None), ("13", None),
])
def test_a_section_answer_is_read_only_as_a_listed_section(answer, expected):
    assert normalise_section(answer, HEADINGS) == expected


# --- the judge sees every section and decides; retrieval is the check ----------------

def test_the_judge_is_shown_every_section_of_the_chapter_and_its_answer_wins():
    judge = _Judge("13.3")
    pick = choose_topic(
        "Find the modal class and hence the mode of the frequency distribution", STATS, "Statistics", CHUNKS,
        HEADINGS, judge,
    )
    assert pick == TopicPick("13.3", "Mode of Grouped Data", "judge", True, "13.3", "because")
    [(_, _, headings, passages)] = judge.prompts
    assert headings == HEADINGS
    assert {p.section for p in passages} == {"13.1", "13.2", "13.3", "13.4"}, (
        "inclusion is earned by being a real section, not by winning a word-overlap contest"
    )
    assert all(p.node_id == STATS for p in passages), "never another chapter's text"


def test_disagreement_with_retrieval_is_what_flags_a_row():
    """Retrieval reads 'mode' and says 13.3; the judge, reading the question, says 13.2.
    The judge's answer stands, and the row is flagged with both named."""
    pick = choose_topic(
        "Find the modal class and hence the mode of the frequency distribution", STATS, "Statistics", CHUNKS,
        HEADINGS, _Judge("13.2"),
    )
    assert pick.section == "13.2" and pick.source == "judge"
    assert pick.retrieval_section == "13.3"
    assert not pick.agreed
    assert "13.3" in pick.rationale and "Mode of Grouped Data" in pick.rationale


def test_a_parent_and_its_sub_section_are_not_a_disagreement():
    chunks = CHUNKS + [_Chunk("c0", "13 Statistics", STATS, "Grouped data: mean, mode "
                              "and median of grouped data.", "13")]
    headings = {"13": "Statistics", **HEADINGS}
    pick = choose_topic(
        "Find the modal class and hence the mode of the frequency distribution", STATS, "Statistics", chunks,
        headings, _Judge("13"),
    )
    assert pick.section == "13" and pick.agreed


@pytest.mark.parametrize("judge", [None, _Judge("none"), _Judge("14.7"), _Judge("x", raises=True)])
def test_without_a_usable_judge_answer_the_chapters_own_passages_decide(judge):
    """An abstention, an invented section, a failed call or no judge at all -- retrieval
    within the chapter decides, and the row is flagged because nobody read it."""
    pick = choose_topic(
        "Find the modal class and hence the mode of the frequency distribution", STATS, "Statistics", CHUNKS,
        HEADINGS, judge,
    )
    assert pick.section == "13.3" and pick.source == "retrieval" and not pick.agreed


def test_the_chapter_judges_own_section_outranks_retrieval_when_the_topic_judge_abstains():
    """A model that read the passages named 13.2; word overlap says 13.3. The model's
    section stands, and the row is still flagged because the two disagree."""
    stem = "Find the modal class and hence the mode of the frequency distribution"
    pick = choose_topic(stem, STATS, "Statistics", CHUNKS, HEADINGS, _Judge("none"),
                        fallback_section="13.2")
    assert pick.section == "13.2" and pick.source == "chapter_judge"
    assert pick.retrieval_section == "13.3" and not pick.agreed

    pick = choose_topic(stem, STATS, "Statistics", CHUNKS, HEADINGS, _Judge("none"),
                        fallback_section="13.3")
    assert pick.section == "13.3" and pick.source == "chapter_judge" and pick.agreed

    # a section the chapter does not have is not a fallback
    pick = choose_topic(stem, STATS, "Statistics", CHUNKS, HEADINGS, _Judge("none"),
                        fallback_section="14.1")
    assert pick.section == "13.3" and pick.source == "retrieval"


def test_a_chapter_without_section_text_has_no_topic():
    pick = choose_topic("anything", "chapter-none", "Nowhere", CHUNKS, HEADINGS, _Judge("13.3"))
    assert pick.section is None and pick.source == "none"


# --- families that share a section: the heading breaks the tie ------------------------

@dataclass(frozen=True)
class _Family:
    code: str
    label: str


def test_of_several_families_claiming_a_section_the_one_named_for_it_wins():
    reform = _Family("POL.CF.REFORM", "How can parties be reformed?")
    national = _Family("POL.CF.NATIONAL", "National parties")
    challenges = _Family("POL.CF.CHALLENGES", "Challenges to political parties")
    sections = {"POL.CF.REFORM": {"6"}, "POL.CF.NATIONAL": {"3", "6"},
                "POL.CF.CHALLENGES": {"5", "6"}}
    choice = choose_family(
        [national, challenges, reform], sections, "6", "Political Parties",
        prefer_label="6 How can parties be reformed?",
    )
    assert choice.family is reform and choice.unsettled is None

    # Without the heading the old rule still applies -- narrowest, and a person looks.
    choice = choose_family([national, challenges, reform], sections, "6", "Political Parties")
    assert choice.family is reform and choice.unsettled is not None


# --- end to end: classify and review both write the topic the column reads ----------

def _auth(school):
    return {"X-API-Key": school["api_key"]}


def _topic_for(db, question_id):
    from app.models import QuestionSkill, TaxonomyNode

    rows = list(db.scalars(select(QuestionSkill).where(QuestionSkill.question_id == question_id)))
    return sorted((db.get(TaxonomyNode, r.node_id).label, r.source) for r in rows)


def test_classify_writes_the_judged_topic_and_review_overwrites_it(
    client, school, book, monkeypatch,
):
    from app.api.placement import _run_placement_job
    from app.classify import anthropic_judge as anthropic_judge_module
    from app.classify import topic as topic_module
    from app.classify.judge import Classification
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import PlacementJob, Question, QuestionPlacement

    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    created = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Topic test", "total_marks": 3},
    )
    aid = created.json()["assessment_id"]
    added = client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [{
            "section": "A", "question_no": "1", "max_marks": 3,
            # Word overlap points at the MODE chunk; the stub judge below reads it as
            # the mean, so the two disagree and the row must be flagged.
            "stem_text": "Find the modal class and hence the mode of the frequency distribution",
            "board_unit": "X.MATH.U.MENSURATION",
            "concept_family": "X.MATH.CF.VOLUME",
            "concept_variant": "topic fixture",
        }]},
    )
    assert added.status_code == 200, added.json()

    class StubJudge:
        def classify(self, question, evidence):
            return Classification(
                chapter="Statistics", curriculum_section="13.3", tier="Applying",
                skill_required="compute a mean", reasoning="asks for the mean",
                confidence=0.9,
            )

    class StubTopicJudge:
        def __init__(self, *a, **kw):
            pass

        def pick(self, stem, chapter_label, headings, passages):
            assert chapter_label == "Statistics"
            assert set(headings) >= {"13.2", "13.3"}

            class _Choice:
                section = "13.2"
                rationale = "the question asks for the mean by step-deviation"

            return _Choice()

    monkeypatch.setattr(anthropic_judge_module, "AnthropicJudge", lambda *a, **kw: StubJudge())
    monkeypatch.setattr(topic_module, "TopicJudge", StubTopicJudge)

    db = SessionLocal()
    try:
        qid = db.scalars(select(Question).where(Question.assessment_id == aid)).first().id
        job = PlacementJob(school_id=school["school_id"], assessment_id=aid)
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
        q = db.get(Question, qid)
        assert q.curriculum_section == "13.2", "the topic judge's section, not the chapter judge's"
        assert _topic_for(db, qid) == [("Mean of Grouped Data", "classify")], (
            "the Topic column reads QuestionSkill, so the decided section must be there"
        )
        placement = db.scalars(
            select(QuestionPlacement).where(QuestionPlacement.question_id == qid)
            .order_by(QuestionPlacement.created_at.desc())
        ).first()
        assert placement.curriculum_section == "13.2"
        assert placement.needs_review, "retrieval said 13.3 -- a real disagreement, flagged"
        assert "Topic 13.2 (Mean of Grouped Data)" in placement.reasoning
        assert "pointed at section 13.3" in placement.reasoning
    finally:
        db.close()

    # A person settles it to the mode section: the topic follows.
    r = client.post(
        f"/assessments/{aid}/review/{qid}", headers=_auth(school),
        json={"chapter_code": "X.MATH.STATS", "curriculum_section": "13.3",
              "reviewed_by": "kingshuk"},
    )
    assert r.status_code == 200, r.json()
    db = SessionLocal()
    try:
        assert _topic_for(db, qid) == [("Mode of Grouped Data", "human")]
    finally:
        db.close()


def test_a_sub_question_is_judged_together_with_its_passage(client, school, book, monkeypatch):
    """'State one way public libraries widened access' names nothing the book can find;
    the passage it sits under does. The judge reads both."""
    from app.api.placement import _run_placement_job
    from app.classify import anthropic_judge as anthropic_judge_module
    from app.classify import topic as topic_module
    from app.classify.judge import Classification
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import PlacementJob, Question, ScannedQuestion

    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    created = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Passage test", "total_marks": 1},
    )
    aid = created.json()["assessment_id"]
    added = client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [{
            "section": "A", "question_no": "7", "sub_part": "1", "max_marks": 1,
            "stem_text": "State the method used.",
            "board_unit": "X.MATH.U.MENSURATION",
            "concept_family": "X.MATH.CF.VOLUME",
            "concept_variant": "passage sub-part",
        }]},
    )
    assert added.status_code == 200, added.json()
    passage = (
        "Read the source: the mean of grouped data by the step-deviation method uses an "
        "assumed mean and a common class size."
    )
    db = SessionLocal()
    try:
        q = db.scalars(select(Question).where(Question.assessment_id == aid)).first()
        qid = q.id
        # the scanned rows: the passage (no sub_part) and the sub-question under it
        db.add(ScannedQuestion(
            assessment_id=aid, address="A/7", section="A", question_no="7", sub_part=None,
            stem_text=passage,
        ))
        db.add(ScannedQuestion(
            assessment_id=aid, address=q.address, section="A", question_no="7", sub_part="1",
            stem_text=q.stem_text,
        ))
        job = PlacementJob(school_id=school["school_id"], assessment_id=aid)
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    seen: dict[str, str] = {}

    class StubJudge:
        def classify(self, question, evidence):
            seen["judge"] = question
            return Classification(
                chapter="Statistics", tier="Applying", skill_required="name a method",
                reasoning="the passage is about the mean", confidence=0.9,
            )

    class StubTopicJudge:
        def __init__(self, *a, **kw):
            pass

        def pick(self, stem, chapter_label, headings, passages):
            seen["topic"] = stem

            class _Choice:
                section = "13.2"
                rationale = "step-deviation is the mean"

            return _Choice()

    monkeypatch.setattr(anthropic_judge_module, "AnthropicJudge", lambda *a, **kw: StubJudge())
    monkeypatch.setattr(topic_module, "TopicJudge", StubTopicJudge)
    _run_placement_job(job_id)

    assert seen["judge"].startswith(passage) and "State the method used." in seen["judge"]
    assert seen["topic"].startswith(passage)
    db = SessionLocal()
    try:
        job = db.get(PlacementJob, job_id)
        assert job.status == "succeeded", job.error_detail
        q = db.get(Question, qid)
        assert q.stem_text == "State the method used.", "the stored stem is never rewritten"
        assert q.curriculum_section == "13.2"
        assert _topic_for(db, qid) == [("Mean of Grouped Data", "classify")]
    finally:
        db.close()


# --- a paper section is its own subject: the other books are never candidates ---------

def test_a_questions_own_scope_keeps_the_other_subjects_chapters_out():
    """A Geography question about aluminium in Odisha reads well against Manufacturing
    Industries too. With its section's scope, that chapter is never offered."""
    from app.classify.judge import Classification
    from app.classify.pipeline import place_paper
    from app.ingest.probe import LexicalIndex

    bauxite = _Chunk("b", "2.3.2 Bauxite", "minerals", "Bauxite deposits in Odisha are "
                     "the raw material of aluminium; the Panchpatmali deposits are the "
                     "most important bauxite deposits.", "2.3.2")
    smelting = _Chunk("s", "3.2 Aluminium Smelting", "industries", "Aluminium smelting "
                      "plants are located in Odisha where bauxite and electricity are "
                      "available; aluminium smelting is the second most important "
                      "metallurgical industry.", "3.2")
    padding = [_Chunk(f"p{i}", f"p{i}", "other", f"unrelated teaching text {i}", "1.1")
               for i in range(6)]
    pool = [bauxite, smelting, *padding]
    chapter_of = {"minerals": "Minerals and Energy Resources",
                  "industries": "Manufacturing Industries", "other": "Other"}.get
    offered: list[set[str]] = []

    class Judge:
        def classify(self, question, evidence):
            chapters = {e.chapter for e in evidence}
            offered.append(chapters)
            chapter = "Manufacturing Industries" if "Manufacturing Industries" in chapters \
                else "Minerals and Energy Resources"
            return Classification(chapter=chapter, tier="Applying", skill_required="x",
                                  reasoning="y", confidence=0.9)

    stem = "Why would Odisha suit an aluminium industry using bauxite?"
    free = place_paper(
        [("q1", stem, 5.0)], [LexicalIndex(pool)], Judge(), chapter_of=chapter_of,
        unit_of=lambda c: "U", section_of=lambda r: None, infer_scope_when_undeclared=False,
    )
    assert "Manufacturing Industries" in offered[0]
    assert free.questions[0].chapter == "Manufacturing Industries"

    scoped = place_paper(
        [("q1", stem, 5.0)], [LexicalIndex(pool)], Judge(), chapter_of=chapter_of,
        unit_of=lambda c: "U", section_of=lambda r: None, infer_scope_when_undeclared=False,
        scope_of={"q1": {"Minerals and Energy Resources"}}.get,
    )
    assert offered[1] == {"Minerals and Energy Resources"}
    assert scoped.questions[0].chapter == "Minerals and Energy Resources"


# --- evidence outranks the label; a disagreement is re-read on the full section text --

class _QuotingJudge:
    """Answers per call: a list of (section, quote) consumed in order."""

    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def pick(self, stem, chapter_label, headings, passages):
        self.calls.append((dict(headings), list(passages)))
        section, quote = self.answers.pop(0)

        class _Choice:
            pass

        c = _Choice()
        c.section, c.quote, c.rationale = section, quote, "because"
        return c


MODE_SENTENCE = "The modal class is the class with the greatest frequency"


def test_the_section_is_where_the_quoted_fact_lives_not_the_heading_the_judge_named():
    """The judge writes 13.2 beside a quote copied from the 13.3 passage: the quote wins,
    retrieval agrees, and the row is not flagged."""
    judge = _QuotingJudge([("13.2", MODE_SENTENCE)])
    pick = choose_topic(
        "Find the modal class and hence the mode of the frequency distribution", STATS,
        "Statistics", CHUNKS, HEADINGS, judge,
    )
    assert pick.section == "13.3" and pick.agreed
    assert "named section 13.2" in pick.rationale and "13.3" in pick.rationale
    assert len(judge.calls) == 1, "no disagreement left to confirm"


def test_a_disagreement_is_re_read_against_the_full_text_of_both_sections():
    """First pass: 13.2, no quote, while retrieval says 13.3. The confirm pass is shown
    every chunk of 13.2 and 13.3 -- including one the first pass never saw -- and its
    quoted answer stands."""
    extra = _Chunk("c3b", "13.3 Mode of Grouped Data (example)", STATS,
                   "Example: the modal class of the given data is 60-80 and the mode is 65.",
                   "13.3")
    judge = _QuotingJudge([("13.2", ""), ("13.3", "the modal class of the given data is 60-80")])
    pick = choose_topic(
        "Find the modal class and hence the mode of the frequency distribution", STATS,
        "Statistics", CHUNKS + [extra], HEADINGS, judge,
    )
    assert len(judge.calls) == 2
    second_headings, second_passages = judge.calls[1]
    assert set(second_headings) == {"13.2", "13.3"}
    assert {p.chunk_id for p in second_passages} == {"c2", "c3", "c3b"}
    assert pick.section == "13.3" and pick.agreed
    assert "switched to 13.3" in pick.rationale


def test_a_confirmed_disagreement_stays_with_the_judge_and_is_flagged():
    judge = _QuotingJudge([("13.2", ""), ("13.2", "step-deviation method uses an assumed mean")])
    pick = choose_topic(
        "Find the modal class and hence the mode of the frequency distribution", STATS,
        "Statistics", CHUNKS, HEADINGS, judge,
    )
    assert pick.section == "13.2" and not pick.agreed
    assert "onfirmed against the full text" in pick.rationale
    assert "pointed at section 13.3" in pick.rationale


def test_a_quote_that_is_not_in_any_passage_is_not_evidence():
    from app.classify.topic import quoted_sections
    from app.ingest.probe import Candidate

    shown = [Candidate("c3", "r", STATS, "T", 0.0, "13.3", CHUNKS[2].text)]
    assert quoted_sections("The modal class is the class with the greatest", shown) == ["13.3"]
    assert quoted_sections("the mode is the most common value", shown) == []
    assert quoted_sections("modal", shown) == [], "a fragment this short proves nothing"
