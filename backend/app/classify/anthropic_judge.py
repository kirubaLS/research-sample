"""The Anthropic-backed judge.

Kept behind a narrow protocol so the classifier can be tested, and run, without a model:
the constraint layer above it is what makes the result robust, and it must be exercisable
on its own.
"""

from __future__ import annotations

from typing import Protocol

from app.classify.judge import SYSTEM, Classification, Evidence, build_prompt


class Judge(Protocol):
    def classify(self, question: str, evidence: list[Evidence]) -> Classification: ...


def confine_to_candidates(
    result: Classification, evidence: list[Evidence]
) -> Classification:
    """Force an answer back inside the candidates, or make it abstain.

    A chapter the model invented looks identical to a correct one downstream: nothing in
    the taxonomy distinguishes "the model chose Circles" from "the model chose a chapter
    that was never offered". So this is enforced rather than trusted.
    """
    allowed = {e.chapter for e in evidence}
    if result.chapter in allowed:
        return result
    return result.model_copy(
        update={
            "chapter": min(allowed, key=lambda c: c.lower()) if allowed else "",
            "confidence": 0.0,
            "reasoning": (
                f"model answered {result.chapter!r}, which was not among the candidates "
                f"-- forced to abstain. " + result.reasoning
            ),
        }
    )


class AnthropicJudge:
    """One call per question, structured output, validated on the way back."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5") -> None:
        if not api_key:
            raise ValueError(
                "no Anthropic API key. Set YAADHUM_ANTHROPIC_API_KEY. Without it the "
                "classifier falls back to nearest-neighbour retrieval, which cannot tell "
                "a question about a theorem from the theorem."
            )
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def classify(self, question: str, evidence: list[Evidence]) -> Classification:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=2000,
            system=SYSTEM,
            messages=[{"role": "user", "content": build_prompt(question, evidence)}],
            output_format=Classification,
        )
        return confine_to_candidates(response.parsed_output, evidence)
