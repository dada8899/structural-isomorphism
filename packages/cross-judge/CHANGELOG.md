# Changelog

All notable changes to `cross-judge` are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-05-24

### Documentation

- Added `docs/quickstart.md` — minimal 3-line install + 3-critic ensemble
  example.
- Added `docs/api-reference.md` — public API surface (`Critic`,
  `Ensemble`, `Verdict`, `EnsembleVerdict`, voting strategies, vendor
  helpers).
- Added `docs/changelog.md` — pointer to this `CHANGELOG.md`.
- Added top-level `CHANGELOG.md` (this file).

### CI / Release Infrastructure

- New repo-level workflow `.github/workflows/ci-packages.yml`:
  matrix-tests every package across Python 3.10 / 3.11 / 3.12 / 3.13 on
  ubuntu-latest and macos-latest. Runs `pytest`, builds sdist + wheel,
  and validates metadata with `twine check`.
- New repo-level workflow `.github/workflows/release-packages.yml`:
  tag-driven (`cross-judge-vX.Y.Z`) automated PyPI publish via
  `PYPI_API_TOKEN`. Safe to land before secret is configured.

### Compatibility

No behavioural change vs `0.1.0`. Public API is byte-compatible.
`__version__` bumped to `"0.1.1"`.

## [0.1.0] - 2026-05-24

### Added

- Initial public release on PyPI.
- `Critic` — single-model judge with vendor / model / temperature /
  prompt-template configuration.
- `Ensemble` — multi-critic panel with pluggable voting strategy
  (`"majority"` / `"unanimous"` / custom).
- `Verdict` / `VerdictKind` — `KEEP` / `REJECT` / `SPLIT` /
  `MERGE_WITH(...)` / `UNCLEAR` enum + result dataclass.
- `EnsembleVerdict` — consensus result with `consensus`, `agreement_pct`,
  `krippendorff_alpha`, per-critic verdicts.
- Disagreement metrics: `krippendorff_alpha`, `agreement_pct`.
- Vendor adapters: DeepSeek, OpenAI, OpenRouter — via built-in `httpx`
  POST to `/v1/chat/completions` (no openai-python SDK required at v0.1).
  Optional `[openai]` extra for users who prefer the official client.
- Legacy `Reviewer` / `JudgePanel` API preserved for the v4 / B3
  ensemble-review pipeline.

[0.1.1]: https://github.com/dada8899/structural-isomorphism/compare/cross-judge-v0.1.0...cross-judge-v0.1.1
[0.1.0]: https://github.com/dada8899/structural-isomorphism/releases/tag/cross-judge-v0.1.0
