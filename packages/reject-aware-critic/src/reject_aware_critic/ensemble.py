"""Ensemble of Critics — B3 (within-vendor multi-decoding) and B4 (cross-vendor).

Two construction helpers:

  CriticEnsemble.b3(vendor=...)        — three decodings on one vendor
                                          (rigorous T=0.0 / lighter T=0.0 /
                                          creative_dissenter T=0.6). This is
                                          the C4 paper B3 stage.
  CriticEnsemble.b4(vendors=[...])     — one rigorous critic per vendor;
                                          cross-architecture probe.

You can also pass `critics=[Critic, Critic, ...]` explicitly to build any
ensemble shape.

Aggregation rule (matches V4 b3_ensemble.consensus_of):
  - plurality / majority for KEEP/REJECT/SPLIT/MERGE (>= ceil(n/2))
  - UNCLEAR / ERROR / PARSE_FAIL are not counted as votes; if no label
    reaches majority the consensus is UNCLEAR.

disagreement_signal = 1 - (max_vote_count / n_valid_votes), in [0, 1].
trap_flags_union = union of all per-critic trap_flags (stable order).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .critic import Critic
from .schemas import CandidateClass, EnsembleResult, TrapFlag, Verdict, VerdictLabel

# Default model id per vendor for ensemble helpers. Users with different
# access tiers can override with vendor_model_map=... at b3()/b4().
DEFAULT_MODELS: dict[str, str] = {
    "deepseek": "deepseek-chat",
    "anthropic": "anthropic/claude-3-5-sonnet",
    "openrouter": "deepseek/deepseek-chat",
    "openai": "gpt-4o-mini",
    "kimi": "moonshotai/kimi-k2",
    "glm": "zhipuai/glm-4",
    "mock": "mock-model",
}

VOTE_LABELS: tuple[VerdictLabel, ...] = ("KEEP", "REJECT", "SPLIT", "MERGE")


def _consensus_of(verdicts: Sequence[Verdict]) -> tuple[VerdictLabel, float, float]:
    """Compute (consensus_label, consensus_confidence, disagreement_signal).

    consensus_confidence = mean confidence of verdicts matching the consensus
        label; 0 if no consensus.
    disagreement_signal = 1 - (top_vote_count / n_valid). 0 if no valid votes.
    """
    counter: Counter[str] = Counter()
    for v in verdicts:
        if v.decision in VOTE_LABELS:
            counter[v.decision] += 1

    n_valid = sum(counter.values())
    if n_valid == 0:
        return "UNCLEAR", 0.0, 0.0

    # Majority threshold = strictly more than half. With 3 votes a 2-1 split
    # passes (2 > 1.5); with 4 votes a 2-2 tie fails (2 not > 2) → UNCLEAR.
    # With 4 votes a 3-1 split passes (3 > 2). Matches the V4 b3_ensemble rule
    # of "majority for KEEP/REJECT/SPLIT/MERGE else UNCLEAR".
    consensus: VerdictLabel = "UNCLEAR"
    half = n_valid / 2.0
    for label in VOTE_LABELS:
        if counter[label] > half:
            consensus = label
            break

    top_count = max(counter.values()) if counter else 0
    disagreement = 1.0 - (top_count / n_valid)

    if consensus == "UNCLEAR":
        confidence = 0.0
    else:
        matching = [v.confidence for v in verdicts if v.decision == consensus]
        confidence = sum(matching) / max(1, len(matching))
    return consensus, round(float(confidence), 4), round(float(disagreement), 4)


def _union_trap_flags(verdicts: Iterable[Verdict]) -> list[TrapFlag]:
    seen: set[str] = set()
    out: list[TrapFlag] = []
    for v in verdicts:
        for f in v.trap_flags:
            if f not in seen:
                seen.add(f)
                out.append(f)
    return out


@dataclass
class CriticEnsemble:
    """A collection of Critics that vote on each CandidateClass."""

    critics: list[Critic] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.critics:
            raise ValueError("CriticEnsemble requires at least one Critic.")

    # ------------------------------------------------------------------
    # construction helpers

    @classmethod
    def b3(
        cls,
        vendor: str = "deepseek",
        model: str | None = None,
        *,
        max_cost_usd: float = 0.05,
        log_path: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        http_client=None,
        mock_responder: str = "default",
    ) -> "CriticEnsemble":
        """B3-style within-vendor multi-decoding ensemble (3 critics on 1 vendor).

        Matches C4 paper B3: rigorous T=0.0, lighter T=0.0, creative_dissenter T=0.6.
        """
        model = model or DEFAULT_MODELS.get(vendor, "")
        if not model:
            raise ValueError(
                f"No default model for vendor '{vendor}'. "
                "Pass model=... explicitly."
            )
        common = dict(
            vendor=vendor,
            model=model,
            max_cost_usd=max_cost_usd,
            log_path=log_path,
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
            mock_responder=mock_responder,
        )
        critics = [
            Critic(persona="rigorous", temperature=0.0, **common),
            Critic(persona="lighter", temperature=0.0, max_tokens=1500, **common),
            Critic(persona="creative_dissenter", temperature=0.6, **common),
        ]
        return cls(critics=critics)

    @classmethod
    def b4(
        cls,
        vendors: Sequence[str] = ("anthropic", "deepseek", "kimi", "glm"),
        *,
        vendor_model_map: dict[str, str] | None = None,
        persona: str = "rigorous",
        temperature: float = 0.0,
        max_cost_usd: float = 0.05,
        log_path: str | None = None,
        http_client=None,
        mock_responder: str = "default",
    ) -> "CriticEnsemble":
        """B4-style cross-vendor ensemble (1 rigorous critic per vendor).

        Each vendor's API key is read from its env var (e.g. ANTHROPIC_API_KEY
        or OPENROUTER_API_KEY). Vendors not in DEFAULT_MODELS require an
        explicit vendor_model_map entry.
        """
        vendor_model_map = vendor_model_map or {}
        critics: list[Critic] = []
        for v in vendors:
            model = vendor_model_map.get(v) or DEFAULT_MODELS.get(v)
            if not model:
                raise ValueError(
                    f"No model for vendor '{v}'. "
                    "Add it to vendor_model_map=... or set a DEFAULT_MODELS entry."
                )
            critics.append(
                Critic(
                    vendor=v,
                    model=model,
                    persona=persona,
                    temperature=temperature,
                    max_cost_usd=max_cost_usd,
                    log_path=log_path,
                    http_client=http_client,
                    mock_responder=mock_responder,
                )
            )
        return cls(critics=critics)

    # ------------------------------------------------------------------
    # judging

    def judge(self, candidate: CandidateClass) -> EnsembleResult:
        """Run each critic on the candidate and aggregate verdicts."""
        if not isinstance(candidate, CandidateClass):
            candidate = CandidateClass.model_validate(candidate)
        verdicts: list[Verdict] = [c.judge(candidate) for c in self.critics]
        consensus, conf, disagreement = _consensus_of(verdicts)
        total_cost = sum(v.cost_usd for v in verdicts)
        n_errors = sum(1 for v in verdicts if v.decision == "ERROR")
        n_parse_fail = sum(1 for v in verdicts if v.decision == "PARSE_FAIL")
        return EnsembleResult(
            class_id=candidate.class_id,
            verdicts=verdicts,
            consensus=consensus,
            consensus_confidence=conf,
            disagreement_signal=disagreement,
            trap_flags_union=_union_trap_flags(verdicts),
            total_cost_usd=round(total_cost, 6),
            n_errors=n_errors,
            n_parse_fail=n_parse_fail,
        )

    def judge_many(self, candidates: Iterable[CandidateClass]) -> list[EnsembleResult]:
        return [self.judge(c) for c in candidates]
