"""
Phase Detector · Structural Screener backend
---------------------------------------------

Precomputes StructTuples for top N companies and exposes query endpoints:

  GET /phase/api/screen?dynamics=DDE_delayed_feedback&phase=approaching_critical
  GET /phase/api/screen/similar?to=NFLX&top_k=20
  GET /phase/api/company/{ticker}
  GET /phase/api/dynamics           — list all known dynamics families with counts
  GET /phase/api/samples            — list 10 curated sample reports

Designed to be mounted as a sub-app in the existing structural beta site.

Data model
----------
companies_struct.jsonl (one line per company):
{
  "ticker": "NFLX",
  "name": "Netflix",
  "domain": "streaming_media",
  "market_cap": 280_000_000_000,
  "exchange": "NASDAQ",
  "updated_at": "2026-04-15",
  "struct": {
    "state_vars": [...],
    "dynamics_family": "ODE1_saturating",
    "feedback_topology": "positive_loop",
    "boundary_behavior": "saturation",
    "timescale_log10_s": 9,
    "canonical_equation": "dN/dt = r*N*(1 - N/K)",
    "invariants": ["number_conservation"],
    "critical_points": ["global_carrying_capacity ~ 1.5B households"],
    "confidence": 0.85
  },
  "phase_state": "approaching_saturation",  // stable | approaching_critical | post_transition | unstable
  "note": "derived_from_financials_2015_2025"
}
"""
from pathlib import Path
from typing import Dict, List, Optional
from collections import Counter
import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/phase/api", tags=["phase"])

PHASE_DIR = Path(__file__).resolve().parent.parent  # phase/
DATA_DIR = PHASE_DIR / "data"
SAMPLES_DIR = PHASE_DIR / "samples"


# --- Data loaders (module-level cache, loaded once at startup) ---
_companies_cache: Optional[List[Dict]] = None


def load_companies() -> List[Dict]:
    global _companies_cache
    if _companies_cache is not None:
        return _companies_cache
    path = DATA_DIR / "companies_struct.jsonl"
    out: List[Dict] = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    _companies_cache = out
    return out


def companies_by_ticker() -> Dict[str, Dict]:
    return {c["ticker"]: c for c in load_companies() if c.get("ticker")}


# --- Pydantic response schemas ---
class CompanyListResponse(BaseModel):
    count: int
    results: List[Dict]


class DynamicsStatsResponse(BaseModel):
    total: int
    families: List[Dict]
    phase_states: Dict[str, int]


class SampleReport(BaseModel):
    slug: str
    ticker: str
    name: str
    dynamics_family: str
    has_report: bool


# --- Endpoints ---
@router.get("/screen")
async def screen(
    dynamics: Optional[str] = Query(None, description="Filter by dynamics_family (enum)"),
    phase: Optional[str] = Query(None, description="Filter by phase state"),
    feedback: Optional[str] = Query(None, description="Filter by feedback_topology"),
    boundary: Optional[str] = Query(None, description="Filter by boundary_behavior"),
    min_market_cap: Optional[float] = Query(None, description="Minimum market cap (USD)"),
    exchange: Optional[str] = Query(None, description="Filter by exchange"),
    limit: int = Query(100, ge=1, le=500),
) -> CompanyListResponse:
    """
    Filter the precomputed company universe by any combination of structural
    and metadata filters. All filters are AND-combined.

    Example queries
    ---------------
      /phase/api/screen?dynamics=DDE_delayed_feedback
      /phase/api/screen?phase=approaching_critical&min_market_cap=10000000000
      /phase/api/screen?feedback=positive_loop&exchange=NASDAQ
    """
    companies = load_companies()
    if not companies:
        return CompanyListResponse(count=0, results=[])

    def match(c: Dict) -> bool:
        s = c.get("struct", {})
        if dynamics and s.get("dynamics_family") != dynamics:
            return False
        if phase and c.get("phase_state") != phase:
            return False
        if feedback and s.get("feedback_topology") != feedback:
            return False
        if boundary and s.get("boundary_behavior") != boundary:
            return False
        if min_market_cap is not None and (c.get("market_cap") or 0) < min_market_cap:
            return False
        if exchange and c.get("exchange") != exchange:
            return False
        return True

    matched = [c for c in companies if match(c)]
    return CompanyListResponse(count=len(matched), results=matched[:limit])


@router.get("/screen/similar")
async def screen_similar(
    to: str = Query(..., description="Reference ticker"),
    top_k: int = Query(20, ge=1, le=100),
) -> CompanyListResponse:
    """
    Find companies structurally similar to the given ticker. Uses field-level
    match on dynamics_family first, then feedback_topology, then boundary_behavior.
    Scored on how many fields match (0-4).
    """
    by_t = companies_by_ticker()
    if to not in by_t:
        raise HTTPException(404, f"ticker {to!r} not in precomputed universe")
    ref = by_t[to]
    ref_s = ref.get("struct", {})

    def score(c: Dict) -> float:
        if c["ticker"] == to:
            return -1.0
        s = c.get("struct", {})
        score = 0
        weights = {"dynamics_family": 2.0, "feedback_topology": 1.0,
                   "boundary_behavior": 1.0, "phase_state": 0.5}
        if s.get("dynamics_family") == ref_s.get("dynamics_family"):
            score += weights["dynamics_family"]
        if s.get("feedback_topology") == ref_s.get("feedback_topology"):
            score += weights["feedback_topology"]
        if s.get("boundary_behavior") == ref_s.get("boundary_behavior"):
            score += weights["boundary_behavior"]
        if c.get("phase_state") == ref.get("phase_state"):
            score += weights["phase_state"]
        # Small bonus for similar timescale
        ts_a = s.get("timescale_log10_s")
        ts_b = ref_s.get("timescale_log10_s")
        if ts_a is not None and ts_b is not None:
            score += max(0, 0.5 - 0.1 * abs(ts_a - ts_b))
        return score

    scored = [(score(c), c) for c in load_companies()]
    scored = [(s, c) for s, c in scored if s > 0]
    scored.sort(key=lambda x: -x[0])

    top = []
    for s, c in scored[:top_k]:
        c_copy = dict(c)
        c_copy["similarity_score"] = round(s, 2)
        top.append(c_copy)

    return CompanyListResponse(count=len(top), results=top)


@router.get("/company/{ticker}")
async def get_company(ticker: str):
    by_t = companies_by_ticker()
    if ticker not in by_t:
        raise HTTPException(404, f"ticker {ticker!r} not in precomputed universe")
    return by_t[ticker]


@router.get("/dynamics")
async def dynamics_stats() -> DynamicsStatsResponse:
    """List all observed dynamics_family values in the universe with counts."""
    companies = load_companies()
    families = Counter()
    phases = Counter()
    for c in companies:
        df = c.get("struct", {}).get("dynamics_family", "Unknown")
        families[df] += 1
        ph = c.get("phase_state", "unknown")
        phases[ph] += 1

    return DynamicsStatsResponse(
        total=len(companies),
        families=[{"family": k, "count": v} for k, v in families.most_common()],
        phase_states=dict(phases),
    )


@router.get("/samples")
async def list_samples() -> List[SampleReport]:
    """List available Day 1 sample reports (static files under phase/samples/)."""
    manifest_path = DATA_DIR / "samples_manifest.json"
    if not manifest_path.exists():
        return []
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    out: List[SampleReport] = []
    for entry in manifest:
        slug = entry.get("slug", "")
        report_path = SAMPLES_DIR / f"{slug}.md"
        out.append(SampleReport(
            slug=slug,
            ticker=entry.get("ticker", ""),
            name=entry.get("name", ""),
            dynamics_family=entry.get("dynamics_family", ""),
            has_report=report_path.exists(),
        ))
    return out


@router.get("/health")
async def health():
    """Quick check of data availability."""
    companies = load_companies()
    return {
        "status": "ok",
        "companies_loaded": len(companies),
        "samples_available": len(list(SAMPLES_DIR.glob("*.md"))) if SAMPLES_DIR.exists() else 0,
    }
