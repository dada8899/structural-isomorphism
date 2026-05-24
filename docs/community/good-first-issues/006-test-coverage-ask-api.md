# [tests] Lift coverage of `web/backend/api/ask.py` above 80 %

## What

`web/backend/api/ask.py` is the SSE orchestrator that powers the production `https://structural-isomorphism.bytedance.city/ask` endpoint (Perplexity-like live answer mode). Today coverage is < 70 %. Add unit + integration tests to bring it to ≥ 80 % with a `pytest-cov` report attached to the PR.

## Why

`ask.py` handles 7-event SSE streaming, per-tier rate-limiting, abort propagation, and OpenRouter region-block fallback. Each of these is fragile and bug-prone; a coverage uplift here is the single highest-leverage test-quality contribution in the repo.

## Where

- Target file: `web/backend/api/ask.py` (117 lines)
- Place tests at: `web/tests/backend/test_ask_api.py`
- Existing test patterns: `web/tests/backend/test_*.py`

## How to start

1. Install dev deps and baseline coverage:
   ```bash
   pip install pytest pytest-cov pytest-asyncio httpx
   pytest --cov=web.backend.api.ask --cov-report=term-missing web/tests/
   ```
2. Identify uncovered branches (the `term-missing` column lists line numbers).
3. Write tests using FastAPI `TestClient` for sync paths and `httpx.AsyncClient` for the SSE stream.
4. Mock OpenRouter via `respx` or `pytest-httpx`. Cover at least: happy path, region-block 403 fallback to DeepSeek, abort mid-stream, malformed upstream JSON, rate-limit 429.

## Definition of done

- [ ] Coverage of `ask.py` ≥ 80 % (attach `pytest --cov` output to PR)
- [ ] At least 1 SSE-streaming test that consumes events and asserts the 7-event order
- [ ] At least 1 fallback-to-DeepSeek test (mock OpenRouter returning 403)
- [ ] CI green (`make test-all` does not regress)

## Difficulty

★★ (requires pytest-asyncio familiarity)
