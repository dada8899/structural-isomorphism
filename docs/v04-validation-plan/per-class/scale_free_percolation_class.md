# scale_free_percolation_class

**Name (zh)**: 无标度网络渗流与级联类
**Name (en)**: Scale-Free Network Percolation & Cascade
**Pre-registered exponent band**: Degree distribution exponent γ ∈ [2.1, 2.9]; percolation threshold p_c < 0.10 for targeted attack on top-degree hubs; effective diameter d_eff ≤ log(N)/log(log(N)) within 30%. Rationale: Cohen–Erez–ben-Avraham–Havlin 2000 PRL 85:4626 + Barabási–Albert 1999 Science 286:509.
**Verified status**: false (target: v0.4). B3 consensus = REJECT, note "folded into percolation_connectivity." See companion file `percolation_connectivity.md`.

## Why this class needs an empirical anchor

B3 already proposed folding this into the broader `percolation_connectivity` class. The verification job is twofold:

1. Confirm the scale-free degree distribution + low p_c signature empirically on DeFi cross-protocol re-collateralization graphs (a domain where the network structure is observable in full).
2. Compare the *exponent and threshold* values against `percolation_connectivity` (a generic Ising-class continuous transition) — if they coincide, fold is justified; if SF-specific signatures (γ-dependent dual robustness/fragility) emerge, the class survives independently.

KB linkage: 3 members — collateral re-hypothecation loops, systemic-risk scale-free network in financial-market microstructure, cyber-insurance correlation problem.

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | DefiLlama liquid-staking-derivative subgraph (stETH, rETH, cbETH, etc.) + Etherscan token-transfer data 2020–2025 | https://defillama.com/lsd + https://etherscan.io/exportData | DefiLlama: CC-BY-NC / Etherscan free up to rate limit | ~50 protocols × 10⁶ addresses | Original pre-registered target; full network observable on-chain | Etherscan rate limits; address-clustering ambiguity |
| 2 [fallback] | BIS cross-border banking exposures network (publicly reported annually) | https://www.bis.org/statistics/bankstats.htm | Free | ~80 jurisdictions × 25 years | Cleaner systemic-risk-network test on traditional finance | Aggregated to jurisdiction level — loses node-level structure |
| 3 [stretch] | Internet AS-level topology (CAIDA AS-Relationships dataset, monthly snapshots 2000–2025) | https://www.caida.org/catalog/datasets/as-relationships/ | Free academic | ~75k ASes | Canonical Barabási–Albert empirical anchor outside finance | Off-topic relative to the KB's finance-focused members |

## Validation procedure (concrete)

```bash
mkdir -p data/scale_free_percolation_class

# 1. DefiLlama LSD + Etherscan
python scripts/fetch_defi_lsd_graph.py \
  --protocols stETH,rETH,cbETH,frxETH,sfrxETH,LsETH \
  --out data/scale_free_percolation_class/lsd_graph.graphml

# 2. Fit degree distribution + percolation simulation
python -m v4.cli validate scale_free_percolation_class \
  --data data/scale_free_percolation_class/lsd_graph.graphml \
  --method degree-fit + percolation-sim --attack-mode targeted,random \
  --gamma-band 2.1,2.9 --pc-band 0,0.10 --null-controls erdos-renyi,configuration-model

# 3. Expected verdicts
#   PASS:  gamma in band, targeted p_c < 0.10, random p_c >> 0.10 (dual robustness/fragility)
#          AND signature distinguishable from generic percolation_connectivity
#   FAIL:  not scale-free (e.g., exponential decay) OR p_c too high
#   INCONCLUSIVE: scale-free confirmed but not distinguishable from connectivity class
```

## Estimated workload

- Data acquisition: 5 h (Etherscan rate limits ~5 req/s; need to paginate carefully)
- Pipeline run: 4 h (degree fit + percolation simulation over multiple attack orderings)
- Verdict + writeup including fold-decision narrative: 3 h
- **Total: ~12 h / 1.5 days**

## Risks specific to this class

1. **Address clustering**: many on-chain addresses are owned by the same entity. Without clustering, γ is inflated. Use Chainalysis-style heuristics or community detection.
2. **Fold-vs-keep**: B3 already says REJECT/fold. Sub-agent must explicitly compare against `percolation_connectivity` exponents to determine empirical distinctiveness.
3. **DefiLlama rate limits + NC licence**: derivative use OK but redistribution of raw data not allowed.

## Priority

⭐⭐⭐ (rationale: REJECT likely confirmed; mainly useful as a paired analysis with `percolation_connectivity` for the fold decision)

## Dependencies

- `networkx`, `powerlaw`, `requests`, `web3py`, `tqdm`
- DefiLlama no API key; Etherscan free key
- Storage: ~5 GB
