# D1 Phase Detector — Status

> Last updated: 2026-05-14 (session #7, Wave 1 Agent B)

## Inventory

| Artifact | Rows | Notes |
|---|---|---|
| `companies.jsonl` | 100 | Curated by hand for session-3 dogfood (rich `sector` tags + a-priori dynamics) |
| `structtuples_2026-05-13.jsonl` | 100 | Output of `extract_structtuple.py` on the 100 row set (deepseek-v4-pro, 2026-05-13 batch) |
| `sp500_tickers.json` | 503 | Wikipedia scrape via `fetch_sp500_tickers.py` (2026-05-14) |
| `companies_500_input.jsonl` | 500 | Merged input (100 hand-curated + 400 SP500 additions, dedup by ticker) |
| `companies_500.jsonl` | 55 (sample) | Output of `extract_structtuple_batch.py` (deepseek-v4-flash); 5-row pilot + 50-row sample, all ok=true |

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

- [ ] Full 500-row LLM pass (`--limit 0`); estimated ~50min wall-clock at the
  default sleep + retry settings.
- [ ] Reconcile sector taxonomies: existing 100-row file uses fine-grained
  `tech_software_db`, `financials_payments`, etc.; new SP500 rows use coarse
  GICS buckets (`tech_software`, `financials`). Decision point for the
  reviewer: collapse old to coarse, or upgrade SP500 to fine via a second LLM
  pass (cost ~$0.05).
- [ ] Re-run the existing 100 under `deepseek-v4-flash` for apples-to-apples
  comparison with the new 400 (current 100 are on v4-pro).
