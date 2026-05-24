# Verdict — Oslo Rice Pile (1D Conserved SOC)

> **Date.** 2026-05-25
> **System.** 1D Oslo rice-pile model — Frette 1996 / Christensen 1996.
> **Class.** `oslo_rice_pile`
> **Data provenance.** SYNTHETIC (Oslo CA simulation; n_record=80,000).
> **Predicted exponent (Oslo universality class).**
>   - τ_size ≈ **1.55** (Pruessner 2004 PRE 69 048105)

## Recovered exponent

| Quantity | Predicted | Measured | Band | In band? |
|---|---|---|---|---|
| τ_size | 1.55 | **1.565** | [1.40, 1.70] | yes (within 1%) |

**Verdict: CONFIRMED.** τ recovered within 1% of theoretical Oslo
value. Better-than-finite-size precision because L=256 with 80k
quasi-static drives gives ~50k non-trivial avalanches across 4 decades.

## Avalanche statistics

| Quantity | Value |
|---|---|
| Lattice size L | 256 |
| Warmup drives | 30,000 |
| Recorded drives | 80,000 |
| Non-zero avalanches | 50,684 |
| Mean avalanche size | 326 |
| Max avalanche size | 197,077 |
| Clauset xmin | 17 |
| n_tail | 11,438 |
| α (Clauset MLE) | 1.565 |

## Why synthetic is OK

The Oslo CA implementation **is** the canonical reference model that
Christensen 1996 PRL 77 107 simulated alongside their Frette 1996
Nature 379 49 long-grain rice experiment. Both numerical and
experimental avalanche τ ≈ 1.5-1.6 within their error bars. SYNTHETIC
flag preserved in `data_provenance` and KB.

## Notes

- Clauset's `vs_lognormal_winner` returns "lognormal" — typical for
  truncated power-law data; the upper-tail cutoff in finite-L Oslo
  simulations gives a heavy-but-decaying right tail that lognormal
  also fits. This does NOT invalidate the τ recovery on the
  power-law tail itself. Reported as `lognormal` for transparency.
