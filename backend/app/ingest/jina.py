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

#: Real production bug, hit twice: capping each Chunk's own size
#: (app.ingest.book.MAX_CHUNK_CHARS) was not enough -- /embed still 400'd with "Input text
#: exceeds the model's maximum of 32768 tokens" because Jina counts the WHOLE request's
#: input array against the ceiling, not each text separately, and embed_batch's caller
#: sends up to 32 chunks in one call. len(text) as the token estimate is meant to overcount
#: (roughly 4 chars/token for English), but a book already this session has been dense
#: Devanagari, whose conjunct clusters can run close to or past 1 token/char on a BPE
#: tokenizer -- the first, less conservative version of this budget (24,000) still turned
#: out to be too close to the real ceiling to trust. 12,000 leaves headroom even at a worse
#: ratio than anything observed so far, at the cost of nothing but an extra request or two
#: -- correctness, not request count, is what matters at this scale.
MAX_REQUEST_TOKENS = 12000


def _token_budget_batches(texts: list[str], max_tokens: int) -> list[list[int]]:
    """Group text indices so each group's estimated token count stays under budget.

    Indices, not texts: embed_texts needs to reassemble the caller's original order across
    however many HTTP calls this takes, and indices are what let it do that without
    re-sorting or re-matching text content.
    """
    batches: list[list[int]] = []
    current: list[int] = []
    current_tokens = 0
    for i, text in enumerate(texts):
        estimate = max(len(text), 1)
        if current and current_tokens + estimate > max_tokens:
            batches.append(current)
            current, current_tokens = [], 0
        current.append(i)
        current_tokens += estimate
    if current:
        batches.append(current)
    return batches


class JinaEmbedder:
    """Retries the failures worth retrying, and never sends a request estimated to be over
    Jina's own token ceiling in the first place."""

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

        # A chunk already sitting in book_chunk can predate app.ingest.book.MAX_CHUNK_CHARS
        # -- that cap only stops an oversized Chunk from being CREATED, it does nothing for
        # one a still-earlier upload already wrote to the database, and that row is exactly
        # what /embed reads back. A single one of those is over budget on its own, so no
        # amount of grouping by _token_budget_batches below helps it -- it still has to
        # shrink, or every batch containing it keeps 400ing forever. Only what is SENT to
        # Jina is trimmed; the chunk's own stored text is untouched, so nothing here can
        # rewrite what a re-ingest of that chapter would produce.
        sendable = [t if len(t) <= MAX_REQUEST_TOKENS else t[:MAX_REQUEST_TOKENS] for t in texts]

        vectors: list[list[float] | None] = [None] * len(texts)
        for indices in _token_budget_batches(sendable, MAX_REQUEST_TOKENS):
            batch_vectors = self._embed_request(
                [sendable[i] for i in indices], is_query=is_query
            )
            for i, vector in zip(indices, batch_vectors, strict=True):
                vectors[i] = vector
        assert all(v is not None for v in vectors)
        return vectors  # type: ignore[return-value]

    def _embed_request(self, texts: list[str], *, is_query: bool) -> list[list[float]]:
        """One HTTP call, for a batch already known to fit inside the token budget."""
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
                    # rate limit or provider fault: worth another try, but the body still
                    # belongs in the message -- the final "failed after 3 attempts" is
                    # this exception's str(), and a bare status code without it is exactly
                    # the "true but useless" message this module has already had to fix
                    # once for the non-retried 4xx case.
                    raise httpx.HTTPStatusError(
                        f"jina returned {response.status_code}: {response.text}",
                        request=response.request, response=response,
                    )
                if 400 <= response.status_code < 500:
                    # a client error (bad payload, invalid model/dimensions, a request over
                    # the token limit despite the estimate above): retrying sends the same
                    # broken request three times and, worse, used to discard the response
                    # body, so the real reason never left this function -- fail on the
                    # first try and keep the body.
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

        # `from last` chains the cause in a traceback, but embed_batch only surfaces
        # str(exc) to the operator (see app.api.books) -- without the reason folded into
        # the message itself, "failed after 3 attempts" was all that ever reached them,
        # true but as useless as the 400 case this same fix already covered once.
        raise RuntimeError(
            f"jina embedding failed after {self.max_retries} attempts: {last}"
        ) from last
