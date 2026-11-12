# guarded-llm release runbook

Steps to publish `packages/guarded-llm/` to PyPI. Run from the repo root.

## 0. Prerequisites

- A PyPI account with maintainer access to the `guarded-llm` project.
- A PyPI API token stored in `~/.pypirc` or in the env as
  `TWINE_USERNAME=__token__` and `TWINE_PASSWORD=<your-pypi-token>`.
- The repo on `main` with no uncommitted changes.
- `python -m build`, `twine`, and `pytest` installed (all included in
  `guarded-llm[dev]`).

## 1. Bump the version

Edit `packages/guarded-llm/pyproject.toml`:

```toml
[project]
version = "0.1.1"     # or 0.2.0, or 1.0.0, …
```

And `packages/guarded-llm/src/guarded_llm/__init__.py`:

```python
__version__ = "0.1.1"
```

Keep these two strings in sync — there's a smoke test that verifies
`__version__` matches the wheel filename.

## 2. Run the full test suite

```bash
cd packages/guarded-llm
python -m pytest tests/ -v
```

All tests must pass. If anything's flaky, fix the flake before releasing
(don't ship a release that depends on retries to look green).

## 3. Build the artifacts

```bash
cd packages/guarded-llm
rm -rf dist/ build/ *.egg-info
python -m build
ls dist/
# Expected:
#   guarded_llm-0.1.1-py3-none-any.whl
#   guarded_llm-0.1.1.tar.gz
```

## 4. Sanity-check the wheel in a clean venv

```bash
python3 -m venv /tmp/test-guarded-llm
/tmp/test-guarded-llm/bin/pip install dist/*.whl
/tmp/test-guarded-llm/bin/python -c "
from guarded_llm import GuardedLLM, Budget, RetryPolicy, SchemaValidator
print('import OK')
print('version:', __import__('guarded_llm').__version__)
"
```

## 5. Upload to TestPyPI first

```bash
twine upload --repository testpypi dist/*
```

Verify on https://test.pypi.org/project/guarded-llm/, then:

```bash
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple guarded-llm==0.1.1
```

## 6. Upload to PyPI proper

```bash
twine upload dist/*
```

Verify on https://pypi.org/project/guarded-llm/.

## 7. Tag the release

```bash
git tag -a guarded-llm-v0.1.1 -m "guarded-llm 0.1.1"
git push origin guarded-llm-v0.1.1
```

## 8. GitHub release

```bash
gh release create guarded-llm-v0.1.1 \
    --title "guarded-llm 0.1.1" \
    --notes-file packages/guarded-llm/CHANGELOG.md \
    packages/guarded-llm/dist/*
```

## Rollback

If a release is broken on PyPI, you can't unpublish (only yank). Yank with:

```bash
# via the PyPI web UI: Manage → Releases → 0.1.1 → Yank
```

Then immediately ship `0.1.2` with the fix.

## Notes

- We do NOT auto-publish from CI for `guarded-llm`. The release is manual to
  prevent accidental publishes from a misclicked workflow.
- The `[anthropic]`, `[deepseek]`, `[kimi]`, `[glm]`, `[openai]` extras are
  ALL optional — the package functions without any vendor SDK installed
  (built-in adapters use plain `requests`).
