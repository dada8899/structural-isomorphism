# §301 natural-instrument extension — SESSION-27 sub-agent

**STATUS: PRELIMINARY — point estimate sign-flip consistent with selection diagnosis but CI includes zero**

## TL;DR

- **§301 post-WTO subsample (n=35, individual-level CRS R46604 Table A-1)**:
  k = **+2.09**, bootstrap 95% CI **[-1.04, +27.75]** (n_boot_valid = 2000)
- **Bayard-Elliott 1975–1994 aggregate two-bin (n=72)**:
  k = **-2.48** (CI not estimable from two-bin counts)
- **WTO DSU Horn-Mavroidis (SESSION-25 baseline, n=23)**:
  k = **-2.92**, CI [-7.92, -0.67]
- **Sign verdict**: MIXED across three samples. Post-WTO §301 individual data
  flips toward positive (as the natural-instrument hypothesis predicts), but
  the CI includes zero and the pre-WTO aggregate cross-check stays negative.

## Path selection

- **Path B** (USTR §301 post-WTO Table A-1 individual data + Bayard-Elliott
  1975–1994 aggregate cross-check). Bayard-Elliott individual case codebook
  was not obtained, so the pre-WTO sample is restricted to a two-bin probit
  rather than a clean IV identification.

## Data sources

- **CRS R46604 Table A-1** — cases 96–130 (post-WTO §301 cases initiated
  1995–2020). 35 individual-level rows with `retaliation_applied` ∈ {0,1}
  and `outcome` ∈ {concession, no-concession}, coded against
  CRS R46604 + corresponding WTO DSB filings + USTR press releases.
- **Bayard & Elliott (1994), Reciprocity and Retaliation in U.S. Trade Policy
  (PIIE)** — aggregate counts via Cato PA-930 + CRS R46604 secondary citation:
  72 §301 cases 1975–1994, of which 12 had retaliation applied and 2 yielded
  successful outcomes.

## Sample-level empirics (§301 post-WTO)

| condition | n | P(concession) |
|---|---|---|
| retaliation_applied = 1 | 6 | 0.833 |
| retaliation_applied = 0 | 29 | 0.724 |
| ΔP | — | **+0.11** |

Probit MLE on this subsample yields k = +2.09 (point sign positive),
bootstrap CI [-1.04, +27.75]. CI is consistent with k = 0; the wide upper
bound reflects the small n_retal = 6 and the proximity of P(concession)
to a near-ceiling baseline.

## Identification narrative (paper §6.5 paragraph-ready)

> Section 301 of the U.S. Trade Act of 1974 provides an alternative
> observational window for the Schelling commitment-device mechanism.
> Three features matter for identification. First, initiation is closer
> to random: ~60% of §301 cases originate as private-party petitions whose
> stake reflects export exposure rather than defendant intransigence; the
> remainder are USTR self-initiations driven by executive political
> calculus. Unlike the WTO DSU sample, §301 initiation is not gated on a
> multi-stage adjudication that has already revealed the defendant's
> compliance type. Second, treatment dose varies exogenously: §301
> retaliation magnitude is set politically by USTR (from narrow GSP
> suspensions to broad ad-valorem tariffs across $370B of imports as in
> case 125), not arbitrated for equivalence to nullification as in WTO
> DSU. Third, the sample provides a cross-check on the SESSION-25
> endogenous-selection diagnosis: under the natural-instrument hypothesis,
> k should recover toward positive in §301 data; under the null that the
> Schelling sign is genuinely negative in modern trade, §301 should also
> yield k ≤ 0. We find the §301 post-WTO subsample (n=35) point-estimates
> k = +2.09 (CI [-1.04, +27.75]; includes 0), while Bayard-Elliott
> 1975–1994 aggregate (n=72) yields k = -2.48 (CI not estimable from
> two-bin counts). The point-sign recovery in the narrower post-WTO
> subsample is consistent with — but does not confirm — the selection
> diagnosis; the conflicting pre-WTO aggregate and the wide CI prevent
> upgrading the STRUCTURAL verdict.

## Limitations (honest)

1. **n=35** with only **6 cases retaliation_applied** → CI spans 28 units,
   sign-flip is not statistically distinguishable from zero.
2. **Bayard-Elliott individual codebook not obtained** — only aggregate
   two-bin available, so the 1975–1994 sample cannot be run with the same
   probit specification.
3. **Coding ambiguity**: a handful of §301 cases (e.g. case 125, China §301
   Section 1 actions) have outcomes that are still in progress as of CRS
   R46604 reporting date — these were dropped from n=35 to avoid premature
   classification.

## Impact on v0.5 paper §6.5

- **Verdict**: maintain **STRUCTURAL (a')** — point-estimate sign-flip is
  not statistically significant, and the BE pre-WTO aggregate stays
  negative.
- **Paper paragraph** (paste-ready):

> An attempted §301 natural-instrument extension (n=35 post-WTO §301 cases
> from CRS R46604 Table A-1) yields point estimate k = +2.09 with 95%
> bootstrap CI [-1.04, +27.75] — a sign flip relative to the WTO DSU
> subsample but not statistically distinguishable from zero. A complementary
> aggregate cross-check using Bayard-Elliott (1994) §301 1975–1994 counts
> (n=72) yields k = -2.48, sign-consistent with the WTO DSU finding. The
> sign-flip in the narrower post-WTO §301 subsample is the prediction of
> the natural-instrument identification story (USTR retaliation decisions
> closer to exogenous to defendant type than WTO-DSU stage-by-stage
> adjudication), but the wide CI and the conflicting pre-WTO aggregate
> prevent upgrading the STRUCTURAL verdict from §6.5 to a clean mechanism
> recovery. We treat the §301 extension as a robustness check consistent
> with — but not confirming — the endogenous-selection diagnosis.

## Reproducibility

```bash
cd v4/validation/schelling-credible-commitment/
python3 run_validation_section_301.py
# Outputs results_section_301.json
```

## Files

- `data/section_301_cases.csv` (n=35, post-WTO §301 cases 1995–2020)
- `run_validation_section_301.py` (probit MLE + bootstrap CI + BE aggregate
  cross-check + three-sample sign comparison)
- `results_section_301.json` (full numerical output incl. verdict)
- `summary_section_301.md` (this file)
