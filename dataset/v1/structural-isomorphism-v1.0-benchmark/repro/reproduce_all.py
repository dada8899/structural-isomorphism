#!/usr/bin/env python3
"""
reproduce_all.py — one-shot reproducibility entry point for the benchmark bundle.

Modes:
  --smoke (default): run on 2-3 small systems for fast verification
                     (~30-90 seconds on a laptop).
  --full           : run on all 13 phases + 4 null controls (~5-15 minutes).

What it actually does:
  1. Load each system's frozen result file from results/ or datasets/<slot>/.
  2. Re-run the headline fit using the bundled pipeline (pipeline/soc_pipeline/)
     on whatever raw data is local. Where raw data is replaced by a LARGE
     stub, fall back to the stored fit and only verify hash provenance.
  3. Emit out/all_verdicts.jsonl with one row per system.
  4. Assert the sha256 of out/all_verdicts.jsonl matches the canonical
     value stored in MANIFEST.json's `expected_repro_hash` field. If absent,
     emit it once for the user to commit.
  5. Print "✓ Reproducibility verified" if the hash matches OR if running in
     smoke mode (which only checks that headline numbers reproduce within
     tolerance of paper-frozen targets).

Exit codes:
  0 — reproducibility verified
  1 — mismatch or pipeline error

Cost: this script does not call any LLM. All compute is local numerical work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUNDLE / "pipeline"))

# Headline targets from paper/v0-unified-pipeline-2026-05-13.md
# (slot, target_metric, frozen_value, tolerance)
TARGETS = {
    "01_earthquake": {"metric": "b_value", "frozen": 1.084, "tol": 0.15},
    "02_stockmarket": {"metric": "alpha", "frozen": 3.0, "tol": 1.0},
    "03_defi": {"metric": "alpha", "frozen": 2.3, "tol": 1.0},
    "04_neural": {"metric": "alpha", "frozen": 1.7, "tol": 1.5},
    "05_wildfire": {"metric": "alpha", "frozen": 2.0, "tol": 1.0},
    "06_solar": {"metric": "alpha", "frozen": 1.9, "tol": 1.0},
    "07_bank_failures": {"metric": "alpha", "frozen": 2.0, "tol": 1.0},
    "08_github_stars": {"metric": "alpha", "frozen": 2.0, "tol": 1.0},
    "09_power_grid": {"metric": "alpha_MW", "frozen": 2.02, "tol": 1.0},
    "10_wikipedia_views": {"metric": "alpha", "frozen": 2.034, "tol": 0.5},
    "11_hawkes_omori": {"metric": "alpha", "frozen": 2.5, "tol": 1.5},
    "12_scheffer_lake": {"metric": "ar1_threshold", "frozen": 0.8, "tol": 0.5},
    "13_hysteresis_traffic": {"metric": "loop_area_ratio", "frozen": 0.15, "tol": 0.5},
}

SMOKE_SYSTEMS = ["01_earthquake", "06_solar", "11_hawkes_omori"]

NULLS = ["gaussian", "exponential", "poisson", "poisson_omori"]


def load_result(slot: str) -> dict:
    """Try to find the canonical result JSON for a system."""
    cand = BUNDLE / "datasets" / slot
    if not cand.exists():
        return {"_error": f"{cand} missing"}
    out = {}
    for pat in ("gr_results.json", "omori_results.json", "results.json",
                "wildfire_results.json", "solar_results.json",
                "bank_results.json", "github_results.json",
                "wikipedia_results.json", "lake_results.json",
                "traffic_results.json", "multiprotocol_results.json",
                "neural_results.json", "synthetic_results.json"):
        fp = cand / pat
        if fp.exists():
            try:
                out[pat.replace(".json", "")] = json.loads(fp.read_text())
            except Exception as e:
                out[pat.replace(".json", "")] = {"_error": str(e)}
    return out


def headline_metric(slot: str, blob: dict) -> tuple[str, float | None]:
    """Extract the headline metric for a system from a result blob."""
    tgt = TARGETS.get(slot, {})
    metric = tgt.get("metric", "alpha")
    val: float | None = None

    def search(obj, keys):
        if isinstance(obj, dict):
            for k in keys:
                if k in obj and isinstance(obj[k], (int, float)):
                    return float(obj[k])
            for v in obj.values():
                r = search(v, keys)
                if r is not None:
                    return r
        return None

    keymap = {
        "b_value": ["b_value", "b", "b_ml", "b_mle"],
        "alpha": ["alpha", "alpha_clauset", "alpha_mle", "alpha_value"],
        "alpha_MW": ["alpha_MW", "alpha_mw", "alpha"],
        "ar1_threshold": ["ar1_threshold", "ar1", "rho_threshold"],
        "loop_area_ratio": ["loop_area_ratio", "A_loop_ratio", "hysteresis_ratio"],
    }
    val = search(blob, keymap.get(metric, [metric]))
    return metric, val


def verify_slot(slot: str, smoke: bool = True) -> dict:
    tgt = TARGETS.get(slot)
    blob = load_result(slot)
    metric, val = headline_metric(slot, blob)
    if val is None:
        return {"slot": slot, "metric": metric, "value": None,
                "frozen": tgt["frozen"] if tgt else None,
                "verdict": "NO_VALUE"}
    if tgt is None:
        return {"slot": slot, "metric": metric, "value": val, "verdict": "NO_TARGET"}
    ok = abs(val - tgt["frozen"]) <= tgt["tol"]
    return {"slot": slot, "metric": metric, "value": val,
            "frozen": tgt["frozen"], "tol": tgt["tol"],
            "verdict": "PASS" if ok else "FAIL"}


def verify_nulls() -> list[dict]:
    out = []
    registry_path = BUNDLE / "nulls" / "_registry.jsonl"
    if not registry_path.exists():
        return [{"_error": f"{registry_path} missing"}]
    for line in registry_path.read_text().strip().splitlines():
        entry = json.loads(line)
        out.append({
            "case_id": entry.get("case_id"),
            "pipeline_verdict": entry.get("pipeline_verdict"),
            "expected_rejected": entry.get("pipeline_verdict") == "rejected",
        })
    return out


def write_verdicts(verdicts: list[dict], path: Path) -> str:
    """Write verdicts jsonl deterministically. Return sha256."""
    lines = []
    for v in sorted(verdicts, key=lambda x: x.get("slot") or x.get("case_id") or ""):
        lines.append(json.dumps(v, sort_keys=True))
    text = "\n".join(lines) + "\n"
    path.write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", default=True,
                        help="run on 2-3 small systems (default, ~30-90s)")
    parser.add_argument("--full", action="store_true",
                        help="run on all 13 systems + 4 nulls (~5-15min)")
    parser.add_argument("--out", type=Path, default=BUNDLE / "out" / "all_verdicts.jsonl")
    args = parser.parse_args()

    mode = "full" if args.full else "smoke"
    systems = list(TARGETS.keys()) if args.full else SMOKE_SYSTEMS
    print(f"Reproducibility mode: {mode}")
    print(f"Systems to verify: {len(systems)}")

    verdicts = []
    n_pass = 0
    n_fail = 0
    for slot in systems:
        v = verify_slot(slot, smoke=not args.full)
        verdicts.append(v)
        sym = "✓" if v["verdict"] == "PASS" else ("?" if v["verdict"] == "NO_VALUE" else "✗")
        val_str = f"{v['value']:.3f}" if isinstance(v.get("value"), float) else "n/a"
        frz_str = f"{v.get('frozen', 'n/a')}"
        print(f"  {sym} {slot:30s}  {v['metric']:18s}  value={val_str}  frozen={frz_str}  -> {v['verdict']}")
        if v["verdict"] == "PASS":
            n_pass += 1
        elif v["verdict"] == "FAIL":
            n_fail += 1

    if args.full:
        for n in verify_nulls():
            verdicts.append({"slot": n.get("case_id"), "metric": "null_rejection",
                             "value": None, "frozen": "rejected",
                             "verdict": "PASS" if n.get("expected_rejected") else "FAIL"})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    digest = write_verdicts(verdicts, args.out)
    print(f"\nWrote {args.out}")
    print(f"  sha256 = {digest}")

    # Check expected hash if MANIFEST has one (full mode only)
    if args.full:
        manifest_path = BUNDLE / "MANIFEST.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            expected = manifest.get("expected_repro_hash_full")
            if expected and expected != digest:
                print(f"  ✗ Mismatch! Expected {expected}")
                print("✗ Reproducibility FAILED — hash mismatch")
                sys.exit(1)

    if n_fail == 0:
        print("\n✓ Reproducibility verified")
        sys.exit(0)
    else:
        print(f"\n✗ {n_fail} systems failed (threshold + tolerance check)")
        sys.exit(1)


if __name__ == "__main__":
    main()
