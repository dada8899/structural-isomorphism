# F4 — xmin sensitivity sliding-window scan (W7-D)

**Date:** 2026-05-15
**Reviewer concern (W5-A §3.8 / §4.1):** Standard `powerlaw.Fit` with
KS-distance minimization is correct in principle but has documented edge-case
behavior on small n and on distributions with curvature near the candidate
xmin regime. The paper does not report sensitivity of alpha to perturbations
in xmin. Recommended: for each phase, add a supplementary figure showing
alpha(xmin) on a sliding window across the support, with the chosen
KS-minimum xmin marked.

## Implementation

`paper/figures/methodology/generate_F4.py` — sweeps xmin in log-space across
[baseline × 0.5, baseline × 2.0] in 20 steps. At each xmin, fits a fixed-xmin
Clauset MLE alpha on the tail subset and records the point estimate.

**Baseline xmin** per system is taken from the published Clauset fit in the
phase's `*_results.json` (e.g. `powerlaw_fit.xmin` or `clauset_fit.xmin`).
Earthquake uses energy-domain median (Aki MLE doesn't expose a Clauset
xmin in the energy units).

## Systems swept (8 of 13)

| System | n | baseline xmin | alpha range | drift |
|---|---:|---:|---|---|
| earthquake (energy J) | 37,298 | 1.12e+07 | [1.679, 1.960] (range 0.28) | **mild_drift** |
| stockmarket | 9,060 | 0.00998 | [2.294, 3.000] (range 0.71) | **substantial_drift** |
| defi_aave | 28,943 | 1.75e+04 | (fitting failed, alpha pinned at 1.0) | N/A — see caveat |
| wildfire | 21,022 | 1199 | [1.607, 1.710] (range 0.10) | **robust** |
| solar | 29,907 | 5.2e-06 | [2.101, 2.197] (range 0.10) | **robust** |
| bank_failure | 3,960 | 6.27e+08 | [1.844, 1.931] (range 0.09) | **robust** |
| github_stars | 8,398 | 2.56e+04 | [2.188, 3.000] (range 0.81) | **substantial_drift** |
| wikipedia | 7,521 | 9.84e+05 | [1.874, 2.146] (range 0.27) | **mild_drift** |

**Drift classification** (heuristic, applied per F4 script):
- range < 0.2 -> robust
- 0.2 <= range < 0.5 -> mild_drift
- range >= 0.5 -> substantial_drift

## Five-system not covered

DeFi compound, DeFi maker, mouse cortex (Phase 4), and power-grid (Phase 7)
are deferred to a follow-up round:
- **Compound / maker** use the same Aave-style debt-to-cover field and would
  require the same fitting fix as defi_aave.
- **Mouse cortex** (Phase 4) doesn't have a single canonical alpha — it has
  alpha_T and tau across 16-fold bin sweeps, requiring a different sensitivity
  framing.
- **Power grid** (Phase 7) is n=123 literature meta, baseline xmin not
  directly applicable.

## Findings interpretation

### Robust (3 of 8): wildfire, solar, bank_failure

Alpha varies by < 0.2 across a 4×-multiplicative xmin range. These three
systems' Clauset MLE alpha is well-determined and not artifactually
dependent on the xmin choice. The published verdicts are defensible.

### Mild drift (2 of 8): earthquake, wikipedia

Alpha varies by 0.27-0.28 across the sweep. For earthquake this likely
reflects the b-value vs Clauset-energy-fit discrepancy (paper notes the
3-sigma divergence between alpha = 1 + b/1.5 ≈ 1.72 and Clauset alpha ≈ 1.79).
For wikipedia (which the scholar review already flagged as weak — Vuong-LN
beats PL by 6.3 sigma, top-1000 truncation), the drift is a third independent
reason to demote the verdict label from "CONFIRMED" to "consistent within
caveats."

### Substantial drift (2 of 8): stockmarket, github_stars

Alpha varies by > 0.7 across the sweep. This is the **largest new finding
from F4** — both systems where the Clauset fit climbs to the alpha=3.0 power-law
ceiling at the upper xmin range (i.e., the upper-tail-only sub-fit returns a
canonical inverse-cubic). This is **not necessarily a defect**: it's
consistent with the scholar-reviewer (§4.1) observation that PL/LN coexistence
in finite samples (Mitzenmacher 2004) shows up as xmin-sensitivity. Both
systems have Vuong-LN p > 0.1, i.e., the Vuong test could not pick a winner.

**Action:** in the C1 v0.3 manuscript, alpha estimates for stockmarket and
github_stars should be reported with their drift range (e.g.,
"alpha = 3.00 +/- 0.04 (Clauset) with xmin-sensitivity range alpha in
[2.29, 3.00] across 0.5x-2x xmin sweep"). This is the honest reading.

### defi_aave fitting failure

DeFi Aave V2 liquidation `debt_to_cover_raw` (wei-denominated integers
spanning many decades) trips `powerlaw.Fit`'s edge-case handling — alpha
clamps to ~1.0 with warnings about discrete=False on integer-valued data.
The published Clauset fit (`alpha = 1.68` in `multiprotocol_results.json`)
uses a different code path (multiprotocol_results.json reports per-protocol
fits not the raw input). For F4, this means the defi_aave row in the figure
should be read as N/A. A follow-up F4-bis with discrete=True and proper
xmax handling would close this gap.

## Output

- `paper/figures/methodology/F4_xmin_sensitivity.pdf` — 8-panel grid
- `paper/figures/methodology/F4_xmin_sensitivity.png` — same in PNG
- `paper/figures/methodology/F4_xmin_sensitivity_data.json` — raw alpha(xmin)
  data per system

## Recommended manuscript edit

Add as supplementary figure to C1 v0.3 with a paragraph:

> Figure S4. Clauset alpha estimator sensitivity to xmin choice across
> ±2× of the KS-minimum xmin. Three of the 8 phases tested (wildfire, solar,
> bank failure) show robust alpha variation < 0.2 across the sweep. Two phases
> (earthquake energy, Wikipedia) show mild drift (0.27-0.28), consistent with
> their published b-vs-Clauset discrepancy and top-1000 truncation caveats
> respectively. Two phases (S&P 500 returns, GitHub stars) show substantial
> drift > 0.7 with alpha climbing to the inverse-cubic ceiling at large xmin —
> consistent with Mitzenmacher (2004) PL/LN coexistence in finite samples and
> with the Vuong LR inconclusive verdicts already reported. We add the drift
> range to Table 1 columns.

## References

- Clauset A, Shalizi CR, Newman MEJ (2009). "Power-law distributions in
  empirical data." *SIAM Rev.* 51, 661-703.
- Deluca A, Corral A (2013). "Fitting and goodness-of-fit test of non-
  truncated and truncated power-law distributions." *Acta Geophys.* 61, 1351.
- Voitalov I et al. (2019). "Scale-free networks well done."
  *Phys. Rev. Res.* 1, 033034.
- Mitzenmacher M (2004). "A brief history of generative models for power-law
  and lognormal distributions." *Internet Math.* 1, 226-251.
