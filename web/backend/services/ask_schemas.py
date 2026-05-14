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
from typing import List

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A single inline citation in the synthesized short answer.

    `idx` is the 1-based position into the KB cards list that was provided
    to the LLM in the prompt. AskOrchestrator additionally checks that
    `idx` is within range before emitting the citation downstream.
    """

    idx: int = Field(..., ge=1, le=20)
    kb_id: str = Field(..., min_length=1, max_length=128)
    label: str = Field(..., min_length=1, max_length=200)


class AskAnswerPayload(BaseModel):
    """Top-level shape returned by the LLM for the /ask/stream Phase B call."""

    answer: str = Field(..., min_length=20, max_length=2000)
    # Pydantic v2 uses `min_length` / `max_length` on List fields (the legacy
    # `min_items` / `max_items` aliases still work but emit a deprecation
    # warning). Stay on the v2-native names for forward compat.
    citations: List[Citation] = Field(..., min_length=1, max_length=10)
    followups: List[str] = Field(..., min_length=2, max_length=5)
