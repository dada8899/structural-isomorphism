# Getting started

This page walks through installing the pipeline and running a first
pre-registered validation locally.

## Prerequisites

- Python 3.12 or newer (3.14 is the development target).
- macOS or Linux. Windows is untested.
- About 5 GB of free disk for cached datasets.

## Install

```bash
git clone https://github.com/dada8899/structural-isomorphism.git
cd structural-isomorphism
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The shared analysis stack lives in `v4/lib/soc_pipeline.py` and has no
heavy non-PyPI dependencies. The web backend (under `web/backend/`)
additionally requires FastAPI and a small set of asynchronous client
libraries; see `web/backend/requirements.txt`.

## Run an existing validation

Each system has a folder under `v4/validation/`. To replay a fit:

```bash
.venv/bin/python v4/scripts/run_preregistered_validation.py \
    v4/preregistration/cve-vulnerabilities.yaml
```

This will

1. read the pre-registration YAML,
2. consume the cached burst-size data from
   `v4/validation/cve-vulnerabilities/burst_sizes.json`,
3. run Clauset MLE + Vuong likelihood ratios + block bootstrap CI,
4. write `fit_result.json` with the verdict.

Verdicts are PASS, INCONCLUSIVE, or FAIL according to the rules in the
YAML. The pipeline does no per-system tuning: the same code path produces
all verdicts.

## Run a fresh fit on your own data

To fit a power-law tail on an arbitrary size vector:

```python
from v4.lib.soc_pipeline import fit_clauset_powerlaw, vuong_lr

result = fit_clauset_powerlaw(sizes, discrete=True)
print(result.alpha, result.x_min, result.n_tail)

lr_ln  = vuong_lr(sizes, result, alternative="lognormal")
lr_exp = vuong_lr(sizes, result, alternative="exponential")
print(lr_ln.R, lr_ln.p, lr_exp.R, lr_exp.p)
```

See [Pipeline](pipeline.md) for the full API surface.

## Tests

```bash
PYTHONPATH=. .venv/bin/python -m pytest web/backend/tests/ -q
```

At the time of writing the web backend test suite has 30 passing tests
covering the SSE orchestrator, rate-limited API endpoints, and the
pipeline result serializer.

## Next steps

- Read the [Pipeline](pipeline.md) overview to understand the seven
  analytical operations exposed by the shared library.
- Read the [Pre-registration methodology](methodology/pre-registration.md)
  to understand how exponent bands are locked before data acquisition.
- Browse [Papers](papers.md) for the preprint set, including the unified
  thirteen-system preprint and the CVE falsification.
