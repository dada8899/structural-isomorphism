# reaction_diffusion_steady_state_class

**Name (zh)**: 稳态反应-扩散梯度场类
**Name (en)**: Steady-State Reaction-Diffusion Gradient Field
**Pre-registered exponent band**: Characteristic length λ = √(D/k) ∈ [1.5, 8.0] km for urban-heat-island; logarithmic-radial profile R² > 0.70; D inferred from gradient consistent with independent meteorological D within factor of 2. Rationale: Fick 1855, Wolpert 1969 French-flag morphogen, Oke 1973 urban-heat-island review.
**Verified status**: false (target: v0.4). B3 consensus = KEEP (one of the 5 KEEPs — high prior).

## Why this class needs an empirical anchor

The KEEP signal from B3 says the class is mechanistically distinctive. Urban-heat-island data is the cleanest empirical anchor because (i) the gradient is directly measurable from satellite TIR, (ii) D (turbulent diffusion) is independently estimated from meteorology, and (iii) the steady-state assumption holds on summer-nighttime time windows.

KB linkage: 3 members — urban heat-island spatial gradient (env science), groundwater drawdown cone from foundation-pit dewatering (civil eng), maternal-effect-gene egg-axis polarization (dev bio).

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | NASA Landsat 8/9 Collection 2 thermal-infrared (Shanghai + Beijing + Guangzhou, summer nights 2015–2025) | https://www.usgs.gov/landsat-missions/landsat-collection-2-data | Public domain | ~120 scenes × 3 cities | Original pre-registered target; spatial resolution 100 m enough to resolve λ | Cloud cover; surface-emissivity correction needed |
| 2 [fallback] | ERA5-Land reanalysis 2 m temperature 1980–2025 (0.1° resolution global) | https://cds.climate.copernicus.eu/cdsapp#!/dataset/reanalysis-era5-land | Free, registration | Hourly × 0.1° | Cross-check λ on multiple cities; independent D from ERA5 wind/turbulence | Coarse resolution may underresolve λ < 2 km |
| 3 [stretch] | Wolpert-style morphogen gradient measurements in Drosophila embryos (FlyBase + Houchmandzadeh–Wieschaus–Leibler 2002 Nature 415:798 replication) | https://flybase.org/ | CC-BY 4.0 | ~50 embryos | Tests dev-bio variant on canonical Bicoid gradient | Different scale entirely — biological membrane-bounded |

## Validation procedure (concrete)

```bash
mkdir -p data/reaction_diffusion_steady_state_class

# 1. Landsat TIR via USGS Earth Explorer / Google Earth Engine
python scripts/fetch_landsat_tir.py \
  --cities Shanghai,Beijing,Guangzhou --season summer --years 2015-2025 \
  --out data/reaction_diffusion_steady_state_class/landsat_tir.tif

# 2. Fit radial profile to log decay
python -m v4.cli validate reaction_diffusion_steady_state_class \
  --data data/reaction_diffusion_steady_state_class/landsat_tir.tif \
  --method radial-profile-log --centre-detection automated \
  --lambda-band 1.5,8.0 --null-controls linear-decay,exponential-decay,no-gradient

# 3. Cross-check D from ERA5-Land turbulent-flux outputs
python scripts/check_diffusion_consistency.py

# 4. Expected verdicts
#   PASS:  log decay R² > 0.70 across cities, λ in band, D back-inferred matches ERA5 within 2x
#   FAIL:  exponential decay preferred (1D point source not 2D), OR D mismatch > 5x
#   INCONCLUSIVE: gradient present but profile shape ambiguous
```

## Estimated workload

- Data acquisition: 5 h (Landsat via GEE is efficient; ERA5-Land via CDS slower)
- Pipeline run: 4 h (per-scene radial profiling + cross-scene aggregation)
- Verdict + writeup: 3 h
- **Total: ~12 h / 1.5 days**

## Risks specific to this class

1. **Centre-detection bias**: cities have multiple thermal hotspots; pre-register heuristic (population-weighted centroid).
2. **Steady-state assumption** valid only on calm summer nights; filter for wind speed < 3 m/s.
3. **2D vs 3D solution**: vertical structure matters; pre-register that we are testing the 2D radial solution u(r) ∝ −ln(r).

## Priority

⭐⭐⭐⭐ (rationale: B3 KEEP; clean satellite data; closed-form prediction; cross-domain via Drosophila stretch)

## Dependencies

- `rasterio`, `numpy`, `scipy.optimize`
- Optional: Google Earth Engine Python API
- ERA5 registration required
- Storage: ~50 GB (Landsat scenes are large)
