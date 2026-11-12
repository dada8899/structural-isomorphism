# CI matrix decisions

> Source of truth for which OS × Python combos run in `.github/workflows/ci.yml`.
> Update this doc whenever the matrix changes — the matrix comment in `ci.yml`
> references this file.

## Active matrix (backend job)

| OS             | py3.10 | py3.11 | py3.12 |
| -------------- | :----: | :----: | :----: |
| ubuntu-latest  |   ✅   |   ✅   |   ✅   |
| macos-latest   |   ❌   |   ✅   |   ✅   |
| windows-latest |   ❌   |   ❌   |   ❌   |

Rationale:
- **ubuntu-latest** is the production target (VPS deploys are Linux). All three
  Python minors must stay green here — 3.10 is the floor, 3.11/3.12 are forward.
- **macos-latest** covers dev-laptop parity (most contributors). 3.10 dropped
  to keep total wall-time low; 3.10 + macOS combo adds zero unique signal
  beyond what ubuntu 3.10 already provides.
- **windows-latest** excluded entirely (see below).

## Why Windows is excluded

Empirically, every Windows job under py3.11 / py3.12 hits one of three
classes of failure that are **infrastructure-shaped, not logic-shaped** —
fixing them requires sweeping changes across the codebase for zero deploy
value (prod is Linux, dev is macOS):

1. **UnicodeDecodeError on `pathlib.read_text()`** — Windows defaults to
   `cp1252` when no `encoding=` is passed. Any JSON fixture containing UTF-8
   chars (`≥`, `±`, `μ`, CJK) fails to decode on Windows. Example:
   `v4/tests/sanity/test_site_data_consistency.py` reading `web/data/*.json`.
2. **UnicodeEncodeError on stdout/file writes** — Python prints `≥` (`≥`)
   to a cp1252 stream and crashes. Hit in
   `v4/tests/sanity/test_b3_ensemble.py::TestWriteSummary`.
3. **`sys.path` / module-discovery differences under `D:\a\...` runner paths**
   — subprocess tests that do `sys.path.insert(0, 'v4/scripts')` then
   `import b3_ensemble` fail with `ModuleNotFoundError` on Windows, even
   though they pass on ubuntu/macos with the same `sys.path` mutation.

A global fix would require:
- Auditing every `open()` / `read_text()` / `write_text()` to add
  `encoding='utf-8'` (hundreds of call sites).
- Replacing all `≥`-style chars in stdout with ASCII equivalents,
  OR forcing `PYTHONUTF8=1` env via `setup-python` (still has edge cases).
- Switching subprocess `sys.path` injection to use `pathlib.Path(...).resolve()`
  with `as_posix()` everywhere.

For a Linux-deploy product with macOS dev fleet, that's net-negative ROI.

## When to reconsider

Re-introduce Windows to the matrix only if **all** of the following become true:
- Windows becomes a supported deployment target (currently no plan).
- Or, a contributor permanently dev-fleets on Windows.
- Or, a dependency we add (e.g. pure-Python library) starts shipping
  Windows-specific bugs that need regression coverage.

If reintroduced, the prereq work above must land first as its own milestone
(estimated: 1–2 days, multiple files, schema-touching).

## History

- **2026-04-xx**: Original matrix excluded `(macos, 3.10)` and `(windows, 3.10)`
  only — windows 3.11/3.12 expected to pass.
- **2026-05-15** (session #11): Windows runners consistently red across
  py3.11 / py3.12 due to the three failure classes above. Pragmatic call:
  drop Windows entirely, keep macOS for dev parity. Documented here so
  future contributors don't re-add Windows assuming it was "just slow".

## 2026-07-14 release-gate aggregation and external boundary

`.github/release-gate-manifest.json` is the single repository authority for
release checks. The `release-gate-summary` job in `ci.yml` fails closed over
all CI-internal jobs, including both browser contracts. Type regeneration,
the canonical sanity suite, and the three-run beta performance audit remain
separate workflows so their evidence and timeouts stay independently visible.

GitHub Actions cannot express `needs` across workflow files. Therefore the
final merge boundary is external: main-branch protection must require every
check in `branch_protection_required_checks` from the manifest. A green
`release-gate-summary` alone is insufficient. The types and performance
workflows intentionally run on every pull request and push to `main`; adding
path filters would make a required check remain absent or pending.

Branch protection must use the manifest's exact `context` values, not assume
that a workflow job id is the emitted check name. GitHub Actions emits the
job-level `name` when present; only unnamed jobs fall back to their job id.
The desired contexts are `release-gate`, `sanity`, `check`, and
`beta-perf-audit`.

The live protection API is authoritative. As checked on 2026-07-14, `main`
was strict but required only `sanity`, so the external release boundary was
not yet satisfied. Do not add a context before a pull request has emitted its
check run: first confirm all four names from the PR checks, update branch
protection, then read the protection API again and compare its exact context
set with the manifest. The manifest is a configuration contract, not evidence
that the repository setting has already been applied.

The TypeScript generator has two evidence levels. Local `make types-check`
proves byte reproducibility in the current developer runtime; it is not an
attestation against a hostile same-UID process that can replace the checkout,
interpreter, or native executables. Release evidence comes from the required
`check` job on a clean GitHub runner: `actions/setup-node` establishes the Node
runtime, `npm ci --ignore-scripts` reconstructs the content-locked dependency
tree, and the generated artifact must byte-match the committed file. The
generator additionally rejects shell command overrides, package-entrypoint
escape, entrypoint content drift, script wrappers, and Node identity mismatch.
