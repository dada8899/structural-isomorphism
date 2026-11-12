"""Ingest StructTuple JSONL records into a database (Postgres or SQLite).

Usage:
    python ingest_to_postgres.py <jsonl> [--db-url URL] [--companies-jsonl PATH]

Defaults:
    --db-url            postgresql://localhost:5432/phase_detector
    --companies-jsonl   <v4/product/d1_phase_detector/companies.jsonl>  (used to enrich
                        sector / market_cap; skipped if missing)

SQLite fallback:
    --db-url sqlite:///path/to/d1.sqlite

The script:
1. Connects to the DB
2. Runs the migration (idempotent)
3. Reads JSONL; for each record extracts struct_tuple + provenance, upserts
4. Prints summary: inserted / updated / errors / skipped
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingest")

DEFAULT_DB_URL = "postgresql://localhost:5432/phase_detector"
THIS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = THIS_DIR.parent  # v4/product/d1_phase_detector
MIGRATIONS_DIR = PROJECT_DIR / "migrations"


def parse_db_url(url: str) -> dict[str, Any]:
    """Return {'driver': 'sqlite'|'postgres', 'path': str}."""
    if url.startswith("sqlite:///"):
        return {"driver": "sqlite", "path": url[len("sqlite:///") :]}
    if url.startswith(("postgres://", "postgresql://")):
        return {"driver": "postgres", "path": url}
    raise ValueError(f"Unsupported db url: {url}")


def open_connection(parsed: dict[str, Any]):
    """Return (conn, driver_name). Caller responsible for close()."""
    if parsed["driver"] == "sqlite":
        import sqlite3

        # ensure parent dir exists
        Path(parsed["path"]).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(parsed["path"])
        conn.execute("PRAGMA foreign_keys=ON")
        return conn, "sqlite"
    elif parsed["driver"] == "postgres":
        try:
            import psycopg2  # type: ignore
        except ImportError as exc:
            raise SystemExit(
                "psycopg2 not installed. Either `pip install psycopg2-binary` "
                "or use --db-url sqlite:///path.sqlite"
            ) from exc
        conn = psycopg2.connect(parsed["path"])
        return conn, "postgres"
    else:
        raise ValueError(f"Unknown driver: {parsed['driver']}")


def run_migration(conn, driver: str) -> None:
    """Run 0001 migration appropriate for the driver."""
    if driver == "sqlite":
        path = MIGRATIONS_DIR / "0001_companies_structtuples_sqlite.sql"
    else:
        path = MIGRATIONS_DIR / "0001_companies_structtuples.sql"
    sql = path.read_text()
    cur = conn.cursor()
    if driver == "sqlite":
        cur.executescript(sql)
    else:
        cur.execute(sql)
    conn.commit()
    log.info("Migration applied: %s", path.name)


def load_companies_lookup(path: Path | None) -> dict[str, dict[str, Any]]:
    """Build a {ticker: {sector, industry, market_cap_usd_b}} lookup from companies.jsonl."""
    if not path or not path.exists():
        log.warning("companies.jsonl not found at %s; sector/cap will be None", path)
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ticker = row.get("ticker")
        if not ticker:
            continue
        lookup[ticker] = {
            "sector": row.get("sector"),
            "industry": row.get("industry"),
            "market_cap_usd_b": row.get("market_cap_bn_usd") or row.get("market_cap_usd_b"),
        }
    log.info("Loaded %d company metadata rows from companies.jsonl", len(lookup))
    return lookup


def extract_row(record: dict[str, Any], company_lookup: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Flatten a JSONL record into a d1_companies row dict. Return None if invalid."""
    if not record.get("ok"):
        return None
    st = record.get("struct_tuple")
    if not st:
        return None
    ticker = st.get("ticker")
    if not ticker:
        return None

    meta = company_lookup.get(ticker, {})

    indicators = st.get("early_warning_indicators") or st.get("primary_indicators")
    evidence = st.get("evidence_anchors")
    caveats = st.get("caveats")
    if not caveats and evidence:
        # surface the first evidence anchor 'fact' as a faint caveat fallback
        caveats = None

    extracted_at_str = st.get("as_of_date") or st.get("extracted_at")
    if extracted_at_str:
        # accept either YYYY-MM-DD or full ISO
        try:
            if len(extracted_at_str) == 10:
                extracted_at = datetime.strptime(extracted_at_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            else:
                extracted_at = datetime.fromisoformat(extracted_at_str.replace("Z", "+00:00"))
        except ValueError:
            extracted_at = datetime.now(timezone.utc)
    else:
        extracted_at = datetime.now(timezone.utc)

    return {
        "ticker": ticker,
        "name": st.get("company_name") or ticker,
        "sector": meta.get("sector"),
        "industry": meta.get("industry"),
        "market_cap_usd_b": meta.get("market_cap_usd_b"),
        "dynamics_family": st.get("dynamics_family") or "unknown",
        "critical_point_state": st.get("critical_point_state") or "unknown",
        "universality_class": st.get("universality_class"),
        "extraction_confidence": st.get("confidence"),
        "extraction_model": record.get("model") or record.get("usage", {}).get("model"),
        "extracted_at": extracted_at,
        "tldr": st.get("structural_summary") or st.get("tldr"),
        "primary_indicators": indicators,
        "caveats": caveats,
        "raw_response": st,
    }


UPSERT_PG = """
INSERT INTO d1_companies (
    ticker, name, sector, industry, market_cap_usd_b,
    dynamics_family, critical_point_state, universality_class,
    extraction_confidence, extraction_model, extracted_at,
    tldr, primary_indicators, caveats, raw_response
) VALUES (
    %(ticker)s, %(name)s, %(sector)s, %(industry)s, %(market_cap_usd_b)s,
    %(dynamics_family)s, %(critical_point_state)s, %(universality_class)s,
    %(extraction_confidence)s, %(extraction_model)s, %(extracted_at)s,
    %(tldr)s, %(primary_indicators)s, %(caveats)s, %(raw_response)s
)
ON CONFLICT (ticker) DO UPDATE SET
    name = EXCLUDED.name,
    sector = EXCLUDED.sector,
    industry = EXCLUDED.industry,
    market_cap_usd_b = EXCLUDED.market_cap_usd_b,
    dynamics_family = EXCLUDED.dynamics_family,
    critical_point_state = EXCLUDED.critical_point_state,
    universality_class = EXCLUDED.universality_class,
    extraction_confidence = EXCLUDED.extraction_confidence,
    extraction_model = EXCLUDED.extraction_model,
    extracted_at = EXCLUDED.extracted_at,
    tldr = EXCLUDED.tldr,
    primary_indicators = EXCLUDED.primary_indicators,
    caveats = EXCLUDED.caveats,
    raw_response = EXCLUDED.raw_response
RETURNING (xmax = 0) AS inserted
"""

UPSERT_SQLITE = """
INSERT INTO d1_companies (
    ticker, name, sector, industry, market_cap_usd_b,
    dynamics_family, critical_point_state, universality_class,
    extraction_confidence, extraction_model, extracted_at,
    tldr, primary_indicators, caveats, raw_response
) VALUES (
    :ticker, :name, :sector, :industry, :market_cap_usd_b,
    :dynamics_family, :critical_point_state, :universality_class,
    :extraction_confidence, :extraction_model, :extracted_at,
    :tldr, :primary_indicators, :caveats, :raw_response
)
ON CONFLICT(ticker) DO UPDATE SET
    name = excluded.name,
    sector = excluded.sector,
    industry = excluded.industry,
    market_cap_usd_b = excluded.market_cap_usd_b,
    dynamics_family = excluded.dynamics_family,
    critical_point_state = excluded.critical_point_state,
    universality_class = excluded.universality_class,
    extraction_confidence = excluded.extraction_confidence,
    extraction_model = excluded.extraction_model,
    extracted_at = excluded.extracted_at,
    tldr = excluded.tldr,
    primary_indicators = excluded.primary_indicators,
    caveats = excluded.caveats,
    raw_response = excluded.raw_response
"""


def upsert_row(conn, driver: str, row: dict[str, Any]) -> str:
    """Return 'inserted' or 'updated'."""
    cur = conn.cursor()
    if driver == "postgres":
        params = dict(row)
        params["primary_indicators"] = json.dumps(row["primary_indicators"]) if row["primary_indicators"] is not None else None
        params["raw_response"] = json.dumps(row["raw_response"]) if row["raw_response"] is not None else None
        cur.execute(UPSERT_PG, params)
        inserted = cur.fetchone()[0]
        return "inserted" if inserted else "updated"
    else:
        # sqlite: encode JSON fields as text; check existence first to count properly
        cur.execute("SELECT 1 FROM d1_companies WHERE ticker = ?", (row["ticker"],))
        existed = cur.fetchone() is not None
        params = dict(row)
        params["extracted_at"] = row["extracted_at"].isoformat()
        params["primary_indicators"] = json.dumps(row["primary_indicators"]) if row["primary_indicators"] is not None else None
        params["raw_response"] = json.dumps(row["raw_response"]) if row["raw_response"] is not None else None
        cur.execute(UPSERT_SQLITE, params)
        return "updated" if existed else "inserted"


def ingest(jsonl_path: Path, db_url: str, companies_path: Path | None) -> dict[str, int]:
    parsed = parse_db_url(db_url)
    conn, driver = open_connection(parsed)
    try:
        run_migration(conn, driver)
        lookup = load_companies_lookup(companies_path)

        counts = {"inserted": 0, "updated": 0, "errors": 0, "skipped": 0}
        with jsonl_path.open() as fp:
            for lineno, line in enumerate(fp, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    log.error("L%d: JSON parse error: %s", lineno, exc)
                    counts["errors"] += 1
                    continue
                row = extract_row(rec, lookup)
                if row is None:
                    counts["skipped"] += 1
                    continue
                try:
                    result = upsert_row(conn, driver, row)
                    counts[result] += 1
                except Exception as exc:  # noqa: BLE001
                    log.error("L%d ticker=%s upsert failed: %s", lineno, row.get("ticker"), exc)
                    counts["errors"] += 1
        conn.commit()
        log.info(
            "Ingestion complete: %d inserted / %d updated / %d skipped / %d errors",
            counts["inserted"], counts["updated"], counts["skipped"], counts["errors"],
        )
        return counts
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Ingest StructTuple JSONL into DB")
    p.add_argument("jsonl", help="Path to structtuples_*.jsonl")
    p.add_argument("--db-url", default=DEFAULT_DB_URL, help=f"DB URL (default: {DEFAULT_DB_URL})")
    p.add_argument(
        "--companies-jsonl",
        default=str(PROJECT_DIR / "companies.jsonl"),
        help="Path to companies.jsonl for sector/cap enrichment (optional)",
    )
    args = p.parse_args(argv)

    jsonl_path = Path(args.jsonl)
    if not jsonl_path.exists():
        log.error("JSONL file not found: %s", jsonl_path)
        return 2

    companies_path = Path(args.companies_jsonl) if args.companies_jsonl else None
    counts = ingest(jsonl_path, args.db_url, companies_path)
    return 0 if counts["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
