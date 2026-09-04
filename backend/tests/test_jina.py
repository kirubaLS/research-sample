"""app.ingest.jina.JinaEmbedder: what gets retried and what doesn't.

Real production bug: a 400 Bad Request (a genuinely bad payload -- wrong dimensions, a
chunk over the token limit, whatever Jina's own message says) was being retried three
times like a transient failure, and the response body that would have named the actual
reason was thrown away each time. What reached the operator was just "jina embedding
failed after 3 attempts" -- true, but useless. 429 and 5xx are the ones worth another try;
a 4xx is not going to succeed on attempt two with an identical payload.
"""

from __future__ import annotations

import httpx
import pytest

from app.ingest.jina import JinaEmbedder


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
