"""Ensemble — N Critics judging the same query + consensus aggregation.

Ensemble is the v0.1 PyPI public surface for multi-critic LLM-as-judge.

Usage:
    ensemble = Ensemble(
        critics=[
            Critic(name="claude-strict", model="anthropic/claude-sonnet-4.5", ...),
            Critic(name="deepseek-creative", model="deepseek-v4-pro", ...),
            Critic(name="kimi-rigor", model="moonshot/kimi-k2", ...),
        ],
        voting="majority",
    )
    result = ensemble.judge(query="Is this isomorphic to power-law?")
    print(result.consensus, result.krippendorff_alpha, result.agreement_pct)

The ensemble makes one call per critic per query (sequential by default).
For parallel calls, callers can drive Critic.judge directly via their own
ThreadPoolExecutor and pass the resulting list to .aggregate_verdicts().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .verdict import EnsembleVerdict, Verdict
from .voting import (
    VotingStrategy,
    agreement_pct,
    get_voting_strategy,
    krippendorff_alpha,
)
from .core import Critic


VotingName = Literal["majority", "unanimous"]


@dataclass
class Ensemble:
    """A panel of Critics + a voting strategy.

    Args:
        critics: list of Critic instances. All critics judge every query.
        voting: 'majority' (default) | 'unanimous' | custom callable returning
            (consensus_label, disagreement_bool).
        voting_kwargs: passed through to the voting strategy
            (e.g. priority=['REJECT', 'KEEP'] for tie-breaking).
    """

    critics: list[Critic]
    voting: str | VotingStrategy = "majority"
    voting_kwargs: dict[str, Any] = field(default_factory=dict)

    def judge(
        self,
        query: str,
        *,
        query_id: str | None = None,
        context: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> EnsembleVerdict:
        """Judge a query with all critics and aggregate consensus.

        Args:
            query: the item to judge.
            query_id: optional explicit identifier (defaults to query truncated to 80 chars).
            context: extra template variables passed to each Critic.
            meta: caller-supplied metadata pass-through.

        Returns:
            EnsembleVerdict — per-critic verdicts + consensus + agreement +
            Krippendorff α.
        """
        verdicts: list[Verdict] = []
        for c in self.critics:
            verdicts.append(c.judge(query, context=context))
        return self.aggregate_verdicts(
            verdicts,
            query_id=query_id or query[:80],
            meta=meta,
        )

    def aggregate_verdicts(
        self,
        verdicts: list[Verdict],
        *,
        query_id: str,
        meta: dict[str, Any] | None = None,
    ) -> EnsembleVerdict:
        """Aggregate a precomputed list of verdicts (useful for parallel-call
        orchestration outside this class)."""
        strategy_fn = get_voting_strategy(self.voting)
        consensus, disagreement = strategy_fn(verdicts, **self.voting_kwargs)
        strategy_name = (
            self.voting if isinstance(self.voting, str) else getattr(self.voting, "__name__", "custom")
        )
        valid_confs = [v.confidence for v in verdicts if v.error is None]
        avg_conf = sum(valid_confs) / len(valid_confs) if valid_confs else 0.0
        return EnsembleVerdict(
            query_id=query_id,
            verdicts=verdicts,
            consensus=consensus,
            avg_confidence=avg_conf,
            disagreement=disagreement,
            agreement_pct=agreement_pct(verdicts, consensus),
            krippendorff_alpha=krippendorff_alpha(verdicts),
            voting=str(strategy_name),
            meta=meta or {},
        )
