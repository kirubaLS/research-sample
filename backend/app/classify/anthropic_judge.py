"""The Anthropic-backed judge.

Kept behind a narrow protocol so the classifier can be tested, and run, without a model:
the constraint layer above it is what makes the result robust, and it must be exercisable
on its own.
"""

from __future__ import annotations

from typing import Protocol

from app.classify.grounding import Grounded, ground
from app.classify.judge import SYSTEM, Classification, Evidence, build_prompt
from app.llm import output_config


class Judge(Protocol):
    def classify(self, question: str, evidence: list[Evidence]) -> Classification: ...


class AnthropicJudge:
    """One call per question, structured output, validated on the way back."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-opus-5",
        *,
        known_sections: dict[str, set[str]] | None = None,
        effort: str | None = None,
    ) -> None:
        if not api_key:
            raise ValueError(
                "no Anthropic API key. Set YAADHUM_ANTHROPIC_API_KEY. Without it the "
                "classifier falls back to nearest-neighbour retrieval, which cannot tell "
                "a question about a theorem from the theorem."
            )
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        #: None on a model that does not take an effort parameter, and then the keyword is
        #: dropped from the request rather than sent empty
        self.output_config = output_config(model, effort)
        #: chapter -> the section numbers that actually exist for it, from the taxonomy
        self.known_sections = known_sections
        #: every field the knowledge base could not vouch for, kept for inspection
        self.violations: list[tuple[str, list[str]]] = []

    def classify(self, question: str, evidence: list[Evidence]) -> Classification:
        extra = {"output_config": self.output_config} if self.output_config else {}
        response = self.client.messages.parse(
            model=self.model,
            # Room for the reasoning as well as the answer. Thinking is on by default on
            # the current models and its tokens count against this ceiling, so a limit
            # sized for the answer alone truncates the reply mid-thought -- on a paid
            # request, in production, which is exactly what app.llm exists to prevent.
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": build_prompt(question, evidence)}],
            output_format=Classification,
            **extra,
        )
        checked: Grounded = ground(
            response.parsed_output, evidence, known_sections=self.known_sections
        )
        if checked.violations:
            # kept rather than logged away: how often the model has to be corrected is the
            # measure of whether it can be trusted on the next paper
            self.violations.append((question[:80], checked.violations))
        return checked.classification
