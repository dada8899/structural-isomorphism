# preisach_hysteresis_cascade

**Name (zh)**: Preisach 迟滞级联 (Barkhausen 跳变分布)
**Name (en)**: Preisach hysteresis cascade (Barkhausen-style jump distribution)
**Pre-registered exponent band**: Avalanche-size exponent τ ∈ [1.5, 2.5] (Sethna 2001 PRL 88:050601 gives τ = 1.5 in 3D + corrections); duration exponent τ_T ≈ 2; power-spectrum exponent 1 + θ with θ ≈ 0.5. Rationale: Sethna–Dahmen–Myers 1993, Sethna 2001, Spasojevic et al. 1996 Barkhausen Mn-Zn-ferrite.
**Verified status**: unverified (no `verified` field — confidence "speculative"). No KB predictions yet — taxonomy-completion entry. Distinct from `hysteresis_preisach` (already verified) which covers the non-coupled classical Preisach class — here the cascade *coupling* between bistable elements is the universality marker.

## Why this class needs an empirical anchor

This is the Sethna "crackling noise" class — coupled bistable elements at a disorder critical point producing power-law avalanche distributions. Distinguishing it from `hysteresis_preisach` (already verified, non-coupled) is the core taxonomy question. Verification needs the *coupling* signature: power-law avalanches, 1/f-like power spectrum, *not* just hysteresis-loop area.

KB linkage: 5 members across Condensed matter magnetism / Plasticity / Charge-density waves / Finance. Specific members not enumerated in JSON; grep KB JSONL.

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | Barkhausen noise time series — Spasojevic et al. 1996 PRE 54:2531 or Durin–Zapperi 2006 chapter datasets; some modern replication data on Zenodo (search "Barkhausen avalanche") | Various Zenodo / DOI:10.1103/PhysRevE.54.2531 | CC-BY | ~10⁵–10⁶ avalanches | Canonical anchor for the crackling-noise universality | Older datasets may be hard to retrieve; cite by figure if needed |
| 2 [fallback] | Acoustic-emission from compressed porous materials (Salje group, e.g. Salje et al. 2017 Phys Rev Lett 119:189901) | Supplementary data via Cambridge | Restricted to free supplementary | ~10⁴ events per experiment | Plasticity-side member; same τ band predicted | Acoustic-emission detection threshold biases small-event tail |
| 3 [stretch] | Stock-return inter-event tail from high-frequency LOB (re-using LOBSTER from `fractional_brownian_crossings`) | https://lobsterdata.com/info/DataSamples.php | Free academic | ~10⁷ events | Finance-side member; tests cross-domain τ universality | Confound with fBm long-memory; need to disentangle |

## Validation procedure (concrete)

```bash
mkdir -p data/preisach_hysteresis_cascade

# 1. Locate Barkhausen avalanche-size series (Zenodo search)
python scripts/fetch_zenodo.py --query "Barkhausen avalanche size distribution" \
  --out data/preisach_hysteresis_cascade/barkhausen.csv

# 2. Fit avalanche-size power-law + duration power-law + power spectrum slope
python -m v4.cli validate preisach_hysteresis_cascade \
  --data data/preisach_hysteresis_cascade/barkhausen.csv \
  --method crackling-noise-triplet \
  --tau-band 1.5,2.5 --tauT-band 1.7,2.3 --pwspec-band 1.3,1.7 \
  --null-controls poisson,lognormal,truncated-power-law

# 3. Distinguish from non-coupled hysteresis_preisach
python scripts/compare_preisach_classical_vs_cascade.py

# 4. Expected verdicts
#   PASS:  Sethna triplet (τ, τ_T, 1+θ) all in bands AND scaling relation τ_T = (τ-1)/σνz checks out,
#          AND distinguishable from non-coupled Preisach (no avalanche power-law in classical case)
#   FAIL:  any of triplet exponents outside bands, OR triplet inconsistent with each other
#   INCONCLUSIVE: triplet present but cutoff dominates the fit window
```

## Estimated workload

- Data acquisition: 4 h (Barkhausen data discovery on Zenodo can be slow — manual)
- Pipeline run: 5 h (triple power-law fit with Clauset method + bootstrap CI on each)
- Verdict + writeup: 3 h
- **Total: ~12 h / 1.5–2 days**

## Risks specific to this class

1. **No public datasets enumerated** — sub-agent must do dataset discovery as part of the work. If no clean Barkhausen series found, fall back to Salje acoustic-emission or simulate from random-field Ising (own code), defensibly.
2. **Confusion with classical Preisach**: must explicitly compare against `hysteresis_preisach` (already verified) to demonstrate distinct signature.
3. **No KB predictions yet** — grep KB JSONL before running to enumerate target members.

## Priority

⭐⭐⭐ (rationale: textbook physics interest but dataset hunting friction; useful as paired analysis with classical Preisach for class-boundary clarification)

## Dependencies

- `powerlaw`, `numpy`, `scipy`, `requests` (Zenodo API)
- No paid API
- Storage: < 5 GB
