"""Classification: the judge's contract, and the constraint layer that catches it.

The constraint tests matter most. The judge is a model and cannot be pinned down in a unit
test; the reconciliation is arithmetic and can be, and it is the part that makes a wrong
answer recoverable rather than final.
"""

from __future__ import annotations

import pytest

from app.classify.judge import Classification, Evidence, build_prompt
from app.classify.reconcile import (
    Option,
    QuestionSlot,
    needs_a_human,
    reconcile,
)

MENS, TRIG, ALG = "MENSURATION", "TRIG", "ALGEBRA"


# --- the prompt -------------------------------------------------------------------------

def test_the_prompt_names_the_candidates_and_nothing_else():
    """The judge must choose among what retrieval found. A chapter it invented would look
    identical to a correct answer downstream."""
    evidence = [
        Evidence("Surface Areas and Volumes", "Example 3", "12.2", "A cone of radius..."),
        Evidence("Applications of Trigonometry", "Example 1", "9.1", "A tower stands..."),
    ]
    prompt = build_prompt("The slant height of a cone is", evidence)
    assert "CANDIDATE CHAPTERS" in prompt
    assert "Surface Areas and Volumes" in prompt
    assert "Applications of Trigonometry" in prompt
    assert "section 12.2" in prompt


def test_a_long_passage_is_truncated_in_the_prompt():
    """A whole exercise runs to 8500 characters and its tail is later questions, which
    would pull the judge towards whatever they happen to be about."""
    evidence = [Evidence("Statistics", "EXERCISE 13.2", "13.2", "x" * 9000)]
    assert len(build_prompt("q", evidence)) < 3000


# --- the classification contract ---------------------------------------------------------

def test_a_classification_will_not_accept_an_out_of_range_confidence():
    with pytest.raises(ValueError):
        Classification(
            chapter="Circles", tier="Applying", skill_required="x",
            reasoning="y", confidence=1.4,
        )


def test_a_section_may_be_absent_rather_than_guessed():
    c = Classification(
        chapter="Circles", tier="Applying", skill_required="x", reasoning="y",
        confidence=0.9,
    )
    assert c.curriculum_section is None


# --- the constraint layer -----------------------------------------------------------------

def test_the_blueprint_overrules_a_confident_but_impossible_placement():
    """The real failure: 'slant height of a right circular cone' scored highest against
    Applications of Trigonometry, because that chapter is full of right triangles with a
    hypotenuse. The marks say otherwise."""
    slots = [
        QuestionSlot("17", 1.0, [
            Option("Applications of Trigonometry", TRIG, 0.68),
            Option("Surface Areas and Volumes", MENS, 0.66),
        ]),
        QuestionSlot("15", 1.0, [Option("Areas Related to Circles", MENS, 0.95)]),
        QuestionSlot("13", 1.0, [Option("Introduction to Trigonometry", TRIG, 0.95)]),
    ]
    result = reconcile(slots, {MENS: 2.0, TRIG: 1.0})

    assert result.assignment["17"].chapter == "Surface Areas and Volumes"
    assert result.feasible
    assert "17" in result.overruled


def test_a_correct_assignment_is_left_alone():
    slots = [
        QuestionSlot("1", 3.0, [Option("Circles", MENS, 0.9)]),
        QuestionSlot("2", 2.0, [Option("Polynomials", ALG, 0.9)]),
    ]
    result = reconcile(slots, {MENS: 3.0, ALG: 2.0})
    assert result.feasible
    assert result.overruled == []


def test_confidence_decides_which_question_moves():
    """Two questions could close the gap; the one believed less should be the one to go."""
    slots = [
        QuestionSlot("sure", 2.0, [
            Option("Polynomials", ALG, 0.99), Option("Circles", MENS, 0.30),
        ]),
        QuestionSlot("unsure", 2.0, [
            Option("Polynomials", ALG, 0.55), Option("Circles", MENS, 0.45),
        ]),
    ]
    result = reconcile(slots, {ALG: 2.0, MENS: 2.0})
    assert result.assignment["sure"].chapter == "Polynomials"
    assert result.assignment["unsure"].chapter == "Circles"


def test_an_unclosable_paper_says_so_instead_of_returning_a_tidy_answer():
    """If the totals cannot balance, the right chapter may never have been a candidate --
    reporting a neat assignment would hide that."""
    slots = [QuestionSlot("1", 5.0, [Option("Circles", MENS, 0.9)])]
    result = reconcile(slots, {MENS: 10.0})
    assert not result.feasible
    assert result.residual[MENS] == (5.0, 10.0)
    assert "could not be closed" in result.note


def test_a_paper_declaring_no_blueprint_is_left_untouched():
    """A school unit test declares nothing, and inventing a constraint would corrupt it."""
    slots = [QuestionSlot("1", 3.0, [Option("Circles", MENS, 0.4)])]
    result = reconcile(slots, {})
    assert result.assignment["1"].chapter == "Circles"
    assert "no blueprint" in result.note


# --- who gets looked at --------------------------------------------------------------------

def test_low_confidence_and_overruled_questions_both_reach_a_human():
    slots = [
        QuestionSlot("weak", 1.0, [Option("Circles", MENS, 0.40)]),
        QuestionSlot("strong", 1.0, [Option("Polynomials", ALG, 0.98)]),
    ]
    result = reconcile(slots, {MENS: 1.0, ALG: 1.0})
    flagged = needs_a_human(slots, result)
    assert "weak" in flagged
    assert "strong" not in flagged


def test_when_the_totals_never_close_the_whole_paper_is_suspect():
    slots = [
        QuestionSlot("a", 2.0, [Option("Circles", MENS, 0.99)]),
        QuestionSlot("b", 2.0, [Option("Polynomials", ALG, 0.95)]),
    ]
    result = reconcile(slots, {MENS: 10.0, ALG: 2.0})
    assert not result.feasible
    # even the confident ones are worth a look when the arithmetic is broken
    assert set(needs_a_human(slots, result)) == {"a", "b"}


# --- the three stages together -------------------------------------------------------------

def test_the_pipeline_lets_the_blueprint_correct_the_judge():
    """End to end on the failure that motivated the constraint layer, with a stub judge
    standing in for the model so the arithmetic is what is being tested."""
    from app.classify.pipeline import place_paper
    from app.ingest.probe import LexicalIndex

    class Chunk:
        def __init__(self, cid, text, node):
            self.chunk_id = cid
            self.id = cid
            self.text = text
            self.reference = cid
            self.node_id = node
            self.bucket = "T"
            self.embedding = None

    chunks = [
        Chunk("mens1", "cone slant height radius volume of a solid", "SAV"),
        Chunk("mens2", "surface area of a combination of solids cone", "SAV"),
        Chunk("trig1", "tower height angle of elevation observer", "APPTRIG"),
        Chunk("trig2", "line of sight horizontal angle of elevation", "APPTRIG"),
    ]
    chunks += [Chunk(f"pad{i}", f"unrelated topic {i}", f"P{i}") for i in range(20)]

    class StubJudge:
        """Reproduces the model's actual mistake: prefers trigonometry for a cone."""

        def classify(self, question, evidence):
            return Classification(
                chapter="Applications of Trigonometry", tier="Applying",
                skill_required="right triangle", reasoning="height and a right angle",
                confidence=0.68, alternative_chapter="Surface Areas and Volumes",
            )

    names = {"SAV": "Surface Areas and Volumes", "APPTRIG": "Applications of Trigonometry"}
    units = {"Surface Areas and Volumes": MENS, "Applications of Trigonometry": TRIG}

    placement = place_paper(
        [("17", "cone slant height radius", 1.0)],
        [LexicalIndex(chunks)],
        StubJudge(),
        chapter_of=lambda n: names.get(n),
        unit_of=lambda c: units.get(c),
        section_of=lambda r: None,
        declared={MENS: 1.0},          # the paper says this mark is Mensuration
    )

    [q] = placement.questions
    assert q.chapter == "Surface Areas and Volumes", "the blueprint must overrule the judge"
    assert q.overruled
    assert q.needs_review, "two sources disagreeing is exactly what a human should see"
    assert placement.feasible


def test_a_paper_with_no_blueprint_keeps_what_the_judge_decided():
    from app.classify.pipeline import place_paper
    from app.ingest.probe import LexicalIndex

    class Chunk:
        def __init__(self, cid, text, node):
            self.chunk_id = cid
            self.id = cid
            self.text = text
            self.reference = cid
            self.node_id = node
            self.bucket = "T"
            self.embedding = None

    chunks = [Chunk("c1", "circle tangent chord radius", "CIRCLE")]
    chunks += [Chunk(f"pad{i}", f"unrelated topic {i}", f"P{i}") for i in range(20)]

    class StubJudge:
        def classify(self, question, evidence):
            return Classification(
                chapter="Circles", tier="Applying", skill_required="tangents",
                reasoning="about tangents", confidence=0.92,
            )

    placement = place_paper(
        [("1", "circle tangent chord", 2.0)],
        [LexicalIndex(chunks)],
        StubJudge(),
        chapter_of=lambda n: "Circles",
        unit_of=lambda c: MENS,
        section_of=lambda r: "10.2",
        declared=None,
    )
    [q] = placement.questions
    assert q.chapter == "Circles"
    assert not q.overruled
    assert not q.needs_review
    assert q.curriculum_section == "10.2" or q.curriculum_section is None


def test_a_judge_answering_outside_the_candidates_is_forced_to_abstain():
    """A chapter the model invented looks identical to a correct one downstream, and
    nothing in the taxonomy would catch it."""
    from app.classify.grounding import ground as confine_to_candidates

    evidence = [
        Evidence("Circles", "Example 1", "10.2", "tangent"),
        Evidence("Triangles", "Theorem 6.1", "6.2", "similar"),
    ]

    invented = Classification(
        chapter="Quantum Mechanics", tier="Applying", skill_required="x",
        reasoning="because", confidence=0.99,
    )
    forced = confine_to_candidates(invented, evidence).classification
    assert forced.chapter in {"Circles", "Triangles"}
    assert forced.confidence == 0.0, "an invented answer must not keep its confidence"


def test_an_answer_inside_the_candidates_is_untouched():
    from app.classify.grounding import ground

    evidence = [Evidence("Circles", "Example 1", "10.2", "tangent")]
    good = Classification(
        chapter="Circles", tier="Applying", skill_required="tangents",
        reasoning="about tangents", confidence=0.91,
    )
    checked = ground(good, evidence, known_sections={"Circles": {"10.2"}})
    assert checked.clean
    assert checked.classification is good


# --- rung 2: the declared syllabus scope ---------------------------------------------------

class _Chunk:
    def __init__(self, cid, text, node):
        self.chunk_id = cid
        self.id = cid
        self.text = text
        self.reference = cid
        self.node_id = node
        self.bucket = "T"
        self.embedding = None


def _corpus():
    chunks = [
        _Chunk("sav1", "cone slant height radius volume of a solid", "SAV"),
        _Chunk("sav2", "surface area of a combination of solids cone", "SAV"),
        _Chunk("trig1", "tower height angle of elevation observer slant", "APPTRIG"),
        _Chunk("trig2", "line of sight horizontal angle of elevation height", "APPTRIG"),
    ]
    chunks += [_Chunk(f"pad{i}", f"unrelated topic {i}", f"P{i}") for i in range(20)]
    return chunks


NAMES = {"SAV": "Surface Areas and Volumes", "APPTRIG": "Applications of Trigonometry"}


def test_scope_removes_out_of_range_chapters_from_retrieval():
    """A teacher who says 'this test covers chapters 1 to 5' has ruled chapter 9 out. It is
    not a weaker answer; it is a wrong one."""
    from app.ingest.probe import LexicalIndex, locate

    index = LexicalIndex(_corpus())
    unscoped = locate("tower height angle of elevation", [index])
    assert unscoped.node_id == "APPTRIG"

    scoped = locate(
        "tower height angle of elevation", [index],
        scope={"Surface Areas and Volumes"}, chapter_of=NAMES.get,
    )
    assert scoped.node_id == "SAV", "out of scope must be unreachable, not merely unlikely"


def test_scope_rescues_a_question_the_judge_would_have_misplaced():
    """The cone question, on a cyclic test that covers mensuration but not trigonometry --
    no blueprint anywhere, which is the case most papers actually are."""
    from app.classify.pipeline import place_paper
    from app.ingest.probe import LexicalIndex

    class StubJudge:
        """Would pick trigonometry if shown it -- and must never be shown it."""

        def classify(self, question, evidence):
            chapters = {e.chapter for e in evidence}
            assert "Applications of Trigonometry" not in chapters, (
                "an out-of-scope chapter reached the judge"
            )
            return Classification(
                chapter="Surface Areas and Volumes", tier="Applying",
                skill_required="mensuration formula", reasoning="a cone",
                confidence=0.88,
            )

    placement = place_paper(
        [("17", "cone slant height radius", 1.0)],
        [LexicalIndex(_corpus())],
        StubJudge(),
        chapter_of=NAMES.get,
        unit_of=lambda c: MENS,
        section_of=lambda r: None,
        declared=None,                       # no blueprint at all
        scope={"Surface Areas and Volumes"},
    )
    [q] = placement.questions
    assert q.chapter == "Surface Areas and Volumes"
    assert not q.needs_review, "a confident in-scope placement needs no one's time"


def test_no_scope_declared_is_not_the_same_as_the_whole_syllabus():
    """None means the paper said nothing, and a report has to be able to say so."""
    from app.classify.pipeline import place_paper
    from app.ingest.probe import LexicalIndex

    class StubJudge:
        def classify(self, question, evidence):
            return Classification(
                chapter=sorted({e.chapter for e in evidence})[0], tier="Applying",
                skill_required="x", reasoning="y", confidence=0.9,
            )

    both = place_paper(
        [("17", "tower height angle of elevation", 1.0)],
        [LexicalIndex(_corpus())], StubJudge(),
        chapter_of=NAMES.get, unit_of=lambda c: MENS, section_of=lambda r: None,
        scope=None,
    )
    assert both.questions, "an undeclared scope must not filter everything away"


def test_a_paper_with_no_declaration_infers_its_own_scope_and_narrows():
    """What most papers are: a cyclic test, no blueprint, no teacher input. The paper says
    what it covers by where its questions fall, and the second pass uses that."""
    from app.classify.pipeline import place_paper
    from app.ingest.probe import LexicalIndex

    chunks = [
        _Chunk("real1", "irrational number prime factorisation fundamental theorem", "REAL"),
        _Chunk("real2", "prove that root five is irrational contradiction", "REAL"),
        _Chunk("poly1", "polynomial zeroes coefficients quadratic sum product", "POLY"),
        _Chunk("poly2", "graph of a polynomial cuts the x axis zeroes", "POLY"),
        _Chunk("trig1", "tower angle of elevation observer line of sight", "APPTRIG"),
    ]
    chunks += [_Chunk(f"pad{i}", f"unrelated topic {i}", f"P{i}") for i in range(20)]
    names = {"REAL": "Real Numbers", "POLY": "Polynomials",
             "APPTRIG": "Applications of Trigonometry"}
    units = {"Real Numbers": "NUMBER", "Polynomials": ALG,
             "Applications of Trigonometry": TRIG}

    asked: list[set[str]] = []

    class StubJudge:
        """Confident on the real topics; wrong and unsure on one question."""

        def classify(self, question, evidence):
            asked.append({e.chapter for e in evidence})
            if "irrational" in question:
                return Classification(
                    chapter="Real Numbers", tier="Applying", skill_required="proof",
                    reasoning="irrationality", confidence=0.92,
                )
            if "polynomial" in question:
                return Classification(
                    chapter="Polynomials", tier="Applying", skill_required="zeroes",
                    reasoning="zeroes", confidence=0.90,
                )
            # the outlier: one question misread into a chapter the test does not cover
            return Classification(
                chapter="Applications of Trigonometry", tier="Applying",
                skill_required="right triangle", reasoning="an angle", confidence=0.66,
            )

    questions = (
        [(f"r{i}", "prove irrational number", 2.0) for i in range(5)]
        + [(f"p{i}", "find the zeroes of the polynomial", 2.0) for i in range(4)]
        + [("odd", "an angle appears somewhere", 1.0)]
    )

    placement = place_paper(
        questions, [LexicalIndex(chunks)], StubJudge(),
        chapter_of=names.get, unit_of=units.get, section_of=lambda r: None,
        declared=None, scope=None,
    )

    assert placement.scope_source == "inferred"
    assert placement.scope.chapters == {"Real Numbers", "Polynomials"}
    assert "Applications of Trigonometry" in placement.scope.rejected

    # In the second pass an in-scope question sees only in-scope chapters. (The very last
    # call is the outlier's deliberate unscoped retry -- see below.)
    second_pass = asked[len(questions):]
    in_scope_calls = [a for a in second_pass if a != {"Applications of Trigonometry"}]
    assert in_scope_calls, "the second pass should have classified the real questions"
    assert all("Applications of Trigonometry" not in a for a in in_scope_calls)

    # The outlier is kept, not deleted: a question missing from a report is worse than one
    # visibly in the wrong place. It is retried without the scope and handed to a person.
    odd = next(q for q in placement.questions if q.question_id == "odd")
    assert odd.needs_review
    assert odd.confidence == 0.0
    assert "not from this paper" in odd.reasoning


# --- a second subject ---------------------------------------------------------------------

def test_the_science_units_carry_the_boards_own_marks():
    """80 theory marks across five units. A total that does not reach 80 would make every
    board-impact figure wrong by a constant, silently."""
    from app.curriculum import X_SCIENCE

    assert sum(u.weight_pct for u in X_SCIENCE.units) == 80.0
    assert len(X_SCIENCE.units) == 5


def test_science_declares_no_chapters_until_its_book_is_read():
    """The rationalised syllabus renumbered the book and secondary sources disagree. A
    chapter mapped to the wrong unit sends a student's marks to the wrong place in the
    report, so the contents page decides -- as it already does for sections."""
    from app.curriculum import X_SCIENCE

    assert X_SCIENCE.chapters == []


def test_applying_a_curriculum_with_no_chapters_still_sets_up_its_units(tmp_path):
    """The intermediate state has to be usable: units first, chapters when the book lands."""
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from app.curriculum import X_SCIENCE
    from app.curriculum.apply import apply
    from app.models import Base, BoardUnitWeight, TaxonomyNode

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path}/sci.db")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        created = apply(db, X_SCIENCE)
        assert created["units"] == 5
        assert created["chapters"] == 0
        assert db.scalar(
            select(func.count(TaxonomyNode.id)).where(TaxonomyNode.kind == "board_unit")
        ) == 5
        # every unit carries its citation, because a principal will challenge these
        assert all(
            w.source_doc_url
            for w in db.scalars(select(BoardUnitWeight))
        )
