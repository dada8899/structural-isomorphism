# second_order_damped_oscillator

**Name (zh)**: 二阶阻尼振子类
**Name (en)**: Second-Order Damped Oscillator
**Pre-registered exponent band**: First-mode natural frequency ω₀ ∈ [0.10, 0.30] Hz for super-tall buildings; damping ratio ζ ∈ [0.005, 0.030]; resonance amplification Q = 1/(2ζ) ∈ [17, 100]. Rationale: Kareem 1981 wind-engineering review; Tamura–Suganuma 1996 amplitude-dependent damping; ASCE 7-22 standard.
**Verified status**: false (target: v0.4). B3 consensus = KEEP — high prior. **Likely SPLIT outcome** because B3 also flagged "linear-class-not-mechanism" concerns elsewhere.

## Why this class needs an empirical anchor

A linear second-order ODE is the most textbook system in physics. The B3 KEEP reflects the fact that across high-rises and power systems, the *same* parameters (ω₀, ζ) describe the dominant mode. The risk is the same as Markov / EVT — that "second-order ODE" is a math template not a mechanism. Validation should test whether the *cross-domain* ω₀ × ζ joint distribution clusters or scatters; clustering supports mechanism interpretation, scatter supports REJECT/template.

KB linkage: 3 members — power-system small-signal oscillation, power-system transient stability, high-rise wind-induced vibration.

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | Tamura-lab tall-building damping database (Architectural Institute of Japan, public summary 2012, ~200 buildings) | http://www.wind.arch.t-kougei.ac.jp/info_center/damping.html | Free, summary-level | ~200 buildings | Curated ω₀, ζ estimates from operational SHM | Summary only — no raw time series; values pre-computed |
| 2 [fallback] | Shanghai World Financial Center / Taipei 101 / Burj Khalifa structural-health-monitoring public datasets | Cited in academic papers (e.g. Li et al. 2018 Eng Struct 158:51 for SWFC) | Mixed open/restricted | ~8000 monitoring hours × 3 buildings | Allows independent ω₀/ζ extraction from raw accel time series | Raw data not always public — may need to digitise published spectra |
| 3 [stretch] | NERC Eastern Interconnection PMU phasor measurement data 2015–2023 (small-signal oscillation modes) | https://www.nerc.com/pa/RAPA/PA/Pages/SecureFTP.aspx (restricted) or aggregated EPRI publications | Restricted | ~10⁶ events × 100 PMUs | Cross-domain power-system variant — tests ω₀/ζ universality vs domain-specificity | Restricted access; sanitised aggregates only |

## Validation procedure (concrete)

```bash
mkdir -p data/second_order_damped_oscillator

# 1. Tamura building database — bulk scrape summary
python scripts/scrape_tamura_db.py --out data/second_order_damped_oscillator/buildings.csv

# 2. Fit joint distribution of (ω₀, ζ) across buildings
python -m v4.cli validate second_order_damped_oscillator \
  --data data/second_order_damped_oscillator/buildings.csv \
  --method joint-dist-cluster --features omega0,zeta \
  --omega-band 0.10,0.30 --zeta-band 0.005,0.030 \
  --null-controls uniform-scatter,no-clustering

# 3. Cross-domain: compare to power-system PMU modal estimates
python scripts/compare_powersys_pmu.py

# 4. Expected verdicts
#   PASS:  building (ω₀, ζ) cluster in bands AND cross-domain (power-system) modes
#          show same Q = 1/(2ζ) distribution (universality)
#   FAIL:  no clustering OR Q distributions disjoint between domains
#   INCONCLUSIVE: building cluster present but power-sys data too restricted to compare
```

## Estimated workload

- Data acquisition: 4 h (Tamura DB is scrape-friendly; PMU is restricted)
- Pipeline run: 3 h (joint-distribution clustering + bootstrap)
- Verdict + writeup: 3 h
- **Total: ~10 h / 1.5 days**

## Risks specific to this class

1. **Amplitude-dependent damping** (Tamura 1996): ζ varies with vibration amplitude. Restrict to small-amplitude regime for fair cross-building comparison.
2. **Power-system data access**: PMU data is mostly restricted. May need to fall back to published modal-analysis summary tables (much smaller N).
3. **Template-vs-mechanism boundary**: pre-register interpretation — clustering supports mechanism, scatter supports template/REJECT.

## Priority

⭐⭐⭐ (rationale: B3 KEEP but textbook-template risk; modest data hunting; cross-domain test is the real value)

## Dependencies

- `pandas`, `scipy.signal`, `numpy`, `requests`, `beautifulsoup4`
- No paid API for primary
- Storage: < 1 GB
