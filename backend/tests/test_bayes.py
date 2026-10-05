"""The trained chapter classifier and its place as a gate reader. No model, no network."""

from __future__ import annotations

from app.classify.bayes import NaiveBayesChapters
from app.classify.judge import Classification
from app.classify.pipeline import PassOptions, place_paper
from app.ingest.probe import LexicalIndex

TRAIN = [
    ("Circles", "tangent to a circle is perpendicular to the radius through the point of contact", 1),
    ("Circles", "chord secant tangent radius circle theorem proof length of tangent", 1),
    ("Statistics", "mean median mode of grouped data class frequency cumulative", 1),
    ("Statistics", "the modal class has the greatest frequency in the data distribution", 1),
]


def _model():
    return NaiveBayesChapters().fit(TRAIN)


def test_it_names_the_chapter_whose_vocabulary_the_question_uses():
    chapter, posterior = _model().predict("Prove that the tangent at a point of a circle is perpendicular")
    assert chapter == "Circles" and posterior > 0.9
    chapter, _ = _model().predict("Find the mode of the frequency distribution")
    assert chapter == "Statistics"


def test_it_only_chooses_among_the_allowed_chapters():
    assert _model().predict("tangent circle radius", allowed={"Statistics"}) == ("Statistics", 1.0)
    assert _model().predict("tangent circle radius", allowed={"Statistics", "Circles"})[0] == "Circles"


def test_it_abstains_on_words_it_has_never_seen():
    assert _model().predict("quantum chromodynamics gluon")[0] is None
    assert NaiveBayesChapters().predict("tangent")[0] is None


def test_a_confirmed_question_counts_for_more_than_a_book_passage():
    def trained(w_stats, w_circles):
        return NaiveBayesChapters().fit([
            ("Statistics", "zebra mean", w_stats), ("Circles", "zebra radius", w_circles)])

    assert trained(3, 1).predict("zebra")[0] == "Statistics"
    assert trained(1, 3).predict("zebra")[0] == "Circles"


# --- as a reader of the gate ---------------------------------------------------------------


class _Chunk:
    def __init__(self, cid, text, node):
        self.chunk_id = self.id = cid
        self.text, self.node_id, self.reference, self.bucket = text, node, cid, "T"
        self.embedding = None
        self.section_number = None


NAMES = {"G1": "Circles", "H1": "Statistics"}


def _corpus():
    chunks = [
        _Chunk("g1a", "tangent circle radius perpendicular point contact tangent", "G1"),
        _Chunk("g1b", "circle tangent radius theorem proof", "G1"),
        _Chunk("h1a", "mean mode median grouped data frequency", "H1"),
    ]
    return chunks + [_Chunk(f"pad{i}", f"unrelated filler topic {i}", f"X{i}") for i in range(20)]


class _Judge:
    def __init__(self):
        self.seen = 0

    def classify(self, question, evidence, *, scoped=False, examples=None):
        self.seen += 1
        return Classification(chapter="Circles", curriculum_section=None, tier=None,
                              skill_required="", reasoning="s", evidence=[], confidence=0.9,
                              alternative_chapter=None)


def _run(classifier, stem="tangent circle radius perpendicular"):
    judge, log = _Judge(), {}
    place_paper(
        [("q", stem, 1.0)], [LexicalIndex(_corpus()), LexicalIndex(_corpus())], judge,
        chapter_of=NAMES.get, unit_of=NAMES.get, section_of=lambda r: None,
        evidence_passages=4, evidence_chapters=2,
        options=PassOptions(gate=True, gate_log=log, gate_min_margin=0.0,
                            gate_classifier=classifier),
    )
    return log


def test_a_classifier_confident_of_another_chapter_vetoes_the_gate():
    wrong = NaiveBayesChapters().fit([("Statistics", "tangent circle radius perpendicular", 5),
                                      ("Circles", "mean mode median", 5)])
    log = _run(wrong)
    assert not log["q"]["passed"] and "classifier prefers Statistics" in log["q"]["reason"]


def test_a_classifier_that_agrees_lets_the_gate_pass():
    assert _run(_model())["q"]["passed"]


def test_a_classifier_with_nothing_to_say_neither_places_nor_refuses():
    unrelated = NaiveBayesChapters().fit([("Statistics", "alpha", 1), ("Circles", "beta", 1)])
    assert _run(unrelated)["q"]["passed"]
