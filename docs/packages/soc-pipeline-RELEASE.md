# soc-pipeline 0.1.0 — Release notes & PyPI upload runbook

> Status: **prepared**, **not uploaded**. This document captures the build
> artifacts produced by w8-a and the commands the maintainer must run by hand
> to publish to PyPI.

## Package summary

| Field | Value |
|---|---|
| Name | `soc-pipeline` |
| Version | `0.1.0` |
| License | MIT |
| Python | `>=3.10` |
| Runtime deps | `numpy>=1.24`, `scipy>=1.10`, `powerlaw>=1.5` (+ `pandas>=2.0` for catalogue helpers) |
| Extras | `[vis]` matplotlib · `[notebooks]` jupyter+matplotlib+nbconvert · `[dev]` pytest+ruff+mypy+build |
| Public API | `validate`, `Verdict`, `fit_clauset_powerlaw`, `bootstrap_ci`, `synthetic_null`, `vuong_lr_test`, `shape_normalized_collapse`, `fit_omori_p`, `fit_b_value`, `time_resolution_sweep`, `empirical_ccdf`, `verdict_from_alpha_band` |

The unified one-call entry point is `soc_pipeline.validate(data, label, expected_band=None) -> Verdict`.

## Build artifacts

Built via `python -m build` (Hatchling). Both wheel and sdist live in
`packages/soc-pipeline/dist/` (gitignored, regenerate per release):

```
dist/
  soc_pipeline-0.1.0-py3-none-any.whl
  soc_pipeline-0.1.0.tar.gz
```

The wheel was smoke-tested in a fresh `python -m venv` — install + `import soc_pipeline` + `validate(Pareto(α=2.5), expected_band=(2.3, 2.7))` returns `PASS`.

## How to re-build (any maintainer)

```bash
cd packages/soc-pipeline
rm -rf dist build *.egg-info
python -m pip install --upgrade build twine
python -m build      # writes dist/soc_pipeline-0.1.0-*.whl + .tar.gz
python -m twine check dist/*
```

## How to upload (left for maintainer with PyPI token)

1. Configure a PyPI API token (once):

   ```bash
   # ~/.pypirc
   [pypi]
     username = __token__
     password = pypi-AgEIc...   # paste the token from https://pypi.org/manage/account/token/
   ```

   or export `TWINE_USERNAME=__token__` + `TWINE_PASSWORD=<token>`.

2. Dry-run on TestPyPI first:

   ```bash
   twine upload --repository testpypi dist/soc_pipeline-0.1.0-*.whl dist/soc_pipeline-0.1.0.tar.gz
   pip install --index-url https://test.pypi.org/simple/ soc-pipeline==0.1.0
   python -c "import soc_pipeline; print(soc_pipeline.__version__)"
   ```

3. Real upload:

   ```bash
   twine upload dist/soc_pipeline-0.1.0-*.whl dist/soc_pipeline-0.1.0.tar.gz
   ```

4. Verify:

   ```bash
   pip install --upgrade soc-pipeline
   python -c "from soc_pipeline import validate, __version__; print(__version__)"
   ```

## Post-release checklist

- [ ] Tag the release: `git tag v0.1.0-soc-pipeline && git push origin v0.1.0-soc-pipeline`
- [ ] Open a GitHub release pointing at the tag, link to the wheel & sdist
- [ ] Update `README.md` in `packages/soc-pipeline/` if any installation instructions changed
- [ ] Note the release in the project root changelog
- [ ] Run a clean-venv install smoke test from the published wheel: `pip install soc-pipeline==0.1.0 && python -c "from soc_pipeline import validate"`

## Backwards compatibility

`v4/lib/soc_pipeline.py` remains as a thin deprecation shim — it re-exports
the new package API and emits a `DeprecationWarning`. Removal is scheduled
for `soc-pipeline >= 1.0.0`.
