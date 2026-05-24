# percolation_connectivity

**Name (zh)**: 渗流临界相变与 tipping point 类
**Name (en)**: Percolation Critical Tipping Point
**Pre-registered exponent band**: Order-parameter exponent β ∈ [0.30, 0.45]; correlation-length exponent ν ∈ [0.90, 1.20]; critical threshold p_c ∈ [0.15, 0.35] for social-contagion-style transitions. Rationale: 2D Ising β = 5/36 ≈ 0.139 (lower bound) up to mean-field β = 1/2 (upper bound); Broadbent–Hammersley 1957, Newman–Ziff 2000.
**Verified status**: false (target: v0.4). B3 consensus = SPLIT — sociology vs entrepreneurship vs finance variants suggested as separable.

## Why this class needs an empirical anchor

Percolation is a textbook universality class; the empirical question is which *real-world* contagion processes actually exhibit second-order critical scaling versus first-order discontinuous transitions. The Reddit identity-conversion dataset is well-suited: identity flips are individual events with observable neighbour states, allowing direct estimation of β and ν.

KB linkage: 3 members — social-identity contagion (sociology), competitor-entry critical scale (entrepreneurship), liquidity externalities active-vs-index (financial microstructure).

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | Reddit Pushshift archive + Politosphere identity-label dataset (Hofmann et al. 2022) 2018–2024 | https://github.com/CopenhagenCSS/Politosphere | CC-BY 4.0 | ~20M users × 20 communities | Pre-registered target; identity flips observable as flair changes | Politosphere labels are noisy; coverage skewed to active users |
| 2 [fallback] | Granovetter-style empirical contagion dataset: Christakis–Fowler 2007 obesity/Framingham network propagation | https://datadryad.org/stash search "Christakis Fowler 2007" | Restricted (IRB) | ~12k subjects × 32 y | Classical contagion test with clean order-parameter measurement | Restricted access; older data |
| 3 [stretch] | Public Twitter cascade dataset from Cheng et al. 2014 WWW (recursive cascade structures) | https://snap.stanford.edu/data/cascades.html | CC-BY 4.0 | ~150k cascades | Tests cluster-size distribution at criticality | Pre-API-shutdown; specific to Twitter circa 2014 |

## Validation procedure (concrete)

```bash
mkdir -p data/percolation_connectivity

# 1. Pushshift + Politosphere merge
python scripts/fetch_politosphere.py --out data/percolation_connectivity/politosphere.parquet

# 2. Estimate critical exponents from identity-flip events
python -m v4.cli validate percolation_connectivity \
  --data data/percolation_connectivity/politosphere.parquet \
  --method finite-size-scaling --order-param identity_flip_density \
  --beta-band 0.30,0.45 --nu-band 0.90,1.20 \
  --null-controls first-order-jump,no-transition

# 3. Expected verdicts
#   PASS:  β and ν in bands consistent with 2D Ising universality, p_c in [0.15, 0.35],
#          cluster-size distribution power-law at p_c with exponent τ ≈ 2.0–2.3
#   FAIL:  first-order signature (discontinuous m(p)) OR exponents far from 2D Ising
#   INCONCLUSIVE: signal present but finite-size effects dominate
```

## Estimated workload

- Data acquisition: 5 h (Pushshift bulk + Politosphere merge)
- Pipeline run: 8 h (finite-size scaling requires multiple system sizes — slow)
- Verdict + writeup: 3 h
- **Total: ~16 h / 2 days**

## Risks specific to this class

1. **Mechanism ambiguity**: identity flips on Reddit may involve simple contagion (one neighbour suffices) or complex contagion (multiple neighbours needed). Each gives different exponents.
2. **Finite-size scaling** needs system sizes spanning at least 2 orders of magnitude — only achievable by stratifying communities by size.
3. **Politosphere label noise** propagates into β estimate; use bootstrap with label-flipping noise injection.

## Priority

⭐⭐⭐⭐ (rationale: clean physics-class test; if Ising exponents recovered on sociological data, strong textbook-class confirmation worth a paper section)

## Dependencies

- `numpy`, `scipy`, `networkx`, `pyzstd`, `pandas`
- Storage: ~30 GB Pushshift slice
- No paid API
