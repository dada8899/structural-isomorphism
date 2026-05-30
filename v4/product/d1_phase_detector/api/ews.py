"""EWS (Early-Warning-Signal) HTTP router.

Reads the JSON artifacts produced by `run_ews_pipeline.py` and serves them
behind versioned `/api/ews/*` paths.

Design choices
==============
* In-memory cache loaded on first request and re-loaded if the file
  mtime changes. This means cron updates to ews_results.json are picked
  up without a restart.
* No DB. The EWS dataset is at most ~600 tickers × 252 days; even with
  HK + bench expansion it fits comfortably in RAM (<20 MB), and a flat
  JSON file is easier to swap atomically than a Postgres migration.
* All endpoints degrade gracefully when the file is missing — returning
  empty payloads with `provenance="missing"` so the frontend can show an
  honest "data refreshing" state instead of a 500.

Endpoints
---------
GET  /api/ews/meta
GET  /api/ews/leaderboard?market=US|HK|ALL&phase=...&limit=...
GET  /api/ews/{ticker}
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

LOG = logging.getLogger("ews_router")
router = APIRouter(prefix="/api/ews", tags=["ews"])

# Resolve data files relative to this file (api/ews.py -> ../data/)
_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.abspath(os.path.join(_HERE, "..", "data"))
_RESULTS_PATH = os.environ.get("EWS_RESULTS_PATH",
                               os.path.join(_DATA_DIR, "ews_results.json"))
_LEADERBOARD_PATH = os.environ.get("EWS_LEADERBOARD_PATH",
                                   os.path.join(_DATA_DIR, "ews_leaderboard.json"))
_META_PATH = os.environ.get("EWS_META_PATH",
                            os.path.join(_DATA_DIR, "ews_meta.json"))

_CACHE: Dict[str, Any] = {
    "results": None,           # dict[ticker, full EWS dict]
    "leaderboard": None,       # list[card dict]
    "meta": None,              # dict
    "results_mtime": 0.0,
    "leaderboard_mtime": 0.0,
    "meta_mtime": 0.0,
}
_LOCK = threading.Lock()


def _load_if_stale(path: str, key: str) -> Any:
    """Load JSON from path into cache if file mtime changed. Returns the
    cached value (possibly None if file missing)."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        with _LOCK:
            _CACHE[key] = None
            _CACHE[f"{key}_mtime"] = 0.0
        return None
    with _LOCK:
        if _CACHE[key] is not None and _CACHE[f"{key}_mtime"] >= mtime:
            return _CACHE[key]
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        LOG.warning("EWS %s load failed: %s", path, exc)
        return None
    with _LOCK:
        _CACHE[key] = obj
        _CACHE[f"{key}_mtime"] = mtime
    LOG.info("Loaded EWS %s (%d bytes mtime %s)", path,
             os.path.getsize(path), mtime)
    return obj


def _results() -> Dict[str, dict]:
    return _load_if_stale(_RESULTS_PATH, "results") or {}


def _leaderboard() -> List[dict]:
    lb = _load_if_stale(_LEADERBOARD_PATH, "leaderboard")
    return lb if isinstance(lb, list) else []


def _meta() -> dict:
    m = _load_if_stale(_META_PATH, "meta")
    return m if isinstance(m, dict) else {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/meta")
def get_meta() -> dict:
    """Run provenance + counts. UI shows the as-of timestamp and
    `price_provenance` so users know whether they're seeing real or demo
    data."""
    m = dict(_meta())
    if not m:
        return {
            "version": "0.0.0",
            "n_tickers": 0,
            "price_provenance": "missing",
            "msg": "EWS pipeline has not produced data yet.",
        }
    # add cache-friendliness — frontend can ISR on this
    m.setdefault("price_provenance", "unknown")
    return m


@router.get("/leaderboard")
def get_leaderboard(
    market: str = Query("ALL", pattern="^(ALL|US|HK)$"),
    phase: Optional[str] = Query(
        None,
        pattern="^(far_from_critical|approaching_critical|at_critical|"
              "post_critical_transition|unknown)$",
    ),
    sector: Optional[str] = Query(None),
    min_score: float = Query(0.0, ge=0.0, le=100.0),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=600),
) -> list[dict]:
    """Ranked EWS cards. Filters compose; default returns top 50 across
    both markets ordered by phase-state then score."""
    lb = _leaderboard()
    if not lb:
        return []
    out: List[dict] = []
    for r in lb:
        if market != "ALL" and r.get("market") != market:
            continue
        if phase and r.get("phase_state") != phase:
            continue
        if sector and r.get("sector") != sector:
            continue
        if (r.get("criticality_score") or 0.0) < min_score:
            continue
        if (r.get("confidence") or 0.0) < min_confidence:
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


@router.get("/{ticker}")
def get_ticker(ticker: str) -> dict:
    """Full per-ticker EWS detail incl. trailing 252d ar1/var time series.

    404 when the ticker is not in the universe; the UI should fall back
    to the leaderboard-card path for tickers that haven't been ingested."""
    results = _results()
    if not results:
        raise HTTPException(
            status_code=503,
            detail="EWS data not yet available; pipeline pending first run.",
        )
    t = ticker.upper()
    # tolerate users typing without .HK suffix when only HK form exists
    if t not in results and f"{t}.HK" in results:
        t = f"{t}.HK"
    if t not in results:
        raise HTTPException(status_code=404, detail=f"ticker {ticker} not in EWS universe")
    return results[t]
