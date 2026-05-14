# structural-isomorphism

A pre-registered, cross-domain validation pipeline for universality classes in
complex systems. One shared Python pipeline (`v4/lib/soc_pipeline.py`, frozen
at commit `7ee228c`) is applied unchanged to thirteen independent datasets
spanning geology, finance, neuroscience, ecology, banking history, software
communities, power grids, and highway traffic — and a growing set of
adversarial pre-registrations that have produced PASS, INCONCLUSIVE, and FAIL
verdicts without per-system tuning.

## What this project is

- **A reproducible pipeline.** Clauset-Shalizi-Newman 2009 MLE power-law fits
  with KS-optimal $x_{\mathrm{min}}$, bootstrap confidence intervals, Vuong
  likelihood ratios against lognormal and exponential, Omori-Utsu temporal
  stacking, matched-$n$ synthetic null controls, log-binned density
  estimation, and Bayesian Information Criterion model comparison — all in
  one frozen module.
- **A pre-registration discipline.** Predicted exponent bands are committed
  to git **before** data acquisition. Once pushed, bands cannot be silently
  widened post hoc.
- **A cross-judge ensemble.** Multi-model taxonomy review (B3) and
  cross-judge calibration (B4) catch over-claiming on individual systems.
- **A live phase detector.** D1 ships the pipeline as a queryable service
  with a 7-event SSE orchestrator for streaming verdicts.

## Quick links

- [Getting started](getting-started.md) — install and first run.
- [Pipeline](pipeline.md) — the shared analysis stack.
- [Phase Detector](phase-detector.md) — D1 product overview.
- [Methodology / cross-judge](methodology/cross-judge.md) — B3 and B4
  ensemble methodology.
- [Methodology / pre-registration](methodology/pre-registration.md) —
  how predictions are locked.
- [Papers](papers.md) — preprints including the unified pipeline preprint
  and the CVE falsification.

## Citation

If you reference this work, please cite the unified pipeline preprint:

```bibtex
@unpublished{structural_isomorphism_2026,
  author = {dada8899},
  title  = {Unified pre-registered validation of self-organized criticality
            across thirteen complex systems},
  year   = {2026},
  note   = {Preprint at \url{https://github.com/dada8899/structural-isomorphism}}
}
```

## Status

This is a research repository under active development. The pipeline library
is frozen at commit `7ee228c`; phase papers and pre-registrations continue to
accrete. See [Papers](papers.md) for the current preprint set.
