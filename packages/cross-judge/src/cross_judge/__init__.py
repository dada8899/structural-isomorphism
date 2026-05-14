"""cross-judge — Multi-vendor LLM ensemble judge.

Quick example:

    from cross_judge import Reviewer, JudgePanel

    reviewers = [
        Reviewer(reviewer_id="ds-pro-T0",    model="deepseek-v4-pro",   temperature=0.0),
        Reviewer(reviewer_id="ds-flash-T0",  model="deepseek-v4-flash", temperature=0.0),
        Reviewer(reviewer_id="ds-pro-T07",   model="deepseek-v4-pro",   temperature=0.7),
    ]
    panel = JudgePanel(reviewers=reviewers, strategy="majority")
    result = panel.ask(item_id="example_1", user_prompt="...")
    print(result.consensus, result.avg_confidence, result.disagreement)
"""
from .aggregation import (
    AggregationStrategy,
    avg_confidence,
    first_disagreement,
    get_strategy,
    majority,
    unanimous,
    weighted,
)
from .panel import JudgePanel
from .reviewer import Reviewer
from .schema import EnsembleResult, Verdict
from .vendors import VENDORS, VendorConfig, get_vendor, make_client

__version__ = "0.1.0"

__all__ = [
    "AggregationStrategy",
    "EnsembleResult",
    "JudgePanel",
    "Reviewer",
    "VENDORS",
    "Verdict",
    "VendorConfig",
    "avg_confidence",
    "first_disagreement",
    "get_strategy",
    "get_vendor",
    "majority",
    "make_client",
    "unanimous",
    "weighted",
    "__version__",
]
