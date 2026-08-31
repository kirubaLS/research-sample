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
#: sent. That matters here because Haiku is the default for both the classifier and the
#: family proposer, being the cheapest model available. There is nothing to fix: a Haiku
#: request with no thinking configured is already cheaper than any effort level of a
#: larger model, so "low effort" is satisfied by the model choice itself.
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
