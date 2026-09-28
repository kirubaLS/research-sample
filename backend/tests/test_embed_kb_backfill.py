"""scripts.embed_kb: the backfill for BookChunk rows that import_book_map.py wrote without
an embedding (Fix 3 of the /map accuracy audit).

The chunk shape import_book_map.py produces is a plain BookChunk -- identical to any other
subject's -- so this proves the *generic* script against that shape rather than adding a
one-off. httpx.post is faked the same way tests/test_jina.py fakes it: no real Jina call.
"""

from __future__ import annotations

import hashlib

import httpx
import pytest


def _fake_semantic_vector(text: str, dimensions: int = 8) -> list[float]:
    """A deterministic, content-sensitive vector -- close for related text, far for
    unrelated text -- so a retrieval test on it means something, unlike a pure hash."""
    words = set(text.lower().split())
    keys = ["river", "himalaya", "monsoon", "plateau", "delta", "glacier", "climate", "soil"]
    return [1.0 if k in words else 0.0 for k in keys][:dimensions] or [0.0]


@pytest.fixture
def book_map_chunks(school, monkeypatch):
    """Two chunks shaped exactly as import_book_map.py writes them: no embedding set."""
    from app.db import SessionLocal
    from app.models import BookChunk

    db = SessionLocal()
    a = BookChunk(
        curriculum_version="2024", subject_code="X.GEO", node_id=None, bucket="T",
        reference="9.2", section_number="9.2",
        text="the himalaya is a young fold mountain formed by river and glacier action",
        normalised="the himalaya is a young fold mountain formed by river and glacier action",
        stem_hash=hashlib.sha256(b"himalaya-chunk").hexdigest(),
    )
    b = BookChunk(
        curriculum_version="2024", subject_code="X.GEO", node_id=None, bucket="E",
        reference="9.5", section_number="9.5",
        text="monsoon rainfall and climate patterns across the deccan plateau",
        normalised="monsoon rainfall and climate patterns across the deccan plateau",
        stem_hash=hashlib.sha256(b"monsoon-chunk").hexdigest(),
    )
    # a third chunk that is already embedded -- must be left untouched (idempotency)
    already = BookChunk(
        curriculum_version="2024", subject_code="X.GEO", node_id=None, bucket="T",
        reference="9.1", section_number="9.1",
        text="river delta formation at the mouth of a river",
        normalised="river delta formation at the mouth of a river",
        stem_hash=hashlib.sha256(b"delta-chunk").hexdigest(),
        embedding=[9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0],
    )
    db.add_all([a, b, already])
    db.commit()
    ids = (a.id, b.id, already.id)
    db.close()

    def fake_post(url, *, json, headers, timeout):
        request = httpx.Request("POST", url)
        data = [
            {"index": i, "embedding": _fake_semantic_vector(item["text"])}
            for i, item in enumerate(json["input"])
        ]
        return httpx.Response(200, request=request, json={"data": data})

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv("YAADHUM_JINA_API_KEY", "test-key")
    from app.config import get_settings
    get_settings.cache_clear()

    yield ids

    db = SessionLocal()
    from app.models import BookChunk
    db.query(BookChunk).filter(BookChunk.subject_code == "X.GEO").delete()
    db.commit()
    db.close()
    get_settings.cache_clear()


def test_backfill_embeds_chunks_that_have_none(book_map_chunks):
    from scripts.embed_kb import main

    a_id, b_id, already_id = book_map_chunks
    import sys
    old_argv = sys.argv
    sys.argv = ["embed_kb", "--subject", "X.GEO"]
    try:
        main()
    finally:
        sys.argv = old_argv

    from app.db import SessionLocal
    from app.models import BookChunk

    db = SessionLocal()
    a = db.get(BookChunk, a_id)
    b = db.get(BookChunk, b_id)
    already = db.get(BookChunk, already_id)
    assert a.embedding is not None
    assert b.embedding is not None
    # idempotency: the pre-existing vector was not touched or re-requested
    assert already.embedding == [9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0]
    db.close()


def test_backfill_is_idempotent_on_a_second_run(book_map_chunks, monkeypatch):
    from scripts.embed_kb import main
    import sys

    old_argv = sys.argv
    sys.argv = ["embed_kb", "--subject", "X.GEO"]
    try:
        main()
    finally:
        sys.argv = old_argv

    call_count = []
    real_post = httpx.post

    def counting_post(url, *, json, headers, timeout):
        call_count.append(len(json["input"]))
        return real_post(url, json=json, headers=headers, timeout=timeout)

    monkeypatch.setattr(httpx, "post", counting_post)

    sys.argv = ["embed_kb", "--subject", "X.GEO"]
    try:
        main()  # nothing left to embed -- should make zero requests
    finally:
        sys.argv = old_argv

    assert call_count == [], "a fully embedded subject must send no further requests"


def test_the_resulting_embedding_is_usable_by_semantic_retrieval(book_map_chunks):
    """Not just 'a JSON blob got written' -- proves SemanticIndex can now match a
    semantically-related but lexically-different query, which is the whole point of the
    backfill: /map degrading to lexical-only is exactly the gap this closes."""
    from scripts.embed_kb import main
    import sys

    old_argv = sys.argv
    sys.argv = ["embed_kb", "--subject", "X.GEO"]
    try:
        main()
    finally:
        sys.argv = old_argv

    class FakeQueryEmbedder:
        model = "fake"
        dimensions = 8

        def embed_texts(self, texts, *, is_query=False):
            return [_fake_semantic_vector(t) for t in texts]

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.ingest.probe import SemanticIndex
    from app.models import BookChunk

    db = SessionLocal()
    chunks = db.scalars(select(BookChunk).where(BookChunk.subject_code == "X.GEO")).all()
    db.close()

    index = SemanticIndex(chunks, FakeQueryEmbedder())
    assert index.skipped == 0, "every chunk, including the pre-existing one, must be searchable"

    # lexically this shares almost no words with the himalaya chunk's text, but both are
    # about "glacier" -- the shared concept the fake embedder encodes
    [best] = index.search("what causes glacier melt in mountain regions", k=1)
    assert best.reference == "9.2"
