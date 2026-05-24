# Quickstart

Three lines to install. One screen to verify it works.

## Install

```bash
pip install soc-pipeline                  # core (numpy + scipy + pandas + powerlaw)
pip install 'soc-pipeline[vis]'           # + matplotlib
pip install 'soc-pipeline[notebooks]'     # + jupyter + nbconvert + matplotlib
pip install 'soc-pipeline[dev]'           # + pytest + ruff + mypy + build
```

Requires Python >= 3.10. Pure-Python; no compiled extensions.

## Minimal example

```python
import numpy as np
from soc_pipeline import (
    fit_clauset_powerlaw,
    bootstrap_ci,
    synthetic_null,
    verdict_from_alpha_band,
)

# Your data: any 1-D positive array of event sizes
event_sizes = np.loadtxt("events.txt")

# 1. Fit power-law tail (Clauset-Shalizi-Newman 2009)
fit = fit_clauset_powerlaw(event_sizes, discrete=False)
print(f"alpha = {fit.alpha:.2f}  xmin = {fit.xmin:.2g}  n_tail = {fit.n_tail}")

# 2. Bootstrap confidence interval
ci = bootstrap_ci(event_sizes, n_boot=200)
print(f"alpha CI = [{ci.ci_low:.2f}, {ci.ci_high:.2f}]")

# 3. Null controls — healthy pipelines reject all three
for name, case in synthetic_null().items():
    assert case.correctly_rejected, f"null {name!r} not rejected — pipeline broken"

# 4. Verdict against predicted band
v = verdict_from_alpha_band(fit.alpha, predicted=(1.5, 2.0), literature=(1.3, 2.3))
print(v)   # 'CONFIRMED' | 'CONFIRMED (literature band)' | 'DEVIATING'
```

## Earthquake b-value (Gutenberg-Richter)

```python
from soc_pipeline import fit_b_value
bv = fit_b_value(magnitudes, bootstrap=True)
print(f"b = {bv.b:.3f}  Mc = {bv.mc}  alpha_eq = {bv.alpha_equivalent:.3f}")
```

## Omori-Utsu aftershock decay

```python
from soc_pipeline import fit_omori_p, bin_and_omori_from_events

# Stack mode: pass aftershock delays in seconds
om = fit_omori_p(aftershock_delays_sec)
print(f"p = {om.p:.3f}  R^2 = {om.R2:.3f}")

# Stream mode: auto-detect main shocks
om2 = bin_and_omori_from_events(event_times_sec, bin_seconds=60.0)
```

## Where to next

- [API reference](./api-reference.md) — full public surface.
- [Notebooks](../notebooks/) — 5 reproducible headline results.
- [CHANGELOG](../CHANGELOG.md) — per-release notes.
