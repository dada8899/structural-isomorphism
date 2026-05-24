# Changelog

All notable changes to `soc-pipeline` are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-05-24

### Documentation

- Added `docs/quickstart.md` — minimal 3-line install + 5-minute example.
- Added `docs/api-reference.md` — full public API surface (mirrors
  `docs/api_reference.md` under the dash-style filename for consistency
  across packages).
- Added `docs/changelog.md` — pointer to this `CHANGELOG.md`.
- Added top-level `CHANGELOG.md` (this file).

### CI / Release Infrastructure

- New repo-level workflow `.github/workflows/ci-packages.yml`:
  matrix-tests every package across Python 3.10 / 3.11 / 3.12 / 3.13 on
  ubuntu-latest and macos-latest. Runs `pytest`, builds sdist + wheel,
  and validates metadata with `twine check`.
- New repo-level workflow `.github/workflows/release-packages.yml`:
  tag-driven (`soc-pipeline-vX.Y.Z`) automated PyPI publish via
  `PYPI_API_TOKEN`. Safe to land before secret is configured (skips
  upload step when token is absent).

### Compatibility

No behavioural change vs `0.1.0`. Public API is byte-compatible.
`__version__` bumped to `"0.1.1"`.

## [0.1.0] - 2026-05-24

### Added

- Initial public release on PyPI.
- `fit_clauset_powerlaw` — Clauset-Shalizi-Newman 2009 MLE on alpha with
  KS-minimised `xmin`, supporting continuous and discrete tails.
- `bootstrap_ci` — non-parametric bootstrap CI on alpha.
- `synthetic_null` — gaussian-walk / exponential / Poisson-IAT non-heavy-tail
  null controls; healthy pipelines reject all three.
- `vuong_lr_test` — power-law vs lognormal / exponential /
  stretched-exponential / truncated-power-law via Vuong 1989 LR.
- `fit_b_value` — Gutenberg-Richter b-value (Aki 1965 MLE) with optional
  bootstrap CI and `alpha_equivalent` conversion via Hanks-Kanamori.
- `fit_omori_p` / `bin_and_omori_from_events` — Omori-Utsu aftershock
  decay fitting (stack-mode and stream-mode).
- `shape_normalized_collapse` — universal CCDF collapse across systems.
- `time_resolution_sweep` — stability check across binning resolutions.
- `verdict_from_alpha_band` — 3-tier `CONFIRMED` / `DEVIATING` / `INCONCLUSIVE`
  verdict assignment.

[0.1.1]: https://github.com/dada8899/structural-isomorphism/compare/soc-pipeline-v0.1.0...soc-pipeline-v0.1.1
[0.1.0]: https://github.com/dada8899/structural-isomorphism/releases/tag/soc-pipeline-v0.1.0
