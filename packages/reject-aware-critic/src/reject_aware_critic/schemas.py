"""Pydantic schemas for reject-aware-critic.

Three top-level data models:

  CandidateClass  — input to the critic: one candidate universality class
                    with shared equations, claimed members, domains.
  Verdict         — output of a single Critic.judge() call.
  EnsembleResult  — output of CriticEnsemble.judge() (multiple Verdicts +
                    consensus + disagreement signals).

The verdict labels follow the C4 paper schema:
  KEEP / REJECT / SPLIT / MERGE / UNCLEAR plus operational ERROR / PARSE_FAIL.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Verdict labels admitted by the LLM-decided fields.
# ERROR / PARSE_FAIL are operational labels assigned by the critic code path
# when the API call or JSON parsing fails; the LLM never emits them itself.
VerdictLabel = Literal[
    "KEEP",
    "REJECT",
    "SPLIT",
    "MERGE",
    "UNCLEAR",
    "ERROR",
    "PARSE_FAIL",
]

# Trap flag identifiers — the 4 prototype reject-aware filter traps from
# C4 paper §4.3 plus an "other" escape valve for novel patterns.
TrapFlag = Literal[
    "mechanism_vs_limit_theorem",
    "mathematical_framework_masquerading",
    "surface_similarity_from_heavy_tails",
    "mechanism_dispersion_monolith",
    "other",
]


class CandidateClass(BaseModel):
    """A candidate cross-domain universality class for critic review.

    Mirrors the YAML schema used by V4 `taxonomy/classes/*.yaml`, but
    package-internal — does not depend on the V4 repo layout.
    """

    model_config = ConfigDict(extra="allow")

    class_id: str = Field(..., description="Stable identifier, e.g. 'delay_differential_debt'.")
    name: str = Field("", description="Human-readable display name.")
    hub: str = Field("", description="Canonical hub phenomenon (one-line).")
    shared_equations: list[str] = Field(
        default_factory=list,
        description="Equations / normal forms the candidate members share.",
    )
    key_invariants: list[str] = Field(
        default_factory=list,
        description="Invariants (exponents, conservation laws, symmetry constraints).",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="Domains the candidate members are drawn from (physics, finance, ...).",
    )
    members: list[str] = Field(
        default_factory=list,
        description="Positive-example phenomena claimed to be in the class.",
    )
    negative_examples: list[str] = Field(
        default_factory=list,
        description="Boundary / negative cases (should NOT be in class).",
    )
    notes: str = Field("", description="Free-form curator notes from YAML.")
    prior_verdict: str | None = Field(
        None,
        description="Optional prior verdict from upstream critic (e.g. B1).",
    )
    prior_confidence: float | None = Field(
        None, description="Optional prior confidence in [0,1]."
    )
    prior_rationale: str | None = Field(
        None, description="Optional prior rationale (short)."
    )

    @field_validator("class_id")
    @classmethod
    def _strip_id(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("class_id must not be empty")
        return v


class Verdict(BaseModel):
    """One critic's verdict on one candidate class."""

    model_config = ConfigDict(extra="allow")

    class_id: str
    critic_id: str = Field(..., description="Identifier of the critic that produced this verdict.")
    decision: VerdictLabel = "UNCLEAR"
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    rationale: str = ""
    trap_flags: list[TrapFlag] = Field(default_factory=list)
    elapsed_s: float = 0.0
    cost_usd: float = 0.0
    raw_response: str | None = None
    error: str | None = None

    @field_validator("decision", mode="before")
    @classmethod
    def _normalize_decision(cls, v: object) -> str:
        if v is None:
            return "UNCLEAR"
        s = str(v).strip().upper()
        # Tolerate verbose model outputs like "SPLIT_INTO_TWO".
        for label in ("KEEP", "REJECT", "SPLIT", "MERGE", "UNCLEAR", "ERROR", "PARSE_FAIL"):
            if s.startswith(label):
                return label
        return "UNCLEAR"

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: object) -> float:
        try:
            f = float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, f))


class EnsembleResult(BaseModel):
    """Aggregate of multiple Verdicts on the same CandidateClass."""

    model_config = ConfigDict(extra="allow")

    class_id: str
    verdicts: list[Verdict]
    consensus: VerdictLabel
    consensus_confidence: float = Field(0.0, ge=0.0, le=1.0)
    disagreement_signal: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="0 = unanimous, 1 = maximally split across labels.",
    )
    trap_flags_union: list[TrapFlag] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    n_errors: int = 0
    n_parse_fail: int = 0
