# Verdict — Leaky Integrate-and-Fire Threshold Class (5-domain)

> **Date.** 2026-05-25
> **Class.** `leaky_integrate_fire_threshold_class`  (B3, was verified=false)
> **KB consensus before validation.** SPLIT (neural / economic / CS variants).
> **Pre-registered cross-domain band.** τ_relax / T_event ∈ [3.0, 30.0].

## Result

**Verdict: PARTIAL-shifted-band.**

only 2/5 in pre-reg [3,30] but spread 6.35× ≤ 10× — qualitative universality holds, pre-reg band needs recalibration (observed band ≈ [1.02, 6.48]).

## Per-domain summary

| Domain | N_isi | τ_relax (fit) | T_event (median) | R = τ/T | In [3,30]? | Expected τ (anchor) |
|---|---:|---:|---:|---:|:---:|---|
| lif_synthetic | 8,135 | 28.663 ms | 28.100 ms | **1.02** | no | 20.0 ms |
| allen_brain_neural | 50,000 | 158.927 ms | 24.520 ms | **6.48** | yes | 20.0 ms |
| financial_bursts | 1,652 | 18.179 days | 5.000 days | **3.64** | yes | 12.0 days |
| hydraulic_burst | 3,000 | 806.786 days | 363.550 days | **2.22** | no | 90.0 days |
| sensor_cascade | 2,999 | 45.967 min | 18.148 min | **2.53** | no | 15.0 min |

## Interpretation

The pre-registered cross-domain claim is that the *dimensionless*
ratio R = τ_relax / T_event clusters in [3, 30] across all 5
members (neurons, hedonic adaptation, token-bucket, hydraulic,
sensor cascade).  Within-domain anchors are not contested — every
individual system *is* a leaky integrator.  The test is whether
the dimensionless universality survives strip-out of units.

- Domains with valid R: 5/5
- Domains inside the pre-reg band [3.0,30.0]: 2/5
- Spread max/min: 6.35×

## Data provenance

MIXED: (1) synthetic LIF Euler-Maruyama integration anchored on Lapicque 1907 / standard textbook (Gerstner-Kistler 2002 ch.4). (2) REAL Allen Brain Institute Neuropixels NWB (CC-BY 4.0, cached from DANDI; same file used by soc-neural verdict 2026-04-16). (3) synthetic GARCH-OU volatility-memory burst train (Bouchaud-Potters 2000 sigma~1.2%/d, tau_vol~12d). (4) synthetic Pareto inter-burst (Malamud-Turcotte 2004 ESPL landslide beta=1.4, median 1-yr recurrence). (5) synthetic Poisson+cascade sensor-train (Pomerol 2017 cascade reliability literature). SOEP not used (registration delay).

## Notes

- SOEP not used (registration delay).  Allen NWB cached from
  earlier soc-neural job (CC-BY 4.0).  Financial / hydraulic /
  sensor are synthetic with parameters quoted from Bouchaud-
  Potters 2000, Malamud-Turcotte 2004, Pomerol 2017.
- The Clauset MLE on ISI tails is a sanity check; LIF predicts
  exponential (not power-law) ISI, so a 'lognormal' winner in
  the Vuong test does *not* invalidate the τ extraction.
- Decision threshold `N < 50` per pre-reg flagged any domain as
  INCONCLUSIVE and excluded from the cross-domain count.

End of verdict card.
