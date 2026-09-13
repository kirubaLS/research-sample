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


def test_science_chapters_come_from_the_contents_page_in_book_order():
    """The rationalised syllabus renumbered the book and secondary sources disagree, so the
    contents page of Reprint 2026-27 decides -- thirteen chapters, page xi.

    Order is load-bearing: chapter_title() resolves jesc108.pdf by position, so a row
    inserted or moved silently retitles a chapter, and every question placed in it lands
    under the wrong heading in the report.
    """
    from app.curriculum import X_SCIENCE, chapter_title

    assert len(X_SCIENCE.chapters) == 13
    assert chapter_title("X.SCI", 1) == "Chemical Reactions and Equations"
    assert chapter_title("X.SCI", 8) == "Heredity"
    assert chapter_title("X.SCI", 9) == "Light \u2013 Reflection and Refraction"
    assert chapter_title("X.SCI", 13) == "Our Environment"
    assert chapter_title("X.SCI", 14) is None


def test_every_science_chapter_maps_to_a_unit_the_board_actually_weights():
    """A chapter pointing at a unit that does not exist drops its marks out of the
    board-impact figure entirely, and the figure still renders -- which is the dangerous
    part. Both directions are checked: no orphan chapter, and no unit left untested."""
    from app.curriculum import X_SCIENCE

    units = {u.code for u in X_SCIENCE.units}
    assert {c.board_unit for c in X_SCIENCE.chapters} == units
    assert all(c.board_unit in units for c in X_SCIENCE.chapters)
    assert len({c.code for c in X_SCIENCE.chapters}) == 13

    by_unit: dict[str, int] = {}
    for c in X_SCIENCE.chapters:
        by_unit[c.board_unit] = by_unit.get(c.board_unit, 0) + 1
    assert by_unit == {
        "X.SCI.U.CHEMICAL": 4, "X.SCI.U.LIVING": 4,
        "X.SCI.U.PHENOMENA": 2, "X.SCI.U.CURRENT": 2, "X.SCI.U.RESOURCES": 1,
    }


def test_science_declares_no_concept_families_until_its_book_is_read():
    """Families are proposed from the book's own section headings once the chapters are
    embedded, then reviewed. Inventing them ahead of the text is the creativity this
    pipeline is built to refuse."""
    from app.curriculum import X_SCIENCE

    assert X_SCIENCE.concept_families == []


def test_applying_the_science_curriculum_sets_up_its_units_and_chapters(tmp_path):
    """Units carry the board's marks; chapters carry the mapping into them."""
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
        assert created["chapters"] == 13
        assert db.scalar(
            select(func.count(TaxonomyNode.id)).where(TaxonomyNode.kind == "board_unit")
        ) == 5
        # every unit carries its citation, because a principal will challenge these
        assert all(
            w.source_doc_url
            for w in db.scalars(select(BoardUnitWeight))
        )


def test_a_heading_the_book_shouts_is_not_a_family_name():
    """Science prints its section headings in full capitals. Carried through, the report
    would say the student is weak at 'HOW DO OUR ACTIVITIES AFFECT THE ENVIRONMENT?'."""
    from app.curriculum.families import propose, readable

    assert readable("HOW DO OUR ACTIVITIES AFFECT THE ENVIRONMENT?") == (
        "How do our activities affect the environment?"
    )
    assert readable("OHM’S LAW") == "Ohm’s law"
    assert readable("ECO-SYSTEM — WHAT ARE ITS COMPONENTS?") == (
        "Eco-system — what are its components?"
    )
    # Maths already sets its headings properly and must come through untouched.
    assert readable("Volume of a Combination of Solids") == "Volume of a Combination of Solids"

    [p] = propose(
        [("X.SCI.ELECTRICITY", "Electricity", "12.5", "ELECTRIC POWER", 3)], "X.SCI"
    )
    assert p.label == "Electric power"
    # The code is derived from the words, so it is unaffected by the casing fix.
    assert p.code == "X.SCI.CF.ELECTRIC_POWER"


def test_a_long_label_is_cut_at_a_word_and_kept_unique():
    """Codes are never renamed, so a bad one is permanent. A plain character cut severed
    words -- 'Trigonometric ratios of standard angles (0 deg, 30 deg, ...)' ended
    ...ANGLES_0_3, which reads as nought point three."""
    from app.curriculum.families import CODE_CHARS, slugify

    code = slugify("Trigonometric ratios of standard angles (0°, 30°, 45°, 60°, 90°)")
    assert len(code) <= CODE_CHARS
    assert not code.endswith("_")
    assert code.startswith("TRIGONOMETRIC_RATIOS_STANDARD_")


def test_two_labels_sharing_a_long_prefix_do_not_become_one_code():
    """The dangerous case: one code for two families silently merges two trends into one
    report row, and nothing downstream can tell."""
    from app.curriculum.families import slugify

    a = slugify("Finding heights and distances using angles of elevation from a tower")
    b = slugify("Finding heights and distances using angles of elevation from a cliff")
    assert a != b
    assert a.startswith("FINDING_HEIGHTS_DISTANCES_USING_")


def test_a_label_that_fits_is_left_exactly_as_it_was():
    """Most labels fit, including every family created so far. Adding a digest to those
    would change codes already applied, which is the one thing this must never do."""
    from app.curriculum.families import slugify

    assert slugify("Volume of composite solids") == "VOLUME_COMPOSITE_SOLIDS"
    assert slugify("Area of a sector") == "AREA_SECTOR"
    assert slugify("Corrosion") == "CORROSION"


def test_the_digest_is_stable_across_runs():
    """A code that changed between runs would fork the trend it exists to hold together."""
    from app.curriculum.families import slugify

    label = "Mean for grouped data using step-deviation method"
    assert slugify(label) == slugify(label) == "MEAN_FOR_GROUPED_DATA_USING_STEP_1010A8"


def test_a_proposed_family_records_the_section_number_not_its_heading():
    """The number is what a question's section is matched against.

    Recording the heading instead made that comparison one that could never succeed, so a
    chapter with two families blocked every question in it for want of a choice.
    """
    from app.curriculum.families import propose

    [p] = propose(
        [("X.MATH.STATS", "Statistics", "13.2", "Mean of Grouped Data", 7)], "X.MATH"
    )
    assert p.from_section == "13.2"
    assert p.label == "Mean of Grouped Data"


def test_the_classifier_request_is_one_its_configured_model_accepts():
    """The settings and the call have to agree, or the paper fails on a paid request.

    Two ways they can disagree, both silent until the money is spent: an effort level sent
    to a model that rejects it, and a token ceiling sized for the answer alone on a model
    that thinks before answering -- thinking counts against the same ceiling, so the reply
    is truncated mid-thought.
    """
    import inspect

    from app.classify.anthropic_judge import AnthropicJudge
    from app.config import get_settings
    from app.llm import output_config

    settings = get_settings()
    judge = AnthropicJudge.__new__(AnthropicJudge)
    judge.output_config = output_config(settings.model_classifier, settings.model_effort)

    # Either the model takes effort and gets it, or it does not and the keyword is dropped
    # entirely -- never sent empty.
    assert judge.output_config in (None, {"effort": settings.model_effort})

    source = inspect.getsource(AnthropicJudge.classify)
    ceiling = int(
        source.split("max_tokens=")[1].split(",")[0].replace("_", "")
    )
    assert ceiling >= 8000, "leaves no room for the reasoning the model does first"
    # Sampling parameters and a fixed thinking budget are rejected outright by the current
    # models. Neither has any business in a structured-output call anyway.
    for rejected in ("temperature", "top_p", "top_k", "budget_tokens"):
        assert rejected not in source


def test_the_reader_is_shown_the_chapters_that_were_in_contention():
    """It is asked to choose one chapter from the candidates it is given.

    It was given one: the passages all came from the chapter retrieval had already picked,
    so the reading could never correct it. Correcting it is the whole reason the step
    exists -- similarity picks the chapter full of right triangles for a cone, and only a
    reader shown both can say otherwise.
    """
    from app.classify.judge import Evidence, build_prompt
    from app.ingest.probe import LexicalIndex, locate

    class Chunk:
        def __init__(self, cid, text, node):
            self.chunk_id = self.id = cid
            self.text = self.reference = text if len(text) < 40 else cid
            self.text = text
            self.node_id = node
            self.bucket = "T"
            self.embedding = None
            self.section_number = None

    chunks = [
        Chunk("m1", "cone slant height radius volume of a solid combination", "SAV"),
        Chunk("m2", "surface area of a combination of solids cone hemisphere", "SAV"),
        Chunk("t1", "tower height angle of elevation observer slant", "APPTRIG"),
        Chunk("t2", "line of sight horizontal angle of elevation height", "APPTRIG"),
    ]
    chunks += [Chunk(f"p{i}", f"unrelated topic {i}", f"P{i}") for i in range(20)]

    # A query both chapters score on, which is the case the reading exists to settle:
    # "slant height" is a cone, "angle of elevation" is trigonometry, and similarity alone
    # sees a right triangle in both.
    verdict = locate(
        "slant height angle of elevation", [LexicalIndex(chunks)],
        evidence_passages=6, evidence_chapters=3,
    )
    shown = {c.node_id for c in verdict.evidence}
    assert len(shown) > 1, "only the winner's passages were shown"
    assert "APPTRIG" in shown, "the rival chapter never reached the reader"

    # And the prompt says so, which is what the model is choosing between.
    names = {"SAV": "Surface Areas and Volumes", "APPTRIG": "Applications of Trigonometry"}
    prompt = build_prompt("slant height angle of elevation", [
        Evidence(chapter=names[c.node_id], section="", reference=c.reference, text=c.text)
        for c in verdict.evidence
    ])
    line = next(l for l in prompt.splitlines() if l.startswith("CANDIDATE CHAPTERS"))
    assert "Surface Areas and Volumes" in line and "Applications of Trigonometry" in line

    # And the passages are actually in it. They were not: the candidate carried a
    # reference and a score and no text, so the prompt said "PASSAGES FROM THE BOOK" with
    # nothing under it and the reading was a guess from two chapter names.
    assert "angle of elevation" in prompt
    assert "volume of a solid combination" in prompt


def test_how_much_of_a_passage_the_reader_sees_is_a_setting_not_a_constant():
    """It is the price of the call and the quality of the answer at once."""
    from app.classify.judge import Evidence, build_prompt

    long_passage = "a" * 5000
    ev = [Evidence(chapter="Statistics", section="13.2", reference="Section 13.2",
                   text=long_passage)]
    assert len(build_prompt("q", ev, 400)) < len(build_prompt("q", ev, 1200))


def test_every_setting_the_deployment_declares_is_one_the_app_reads():
    """A name without the prefix is read by nothing.

    The blueprint declared ANTHROPIC_API_KEY. Settings read YAADHUM_ANTHROPIC_API_KEY, so
    the key would have sat in the dashboard looking present while classification refused
    for want of one -- a failure with no symptom except the refusal it causes.
    """
    from pathlib import Path

    import yaml

    from app.config import Settings

    blueprint = Path(__file__).resolve().parents[2] / "render.yaml"
    if not blueprint.exists():                      # not every checkout ships it
        return

    prefix = Settings.model_config["env_prefix"]
    known = {f"{prefix}{name}".upper() for name in Settings.model_fields}

    declared = [
        entry["key"]
        for service in yaml.safe_load(blueprint.read_text())["services"]
        for entry in service.get("envVars", [])
        if entry["key"].upper().startswith(prefix)
        or "ANTHROPIC" in entry["key"].upper()
        or "JINA" in entry["key"].upper()
    ]
    unread = [key for key in declared if key.upper() not in known]
    assert not unread, f"declared to the deployment and read by nothing: {unread}"
