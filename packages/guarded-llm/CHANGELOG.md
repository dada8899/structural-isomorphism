# Changelog

All notable changes to `guarded-llm` are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-05-24

### Documentation

- Added `docs/quickstart.md` — 3-line install + minimal end-to-end example.
- Added `docs/api-reference.md` — public API surface (mirrors
  `docs/api_reference.md` under the dash-style filename for consistency
  across the three packages).
- Added `docs/changelog.md` — pointer to this `CHANGELOG.md`.
- Added top-level `CHANGELOG.md` (this file).

### CI / Release Infrastructure

- New repo-level workflow `.github/workflows/ci-packages.yml`:
  matrix-tests every package across Python 3.10 / 3.11 / 3.12 / 3.13 on
  ubuntu-latest and macos-latest. Runs `pytest`, builds sdist + wheel,
  and validates metadata with `twine check`.
- New repo-level workflow `.github/workflows/release-packages.yml`:
  tag-driven (`guarded-llm-vX.Y.Z`) automated PyPI publish via
  `PYPI_API_TOKEN` (workflow degrades to dry-run when the secret is
  absent, so it is safe to land before the secret is configured).

### Compatibility

No behavioural change vs `0.1.0`. Public API is byte-compatible.
`__version__` bumped to `"0.1.1"`.

## [0.1.0] - 2026-05-24

### Added

- Initial public release on PyPI.
- `GuardedLLM` high-level wrapper with strict-JSON validation, retry
  with error-feedback, and `Budget` cap.
- Provider adapters: DeepSeek, Anthropic, OpenAI, Kimi (Moonshot),
  GLM / Zhipu — via built-in `httpx` adapters; optional vendor SDK
  extras (`[anthropic]`, `[openai]`, `[deepseek]`, `[kimi]`, `[glm]`,
  `[all]`).
- 4-layer guard pipeline: fence strip → state-machine fix → `json.loads`
  → schema validation (`LLMSchema` / Pydantic / `.validate(...)` duck-type).
- Legacy positional API (`guardrailed_llm_call(prompt_fn, llm_caller,
  schema_cls, max_retries)`) preserved for v4 pipeline callers.
- Legacy dataclass schemas re-exported for backwards compat:
  `Layer3CriticVerdict`, `Layer4Prediction`, `B3EnsembleReview`.

[0.1.1]: https://github.com/dada8899/structural-isomorphism/compare/guarded-llm-v0.1.0...guarded-llm-v0.1.1
[0.1.0]: https://github.com/dada8899/structural-isomorphism/releases/tag/guarded-llm-v0.1.0
