# cross-judge 0.1.0 — PyPI Release Runbook

## Pre-flight

```bash
cd packages/cross-judge

# 1. Verify tests pass
../../.venv/bin/python -m pytest tests/ -v
# expected: 82 passed (37 legacy + 45 new)

# 2. Verify version + metadata
grep -E '^version|^name|^description' pyproject.toml

# 3. Clean stale artifacts
rm -rf dist/ build/ src/*.egg-info

# 4. Build sdist + wheel
../../.venv/bin/pip install build --quiet
../../.venv/bin/python -m build
ls dist/
# expected:
#   cross_judge-0.1.0-py3-none-any.whl
#   cross_judge-0.1.0.tar.gz
```

## Clean-venv smoke test (mandatory before upload)

```bash
python3 -m venv /tmp/cj-smoke
/tmp/cj-smoke/bin/pip install dist/*.whl pydantic httpx pyyaml --quiet
/tmp/cj-smoke/bin/python -c "
from cross_judge import Critic, Ensemble, Verdict, VerdictKind, EnsembleVerdict
from cross_judge.voting import krippendorff_alpha, majority_vote, unanimous
print('cross-judge', __import__('cross_judge').__version__)
print('public API OK')
"
rm -rf /tmp/cj-smoke
```

## TestPyPI upload (dry-run)

```bash
# 1. Register account at https://test.pypi.org/
# 2. Generate API token, save to ~/.pypirc:
#    [testpypi]
#    username = __token__
#    password = pypi-AgENdGV...
#
# 3. Install twine
../../.venv/bin/pip install twine --quiet

# 4. Upload to TestPyPI
../../.venv/bin/twine upload --repository testpypi dist/*

# 5. Verify install from TestPyPI
python3 -m venv /tmp/cj-test
/tmp/cj-test/bin/pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    cross-judge==0.1.0
/tmp/cj-test/bin/python -c "from cross_judge import Critic, Ensemble; print('TestPyPI install OK')"
rm -rf /tmp/cj-test
```

## Production PyPI upload

```bash
# 1. Register at https://pypi.org/
# 2. Generate API token, add to ~/.pypirc:
#    [pypi]
#    username = __token__
#    password = pypi-AgENdGV...
#
# 3. Upload
../../.venv/bin/twine upload dist/*

# 4. Verify
pip install cross-judge==0.1.0
python -c "from cross_judge import Critic, Ensemble; print('PyPI OK')"
```

## Post-release

1. Tag the release in git:
   ```bash
   git tag -a packages/cross-judge/v0.1.0 -m "cross-judge 0.1.0 first PyPI release"
   git push origin packages/cross-judge/v0.1.0
   ```
2. Create GitHub release with notes pasted from this section's changelog.
3. Update `packages/cross-judge/README.md` install instructions to drop the
   `-e packages/cross-judge` form.
4. Bump version in `pyproject.toml` + `__init__.py` to `0.2.0.dev0` to
   prevent accidental re-release of `0.1.0`.

## Changelog (0.1.0)

- Initial PyPI-ready release.
- Public API: `Critic`, `Ensemble`, `Verdict`, `VerdictKind`,
  `EnsembleVerdict`, `majority_vote`, `unanimous`,
  `krippendorff_alpha`, `agreement_pct`.
- Standalone httpx-based client (no openai-python dependency).
  Optional convenience extra `cross-judge[openai]` for users who prefer
  injecting an openai-python client.
- Default vocabulary: `KEEP / REJECT / SPLIT / MERGE / UNCLEAR /
  ERROR / PARSE_FAIL`.
- Bundled prompts under `cross_judge/prompts/`:
  - `b3_universality_critic.yaml`
  - `generic_universality_judge.yaml`
- 82 tests passing (37 legacy + 45 new).
- Backward-compat: legacy `Reviewer` / `JudgePanel` / aggregation API
  preserved for `v4/scripts/b3_ensemble.py`.

## Known limitations

- v0.1 makes sequential LLM calls in `Ensemble.judge`. For parallel calls,
  drive `Critic.judge` externally and pass verdicts to
  `Ensemble.aggregate_verdicts(...)`. Native async + ThreadPool support
  planned for 0.2.
- Krippendorff α implementation is for nominal data only. Ordinal /
  interval coefficients planned for 0.2 if needed.
- The bundled httpx client doesn't auto-retry on 429 / 5xx. Inject your
  own httpx.Client with retry transport for production use, or use the
  `cross-judge[openai]` extra and pass an openai-python client.
