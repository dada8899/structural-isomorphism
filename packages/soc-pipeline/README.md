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

## Quickstart — the one-call `validate()` API

The recommended entry point for almost all users:

```python
import numpy as np
from soc_pipeline import validate

# 1-D positive event sizes — earthquake energies, S&P returns, avalanche sizes, …
event_sizes = np.loadtxt("my_events.txt")

# Pre-registered acceptance band on the Clauset α (best practice)
verdict = validate(event_sizes, label="my_events", expected_band=(1.8, 2.2))

print(verdict.verdict)       # PASS | FAIL | INCONCLUSIVE
print(verdict.alpha)         # Clauset 2009 MLE
print(verdict.alpha_ci_lo, verdict.alpha_ci_hi)   # 95% bootstrap CI
print(verdict.in_band)       # True / False / None
print(verdict.reason)        # human-readable explanation
```

**Verdict rules** (Clauset 2009 §6 + pre-registration discipline):

| Verdict | When |
|---|---|
| `PASS` | Fit succeeds, alpha inside `expected_band` (if given), no alternative model significantly preferred |
| `FAIL` | Fit succeeds, but alpha outside band **or** an alternative (lognormal / exponential) is significantly preferred (R<0 and p<0.1) |
| `INCONCLUSIVE` | Fewer than `min_samples` (default 100), or the underlying `powerlaw` fit fails |

### Pre-registered band concept

The `expected_band` parameter is the discipline that separates exploratory
data fitting from confirmatory analysis. The recipe:

1. **Before** you look at your data, write down the (low, high) range of
   alpha you expect from theory or prior literature.
2. Run `validate(data, expected_band=(low, high))`.
3. Report the verdict exactly. PASS = confirmation; FAIL = either the theory
   needs updating or the model fits a different distribution.

This is the same discipline used in particle physics (5σ pre-registered
discovery bands) and clinical trials (pre-registered primary endpoints).

## Lower-level API (for diagnostics)

If you need the individual building blocks:

```python
from soc_pipeline import (
    fit_clauset_powerlaw,
    bootstrap_ci,
    synthetic_null,
    verdict_from_alpha_band,
)

fit = fit_clauset_powerlaw(event_sizes, discrete=False)
print(f"alpha = {fit.alpha:.2f}  xmin = {fit.xmin:.2g}  n_tail = {fit.n_tail}")

ci = bootstrap_ci(event_sizes, n_boot=200)
print(f"CI = [{ci.ci_low:.2f}, {ci.ci_high:.2f}]")

# Synthetic null controls — pipeline must reject all three
nulls = synthetic_null()
for name, case in nulls.items():
    print(f"{name}: correctly_rejected = {case.correctly_rejected}")

# Tier verdict against predicted vs literature bands
v = verdict_from_alpha_band(fit.alpha, predicted=(1.5, 2.0), literature=(1.3, 2.3))
print(f"verdict: {v}")
```

## Public API table

| Name | Kind | Purpose |
|---|---|---|
| `validate(data, label, expected_band=None) -> Verdict` | function | One-call PASS/FAIL/INCONCLUSIVE verdict |
| `Verdict` | dataclass | Result of `validate()` (alpha, CI, xmin, KS, LR p-values, band check) |
| `fit_clauset_powerlaw(x_data, discrete=False)` | function | Clauset 2009 MLE — returns `FitResult` |
| `FitResult` | dataclass | Per-fit numerics (alpha, sigma, xmin, KS, LR vs lognormal/exponential) |
| `bootstrap_ci(x_data, n_boot=200, seed=42)` | function | Resampled CI on alpha — returns `BootstrapResult` |
| `synthetic_null(n=20000, seed=42)` | function | 3 not-power-law samples for negative control |
| `vuong_lr_test(...)` | function | Standalone Vuong LR vs lognormal/exponential |
| `shape_normalized_collapse(...)` | function | Multi-system master-curve collapse |
| `fit_omori_p(...)` | function | Omori-Utsu aftershock decay |
| `fit_b_value(...)` | function | Gutenberg-Richter b-value (Aki 1965 MLE) |
| `b_to_clauset_alpha(b)` | function | Mapping b → α for energy-size GR catalogues |
| `time_resolution_sweep(...)` | function | Stability across binning |
| `empirical_ccdf(x_data)` | function | Log-spaced empirical CCDF |
| `verdict_from_alpha_band(alpha, predicted, literature)` | function | 3-tier band classification |

## Limitations

- **Finite-size sensitivity.** Below ~1000 tail samples the Clauset MLE
  starts to wander; the bootstrap CI widens accordingly. The validator
  enforces `min_samples=100` on the *raw* count and returns INCONCLUSIVE
  below that.
- **xmin sensitivity.** Clauset 2009 KS-minimisation works well for clean
  power-laws but can mis-identify xmin on bimodal or contaminated tails.
  Always plot the empirical CCDF visually before trusting the verdict.
- **LR tests are non-nested.** Vuong's likelihood-ratio test compares
  *non-nested* alternatives (power-law vs lognormal). The p-value reflects
  the strength of preference, not the absolute goodness of fit.
- **Bootstrap is i.i.d.** The default `bootstrap_ci` resamples with
  replacement assuming i.i.d. observations. For autocorrelated time series,
  use a block bootstrap (not currently shipped — open an issue).
- **`powerlaw` 1.5+ dependency.** Underlying numerics depend on
  Alstott et al. 2014. Pinned via `dependencies` in `pyproject.toml`.

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

## Tutorials & reproducibility notebooks

Beginner-friendly 10-cell walkthrough:

```
tutorials/
└── 01_quickstart.ipynb       # synthetic Gutenberg-Richter end-to-end (~10 cells)
```

Cross-domain reproducibility notebooks (each loads source data and reproduces
the headline result of a published or working paper):

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
