"""F1 (W7-D / W5-A §3.2 / scholar review highest-priority statistical fix) —
Bootstrap convergence: n=100 (paper baseline) vs n=10000.

The paper reports bootstrap CIs at n_boot=100 throughout (n=300 for Phase 7
small-sample case). Scholar reviewer flagged this: at n_boot=100, the 95% CI
endpoints have ~10% standard error themselves.

This script reruns the Clauset alpha bootstrap at n_boot=10000 for a
representative subset of 3 systems (earthquake / wildfire / solar) and writes:

  v4/results/F1_bootstrap10k_subset.jsonl  — per-system n=100 vs n=10000 row

Output table shows whether the CI substantively shifts. The verdict for any
system should not change (since the point estimate is unchanged), but the CI
width should converge.

Full 13-system 10k rerun is queued in F1_full_rerun_overnight.sh.

Usage:
    PYTHONPATH=packages/soc-pipeline/src python v4/scripts/F1_bootstrap_10k_subset.py
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np

# Allow soc_pipeline import without pip install
import sys
ROOT = Path(__file__).resolve().parents[2]
SOC_SRC = ROOT / "packages" / "soc-pipeline" / "src"
if str(SOC_SRC) not in sys.path:
    sys.path.insert(0, str(SOC_SRC))

from soc_pipeline import bootstrap_ci  # noqa: E402


VALIDATION = ROOT / "v4" / "validation"
RESULTS = ROOT / "v4" / "results"


def _load_jsonl_field(path: Path, field_names: tuple[str, ...]) -> np.ndarray:
    rows: list[float] = []
    if not path.exists():
        return np.array([])
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            v = None
            for fn in field_names:
                if fn in rec and rec[fn] is not None:
                    v = rec[fn]
                    break
            if v is None:
                continue
            try:
                v = float(v)
            except Exception:
                continue
            if v > 0 and math.isfinite(v):
                rows.append(v)
    return np.array(rows)


def load_earthquake_energy() -> tuple[np.ndarray, str]:
    """Energy in joules = 10^(1.5*mag) for mag >= 4.45."""
    p = VALIDATION / "soc-earthquake" / "catalog.jsonl"
    if not p.exists():
        return np.array([]), "earthquake: missing"
    mags = []
    with p.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
                m = float(rec["mag"])
                if m >= 4.45:
                    mags.append(m)
            except Exception:
                continue
    if not mags:
        return np.array([]), "earthquake: empty"
    return np.power(10.0, 1.5 * np.array(mags)), "earthquake energy (J)"


def load_wildfire_acres() -> tuple[np.ndarray, str]:
    vals = _load_jsonl_field(VALIDATION / "soc-wildfire" / "fires.jsonl",
                              ("size_acres",))
    return vals, "wildfire (acres)"


def load_solar_flux() -> tuple[np.ndarray, str]:
    vals = _load_jsonl_field(VALIDATION / "soc-solar" / "flares.jsonl",
                              ("peak_flux_W_m2", "peak_flux"))
    return vals, "solar flare peak flux (W/m^2)"


SUBSET = [
    ("earthquake", load_earthquake_energy),
    ("wildfire", load_wildfire_acres),
    ("solar", load_solar_flux),
]


def run_one(name: str, vals: np.ndarray, n_boot: int, seed: int = 42) -> dict:
    """Run a single bootstrap and return summary row."""
    t0 = time.time()
    r = bootstrap_ci(vals, n_boot=n_boot, seed=seed, discrete=False)
    elapsed = time.time() - t0
    if r.error:
        return {
            "system": name,
            "n_boot": n_boot,
            "n_total": int(len(vals)),
            "error": r.error,
            "elapsed_s": elapsed,
        }
    return {
        "system": name,
        "n_boot": n_boot,
        "n_total": int(len(vals)),
        "n_boot_succeeded": int(r.n_boot_succeeded),
        "alpha_mean": float(r.alpha_mean),
        "alpha_median": float(r.alpha_median),
        "alpha_std": float(r.alpha_std),
        "ci_low": float(r.ci_low),
        "ci_high": float(r.ci_high),
        "ci_width": float(r.ci_high - r.ci_low),
        "elapsed_s": float(elapsed),
    }


def main():
    out_path = RESULTS / "F1_bootstrap10k_subset.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    print("[F1] bootstrap convergence — n=100 (paper) vs n=10000")
    for name, loader in SUBSET:
        vals, label = loader()
        if len(vals) == 0:
            print(f"  [{name}] no data, skip")
            rows.append({"system": name, "error": "no data"})
            continue
        print(f"  [{name}] n_total={len(vals)} ({label})")
        for nb in (100, 1000, 10000):
            r = run_one(name, vals, n_boot=nb)
            r["label"] = label
            rows.append(r)
            if "error" not in r:
                print(
                    f"    n_boot={nb:>6d}  alpha_mean={r['alpha_mean']:.4f} "
                    f"CI=[{r['ci_low']:.4f}, {r['ci_high']:.4f}] "
                    f"width={r['ci_width']:.4f}  ({r['elapsed_s']:.1f}s)"
                )
            else:
                print(f"    n_boot={nb}: ERROR {r['error']}")

    with out_path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"[F1] wrote {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
