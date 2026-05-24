# Retrieval analytics framework — 2026-05-24 (Session 22)

## What this doc covers

A quantitative framework for analysing `web/backend/logs/retrieval.jsonl` —
the structured log stream emitted by `services.retrieval_pipeline.run_retrieval`
on every `/ask` retrieval call. The X2 agent introduced the logger in
session 22; this framework defines the **questions we will ask of those
logs 1 week from now** and the **script that answers them**.

- Analysis script: `scripts/analyze_retrieval_logs.py`
- Output: `docs/observability/retrieval-analysis-<UTC-ts>/{report.md,summary.json,figures/*.png}`
- Cadence: run weekly (manually for the first 4 weeks while we calibrate
  the metrics, then move to a `loop` or `schedule` task).

## Log schema (canonical, mirrors retrieval_pipeline.py)

```jsonc
{
  "ts":               "2026-05-25T07:43:12.301456+00:00",  // ISO-8601 UTC
  "event":            "ask.retrieval",
  "query_hash":       "a1b2c3d4e5f60718",                  // 16-hex SHA-256 prefix (privacy)
  "query_len":        37,                                  // chars in raw query
  "lang_detected":    "zh" | "en" | "mixed" | "und",
  "expansion_used":   true | false,                        // LLM query-expansion fired
  "translation_used": true | false,                        // ZH↔EN translation fired
  "candidate_count":  4,                                   // 1 if no expansion, up to 4 with expansion
  "total_recall":     43,                                  // Σ |hits| across variants (pre-fusion)
  "fused_count":      12,                                  // post-fusion result count
  "top_5_kb_ids":     ["kb-22-101", "neuro-x1-022", ...],  // top-5 ids returned to caller
  "top_5_scores":     [0.812, 0.689, 0.542, 0.510, 0.470], // parallel to top_5_kb_ids
  "elapsed_ms":       234                                  // end-to-end retrieval latency
}
```

**Privacy posture**: only the query hash is logged, never the raw query
text. This is intentional and not negotiable — the analytics that follow
**cannot** answer "what topics are users searching" beyond what's
revealed by KB-id-level frequencies.

## Questions the weekly analysis answers

| # | Question | Metric | Where in report |
| --- | --- | --- | --- |
| 1 | Is the system seeing ZH-dominant, EN-dominant, or mixed traffic? | `lang_distribution` | Language section |
| 2 | Is query expansion firing enough to justify its latency cost? | `expansion_hit_rate`, `candidate_count.mean` | Expansion section |
| 3 | What's the typical / tail latency? Should we tune cache or pool size? | `elapsed_ms.{mean,p50,p95,p99,max}` | Latency table + histogram |
| 4 | Are we retrieving enough candidates pre-fusion to make fusion meaningful? | `total_recall_pre_fusion.{mean,p95}` | Recall volume section |
| 5 | How confident are top-1 results? Is the answer surface crisp or muddy? | `top1_score.{p25,p50,p75}` + `top1_minus_top5_gap` | Quality proxy section |
| 6 | Which KB entries dominate top-5? Is the long tail dead? | `kb_coverage.top_15_most_frequent`, `share_of_top1_in_one_id` | KB coverage section |
| 7 | Do users repeat queries? (signals confusion or non-resolution) | `queries.repeat_share` | Query repetition section |
| 8 | What's the traffic shape day-by-day? | `daily_volume` | Daily volume table + figure |

## Expected insights at 1 week (priors)

These are **priors**, not predictions. The point of the framework is to
see where the data diverges from these priors. The hypotheses sit here
so we have something to falsify rather than rationalising whatever
numbers show up.

1. **Language**: ~60-70% ZH, 20-30% EN, ≤10% mixed/und. (Demo audience is
   primarily Chinese-speaking.)
2. **Expansion hit rate**: 30-50% of queries trigger expansion. Lower
   than that = expansion gate is too aggressive; higher = we are
   spending LLM tokens on queries that don't need it.
3. **Latency**: p50 ≤ 400 ms, p95 ≤ 1500 ms, p99 ≤ 3000 ms. p99 > 3 s is
   a yellow flag (likely an LLM expansion timeout or cold cache).
4. **Top-1 score distribution**: median around 0.5-0.7. **>20%** of
   queries with top-1 < 0.3 means the embedding model + KB are
   structurally failing to recall — that's an X1-style coverage gap.
5. **Top-1 score gap (top1 - top5)**: mean ~0.2-0.3. A small gap means
   the ranker can't tell good from mediocre; a very large gap (>0.5)
   means too much winner-takes-all (low diversity).
6. **KB coverage in top-5**:
   - Distinct KB ids appearing in top-5 across the week:
     ≥ 200 (out of 4888). Below that = severely underused KB.
   - Single most-frequent id share: ≤ 5%. Above that = one entry is
     swamping (likely a too-broad description).
7. **Repeat-query share**: 5-15%. Repeats are normal (demos, re-asking).
   > 30% = users are not finding what they need on first try.
8. **Daily volume**: depends on demo cadence; baseline ~50-200 events/day.

If real data diverges from these by more than ~50%, that's a finding
worth a follow-up doc, not a "tune the priors" moment.

## X2-estimated N=7 vs real-log N=?

The X2 brief (post-implementation, 2026-05-24) reported "**estimated N=7
retrieval calls so far in this session**" — that was an offline estimate
based on how many times the test runner exercised the pipeline plus a
manual smoke test or two. The estimate has two known weaknesses:

1. It only counts events the X2 agent personally observed. Any
   pre-existing demo traffic, background test runs, or parallel-session
   activity is invisible to it.
2. It does not distinguish synthetic-test traffic from real-user-shaped
   traffic. The retrieval pipeline logs unconditionally; tests that
   exercise it (e.g. `test_query_expansion.py`,
   `test_lang_detection.py`) drop rows into the same log.

**Reconciliation method** (run at end of week 1):

```bash
# Count rows in the prod log
wc -l web/backend/logs/retrieval.jsonl

# Run the analyser — N is reported as `summary["N"]`
PYTHONPATH=. .venv/bin/python scripts/analyze_retrieval_logs.py

# For test-vs-real split, the test runner monkey-patches _LOG_PATH per
# `web/backend/tests/test_query_expansion.py:73` and
# `web/backend/tests/test_lang_detection.py:35` — so prod log rows are
# tester-free by construction. Any inflation comes from manual smoke tests.
```

Then triangulate:

| signal                       | what it tells us                  |
| ---------------------------- | --------------------------------- |
| `summary["N"]`               | rows actually logged in prod path |
| `summary["queries"]["unique"]` | distinct queries (by hash)        |
| `summary["daily_volume"]`    | when those events landed          |
| `git log --since 1.week` on retrieval_pipeline.py | logger-disabled gaps   |

The **expected delta** between X2's N=7 estimate and the real number at
1 week is large (probably 1-2 orders of magnitude up if any real demo
traffic happens). The interesting comparison is not the absolute number
but **per-day stability**: if daily_volume varies by >5× day-to-day, we
have a demo-driven spike pattern (fine) or a partial outage (not fine)
— the daily_volume figure makes that obvious at a glance.

## Operational notes

- **Log rotation**: not yet implemented. If the file grows past 50 MB
  (~roughly 250K events at 200 B/line) we should add a rotation step;
  for the first month manual rotation via
  `mv retrieval.jsonl retrieval.jsonl.$(date +%Y%m%d)` is fine.
- **Privacy**: query text is **never** logged. If someone files a
  feature request to "see actual queries", first re-read the
  `_hash_query` comment in `services/retrieval_pipeline.py` — the hash
  is one-way and intentional.
- **PII**: `top_5_kb_ids` may contain ids that themselves leak structural
  metadata (which domain a user was asking about), but the ids alone are
  not PII. The hash + ids combination is still re-identifiable in
  principle if an attacker has the full query distribution; that risk
  is acceptable for an internal dashboard but **must not** be exported
  raw to a third party.
- **Schema evolution**: if `retrieval_pipeline._write_retrieval_log`
  gains a new field, `summarise()` in
  `scripts/analyze_retrieval_logs.py` will silently ignore it. That's
  OK — older log files stay readable. Removing or renaming a field
  requires updating the summariser explicitly.

## Future extensions (parking lot)

1. **Click-through correlation**: join retrieval.jsonl with the front-end
   "result clicked" event (not yet logged). Best proxy for "did the
   top-1 actually help?"
2. **Per-language quality**: split `top1_score` by `lang_detected` —
   are zh queries getting worse top-1 than en? Would suggest tokeniser
   or embedding gap on Chinese.
3. **Expansion ROI**: A/B compare `top1_score` and `elapsed_ms` between
   `expansion_used=true` and `=false`. Currently confounded by which
   queries trigger expansion (the gate uses query difficulty).
4. **Latency anomaly alerts**: trigger when `elapsed_ms.p95` over a
   30-min sliding window exceeds 2 × the 7-day rolling p95.
5. **KB coverage gap detector**: monitor the *bottom* tail — if a
   recently-added KB id (e.g. `5k-clm-005`) has zero appearances in
   top-5 across a full week of relevant traffic, the embedding may have
   placed it badly in the space, or the description may be too narrow.

## File-path summary

| What | Path |
| --- | --- |
| Log stream (input) | `web/backend/logs/retrieval.jsonl` |
| Analyser | `scripts/analyze_retrieval_logs.py` |
| This doc | `docs/observability/retrieval-analytics-framework-2026-05-24.md` |
| Weekly outputs | `docs/observability/retrieval-analysis-<UTC-ts>/` |
| Schema source-of-truth | `web/backend/services/retrieval_pipeline.py:167-181` |

## Run recipe

```bash
# default run (writes to docs/observability/retrieval-analysis-<ts>/)
PYTHONPATH=. .venv/bin/python scripts/analyze_retrieval_logs.py

# specific output dir + skip figures (for CI / no-matplotlib environments)
PYTHONPATH=. .venv/bin/python scripts/analyze_retrieval_logs.py \
    --out docs/observability/week-1 --no-figures
```
