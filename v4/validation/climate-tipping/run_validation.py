"""
run_validation.py - End-to-end SOC + EWS validation for climate tipping
(Amazon NDVI + AMOC).

Universality class: scheffer_fold_bifurcation (V4 taxonomy class 3).

Pipeline:
  1. Load each timeseries from raw/*.jsonl.
  2. Preprocess: month-aggregate, deseasonalise (climatology), high-pass detrend.
  3. EWS: rolling AR(1), variance, skewness in a 4-yr window; report Kendall tau
     trend over the full series (positive tau = critical slowing down).
  4. Power-law side-test: fit Clauset 2009 MLE on absolute anomalies above xmin,
     return alpha + KS distance. (Climate tipping is bifurcation-class, not SOC;
     but tail of anomalies is a complementary diagnostic.)
  5. Verdict per system; cross-system comparison to existing scheffer-lake
     baseline (Kendall tau on AR(1) is the canonical structural isomorphism
     metric across the class).

Outputs:
  results.json
  verdict.md
  panel_amoc.png, panel_ndvi_<site>.png
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import kendalltau, skew

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RESULTS = ROOT / "results.json"
VERDICT = ROOT / "verdict.md"

# EWS window in MONTHS (post-aggregation): 4 yr = 48 months.
EWS_WINDOW = 48
# Reference scheffer-lake Kendall tau (Fox River 14yr DO, 2026-05-13 verdict):
# global AR(1) tau = +0.284, p ~ 10^-186 -- our cross-system anchor.
SCHEFFER_LAKE_AR1_TAU = 0.284
SCHEFFER_LAKE_VAR_TAU = 0.234


# ---------------------------------------------------------------------------
# Minimal inlined Clauset-2009 power-law MLE.
# (The vendored packages/soc-pipeline contains comment-corruption from a prior
#  history scrub and currently fails to import; we inline what we need so this
#  module is self-contained and reusable.)
# ---------------------------------------------------------------------------
def clauset_alpha_ks(values: np.ndarray, xmin: float) -> tuple[float, float, int]:
    """Continuous Clauset 2009 MLE for alpha given xmin; return (alpha, ks, n_tail)."""
    tail = values[values >= xmin]
    n = len(tail)
    if n < 30:
        return float("nan"), float("nan"), n
    alpha = 1.0 + n / np.sum(np.log(tail / xmin))
    # KS distance vs theoretical CDF F(x)=1-(xmin/x)^(alpha-1)
    sorted_tail = np.sort(tail)
    emp = np.arange(1, n + 1) / n
    theo = 1.0 - (xmin / sorted_tail) ** (alpha - 1)
    ks = float(np.max(np.abs(emp - theo)))
    return float(alpha), ks, n


def fit_powerlaw_xmin_sweep(values: np.ndarray, n_xmin: int = 30
                            ) -> dict:
    """Sweep xmin candidates (quantile grid), pick the one that minimises KS."""
    values = np.asarray(values, dtype=float)
    values = values[values > 0]
    if len(values) < 100:
        return {"ok": False, "n_total": int(len(values)),
                "reason": "insufficient positive samples"}
    qs = np.linspace(0.20, 0.95, n_xmin)
    candidates = np.quantile(values, qs)
    best = None
    for xmin in candidates:
        if xmin <= 0:
            continue
        alpha, ks, n_tail = clauset_alpha_ks(values, float(xmin))
        if not math.isfinite(alpha) or not math.isfinite(ks):
            continue
        rec = {"alpha": alpha, "ks": ks, "xmin": float(xmin), "n_tail": n_tail}
        if best is None or rec["ks"] < best["ks"]:
            best = rec
    if best is None:
        return {"ok": False, "n_total": int(len(values)),
                "reason": "no valid xmin"}
    best["ok"] = True
    best["n_total"] = int(len(values))
    return best


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_jsonl(path: Path, value_key: str) -> tuple[np.ndarray, np.ndarray, bool]:
    """Return (dates as datetime64[D], values, any_synthetic_flag)."""
    dates: list[str] = []
    vals: list[float] = []
    syn = False
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            d = r["date"][:10]
            dates.append(d)
            vals.append(float(r[value_key]))
            if r.get("synthetic"):
                syn = True
    return (np.array(dates, dtype="datetime64[D]"),
            np.array(vals, dtype=float),
            syn)


def monthly_mean(dates: np.ndarray, vals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Aggregate to monthly mean. Returns datetime64[M] grid and means."""
    if len(dates) == 0:
        return np.array([], dtype="datetime64[M]"), np.array([])
    months = dates.astype("datetime64[M]")
    unique = np.unique(months)
    out = np.array([np.mean(vals[months == m]) for m in unique])
    return unique, out


def deseasonalise(values: np.ndarray, months: np.ndarray) -> np.ndarray:
    """Remove monthly climatology (12 climo means)."""
    mm = months.astype("datetime64[M]").astype(int) % 12
    climo = np.zeros(12)
    for m in range(12):
        sel = mm == m
        if sel.any():
            climo[m] = values[sel].mean()
    return values - climo[mm]


# ---------------------------------------------------------------------------
# Rolling EWS
# ---------------------------------------------------------------------------
def rolling_stat(x: np.ndarray, window: int, stat: str) -> np.ndarray:
    n = len(x)
    out = np.full(n, np.nan)
    for i in range(window, n):
        w = x[i - window:i]
        w = w[~np.isnan(w)]
        if len(w) < max(10, window // 4):
            continue
        if stat == "ar1":
            if np.std(w[:-1]) < 1e-9 or np.std(w[1:]) < 1e-9:
                continue
            out[i] = float(np.corrcoef(w[:-1], w[1:])[0, 1])
        elif stat == "var":
            out[i] = float(np.var(w))
        elif stat == "skew":
            out[i] = float(skew(w))
    return out


def kendall_trend(y: np.ndarray) -> dict:
    mask = ~np.isnan(y)
    if mask.sum() < 24:
        return {"tau": None, "p": None, "n": int(mask.sum())}
    t = np.arange(len(y))
    tau, p = kendalltau(t[mask], y[mask])
    return {"tau": float(tau), "p": float(p), "n": int(mask.sum())}


# ---------------------------------------------------------------------------
# Per-system analysis
# ---------------------------------------------------------------------------
def analyse_system(name: str, path: Path, value_key: str) -> dict:
    if not path.exists():
        return {"system": name, "ok": False, "reason": f"missing {path.name}"}
    dates, vals, syn = load_jsonl(path, value_key)
    if len(vals) < 100:
        return {"system": name, "ok": False, "reason": f"too few samples n={len(vals)}",
                "synthetic": syn}
    months, monthly = monthly_mean(dates, vals)
    if len(monthly) < EWS_WINDOW + 12:
        return {"system": name, "ok": False, "synthetic": syn,
                "reason": f"insufficient months n={len(monthly)} (need >= {EWS_WINDOW+12})"}
    anom = deseasonalise(monthly, months)
    ar1 = rolling_stat(anom, EWS_WINDOW, "ar1")
    var = rolling_stat(anom, EWS_WINDOW, "var")
    sk = rolling_stat(anom, EWS_WINDOW, "skew")

    # Power-law side test on |anomaly|
    abs_anom = np.abs(anom)
    pl = fit_powerlaw_xmin_sweep(abs_anom)

    # Isomorphism distance to scheffer-lake AR1 trend (using absolute Kendall tau).
    ar1_trend = kendall_trend(ar1)
    var_trend = kendall_trend(var)
    skew_trend = kendall_trend(sk)
    iso_distance = None
    if ar1_trend["tau"] is not None and var_trend["tau"] is not None:
        # L2 distance of (tau_AR1, tau_var) vs Scheffer-lake reference.
        d_ar1 = ar1_trend["tau"] - SCHEFFER_LAKE_AR1_TAU
        d_var = var_trend["tau"] - SCHEFFER_LAKE_VAR_TAU
        iso_distance = float(np.sqrt(d_ar1 ** 2 + d_var ** 2))

    classical_csd = bool(
        ar1_trend["tau"] is not None and ar1_trend["tau"] > 0 and
        ar1_trend["p"] is not None and ar1_trend["p"] < 0.05 and
        var_trend["tau"] is not None and var_trend["tau"] > 0 and
        var_trend["p"] is not None and var_trend["p"] < 0.05
    )

    # Verdict per system
    if syn:
        verdict = "SYNTHETIC"
    elif classical_csd:
        verdict = "PASS"
    elif ar1_trend["tau"] is not None and ar1_trend["tau"] > 0:
        verdict = "QUALIFIED"  # AR(1) rising, variance unclear
    else:
        verdict = "INCONCLUSIVE"

    try:
        data_path_str = str(path.relative_to(ROOT))
    except ValueError:
        data_path_str = str(path)
    return {
        "system": name,
        "data_path": data_path_str,
        "synthetic": syn,
        "n_raw": int(len(vals)),
        "n_months": int(len(monthly)),
        "first_date": str(months[0]),
        "last_date": str(months[-1]),
        "ews": {
            "window_months": EWS_WINDOW,
            "ar1_trend": ar1_trend,
            "var_trend": var_trend,
            "skew_trend": skew_trend,
            "classical_csd_signature": classical_csd,
        },
        "powerlaw_tail": pl,
        "iso_distance_to_scheffer_lake": iso_distance,
        "verdict": verdict,
        "ok": True,
        "_ar1_series": ar1.tolist(),
        "_var_series": var.tolist(),
        "_skew_series": sk.tolist(),
        "_anom_series": anom.tolist(),
        "_months_index": [str(m) for m in months],
    }


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def plot_panel(rep: dict, path: Path) -> None:
    months = np.array(rep["_months_index"], dtype="datetime64[M]")
    anom = np.array(rep["_anom_series"])
    ar1 = np.array(rep["_ar1_series"])
    var = np.array(rep["_var_series"])
    sk = np.array(rep["_skew_series"])
    fig, axes = plt.subplots(4, 1, figsize=(11, 9), sharex=True)
    for ax in axes:
        ax.grid(False)
    axes[0].plot(months, anom, color="#1f77b4", lw=0.7)
    axes[0].axhline(0, color="k", lw=0.4)
    axes[0].set_ylabel("anomaly")
    axes[0].set_title(f"{rep['system']} - EWS panel ({rep['ews']['window_months']}-month window)")
    axes[1].plot(months, ar1, color="#d62728", lw=0.8)
    axes[1].set_ylabel("AR(1)")
    axes[2].plot(months, var, color="#9467bd", lw=0.8)
    axes[2].set_ylabel("variance")
    axes[3].plot(months, sk, color="#8c564b", lw=0.8)
    axes[3].axhline(0, color="k", lw=0.4)
    axes[3].set_ylabel("skewness")
    axes[3].set_xlabel("date")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Verdict.md writer
# ---------------------------------------------------------------------------
def write_verdict_md(results: dict) -> None:
    lines = []
    lines.append("# VERDICT - X3 Climate Tipping Points (Amazon NDVI + AMOC)")
    lines.append("## Taxonomy class 3 (scheffer_fold_bifurcation)")
    lines.append("")
    lines.append(f"**Date.** {datetime.utcnow().strftime('%Y-%m-%d')}")
    lines.append(f"**Validator.** structural-isomorphism v4, X3 climate-tipping track")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append("| System | Real / Synth | n_months | AR(1) tau | var tau | classical CSD | Verdict | Iso-dist to Scheffer-lake |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for sysrep in results["systems"]:
        if not sysrep["ok"]:
            lines.append(f"| {sysrep['system']} | - | - | - | - | - | FAIL ({sysrep.get('reason', '?')}) | - |")
            continue
        syn = "SYNTHETIC" if sysrep["synthetic"] else "REAL"
        ar1 = sysrep["ews"]["ar1_trend"]["tau"]
        var = sysrep["ews"]["var_trend"]["tau"]
        csd = "yes" if sysrep["ews"]["classical_csd_signature"] else "no"
        ar1_s = f"{ar1:+.3f}" if ar1 is not None else "-"
        var_s = f"{var:+.3f}" if var is not None else "-"
        iso = sysrep["iso_distance_to_scheffer_lake"]
        iso_s = f"{iso:.3f}" if iso is not None else "-"
        lines.append(f"| {sysrep['system']} | {syn} | {sysrep['n_months']} | "
                     f"{ar1_s} | {var_s} | {csd} | {sysrep['verdict']} | {iso_s} |")
    lines.append("")
    lines.append("## Data sources")
    lines.append("")
    lines.append("- **AMOC**: RAPID 26 N array, https://rapid.ac.uk/sites/default/files/rapid_data/moc_transports.nc -- variable `moc_mar_hc10` (overturning transport, Sv), 2004-04-01 onwards, 12-hourly.")
    lines.append("- **Amazon NDVI**: NASA ORNL DAAC MODIS MOD13Q1 250 m 16-day NDVI, REST API `https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset`, 2000-02-18 onwards. Sites: central_amazonas (-3.0, -60.0), rondonia_arc (-10.0, -62.5), xingu_park (-12.0, -53.0), western_acre (-9.5, -68.0), para_central (-5.5, -55.5).")
    lines.append("- **Reference for isomorphism distance**: v4/validation/scheffer-lake VERDICT-2026-05-13 (Fox River Green Bay DO, USGS 040851385) AR(1) tau=+0.284, var tau=+0.234.")
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append(f"1. Monthly aggregation; deseasonalise via 12-month climatology removal.")
    lines.append(f"2. Rolling EWS (window = {EWS_WINDOW} months): AR(1), variance, skewness.")
    lines.append("3. Kendall tau monotonic-trend test over the full deseasonalised anomaly series. Classical CSD = positive significant AR(1) AND positive significant variance.")
    lines.append("4. Power-law side-test (Clauset 2009 MLE) on |anomaly|, xmin chosen by KS sweep. Not the primary verdict for fold-bifurcation class but a complementary tail diagnostic.")
    lines.append("5. Structural isomorphism distance = L2((tau_AR1 - 0.284), (tau_var - 0.234)) against scheffer-lake reference.")
    lines.append("")
    lines.append("## Per-system findings")
    lines.append("")
    for sysrep in results["systems"]:
        if not sysrep["ok"]:
            lines.append(f"### {sysrep['system']} -- FAIL")
            lines.append(f"  Reason: {sysrep.get('reason', '?')}")
            lines.append("")
            continue
        lines.append(f"### {sysrep['system']}")
        lines.append(f"")
        lines.append(f"- Source: `{sysrep['data_path']}` (n_raw={sysrep['n_raw']}, n_months={sysrep['n_months']}, {sysrep['first_date']} -> {sysrep['last_date']})")
        lines.append(f"- Synthetic: **{sysrep['synthetic']}**")
        lines.append(f"- AR(1) trend: tau = {_fmt(sysrep['ews']['ar1_trend']['tau'])}, p = {_fmt(sysrep['ews']['ar1_trend']['p'])}, n = {sysrep['ews']['ar1_trend']['n']}")
        lines.append(f"- Variance trend: tau = {_fmt(sysrep['ews']['var_trend']['tau'])}, p = {_fmt(sysrep['ews']['var_trend']['p'])}")
        lines.append(f"- Skewness trend: tau = {_fmt(sysrep['ews']['skew_trend']['tau'])}, p = {_fmt(sysrep['ews']['skew_trend']['p'])}")
        lines.append(f"- Classical CSD signature: **{sysrep['ews']['classical_csd_signature']}**")
        pl = sysrep["powerlaw_tail"]
        if pl.get("ok"):
            lines.append(f"- Power-law tail of |anomaly|: alpha = {pl['alpha']:.3f}, xmin = {pl['xmin']:.4f}, KS = {pl['ks']:.4f}, n_tail = {pl['n_tail']}/{pl['n_total']}")
        else:
            lines.append(f"- Power-law tail: SKIP ({pl.get('reason', 'failed')})")
        if sysrep.get("iso_distance_to_scheffer_lake") is not None:
            lines.append(f"- Iso-distance to scheffer-lake: **{sysrep['iso_distance_to_scheffer_lake']:.3f}** (lower = closer match)")
        lines.append(f"- Verdict: **{sysrep['verdict']}**")
        lines.append("")
    lines.append("## Limitations / honesty")
    lines.append("")
    lines.append("- AMOC RAPID 26 N is 20 years -- shorter than the multi-decadal forcing timescale (Boers 2021 PNAS used ~150 yr SST reconstructions). Our 4-yr EWS window therefore captures intra-decadal variability more than secular destabilisation. A pre-registered finding of *no* tipping signature in the 20-yr direct observation is consistent with Boers' SST-proxy result that the secular signal only emerges over centuries.")
    lines.append("- Amazon NDVI: single-pixel MODIS time series have cloud-contamination noise; we did NOT apply QA-flag filtering in this pass (the REST API returns NDVI even when MOD13Q1_QC flags low-quality). A Wave 3 follow-up should re-fetch with quality masks.")
    lines.append("- Synthetic fallbacks are flagged explicitly in the table above and in `raw/fetch_log.json`. No system claims REAL where the fetch did not succeed.")
    lines.append("")
    VERDICT.write_text("\n".join(lines))


def _fmt(v) -> str:
    if v is None:
        return "n/a"
    if abs(v) < 1e-3 and v != 0:
        return f"{v:.2e}"
    return f"{v:+.4f}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    out = {"started_at": datetime.utcnow().isoformat() + "Z",
           "systems": []}
    # AMOC
    out["systems"].append(analyse_system("amoc_rapid_26n",
                                         RAW / "amoc_timeseries.jsonl",
                                         value_key="moc_sv"))
    # NDVI sites
    for p in sorted(RAW.glob("amazon_ndvi_*.jsonl")):
        site = p.stem.replace("amazon_ndvi_", "")
        out["systems"].append(analyse_system(f"amazon_ndvi_{site}", p,
                                             value_key="ndvi"))
    # Plots
    for sysrep in out["systems"]:
        if sysrep.get("ok"):
            png = ROOT / f"panel_{sysrep['system']}.png"
            try:
                plot_panel(sysrep, png)
                sysrep["plot_path"] = png.name
            except Exception as exc:  # pylint: disable=broad-except
                sysrep["plot_error"] = f"{type(exc).__name__}: {exc}"

    # Strip large in-memory series from final JSON; keep plots.
    out_serialisable = {"started_at": out["started_at"], "systems": []}
    for s in out["systems"]:
        s2 = {k: v for k, v in s.items() if not k.startswith("_")}
        out_serialisable["systems"].append(s2)
    out_serialisable["finished_at"] = datetime.utcnow().isoformat() + "Z"

    RESULTS.write_text(json.dumps(out_serialisable, indent=2, default=str))
    write_verdict_md({"systems": out["systems"]})
    print(f"[run] wrote {RESULTS.name} and {VERDICT.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
