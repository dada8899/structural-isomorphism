"""
fetch_climate_data.py - Real climate-tipping data fetchers (Amazon NDVI + AMOC).

Two systems:
  1. AMOC RAPID 26 N array: overturning transport (Sv), 12-hourly 2004 - now.
     URL: https://rapid.ac.uk/sites/default/files/rapid_data/moc_transports.nc
     Variable: moc_mar_hc10 (overturning transport, Sv).
     NetCDF (HDF5) - parsed with h5py.

  2. Amazon NDVI: MODIS MOD13Q1 250m 16-day NDVI via NASA ORNL DAAC REST API.
     URL: https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset
     We fetch single-pixel time series at 3-5 sites across the Amazon basin
     2000-02-18 onwards (start of MOD13Q1) -> 24+ years of 16-day samples.

Output:
  raw/moc_transports.nc                (binary, may already exist)
  raw/amoc_timeseries.jsonl            (date, moc_sv)
  raw/amazon_ndvi_<site>.jsonl         (date, ndvi)
  raw/fetch_log.json                   (audit trail per source)

Honesty rule: if a real source fails for any site, write SYNTHETIC fallback
samples + log it explicitly. Never claim real where it isn't.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(parents=True, exist_ok=True)

UA = "structural-isomorphism-v4/climate-tipping (research; contact: github.com/dada8899)"

# ---------------------------------------------------------------------------
# 1. AMOC RAPID 26N
# ---------------------------------------------------------------------------
AMOC_URL = "https://rapid.ac.uk/sites/default/files/rapid_data/moc_transports.nc"
AMOC_NC = RAW / "moc_transports.nc"
AMOC_JSONL = RAW / "amoc_timeseries.jsonl"


def fetch_amoc() -> dict:
    """Download MOC transports NetCDF and extract moc_mar_hc10 time series.

    Returns audit dict. Uses h5py (NetCDF4 = HDF5).
    """
    audit = {"source": "RAPID 26N", "url": AMOC_URL, "ok": False,
             "synthetic": False, "n_records": 0, "error": None}
    try:
        if not AMOC_NC.exists():
            req = urllib.request.Request(AMOC_URL, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as resp:
                AMOC_NC.write_bytes(resp.read())
        audit["bytes_on_disk"] = AMOC_NC.stat().st_size
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        audit["error"] = f"{type(exc).__name__}: {exc}"

    try:
        import h5py  # noqa: F401
    except ImportError:
        audit["error"] = (audit["error"] or "") + " | h5py not available; cannot parse NetCDF4"
        # Fall back to synthetic AMOC.
        return _synthetic_amoc(audit)

    try:
        import h5py
        import numpy as np
        with h5py.File(AMOC_NC, "r") as f:
            t_days = f["time"][:]
            moc = f["moc_mar_hc10"][:]
        # time is "days since 2004-04-01"
        base = datetime(2004, 4, 1)
        # mask fill values
        valid = moc > -9000
        moc = moc[valid]
        t_days = t_days[valid]
        records = []
        for d, v in zip(t_days, moc):
            dt = base + timedelta(days=float(d))
            records.append({"date": dt.strftime("%Y-%m-%dT%H:%M"),
                            "moc_sv": float(v)})
        with AMOC_JSONL.open("w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        audit["ok"] = True
        audit["n_records"] = len(records)
        audit["first_date"] = records[0]["date"]
        audit["last_date"] = records[-1]["date"]
    except Exception as exc:  # pylint: disable=broad-except
        audit["error"] = f"parse: {type(exc).__name__}: {exc}"
        return _synthetic_amoc(audit)
    return audit


def _synthetic_amoc(audit: dict) -> dict:
    """Synthetic AMOC: slow secular decline + noise + a fold-like late drop.

    Marked [SYNTHETIC] so downstream verdict knows not to claim real.
    """
    import numpy as np
    rng = np.random.default_rng(0)
    n = 20 * 365  # 20 yr daily
    t = np.arange(n)
    base = 17.0  # mean MOC ~17 Sv
    # slow secular decline -2 Sv over 20 yr
    drift = -2.0 * t / n
    # red noise
    rho = 0.9
    noise = np.zeros(n)
    for i in range(1, n):
        noise[i] = rho * noise[i - 1] + rng.normal(0, 0.6)
    sig = base + drift + noise
    # add a fold-induced increase in variance late in the series
    sig[int(n * 0.7):] += rng.normal(0, 1.0, n - int(n * 0.7))
    start = datetime(2004, 4, 1)
    records = []
    for i, v in enumerate(sig):
        records.append({"date": (start + timedelta(days=i)).strftime("%Y-%m-%dT%H:%M"),
                        "moc_sv": float(v),
                        "synthetic": True})
    with AMOC_JSONL.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    audit["synthetic"] = True
    audit["ok"] = True
    audit["n_records"] = len(records)
    audit["first_date"] = records[0]["date"]
    audit["last_date"] = records[-1]["date"]
    return audit


# ---------------------------------------------------------------------------
# 2. Amazon NDVI via MODIS ORNL DAAC REST
# ---------------------------------------------------------------------------
MODIS_BASE = "https://modis.ornl.gov/rst/api/v1/MOD13Q1"
# Three intact-forest sites + one degraded "arc-of-deforestation" site.
# Locations chosen from Lenton 2023 Earth System Dynamics + Brando 2019 PNAS.
SITES = [
    ("central_amazonas", -3.0, -60.0, "Central Amazonas (intact, near Manaus)"),
    ("rondonia_arc", -10.0, -62.5, "Rondonia (degraded arc-of-deforestation)"),
    ("xingu_park", -12.0, -53.0, "Xingu (mixed park edge)"),
    ("western_acre", -9.5, -68.0, "Western Acre (intact)"),
    ("para_central", -5.5, -55.5, "Para central (transitional)"),
]

# MODIS REST allows up to 10 16-day tiles per request -> ~160 days. Use 9 to
# leave headroom.
TILES_PER_REQ = 9
DAYS_PER_TILE = 16


def _modis_dates_in_range(lat: float, lon: float, start: int = 2000, end: int = 2024,
                          attempts: int = 5) -> list[str]:
    """Get all valid MODIS date codes for a site in [start, end] inclusive.

    Retries on 5xx with exponential backoff (10, 20, 40, 80 sec).
    """
    url = f"{MODIS_BASE}/dates?latitude={lat}&longitude={lon}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last_err = None
    for k in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read())
            out = []
            for d in data.get("dates", []):
                yr = int(d["calendar_date"][:4])
                if start <= yr <= end:
                    out.append(d["modis_date"])
            return out
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (429, 500, 502, 503, 504):
                wait = 10 * (2 ** k)
                print(f"[ndvi]    dates HTTP {exc.code} -> sleep {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = exc
            time.sleep(10 * (2 ** k))
    raise last_err


def _modis_subset(lat: float, lon: float, start_code: str, end_code: str) -> list[dict]:
    """One subset request returning list of {modis_date, calendar_date, ndvi}."""
    url = (f"{MODIS_BASE}/subset?latitude={lat}&longitude={lon}"
           f"&startDate={start_code}&endDate={end_code}"
           f"&kmAboveBelow=0&kmLeftRight=0&band=250m_16_days_NDVI")
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read())
    scale = float(data.get("scale", 0.0001))
    out = []
    for s in data.get("subset", []):
        raw_vals = s.get("data", [])
        if not raw_vals or raw_vals[0] is None:
            continue
        v = raw_vals[0]
        # MODIS fill -3000 or -1; valid NDVI ~ [-2000, 10000]
        if v < -2000 or v > 10000:
            continue
        out.append({"date": s["calendar_date"],
                    "modis_date": s["modis_date"],
                    "ndvi": float(v) * scale})
    return out


def _modis_subset_retry(lat: float, lon: float, start_code: str,
                        end_code: str, attempts: int = 5) -> list[dict]:
    """Subset with exponential backoff on 5xx / transient errors.

    Backoff schedule: 5, 10, 20, 40, 80 sec.
    """
    last_err = None
    for k in range(attempts):
        try:
            return _modis_subset(lat, lon, start_code, end_code)
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (429, 500, 502, 503, 504):
                time.sleep(5 * (2 ** k))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = exc
            time.sleep(5 * (2 ** k))
    if last_err:
        raise last_err
    return []


def fetch_amazon_ndvi() -> list[dict]:
    """Fetch NDVI for each SITE; write per-site JSONL; return audits."""
    audits = []
    for site_id, lat, lon, descriptor in SITES:
        audit = {"source": "MODIS MOD13Q1", "site_id": site_id,
                 "lat": lat, "lon": lon, "descriptor": descriptor,
                 "ok": False, "synthetic": False, "n_records": 0, "error": None,
                 "n_chunks_ok": 0, "n_chunks_failed": 0}
        try:
            dates = _modis_dates_in_range(lat, lon, 2000, 2024)
            print(f"[ndvi]  {site_id}: {len(dates)} candidate dates", file=sys.stderr)
            records = []
            errors = []
            for i in range(0, len(dates), TILES_PER_REQ):
                chunk = dates[i:i + TILES_PER_REQ]
                start_code, end_code = chunk[0], chunk[-1]
                try:
                    sub = _modis_subset_retry(lat, lon, start_code, end_code)
                    records.extend(sub)
                    audit["n_chunks_ok"] += 1
                except Exception as exc:  # pylint: disable=broad-except
                    audit["n_chunks_failed"] += 1
                    errors.append(f"{start_code}-{end_code}: {type(exc).__name__}: {exc}")
                    print(f"[ndvi]    chunk {start_code}-{end_code} failed: {exc}",
                          file=sys.stderr)
                time.sleep(1.2)  # rate-limit politeness
            if errors:
                audit["error"] = "; ".join(errors[:3]) + (f"... +{len(errors)-3} more" if len(errors) > 3 else "")
            if len(records) >= 100:
                path = RAW / f"amazon_ndvi_{site_id}.jsonl"
                with path.open("w") as f:
                    for r in records:
                        r["site_id"] = site_id
                        r["lat"] = lat
                        r["lon"] = lon
                        f.write(json.dumps(r) + "\n")
                audit["ok"] = True
                audit["n_records"] = len(records)
                audit["first_date"] = records[0]["date"]
                audit["last_date"] = records[-1]["date"]
                audit["path"] = path.name
            else:
                audit["error"] = f"insufficient real data (n={len(records)})"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
            audit["error"] = f"{type(exc).__name__}: {exc}"
        audits.append(audit)
    return audits


def synthetic_ndvi_fallback(site_id: str, near_tip: bool = False) -> dict:
    """Synthetic NDVI: stable ~0.85 mean, optional pre-tip variance rise."""
    import numpy as np
    rng = np.random.default_rng(hash(site_id) & 0xffff)
    n = 24 * 23  # 24 yr * 23 16-day samples
    t = np.arange(n)
    seasonal = 0.06 * np.sin(2 * np.pi * t / 23.0)
    base = 0.85 + seasonal
    rho = 0.6
    eps = np.zeros(n)
    for i in range(1, n):
        eps[i] = rho * eps[i - 1] + rng.normal(0, 0.025)
    if near_tip:
        # variance + AR(1) rise in last 30%
        n_tail = int(n * 0.3)
        amp = np.linspace(1.0, 3.0, n_tail)
        eps[-n_tail:] *= amp
        base[-n_tail:] -= np.linspace(0, 0.08, n_tail)  # slow drift down
    ndvi = base + eps
    start = datetime(2000, 2, 18)
    records = []
    for i, v in enumerate(ndvi):
        d = start + timedelta(days=i * 16)
        records.append({
            "date": d.strftime("%Y-%m-%d"),
            "site_id": site_id,
            "ndvi": float(v),
            "synthetic": True,
            "near_tip": near_tip,
        })
    path = RAW / f"amazon_ndvi_{site_id}.jsonl"
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return {"site_id": site_id, "synthetic": True, "ok": True,
            "n_records": len(records), "path": path.name}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    log = {"started_at": datetime.utcnow().isoformat() + "Z",
           "amoc": None, "ndvi": []}

    print("[fetch] === AMOC RAPID 26N ===", file=sys.stderr)
    log["amoc"] = fetch_amoc()
    print(f"[fetch] AMOC ok={log['amoc']['ok']} n={log['amoc']['n_records']} "
          f"synthetic={log['amoc']['synthetic']}", file=sys.stderr)

    print("[fetch] === Amazon NDVI ===", file=sys.stderr)
    log["ndvi"] = fetch_amazon_ndvi()
    # Synthetic fallback ONLY for sites that genuinely failed.
    for a in log["ndvi"]:
        if not a["ok"]:
            print(f"[fetch] NDVI {a['site_id']} fell back to SYNTHETIC", file=sys.stderr)
            near_tip = a["site_id"] in ("rondonia_arc", "para_central")
            syn = synthetic_ndvi_fallback(a["site_id"], near_tip=near_tip)
            a.update(syn)
    log["finished_at"] = datetime.utcnow().isoformat() + "Z"
    (RAW / "fetch_log.json").write_text(json.dumps(log, indent=2))
    print("[fetch] log -> raw/fetch_log.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
