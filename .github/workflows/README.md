# GitHub Actions Workflows

This directory contains CI / observability workflows for the structural-isomorphism
project. All workflows run on `ubuntu-latest`.

## Workflows

### `ci.yml` (pre-existing)

Multi-Python-version matrix for full test suite (sanity + integration) and
package tests. Triggered on push / PR to `main`. Slower (~5-10 min); the
authoritative correctness gate.

### `sanity.yml` (this batch)

Minimal sanity-only workflow on Python 3.11. Runs `pytest v4/tests/sanity -m sanity`
in quiet mode with short tracebacks. Purpose:

- Fast-feedback signal for PRs touching v4 lib (must stay green to merge)
- Cheaper than the full matrix; complements `ci.yml` rather than replacing it

Triggered on push / PR to `main`.

### `site-smoke.yml` (this batch)

Curls the three public hosts every 6 hours to confirm they return HTTP 200:

- `https://beta.structural.bytedance.city/`
- `https://structural.bytedance.city/`
- `https://phase.bytedance.city/`

Any non-200 fails the job and surfaces in the Actions tab. Purpose: catch
silent VPS / nginx / DNS regressions without requiring an external uptime
service.

#### How to trigger manually

```
# via gh CLI
gh workflow run site-smoke.yml

# via GitHub UI
Actions tab -> "site smoke" -> "Run workflow" -> "Run workflow" (main branch)
```

Schedule: cron `0 */6 * * *` (every 6h on the hour, UTC). GitHub may delay
scheduled runs during high load; `workflow_dispatch` is the always-reliable
manual escape hatch.

## Adding a new workflow

1. Drop the `.yml` file in this directory
2. Validate locally: `python -c "import yaml; yaml.safe_load(open('.github/workflows/<name>.yml'))"`
3. Push; first run lands in Actions tab
4. Update this README with the workflow's purpose + trigger conditions
