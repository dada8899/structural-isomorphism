# D1 Phase Detector — Screener API

FastAPI service exposing the StructTuple universe to the W3-C frontend.

## Endpoints

| Method | Path                       | Description                                                                     |
|--------|----------------------------|---------------------------------------------------------------------------------|
| GET    | `/health`                  | Liveness probe.                                                                 |
| GET    | `/screener`                | Filter companies by `dynamics_family`, `critical_point_state`, `universality_class`, `sector`, `min_confidence`. Pagination via `limit` (1–500). |
| GET    | `/company/{ticker}`        | Detail for one ticker. 404 if absent. Case-insensitive.                         |
| GET    | `/stats`                   | Counts: total + grouped by `dynamics_family`, `critical_point_state`, `universality_class`, `sector`. |

OpenAPI auto-docs: `/docs` (swagger) and `/redoc`.

## Quick start

```bash
# from repo root, with .venv activated and dependencies installed
PYTHONPATH=. \
  .venv/bin/uvicorn v4.product.d1_phase_detector.api.main:app --reload --port 8000
```

Then:

```bash
curl http://localhost:8000/health
curl 'http://localhost:8000/screener?dynamics_family=soc&min_confidence=0.5&limit=10'
curl http://localhost:8000/company/AAPL
curl http://localhost:8000/stats
```

## Environment

| Var      | Default                                                  | Notes                                                |
|----------|----------------------------------------------------------|------------------------------------------------------|
| `DB_URL` | `sqlite:///<api>/../d1.sqlite`                            | Use `postgresql://...` for prod. SQLite is the dev / test default. |

## Data loading

Ingest StructTuple JSONL into the DB:

```bash
# SQLite (default for dev)
.venv/bin/python v4/product/d1_phase_detector/scripts/ingest_to_postgres.py \
  v4/product/d1_phase_detector/structtuples_2026-05-13.jsonl \
  --db-url sqlite:///v4/product/d1_phase_detector/d1.sqlite

# Postgres
.venv/bin/python v4/product/d1_phase_detector/scripts/ingest_to_postgres.py \
  v4/product/d1_phase_detector/structtuples_2026-05-13.jsonl \
  --db-url postgresql://user:pass@host:5432/phase_detector
```

The ingestion script:

1. Runs the appropriate migration in `migrations/` (idempotent).
2. Enriches each record with `sector` / `market_cap` from `companies.jsonl` if available.
3. Upserts by `ticker` (`ON CONFLICT DO UPDATE`).
4. Logs `N inserted / N updated / N skipped / N errors`.

## Tests

```bash
PYTHONPATH=. .venv/bin/python -m pytest v4/product/d1_phase_detector/api/tests/ -v --override-ini="testpaths="
```

Tests use SQLite in-temp-dir fixtures, no external DB required. All 16 cases cover:
- `/health`
- `/stats` aggregation
- `/screener` filters (family / state / sector / universality_class), combos, `min_confidence`, `limit` boundaries
- `/screener` empty result
- `/company/{ticker}` hit / case-insensitive / 404
- CORS

## Production deploy (sketch — not part of this PR)

Target host: `phase.bytedance.city`.

1. Run Postgres locally on VPS (or reuse existing pgvector-ready container).
2. `DB_URL=postgresql://...` exported in systemd unit.
3. systemd unit `phase-detector-api.service` runs uvicorn on `127.0.0.1:8000`.
4. nginx reverse-proxies `phase.bytedance.city → 127.0.0.1:8000`.
5. certbot Let's Encrypt cert via nginx plugin.

## CORS

`allow_origins=["*"]` for dev. Tighten to the W3-C origin before prod.

## Schema

Postgres: `migrations/0001_companies_structtuples.sql`
SQLite fallback: `migrations/0001_companies_structtuples_sqlite.sql` (mirrors columns; JSON stored as TEXT).

Columns:

| col                       | type            | notes                                                |
|---------------------------|-----------------|------------------------------------------------------|
| ticker                    | TEXT PRIMARY KEY |                                                      |
| name                      | TEXT NOT NULL    |                                                      |
| sector, industry          | TEXT             | from companies.jsonl                                 |
| market_cap_usd_b          | NUMERIC          |                                                      |
| dynamics_family           | TEXT NOT NULL    | indexed                                              |
| critical_point_state      | TEXT NOT NULL    | indexed                                              |
| universality_class        | TEXT             | indexed                                              |
| extraction_confidence     | NUMERIC          | 0–1                                                  |
| extraction_model          | TEXT             |                                                      |
| extracted_at              | TIMESTAMPTZ      | required                                             |
| tldr                      | TEXT             | aka structural_summary                               |
| primary_indicators        | JSONB / TEXT     | aka early_warning_indicators                         |
| caveats                   | TEXT             |                                                      |
| raw_response              | JSONB / TEXT     | full StructTuple for downstream                      |
