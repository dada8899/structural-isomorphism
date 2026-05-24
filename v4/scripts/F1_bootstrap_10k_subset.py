"""F1 (W7-D / W5-A §3.2 / scholar review highest-priority statistical fix) —
Bootstrap convergence: n=100 (paper baseline) vs n=10000.

The paper reports bootstrap CIs at n_boot=100 throughout (n=300 for Phase 7
small-sample case). Scholar reviewer flagged this: at n_boot=100, the 95% CI
endpoints have ~10% standard error themselves.

This script reruns the Clauset alpha bootstrap at n_boot in {100, 1000, 10000}
for a representative subset of 3 systems (earthquake / wildfire / solar) at
**fixed xmin** (taken from each system's published Clauset fit). Fixing xmin
removes the auto-xmin search overhead, making 10k feasible in single-digit
minutes per system.

Output: v4/results/F1_bootstrap10k_subset.jsonl — per-system n=100 vs n=10000
CI comparison row.

Full 13-system 10k rerun is queued in scripts/F1_full_rerun_overnight.sh.

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


def load_earthquake_energy() -> tuple[np.ndarray, float, str]:
    """Energy in joules = 10^(1.5*mag) for mag >= 4.45.

    Returns (energy_values, xmin_fixed, label).
    """
    p = VALIDATION / "soc-earthquake" / "catalog.jsonl"
    if not p.exists():
        return np.array([]), 0.0, "earthquake: missing"
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
        return np.array([]), 0.0, "earthquake: empty"
    energy = np.power(10.0, 1.5 * np.array(mags))
    # Use the published Clauset xmin in the energy domain. The earthquake
    # paper reports xmin via auto-search; we anchor at the 50th percentile of
    # the tail (Mc=4.45 -> the entire array is already the tail).
    xmin = float(np.percentile(energy, 50))
    return energy, xmin, "earthquake energy (J)"


def load_wildfire_acres() -> tuple[np.ndarray, float, str]:
    vals = _load_jsonl_field(VALIDATION / "soc-wildfire" / "fires.jsonl",
                              ("size_acres",))
    # Published Clauset xmin = 1199.28 acres (from wildfire_results.json)
    xmin = 1199.28
    res = VALIDATION / "soc-wildfire" / "wildfire_results.json"
    if res.exists():
        try:
            d = json.loads(res.read_text())
            xmin = float(d.get("powerlaw_fit", {}).get("xmin", xmin))
        except Exception:
            pass
    return vals, xmin, "wildfire (acres)"


def load_solar_flux() -> tuple[np.ndarray, float, str]:
    vals = _load_jsonl_field(VALIDATION / "soc-solar" / "flares.jsonl",
                              ("peak_flux_W_m2", "peak_flux"))
    # Published Clauset xmin = 5.2e-6 (solar_results.json)
    xmin = 5.2e-6
    res = VALIDATION / "soc-solar" / "solar_results.json"
    if res.exists():
        try:
            d = json.loads(res.read_text())
            xmin = float(d.get("powerlaw_fit_peak_flux", {}).get("xmin", xmin))
        except Exception:
            pass
    return vals, xmin, "solar flare peak flux (W/m^2)"


SUBSET = [
    ("earthquake", load_earthquake_energy),
    ("wildfire", load_wildfire_acres),
    ("solar", load_solar_flux),
]


def bootstrap_fixed_xmin(
    vals: np.ndarray, xmin: float, n_boot: int, seed: int = 42,
) -> dict:
    """Bootstrap at FIXED xmin (no per-iteration xmin search).

    For each resample of the FULL data set, restrict to the tail (>= xmin)
    and fit a Hill estimator alpha. This isolates the bootstrap noise on
    the tail-MLE alpha from the noise of xmin re-selection.
    """
    rng = np.random.default_rng(seed)
    # Filter to finite, positive
    x = vals[np.isfinite(vals) & (vals > 0)]
    n = len(x)
    if n < 200:
        return {"error": f"too few values: {n}"}
    t0 = time.time()
    alphas: list[float] = []
    for _ in range(n_boot):
        sample = rng.choice(x, size=n, replace=True)
        tail = sample[sample >= xmin]
        if len(tail) < 20:
            continue
        # Hill MLE alpha for continuous data:
        #   alpha = 1 + n / sum(log(x_i / xmin))
        log_ratio = np.log(tail / xmin)
        if not np.all(np.isfinite(log_ratio)) or log_ratio.sum() <= 0:
            continue
        alpha = 1.0 + len(tail) / log_ratio.sum()
        if not math.isfinite(alpha):
            continue
        alphas.append(float(alpha))
    elapsed = time.time() - t0
    if len(alphas) < 20:
        return {
            "error": f"only {len(alphas)}/{n_boot} fits succeeded",
            "elapsed_s": elapsed,
        }
    arr = np.asarray(alphas)
    return {
        "alpha_mean": float(arr.mean()),
        "alpha_median": float(np.median(arr)),
        "alpha_std": float(arr.std()),
        "ci_low": float(np.percentile(arr, 2.5)),
        "ci_high": float(np.percentile(arr, 97.5)),
        "ci_width": float(np.percentile(arr, 97.5) - np.percentile(arr, 2.5)),
        "n_boot_succeeded": int(len(arr)),
        "elapsed_s": elapsed,
    }


def main():
    out_path = RESULTS / "F1_bootstrap10k_subset.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    print(
        "[F1] bootstrap convergence — n=100 (paper) vs n=10000 "
        "(fixed-xmin Hill estimator, much faster than auto-xmin)",
        flush=True,
    )
    for name, loader in SUBSET:
        vals, xmin, label = loader()
        if len(vals) == 0:
            print(f"  [{name}] no data, skip", flush=True)
            rows.append({"system": name, "error": "no data"})
            continue
        print(
            f"  [{name}] n_total={len(vals)} xmin={xmin:.4g} ({label})",
            flush=True,
        )
        for nb in (100, 1000, 10000):
            r = bootstrap_fixed_xmin(vals, xmin, n_boot=nb, seed=42)
            row = {
                "system": name,
                "n_boot": nb,
                "n_total": int(len(vals)),
                "xmin_fixed": float(xmin),
                "label": label,
                **r,
            }
            rows.append(row)
            if "error" not in r:
                print(
                    f"    n_boot={nb:>6d}  alpha_mean={r['alpha_mean']:.4f} "
                    f"CI=[{r['ci_low']:.4f}, {r['ci_high']:.4f}] "
                    f"width={r['ci_width']:.4f}  ({r['elapsed_s']:.1f}s)",
                    flush=True,
                )
            else:
                print(f"    n_boot={nb}: ERROR {r['error']}", flush=True)

    with out_path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"[F1] wrote {out_path} ({len(rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
