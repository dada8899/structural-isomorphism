# Cross-judge ensemble methodology

A power-law tail alone does not adjudicate universality class membership.
A system can show $\alpha \in [1.3, 2.0]$ for reasons that do not satisfy
the SOC microscopic conditions (slow drive, threshold cascade,
near-instantaneous dissipation), and conversely a genuinely SOC system can
fail the test under finite-size or contamination effects. The
**cross-judge ensemble** is the methodological apparatus that catches both
failure modes.

## B3: multi-model taxonomy review

The B3 pass runs three reviewer language models over the candidate
universality class catalog. Each reviewer issues one of four verdicts on
each class:

- **KEEP** — the class is well-defined and the prediction is falsifiable.
- **REJECT** — the class is poorly defined or fails the mechanism-vs-
  limit-theorem test.
- **SPLIT** — the class lumps together mechanisms that should be
  separated.
- **MERGE** — the class duplicates an existing one and should be merged.

The three reviewers in the v4 pipeline are DeepSeek v4-pro (rigorous),
DeepSeek v4-flash (rigorous), and DeepSeek v4-pro (creative). The same
prompt and class description are passed to each, and the verdicts are
aggregated. The full B3 pass over 21 candidate classes returned 63
verdicts in 40.8 minutes with zero parse errors:

| Verdict   | Count |
|-----------|-------|
| KEEP      | 5     |
| REJECT    | 7     |
| SPLIT     | 5     |
| MERGE     | 4     |

B3-driven demotions: `delay_differential_debt`, `hysteresis_preisach`
(as a monolithic class), `scale_free_percolation_class`, and
`tail_copula_contagion` were rejected on grounds of mechanism-vs-limit-
theorem confusion.

## B4: cross-judge calibration

B4 takes a different cut at the same problem. Instead of asking reviewers
to assess classes, B4 has them assess **individual system fits**. Each
reviewer sees the data, the fit, the alternative comparisons, and the
verdict, and assigns a calibration score on a 0-5 scale:

- 0 — over-claim; the data does not support the verdict.
- 5 — calibrated; the verdict matches the data quality.

A fit is published only if it receives a B4 mean score above 3.0 with at
least two reviewers above 4.0. The remaining fits are queued for
additional data acquisition or pre-registration revision.

## Why ensemble

Single-reviewer adjudication has a well-known pathology: each reviewer
has blind spots (training-data gaps, prior-anchor preferences, calibration
drift) and a single reviewer's idiosyncrasies translate directly into the
catalog. The ensemble pass averages over these idiosyncrasies provided
the reviewer pool is heterogeneous. The v4 reviewer pool is intentionally
diverse: two model variants (v4-pro vs v4-flash) and two prompt styles
(rigorous vs creative). Future passes will broaden the pool to include
non-DeepSeek models.

## Failure modes documented

The B3 ⊗ B1 (single-model) consensus agrees on 14 of 21 classes. The
remaining seven disagreements are documented in the unified preprint and
re-examined at each pipeline release. B4 calibration scores below 3.0
have flagged three system fits for additional bootstrap iterations and
one for re-fetching with a higher resolution data source.

## How to consume the ensemble in your own work

The cross-judge artifacts are stored under `v4/taxonomy/` and are
re-runnable. To re-run B3 on the current class catalog:

```bash
.venv/bin/python v4/taxonomy/run_b3_ensemble.py \
    --catalog v4/taxonomy/classes.yaml \
    --reviewers v4/taxonomy/reviewers.yaml \
    --out v4/taxonomy/b3_results.json
```

The reviewer YAML specifies the model endpoints, system prompts, and
sampling parameters. Replacing the reviewer pool is the canonical way to
extend the ensemble.
