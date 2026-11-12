# schelling_credible_commitment

**Name (zh)**: 可信承诺 / 时间不一致类
**Name (en)**: Schelling Credible Commitment
**Pre-registered exponent band**: Logit slope b ∈ [1.2, 2.6] for `logit(p_exec) ~ a + b · s` (s = sunk-cost ratio); execution rate > 0.75 for s > 0.4 and < 0.35 for s < 0.2. Rationale: Bown 2009 WTO retaliation empirics + Kydland–Prescott 1977 time-inconsistency theory + Bagwell–Staiger 2002 trade-agreement formal models.
**Verified status**: false (target: v0.4). B3 consensus = REJECT.

## Why this class needs an empirical anchor

Schelling-style credible commitment is widely invoked across game theory, IR, and monetary policy, but the B3 REJECT reflects scepticism about whether "credibility" is a mechanism in the same sense as a bifurcation or threshold. Empirical verification on WTO retaliations gives the cleanest test: each retaliation has a *measurable* sunk cost and a *measurable* execution outcome. If the logit relation holds with a universal slope across decades and dispute types, the class earns mechanism status. If slopes vary wildly by region/era, the REJECT stands.

KB linkage: 5 members — contract hold-up, entry deterrence (capacity over-commitment), trade tariff retaliation, bundled concessions in IR, monetary time-inconsistency.

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | WTO Dispute Settlement Database (Horn–Mavroidis World Bank dataset, updated through 2025) | https://datacatalog.worldbank.org/search/dataset/0039943 | CC-BY 4.0 | ~620 disputes, ~110 with retaliation authorisation | Original pre-registered target; sunk costs partially measurable | Coding of "sunk cost" requires manual case-by-case judgement |
| 2 [fallback] | Federal Reserve FOMC forward-guidance language + realised policy deviations 2008–2025 (Hansen–McMahon dataset) | https://www.aeaweb.org/articles?id=10.1257/aer.20151359 (replication data) | CC-BY 4.0 | ~140 FOMC statements + ex post outcomes | Tests monetary credibility variant; cleaner numerical commitment | Cross-cycle non-stationarity; FOMC reaction function changed in 2012 |
| 3 [stretch] | Global Trade Alert anti-dumping investigation database (sunk cost proxied by investigation duration + legal fee disclosures) | https://www.globaltradealert.org/data_extraction | Free academic | ~25k measures since 2009 | Larger N for statistical power | Sunk-cost proxy is noisy |

## Validation procedure (concrete)

```bash
mkdir -p data/schelling_credible_commitment

# 1. Download WTO disputes
curl -L "https://datacatalogfiles.worldbank.org/.../wto_disputes_v2024.csv" \
  -o data/schelling_credible_commitment/wto_disputes.csv

# 2. Logit fit p_exec ~ s with bootstrap CI on slope
python -m v4.cli validate schelling_credible_commitment \
  --data data/schelling_credible_commitment/wto_disputes.csv \
  --method logit --predictor sunk_cost_ratio --outcome retaliation_executed \
  --slope-band 1.2,2.6 --null-controls uniform-execution,random-coin

# 3. Expected verdicts
#   PASS:  slope b ∈ [1.2, 2.6] with 95% CI excluding 0, and threshold behaviour
#          (high-execution band > 0.75, low-execution band < 0.35) confirmed
#   FAIL:  slope outside band OR not statistically distinguishable from 0
#   INCONCLUSIVE: direction correct, magnitude outside band
```

## Estimated workload

- Data acquisition + sunk-cost coding: 6 h (manual coding is the bottleneck — even partial coverage of 200 disputes takes a day)
- Pipeline run: 1 h (logit is cheap)
- Verdict + writeup: 3 h
- **Total: ~10 h / 1.5 days**

## Risks specific to this class

1. **Sunk-cost measurement** is the dominant uncertainty. Pre-register a coding protocol (e.g., legal-fee disclosures + reputational cost proxy via prior dispute history) before opening the data.
2. **Selection bias**: only disputes that reach the retaliation phase are observed; truncation at the filing decision. Use Heckman correction or report as caveat.
3. The class may turn out to be domain-specific (trade ≠ monetary policy) — pre-register that "passing the trade variant only" → SPLIT, not PASS.

## Priority

⭐⭐⭐ (rationale: high paper interest because economics members are rare in the KB, but manual coding makes it labour-heavy and the REJECT may be confirmed)

## Dependencies

- `pandas`, `statsmodels` (logit), `numpy`
- No paid API
- Storage: < 50 MB
- **Caveat**: needs human-in-the-loop coding of sunk-cost ratio — not fully automatable
