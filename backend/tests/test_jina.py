"""app.ingest.jina.JinaEmbedder: what gets retried and what doesn't, and the token-budget
batching that keeps a request under Jina's own ceiling.

Real production bug, in two parts. First: a 400 Bad Request (a genuinely bad payload --
wrong dimensions, a request over the token limit, whatever Jina's own message says) was
being retried three times like a transient failure, and the response body that would have
named the actual reason was thrown away each time. What reached the operator was just
"jina embedding failed after 3 attempts" -- true, but useless. 429 and 5xx are the ones
worth another try; a 4xx is not going to succeed on attempt two with an identical payload.

Second, once that fix let the real message through: "Input text exceeds the model's
maximum of 32768 tokens" kept firing even after every individual chunk was capped well
under that (app.ingest.book.MAX_CHUNK_CHARS). Jina counts the WHOLE request's input array
against the ceiling, not each text separately -- embed_batch sends up to 32 chunks in one
call, and their combined length is what was blowing the limit. embed_texts now splits into
several HTTP calls by an estimated token budget across the batch, not just per item.
"""

from __future__ import annotations

import httpx
import pytest

from app.ingest.jina import JinaEmbedder, _token_budget_batches


def test_a_bad_request_fails_on_the_first_try_and_keeps_jinas_own_message(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append(1)
        request = httpx.Request("POST", url)
        return httpx.Response(400, request=request, text='{"detail":"dimensions must be one of [128,256,512,1024,2048]"}')

    monkeypatch.setattr(httpx, "post", fake_post)
    embedder = JinaEmbedder("key")

    with pytest.raises(RuntimeError, match="dimensions must be one of"):
        embedder.embed_texts(["some chunk text"])
    assert len(calls) == 1


def test_a_rate_limit_is_retried(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append(1)
        request = httpx.Request("POST", url)
        if len(calls) < 3:
            return httpx.Response(429, request=request, text="rate limited")
        return httpx.Response(
            200, request=request,
            json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("app.ingest.jina.time.sleep", lambda s: None)
    embedder = JinaEmbedder("key")

    vectors = embedder.embed_texts(["some chunk text"])
    assert vectors == [[0.1, 0.2]]
    assert len(calls) == 3


def test_a_server_error_is_retried_and_still_fails_after_max_retries(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append(1)
        request = httpx.Request("POST", url)
        return httpx.Response(500, request=request, text="upstream error")

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("app.ingest.jina.time.sleep", lambda s: None)
    embedder = JinaEmbedder("key", max_retries=3)

    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        embedder.embed_texts(["some chunk text"])
    assert len(calls) == 3


def test_a_batch_over_the_token_budget_is_split_into_several_requests(monkeypatch):
    """32 chunks of ~6,000 characters each -- exactly what embed_batch's default limit=32
    against MAX_CHUNK_CHARS sends -- is well over MAX_REQUEST_TOKENS in one call, the real
    shape of the production 400."""
    texts = ["अ" * 6000 for _ in range(32)]
    request_sizes = []

    def fake_post(url, *, json, headers, timeout):
        request_sizes.append(len(json["input"]))
        request = httpx.Request("POST", url)
        return httpx.Response(
            200, request=request,
            json={
                "data": [
                    {"index": i, "embedding": [float(i)]}
                    for i in range(len(json["input"]))
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    embedder = JinaEmbedder("key")

    vectors = embedder.embed_texts(texts)

    assert len(request_sizes) > 1, "one request for 192,000 characters should never happen"
    assert len(vectors) == 32
    assert all(size <= 2 for size in request_sizes)


def test_order_is_preserved_across_multiple_requests(monkeypatch):
    texts = ["अ" * 6000 for _ in range(32)]

    def fake_post(url, *, json, headers, timeout):
        request = httpx.Request("POST", url)
        # each item's embedding encodes which text it actually is, out of request order
        return httpx.Response(
            200, request=request,
            json={
                "data": [
                    {"index": i, "embedding": [hash(t) % 1000]}
                    for i, t in enumerate(json["input"])
                    for t in [t["text"]]
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    embedder = JinaEmbedder("key")

    vectors = embedder.embed_texts(texts)
    expected = [[hash(t) % 1000] for t in texts]
    assert vectors == expected


def test_token_budget_batches_never_exceeds_the_estimate(monkeypatch):
    texts = ["x" * 1000, "y" * 30000, "z" * 500]
    batches = _token_budget_batches(texts, max_tokens=24000)
    # the 30,000-char text is over budget on its own -- it still gets sent, alone, rather
    # than being silently dropped or merged with something else
    assert [sorted(b) for b in batches] == [[0], [1], [2]]


def test_a_chunk_already_in_the_database_from_before_the_size_cap_is_truncated_not_rejected(
    monkeypatch,
):
    """The retroactive case: app.ingest.book.MAX_CHUNK_CHARS only stops a NEW Chunk from
    being created oversized -- it does nothing for one an earlier upload already wrote to
    book_chunk, and that row is exactly what /embed reads back and sends here. On its own
    in a batch of one, grouping by budget can't shrink it; it has to be trimmed to fit."""
    huge = "अ" * 50_000
    sent_lengths = []

    def fake_post(url, *, json, headers, timeout):
        sent_lengths.append(len(json["input"][0]["text"]))
        request = httpx.Request("POST", url)
        return httpx.Response(
            200, request=request, json={"data": [{"index": 0, "embedding": [1.0]}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    embedder = JinaEmbedder("key")

    vectors = embedder.embed_texts([huge])

    assert vectors == [[1.0]]
    assert sent_lengths == [12000]
