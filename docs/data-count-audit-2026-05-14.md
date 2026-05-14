# Phase Detector data-count audit — 2026-05-14

> session #9, Wave 1 sub-agent B. Trigger: README claims "500 publicly listed
> companies" but the live phase.bytedance.city hero copy reads "100 家全球公司".
> Same product, two numbers in user-visible surfaces → trust killer. This doc
> establishes the ground truth and reconciles all surfaces to one consistent
> story.

## TL;DR

| Surface | Number before | Number after | Rationale |
|---|---|---|---|
| Frontend `app/page.tsx` hero | 100 家全球公司 | **100 家全球公司**（unchanged） | Matches production DB |
| Frontend `app/about/page.tsx` | 当前覆盖 100 家上市公司 | unchanged | Matches production DB |
| Frontend `app/methodology/page.tsx` | 当前 100 家公司 | unchanged | Matches production DB |
| README.md § "Phase Detector product" | tags **500** publicly listed companies | tags **100** publicly listed companies (with a 500-ticker S&P 500 walk-forward backtest universe) | Aligns with production DB; calls out the larger backtest universe separately |
| README.md § "Live demos" table | 500 companies tagged ... | 100 companies tagged ... (500-ticker S&P 500 backtest universe in v0.1) | Same |
| README.md § "Status snapshot" | Live at 500 companies + backtest v0.1 | Live at 100 companies + 500-ticker S&P 500 backtest v0.1 | Same |
| `v4/product/d1_phase_detector/README_BACKTEST.md` | "497/500 tickers" / "500 SP500 StructTuples" | unchanged | These numbers describe the backtest universe and are accurate (see below). |

## Ground truth — where each number comes from

### Production product universe = **100 companies**

This is what `phase.bytedance.city` actually serves.

| Evidence | Value |
|---|---|
| `v4/product/d1_phase_detector/companies.jsonl` (`wc -l`) | **100** rows |
| `v4/product/d1_phase_detector/structtuples_2026-05-13.jsonl` (`wc -l`) | **100** rows (97 ok + 3 failed, per stats md) |
| `v4/product/d1_phase_detector/batch_run_2026-05-13_stats.md` line 5 | "rows processed: **100**" |
| `v4/product/d1_phase_detector/STATUS.md` line 11 | "`companies.jsonl` \| 100 \| Curated by hand for session-3 dogfood" |
| `v4/product/d1_phase_detector/STATUS.md` line 12 | "`structtuples_2026-05-13.jsonl` \| 100 \| Output of `extract_structtuple.py` on the 100 row set (deepseek-v4-pro, 2026-05-13 batch)" |
| `v4/product/d1_phase_detector/scripts/ingest_to_postgres.py` defaults | reads `structtuples_2026-05-13.jsonl` → ingests to `d1_companies` table consumed by `/screener` API |

The DeepSeek-v4-**pro** model was used for the production extraction (richer
reasoning, higher cost ≈ $0.05). The 100-row roster was hand-curated to give
diverse sector coverage + explicit a-priori expected dynamics families for
calibration purposes.

### Backtest universe = **500 / 497 fetched** tickers

This is a different artefact: a walk-forward statistical backtest that ran
against a much larger universe to test whether the `near_critical` label
predicts forward returns. The 500-ticker run uses cheaper
`deepseek-v4-**flash**` for cost reasons (~$0.50 vs ~$2.50).

| Evidence | Value |
|---|---|
| `v4/product/d1_phase_detector/sp500_tickers.json` `count` field | 503 (Wikipedia scrape, 2026-05-14) |
| `v4/product/d1_phase_detector/companies_500_input.jsonl` (`wc -l`) | 500 (100 hand-curated + 400 SP500 dedup additions) |
| `v4/product/d1_phase_detector/companies_500.jsonl` (`wc -l`) | 500 (deepseek-v4-flash, all ok=true) |
| `v4/product/d1_phase_detector/prices.meta.json` `yfinance_tickers` | **497** fetched (3 missing: `RE` delisted, `BF.B` + `BRK.B` dotted-ticker yfinance bug) |
| `v4/product/d1_phase_detector/README_BACKTEST.md` line 76 | "walk-forward backtest on real SP500 monthly prices (yfinance, 5y history, 497/500 tickers)" |

Backtest result (`backtest_result.json` / `cumulative_return.png`):
`near_critical` label produced statistically indistinguishable 6-month forward
returns vs `other` on the SP500 universe (p ≫ 0.05). This is documented as a
**negative result** in `README_BACKTEST.md` ("商业化路径暂未打开"). The 500-ticker
universe is therefore a research artefact, not a product feature.

### Why the README said 500

Likely written aspirationally during the M11+M12 scale-up sprint (commit log
references `companies_500.jsonl` work). The intent was to ship a 500-company
product after the backtest validated the signal — but the backtest came back
negative, so the production deploy stayed on the 100-row curated set while the
README was never walked back. Classic "documentation lags actual ship".

## Decision

1. **Frontend wins** — every user-visible surface on `phase.bytedance.city`
   already says 100. The data layer agrees. Don't touch the frontend.
2. **Fix the README** to match production reality, but **don't erase the 500**:
   the 500-ticker S&P 500 backtest universe is a real research artefact, just
   not the product. Re-frame as "100 in product + 500 in backtest universe" so
   the cross-references in `README_BACKTEST.md` stay coherent.
3. **Leave `README_BACKTEST.md` alone** — the 497/500 / 500 SP500 numbers there
   describe the backtest run accurately.

## Future-proofing

If we ever ship a 500-company production roster (i.e. ingest
`companies_500.jsonl` outputs into `d1_companies` and serve them via
`/screener`), update:

- `README.md` § "Phase Detector product"
- `README.md` § "Live demos" table
- `README.md` § "Status snapshot"
- `web/phase-detector/app/page.tsx` line 150 ("100 家全球公司")
- `web/phase-detector/app/about/page.tsx` line 46 ("当前覆盖 100 家上市公司")
- `web/phase-detector/app/methodology/page.tsx` line 181 ("覆盖：当前 100 家公司")
- `v4/product/d1_phase_detector/README.md` (every "100-company" mention)
- `v4/product/d1_phase_detector/STATUS.md` inventory table

In other words: do not change one surface in isolation. The "100" string lives
in 8 places and they must move together.

## References

- README change committed in this PR (`session-9/w1-b-data-count-reconcile`)
- Audit performed in worktree `/tmp/structural-w1-b-*`
- All numbers verified with `wc -l` / `head` / `grep` on the actual files
  (not LLM-inferred), 2026-05-14.
