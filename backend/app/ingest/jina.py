"""Jina as the embedding provider.

Chosen for one reason the alternatives do not cover: the papers are bilingual (English and
Hindi in the same 2-up sheet) and Tamil papers are in scope, so the embedder has to be
genuinely multilingual. A local English-first model would quietly degrade on the Tamil
paper rather than fail, which is the worst shape of failure here.

The whole Class X Maths book is roughly 74,000 tokens -- well inside the free tier. Cost is
not a consideration at this scale; correctness across three scripts is.
"""

from __future__ import annotations

import time

import httpx

ENDPOINT = "https://api.jina.ai/v1/embeddings"

#: Matryoshka: the model emits 2048 dimensions and can be truncated with little loss.
#: 512 keeps a 213-chunk index small and comparisons fast, and is far above the point
#: where truncation starts to cost recall.
DEFAULT_DIMENSIONS = 512


class JinaEmbedder:
    """One batch call per request, with retries on the failures worth retrying."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "jina-embeddings-v4",
        dimensions: int = DEFAULT_DIMENSIONS,
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise ValueError(
                "no Jina API key. Set YAADHUM_JINA_API_KEY; without it the knowledge base "
                "can only answer exact matches, so three of the four familiarity levels "
                "collapse."
            )
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.timeout = timeout
        self.max_retries = max_retries

    def embed_texts(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        if not texts:
            return []

        payload = {
            "model": self.model,
            "dimensions": self.dimensions,
            # asymmetric retrieval: a short exam stem and a long book passage are encoded
            # differently, and using one task for both measurably costs recall
            "task": "retrieval.query" if is_query else "retrieval.passage",
            "input": [{"text": t} for t in texts],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = httpx.post(
                    ENDPOINT, json=payload, headers=headers, timeout=self.timeout
                )
                if response.status_code == 429 or response.status_code >= 500:
                    # rate limit or provider fault: worth another try
                    raise httpx.HTTPStatusError(
                        f"jina returned {response.status_code}",
                        request=response.request, response=response,
                    )
                if 400 <= response.status_code < 500:
                    # a client error (bad payload, invalid model/dimensions, a chunk over
                    # the token limit): retrying sends the same broken request three times
                    # and, worse, used to discard the response body, so the real reason
                    # never left this function -- fail on the first try and keep the body.
                    raise RuntimeError(
                        f"jina rejected the request: {response.status_code} {response.text}"
                    )
                response.raise_for_status()
                data = response.json()["data"]
                # the API does not promise input order, and a silently misaligned index
                # would attach every chunk's vector to a different chunk
                data.sort(key=lambda row: row["index"])
                return [row["embedding"] for row in data]
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last = exc
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)

        raise RuntimeError(f"jina embedding failed after {self.max_retries} attempts") from last
