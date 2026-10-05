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


# --- the question's own terms are evidence the judge cannot talk past ---------------

def test_distinctive_terms_are_names_titles_and_years_not_exam_boilerplate():
    from app.classify.topic import distinctive_terms

    terms = distinctive_terms(
        "Assertion (A) : The Roman Catholic Church began keeping an Index of Prohibited "
        "Books from the middle of the sixteenth century. Reason (R) : The Church feared"
    )
    assert "Index of Prohibited Books" in terms and "Roman Catholic Church" in terms
    assert "Assertion" not in terms and "Reason" not in terms
    assert distinctive_terms("Explain any three functions performed by political parties.") == []
    assert "1878" in distinctive_terms("It was passed in 1878.")


FEAR = _Chunk("f", "3.2 Religious Debates and the Fear of Print", STATS,
              "Print created the possibility of wide circulation of ideas. The Church feared "
              "that printed books would spread rebellious ideas.", "3.2")
DISSENT = _Chunk("d", "3.3 Print and Dissent", STATS,
                 "Menocchio reinterpreted the Bible. When the Roman Church began its inquisition "
                 "it imposed severe controls and maintained an Index of Prohibited Books from "
                 "1558.", "3.3")
PRINT_HEADINGS = {"3.2": "Religious Debates and the Fear of Print", "3.3": "Print and Dissent"}
INDEX_STEM = ("Assertion (A) : The Roman Catholic Church began keeping an Index of Prohibited "
              "Books from the middle of the sixteenth century. Reason (R) : The Church feared "
              "that the wide circulation of printed books would spread ideas.")


def test_a_term_the_book_uses_in_one_section_forces_a_re_read_even_when_retrieval_agrees():
    """The judge and retrieval both say 3.2 ("fear", "Church", "circulation" all score
    there); the question names the Index of Prohibited Books, which the chapter mentions
    only under 3.3. That chunk is shown to the judge, the disagreement is re-read on full
    text, and the quoted answer lands on 3.3."""
    from app.classify.topic import term_evidence, term_vote

    chunks = [FEAR, DISSENT, CHUNKS[4]]
    votes, shown = term_evidence(INDEX_STEM, chunks)
    assert votes["Index of Prohibited Books"] == ["3.3"]
    assert term_vote(votes) == "3.3"
    # the Index chunk first; "Church" is in both sections, so its chunk is shown but casts no vote
    assert [c.id for c in shown] == ["d", "f"]

    judge = _QuotingJudge([
        ("3.2", "The Church feared that printed books would spread rebellious ideas"),
        ("3.3", "maintained an Index of Prohibited Books from 1558"),
    ])
    pick = choose_topic(INDEX_STEM, STATS, "Print Culture", chunks, PRINT_HEADINGS, judge)
    assert len(judge.calls) == 2
    assert set(judge.calls[1][0]) == {"3.2", "3.3"}
    assert pick.section == "3.3" and pick.agreed
    assert "Index of Prohibited Books" in pick.rationale and "only under section 3.3" in pick.rationale


def test_a_judge_that_still_contradicts_the_books_own_term_is_flagged():
    judge = _QuotingJudge([("3.2", ""), ("3.2", "The Church feared that printed books")])
    chunks = [FEAR, DISSENT, CHUNKS[4]]
    pick = choose_topic(INDEX_STEM, STATS, "Print Culture", chunks, PRINT_HEADINGS, judge)
    assert pick.section == "3.2" and not pick.agreed


# --- whole chapter: the judge reads everything, the quote's location is the answer -----

class _DocumentJudge:
    """A judge that reads documents. Answers consumed in order as (section, quote)."""

    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def pick_from_document(self, stem, chapter_label, headings, document, candidates=None,
                           mode="answer", exclude=None):
        self.calls.append((dict(headings), document, candidates, mode, exclude))
        section, quote, *rest = self.answers.pop(0)

        class _Choice:
            pass

        c = _Choice()
        c.section, c.quote, c.rationale = section, quote, "read the chapter"
        c.answer, c.quotes = "", [quote] if quote else []
        c.also = list(rest[0]) if rest else []
        return c


class _VerifyingJudge(_DocumentJudge):
    """A document judge that can also be asked whether one section answers the question
    by itself: ``verdicts`` maps a section to (answerable, quote)."""

    def __init__(self, answers, verdicts):
        super().__init__(answers)
        self.verdicts, self.checked = dict(verdicts), []

    def answerable(self, stem, chapter_label, headings, document, section, sub_sections=None):
        self.checked.append((section, list(sub_sections or [])))
        ok, quote = self.verdicts.get(section, (False, ""))

        class _Verdict:
            pass

        v = _Verdict()
        v.answerable, v.quotes, v.reason = ok, [quote] if quote else [], "checked"
        return v


def test_the_chapter_document_is_every_section_in_book_order_with_headings():
    from app.classify.topic import chapter_document

    doc = chapter_document([FEAR, DISSENT], PRINT_HEADINGS)
    assert doc.index("## SECTION 3.2  Religious Debates") < doc.index("## SECTION 3.3  Print and Dissent")
    assert "Index of Prohibited Books" in doc and "The Church feared" in doc


def test_a_document_judge_is_given_the_whole_chapter_and_its_quote_decides():
    """The judge writes 3.2 but quotes the Index sentence, which is only under 3.3: the
    section is 3.3, the term vote agrees, nothing is flagged, and the judge was shown
    every section's text rather than a sampled passage."""
    chunks = [FEAR, DISSENT, CHUNKS[4]]
    judge = _DocumentJudge([
        ("3.2", "maintained an Index of Prohibited Books from 1558"),   # answer read
        ("3.3", "maintained an Index of Prohibited Books from 1558"),   # taught read
    ])
    pick = choose_topic(INDEX_STEM, STATS, "Print Culture", chunks, PRINT_HEADINGS, judge)
    assert pick.section == "3.3" and pick.agreed and pick.source == "judge"
    assert [c[3] for c in judge.calls] == ["answer", "taught"], "two independent reads, no confirm needed"
    headings, document, candidates, _, _ = judge.calls[0]
    assert candidates is None and headings == PRINT_HEADINGS
    assert "## SECTION 3.2" in document and "## SECTION 3.3" in document
    assert "named section 3.2" in pick.rationale


def test_a_document_judge_that_contradicts_the_books_own_term_is_re_read_on_those_sections():
    chunks = [FEAR, DISSENT, CHUNKS[4]]
    judge = _DocumentJudge([
        ("3.2", "The Church feared that printed books would spread rebellious ideas"),  # answer
        ("3.2", "The Church feared that printed books would spread rebellious ideas"),  # taught
        ("3.3", "maintained an Index of Prohibited Books from 1558"),                   # confirm
    ])
    pick = choose_topic(INDEX_STEM, STATS, "Print Culture", chunks, PRINT_HEADINGS, judge)
    assert len(judge.calls) == 3
    assert set(judge.calls[2][2]) == {"3.2", "3.3"}, "the confirm pass is restricted to the claimants"
    assert judge.calls[2][1] == judge.calls[0][1], "the same document, so the cache hits"
    assert pick.section == "3.3" and pick.agreed
    assert "switched to 3.3" in pick.rationale


def test_a_document_judge_that_abstains_falls_back_like_the_sampled_mode():
    chunks = [FEAR, DISSENT, CHUNKS[4]]
    judge = _DocumentJudge([("none", ""), ("none", "")])
    pick = choose_topic(INDEX_STEM, STATS, "Print Culture", chunks, PRINT_HEADINGS, judge,
                        fallback_section="3.3")
    assert pick.section == "3.3" and pick.source == "chapter_judge"


def test_a_sampled_judge_without_document_reading_still_uses_the_sampled_mode():
    judge = _QuotingJudge([("3.3", "maintained an Index of Prohibited Books from 1558")])
    pick = choose_topic(INDEX_STEM, STATS, "Print Culture", [FEAR, DISSENT, CHUNKS[4]],
                        PRINT_HEADINGS, judge)
    assert pick.section == "3.3" and pick.agreed



# --- answered, not mentioned -----------------------------------------------------------

CHALLENGE = _Chunk("ch5", "5 Challenges to political parties", STATS,
                   "The third challenge is about the growing role of money and muscle power "
                   "in parties, especially during elections.", "5")
REFORM = _Chunk("ch6", "6 How can parties be reformed?", STATS,
                "It should be made mandatory for parties to maintain a register of members. "
                "There should be state funding of elections to reduce the role of money.", "6")
POL_HEADINGS = {"5": "Challenges to political parties", "6": "How can parties be reformed?"}
MEASURES_STEM = (
    "Suggest any two measures that can be taken to reduce the influence of money and "
    "muscle power in political parties."
)


def test_the_section_that_answers_beats_the_section_that_mentions_the_subject():
    """The taught read quotes where money and muscle power is NAMED (5); the answer read
    quotes the measures (6). The answer read leads, the re-read sides with it, settled."""
    judge = _DocumentJudge([
        ("6", "There should be state funding of elections to reduce the role of money"),   # answer
        ("5", "growing role of money and muscle power in parties"),                        # taught
        ("6", "It should be made mandatory for parties to maintain a register of members"), # confirm
    ])
    pick = choose_topic(MEASURES_STEM, STATS, "Political Parties", [CHALLENGE, REFORM, CHUNKS[4]],
                        POL_HEADINGS, judge)
    assert pick.section == "6" and pick.agreed
    assert "answers the question (6" in pick.rationale
    assert [c[3] for c in judge.calls] == ["answer", "taught", "answer"]


def test_a_re_read_that_sides_with_the_taught_read_switches_and_stays_settled():
    judge = _DocumentJudge([
        ("6", "There should be state funding of elections to reduce the role of money"),
        ("5", "growing role of money and muscle power in parties"),
        ("5", "growing role of money and muscle power in parties"),
    ])
    pick = choose_topic(MEASURES_STEM, STATS, "Political Parties", [CHALLENGE, REFORM, CHUNKS[4]],
                        POL_HEADINGS, judge)
    assert pick.section == "5" and pick.agreed
    assert "switched to 5" in pick.rationale


# --- multi-part questions: the other sections a part is answered in ---------------------

def test_the_other_sections_a_part_of_the_question_is_answered_in_are_secondaries():
    """A chronology answered across 3.2 and 3.3: the primary is where most of it is, the
    rest ride along as secondaries -- never the primary itself or one of its relatives."""
    chunks = [FEAR, DISSENT, CHUNKS[4]]
    judge = _DocumentJudge([
        ("3.2", "The Church feared that printed books would spread rebellious ideas", ["3.3", "3.2", "9.9"]),
        ("3.2", "The Church feared that printed books would spread rebellious ideas"),
    ])
    pick = choose_topic(INDEX_STEM, STATS, "Print Culture", chunks, PRINT_HEADINGS, judge)
    assert pick.section == "3.2"
    assert pick.secondaries == (("3.3", "Print and Dissent"),), (
        "3.2 is the primary, 9.9 is not a section of this chapter"
    )
    assert pick.verified is None, "a judge that cannot be asked to verify leaves it unchecked"


def test_a_single_part_question_has_no_secondaries():
    judge = _DocumentJudge([("3.3", "maintained an Index of Prohibited Books from 1558"),
                            ("3.3", "maintained an Index of Prohibited Books from 1558")])
    pick = choose_topic(INDEX_STEM, STATS, "Print Culture", [FEAR, DISSENT, CHUNKS[4]],
                        PRINT_HEADINGS, judge)
    assert pick.secondaries == ()


# --- verification: the section must ANSWER the question from its own text ---------------

def test_a_section_that_only_mentions_the_subject_fails_verification_and_the_answering_claimant_is_taken():
    """Both the answer read and the confirm pass pick 5, where money and muscle power is
    NAMED; only 6 lists the measures. Asked whether 5 alone answers the question the
    judge says no, 6 yes with a real sentence of 6 -- so 6 is the topic, verified."""
    judge = _VerifyingJudge(
        [
            ("5", "growing role of money and muscle power in parties"),                        # answer
            ("6", "There should be state funding of elections to reduce the role of money"),   # taught
            ("5", "growing role of money and muscle power in parties"),                        # confirm
        ],
        {"5": (False, ""), "6": (True, "state funding of elections to reduce the role of money")},
    )
    pick = choose_topic(MEASURES_STEM, STATS, "Political Parties", [CHALLENGE, REFORM, CHUNKS[4]],
                        POL_HEADINGS, judge)
    assert [c[0] for c in judge.checked] == ["5", "6"]
    assert pick.section == "6" and pick.verified is True and pick.agreed
    assert "cannot answer the question on its own; section 6" in pick.rationale


def test_when_every_read_agrees_on_a_section_that_cannot_answer_the_judge_is_asked_where_else():
    """Both reads quote the activity that says 'locate the nuclear power stations'; the
    plant's name is only in the map work of another section. Agreement is worthless
    here: the check fails, the judge is re-asked with 5 ruled out, and its new answer is
    verified before it is believed."""
    judge = _VerifyingJudge(
        [
            ("5", "growing role of money and muscle power in parties"),                        # answer
            ("5", "growing role of money and muscle power in parties"),                        # taught
            ("6", "It should be made mandatory for parties to maintain a register of members"), # relocate
        ],
        {"5": (False, ""), "6": (True, "mandatory for parties to maintain a register of members")},
    )
    pick = choose_topic(MEASURES_STEM, STATS, "Political Parties", [CHALLENGE, REFORM, CHUNKS[4]],
                        POL_HEADINGS, judge)
    relocate = judge.calls[2]
    assert relocate[3] == "answer" and relocate[4] == {"5": "Challenges to political parties"}
    assert [c[0] for c in judge.checked] == ["5", "6"]
    assert pick.section == "6" and pick.verified is True and pick.agreed
    assert "ruled out, the judge found it answered in section 6" in pick.rationale


def test_a_yes_that_quotes_nothing_from_that_section_is_not_a_yes():
    """The judge says 6 answers it but quotes a sentence of 5: a paraphrase from
    elsewhere, not evidence. Nothing passes, the first answer is kept and flagged."""
    judge = _VerifyingJudge(
        [
            ("5", "growing role of money and muscle power in parties"),
            ("5", "growing role of money and muscle power in parties"),
            ("none", ""),
        ],
        {"5": (False, ""), "6": (True, "growing role of money and muscle power in parties")},
    )
    pick = choose_topic(MEASURES_STEM, STATS, "Political Parties", [CHALLENGE, REFORM, CHUNKS[4]],
                        POL_HEADINGS, judge)
    assert pick.section == "5" and pick.verified is False and not pick.agreed
    assert "answers this question from its own text" in pick.rationale


def test_a_verified_section_is_settled_and_a_parent_is_checked_with_its_sub_sections():
    judge = _VerifyingJudge(
        [("3", "maintained an Index of Prohibited Books from 1558"),
         ("3.3", "maintained an Index of Prohibited Books from 1558")],
        {"3.3": (True, "maintained an Index of Prohibited Books from 1558")},
    )
    headings = {"3": "The Print Revolution and its Impact", **PRINT_HEADINGS}
    pick = choose_topic(INDEX_STEM, STATS, "Print Culture", [FEAR, DISSENT, CHUNKS[4]],
                        headings, judge)
    assert pick.section == "3.3", "the quoted sentence sits under 3.3, the deepest match"
    assert judge.checked == [("3.3", [])]
    assert pick.verified is True and pick.agreed


def test_a_parent_section_is_verified_together_with_its_sub_sections():
    parent = _Chunk("p3", "3 The Print Revolution and its Impact", STATS,
                    "The print revolution transformed the lives of people, changing their "
                    "relationship to information and knowledge.", "3")
    judge = _VerifyingJudge(
        [("3", "changing their relationship to information and knowledge"),
         ("3", "changing their relationship to information and knowledge")],
        {"3": (True, "maintained an Index of Prohibited Books from 1558")},
    )
    headings = {"3": "The Print Revolution and its Impact", **PRINT_HEADINGS}
    pick = choose_topic("Explain the impact of the print revolution.", STATS, "Print Culture",
                        [parent, FEAR, DISSENT, CHUNKS[4]], headings, judge)
    assert judge.checked == [("3", ["3.2", "3.3"])]
    assert pick.section == "3" and pick.verified is True, (
        "a sentence of a sub-section counts as the parent's own text"
    )


# --- the rows: a secondary topic is written beside the primary ---------------------------

def test_secondary_topics_are_written_beside_the_primary_at_half_weight_and_replaced_with_it(
    client, school, book,
):
    from app.db import SessionLocal
    from app.mapping.topic_node import SECONDARY_WEIGHT, set_question_topic
    from app.models import Question, QuestionSkill, TaxonomyNode

    created = client.post(
        "/assessments", headers=_auth(school),
        json={"subject_code": "X.MATH", "title": "Secondary topics", "total_marks": 3},
    )
    aid = created.json()["assessment_id"]
    added = client.post(
        f"/assessments/{aid}/questions", headers=_auth(school),
        json={"questions": [{
            "section": "A", "question_no": "1", "max_marks": 3,
            "stem_text": "Find the mean, and the mode, of the frequency distribution",
            "board_unit": "X.MATH.U.MENSURATION", "concept_family": "X.MATH.CF.VOLUME",
            "concept_variant": "secondary fixture",
        }]},
    )
    assert added.status_code == 200, added.json()
    db = SessionLocal()
    try:
        qid = db.scalars(select(Question).where(Question.assessment_id == aid)).first().id
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.STATS"))

        def rows():
            out = []
            for r in db.scalars(select(QuestionSkill).where(QuestionSkill.question_id == qid)):
                out.append((db.get(TaxonomyNode, r.node_id).label, r.source, r.weight))
            return sorted(out, key=lambda t: -t[2])

        set_question_topic(
            db, qid, chapter, "13.2", "Mean of Grouped Data", source="classify",
            secondaries=(("13.3", "Mode of Grouped Data"), ("13.2", "Mean of Grouped Data")),
        )
        assert rows() == [("Mean of Grouped Data", "classify", 1.0),
                          ("Mode of Grouped Data", "classify", SECONDARY_WEIGHT)]
        # decided again, this time as a single-part question: the secondary goes
        set_question_topic(db, qid, chapter, "13.2", "Mean of Grouped Data", source="classify")
        assert rows() == [("Mean of Grouped Data", "classify", 1.0)]
        # a person's choice is one topic, and a later machine pass never adds to it
        set_question_topic(db, qid, chapter, "13.3", "Mode of Grouped Data", source="human")
        set_question_topic(
            db, qid, chapter, "13.2", "Mean of Grouped Data", source="classify",
            secondaries=(("13.4", "Median of Grouped Data"),),
        )
        assert rows() == [("Mode of Grouped Data", "human", 1.0)]
    finally:
        db.rollback()
        db.close()


# --- the book map's map-only places reach the knowledge base -----------------------------

def test_map_items_are_read_from_the_markdown_beside_the_units_json(tmp_path):
    from scripts.import_book_map import _text_chunks, map_items_from_markdown

    (tmp_path / "5_minerals.md").write_text(
        "### 4.1.4 Electricity\n"
        "unit: X.GEO.MINERALSENERGY.4.1.4 | kind: subsection | parent: X.GEO.MINERALSENERGY.4.1\n"
        "\nElectricity is generated mainly in two ways.\n"
        "\n**CBSE map items linked to this unit** · Thermal power plant: Namrup (shown on the "
        "map only, not named in the text); Thermal power plant: Ramagundam\n"
        "\n### 4.2.1 Nuclear or Atomic Energy\n"
        "unit: X.GEO.MINERALSENERGY.4.2.1 | kind: subsection | parent: X.GEO.MINERALSENERGY.4.2\n"
        "\nIt is obtained by altering the structure of atoms.\n"
        "\n**CBSE map items linked to this unit** · Nuclear power plant: Kalpakkam (shown on the "
        "map only, not named in the text); Nuclear power plant: Tarapur (shown on the map only, "
        "not named in the text)\n"
        "\n### 4.2.2 Solar Energy\nunit: X.GEO.MINERALSENERGY.4.2.2 | kind: subsection\n"
    )
    items = map_items_from_markdown(tmp_path)
    assert items == {
        "X.GEO.MINERALSENERGY.4.1.4": ["Thermal power plant: Namrup", "Thermal power plant: Ramagundam"],
        "X.GEO.MINERALSENERGY.4.2.1": ["Nuclear power plant: Kalpakkam", "Nuclear power plant: Tarapur"],
    }
    unit = {"id": "X.GEO.MINERALSENERGY.4.2.1", "number": "4.2.1", "title": "Nuclear or Atomic Energy",
            "body": [{"text": "It is obtained by altering the structure of atoms."}]}
    chunks = _text_chunks("X.GEO.MINERALSENERGY", unit, items[unit["id"]])
    assert chunks[0] == ("4.2.1 Nuclear or Atomic Energy", "4.2.1",
                         "It is obtained by altering the structure of atoms.")
    reference, section, text = chunks[-1]
    assert reference == "4.2.1 Nuclear or Atomic Energy (map)" and section == "4.2.1"
    assert "Kalpakkam" in text and "Tarapur" in text and "shown on the map only" not in text
    assert _text_chunks("X.GEO.MINERALSENERGY", unit, None) == chunks[:1]


def test_a_map_chunks_reference_is_not_the_sections_heading():
    from app.mapping.topic_node import book_map_topic_label

    body = _Chunk("m1", "4.2.1 Nuclear or Atomic Energy (map)", "geo",
                  "Map work for this section. Shown on the map of India under this topic: "
                  "Nuclear power plant: Kalpakkam.", "4.2.1")
    body.subject_code = "X.GEO"
    assert book_map_topic_label([body], "geo", "4.2.1") == "4.2.1 Nuclear or Atomic Energy"


# --- adaptive reads: the second read is skipped only when nothing doubts the first ----------

def test_adaptive_reads_skip_the_taught_read_when_the_first_is_corroborated():
    chunks = [FEAR, DISSENT, CHUNKS[4]]
    quote = "maintained an Index of Prohibited Books from 1558"
    judge = _VerifyingJudge([("3.3", quote)], {"3.3": (True, quote)})
    pick = choose_topic(INDEX_STEM, STATS, "Print Culture", chunks, PRINT_HEADINGS, judge,
                        adaptive_reads=True)
    assert pick.section == "3.3" and pick.agreed and pick.verified is True
    assert [c[3] for c in judge.calls] == ["answer"], "no taught read, no confirm"
    assert judge.checked, "the answerability check still runs"


def test_without_the_flag_both_reads_are_made_as_before():
    chunks = [FEAR, DISSENT, CHUNKS[4]]
    quote = "maintained an Index of Prohibited Books from 1558"
    judge = _VerifyingJudge([("3.3", quote), ("3.3", quote)], {"3.3": (True, quote)})
    choose_topic(INDEX_STEM, STATS, "Print Culture", chunks, PRINT_HEADINGS, judge)
    assert [c[3] for c in judge.calls] == ["answer", "taught"]


def test_adaptive_reads_still_make_the_second_read_when_the_first_is_not_corroborated():
    """The judge names 3.2 but quotes a sentence that is only under 3.3: its own number and
    quote disagree, so it is not settled and the taught read is made."""
    chunks = [FEAR, DISSENT, CHUNKS[4]]
    quote = "maintained an Index of Prohibited Books from 1558"
    judge = _DocumentJudge([("3.2", quote), ("3.3", quote)])
    pick = choose_topic(INDEX_STEM, STATS, "Print Culture", chunks, PRINT_HEADINGS, judge,
                        adaptive_reads=True)
    assert [c[3] for c in judge.calls] == ["answer", "taught"]
    assert pick.section == "3.3"


def test_adaptive_reads_do_not_skip_when_the_books_terms_name_another_section():
    chunks = [FEAR, DISSENT, CHUNKS[4]]
    wrong = "The Church feared that printed books would spread rebellious ideas"
    judge = _DocumentJudge([("3.2", wrong), ("3.2", wrong),
                            ("3.3", "maintained an Index of Prohibited Books from 1558")])
    choose_topic(INDEX_STEM, STATS, "Print Culture", chunks, PRINT_HEADINGS, judge,
                 adaptive_reads=True)
    assert [c[3] for c in judge.calls][:2] == ["answer", "taught"]
