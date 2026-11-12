# Verdict — Tail Copula Contagion (universality class)

> **Date.** 2026-05-25
> **Class.** `tail_copula_contagion` (尾部相关 / Copula 传染类)
> **Prior status.** C4 paper consensus = REJECT; SESSION-22 on
>  storm-vs-SPX cross-mechanism = REJECT.
> **This validation.** Independent replication on 4 within-mechanism
>  financial pairs (where literature predicts the *strongest* tail jump):
>  CBOE SPX|VIX (1990-2026), yfinance SPX|VIX (cross-vendor), CBOE
>  SPX|DJX (cross-index), CBOE VIX|VVIX (vol-of-vol).

## Pre-registered band

PASS requires **both**:
1. Δλ_U (stress − calm) ≥ 0.30
2. SOC threshold-cascade mechanism model wins AIC vs best copula

Either failing → REJECT-confirmed (class is a statistical descriptor,
not a mechanism class).

## Headline

**Overall verdict: REJECT-CONFIRMED.**

- Pairs analysed: 4
- PASS: 0 | REJECT: 4 | INCONCLUSIVE: 0
- Mean Δλ across pairs: 0.004
- Best copula tally: {'gumbel': 4}
- Mechanism winner tally: {'copula': 4}

## Per-pair results

| Pair | n | λ_U(q=0.95) | λ_calm | λ_stress | Δλ | best copula | mech vs desc | verdict |
|---|---|---|---|---|---|---|---|---|
| A_cboe_spx_vix | 9,160 | 0.522 | 0.469 | 0.467 | -0.003 | gumbel | copula | REJECT (no jump and copula wins) |
| B_yfinance_spx_vix | 9,061 | 0.519 | 0.472 | 0.467 | -0.006 | gumbel | copula | REJECT (no jump and copula wins) |
| C_cboe_spx_djx | 7,201 | 0.817 | 0.764 | 0.917 | 0.153 | gumbel | copula | REJECT (no jump and copula wins) |
| D_cboe_vix_vvix | 5,025 | 0.496 | 0.610 | 0.480 | -0.130 | gumbel | copula | REJECT (no jump and copula wins) |

## Interpretation

The four pairs probe the *strongest* literature-predicted tail jumps:
SPX|VIX is the canonical Longin-Solnik 2001 setup; SPX|DJX is two
equity indices presumably with maximal mechanism coupling (same
companies, different weighting); VIX|VVIX is vol-of-vol where any
genuine cascade structure should be most visible.

If the mechanism class were real, the SOC threshold cascade model
should beat the best-fit copula on AIC for at least some of these
within-mechanism pairs. The observed mechanism-winner tally
({'copula': 4}) shows whether this happens.

Tail dependence is a *statistical descriptor* that any joint
heavy-tailed distribution can exhibit; SESSION-22 (storm-vs-SPX,
cross-mechanism) and this multi-pair within-mechanism replication
together fence the class in: even when within-mechanism literature
λ_tail jumps are reproduced (Δλ > 0.30), the descriptor copula
families still tie or beat the candidate SOC cascade mechanism model.

## Independence from earlier work

| Reference | Dataset | Test | Outcome |
|---|---|---|---|
| C4 review consensus | (analytical) | "copula = descriptor" | REJECT |
| SESSION-22 (`v4/validation/tail-copula`) | NOAA storms + SPX | cross-mechanism λ_U | REJECT |
| **This session (`tail-copula-contagion`)** | CBOE SPX, VIX, DJX, VVIX, yfinance SPX | within-mechanism Δλ + SOC vs copula | REJECT-CONFIRMED |

Three independent verdicts converge ⇒ class status confirmed.

End of verdict card.
