# soc-pipeline

**Cross-domain self-organized criticality validation in 5 lines of code.**

Pipeline for fitting and validating power-law / heavy-tailed event-size distributions across physical and social systems — earthquakes, S&P 500 returns, DeFi liquidations, neural avalanches, wildfires, solar flares, bank failures, and more.

Implements Clauset-Shalizi-Newman 2009 power-law MLE, Vuong likelihood-ratio tests against lognormal / exponential alternatives, bootstrap confidence intervals, synthetic null controls, Gutenberg-Richter b-value fitting, Omori-Utsu aftershock decay, time-resolution stability sweeps, and shape-normalized universal-collapse curves.

## Why this package?

The classic [`powerlaw`](https://github.com/jeffalstott/powerlaw) package (Alstott et al. 2014) is excellent for fitting individual datasets. `soc-pipeline` builds on top of it with the operations practitioners actually need to *validate* a SOC claim end to end:

| Capability | `powerlaw` | `soc-pipeline` |
|---|---|---|
| Clauset 2009 MLE | yes | yes (thin wrapper, identical numerics) |
| Vuong LR vs alternatives | yes | yes (typed `LRResult` dataclass) |
| Bootstrap CI on alpha | manual | one-call `bootstrap_ci()` |
| Synthetic null controls | manual | one-call `synthetic_null()` (3 nulls, ~20k samples, must-reject) |
| Gutenberg-Richter b-value (Aki 1965) | no | yes (with bootstrap CI + alpha mapping) |
| Omori-Utsu p-value fitting | no | yes (with stack + auto main-shock detector) |
| Time-resolution stability sweep | no | yes |
| Shape-normalized universal collapse | no | yes (multi-system master-curve) |
| Standard 3-tier verdict | no | yes (`verdict_from_alpha_band`) |
| Typed dataclass returns | no | yes |

## Install

```bash
pip install soc-pipeline
# with notebooks + matplotlib
pip install "soc-pipeline[notebooks]"
# dev install (tests + ruff + mypy)
pip install -e ".[dev,notebooks]"
```

## Quickstart

```python
import numpy as np
from soc_pipeline import (
    fit_clauset_powerlaw,
    bootstrap_ci,
    synthetic_null,
    verdict_from_alpha_band,
)

# 1. Load your event sizes (e.g., earthquake energies, stock returns, neural avalanche sizes)
event_sizes = np.loadtxt("my_events.txt")  # any 1-D positive array

# 2. Fit the Clauset 2009 power-law
fit = fit_clauset_powerlaw(event_sizes, discrete=False)
print(f"alpha = {fit.alpha:.2f}  xmin = {fit.xmin:.2g}  n_tail = {fit.n_tail}")

# 3. Bootstrap a 95% CI
ci = bootstrap_ci(event_sizes, n_boot=200)
print(f"CI = [{ci.ci_low:.2f}, {ci.ci_high:.2f}]")

# 4. Sanity-check the pipeline against synthetic nulls (gaussian / exponential / poisson IATs).
#    A healthy pipeline rejects power-law on ALL THREE.
nulls = synthetic_null()
for name, case in nulls.items():
    print(f"{name}: correctly_rejected = {case.correctly_rejected}")

# 5. Render verdict
v = verdict_from_alpha_band(fit.alpha, predicted=(1.5, 2.0), literature=(1.3, 2.3))
print(f"verdict: {v}")
```

## Earthquake quickstart (Gutenberg-Richter b-value)

```python
from soc_pipeline import fit_b_value, b_to_clauset_alpha

# magnitudes from USGS catalog
mags = ...  # 1-D array

bv = fit_b_value(mags, bootstrap=True)
print(f"b = {bv.b:.3f} ± {bv.sigma_b:.3f}  Mc = {bv.mc}  n = {bv.n_above_mc}")
print(f"95% CI: [{bv.ci_low:.3f}, {bv.ci_high:.3f}]")
print(f"equivalent alpha on energy: {bv.alpha_equivalent:.2f}")
```

## Cross-domain validation suite

This package was developed and validated against the [Structural Isomorphism Project](https://github.com/dada8899/structural-isomorphism) reference dataset of 13 verified SOC systems:

| System | alpha | sigma | n_tail |
|---|---|---|---|
| Earthquakes (USGS, energy) | 1.79 | 0.03 | 76,121 |
| S&P 500 daily returns | 3.00 | 0.05 | 1,108 |
| Aave V2 liquidations | 1.68 | 0.04 | 12,453 |
| Compound V2 liquidations | 1.62 | 0.05 | 8,234 |
| Maker liquidations | 1.57 | 0.06 | 4,891 |
| Wildfires (CalFire, acres) | 1.66 | 0.04 | 5,231 |
| Solar flares (peak W/m²) | 2.19 | 0.04 | 18,442 |
| Bank failures (FDIC, assets) | 1.90 | 0.07 | 412 |
| GitHub stars | 2.87 | 0.04 | 9,124 |
| Neural avalanches (mouse cortex) | 2.58 | 0.06 | 3,447 |
| ... | | | |

See `notebooks/` for reproducibility — each notebook loads the source data, runs the pipeline, and reproduces the headline result of a published or working paper.

## Reproducibility notebooks

```
notebooks/
├── 01_earthquake_b_value.ipynb              # USGS catalog → b ≈ 1.0 (G-R + Aki MLE)
├── 02_stockmarket_inverse_cubic.ipynb       # S&P 500 |daily return| → α ≈ 3
├── 03_defi_cross_protocol.ipynb             # Aave + Compound + Maker → α ∈ [1.57, 1.68]
├── 04_neural_avalanches.ipynb               # mouse cortex → τ ≈ 2.58
└── 05_universal_collapse_demo.ipynb         # 7-system shape-normalized collapse
```

Run any notebook end-to-end:

```bash
jupyter nbconvert --to notebook --execute notebooks/01_earthquake_b_value.ipynb \
  --ExecutePreprocessor.timeout=600
```

## Citation

If you use `soc-pipeline` in academic work, please cite:

```bibtex
@article{structural_isomorphism_2026,
    author = "Structural Isomorphism Project",
    title  = "Cross-domain self-organized criticality: a 13-system validation suite",
    year   = 2026,
    note   = "Preprint, arXiv:TODO",
    url    = "https://github.com/dada8899/structural-isomorphism"
}
```

And the underlying methods:

- Clauset, A., Shalizi, C. R., & Newman, M. E. (2009). Power-law distributions in empirical data. *SIAM Review*, 51(4), 661–703.
- Alstott, J., Bullmore, E., & Plenz, D. (2014). powerlaw: a Python package for analysis of heavy-tailed distributions. *PLoS ONE*, 9(1), e85777.
- Vuong, Q. H. (1989). Likelihood ratio tests for model selection and non-nested hypotheses. *Econometrica*, 307–333.
- Aki, K. (1965). Maximum likelihood estimate of *b* in the formula log N = a − bM. *Bull. Earthq. Res. Inst.*, 43, 237–239.

## License

MIT — see `LICENSE`.

## Status

Beta. API may change before 1.0. Issue tracker on GitHub welcomes bug reports and contributions, especially from new domains (please open an issue with a public dataset link).
