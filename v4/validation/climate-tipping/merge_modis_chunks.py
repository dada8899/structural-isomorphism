"""Merge per-chunk MODIS JSON files (from fetch_modis_curl.sh) into the standard
amazon_ndvi_<site>.jsonl format expected by run_validation.py.

If a site has < 100 valid records OR the subset directory is empty,
fall back to synthetic_ndvi_fallback for that site and flag synthetic=True.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUBSET_DIR = ROOT / "raw" / "modis_subset"
RAW = ROOT / "raw"

SITES = [
    ("central_amazonas", -3.0, -60.0, "Central Amazonas (intact, near Manaus)"),
    ("rondonia_arc", -10.0, -62.5, "Rondonia (degraded arc-of-deforestation)"),
    ("xingu_park", -12.0, -53.0, "Xingu (mixed park edge)"),
    ("western_acre", -9.5, -68.0, "Western Acre (intact)"),
    ("para_central", -5.5, -55.5, "Para central (transitional)"),
]


def parse_chunk(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    scale = float(data.get("scale", 0.0001))
    out = []
    for s in data.get("subset", []):
        raw_vals = s.get("data", [])
        if not raw_vals or raw_vals[0] is None:
            continue
        v = raw_vals[0]
        if v < -2000 or v > 10000:
            continue
        out.append({"date": s["calendar_date"],
                    "modis_date": s["modis_date"],
                    "ndvi": float(v) * scale})
    return out


def main() -> int:
    audit = []
    for site_id, lat, lon, descriptor in SITES:
        records: dict[str, dict] = {}
        chunk_files = sorted(SUBSET_DIR.glob(f"{site_id}_A*.json"))
        for cf in chunk_files:
            for r in parse_chunk(cf):
                records[r["modis_date"]] = r  # dedupe by modis_date
        ordered = sorted(records.values(), key=lambda r: r["date"])
        a = {"site_id": site_id, "lat": lat, "lon": lon,
             "descriptor": descriptor,
             "source": "MODIS MOD13Q1 (via curl + merge_modis_chunks.py)",
             "n_chunks_found": len(chunk_files),
             "n_records": len(ordered),
             "synthetic": False}
        if len(ordered) < 100:
            # Fall back to synthetic.
            from fetch_climate_data import synthetic_ndvi_fallback  # type: ignore
            near_tip = site_id in ("rondonia_arc", "para_central")
            syn = synthetic_ndvi_fallback(site_id, near_tip=near_tip)
            a.update({"synthetic": True, "n_records": syn["n_records"],
                      "fallback_reason": f"real_n={len(ordered)}"})
        else:
            out_path = RAW / f"amazon_ndvi_{site_id}.jsonl"
            with out_path.open("w") as f:
                for r in ordered:
                    r["site_id"] = site_id
                    r["lat"] = lat
                    r["lon"] = lon
                    f.write(json.dumps(r) + "\n")
            a["first_date"] = ordered[0]["date"]
            a["last_date"] = ordered[-1]["date"]
            a["path"] = out_path.name
        audit.append(a)
        print(f"[merge] {site_id}: {a['n_records']} records, synthetic={a['synthetic']}",
              file=sys.stderr)

    log_path = RAW / "merge_log.json"
    log_path.write_text(json.dumps({"merged_at": datetime.utcnow().isoformat() + "Z",
                                    "sites": audit}, indent=2))
    print(f"[merge] log -> {log_path.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    sys.exit(main())
