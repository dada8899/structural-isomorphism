# WTO robustness and independent coding protocol

Date: 2026-07-12
Status: internal sensitivity analysis; not submission-ready

The original WTO analysis treats 23 complaint rows as observations even though
several rows concern the same policy event. `scripts/wto_reproducibility.py`
defines 17 policy-level clusters, resamples whole clusters, and performs a
leave-one-cluster-out analysis. It does not repair observational selection,
prove independence inside a cluster, or turn manual coding into external data.

The deterministic 2,000-draw result is stored in
`evaluation/research/wto-robustness-v1.json`. The row-level slope remains
negative. The policy-cluster bootstrap interval is `[-94.23, -0.11]`, with
97.9% of valid draws below zero; all 17 leave-one-cluster-out fits are negative
(`[-5.04, -2.24]`). The extreme lower tail and separation warning show that
the coefficient magnitude is unstable. The defensible statement is therefore
“the sign reversal survives this sensitivity analysis,” not “the effect size
is precisely estimated.” This still does not establish causality.

## Reproduce locally

```bash
python3 scripts/wto_reproducibility.py robustness --samples 2000 \
  --output evaluation/research/wto-robustness-v1.json
python3 -m pytest tests/test_wto_reproducibility.py
```

## Independent double coding

`evaluation/review/wto-independent-coding-bundle-v1.json` contains only a
randomized task ID, dispute number, title, and request year. Existing stage,
score, compliance outcome, notes, and coding rationale are excluded.

Two domain-qualified humans must code all 23 tasks independently using the
Horn-Mavroidis source and WTO official case materials, record exact source
locators, and use `null` when evidence is insufficient. They must not inspect
the existing coded CSV or each other's exports before comparison. The tool
validates source requirements, fingerprints and coder-file separation, then
produces a disagreement list. A third qualified adjudicator resolves disputes
with a written rationale. No independent codings or adjudications currently
exist in the repository.

## Submission boundary

Submission remains blocked until independent double coding is complete,
cluster definitions receive trade-law review, disputes are adjudicated, and
the analysis is rerun on the adjudicated data. Even then, the selected
retaliation-request sample cannot identify a causal effect without a credible
assignment strategy or experimental design.
