# Reproduction tutorials

> From-scratch reproductions of the structural-isomorphism Phase 1 results.
> Default 1-year window runs in ~5 seconds (CLI script) / ~3 minutes (notebook with explanations).
> The full 5-year headline window takes ~5 minutes (script) / ~30 minutes (notebook).
> No GPU, no credentials, no private data. Just `pip install` and a USGS REST call.

## What's here

| File | What it does | ETA |
|---|---|---|
| `01_reproduce_earthquake_soc.ipynb` | Jupyter notebook: USGS pull → $M_c$ → Aki $b$ → bootstrap CI → Clauset 2009 fit on energy → Vuong LR tests → log-log plot → verdict | ~3 min (1-yr default end-to-end with explanatory cells); ~30 min for the 5-yr headline reproduction |
| `01_phase_1_quick.py` | Same pipeline as a one-command CLI script for users who don't want Jupyter | **~5 seconds** (1-yr default; W5-D dogfood measured 5.2 s on a 2024 MacBook Air); ~5 min for 5-yr window |

The notebook is for understanding (each step explained, intermediate plots). The script is for batch runs (CI, dogfooding, "just give me the number").

## Prerequisites

- Python **3.11+**
- ~200 MB free disk (USGS pull + matplotlib cache)
- Network access to `earthquake.usgs.gov`

The notebook installs everything from a single cell. The CLI script needs the same six packages installed up front. Explicit one-liner — copy-paste this exact line, in this order, so you get the right versions:

```bash
pip install numpy scipy pandas matplotlib powerlaw requests jupyter
```

(Notebook users need `jupyter`; CLI-only users can drop it.)

You can also install the repo with the `[tutorials]` extra, which pulls the same set:

```bash
pip install -e ".[tutorials]"   # from the repo root
```

## Run the notebook

```bash
git clone https://github.com/dada8899/structural-isomorphism
cd structural-isomorphism/tutorials
jupyter notebook 01_reproduce_earthquake_soc.ipynb
# or
jupyter lab 01_reproduce_earthquake_soc.ipynb
```

Then **Run All Cells**. The slow steps are the USGS pull (~10-30 s for a 1-year window) and the Clauset `powerlaw.Fit` (~20-60 s on 10k tail events).

## Run the script

```bash
python 01_phase_1_quick.py                                            # 1-year window, fastest
python 01_phase_1_quick.py --start 2020-01-01 --end 2025-01-01        # full 5-year, ~37k tail events
```

The 1-year default is enough to clear the verdict. Use the 5-year window if you want to match the published headline numbers exactly.

## Acceptance criterion

You have successfully reproduced Phase 1 if you see:

- $b \in [0.95, 1.15]$ (the canonical Gutenberg-Richter band)
- Bootstrap 95% CI on $b$ has width < 0.05
- Clauset fit's likelihood-ratio test rejects exponential ($p_\text{exp} < 0.1$, $R > 0$)

The 5-year run should land within ~1% of the paper's headline: $b = 1.084$, CI $[1.073, 1.094]$, $\alpha \approx 1.79$, $n_\text{tail} = 37281$.

## Troubleshooting

### `pip install powerlaw` fails

`powerlaw` depends on `mpmath` and pulls a Fortran-compiled `scipy` on some platforms. If the install errors out:

```bash
pip install --upgrade pip setuptools wheel
pip install scipy mpmath
pip install powerlaw
```

On Apple Silicon you may need `pip install --no-cache-dir powerlaw`.

### USGS API rate-limit / 503 / timeout

USGS rate-limits queries that return more than ~20 000 events in a single window. The notebook's default 1-year M>=3.5 window stays well under that. If you hit a 503:

- Wait a minute, then re-run.
- Cut the window in half (`endtime=2020-07-01`).
- Raise `minmagnitude` (e.g. to 3.5) — this is what the published Phase 1 fetcher does for the 5-year window.

The 5-year, M>=3.5 window will _not_ fit in one call and will return only the first 20 000 events; use the [batched fetcher in the main repo](../v4/validation/soc-earthquake/fetch_earthquakes.py) for that case.

### "Mc looks too low" or "b looks too high"

A common gotcha is including induced seismicity (fracking, reservoirs) or quarry blasts. Both inflate $b$. The notebook already filters on `type == "earthquake"`. If your number is off:

- Check `df.type.value_counts()` — anything other than `earthquake` is non-tectonic.
- Try restricting to a tectonic region (`latitude`, `longitude` bounds on the geojson features).
- Use a stricter $M_c$ (Wiemer-Wyss 2000 max-curvature is the standard; some authors prefer Mc+0.2 conservative offset).

### Bootstrap CI is suspiciously wide

You probably have fewer than ~500 tail events. Pull a longer window. The CI shrinks as $\sqrt{n}$, so 5 yr cuts the width to ~$1/\sqrt{5} \approx 45\%$ of the 1 yr width.

## Planned future tutorials

| File | Phase | Domain |
|---|---|---|
| `02_reproduce_defi_soc.ipynb` | Phase 1 | Aave / Compound liquidation cascades |
| `03_reproduce_universal_collapse.ipynb` | Phase 2 | Cross-domain scaling collapse (earthquake + DeFi + bank failures on one plot) |
| `04_reproduce_hawkes_aftershocks.ipynb` | Phase 3 | Hawkes process fit on USGS aftershock sequences (Omori law) |

Until those land, the script `v4/validation/soc-earthquake/gutenberg_richter.py` in the main repo runs the canonical pipeline, and `paper/` has the writeups for all phases.

## Citing

If you use this tutorial in published work, please cite the repository (see top-level `CITATION.cff`) and the original method papers: Aki 1965, Bak-Tang-Wiesenfeld 1987, Wiemer-Wyss 2000, Clauset-Shalizi-Newman 2009.
