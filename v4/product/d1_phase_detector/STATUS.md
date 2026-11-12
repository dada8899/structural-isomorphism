# D1 Phase Detector — Status

> Last updated: 2026-05-22 (D1 scale-up verification — full 500-row pass confirmed)

## Inventory

| Artifact | Rows | Notes |
|---|---|---|
| `companies.jsonl` | 100 | Curated by hand for session-3 dogfood (rich `sector` tags + a-priori dynamics) |
| `structtuples_2026-05-13.jsonl` | 100 | Output of `extract_structtuple.py` on the 100 row set (deepseek-v4-pro, 2026-05-13 batch) |
| `sp500_tickers.json` | 503 | Wikipedia scrape via `fetch_sp500_tickers.py` (2026-05-14) |
| `companies_500_input.jsonl` | 500 | Merged input (100 hand-curated + 400 SP500 additions, dedup by ticker) |
| `companies_500.jsonl` | 500 (full) | Output of `extract_structtuple_batch.py` (deepseek-v4-flash); full 500-row pass, 500/500 ok=true, 0 fail, no missing fields, every row has >=2 evidence anchors |
| `backtest_result.json` | — | `backtest.py` walk-forward (6m hold, 54 snapshots) on full 500: Sharpe nc=0.238 / other=0.318, t=-0.41 p=0.68 — **null result** (no near-critical edge) |
| `backtest/results/v0.1-1000-universe-*.json` | — | `backtest/engine.py` 1000-ticker daily engine (separate experiment): near-critical Sharpe 0.70 vs benchmark 0.77, p=0.57 — also **null result** |

## Pipeline scale-up (100 → 500)

Scripts added in this milestone:

1. **`fetch_sp500_tickers.py`** — pulls the S&P 500 constituent table from Wikipedia
   (`https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`) via stdlib
   `urllib + html.parser`; falls back to a static ~120-row list embedded in the
   script if Wikipedia is unreachable. Output: `sp500_tickers.json`
   (`{source, count, tickers: [{symbol, name, sector}, ...]}`).
2. **`extract_structtuple_batch.py`** — thin batch wrapper around the prior
   `extract_structtuple.extract_one`. Adds:
   - default model `deepseek-v4-flash` (cheaper for batch)
   - `--dry-run` mode (prints prompts only, no LLM call, no key required)
   - `--limit N` (default `50` for sample, `0` for full pass)
   - resume support: skips tickers already in output with `ok=true`
   - inlined `.env` autoload for `DEEPSEEK_API_KEY`
   - PYTHONPATH fix-up for `guarded_llm` (editable install paths drift across
     worktrees)

## Cost / budget

deepseek-v4-flash, ~750 prompt + ~970 completion tokens per row (reasoning model):
- 5-row pilot: 3727 in / 4186 out → ~$0.005
- 50-row sample: 37388 in / 48614 out (601.7s wall) → ~$0.05
- 500-row full pass: ~$0.50 projected, ~50 min wall-clock

Well under the $5 standing batch budget. Full 500-row run is gated by reviewer
sign-off + a small price-check rerun, not by budget.

## Reproduce

```bash
# 1. ticker list (Wikipedia or fallback)
.venv/bin/python3 v4/product/d1_phase_detector/fetch_sp500_tickers.py

# 2. merge -> 500-row input (inline script in commit message;
#    rerunning fetch + edit script is idempotent)
# (companies_500_input.jsonl is committed; only regenerate if SP500 membership changes)

# 3. dry-run sanity check
.venv/bin/python3 v4/product/d1_phase_detector/extract_structtuple_batch.py \
    --dry-run --limit 3

# 4. 50-row sample (resume-safe)
.venv/bin/python3 v4/product/d1_phase_detector/extract_structtuple_batch.py \
    --limit 50

# 5. full 500-row pass (after reviewer)
.venv/bin/python3 v4/product/d1_phase_detector/extract_structtuple_batch.py \
    --limit 0 --model deepseek-v4-flash
```

## Pending / next session

- [x] Full 500-row LLM pass (`--limit 0`) — DONE. `companies_500.jsonl` holds
  500/500 successful rows, all `model=deepseek-v4-flash`, 0 fail, 0 missing
  fields. Family mix: linear_quasi_equilibrium 300, preferential_attachment 49,
  hysteresis_preisach 30, soc_threshold_cascade 28, motter_lai_cascade 27,
  mixed_or_unclear 21, scheffer_fold 18, reflexive_fixed_point 15,
  extreme_value_tail 12. Only 2 rows have confidence < 0.5.
- [x] Backtest on full 500 — DONE. `backtest.py` walk-forward (6m hold) re-run
  2026-05-22, identical to prior result: **null result**, near-critical cohort
  shows no edge (Sharpe 0.238 vs other 0.318, t=-0.41, p=0.68).
- [x] Sector taxonomy — left as-is. The mixed fine/coarse `sector` tags do NOT
  feed the extractor prompt or the backtest cohorting (cohorting is by
  `critical_point_state`), so the inconsistency is cosmetic. No reconciliation
  needed for D1.
- [ ] Re-run the existing 100 under `deepseek-v4-flash` for apples-to-apples
  comparison — moot now: all 500 in `companies_500.jsonl` are already on
  `deepseek-v4-flash`. The legacy `structtuples_2026-05-13.jsonl` (v4-pro) is
  superseded by `companies_500.jsonl` for any downstream use.
