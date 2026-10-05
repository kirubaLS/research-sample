"""The Anthropic-backed judge.

Kept behind a narrow protocol so the classifier can be tested, and run, without a model:
the constraint layer above it is what makes the result robust, and it must be exercisable
on its own.
"""

from __future__ import annotations

from typing import Protocol

from app.classify.grounding import Grounded, ground
from app.classify.judge import (
    CITE_NOTE,
    SCOPE_NOTE,
    SYSTEM,
    Classification,
    Evidence,
    NumberedClassification,
    NumberedScopedClassification,
    ScopedClassification,
    build_prompt,
)
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
        passage_chars: int = 1200,
        batched: bool = False,
        batch_options: dict | None = None,
        section_mapper=None,
        cite_by_number: bool = False,
    ) -> None:
        if not api_key:
            raise ValueError(
                "no Anthropic API key. Set YAADHUM_ANTHROPIC_API_KEY. Without it the "
                "classifier falls back to nearest-neighbour retrieval, which cannot tell "
                "a question about a theorem from the theorem."
            )
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        #: served from the Message Batches API at half price (see app.llm_batch); a
        #: caller that asks its questions concurrently gets one batch per round
        self.batched = batched
        if batched:
            from app.llm_batch import BatchedClient

            self.client = BatchedClient(self.client, **(batch_options or {}))
        self.model = model
        #: None on a model that does not take an effort parameter, and then the keyword is
        #: dropped from the request rather than sent empty
        self.output_config = output_config(model, effort)
        #: chapter -> the section numbers that actually exist for it, from the taxonomy
        self.known_sections = known_sections
        #: how much of each passage the model is shown -- the price of the call
        self.passage_chars = passage_chars
        #: (chapter, section) -> the section cut to the subject's depth (topic_depth_cap),
        #: applied to the answer before it is checked against known_sections
        self.section_mapper = section_mapper
        #: every field the knowledge base could not vouch for, kept for inspection
        self.violations: list[tuple[str, list[str]]] = []
        #: cite_passages_by_number: passages are cited by their printed number, checked;
        #: a citation problem is kept here as a warning and changes nothing else
        self.cite_by_number = cite_by_number
        self.citation_warnings: list[tuple[str, list[str]]] = []
        #: What was actually spent, added up as the paper is read. Reported rather than
        #: estimated: every figure anybody quoted for a paper before this, mine included,
        #: was arithmetic on a guess about the prompt.
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.calls = 0

    def _schema(self, scoped: bool) -> type[Classification]:
        if getattr(self, "cite_by_number", False):
            return NumberedScopedClassification if scoped else NumberedClassification
        return ScopedClassification if scoped else Classification

    def classify(
        self, question: str, evidence: list[Evidence], *, scoped: bool = False,
    ) -> Classification:
        """``scoped`` (cross_scope_fallback, a question confined to a declared scope):
        also ask whether none of the candidates can answer it -- ScopedClassification.
        Off, the request is exactly as before."""
        extra = {"output_config": self.output_config} if self.output_config else {}
        response = self.client.messages.parse(
            model=self.model,
            # Room for the reasoning as well as the answer. Thinking is on by default on
            # the current models and its tokens count against this ceiling, so a limit
            # sized for the answer alone truncates the reply mid-thought -- on a paid
            # request, in production, which is exactly what app.llm exists to prevent.
            max_tokens=16000,
            system=(SYSTEM + (SCOPE_NOTE if scoped else "")
                    + (CITE_NOTE if getattr(self, "cite_by_number", False) else "")),
            messages=[{
                "role": "user",
                "content": build_prompt(question, evidence, self.passage_chars),
            }],
            output_format=self._schema(scoped),
            **extra,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.input_tokens += getattr(usage, "input_tokens", 0) or 0
            self.output_tokens += getattr(usage, "output_tokens", 0) or 0
            self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
            self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.calls += 1
        result = response.parsed_output
        mapper = getattr(self, "section_mapper", None)
        if mapper is not None and getattr(result, "curriculum_section", None):
            result = result.model_copy(update={
                "curriculum_section": mapper(result.chapter, result.curriculum_section),
            })
        numbered = getattr(self, "cite_by_number", False)
        checked: Grounded = ground(
            result, evidence, known_sections=self.known_sections, cite_by_number=numbered,
        )
        if checked.warnings:
            self.citation_warnings.append((question[:80], checked.warnings))
        if checked.violations:
            # kept rather than logged away: how often the model has to be corrected is the
            # measure of whether it can be trusted on the next paper
            self.violations.append((question[:80], checked.violations))
        return checked.classification
