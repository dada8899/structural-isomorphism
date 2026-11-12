"""Pydantic schemas for cross-judge verdicts and aggregation results."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

VerdictLabel = str  # free-form (KEEP/REJECT/UNCLEAR/SPLIT/MERGE/...); callers pick the vocabulary


class Verdict(BaseModel):
    """A single reviewer's verdict for one item.

    The verdict label vocabulary is caller-defined (e.g. KEEP/REJECT/UNCLEAR
    for taxonomy review, or PASS/FAIL/UNSURE for code review). The aggregation
    layer treats labels as opaque strings.
    """

    model_config = ConfigDict(extra="allow")

    reviewer_id: str = Field(..., description="Unique reviewer identifier (e.g. 'deepseek-pro-T0').")
    verdict: str = Field(..., description="Verdict label (caller-defined vocabulary).")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Reviewer self-reported confidence 0-1.")
    rationale: str = Field("", description="Short reasoning (1-4 sentences).")
    raw_response: str | None = Field(None, description="Raw LLM response for audit / debugging.")
    error: str | None = Field(None, description="Error message if the call failed; verdict will be 'ERROR'.")
    elapsed_s: float = Field(0.0, description="Wall time of the call in seconds.")


class EnsembleResult(BaseModel):
    """Aggregate result for one item across all reviewers in a panel."""

    model_config = ConfigDict(extra="allow")

    item_id: str = Field(..., description="Caller-supplied item identifier.")
    verdicts: list[Verdict] = Field(..., description="Per-reviewer verdicts (one per reviewer).")
    consensus: str = Field(..., description="Aggregated label per the panel's strategy.")
    avg_confidence: float = Field(0.0, ge=0.0, le=1.0)
    disagreement: bool = Field(False, description="True if not all reviewers agreed on the same label.")
    strategy: str = Field(..., description="Name of the aggregation strategy that produced consensus.")
    meta: dict[str, Any] = Field(default_factory=dict, description="Caller-supplied metadata.")
