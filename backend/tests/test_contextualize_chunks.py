from types import SimpleNamespace

from app.ingest.context import chunk_context
from scripts.contextualize_chunks import (
    MAX_CONTEXT_CHARS,
    chapter_document,
    clean,
    contextualize,
    estimate,
    request_for,
)


def _c(cid, text, ref="Section 13.3", context=None):
    return SimpleNamespace(id=cid, text=text, reference=ref, section_number="13.3",
                           node_id="N", context=context)


class _Client:
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []
        self.messages = self

    def create(self, **kw):
        self.requests.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=r)])


def test_the_chapter_is_the_cached_block_and_the_chunk_is_the_question():
    chunks = [_c("a", "modal class text"), _c("b", "median text")]
    req = request_for("Statistics", chapter_document(chunks), chunks[0])
    cached = req["system"][1]
    assert cached["cache_control"] == {"type": "ephemeral"}
    assert "CHAPTER: Statistics" in cached["text"] and "median text" in cached["text"]
    assert "modal class text" in req["messages"][0]["content"]


def test_each_chunk_gets_its_own_context_and_failures_are_skipped_not_guessed():
    chunks = [_c("a", "x"), _c("b", "y"), _c("c", "z")]
    out = contextualize(_Client([' "About the mode of grouped data." ', RuntimeError("boom"),
                                 "Median."]), "m", "Statistics", chunks)
    assert out == {"a": "About the mode of grouped data.", "c": "Median."}


def test_a_chunk_that_already_has_context_is_not_asked_again():
    client = _Client(["new"])
    out = contextualize(client, "m", "S", [_c("a", "x", context="kept"), _c("b", "y")])
    assert list(out) == ["b"] and len(client.requests) == 1


def test_context_is_clipped_to_the_column():
    assert len(clean("w " * 500)) <= MAX_CONTEXT_CHARS


def test_the_estimate_counts_only_what_is_left_to_do_and_reads_the_cache_for_the_rest():
    chunks = [_c(str(i), "word " * 400) for i in range(10)]
    plan = estimate({"N": chunks}, "claude-haiku-4-5")
    assert plan["chunks"] == 10 and plan["cache_read_tokens"] > plan["cache_write_tokens"]
    done = [_c(str(i), "word " * 400, context="x") for i in range(10)]
    assert estimate({"N": done}, "claude-haiku-4-5")["chunks"] == 0


def test_the_written_context_joins_the_index_text_but_is_optional():
    chunk = _c("a", "t", context="About the mode of grouped data.")
    assert chunk_context(chunk, lambda n: "Statistics") == (
        "Statistics Section 13.3 About the mode of grouped data.")
    assert chunk_context(_c("b", "t"), lambda n: "Statistics") == "Statistics Section 13.3"
