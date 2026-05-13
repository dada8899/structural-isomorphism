# Getting Started

## Install

```bash
pip install soc-pipeline                # core
pip install "soc-pipeline[notebooks]"   # + jupyter + matplotlib
pip install "soc-pipeline[dev]"         # + tests + ruff + mypy
```

Requires Python >= 3.10. Pure-Python; no compiled extensions.

## 5-minute quickstart

```python
import numpy as np
from soc_pipeline import (
    fit_clauset_powerlaw, bootstrap_ci, synthetic_null, verdict_from_alpha_band,
)

# Your data: any 1-D positive array of event sizes
event_sizes = np.loadtxt("events.txt")

# 1. Fit
fit = fit_clauset_powerlaw(event_sizes, discrete=False)
print(f"alpha = {fit.alpha:.2f}  xmin = {fit.xmin:.2g}  n_tail = {fit.n_tail}")

# 2. Bootstrap CI
ci = bootstrap_ci(event_sizes, n_boot=200)
print(f"CI = [{ci.ci_low:.2f}, {ci.ci_high:.2f}]")

# 3. Null check (pipeline must REJECT power-law on synthetic non-heavy-tail)
nulls = synthetic_null()
for name, case in nulls.items():
    assert case.correctly_rejected, f"{name} not rejected — pipeline broken"

# 4. Verdict
v = verdict_from_alpha_band(fit.alpha, predicted=(1.5, 2.0), literature=(1.3, 2.3))
print(v)  # 'CONFIRMED' | 'CONFIRMED (literature band)' | 'DEVIATING'
```

## Earthquake b-value

```python
from soc_pipeline import fit_b_value
mags = np.array([...])  # magnitudes from any earthquake catalog
bv = fit_b_value(mags, bootstrap=True)
print(f"b = {bv.b:.3f}  Mc = {bv.mc}  alpha_eq = {bv.alpha_equivalent:.3f}")
```

## Omori aftershock decay

```python
from soc_pipeline import fit_omori_p, bin_and_omori_from_events
# Stack mode: pass aftershock delays in seconds
om = fit_omori_p(aftershock_delays_sec)
print(f"p = {om.p:.3f}  R^2 = {om.R2:.3f}")

# Stream mode: auto-detect main shocks
om2 = bin_and_omori_from_events(event_times_sec, bin_seconds=60.0)
```

## Reproducibility

5 notebooks in `notebooks/` each reproduce a published headline:

```bash
jupyter nbconvert --to notebook --execute notebooks/01_earthquake_b_value.ipynb \
  --ExecutePreprocessor.timeout=600
```

## Troubleshooting

- **"too few values"** — sample below `min_samples` (default 100). Get more data or pass `min_samples=N` with N appropriate to your domain.
- **"No valid fits found for distribution lognormal"** (powerlaw warning) — common with very small `xmin`; the LR test fields will be None. Increase data or check for zero/negative values.
- **Bootstrap CI is wide** — typical for n_tail < 500. Increase n_boot or aggregate more data.

## Citing

See `README.md`.
