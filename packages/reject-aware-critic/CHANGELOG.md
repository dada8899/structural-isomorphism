# Changelog

All notable changes to `reject-aware-critic` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2026-05-25

Initial public release. Packages the V4 B3 (within-vendor multi-decoding)
and B4 (cross-vendor) critic ensembles from the
[C4 paper](https://github.com/dada8899/structural-isomorphism/blob/main/paper/c4-reject-aware-pipeline-2026-05-13.md)
as a standalone PyPI library.

### Added

- `Critic` — single-vendor single-decoding LLM judge with cost guardrail and
  optional JSONL audit logging.
- `CriticEnsemble` — collection of critics with `.b3()` (3 decodings on
  1 vendor) and `.b4()` (1 critic per vendor) construction helpers.
- `CandidateClass` / `Verdict` / `EnsembleResult` Pydantic schemas.
- Reject-aware filter (`filters.py`) for the four prototype trap categories
  from C4 §4.3:
  - `mechanism_vs_limit_theorem`
  - `mathematical_framework_masquerading`
  - `surface_similarity_from_heavy_tails`
  - `mechanism_dispersion_monolith`
- Vendor adapter (`_vendors.py`) covering DeepSeek, OpenRouter, Anthropic
  (via OpenRouter), Kimi (via OpenRouter), GLM (via OpenRouter), OpenAI,
  plus an offline `mock` vendor for CI.
- `CostBudgetError` enforcement on every `judge()` call (default $0.05).
- `register_mock_responder(...)` hook for offline tests / CI.
- `examples/21_class_panel_demo.py` — offline reproduction of three C4 §4.3
  prototype demotions using the mock vendor.
