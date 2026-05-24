# fractional_brownian_crossings

**Name (zh)**: 分数布朗运动零交叉类
**Name (en)**: Fractional Brownian motion level crossings
**Pre-registered exponent band**: Inter-crossing return-time power-law α = 2 - H with H ∈ (0, 1) giving α ∈ (1, 2). Hurst exponent H ∈ [0.55, 0.80] for high-frequency LOB mid-price; H ∈ [0.65, 0.85] for hydrology gauge records; H ∈ [0.50, 0.60] for Internet traffic. Rationale: Mandelbrot–Van Ness 1968 SIAM Rev 10:422, Beran 1994.
**Verified status**: unverified (no `verified` field in JSON — speculative confidence). No KB predictions yet — this is a textbook-class entry inserted by the taxonomy-completion sweep.

## Why this class needs an empirical anchor

fBm is a canonical *long-memory* process distinct from Markov class — the verification matters because the KB has multiple members marked as power-law tail in inter-event times whose mechanism could be either fBm-style long memory or memoryless Poisson with heavy tails. Distinguishing them is non-trivial without a long enough series. Validation on LOBSTER high-frequency limit-order-book mid-price provides cleanest test (sub-second resolution, millions of observations, H well-characterised in literature).

KB linkage: 5 members across finance / network-comms / hydrology / turbulence. Domain list: Finance, Network/Communications, Hydrology/Geophysics, Turbulence physics. (Specific members not enumerated in JSON; sub-agent should grep KB JSONL for fBm-associated entries before run.)

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | LOBSTER Limit Order Book Reconstructor (academic sample: AAPL, MSFT, INTC, GOOG full LOB 2012-06-21) | https://lobsterdata.com/info/DataSamples.php | Free academic sample / paid commercial | ~10⁷ events per stock per day | Canonical high-frequency H estimation; benchmark for fractional-memory finance | Free sample is only single day; longer series requires paid licence |
| 2 [fallback] | USGS Streamflow daily discharge (Yangtze + Mississippi + Nile annual flood series, multi-century records) | https://waterdata.usgs.gov/ + WMO Global Runoff Data Centre | Public | ~150 y daily / centuries annual | Hurst's original 1951 anchor — Nile floods H ≈ 0.73 | Daily-to-annual aggregation changes effective H estimate |
| 3 [stretch] | CAIDA Internet backbone traffic traces (passive, anonymised, 2018–2024) | https://www.caida.org/catalog/datasets/passive_dataset/ | Free academic, registration | ~TB of packet traces per snapshot | Tests network-comms variant; literature H ≈ 0.55–0.75 (Leland–Taqqu 1994) | Heavy storage; requires registration |

## Validation procedure (concrete)

```bash
mkdir -p data/fractional_brownian_crossings

# 1. LOBSTER free sample
curl -L "https://lobsterdata.com/data/sample/INTC_2012-06-21_34200000_57600000_orderbook_10.csv" \
  -o data/fractional_brownian_crossings/intc_lob.csv

# 2. Estimate Hurst exponent via R/S, DFA, wavelet methods (consensus)
python -m v4.cli validate fractional_brownian_crossings \
  --data data/fractional_brownian_crossings/intc_lob.csv \
  --method hurst-multimethod --estimators rs,dfa,wavelet,whittle \
  --hurst-band 0.55,0.80 --null-controls bm-h05,markov-short-memory

# 3. Cross-domain: same pipeline on USGS Yangtze
python scripts/cross_domain_hurst.py

# 4. Expected verdicts
#   PASS:  Hurst estimators agree within ±0.05, H in band, return-time tail power-law
#          exponent matches α = 2 - H within ±0.15
#   FAIL:  H ≈ 0.5 (no long memory) OR estimators disagree by > 0.15
#   INCONCLUSIVE: methods disagree (very common for short series < 10⁴)
```

## Estimated workload

- Data acquisition: 3 h (LOBSTER free sample + USGS API both fast)
- Pipeline run: 5 h (multi-method Hurst estimation, especially Whittle MLE)
- Verdict + writeup: 3 h
- **Total: ~11 h / 1.5 days**

## Risks specific to this class

1. **H estimator disagreement** is common; pre-register consensus rule (e.g., median of R/S, DFA, wavelet, Whittle within ±0.05).
2. **Multifractal vs monofractal**: real LOB data is multifractal; H is then ambiguous. Use the q=2 multifractal exponent as the canonical H.
3. **No KB predictions yet** — sub-agent must first grep KB JSONL for fBm-associated entries to enumerate the target predictions properly.

## Priority

⭐⭐⭐ (rationale: canonical textbook test, but no pre-registered KB predictions yet — extra brief-writing time needed before validation)

## Dependencies

- `numpy`, `scipy`, `nolds`, `pywavelets`, `MFDFA` (multifractal DFA package)
- LOBSTER free sample no auth; paid for longer series
- Storage: ~10 GB if extending beyond free sample
