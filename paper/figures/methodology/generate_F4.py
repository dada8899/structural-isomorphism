"""F4 (W7-D / W5-A §3.8) — xmin sensitivity sliding-window scan.

For each system, sweep xmin across [0.5 * xmin_baseline, 2.0 * xmin_baseline]
in 20 log-spaced steps. Fit Clauset alpha at each xmin. Plot the alpha(xmin)
curve in a 13-panel (or N-panel) grid.

A flat curve means the alpha point estimate is robust to xmin choice. A
sloped curve indicates xmin sensitivity.

Output:
  paper/figures/methodology/F4_xmin_sensitivity.{pdf,png}
  paper/figures/methodology/F4_xmin_sensitivity_data.json

Usage:
    PYTHONPATH=packages/soc-pipeline/src python paper/figures/methodology/generate_F4.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


THIS = Path(__file__).resolve()
HERE = THIS.parent
ROOT = THIS.parents[3]
VALIDATION = ROOT / "v4" / "validation"
OUT_DATA = HERE / "F4_xmin_sensitivity_data.json"
OUT_PDF = HERE / "F4_xmin_sensitivity.pdf"
OUT_PNG = HERE / "F4_xmin_sensitivity.png"


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


def _load_earthquake_energy() -> tuple[np.ndarray, float]:
    """Energy in joules for mag >= 4.45. Baseline xmin from gr_results.json."""
    p = VALIDATION / "soc-earthquake" / "catalog.jsonl"
    if not p.exists():
        return np.array([]), 1e8
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
    energy = np.power(10.0, 1.5 * np.array(mags)) if mags else np.array([])
    # baseline xmin: use Clauset fit's xmin from gr_results.json if available
    gr = VALIDATION / "soc-earthquake" / "gr_results.json"
    if gr.exists():
        d = json.loads(gr.read_text())
        # Earthquake uses b-value, not Clauset-xmin in energy. Use median energy
        baseline = float(np.median(energy)) if len(energy) else 1e8
    else:
        baseline = float(np.median(energy)) if len(energy) else 1e8
    return energy, baseline


def _load_stockmarket() -> tuple[np.ndarray, float]:
    import pandas as pd
    p = VALIDATION / "soc-stockmarket" / "sp500_daily.csv"
    if not p.exists():
        return np.array([]), 0.01
    df = pd.read_csv(p, skiprows=3, header=None,
                     names=["Date", "Adj Close", "Close", "High", "Low", "Open", "Volume"])
    prices = pd.to_numeric(df["Close"], errors="coerce").dropna().values
    if len(prices) < 10:
        return np.array([]), 0.01
    rets = np.diff(np.log(prices))
    abs_rets = np.abs(rets[np.isfinite(rets)])
    abs_rets = abs_rets[abs_rets > 0]
    # baseline xmin from gr_results.json clauset_fit.xmin
    gr = VALIDATION / "soc-stockmarket" / "gr_results.json"
    baseline = 0.01
    if gr.exists():
        d = json.loads(gr.read_text())
        baseline = float(d.get("clauset_fit", {}).get("xmin", 0.01))
    return abs_rets, baseline


def _baseline_from_results(json_path: Path, *keys: str, default: float = 1.0) -> float:
    if not json_path.exists():
        return default
    try:
        d = json.loads(json_path.read_text())
    except Exception:
        return default
    cur: object = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    try:
        return float(cur)
    except Exception:
        return default


# Per-system loader returning (vals, baseline_xmin, label)
def make_systems() -> list[tuple[str, np.ndarray, float, str]]:
    out: list[tuple[str, np.ndarray, float, str]] = []

    # Earthquake (use magnitude as observable since b-value uses mag)
    eq_vals, eq_baseline = _load_earthquake_energy()
    if len(eq_vals) > 0:
        # For energy data, xmin baseline from data percentile (50th)
        out.append(("earthquake", eq_vals, float(np.percentile(eq_vals, 50)),
                    "earthquake energy (J)"))

    # Stockmarket
    sp_vals, sp_baseline = _load_stockmarket()
    if len(sp_vals) > 0:
        out.append(("stockmarket", sp_vals, sp_baseline, "S&P 500 |daily ret|"))

    # DeFi Aave
    aave = _load_jsonl_field(VALIDATION / "soc-defi" / "aave_v2_liquidations.jsonl",
                              ("debt_to_cover_raw", "debt_to_cover"))
    if len(aave) > 0:
        baseline = _baseline_from_results(
            VALIDATION / "soc-defi" / "multiprotocol_results.json",
            "aave_v2", "power_law", "xmin_usd", default=17494.0,
        )
        out.append(("defi_aave", aave, baseline, "DeFi Aave V2 liquidations"))

    # Wildfire
    wf = _load_jsonl_field(VALIDATION / "soc-wildfire" / "fires.jsonl",
                            ("size_acres",))
    if len(wf) > 0:
        baseline = _baseline_from_results(
            VALIDATION / "soc-wildfire" / "wildfire_results.json",
            "powerlaw_fit", "xmin", default=1199.0,
        )
        out.append(("wildfire", wf, baseline, "wildfire (acres)"))

    # Solar flares
    sol = _load_jsonl_field(VALIDATION / "soc-solar" / "flares.jsonl",
                             ("peak_flux_W_m2", "peak_flux"))
    if len(sol) > 0:
        baseline = _baseline_from_results(
            VALIDATION / "soc-solar" / "solar_results.json",
            "powerlaw_fit_peak_flux", "xmin", default=5.2e-6,
        )
        out.append(("solar", sol, baseline, "solar flare peak flux"))

    # Bank failures
    bf = _load_jsonl_field(VALIDATION / "soc-bank-failures" / "bank_failures.jsonl",
                            ("assets_usd",))
    if len(bf) > 0:
        baseline = _baseline_from_results(
            VALIDATION / "soc-bank-failures" / "bank_results.json",
            "powerlaw_fit_assets", "xmin", default=6.27e8,
        )
        out.append(("bank_failure", bf, baseline, "bank assets (USD)"))

    # GitHub stars
    gh = _load_jsonl_field(VALIDATION / "soc-github-stars" / "repos.jsonl",
                            ("stars", "stargazers_count"))
    if len(gh) > 0:
        baseline = _baseline_from_results(
            VALIDATION / "soc-github-stars" / "github_results.json",
            "powerlaw_fit", "xmin", default=25585.0,
        )
        out.append(("github_stars", gh, baseline, "GitHub stargazers"))

    # Wikipedia
    wk = _load_jsonl_field(VALIDATION / "soc-wikipedia-views" / "pageviews_2023_2024.jsonl",
                            ("views_total", "views", "pageviews"))
    if len(wk) > 0:
        baseline = _baseline_from_results(
            VALIDATION / "soc-wikipedia-views" / "wikipedia_results.json",
            "powerlaw_fit", "xmin", default=984148.0,
        )
        out.append(("wikipedia", wk, baseline, "Wikipedia pageviews"))

    return out


def sweep_xmin(
    vals: np.ndarray, baseline: float, n_steps: int = 20, factor_lo: float = 0.5,
    factor_hi: float = 2.0,
) -> dict:
    """Sweep xmin in log-space; fit fixed-xmin powerlaw at each step."""
    try:
        import powerlaw
    except ImportError:
        return {"error": "powerlaw missing"}

    xmin_grid = np.geomspace(baseline * factor_lo, baseline * factor_hi, n_steps)
    alphas: list[float] = []
    n_tails: list[int] = []
    for xm in xmin_grid:
        tail = vals[vals >= xm]
        if len(tail) < 10:
            alphas.append(float("nan"))
            n_tails.append(int(len(tail)))
            continue
        try:
            f = powerlaw.Fit(tail, xmin=float(xm), discrete=False, verbose=False)
            alphas.append(float(f.power_law.alpha))
            n_tails.append(int(len(tail)))
        except Exception:
            alphas.append(float("nan"))
            n_tails.append(int(len(tail)))

    arr = np.array(alphas)
    finite = arr[np.isfinite(arr)]
    if len(finite) == 0:
        return {
            "xmin_grid": xmin_grid.tolist(),
            "alphas": alphas,
            "n_tails": n_tails,
            "alpha_min": None, "alpha_max": None,
            "alpha_range": None, "alpha_std": None,
            "drift_assessment": "no_data",
        }
    return {
        "xmin_grid": xmin_grid.tolist(),
        "alphas": [float(a) if math.isfinite(a) else None for a in alphas],
        "n_tails": n_tails,
        "alpha_min": float(np.nanmin(arr)),
        "alpha_max": float(np.nanmax(arr)),
        "alpha_range": float(np.nanmax(arr) - np.nanmin(arr)),
        "alpha_std": float(np.nanstd(arr)),
        "baseline_xmin": float(baseline),
        # Drift = absolute alpha range across xmin sweep
        # < 0.2 = robust, 0.2-0.5 = mild drift, > 0.5 = substantial drift
        "drift_assessment": (
            "robust" if (np.nanmax(arr) - np.nanmin(arr)) < 0.2 else
            "mild_drift" if (np.nanmax(arr) - np.nanmin(arr)) < 0.5 else
            "substantial_drift"
        ),
    }


def main():
    print("[F4] xmin sensitivity sweep across systems...")
    systems = make_systems()
    print(f"[F4] {len(systems)} systems loaded")

    results = {}
    for name, vals, baseline, label in systems:
        print(f"  [{name}] n={len(vals)} baseline_xmin={baseline:.4g}", end=" ", flush=True)
        res = sweep_xmin(vals, baseline)
        results[name] = {"label": label, **res}
        if "error" in res:
            print(f"ERR {res['error']}")
        else:
            print(f"alpha range=[{res.get('alpha_min')}, {res.get('alpha_max')}] "
                  f"drift={res['drift_assessment']}")

    OUT_DATA.write_text(json.dumps(results, indent=2))
    print(f"[F4] wrote {OUT_DATA}")

    # Plot grid
    n_sys = len(results)
    ncols = 3
    nrows = (n_sys + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 4.5, nrows * 3.2))
    axes_flat = axes.flatten() if n_sys > 1 else [axes]

    for ax, (name, info) in zip(axes_flat, results.items()):
        x = np.asarray(info["xmin_grid"], dtype=float)
        y = np.asarray([
            float(a) if a is not None else np.nan
            for a in info["alphas"]
        ])
        baseline_xmin = info.get("baseline_xmin", x[len(x) // 2])
        # Normalize x to baseline ratio
        x_ratio = x / baseline_xmin
        ax.plot(x_ratio, y, "o-", color="#1f77b4", lw=1.5, ms=4, alpha=0.85)
        ax.axvline(1.0, color="k", ls="--", alpha=0.5, lw=1, label="baseline")
        # Reference band: baseline alpha plus/minus 0.2
        finite = y[np.isfinite(y)]
        if len(finite) > 0:
            alpha_mean = float(np.mean(finite))
            ax.axhspan(alpha_mean - 0.2, alpha_mean + 0.2, color="green",
                        alpha=0.08, label="±0.2 robust band")
        ax.set_xscale("log")
        ax.set_xlabel(r"$x_{\min}$ / baseline")
        ax.set_ylabel(r"$\hat\alpha$")
        drift = info.get("drift_assessment", "?")
        ax.set_title(f"{info.get('label', name)}\ndrift: {drift}",
                     fontsize=9)
        ax.grid(True, which="both", alpha=0.3)

    # Hide unused axes
    for ax in axes_flat[len(results):]:
        ax.axis("off")

    fig.suptitle("F4: Clauset $\\hat\\alpha$ vs $x_{\\min}$ sweep (W5-A §3.8)",
                 fontsize=13, y=1.001)
    plt.tight_layout()
    plt.savefig(OUT_PDF, bbox_inches="tight", dpi=140)
    plt.savefig(OUT_PNG, bbox_inches="tight", dpi=140)
    plt.close(fig)
    print(f"[F4] wrote {OUT_PDF}")
    print(f"[F4] wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
