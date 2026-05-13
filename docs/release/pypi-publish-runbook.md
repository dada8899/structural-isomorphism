# PyPI Publish Runbook — soc-pipeline + guarded-llm

This runbook walks you (user) through publishing two packages from this repo to PyPI in 1 click.

## What gets published

| Package | Version | Wheel | sdist |
|---|---|---|---|
| `soc-pipeline` | 0.1.0 | `soc_pipeline-0.1.0-py3-none-any.whl` | `soc_pipeline-0.1.0.tar.gz` |
| `guarded-llm` | 0.1.0 | `guarded_llm-0.1.0-py3-none-any.whl` | `guarded_llm-0.1.0.tar.gz` |

The release F3 agent already built + `twine check`'d both packages locally (sizes: soc-pipeline 20 KB wheel + 18 KB sdist; guarded-llm 23 KB wheel + 24 KB sdist; all PASSED twine check + fresh-venv import test).

**Note**: `dist/` is gitignored, so wheels are NOT in git. `publish_pypi.sh` auto-rebuilds via `python -m build` if `dist/` is empty. No manual prep needed.

## Prerequisites (one-time)

1. **PyPI account**: register at https://pypi.org if you don't have one. Enable 2FA (required since 2024).
2. **TestPyPI account** (optional but recommended for dry-run): https://test.pypi.org.
3. **Reserve project names**: PyPI auto-claims `soc-pipeline` + `guarded-llm` on first upload. Names are case-insensitive and "-" / "_" / "." are normalized — so `soc-pipeline` and `soc_pipeline` collide. If either name is already taken, you'll need to rename in `pyproject.toml` (e.g. `soc-pipeline` → `socpipeline` or `dada-soc-pipeline`) and rebuild before publishing.
4. **Create API tokens**:
   - PyPI: https://pypi.org/manage/account/token/ → "Add API token" → scope = "Entire account" for first publish (after first upload, scope down to per-project).
   - TestPyPI: https://test.pypi.org/manage/account/token/ — same flow.
5. **Save tokens locally** (never commit). Example `.envrc` or `~/.config/secrets/pypi.env`:
   ```bash
   export PYPI_TOKEN="pypi-AgEIcHlwaS5vcmcCJ..."
   export TESTPYPI_TOKEN="pypi-AgENdGVzdC5weXBpLm9yZ..."
   ```

## Step 1 — TestPyPI dry-run (recommended)

```bash
cd ~/Projects/structural-isomorphism
source ~/.config/secrets/pypi.env   # loads TESTPYPI_TOKEN + PYPI_TOKEN
bash scripts/release/publish_pypi.sh --test
```

What this does:
- Verifies wheels exist (rebuilds if missing)
- Runs `twine check`
- Uploads to https://test.pypi.org

Verify install:
```bash
python3 -m venv /tmp/pypi_test && source /tmp/pypi_test/bin/activate
pip install -i https://test.pypi.org/simple/ soc-pipeline guarded-llm
python -c "from soc_pipeline import fit_clauset_powerlaw; print('soc OK')"
python -c "from guarded_llm import guardrailed_llm_call; print('guarded OK')"
deactivate && rm -rf /tmp/pypi_test
```

## Step 2 — Production PyPI

```bash
cd ~/Projects/structural-isomorphism
source ~/.config/secrets/pypi.env
bash scripts/release/publish_pypi.sh
```

After ~30 seconds, verify:
- https://pypi.org/project/soc-pipeline/
- https://pypi.org/project/guarded-llm/

End-user install command (announce in README + Twitter / arXiv abstract):
```bash
pip install soc-pipeline guarded-llm
```

## Step 3 — Version bump for next release

When you ship v0.2.0 (next milestone):

1. Edit `packages/soc-pipeline/pyproject.toml` → `version = "0.2.0"`
2. Edit `packages/guarded-llm/pyproject.toml` → same
3. Update `CHANGELOG.md` (create if missing) in each package
4. Rebuild + republish:
   ```bash
   rm -rf packages/*/dist packages/*/build
   bash scripts/release/publish_pypi.sh
   ```

PyPI rejects re-uploads of the same version — you must bump. SemVer:
- `0.1.0` → `0.1.1` for bugfixes
- `0.1.0` → `0.2.0` for new APIs (backward-compat)
- `0.1.0` → `1.0.0` for breaking changes (also drop "Beta" classifier)

## Step 4 — Post-publish announce

- [ ] Tweet / Mastodon / 飞书：`pip install soc-pipeline` is now live
- [ ] arXiv paper §availability — add PyPI links
- [ ] GitHub README badges — already configured (see `packages/{name}/README.md`)
- [ ] Zenodo DOI metadata — add `related_identifiers` entries pointing to PyPI

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `403 Forbidden: The user 'xxx' isn't allowed` | token scope wrong | regenerate token, scope = "Entire account" |
| `400 File already exists` | version already published | bump version in pyproject.toml + rebuild |
| `400 The name 'soc-pipeline' isn't allowed` | name reserved / similar to existing | rename in pyproject.toml |
| `InvalidDistribution` | wheel corrupt | `rm -rf dist/ build/ && python -m build` |

Token rotation: PyPI tokens can be revoked at https://pypi.org/manage/account/token/ — rotate after every publish for paranoia mode.
