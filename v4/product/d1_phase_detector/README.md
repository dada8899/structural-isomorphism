# D1 — Phase Detector MVP groundwork

**Status**: scaffold + sample validated (this session, 2026-05-13)
**Branch**: `v4/session2-mega-sprint`
**Scope**: schema + 100-company roster + DeepSeek extractor + 5-company sample + cost projection. **NO UI / Postgres / deploy** in this layer.

---

## What this is

Phase Detector is the V4 "structural dynamics" research stack made into a screener product (see `plans/company-analysis-product.md` v0.2). The unit of data is a **StructTuple** — one company's structural fingerprint at a point in time, anchoring it to one of the V4 universality classes plus a critical-point state and 2-5 verifiable evidence facts.

The MVP funnel:

```
company list (100)
   │
   ▼
extract_structtuple.py  ── DeepSeek-v4-pro ──>  StructTuple per company
   │
   ▼
[next session]  Postgres ingest + Screener API + UI cards
```

---

## What's in this directory

| File | Status | Purpose |
|---|---|---|
| `schema/structtuple_schema.json` | ✅ done | JSON-schema (draft 2020-12) for the StructTuple object |
| `companies.jsonl` | ✅ done | 100-company roster with sector / market-cap / a-priori expected dynamics family |
| `extract_structtuple.py` | ✅ done | Single-company extractor: DeepSeek call + guardrail validate + retry |
| `sample_run.py` | ✅ done | Calls 5 diverse companies through extract_one, writes JSONL + stats |
| `sample_structtuples.jsonl` | ✅ done | 5 measured StructTuples (AAPL/BBY/JPM/AIG/KO), all valid |
| `sample_run_stats.json` | ✅ done | Per-call usage + latency from the sample |
| `cost_projection.md` | ✅ done | Measured + extrapolated cost and latency for 100-company batch |
| `README.md` | ✅ done (this file) | Handoff |

---

## How to reproduce the sample

```bash
cd /Users/dadamini/Projects/structural-isomorphism
python3 v4/product/d1_phase_detector/sample_run.py
```

The script makes 5 real DeepSeek API calls (no mock). Takes ~4 minutes serial. Output files land next to the script.

To run the full 100-company batch (next session):

```bash
python3 v4/product/d1_phase_detector/extract_structtuple.py \
  v4/product/d1_phase_detector/companies.jsonl \
  v4/product/d1_phase_detector/all_structtuples.jsonl \
  --limit 100
```

Projected cost: **~$0.19**, serial latency **~78 min**, 5-way parallel **~15 min**. See `cost_projection.md`.

---

## Sample dogfood result (2026-05-13)

5/5 calls succeeded on first attempt (0 retries, 0 guardrail-required fixes):

| ticker | a-priori family | actual family (deepseek-v4-pro) | match | conf |
|---|---|---|---|---:|
| AAPL | preferential_attachment | preferential_attachment | MATCH | 0.85 |
| BBY  | scheffer_fold           | linear_quasi_equilibrium | DIFFER | 0.85 |
| JPM  | motter_lai_cascade      | motter_lai_cascade       | MATCH | 0.80 |
| AIG  | motter_lai_cascade      | soc_threshold_cascade    | DIFFER | 0.85 |
| KO   | linear_quasi_equilibrium | linear_quasi_equilibrium | MATCH | 0.95 |

**Reading the differences**:
- BBY DIFFER → model argues Best Buy is mature mean-reverting consumer electronics retail, not a fold-bifurcation candidate. Defensible; my a-priori was too pessimistic.
- AIG DIFFER → model places AIG post-2008 restructuring as SOC-tail (catastrophe-driven P&C losses) rather than network cascade. Also defensible; the cascade story was AIG-pre-bailout.

These priors are **loose sanity checks**, not ground truth. Real calibration needs (a) multi-model ensemble agreement or (b) human expert tagging.

---

## TODO — next session (E1 / E2 or D2)

### Blocking for MVP launch

- [ ] **Full 100-company batch run** via `extract_structtuple.py` (≤30 min, ≤$0.50 total)
- [ ] **Quality calibration**: re-score 20-company subset with `deepseek-v4-flash` + a non-DeepSeek model (Claude-Sonnet-4.5 / Kimi-K2.5) and compute inter-model agreement
- [ ] **Postgres schema**: `struct_tuple` table (one row per company-snapshot) + `evidence_anchor` child table + `v4_class_alignment` JSONB. Migration file `0001_struct_tuple_schema.sql`
- [ ] **Postgres ingestion script**: `ingest_struct_tuples.py` reading the all_structtuples.jsonl and upserting
- [ ] **Screener API endpoint** (FastAPI): `GET /screener?dynamics_family=...&critical_point_state=...&min_confidence=...` returning matching tickers + summary
- [ ] **Screener UI** (Next.js): filter sidebar (dynamics_family / critical_point_state / sector / market-cap) + result list with 30-second TL;DR cards
- [ ] **`phase.bytedance.city` deploy**: nginx config, Let's Encrypt cert, project-site skill

### Nice-to-have

- [ ] **Detail / drill-down page** per ticker showing full StructTuple + evidence_anchors + early_warning_indicators with charts
- [ ] **Refresh cadence cron**: re-run extraction quarterly (or on news trigger)
- [ ] **Diff view**: show how a company's dynamics_family / critical_point_state has changed between snapshots
- [ ] **Public Index API** (B2B) — paid tier, JSONL streaming
- [ ] **Validation against the V4 taxonomy v2** (B3 output): populate `v4_class_alignment` field by computing softmax similarity from the company description to each surviving class in `B3_taxonomy_v2.jsonl`

### Open questions

- Cost-vs-quality A/B between v4-pro and v4-flash — flash is ~3-4× cheaper, run side-by-side to see if dynamics_family accuracy holds
- Ensemble of 3 models vs single v4-pro: does 3-way agreement filter add enough signal to justify 3× cost?
- For Russell 1000 / mid-cap expansion, do we add a "needs human review" flag when models disagree and surface those in a curation UI?

---

## File map (paths)

```
v4/product/d1_phase_detector/
├── README.md                          (this file)
├── schema/
│   └── structtuple_schema.json        (JSON-schema draft 2020-12)
├── companies.jsonl                    (100 rows)
├── extract_structtuple.py             (single-company extractor w/ guardrail)
├── sample_run.py                      (5-company dogfood)
├── sample_structtuples.jsonl          (5 entries)
├── sample_run_stats.json              (per-call usage + latency)
└── cost_projection.md                 (measured + projected)
```

## Dependencies on existing v4 code

- `v4/lib/llm_guardrail.py` — `state_machine_fix` + `validate_json` (consumed by `extract_one`)
- `v4/scripts/b3_ensemble.py` — referenced as the prior-art DeepSeek call pattern (not imported)

## What this session deliberately did NOT do

- No Postgres schema / migration
- No FastAPI endpoints
- No Next.js UI
- No `phase.bytedance.city` deploy / nginx
- No multi-model ensemble (one model, single pass)
- No commit / no push (per session brief)
- No full 100-company batch (sample only — 5 companies)
