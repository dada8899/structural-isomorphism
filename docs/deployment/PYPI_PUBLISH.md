***REMOVED*** PyPI Publishing — `structural-isomorphism` packages

Publishing 3 PyPI packages from this monorepo, fully automated via tag-push:

| Package | Path | PyPI |
|---|---|---|
| `soc-pipeline` | `packages/soc-pipeline/` | https://pypi.org/p/soc-pipeline |
| `guarded-llm` | `packages/guarded-llm/` | https://pypi.org/p/guarded-llm |
| `cross-judge` | `packages/cross-judge/` | https://pypi.org/p/cross-judge |

Workflow file: [`.github/workflows/publish-pypi.yml`](../../.github/workflows/publish-pypi.yml)

---

***REMOVED******REMOVED*** TL;DR — first-time setup (3 steps, ~5 min)

1. **Create a PyPI API token** (account-scoped first time)
   - Log in at <https://pypi.org/manage/account/token/>
   - Click **Add API token**
   - Name: `structural-isomorphism-monorepo-bootstrap`
   - Scope: **Entire account** (we'll narrow to per-project scope in step 4)
   - Copy the token starting with `pypi-…` — shown ONCE, save it now.

2. **Add the secret to GitHub**
   - Repo → **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `PYPI_API_TOKEN`
   - Value: paste the `pypi-…` token
   - Click **Add secret**.

3. **Tag a release and push**
   ```bash
   git tag -a v0.1.0 -m "first PyPI release: soc-pipeline / guarded-llm / cross-judge"
   git push origin v0.1.0
   ```
   The workflow auto-builds + uploads all 3 packages. Watch progress under **Actions → Publish to PyPI**.

4. **(Recommended) Narrow scope after first publish**
   - Go back to <https://pypi.org/manage/account/token/>, **delete** the broad token.
   - Create 3 new tokens, each scoped to a **single project** (`soc-pipeline`, `guarded-llm`, `cross-judge`).
   - For a per-project model, switch the GH secret to a single token that has access to all 3 (PyPI allows multi-project scoping after each project exists).
   - Update `PYPI_API_TOKEN` in GitHub with the new token.

---

***REMOVED******REMOVED*** How the workflow works

**Trigger**: push of any tag matching `v*` (e.g. `v0.1.0`, `v1.2.3`, `v1.2.3-rc1`).
Manual trigger also supported via **Actions → Publish to PyPI → Run workflow** (with optional `dry_run=true` to build-only).

**Matrix**: builds each of the 3 packages independently — one failing doesn't block the others (`fail-fast: false`).

**Per-package job steps**:
1. Checkout repo.
2. Set up Python 3.11.
3. `pip install build twine`.
4. `python -m build --sdist --wheel` inside `packages/<name>/`.
5. `twine check dist/*` — validates metadata + README rendering.
6. Upload `dist/` as a GH Actions artifact (30 day retention) for audit.
7. **Publish path A** (preferred): `twine upload` using `PYPI_API_TOKEN` secret.
8. **Publish path B** (fallback): `pypa/gh-action-pypi-publish` using OIDC trusted publisher (no secret needed).
9. Job summary written to GH Actions UI.

**Auth precedence**: token (path A) runs first when the secret is present. OIDC (path B) only runs when the secret is empty. Configure either — or both for belt-and-suspenders.

---

***REMOVED******REMOVED*** Alternative: OIDC trusted publisher (no secret)

OIDC is more secure than long-lived API tokens — it issues short-lived credentials per workflow run, scoped to a specific repo + environment.

**Setup** (replaces step 1-2 of TL;DR):

1. Go to each package's PyPI settings:
   - <https://pypi.org/manage/project/soc-pipeline/settings/publishing/>
   - <https://pypi.org/manage/project/guarded-llm/settings/publishing/>
   - <https://pypi.org/manage/project/cross-judge/settings/publishing/>

2. Under **Trusted publishers → Add a new publisher**, fill in:
   - **PyPI Project Name**: `soc-pipeline` (or `guarded-llm` / `cross-judge`)
   - **Owner**: `dada8899`
   - **Repository name**: `structural-isomorphism`
   - **Workflow name**: `publish-pypi.yml`
   - **Environment name**: `pypi`

3. Repeat for all 3 packages.

4. No GH secret needed — the workflow's `id-token: write` permission lets it auth via OIDC automatically.

5. Tag-push as before.

**Note**: PyPI requires the project to already exist (with ≥1 manual upload, or a project-name reservation) before you can configure trusted publishing for it. All 3 of our names are reserved (returns 200 on PyPI lookup), so this step is unblocked.

---

***REMOVED******REMOVED*** Release checklist (per release)

Before tagging:

- [ ] Bump version in each `packages/*/pyproject.toml` (currently all at `0.1.0`)
- [ ] Update `CHANGELOG.md` with the new version section
- [ ] Run local sanity check:
  ```bash
  for p in soc-pipeline guarded-llm cross-judge; do
    (cd packages/$p && rm -rf dist/ && python -m build && twine check dist/*)
  done
  ```
- [ ] Commit + push the version bumps to `main` first
- [ ] Tag from `main`: `git tag -a vX.Y.Z -m "release notes"`
- [ ] Push tag: `git push origin vX.Y.Z`
- [ ] Watch GH Actions → Publish to PyPI; verify all 3 jobs green
- [ ] Spot-check `pip install soc-pipeline==X.Y.Z` from a clean venv

If a publish fails mid-matrix (e.g. soc-pipeline ok, guarded-llm fails):
- Fix the failing package
- Re-run **only the failed job** from GH Actions UI — `skip-existing: true` (OIDC path) prevents duplicate-upload errors for the already-published packages.

---

***REMOVED******REMOVED*** Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `HTTP 403 Invalid or non-existent authentication` | Wrong / expired token | Regenerate token, update `PYPI_API_TOKEN` secret |
| `HTTP 400 File already exists` | Re-running same version | Bump version + re-tag; PyPI is append-only |
| `Twine check failed: long_description has syntax errors` | README rST/MD issue | Run `twine check dist/*` locally; fix README |
| OIDC: `Token request failed` | Environment name mismatch | Confirm GH env `pypi` exists + trusted publisher config matches `publish-pypi.yml` |
| Workflow doesn't trigger on tag | Tag pushed without `v` prefix or not pushed | `git push origin v0.1.0` (tag must match `v*`) |

---

***REMOVED******REMOVED*** Manual dry-run (no upload)

To verify the workflow without publishing:

1. **Actions → Publish to PyPI → Run workflow**
2. Branch: `main`
3. `dry_run`: `true`
4. **Run workflow**

Builds + `twine check` runs for all 3 packages; upload step is skipped.

---

***REMOVED******REMOVED*** Files referenced

- `.github/workflows/publish-pypi.yml` — the workflow itself
- `packages/soc-pipeline/pyproject.toml` — hatchling build backend
- `packages/guarded-llm/pyproject.toml` — hatchling build backend
- `packages/cross-judge/pyproject.toml` — setuptools build backend
