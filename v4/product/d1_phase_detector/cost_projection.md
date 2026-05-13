# D1 Phase Detector — cost & latency projection

**Date**: 2026-05-13
**Branch**: v4/session2-mega-sprint
**Model**: `deepseek-v4-pro` (direct API, bypasses OpenRouter CN region-block)

---

## Sample run (5 companies — measured)

5/5 calls succeeded on first attempt. No state-machine fix required (JSON parsed cleanly via guardrail). See `sample_run_stats.json` for raw numbers.

| ticker | prompt_tokens | completion_tokens | total_tokens | latency_s | attempts |
|---|---:|---:|---:|---:|---:|
| AAPL | 744 | 1346 | 2090 | 40.6 | 1 |
| BBY  | 752 | 1246 | 1998 | 38.3 | 1 |
| JPM  | 751 | 1588 | 2339 | 48.2 | 1 |
| AIG  | 745 | 2371 | 3116 | 71.4 | 1 |
| KO   | 745 | 1116 | 1861 | 34.2 | 1 |
| **avg** | **747** | **1533** | **2281** | **46.5** | **1.0** |
| **sum** | **3,737** | **7,667** | **11,404** | **232.6** | — |

**Wall clock** (serial): 232.6s ≈ 3.9 min for 5 companies.

---

## Sample cost (measured)

Pricing reference — DeepSeek `deepseek-v4-pro` (deepseek.com, 2026-05; standard rates, no off-peak discount applied):

- input  (cache-miss): **$0.27 / 1M tokens**
- input  (cache-hit):  **$0.07 / 1M tokens**
- output:              **$1.10 / 1M tokens**

Sample run was all cache-miss (5 distinct system+user prompts):

- input  cost: 3737 tok × $0.27/M = **$0.00101**
- output cost: 7667 tok × $1.10/M = **$0.00843**
- **total sample cost: $0.00944** (~1 US cent for 5 companies)

Per-company average: **$0.00189** (~0.19 cent).

---

## Projected full 100-company batch

Linearly extrapolated from sample averages (avg 747 in / 1533 out per company):

| metric | value |
|---|---:|
| total prompt tokens     | 74,700 |
| total completion tokens | 153,300 |
| total tokens            | 228,000 |
| input cost  ($0.27/M)   | $0.0202 |
| output cost ($1.10/M)   | $0.1686 |
| **total cost**          | **~$0.19** |
| serial latency (46.5s × 100) | **~77.5 min** |
| 5-way parallel latency  | **~15.5 min** |
| 10-way parallel latency | **~7.8 min** |

Even at 10x volume (1000 companies, e.g. Russell 1000) cost is **~$1.90**; latency at 10-way parallel is **~78 min**. Both well within session-affordable.

### Cache-hit savings (likely on system prompt)

The DeepSeek API does prefix caching automatically for repeated system prompts. The system prompt (~270 tokens) is identical across all calls. After the first call in a session, that portion becomes cache-hit:

- naive cost (no cache): $0.19 / 100 companies
- with system-prompt caching (~270 of 747 input tokens hit cache for 99 of 100 calls): savings ≈ 99 × 270 × ($0.27 − $0.07) / 1M = $0.0053
- realistic cost: **~$0.18 / 100 companies** (negligible difference)

So caching savings are not material at this scale; the dominant cost is output tokens.

---

## Retries / failures budget

Sample showed 0 retries needed (100% first-attempt validation). Realistic robust estimate assuming 5% retry rate at 1.5× cost per retried call:

- retry overhead: 5 retries × $0.00189 × 1.5 = $0.014
- **robust total: ~$0.21 / 100 companies**

Tracking the retry rate in production is cheap and surfaces drift early.

---

## Recommendations for next-session full batch

1. **Run mode**: 5-way parallel (`asyncio` or `concurrent.futures.ThreadPoolExecutor(max_workers=5)`) — 100 companies in ~15 min, well below DeepSeek rate limits.
2. **Cost cap**: budget $0.50 total for the 100-company batch (≥2.5× buffer over projection).
3. **Quality cap**: before scaling to Russell 1000 or beyond, **expand the dogfood to 20-30 companies** and have a human (or B3-style ensemble of v4-pro / v4-flash / claude-sonnet) re-score the dynamics_family. Sample showed 3/5 MATCH vs prior expectations, but priors are loose; an ensemble vote will give a real calibration baseline.
4. **Storage**: results fit in a single JSONL (~228k tokens × ~3 bytes/tok JSON ≈ 700KB for 100 companies). Postgres ingestion can wait until volume exceeds ~5,000 StructTuples.
5. **Refresh cadence**: a StructTuple is point-in-time. If we refresh quarterly (every ~90 days), annual recurring cost for 100 companies = ~$0.80. For Russell 1000 quarterly = ~$8/year. Trivial.

---

## Open questions for cost / quality (next session)

- Should we run **multi-model ensemble** (deepseek-v4-pro + deepseek-v4-flash + a non-DeepSeek backup) for higher-confidence StructTuples? Cost would ~3×; latency similar (parallel). Defer until D2 calibration.
- Is `deepseek-v4-pro` vs `deepseek-v4-flash` quality gap worth the ~3-4× cost? Run an A/B on the same 20-company set; if flash is within 80% of pro on dynamics_family accuracy, flash becomes the workhorse and pro is reserved for borderline cases.
- For B2B / Phase Detector public-facing, the per-company **marginal cost is so low (~0.2 cent)** that pricing won't be cost-bound; it's value-bound. We can charge **$5/mo for unlimited screener access** and still net ~$4.99/user/mo even if they run the full 100-company screen daily.
