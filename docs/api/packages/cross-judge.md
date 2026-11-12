# cross-judge

Multi-vendor LLM ensemble-judge framework — majority / unanimous / Krippendorff-α voting across heterogeneous models.

```bash
pip install cross-judge
```

## Quick start

```python
from cross_judge import Critic, Ensemble

critics = [
    Critic(name="claude-strict", model="anthropic/claude-sonnet-4.5", vendor="openrouter"),
    Critic(name="ds-pro-creative", model="deepseek-v4-pro", vendor="deepseek", temperature=0.7),
    Critic(name="kimi-rigor", model="moonshot/kimi-k2", vendor="openrouter"),
]
ensemble = Ensemble(critics=critics, voting="majority")
result = ensemble.judge(query="Is this isomorphic to power-law tail scaling?")
print(result.consensus, result.krippendorff_alpha, result.agreement_pct)
```

## Core API (v0.1)

::: cross_judge.Critic

::: cross_judge.Ensemble

::: cross_judge.Verdict

::: cross_judge.VerdictKind

::: cross_judge.EnsembleVerdict

::: cross_judge.VENDOR_DEFAULTS

## Voting strategies

::: cross_judge.majority_vote

::: cross_judge.unanimous

::: cross_judge.agreement_pct

::: cross_judge.krippendorff_alpha

::: cross_judge.get_voting_strategy

::: cross_judge.VOTING_STRATEGIES

::: cross_judge.VotingStrategy

## Vendor configuration

::: cross_judge.VENDORS

::: cross_judge.VendorConfig

::: cross_judge.get_vendor

::: cross_judge.make_client

## Legacy API (v4 backwards compat)

::: cross_judge.Reviewer

::: cross_judge.JudgePanel

::: cross_judge.EnsembleResult

::: cross_judge.LegacyVerdict

::: cross_judge.AggregationStrategy

::: cross_judge.majority

::: cross_judge.weighted

::: cross_judge.first_disagreement

::: cross_judge.get_strategy

::: cross_judge.avg_confidence
