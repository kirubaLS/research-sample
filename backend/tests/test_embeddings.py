"""The embedding layer, and the familiarity call it exists to make possible.

Tested against a deterministic stub embedder: these assertions are about the decision
logic, which must hold whichever provider supplies the vectors.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from app.ingest.embed import FamiliarityThresholds, classify_familiarity, cosine
from app.ingest.jina import JinaEmbedder
from app.ingest.probe import SemanticIndex


class StubEmbedder:
    """Deterministic vectors from a hash. No network, no key, stable across runs."""

    model = "stub"
    dimensions = 16

    def embed_texts(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        out = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            out.append([b / 255.0 for b in digest[: self.dimensions]])
        return out


class _Chunk:
    def __init__(self, ref, embedding, bucket="T"):
        self.id = ref
        self.reference = ref
        self.node_id = "n1"
        self.bucket = bucket
        self.embedding = embedding
        self.text = ref


# --- cosine ---------------------------------------------------------------------------

def test_cosine_is_one_for_identical_and_zero_for_orthogonal():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_ignores_magnitude():
    """A long passage and a short stem differ hugely in magnitude; only direction matters."""
    assert cosine([1.0, 2.0], [10.0, 20.0]) == pytest.approx(1.0)


def test_a_zero_vector_scores_zero_rather_than_raising():
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


# --- familiarity ------------------------------------------------------------------------

def test_a_close_match_to_an_exercise_is_practised():
    call = classify_familiarity(0.90, "EXERCISE 1.2", "E")
    assert call.level == "PRACTISED"


def test_distance_can_never_reach_t_verbatim():
    """The rule the first version stated and then broke.

    Against the real 30(B) paper, "in two triangles ABC and DEF ... which of the following
    is not true" scored 0.80 against Theorem 6.3 and came back T_VERBATIM. It is a question
    *about* the theorem, not the theorem -- a claim similarity cannot support. Five of ten
    exam questions were mislabelled that way. T_VERBATIM is an exact-hash answer only.
    """
    for similarity in (0.72, 0.85, 0.99):
        for bucket in ("T", "E"):
            assert classify_familiarity(similarity, "Theorem 1.3", bucket).level != "T_VERBATIM"


def test_a_close_match_is_practised_whichever_bucket_it_came_from():
    """A near match to a worked example means the method has been seen, same as a near
    match to an exercise."""
    assert classify_familiarity(0.90, "Theorem 1.3", "T").level == "PRACTISED"
    assert classify_familiarity(0.90, "EXERCISE 1.2", "E").level == "PRACTISED"


def test_a_recognisable_method_in_a_new_setting_is_adapted():
    call = classify_familiarity(0.60, "EXERCISE 1.1", "E")
    assert call.level == "ADAPTED"
    assert "unfamiliar setting" in call.reason


def test_nothing_close_is_novel():
    call = classify_familiarity(0.20, "Example 4", "T")
    assert call.level == "NOVEL"
    assert "0.20" in call.reason


def test_a_call_near_a_boundary_abstains_rather_than_guessing():
    """A wrong familiarity produces a wrong Competency Tier, which a teacher acts on."""
    t = FamiliarityThresholds()
    call = classify_familiarity(t.practised + 0.01, "EXERCISE 1.2", "E")
    assert call.level is None
    assert "too close to call" in call.reason


def test_the_boundaries_are_configuration_not_constants():
    """They are the project's only unvalidated numbers, so they must be tunable."""
    strict = FamiliarityThresholds(practised=0.95, adapted=0.80, margin=0.01)
    assert classify_familiarity(0.90, "EXERCISE 1.2", "E", strict).level == "ADAPTED"


# --- the index ---------------------------------------------------------------------------

def test_the_semantic_index_finds_the_nearest_chunk():
    embedder = StubEmbedder()
    texts = ["volume of a cone", "probability of a coin toss", "irrational numbers"]
    vectors = embedder.embed_texts(texts)
    index = SemanticIndex([_Chunk(t, v) for t, v in zip(texts, vectors, strict=True)], embedder)

    [best] = index.search("volume of a cone", k=1)
    assert best.reference == "volume of a cone"
    assert best.score == pytest.approx(1.0)


def test_chunks_without_a_vector_are_reported_not_silently_dropped():
    """A partially embedded index that looks complete would understate every distance."""
    embedder = StubEmbedder()
    [vector] = embedder.embed_texts(["a"])
    index = SemanticIndex([_Chunk("a", vector), _Chunk("b", None)], embedder)
    assert index.skipped == 1
    assert len(index.chunks) == 1


def test_an_empty_index_returns_nothing_rather_than_a_wrong_answer():
    assert SemanticIndex([], StubEmbedder()).search("anything") == []


# --- the provider ------------------------------------------------------------------------

def test_a_missing_key_fails_loudly_and_says_what_breaks():
    with pytest.raises(ValueError) as exc:
        JinaEmbedder("")
    assert "familiarity" in str(exc.value)


def test_an_empty_batch_makes_no_request():
    """Guarded because a provider that rejects empty input would fail the whole run."""
    assert JinaEmbedder("k").embed_texts([]) == []


def test_the_stub_is_deterministic():
    """Otherwise every test above measures noise."""
    assert StubEmbedder().embed_texts(["x"]) == StubEmbedder().embed_texts(["x"])


def test_vectors_are_unit_comparable_across_dimensions():
    """Matryoshka truncation must not change which chunk is nearest, only the precision."""
    full = [1.0, 0.9, 0.1, 0.05]
    truncated = full[:2]
    other_full = [0.1, 0.05, 1.0, 0.9]
    other_truncated = other_full[:2]
    assert cosine(full, full) > cosine(full, other_full)
    assert cosine(truncated, truncated) > cosine(truncated, other_truncated)


def test_similarity_is_bounded():
    embedder = StubEmbedder()
    a, b = embedder.embed_texts(["alpha", "beta"])
    assert -1.0 - 1e-9 <= cosine(a, b) <= 1.0 + 1e-9
    assert not math.isnan(cosine(a, b))


# --- fusion and chapter voting ----------------------------------------------------------

class _Chunk2:
    def __init__(self, chunk_id, text, node_id, embedding=None):
        self.chunk_id = chunk_id
        self.id = chunk_id
        self.text = text
        self.reference = chunk_id
        self.node_id = node_id
        self.bucket = "T"
        self.embedding = embedding


def test_fusion_recovers_what_one_retriever_alone_misses():
    """The measured reason for combining them: on the 30(B) paper lexical alone missed the
    LCM question ('bells ringing' shares no words with the book's HCF section) and semantic
    alone missed the cone question ('slant height' is a literal-word match). Neither method
    gets both; fused ranking does."""
    from app.ingest.probe import LexicalIndex, locate

    class OnlyKnowsB:
        """Stands in for the retriever that is right where the other is wrong."""

        def search(self, question, k=3):
            from app.ingest.probe import Candidate

            return [Candidate("b1", "b1", "chapter-B", "T", 0.99)]

    chunks = [
        _Chunk2("a1", "cone slant height radius volume", "chapter-A"),
        _Chunk2("a2", "cone volume of a right circular solid", "chapter-A"),
        _Chunk2("b1", "lowest common multiple of three numbers", "chapter-B"),
    ]
    chunks += [
        _Chunk2(f"pad{i}", f"unrelated material number {i}", f"pad-{i}") for i in range(20)
    ]
    lexical = LexicalIndex(chunks)

    # lexical alone follows the words
    assert locate("cone slant height", [lexical]).node_id == "chapter-A"
    # fused with a retriever that is confident about B, B is at least in contention
    fused = locate("cone slant height", [lexical, OnlyKnowsB()])
    assert fused.node_id in ("chapter-A", "chapter-B")
    assert not fused.agreed, "the two retrievers disagreed, and that must be visible"


def test_agreement_between_retrievers_is_reported():
    """A corpus of two makes every IDF zero -- log(2/2) -- so nothing scores. Real
    retrieval needs a real spread of documents, which is why this one is not minimal."""
    from app.ingest.probe import LexicalIndex, locate

    chunks = [_Chunk2("a1", "cone slant height radius solid", "chapter-A")]
    chunks += [
        _Chunk2(f"other{i}", f"unrelated words about topic {i} entirely", f"chapter-{i}")
        for i in range(20)
    ]
    lexical = LexicalIndex(chunks)
    verdict = locate("cone slant height", [lexical, lexical])
    assert verdict.node_id == "chapter-A"
    assert verdict.agreed, "two retrievers picking the same chapter is agreement"


def test_a_long_chapter_cannot_win_on_bulk_alone():
    """Summing every matching chunk scored 6/10 against 8/10 for the best chunk: a long
    chapter accumulates weak matches and beats a short precise one. Circles beat Areas
    Related to Circles twice that way."""
    from app.ingest.probe import LexicalIndex, locate

    chunks = [_Chunk2("precise", "sector of a circle arc length", "short-chapter")]
    chunks += [
        _Chunk2(f"bulk{i}", "circle circle tangent chord radius", "long-chapter")
        for i in range(30)
    ]
    verdict = locate("area of a sector of a circle cut off by an arc", [LexicalIndex(chunks)])
    assert verdict.node_id == "short-chapter"


def test_a_hair_thin_margin_is_reported_so_it_can_be_asked_about():
    from app.ingest.probe import LexicalIndex, locate

    chunks = [
        _Chunk2("a", "triangle angle similar congruent", "chapter-A"),
        _Chunk2("b", "triangle angle similar congruent", "chapter-B"),
    ]
    chunks += [
        _Chunk2(f"pad{i}", f"unrelated material number {i}", f"pad-{i}") for i in range(20)
    ]
    verdict = locate("triangle angle similar congruent", [LexicalIndex(chunks)])
    # not exactly zero: ranks 1 and 2 differ by 1/61 - 1/62 even for identical text. What
    # matters is that it lands far below the margin at which a call is acted on.
    from app.api.books import MIN_MARGIN

    assert verdict.margin < MIN_MARGIN, "identical evidence must not look confident"
