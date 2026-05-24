"""cross-judge — Multi-vendor LLM ensemble-judge framework.

Public v0.1 PyPI API:

    from cross_judge import Critic, Ensemble, Verdict, VerdictKind

    critics = [
        Critic(name="claude-strict",   model="anthropic/claude-sonnet-4.5", vendor="openrouter"),
        Critic(name="ds-pro-creative", model="deepseek-v4-pro",              vendor="deepseek", temperature=0.7),
        Critic(name="kimi-rigor",      model="moonshot/kimi-k2",             vendor="openrouter"),
    ]
    ensemble = Ensemble(critics=critics, voting="majority")
    result = ensemble.judge(query="Is this isomorphic to power-law tail scaling?")
    print(result.consensus, result.krippendorff_alpha, result.agreement_pct)

Legacy API (preserved for cross_judge.examples and v4/scripts/b3_ensemble.py):

    from cross_judge import Reviewer, JudgePanel
    # see docstrings on Reviewer / JudgePanel for usage.
"""
# New v0.1 PyPI public surface
from .core import VENDOR_DEFAULTS, Critic
from .ensemble import Ensemble
from .verdict import EnsembleVerdict, Verdict, VerdictKind
from .voting import (
    VOTING_STRATEGIES,
    VotingStrategy,
    agreement_pct,
    get_voting_strategy,
    krippendorff_alpha,
    majority_vote,
    unanimous,
)

# Legacy public surface (preserved for backward compatibility)
from .aggregation import (
    AggregationStrategy,
    avg_confidence,
    first_disagreement,
    get_strategy,
    majority,
    weighted,
)
from .panel import JudgePanel
from .reviewer import Reviewer
from .schema import EnsembleResult, Verdict as LegacyVerdict
from .vendors import VENDORS, VendorConfig, get_vendor, make_client

__version__ = "0.1.0"

__all__ = [
    # New v0.1 surface
    "Critic",
    "Ensemble",
    "Verdict",
    "VerdictKind",
    "EnsembleVerdict",
    "VENDOR_DEFAULTS",
    # Voting / disagreement metrics
    "majority_vote",
    "unanimous",
    "agreement_pct",
    "krippendorff_alpha",
    "get_voting_strategy",
    "VOTING_STRATEGIES",
    "VotingStrategy",
    # Legacy surface
    "Reviewer",
    "JudgePanel",
    "EnsembleResult",
    "LegacyVerdict",
    "AggregationStrategy",
    "majority",
    "weighted",
    "first_disagreement",
    "get_strategy",
    "avg_confidence",
    "VENDORS",
    "VendorConfig",
    "get_vendor",
    "make_client",
    "__version__",
]
