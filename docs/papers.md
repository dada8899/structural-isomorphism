# Papers

Preprints and working drafts produced from the pipeline are tracked here.
The canonical drafts live under `paper/` in the repository.

## Unified pipeline preprint (C1)

**Unified pre-registered validation of self-organized criticality across
thirteen complex systems.**

A single Python pipeline applied unchanged to thirteen datasets spanning
geology, equity finance, decentralized finance, neuroscience, plasma
astrophysics, ecology, banking history, software communities, power
grids, highway traffic, and lake biogeochemistry. Recovered tail
exponents fall inside predicted bands across nine SOC and preferential-
attachment phases; A2-Hysteresis confirms the Preisach first-order
signature on NGSIM US-101 traffic; A2-Scheffer on Fox River dissolved
oxygen returns INCONCLUSIVE under proper moving-block bootstrap. A B3
multi-model ensemble taxonomy critic across 21 candidate classes
returned KEEP=5 / REJECT=7 / SPLIT=5 / MERGE=4.

- Repository draft: `paper/v0-unified-pipeline-2026-05-13.md`
- Length: approximately 10,400 words
- Status: v0.3, prepared for arXiv submission

## CVE falsification preprint

**Pre-registered validation of self-organized criticality in CVE
disclosure bursts: A falsification.**

The first formal FAIL verdict from the pre-registered pipeline. A power-
law band $\alpha \in [1.5, 2.5]$ was committed to git before any NIST
NVD API call; the downstream fitter recovered $\alpha = 2.668$ with
95% bootstrap CI $[2.40, 2.98]$, outside the band. Vuong likelihood-
ratio tests rejected power-law in favor of both lognormal ($p = 0.002$)
and exponential ($p = 0.0001$). The mechanism of failure is identified:
Microsoft Patch Tuesday and analogous vendor cadences produce a
deterministic administrative cycle that contaminates the daily count
time series and yields a mixture distribution well-fit by lognormal.

- Repository draft: `paper/cve-preregistration-fail-2026-05-14.md`
- Length: approximately 4,500 words
- Status: v0.2, prepared for arXiv submission (`cs.CR` primary,
  `physics.data-an` cross-list)

## Companion: FDNY inconclusive

**Pre-registered validation of self-organized criticality in NYC FDNY
fire incident dispatch.**

Reported inline in the unified pipeline preprint, §S6 supplementary.
Verdict: INCONCLUSIVE on the primary `units_dispatched_all` series;
FAIL on the strict-fires-only subset. The juxtaposition with the CVE
FAIL is discussed in the CVE preprint, §5.2: both systems were
nominated as SOC candidates on plausible literature grounds, and both
fail the test for identifiable, mechanism-level reasons. The
universality class boundary is narrower than the broad cross-domain
use of "SOC-like" would suggest.

- Validation artifacts: `v4/validation/nyc-fdny-fires/`
- Pre-registration: `v4/preregistration/nyc-fdny-fires.yaml`

## Drafts in progress

The following drafts are in early stages and are not yet linked from
the public documentation:

- **Reject-aware pipeline (C4).** Documenting the cross-judge B4
  calibration loop and its impact on published-fit selection.
  See `paper/c4-reject-aware-pipeline-2026-05-13.md`.

## Citing

```bibtex
@unpublished{structural_isomorphism_2026,
  author = {dada8899},
  title  = {Unified pre-registered validation of self-organized criticality
            across thirteen complex systems},
  year   = {2026},
  note   = {Preprint at \url{https://github.com/dada8899/structural-isomorphism}}
}

@unpublished{cve_falsification_2026,
  author = {dada8899},
  title  = {Pre-registered validation of self-organized criticality in
            CVE disclosure bursts: A falsification},
  year   = {2026},
  note   = {Preprint at \url{https://github.com/dada8899/structural-isomorphism}}
}
```
