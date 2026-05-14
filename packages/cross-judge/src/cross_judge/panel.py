"""JudgePanel = a group of Reviewers that judge the same item together.

Usage:
    panel = JudgePanel(
        reviewers=[r1, r2, r3],
        strategy="majority",
    )
    result = panel.ask(item_id="taxonomy_class_42", user_prompt="...")
    # → EnsembleResult(item_id=..., verdicts=[...], consensus="KEEP", ...)

The panel makes one call per reviewer per item. Calls are sequential by
default (simpler error handling, no rate-limit fan-out). For parallel calls,
callers can drive Reviewer.ask directly via their own ThreadPoolExecutor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .aggregation import AggregationStrategy, avg_confidence, get_strategy
from .reviewer import Reviewer
from .schema import EnsembleResult, Verdict


@dataclass
class JudgePanel:
    """A panel of reviewers + an aggregation strategy."""

    reviewers: list[Reviewer]
    strategy: str | AggregationStrategy = "majority"
    strategy_kwargs: dict[str, Any] = field(default_factory=dict)

    def ask(
        self,
        item_id: str,
        user_prompt: str,
        *,
        meta: dict[str, Any] | None = None,
    ) -> EnsembleResult:
        """Ask every reviewer to judge the item, then aggregate."""
        verdicts: list[Verdict] = []
        for r in self.reviewers:
            verdicts.append(r.ask(user_prompt))
        return self._aggregate(item_id, verdicts, meta or {})

    def aggregate_verdicts(
        self,
        item_id: str,
        verdicts: list[Verdict],
        *,
        meta: dict[str, Any] | None = None,
    ) -> EnsembleResult:
        """Aggregate a precomputed list of verdicts (useful when calls were
        driven externally, e.g. via async / parallel orchestration)."""
        return self._aggregate(item_id, verdicts, meta or {})

    def _aggregate(
        self,
        item_id: str,
        verdicts: list[Verdict],
        meta: dict[str, Any],
    ) -> EnsembleResult:
        strategy_fn = get_strategy(self.strategy)
        consensus, disagreement = strategy_fn(verdicts, **self.strategy_kwargs)
        strategy_name = self.strategy if isinstance(self.strategy, str) else getattr(self.strategy, "__name__", "custom")
        return EnsembleResult(
            item_id=item_id,
            verdicts=verdicts,
            consensus=consensus,
            avg_confidence=avg_confidence(verdicts),
            disagreement=disagreement,
            strategy=str(strategy_name),
            meta=meta,
        )
