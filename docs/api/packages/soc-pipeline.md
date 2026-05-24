# soc-pipeline

Clauset-grade power-law validation for self-organized criticality (SOC) data.

```bash
pip install soc-pipeline
```

## Quick start

```python
from soc_pipeline import validate
import numpy as np

# Synthetic Pareto sample
data = np.random.pareto(1.5, 5000) + 1

verdict = validate(data, label="my_events", expected_band=(2.4, 2.6))
print(verdict.verdict, verdict.alpha, verdict.in_band)
```

## Top-level entry points

::: soc_pipeline.validate

::: soc_pipeline.Verdict

## Power-law fit

::: soc_pipeline.fit_clauset_powerlaw

::: soc_pipeline.FitResult

## Bootstrap

::: soc_pipeline.bootstrap_ci

::: soc_pipeline.BootstrapResult

## Likelihood-ratio test (Vuong)

::: soc_pipeline.vuong_lr_test

::: soc_pipeline.LRResult

## Null controls

::: soc_pipeline.synthetic_null

::: soc_pipeline.NullCase

## Universal collapse

::: soc_pipeline.shape_normalized_collapse

::: soc_pipeline.CollapseResult

## Omori-law decay

::: soc_pipeline.fit_omori_p

::: soc_pipeline.OmoriResult

::: soc_pipeline.bin_and_omori_from_events

## Gutenberg-Richter b-value

::: soc_pipeline.fit_b_value

::: soc_pipeline.b_to_clauset_alpha

## Time-resolution sweep

::: soc_pipeline.time_resolution_sweep

## Utilities

::: soc_pipeline.empirical_ccdf

::: soc_pipeline.verdict_from_alpha_band

## Pandas accessor

The package registers a `.soc` accessor on `pandas.Series`:

```python
import pandas as pd
import soc_pipeline  # registers .soc accessor as side-effect

s = pd.Series([...])
v = s.soc.validate(label="my_series", expected_band=(2.0, 3.0))
```

::: soc_pipeline.SocAccessor
