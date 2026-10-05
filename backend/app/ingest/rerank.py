"""A cross-encoder reranker: does this passage actually answer this question?

Retrieval scores a question and a passage separately and compares the numbers; a
cross-encoder reads the two together, which is why a reranker on a retrieval shortlist
recovers failures the first stage cannot (Anthropic's contextual-retrieval evaluation:
contextual embeddings, BM25 and a reranker together took the top-20 retrieval failure rate
from 5.7% to 1.9%). It is
also the cheap kind of second reader. An LLM used pointwise as a reranker costs about ten
times as much and is less accurate than a purpose-built cross-encoder, so this is a
cross-encoder and not a prompt.

Same provider, same key and the same concurrency gate as the embedder, so a run that
embeds and reranks from many threads queues instead of being refused.
"""

from __future__ import annotations

import time

import httpx

from app.ingest.jina import _GATE

ENDPOINT = "https://api.jina.ai/v1/rerank"
DEFAULT_MODEL = "jina-reranker-v2-base-multilingual"
#: characters of one passage sent. The reranker reads a window; the useful signal is at the
#: start of a passage, as everywhere else in this codebase.
MAX_DOC_CHARS = 1500


class JinaReranker:
    def __init__(self, api_key: str, *, model: str = DEFAULT_MODEL, timeout: float = 30.0,
                 max_retries: int = 3) -> None:
        if not api_key:
            raise ValueError("no Jina API key; set YAADHUM_JINA_API_KEY to rerank")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def _post(self, payload: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}",
                   "Content-Type": "application/json"}
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                with _GATE:
                    response = httpx.post(ENDPOINT, json=payload, headers=headers,
                                          timeout=self.timeout)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"jina rerank returned {response.status_code}: {response.text}",
                        request=response.request, response=response)
                if 400 <= response.status_code < 500:
                    raise RuntimeError(
                        f"jina rejected the rerank: {response.status_code} {response.text}")
                return response.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last = exc
                if attempt < self.max_retries - 1:
                    time.sleep(min(2**attempt, 10))
        raise RuntimeError(f"jina rerank failed after {self.max_retries} attempts: {last}")

    def scores(self, query: str, documents: list[str]) -> list[float]:
        """One relevance score per document, in the documents' own order."""
        if not documents:
            return []
        data = self._post({
            "model": self.model, "query": query,
            "documents": [d[:MAX_DOC_CHARS] for d in documents],
            "top_n": len(documents),
        })
        out = [0.0] * len(documents)
        for row in data["results"]:
            out[row["index"]] = float(row["relevance_score"])
        return out
