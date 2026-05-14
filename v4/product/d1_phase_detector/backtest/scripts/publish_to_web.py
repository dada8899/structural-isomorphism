"""Convert the v0.1 1000-ticker result JSON + monthly CSV into the format
consumed by web/phase-detector/public/backtest/.

Produces:
  web/phase-detector/public/backtest/result.json    — page-compatible schema
  web/phase-detector/public/backtest/cumulative.csv — snapshot timeseries
  web/phase-detector/public/backtest/v0.1-1000.json — full v0.1 native schema
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", "..", ".."))
DEFAULT_PUBLIC = os.path.join(REPO_ROOT, "web", "phase-detector", "public", "backtest")
DEFAULT_RESULTS = os.path.join(SCRIPT_DIR, "..", "results")


def find_latest(results_dir: str, prefix: str) -> str | None:
    import glob
    files = sorted(glob.glob(os.path.join(results_dir, prefix)))
    return files[-1] if files else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default=DEFAULT_RESULTS)
    ap.add_argument("--public", default=DEFAULT_PUBLIC)
    ap.add_argument("--summary-json", default=None)
    ap.add_argument("--monthly-csv", default=None)
    args = ap.parse_args(argv)

    sj = args.summary_json or find_latest(args.results_dir, "v0.1-1000-universe-2*.json")
    mc = args.monthly_csv or find_latest(args.results_dir, "v0.1-monthly-1000-universe-2*.csv")
    if not sj or not mc:
        print("ERROR: could not find result files", file=sys.stderr)
        return 2
    print(f"Reading summary: {sj}")
    print(f"Reading monthly: {mc}")

    with open(sj, "r", encoding="utf-8") as f:
        summary = json.load(f)

    # Build legacy-compatible result.json schema
    s_nc = summary["stats"]["near_critical_llm"]
    s_oth = summary["stats"]["other_llm"]
    s_bench = summary["stats"]["benchmark_ew"]
    s_h_nc = summary["stats"]["near_critical_heuristic"]
    s_h_st = summary["stats"]["stable_heuristic"]
    p = summary["params"]

    legacy = {
        # legacy v0.2 schema (page reads these)
        "version": "0.1-1000ticker",
        "mode": "walk_forward",
        "snapshot_anchor": "2026-05-15",
        "period_months": p["hold_months"],
        "n_snapshots": s_bench.get("n_months", 0),
        # In v0.1 1000-ticker schema: cohort sizes (ticker counts), not obs counts.
        # near_critical_llm = 65 SP500 tickers tagged approaching_critical|at_critical
        # other_llm = 434 SP500 tickers tagged far_from_critical|post_critical_transition
        "n_near_critical": summary.get("cohort_counts", {}).get("near_critical_llm", 0),
        "n_other": summary.get("cohort_counts", {}).get("other_llm", 0),
        "mean_return_nc": s_nc.get("mean_monthly", 0.0),
        "mean_return_other": s_oth.get("mean_monthly", 0.0),
        "std_nc": s_nc.get("std_monthly", 0.0),
        "std_other": s_oth.get("std_monthly", 0.0),
        "sharpe_nc": s_nc.get("sharpe_annualised", float("nan")),
        "sharpe_other": s_oth.get("sharpe_annualised", float("nan")),
        "t_stat": s_nc.get("t_stat_vs_bench", float("nan")),
        "p_value": s_nc.get("p_value_vs_bench", float("nan")),
        "groups": {
            "near_critical": {
                "n": s_nc.get("n_months", 0),
                "mean": s_nc.get("mean_monthly", 0.0),
                "std": s_nc.get("std_monthly", 0.0),
                "sharpe": s_nc.get("sharpe_annualised", float("nan")),
            },
            "other": {
                "n": s_oth.get("n_months", 0),
                "mean": s_oth.get("mean_monthly", 0.0),
                "std": s_oth.get("std_monthly", 0.0),
                "sharpe": s_oth.get("sharpe_annualised", float("nan")),
            },
        },
        "ttest_welch": {
            "t": s_nc.get("t_stat_vs_bench", float("nan")),
            "p": s_nc.get("p_value_vs_bench", float("nan")),
        },
        "synthetic": False,
        "prices_meta": {
            "version": "0.1-1000ticker",
            "yfinance_tickers": p["n_universe_covered"],
            "stooq_tickers": 0,
            "synthetic_tickers": 0,
            "missing_tickers": p["n_universe_missing"],
            "synthetic": False,
            "all_synthetic": False,
            "start": p["start"],
            "end": p["end"],
            "period": "5y",
            "interval": "1d",
            "n_total_tickers": p["n_universe_input"],
            "n_universe_covered": p["n_universe_covered"],
            "generated_at": summary["generated_at"],
        },
        # NEW v0.1 fields layered on top
        "v01_extensions": {
            "engine": "walk_forward_1000ticker",
            "universe_composition": {
                "sp500": 500,
                "russell_supplement": 501,
                "total_input": p["n_universe_input"],
                "covered": p["n_universe_covered"],
                "coverage_pct": round(100 * p["n_universe_covered"] / p["n_universe_input"], 1),
            },
            "benchmark_ew": {
                "n_months": s_bench["n_months"],
                "mean_monthly": s_bench["mean_monthly"],
                "std_monthly": s_bench["std_monthly"],
                "sharpe_annualised": s_bench["sharpe_annualised"],
                "max_drawdown": s_bench["max_drawdown"],
                "hit_rate": s_bench["hit_rate"],
                "cumulative_return": s_bench["cumulative_return"],
            },
            "near_critical_llm": s_nc,
            "other_llm": s_oth,
            "near_critical_heuristic": s_h_nc,
            "stable_heuristic": s_h_st,
            "sharpe_lift": s_nc.get("sharpe_lift_vs_bench", float("nan")),
            "verdict": "null_result_pivot_to_research_narrative",
        },
        "last_updated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "generated_at": summary["generated_at"],
    }

    # Replace any NaN with null so JSON is valid
    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_clean(v) for v in o]
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            return None
        return o

    legacy = _clean(legacy)

    os.makedirs(args.public, exist_ok=True)
    out_main = os.path.join(args.public, "result.json")
    out_v01 = os.path.join(args.public, "v0.1-1000.json")
    with open(out_main, "w", encoding="utf-8") as f:
        json.dump(legacy, f, indent=2)
    with open(out_v01, "w", encoding="utf-8") as f:
        json.dump(_clean(summary), f, indent=2)
    print(f"Wrote {out_main}")
    print(f"Wrote {out_v01}")

    # Build cumulative.csv from monthly time-series (LLM near_critical + other + benchmark)
    cum_path = os.path.join(args.public, "cumulative.csv")
    cum_nc = 0.0
    cum_oth = 0.0
    cum_bench = 0.0
    with open(mc, "r", encoding="utf-8") as f, open(cum_path, "w", encoding="utf-8", newline="") as g:
        reader = csv.DictReader(f)
        w = csv.writer(g)
        w.writerow([
            "snapshot_date",
            "mean_nc_ret", "mean_other_ret", "mean_bench_ret",
            "n_nc", "n_other",
            "cum_nc_ret", "cum_other_ret", "cum_bench_ret",
        ])
        n = 0
        for row in reader:
            try:
                d = row["snapshot_date"]
                nc = float(row["near_critical_llm_ret"]) if row["near_critical_llm_ret"] else float("nan")
                oth = float(row["other_llm_ret"]) if row["other_llm_ret"] else float("nan")
                bench = float(row["benchmark_ew_ret"]) if row["benchmark_ew_ret"] else float("nan")
                n_nc = row["n_nc_llm"]
                n_oth = row["n_oth_llm"]
            except (KeyError, ValueError):
                continue
            if not math.isnan(nc):
                cum_nc = (1 + cum_nc) * (1 + nc) - 1
            if not math.isnan(oth):
                cum_oth = (1 + cum_oth) * (1 + oth) - 1
            if not math.isnan(bench):
                cum_bench = (1 + cum_bench) * (1 + bench) - 1
            w.writerow([
                d,
                f"{nc:.6f}" if not math.isnan(nc) else "",
                f"{oth:.6f}" if not math.isnan(oth) else "",
                f"{bench:.6f}" if not math.isnan(bench) else "",
                n_nc, n_oth,
                f"{cum_nc:.6f}",
                f"{cum_oth:.6f}",
                f"{cum_bench:.6f}",
            ])
            n += 1
    print(f"Wrote {cum_path} ({n} rows)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
