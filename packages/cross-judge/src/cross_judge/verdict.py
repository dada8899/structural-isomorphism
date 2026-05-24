"""Verdict types — the canonical PyPI v0.1 public surface.

Two schemas are exposed:

  - `Verdict` — a single critic's judgment (kind / confidence / reasoning).
    The `kind` field is a `VerdictKind` literal: KEEP / REJECT / SPLIT / MERGE.
    Free-form labels (PASS / FAIL / UNCLEAR) are also supported via the
    raw `label` field on the underlying schema (see `cross_judge.schema`).

  - `EnsembleVerdict` — the result of aggregating N critics' verdicts on
    one query. Carries per-critic verdicts + rolled-up consensus +
    disagreement metrics (Krippendorff α + raw agreement %).

VerdictKind = Literal["KEEP", "REJECT", "SPLIT", "MERGE"] is the default
vocabulary expected by the B3 / B4 universality-class taxonomy review
pipeline. Other vocabularies are supported by passing `kind` as a plain
string — Pydantic will coerce it.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VerdictKind = Literal["KEEP", "REJECT", "SPLIT", "MERGE", "UNCLEAR", "ERROR", "PARSE_FAIL"]
"""Default verdict vocabulary for the B3 / B4 universality-class review pattern.

KEEP   — accept the candidate as-is.
REJECT — discard the candidate (does not meet universality-class standards).
SPLIT  — accept but split into multiple sub-classes (composite candidate).
MERGE  — accept but merge with an existing class (duplicate / overlap).
UNCLEAR / ERROR / PARSE_FAIL — fallback labels for partial / failed verdicts.
"""


class Verdict(BaseModel):
    """A single critic's verdict on one query.

    Attributes:
        kind: VerdictKind label (KEEP / REJECT / SPLIT / MERGE / UNCLEAR / ...).
        confidence: 0.0–1.0 self-reported confidence.
        reasoning: 1–4 sentence rationale.
        critic_id: which critic produced this verdict.
        raw_response: the raw LLM response (for audit / debugging).
        error: error string if the call failed; kind will be 'ERROR'.
        elapsed_s: wall-clock seconds of the underlying LLM call.

    The `kind` accepts free-form strings too (e.g. PASS / FAIL for code review),
    but the Literal type is the recommended vocabulary for B3/B4-style taxonomy
    review pipelines.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    kind: str = Field(..., description="Verdict label (default vocab: KEEP/REJECT/SPLIT/MERGE).")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Self-reported confidence 0-1.")
    reasoning: str = Field("", description="Short reasoning (1-4 sentences).")
    critic_id: str = Field("", description="Identifier of the critic that produced this verdict.")
    raw_response: str | None = Field(None, description="Raw LLM response for audit / debugging.")
    error: str | None = Field(None, description="Error message if the call failed.")
    elapsed_s: float = Field(0.0, description="Wall time of the call in seconds.")

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_kwargs(cls, data: Any) -> Any:
        """Accept legacy kwarg names from cross_judge.schema.Verdict:
        - `verdict` → `kind`
        - `rationale` → `reasoning`
        - `reviewer_id` → `critic_id`
        """
        if not isinstance(data, dict):
            return data
        # don't overwrite if both forms present; new name wins
        if "kind" not in data and "verdict" in data:
            data["kind"] = data.pop("verdict")
        if "reasoning" not in data and "rationale" in data:
            data["reasoning"] = data.pop("rationale")
        if "critic_id" not in data and "reviewer_id" in data:
            data["critic_id"] = data.pop("reviewer_id")
        return data

    # Compatibility properties: older code reads `verdict` / `rationale` / `reviewer_id`.
    @property
    def verdict(self) -> str:
        """Alias for `kind` (backward compat with legacy schema)."""
        return self.kind

    @property
    def rationale(self) -> str:
        """Alias for `reasoning` (backward compat)."""
        return self.reasoning

    @property
    def reviewer_id(self) -> str:
        """Alias for `critic_id` (backward compat)."""
        return self.critic_id


class EnsembleVerdict(BaseModel):
    """Aggregate result for one query across all critics in an ensemble.

    Attributes:
        query_id: caller-supplied identifier for the judged item.
        verdicts: per-critic Verdict list (one per critic, in input order).
        consensus: the rolled-up consensus label per the ensemble's voting strategy.
        avg_confidence: mean confidence across all non-errored verdicts.
        disagreement: True if not all critics produced the same `kind`.
        agreement_pct: fraction of critics that agreed with the consensus label.
        krippendorff_alpha: Krippendorff's α inter-rater reliability coefficient
            (computed treating critics as raters and labels as nominal data).
        voting: name of the voting strategy used.
        meta: caller-supplied metadata pass-through.
    """

    model_config = ConfigDict(extra="allow")

    query_id: str = Field(..., description="Caller-supplied query / item identifier.")
    verdicts: list[Verdict] = Field(..., description="Per-critic verdicts.")
    consensus: str = Field(..., description="Aggregated consensus label.")
    avg_confidence: float = Field(0.0, ge=0.0, le=1.0)
    disagreement: bool = Field(False, description="True if not all critics agreed.")
    agreement_pct: float = Field(0.0, ge=0.0, le=1.0, description="Fraction of critics matching consensus.")
    krippendorff_alpha: float | None = Field(
        None,
        description="Krippendorff's α coefficient (1.0 = perfect agreement, 0.0 = chance, <0 = systematic disagreement). None if fewer than 2 valid verdicts.",
    )
    voting: str = Field(..., description="Voting strategy name.")
    meta: dict[str, Any] = Field(default_factory=dict)
