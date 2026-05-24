# extreme_value_tail_class

**Name (zh)**: 极值理论重尾分布类
**Name (en)**: Extreme Value Theory & Heavy-Tailed Distributions
**Pre-registered exponent band**: GPD tail shape ξ ∈ [0.10, 0.60] (Fréchet domain); equivalent power-law tail α = 1/ξ ∈ [1.7, 10]. Rationale: Fisher–Tippett–Gnedenko + Pickands–Balkema–de Haan; observed ξ across wind / seed / catastrophe insurance literature clusters in 0.15–0.45 (Embrechts–Klüppelberg–Mikosch 1997, Coles 2001).
**Verified status**: false (target: v0.4). B3 consensus = REJECT with note "limit-theorem class, not mechanism" — verification will produce either a PASS (universal ξ band recovered) or a documented REJECT that justifies its removal from the mechanism taxonomy.

## Why this class needs an empirical anchor

EVT is foundational textbook material; every insurance / civil-engineering / hydrology curriculum teaches GEV+GPD as universal limiting distributions. The B3 cross-judge marked it REJECT not because the math is wrong but because EVT is a *statistical descriptor* of any heavy-tailed process rather than a *mechanism*. The v0.4 verification matters precisely as a stress test of our "mechanism vs descriptor" boundary: if ξ collapses to a tight universal band across 3 unrelated domains (wind on tall buildings, seed dispersal, catastrophe insurance losses), the REJECT is defensible because the universality is generic GEV not mechanistic. If ξ shows mechanism-specific bands (e.g. wind tightly Weibull-bounded ξ<0, seeds Fréchet ξ>0), then we have grounds to *split* EVT into sub-classes.

KB linkage: 4 members listed (catastrophe bonds, catastrophe derivatives, seed dispersal, wind load on high-rises) — all four are testable.

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | Seed Dispersal Distance Database (Thomson et al. 2011, Ecology 92:1797, updated) | doi:10.5061/dryad.7vh2g | CC-BY | ~140 species × 200–2000 mark–recapture trials | Original pre-registered target; clean tail data already binned by species | Heterogeneous methodology across species; censoring at edge of plot |
| 2 [fallback] | NOAA NCEI Storm Events Database (wind speed extremes, 1996–2025) | https://www.ncei.noaa.gov/access/search/data-search/storm-events | Public domain | ~1.5M events | Cross-domain check (wind extremes vs seed extremes) | Reporting bias toward damaging events; truncation at low end |
| 3 [stretch] | EM-DAT catastrophe insurance loss dataset (Munich Re / CRED) | https://www.emdat.be/ | Free academic, registration | ~25k disasters 1900–2025 with USD loss | Direct test of insurance-side ξ; canonical Embrechts use case | USD inflation adjustment + heterogeneous reporting |

## Validation procedure (concrete)

```bash
# 1. Download primary
mkdir -p data/extreme_value_tail_class
curl -L "https://datadryad.org/api/v2/datasets/doi%3A10.5061%2Fdryad.7vh2g/download" \
  -o data/extreme_value_tail_class/seed_dispersal.zip
unzip data/extreme_value_tail_class/seed_dispersal.zip -d data/extreme_value_tail_class/

# 2. Fit GPD via POT (peaks-over-threshold)
python -m v4.cli validate extreme_value_tail_class \
  --data data/extreme_value_tail_class/seed_dispersal.csv \
  --method pot --threshold-quantile 0.90 \
  --alpha-band 1.7,10 --null-controls lognormal,exponential

# 3. Expected verdicts
#   PASS:  ξ ∈ [0.10, 0.60] AND GPD log-LR vs exponential > 0 AND KS p > 0.05
#   FAIL:  ξ outside band OR exponential preferred (i.e. not actually heavy-tailed)
#   INCONCLUSIVE: heavy-tail accepted but cross-species ξ spread > 0.20 (universality weak)
```

## Estimated workload

- Data acquisition: 2 h (Dryad + EM-DAT registration)
- Pipeline run: 3 h (POT fit + bootstrap CIs + 3 null controls × 140 species)
- Verdict + writeup: 2 h
- **Total: ~7 h / 1 day for one sub-agent**

## Risks specific to this class

1. **Descriptor-vs-mechanism collapse**: B3 already flagged this. If wind, seeds, and insurance all give the *same* ξ, that supports REJECT (it is generic EVT), not PASS. Pre-register the interpretation explicitly.
2. Threshold selection bias: ξ is notoriously sensitive to threshold choice; use mean-excess plot + Hill plot stability check.
3. Seed dispersal has known left-truncation (cannot measure < 1 m); handle with conditional GPD.

## Priority

⭐⭐⭐⭐ (rationale: easy data, canonical method, and the result — PASS or REJECT — is informative either way for the v0.4 taxonomy paper)

## Dependencies

- `scipy.stats.genpareto`, `pyextremes` (POT fitting), `powerlaw` (cross-check)
- No API key
- Storage: < 500 MB total
