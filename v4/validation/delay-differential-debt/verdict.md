# Verdict — delay_differential_debt (REJECT-confirm test)

> **Date.** 2026-05-25
> **Class.** `delay_differential_debt` (B3 REJECT, B1 KEEP — CONTESTED).
> **Prior.** C4 paper §4.3 prototype 'mechanism vs limit theorem confusion'.
> **Data.** SYNTHETIC — 6 DDE simulations with literature mechanism timescales.

## Overall verdict: **REJECT_confirmed_normal_form**

- Absolute T_period CV across systems = 1.184 (threshold for universality clustering: 0.30)
- T_period_max / T_period_min = 21.80
- Normalised T/τ mean = 5.035 (Wright-Hopf theorem predicts 4.0); CV = 0.245
- Crisis-magnitude power-law α: 6/6 in pre-registered band [1.5, 3.0]
- ΔAIC (AR(2) − DDE-oracle) median = -124.36 (positive = DDE wins; negative = AR(2) wins)
- DDE-wins-by-≥2 / AR(2)-wins-by-≥2 / tie: 0 / 6 / 0

## Reason for verdict

Absolute T_period CV >= 0.30 (scatter > 30%) but normalised T/τ clusters near Wright-Hopf theorem value 4 — confirms C4 §4.3 'normal-form theorem mistaken for universality class'

## Per-system table

| System | τ (yr) | T_period (yr) | T/τ | n_cycles | α_PL | ΔAIC(AR2−DDE) |
|---|---|---|---|---|---|---|
| us_debt_gdp | 10.0 | 36.53 | 3.65 | 125 | 2.84 | -120.3 |
| chile_copper_fiscal | 5.0 | 28.02 | 5.60 | 122 | 2.98 | -131.5 |
| argentina_inflation_debt | 3.0 | 10.95 | 3.65 | 132 | 3.00 | -122.2 |
| corporate_debt_compustat | 7.0 | 47.95 | 6.85 | 121 | 2.72 | -126.6 |
| enso_delayed_oscillator | 1.5 | 7.50 | 5.00 | 137 | 3.00 | -152.0 |
| permafrost_methane | 30.0 | 163.50 | 5.45 | 112 | 2.49 | -97.5 |

## Interpretation — link to C4 paper §4.3

The Wright 1955 theorem says: for any 1-D scalar DDE near Hopf
bifurcation, oscillation period ≈ 4·τ. This is a *theorem about*
*the equation form*, not about the underlying physics. If a
group of systems with mechanism-distinct τ values is
'unified' by T/τ ≈ 4, the unification is provided by the math,
not by a shared critical mechanism in the Bak-Tang-Wiesenfeld /
Clauset-Stumpf-Porter sense.

This SPLIT test isolates the two: 
- **Absolute T_period across domains** = invariant a universality
  class would predict (similar to τ_size = 1.27 in 2D Manna).
- **T/τ ratio** = the Wright-Hopf theorem, holds for ANY DDE.

If only T/τ clusters and absolute T_period scatters, we have a
normal-form theorem masquerading as a universality class —
exactly the failure mode the C4 paper §4.3 anticipates and B3
REJECTED at avg confidence 0.75.

## Comparison to manna_sandpile (positive control)

Manna sandpile across L ∈ {64,128,256} lattice sizes:
τ_size = 1.27 ± 0.03 (CV < 0.05) → real universality.
Even with the parallel-update finite-L drift, exponent
stays in a 1.15-1.70 band tied to a single mechanism (conserved
stochastic toppling). delay_differential_debt has no such
anchor because its members live on intrinsically different
mechanism timescales.

End of verdict card.
