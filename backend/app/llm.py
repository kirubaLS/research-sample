"""Request options shared by every Anthropic call in the pipeline.

One module rather than a keyword repeated at each call site, because the rule it encodes
is not obvious and getting it wrong fails at runtime, in production, on a paid request.
"""

from __future__ import annotations

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

#: Model families that accept ``output_config.effort``. An allowlist, not a denylist: an
#: unknown model gets no effort parameter and works, where the reverse would send effort
#: to something that rejects it and fail the request.
#:
#: Haiku 4.5 is deliberately absent -- it does NOT accept effort and returns 400 if it is
#: sent. It is still the default for the family proposer, and stays selectable for the
#: classifier, so the keyword has to disappear from the request rather than be sent empty.
#: There is nothing to fix on those requests: a Haiku call with no thinking configured is
#: already cheaper than any effort level of a larger model.
EFFORT_CAPABLE = (
    "claude-fable-5",
    "claude-mythos-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-opus-4-5",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
)

#: ``xhigh`` and ``max`` arrived after Opus 4.5 and are rejected by it.
_NO_TOP_LEVELS = ("claude-opus-4-5",)


def supports_effort(model: str) -> bool:
    return model in EFFORT_CAPABLE


def output_config(model: str, effort: str | None) -> dict | None:
    """``output_config`` for a request, or None when there is nothing to send.

    Returns None rather than an empty dict so a caller can drop the keyword entirely:
    passing ``output_config={}`` is a different request from passing none.
    """
    if not effort or not supports_effort(model):
        return None
    if effort not in EFFORT_LEVELS:
        raise ValueError(f"unknown effort {effort!r}; expected one of {EFFORT_LEVELS}")
    if model in _NO_TOP_LEVELS and effort in ("xhigh", "max"):
        raise ValueError(f"{model} does not accept effort {effort!r}")
    return {"effort": effort}


#: USD per million tokens: (input, output, cache read). First-party API rates as of
#: 2026-09; the Batches API halves all three. An unknown model estimates as Sonnet.
PRICES_PER_MTOK: dict[str, tuple[float, float, float]] = {
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-fable-5": (10.0, 50.0, 1.0),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-opus-4-8": (5.0, 25.0, 0.50),
    "claude-opus-4-7": (5.0, 25.0, 0.50),
    "claude-opus-4-6": (5.0, 25.0, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-sonnet-5": (2.0, 10.0, 0.20),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30),
    "claude-haiku-4-5": (1.0, 5.0, 0.10),
}


#: Writing a prefix to the 5-minute prompt cache bills at this multiple of the input rate
#: (the 1-hour cache is 2x). Every cache_control block in this codebase is the default
#: 5-minute ephemeral one.
CACHE_WRITE_MULTIPLIER = 1.25


def estimate_usd(
    model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0,
    *, batched: bool = False, cache_write_tokens: int = 0,
) -> float:
    """What a run cost, from the token counts the responses reported. ``input_tokens``
    is the uncached input the API bills at full rate (the usage field of that name);
    cache reads and cache writes are counted separately, each at its own rate -- a write
    is dearer than plain input, so leaving it out understates exactly the calls that
    cache."""
    price_in, price_out, price_cache = PRICES_PER_MTOK.get(model, PRICES_PER_MTOK["claude-sonnet-5"])
    usd = (
        input_tokens * price_in + output_tokens * price_out + cache_read_tokens * price_cache
        + cache_write_tokens * price_in * CACHE_WRITE_MULTIPLIER
    ) / 1_000_000
    return round(usd * (0.5 if batched else 1.0), 4)
