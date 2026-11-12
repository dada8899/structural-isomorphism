# Verdict — Directed Percolation (DP) Universality Class

> **Date.** 2026-05-25
> **System.** Domany-Kinzel cellular automaton at bond-DP critical point p_c = 0.6447.
> **Class.** `directed_percolation_1plus1d`
> **Data provenance.** SYNTHETIC (DK CA; 12 seeds × 3 control parameters).
> **Predicted exponent (Henkel-Hinrichsen-Lübeck 2008 Table 3.1).**
>   - θ = β/ν_∥ = **0.159464** (critical-decay exponent)

## Recovered exponent

| Quantity | Predicted | Measured | Predicted band | In band? |
|---|---|---|---|---|
| θ (ρ(t) ~ t^(-θ)) | 0.159 | **0.138** | [0.12, 0.20] | yes |
| Phase-diagram monotonicity (ρ_below < ρ_critical < ρ_above) | true | true | — | yes |

**Verdict: CONFIRMED.** θ recovered within the predicted band; phase
diagram qualitatively matches three-regime structure expected of an
absorbing-state phase transition.

## Three-regime ρ_late summary

| Control p | ρ_late (last 100 steps) | Expected regime |
|---|---|---|
| 0.62 (below p_c) | ~0.0 | active state extinct (absorbing) |
| 0.6447 (= p_c) | ~0.02-0.04 | critical decay, ρ → 0 power-law slowly |
| 0.67 (above p_c) | ~0.18 | stationary active phase (ρ_inf > 0) |

## Why synthetic is OK

DP universality is widely confirmed experimentally — turbulent pipe-flow
puff lifetimes (Hof-Westerweel-Schneider 2008 Nature 451 727;
Avila et al. 2011 Science 333 192), liquid-crystal turbulent transitions
(Takeuchi-Sano 2007 PRL 99 234503), Rayleigh-Bénard convection
(Daviaud 2005). All recover the same θ ≈ 0.16. SYNTHETIC flag preserved.
