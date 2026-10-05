"""Contextual lexical index: a passage that never names its own chapter is found by the chapter's words."""

from app.ingest.context import chunk_context
from app.ingest.probe import LexicalIndex


class _C:
    def __init__(self, cid, text, node, reference):
        self.chunk_id = self.id = cid
        self.text, self.node_id, self.reference, self.bucket = text, node, reference, "T"
        self.section_number = None


CHUNKS = [
    _C("a", "the modal class is the class with the greatest frequency either side", "N1",
       "Section 13.3 Mode of Grouped Data"),
    _C("b", "the lens forms an image at the focus of rays of light", "N2",
       "Section 10.1 Refraction by Spherical Lenses"),
] + [_C(f"p{i}", f"unrelated filler passage {i}", f"X{i}", f"ref {i}") for i in range(10)]
LABELS = {"N1": "Statistics", "N2": "Light"}


def test_the_context_is_the_chapter_title_and_the_chunks_own_reference():
    assert chunk_context(CHUNKS[0], LABELS.get) == "Statistics Section 13.3 Mode of Grouped Data"
    assert chunk_context(CHUNKS[0], lambda n: None) == "Section 13.3 Mode of Grouped Data"


def test_a_question_using_the_chapters_words_finds_a_passage_that_never_says_them():
    question = "statistics grouped data"
    plain = LexicalIndex(CHUNKS).search(question, k=3)
    ctx = LexicalIndex(CHUNKS, lambda c: chunk_context(c, LABELS.get)).search(question, k=3)
    assert plain == [], "the passage itself never names the chapter's subject"
    assert ctx and ctx[0].chunk_id == "a"


def test_the_shown_text_is_still_the_chunks_own():
    ctx = LexicalIndex(CHUNKS, lambda c: chunk_context(c, LABELS.get)).search("statistics", k=1)
    assert ctx[0].text == CHUNKS[0].text and "Statistics" not in ctx[0].text


def test_without_a_context_function_nothing_changes():
    a = LexicalIndex(CHUNKS).search("modal class frequency", k=2)
    b = LexicalIndex(CHUNKS, None).search("modal class frequency", k=2)
    assert a == b
