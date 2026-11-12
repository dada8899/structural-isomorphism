#!/usr/bin/env python3
"""Walk-forward backtest v0.2 — W7-D real-data upgrade (2026-05-25).

Hypothesis (per W7-D § 4.B, unchanged from v0.1):
    Companies classified by D1 Phase Detector as `near_critical`
    (approaching_critical OR at_critical) outperform an equal-weighted
    SPY benchmark across the 2020-2024 window.

Honest caveats vs v0.1:
    - Prices: REAL yfinance monthly closes (auto-adjust) for SP500 top-100
      + SPY benchmark, 2020-01 → 2024-12 (60 months).
    - D1 classification: **single-snapshot 2026-05-13**, not monthly
      time-varying. This is a static-screen alpha test — we apply a
      classification that "knew the future" of 2020-2024 to historical
      returns. Therefore the result has *look-ahead bias on the classifier*
      (the LLM may have been influenced by knowing 2020-2024 outcomes when
      reasoning about each company's structure). Honest interpretation: this
      tests "does D1's structural classification (built in 2026) correlate
      with 2020-2024 historical risk-adjusted returns?", which is closer to
      an *ex-post discriminative* test than a *true ex-ante forecast*.
    - For a true ex-ante test we need monthly D1 snapshots produced at
      historical timestamps — deferred to v0.3.

Pipeline:
    For each rebalance month from 2020-01 to 2024-12:
        1. Cohort = top-100 tickers labelled `approaching_critical` or
           `at_critical` in companies_500.jsonl (static label).
        2. Equal-weighted hold one month, rebalance monthly.
        3. Compute monthly return for cohort vs SPY.
    Aggregate:
        - cumulative wealth curve cohort + SPY
        - annualized Sharpe (cohort, SPY, lift)
        - max drawdown (cohort, SPY)
        - turnover (zero under static classification — sanity guard)
        - alpha vs SPY: CAPM regression r_cohort = α + β·r_spy + ε
        - alpha t-statistic via residual standard error (Newey-West n/a v0.2)

Outputs:
    backtest/results/walk-forward-v0.2.json
    backtest/results/walk-forward-v0.2.md
    backtest/results/walk-forward-v0.2-cumret.png
    backtest/results/walk-forward-v0.2-drawdown.png
    backtest/results/walk-forward-v0.2-turnover.png

Honest verdict gate (W7-D § 3):
    Sharpe lift ≥ +0.5  → "alpha confirmed, lean into alpha-screener"
    Sharpe lift < +0.3  → "alpha not confirmed, pivot to structured-research narrative"
    in-between          → "inconclusive, extend window / universe"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("structural.backtest.v0_2")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "backtest" / "results"
DEFAULT_PRICES = REPO_ROOT / "backtest" / "data" / "sp500-top100-2020-2024.parquet"
DEFAULT_PRICES_META = REPO_ROOT / "backtest" / "data" / "sp500-top100-2020-2024.meta.json"
DEFAULT_TOP100 = REPO_ROOT / "v4" / "product" / "d1_phase_detector" / "companies.jsonl"
DEFAULT_CLASSIFIED = REPO_ROOT / "v4" / "product" / "d1_phase_detector" / "companies_500.jsonl"

NEAR_CRITICAL_STATES = {"approaching_critical", "at_critical"}


# ----------------- Data loading -----------------

def load_top100_with_classification(
    top100_path: Path,
    classified_path: Path,
) -> tuple[list[dict[str, Any]], str]:
    """Cross-join top-100 metadata with D1 classification snapshot.

    Returns (records, classification_status).
    classification_status ∈ {"REAL", "PARTIAL_REAL", "FALLBACK_NEUTRAL"}.
    """
    if not top100_path.exists():
        logger.warning("top100 metadata missing — fallback to neutral (no cohort)")
        return [], "FALLBACK_NEUTRAL"

    top100: list[dict[str, Any]] = []
    with top100_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                top100.append(json.loads(line))

    cls_map: dict[str, dict[str, Any]] = {}
    if classified_path.exists():
        with classified_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = rec.get("ticker")
                st = rec.get("struct_tuple") or {}
                if t and st:
                    cls_map[t] = {
                        "critical_point_state": st.get("critical_point_state"),
                        "dynamics_family": st.get("dynamics_family"),
                        "confidence": st.get("confidence"),
                    }

    records: list[dict[str, Any]] = []
    matched = 0
    for c in top100:
        t = c.get("ticker")
        if not t:
            continue
        cls = cls_map.get(t)
        rec = dict(c)
        if cls:
            rec.update(cls)
            matched += 1
        else:
            rec["critical_point_state"] = None
        records.append(rec)

    if matched == 0:
        return records, "FALLBACK_NEUTRAL"
    if matched < len(records):
        return records, "PARTIAL_REAL"
    return records, "REAL"


def load_prices(prices_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load monthly close-price parquet. Returns (long_df, meta_dict)."""
    if not prices_path.exists():
        raise FileNotFoundError(
            f"prices parquet missing: {prices_path} — run "
            f"scripts/backtest_fetch_data_v0_2.py first"
        )
    df = pd.read_parquet(prices_path)
    if not {"date", "ticker", "close"}.issubset(df.columns):
        raise ValueError(f"unexpected parquet schema: {list(df.columns)}")
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

    meta_path = prices_path.parent / (prices_path.stem + ".meta.json")
    meta: dict[str, Any] = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return df, meta


# ----------------- Wide-form helpers -----------------

def long_to_wide(long_df: pd.DataFrame) -> pd.DataFrame:
    """Convert long-form (date,ticker,close) to wide (date × ticker)."""
    wide = long_df.pivot(index="date", columns="ticker", values="close").sort_index()
    return wide


def compute_monthly_returns(wide_prices: pd.DataFrame) -> pd.DataFrame:
    """Month-over-month simple returns. First row is NaN, dropped."""
    rets = wide_prices.pct_change(fill_method=None).iloc[1:]
    return rets


# ----------------- Backtest core -----------------

def cohort_from_classification(
    records: list[dict[str, Any]],
) -> list[str]:
    """Static cohort: tickers with critical_point_state ∈ {approaching_critical, at_critical}."""
    return sorted(
        r["ticker"]
        for r in records
        if r.get("critical_point_state") in NEAR_CRITICAL_STATES
    )


def run_walk_forward_static(
    cohort: list[str],
    monthly_rets: pd.DataFrame,
    benchmark: str = "SPY",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Walk-forward with a *static* cohort (single-snapshot classification).

    At each month, equal-weight whatever cohort members have price data
    that month. SPY return is the benchmark.
    """
    if benchmark not in monthly_rets.columns:
        raise ValueError(f"benchmark {benchmark} not in price universe")

    # Filter cohort to those with at least 1 price observation
    cohort_in_universe = [t for t in cohort if t in monthly_rets.columns]

    rows = []
    prev_holdings: set[str] = set()
    for date_idx, row in monthly_rets.iterrows():
        # Active = cohort members with a non-NaN return this month
        active = [t for t in cohort_in_universe if not pd.isna(row.get(t, np.nan))]
        if active:
            cohort_ret = float(np.mean([row[t] for t in active]))
        else:
            cohort_ret = 0.0  # cash-equivalent fallback
        spy_ret = row.get(benchmark, np.nan)
        if pd.isna(spy_ret):
            spy_ret = 0.0
        spy_ret = float(spy_ret)

        holdings = set(active)
        if not prev_holdings and not holdings:
            turnover = 0.0
        elif not prev_holdings:
            turnover = 1.0
        else:
            sym = prev_holdings.symmetric_difference(holdings)
            union = prev_holdings | holdings
            turnover = len(sym) / (2 * max(len(union), 1))
        prev_holdings = holdings

        rows.append({
            "date": date_idx,
            "month": pd.Timestamp(date_idx).strftime("%Y-%m"),
            "n_holdings": len(active),
            "cohort_return": cohort_ret,
            "spy_return": spy_ret,
            "active_return": cohort_ret - spy_ret,
            "turnover": round(turnover, 4),
        })

    rebalances = pd.DataFrame(rows)
    summary = _summarize(rebalances, cohort_size=len(cohort_in_universe))
    return rebalances, summary


# ----------------- Stats -----------------

def annualized_sharpe(rets: np.ndarray, periods_per_year: int = 12) -> float:
    if len(rets) < 2:
        return 0.0
    mu = float(np.mean(rets))
    sd = float(np.std(rets, ddof=0))
    if sd == 0:
        return 0.0
    return (mu / sd) * math.sqrt(periods_per_year)


def max_drawdown(rets: np.ndarray) -> float:
    """Max drawdown anchored at the strategy's start (wealth=1 pre-period).

    This matters for first-period crashes: a -50% first return should give
    a -50% drawdown (peak = 1.0 before any returns), not 0.
    """
    if len(rets) == 0:
        return 0.0
    # Prepend wealth=1 as the implicit peak before the strategy starts trading.
    wealth = np.concatenate([[1.0], np.cumprod(1.0 + np.asarray(rets, dtype=float))])
    peak = np.maximum.accumulate(wealth)
    dd = wealth / peak - 1.0
    return float(np.min(dd))


def cum_return(rets: np.ndarray) -> float:
    if len(rets) == 0:
        return 0.0
    return float(np.prod(1.0 + rets) - 1.0)


def capm_alpha_tstat(
    cohort_rets: np.ndarray,
    spy_rets: np.ndarray,
    periods_per_year: int = 12,
) -> dict[str, float]:
    """Simplified CAPM regression: r_c = α + β·r_spy + ε (no risk-free rate).

    Returns annualized alpha, beta, alpha t-stat, residual std, R².
    Assumes excess returns ≈ raw returns (rf ≈ 0 over the window for monthly).
    """
    if len(cohort_rets) < 6 or len(spy_rets) < 6:
        return {"alpha_annual": 0.0, "beta": 0.0, "alpha_tstat": 0.0,
                "r_squared": 0.0, "n_obs": int(len(cohort_rets))}
    x = np.asarray(spy_rets, dtype=float)
    y = np.asarray(cohort_rets, dtype=float)
    n = len(x)
    X = np.column_stack([np.ones(n), x])
    # OLS via normal eq
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    alpha_monthly, beta = float(coef[0]), float(coef[1])
    y_hat = X @ coef
    resid = y - y_hat
    rss = float(np.sum(resid ** 2))
    tss = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - rss / tss if tss > 0 else 0.0
    # SE of alpha
    dof = max(n - 2, 1)
    sigma2 = rss / dof
    XtX_inv = np.linalg.inv(X.T @ X)
    se_alpha = float(math.sqrt(sigma2 * XtX_inv[0, 0]))
    tstat = alpha_monthly / se_alpha if se_alpha > 0 else 0.0
    alpha_annual = alpha_monthly * periods_per_year  # arithmetic annualization
    return {
        "alpha_monthly": alpha_monthly,
        "alpha_annual": alpha_annual,
        "beta": beta,
        "alpha_tstat": tstat,
        "alpha_se_monthly": se_alpha,
        "r_squared": r2,
        "n_obs": int(n),
    }


def _summarize(rebalances: pd.DataFrame, cohort_size: int) -> dict[str, Any]:
    c = rebalances["cohort_return"].to_numpy()
    s = rebalances["spy_return"].to_numpy()
    cohort_sharpe = annualized_sharpe(c)
    spy_sharpe = annualized_sharpe(s)
    capm = capm_alpha_tstat(c, s)

    return {
        "n_rebalances": int(len(rebalances)),
        "cohort_size": int(cohort_size),
        "cohort_cum_return": cum_return(c),
        "spy_cum_return": cum_return(s),
        "cohort_sharpe": cohort_sharpe,
        "spy_sharpe": spy_sharpe,
        "sharpe_lift": cohort_sharpe - spy_sharpe,
        "cohort_max_drawdown": max_drawdown(c),
        "spy_max_drawdown": max_drawdown(s),
        "avg_turnover": float(rebalances["turnover"].mean()),
        "max_turnover": float(rebalances["turnover"].max()),
        "capm": capm,
    }


# ----------------- Verdict -----------------

def honest_verdict(sharpe_lift: float) -> dict[str, str]:
    """W7-D § 3 month-3 honest gate."""
    if sharpe_lift >= 0.5:
        return {
            "bucket": "alpha_confirmed",
            "headline": "alpha confirmed",
            "recommendation": (
                "Double down on alpha-screener positioning. Sharpe lift "
                "exceeds the +0.5 pre-committed bar."
            ),
        }
    if sharpe_lift < 0.3:
        return {
            "bucket": "alpha_not_confirmed",
            "headline": "alpha not confirmed",
            "recommendation": (
                "Pivot to structured research narrative positioning. "
                "Sharpe lift below the +0.3 floor — D1 classification does "
                "not show evidence of standalone alpha on this universe/window. "
                "Lean into transparent methodology + research-tool framing."
            ),
        }
    return {
        "bucket": "inconclusive",
        "headline": "inconclusive — extend evidence",
        "recommendation": (
            "Extend the evidence base before committing: expand to 200-ticker "
            "universe, push window back to 2015-2024, or wait for monthly "
            "ex-ante D1 snapshots (v0.3)."
        ),
    }


# ----------------- Charts -----------------

def render_charts(rebalances: pd.DataFrame, out_dir: Path, prefix: str) -> dict[str, str]:
    """Write three PNGs: cumulative return, drawdown, turnover bar."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    # 1. Cumulative return curve
    cw = (1.0 + rebalances["cohort_return"]).cumprod()
    sw = (1.0 + rebalances["spy_return"]).cumprod()
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(rebalances["date"], cw, label="Cohort (near_critical, equal-wt)", lw=2)
    ax.plot(rebalances["date"], sw, label="SPY benchmark", lw=2, alpha=0.85)
    ax.set_title(f"{prefix}: cumulative wealth 2020-2024")
    ax.set_ylabel("Wealth (start = 1.0)")
    ax.legend()
    ax.grid(alpha=0.3)
    p1 = out_dir / f"{prefix}-cumret.png"
    fig.tight_layout()
    fig.savefig(p1, dpi=120)
    plt.close(fig)
    paths["cumret"] = str(p1)

    # 2. Drawdown chart (anchored at wealth=1 before period 0)
    def _dd_path(rets):
        w = np.concatenate([[1.0], (1.0 + np.asarray(rets, dtype=float)).cumprod()])
        peak = np.maximum.accumulate(w)
        # Drop the seeded period-0 point so x-axis aligns with rebalances["date"]
        return (w / peak - 1.0)[1:]
    cdd = _dd_path(rebalances["cohort_return"])
    sdd = _dd_path(rebalances["spy_return"])
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.fill_between(rebalances["date"], cdd, 0, alpha=0.4, label="Cohort drawdown")
    ax.plot(rebalances["date"], sdd, lw=1.5, color="black", alpha=0.7, label="SPY drawdown")
    ax.set_title(f"{prefix}: drawdown profile")
    ax.set_ylabel("Drawdown")
    ax.legend()
    ax.grid(alpha=0.3)
    p2 = out_dir / f"{prefix}-drawdown.png"
    fig.tight_layout()
    fig.savefig(p2, dpi=120)
    plt.close(fig)
    paths["drawdown"] = str(p2)

    # 3. Turnover bar chart
    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.bar(rebalances["date"], rebalances["turnover"], width=20.0, alpha=0.7)
    ax.set_title(f"{prefix}: monthly one-way turnover")
    ax.set_ylabel("Turnover")
    ax.set_ylim(0, max(0.05, rebalances["turnover"].max() * 1.3))
    ax.grid(alpha=0.3)
    p3 = out_dir / f"{prefix}-turnover.png"
    fig.tight_layout()
    fig.savefig(p3, dpi=120)
    plt.close(fig)
    paths["turnover"] = str(p3)

    return paths


# ----------------- Report -----------------

def render_report_md(
    summary: dict[str, Any],
    rebalances: pd.DataFrame,
    cohort: list[str],
    cohort_records: list[dict[str, Any]],
    data_status: str,
    classification_status: str,
    prices_meta: dict[str, Any],
    verdict: dict[str, str],
    chart_paths: dict[str, str],
    start: str,
    end: str,
) -> str:
    s = summary
    capm = s["capm"]
    # Cohort breakdown by sector / family
    cohort_set = set(cohort)
    cohort_recs = [r for r in cohort_records if r["ticker"] in cohort_set]
    sectors: dict[str, int] = {}
    families: dict[str, int] = {}
    for r in cohort_recs:
        sectors[r.get("sector", "unknown")] = sectors.get(r.get("sector", "unknown"), 0) + 1
        families[r.get("dynamics_family", "unknown")] = families.get(r.get("dynamics_family", "unknown"), 0) + 1
    sect_str = ", ".join(f"{k} ({v})" for k, v in sorted(sectors.items(), key=lambda x: -x[1]))
    fam_str = ", ".join(f"{k} ({v})" for k, v in sorted(families.items(), key=lambda x: -x[1]))
    cohort_tickers_str = ", ".join(sorted(cohort))

    honesty = []
    if data_status != "REAL":
        honesty.append(
            f"> ⚠️ **Price data status: {data_status}.** Some tickers fell back to mock/missing — see meta JSON.\n"
        )
    honesty.append(
        "> ⚠️ **Classification is single-snapshot (2026-05-13), not monthly time-varying.** "
        "We apply a 2026-built D1 classifier ex-post to 2020-2024 returns. This is an "
        "ex-post *discriminative* test (does today's structural label correlate with "
        "past risk-adjusted returns?), not a true ex-ante forecast. For a clean walk-forward "
        "test we need monthly D1 snapshots at historical timestamps (deferred to v0.3).\n"
    )

    lines = [
        "# Walk-forward backtest v0.2 (real data)",
        "",
        f"_Window_: {start} → {end}",
        f"_Data source — prices_: **{data_status}** (yfinance, {prices_meta.get('n_top100_hits', '?')}/100 top tickers + SPY; "
        f"failed: {prices_meta.get('failed', [])})",
        f"_Data source — classification_: **{classification_status}** "
        f"(D1 single-snapshot {prices_meta.get('classified_as_of', '2026-05-13')})",
        f"_Rebalances_: {s['n_rebalances']} months",
        f"_Cohort_: {s['cohort_size']} tickers (near_critical = approaching_critical ∪ at_critical)",
        "",
        *honesty,
        "## Honest verdict (W7-D § 3 month-3 gate)",
        "",
        f"**{verdict['headline']}** — Sharpe lift = **{s['sharpe_lift']:+.2f}**",
        "",
        f"> {verdict['recommendation']}",
        "",
        "## Headline numbers",
        "",
        "| Metric | Cohort (`near_critical`) | SPY benchmark |",
        "|---|---:|---:|",
        f"| Cumulative return | {s['cohort_cum_return']*100:+.2f}% | {s['spy_cum_return']*100:+.2f}% |",
        f"| Annualized Sharpe | {s['cohort_sharpe']:+.2f} | {s['spy_sharpe']:+.2f} |",
        f"| Max drawdown | {s['cohort_max_drawdown']*100:+.2f}% | {s['spy_max_drawdown']*100:+.2f}% |",
        f"| Sharpe lift | **{s['sharpe_lift']:+.2f}** | — |",
        f"| Avg turnover / rebalance | **{s['avg_turnover']*100:.1f}%** | — |",
        f"| Max turnover | {s['max_turnover']*100:.1f}% | — |",
        "",
        "## CAPM alpha decomposition",
        "",
        "Simplified regression `r_cohort = α + β · r_SPY + ε` (no risk-free; monthly returns).",
        "",
        "| Quantity | Value |",
        "|---|---:|",
        f"| Alpha (monthly) | {capm.get('alpha_monthly', 0)*100:+.3f}% |",
        f"| Alpha (annualized, arithmetic) | **{capm['alpha_annual']*100:+.2f}%** |",
        f"| Alpha t-statistic | **{capm['alpha_tstat']:+.2f}** |",
        f"| Beta (vs SPY) | {capm['beta']:+.2f} |",
        f"| R² | {capm['r_squared']:.3f} |",
        f"| N (months) | {capm['n_obs']} |",
        "",
        "Interpretation guide:",
        "- |t| ≥ 2.0 → alpha statistically distinguishable from 0 at ~95% confidence",
        "- |t| < 1.0 → alpha indistinguishable from noise",
        "- v0.2 uses naive OLS SE (no Newey-West / no rolling); residuals likely autocorrelated",
        "",
        "## Reading guide — W7-D § 3 pre-commits",
        "",
        "| Outcome | Sharpe lift bar | Pre-committed response |",
        "|---|---|---|",
        "| Strong | ≥ +0.5 | Lean into alpha-screener positioning |",
        "| Inconclusive | +0.3 .. +0.5 | Extend evidence (200 tickers / 2015-2024 / monthly D1) |",
        "| Null | < +0.3 | Pivot to structured-research narrative |",
        "",
        "## Cohort composition (static, single-snapshot)",
        "",
        f"- Tickers ({len(cohort)}): {cohort_tickers_str}",
        f"- Sector mix: {sect_str}",
        f"- Dynamics family mix: {fam_str}",
        "",
        "## Pipeline notes",
        "",
        "- yfinance monthly close prices, auto-adjusted (handles splits/dividends)",
        "- Equal-weight monthly rebalance; cohort identity is constant (single-snapshot label)",
        "- Cash-equivalent fallback when cohort member missing a month (e.g., pre-IPO)",
        "- Turnover ≠ 0 only when cohort members enter/exit due to price-data availability",
        "- v0.2 limitations: no transaction costs, no shorts, no factor decomposition (FF / Carhart), no Newey-West SE",
        "",
        "## Charts",
        "",
        f"- Cumulative wealth: `{Path(chart_paths['cumret']).name}`",
        f"- Drawdown profile:  `{Path(chart_paths['drawdown']).name}`",
        f"- Turnover bar:      `{Path(chart_paths['turnover']).name}`",
        "",
        "## v0.3 roadmap",
        "",
        "- Produce monthly D1 snapshots at historical timestamps (2020-01..2024-12) → true ex-ante test",
        "- Carhart 4-factor regression (MKT / SMB / HML / MOM) for alpha attribution",
        "- Bootstrap CI on Sharpe lift + Newey-West SE on alpha",
        "- Sector-neutralized variant (long cohort / short sector-matched SPDR slice)",
        "- Universe expansion: 200 tickers, window 2015-2024",
    ]
    return "\n".join(lines) + "\n"


# ----------------- CLI -----------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Walk-forward backtest v0.2 (real data)")
    parser.add_argument("--prices", default=str(DEFAULT_PRICES))
    parser.add_argument("--top100", default=str(DEFAULT_TOP100))
    parser.add_argument("--classified", default=str(DEFAULT_CLASSIFIED))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--prefix", default="walk-forward-v0.2")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records, classification_status = load_top100_with_classification(
        Path(args.top100), Path(args.classified),
    )
    prices_long, prices_meta = load_prices(Path(args.prices))
    data_status = prices_meta.get("status", "UNKNOWN")

    # Restrict to window
    start_d = pd.Timestamp(args.start)
    end_d = pd.Timestamp(args.end)
    prices_long = prices_long[(prices_long["date"] >= start_d)
                              & (prices_long["date"] <= end_d)]

    wide = long_to_wide(prices_long)
    monthly_rets = compute_monthly_returns(wide)

    cohort = cohort_from_classification(records)
    logger.info("cohort size: %d / %d (near_critical)", len(cohort), len(records))

    rebalances, summary = run_walk_forward_static(cohort, monthly_rets)
    verdict = honest_verdict(summary["sharpe_lift"])

    # Charts
    chart_paths = render_charts(rebalances, out_dir, args.prefix)

    # JSON output
    rebalances_records = rebalances.copy()
    rebalances_records["date"] = rebalances_records["date"].dt.strftime("%Y-%m-%d")
    result = {
        "meta": {
            "version": "v0.2",
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "window_start": args.start,
            "window_end": args.end,
            "data_source_prices": data_status,
            "data_source_classification": classification_status,
            "n_companies_universe": len(records),
            "n_cohort": len(cohort),
            "prices_meta_snapshot": {
                "n_top100_hits": prices_meta.get("n_top100_hits"),
                "failed": prices_meta.get("failed", []),
                "spy_ok": prices_meta.get("spy_ok"),
            },
            "honest_caveats": [
                "D1 classification is single-snapshot (2026-05-13), not monthly time-varying",
                "This is an ex-post discriminative test, not a true ex-ante forecast",
                "True walk-forward requires monthly D1 snapshots at historical timestamps (v0.3)",
                "No transaction costs / no shorts / no factor decomposition",
                "OLS SE on alpha is naive (no Newey-West)",
            ],
        },
        "cohort": {
            "tickers": cohort,
            "size": len(cohort),
        },
        "rebalances": rebalances_records.to_dict(orient="records"),
        "summary": summary,
        "verdict": verdict,
        "chart_paths": {k: Path(v).name for k, v in chart_paths.items()},
    }
    json_path = out_dir / f"{args.prefix}.json"
    json_path.write_text(json.dumps(result, indent=2, default=_json_safe),
                         encoding="utf-8")

    # Markdown
    md_path = out_dir / f"{args.prefix}.md"
    md_path.write_text(
        render_report_md(
            summary=summary,
            rebalances=rebalances,
            cohort=cohort,
            cohort_records=records,
            data_status=data_status,
            classification_status=classification_status,
            prices_meta=prices_meta,
            verdict=verdict,
            chart_paths=chart_paths,
            start=args.start,
            end=args.end,
        ),
        encoding="utf-8",
    )

    logger.info(
        "v0.2 done. cohort=%d/100  sharpe_lift=%+.2f  alpha_annual=%+.2f%%  alpha_t=%+.2f  verdict=%s",
        len(cohort),
        summary["sharpe_lift"],
        summary["capm"]["alpha_annual"] * 100,
        summary["capm"]["alpha_tstat"],
        verdict["bucket"],
    )
    print(str(md_path))
    return 0


def _json_safe(o: Any) -> Any:
    """JSON encoder fallback for numpy types and Timestamp."""
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()
    raise TypeError(f"Type {type(o)} not JSON-serializable")


if __name__ == "__main__":
    sys.exit(main())
