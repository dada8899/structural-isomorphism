"""
Pydantic schemas for /api/ask/stream guardrails.

The Perplexity-like orchestrator asks the LLM to return a single JSON
object containing the short answer, the citation list and the followup
questions. We pipe that raw JSON through these schemas before emitting
SSE events, so any malformed / hallucinated structure fails validation
and triggers a single retry inside AskOrchestrator.

Field shapes are intentionally tight — citation indices must be 1-based
integers; the answer length window catches truncated / empty outputs.
"""
from typing import Any, List

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .input_limits import normalize_research_text


class Citation(BaseModel):
    """A single inline citation in the synthesized short answer.

    `idx` is the 1-based position into the KB cards list that was provided
    to the LLM in the prompt. AskOrchestrator additionally checks that
    `idx` is within range before emitting the citation downstream.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    idx: int = Field(..., ge=1, le=20, strict=True)
    kb_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        strict=True,
    )
    label: str = Field(..., min_length=1, max_length=200)

    @field_validator("label", mode="before")
    @classmethod
    def _normalize_label(cls, value: Any) -> str:
        return normalize_research_text(
            value,
            max_chars=200,
            allow_layout=False,
            field_name="citation.label",
        )


class AskAnswerPayload(BaseModel):
    """Top-level shape returned by the LLM for the /ask/stream Phase B call."""

    model_config = ConfigDict(extra="forbid", strict=True)

    answer: str = Field(..., min_length=20, max_length=2000)
    # Pydantic v2 uses `min_length` / `max_length` on List fields (the legacy
    # `min_items` / `max_items` aliases still work but emit a deprecation
    # warning). Stay on the v2-native names for forward compat.
    citations: List[Citation] = Field(..., min_length=1, max_length=10)
    followups: List[str] = Field(..., min_length=2, max_length=5)

    @field_validator("answer", mode="before")
    @classmethod
    def _normalize_answer(cls, value: Any) -> str:
        return normalize_research_text(
            value,
            max_chars=2000,
            allow_layout=False,
            field_name="answer",
        )

    @field_validator("followups", mode="before")
    @classmethod
    def _normalize_followups(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [
            normalize_research_text(
                item,
                max_chars=240,
                allow_layout=False,
                field_name="followup",
            )
            for item in value
        ]
