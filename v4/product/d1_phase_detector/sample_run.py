#!/usr/bin/env python3
"""D1 — Sample run: extract StructTuples for 5 diverse companies.

Picks 5 companies covering different expected dynamics families:
  - AAPL (preferential_attachment expected)
  - BBY  (scheffer_fold expected)
  - JPM  (motter_lai_cascade expected)
  - AIG  (motter_lai_cascade expected)
  - KO   (linear_quasi_equilibrium expected)

Makes REAL DeepSeek API calls (no mock). Writes results to
`sample_structtuples.jsonl` and prints per-company expected-vs-actual
verdicts. Also writes per-call usage / latency stats to
`sample_run_stats.json` for cost projection.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from extract_structtuple import extract_one, DEFAULT_MODEL  # noqa: E402


SAMPLE_TICKERS = ["AAPL", "BBY", "JPM", "AIG", "KO"]


def load_companies(path: Path) -> dict[str, dict]:
    by_ticker: dict[str, dict] = {}
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                by_ticker[row["ticker"]] = row
    return by_ticker


def main() -> int:
    companies_path = HERE / "companies.jsonl"
    out_path = HERE / "sample_structtuples.jsonl"
    stats_path = HERE / "sample_run_stats.json"

    by_ticker = load_companies(companies_path)
    missing = [t for t in SAMPLE_TICKERS if t not in by_ticker]
    if missing:
        print(f"[D1-sample] missing tickers in companies.jsonl: {missing}", file=sys.stderr)
        return 2

    results: list[dict] = []
    stats = {
        "model": DEFAULT_MODEL,
        "calls": [],
        "n_ok": 0,
        "n_fail": 0,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_elapsed_s": 0.0,
    }

    t_start = time.time()
    with out_path.open("w") as out:
        for ticker in SAMPLE_TICKERS:
            company = by_ticker[ticker]
            print(f"\n[D1-sample] === {ticker} ({company.get('company_name', '')}) ===", file=sys.stderr)
            print(
                f"             sector={company.get('sector')} "
                f"cap=${company.get('market_cap_bn_usd')}B "
                f"prior={company.get('expected_dynamics_family_a_priori')}",
                file=sys.stderr,
            )

            res = extract_one(company, model=DEFAULT_MODEL)
            record = {
                "ticker": ticker,
                "expected_dynamics_family_a_priori": company.get(
                    "expected_dynamics_family_a_priori"
                ),
                "ok": res["ok"],
                "attempts": res["attempts"],
                "elapsed_s": res["elapsed_s"],
                "usage": res["usage"],
                "struct_tuple": res["struct_tuple"],
                "errors": res["errors"],
            }
            results.append(record)
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()

            stats["calls"].append(
                {
                    "ticker": ticker,
                    "ok": res["ok"],
                    "attempts": res["attempts"],
                    "elapsed_s": res["elapsed_s"],
                    "prompt_tokens": (res["usage"] or {}).get("prompt_tokens"),
                    "completion_tokens": (res["usage"] or {}).get("completion_tokens"),
                    "total_tokens": (res["usage"] or {}).get("total_tokens"),
                }
            )

            if res["ok"]:
                stats["n_ok"] += 1
                if res["usage"]:
                    stats["total_prompt_tokens"] += res["usage"].get("prompt_tokens", 0) or 0
                    stats["total_completion_tokens"] += (
                        res["usage"].get("completion_tokens", 0) or 0
                    )
                stats["total_elapsed_s"] += res["elapsed_s"]
                st = res["struct_tuple"]
                exp = company.get("expected_dynamics_family_a_priori")
                actual = st["dynamics_family"]
                match = (
                    "MATCH" if exp == actual else ("(no prior)" if exp is None else "DIFFER")
                )
                print(
                    f"  -> family={actual} state={st['critical_point_state']} "
                    f"conf={st['confidence']:.2f} attempts={res['attempts']} "
                    f"elapsed={res['elapsed_s']:.1f}s [{match}]",
                    file=sys.stderr,
                )
                print(f"     summary: {st['structural_summary'][:200]}", file=sys.stderr)
            else:
                stats["n_fail"] += 1
                print(
                    f"  -> FAIL attempts={res['attempts']} errors={res['errors']}",
                    file=sys.stderr,
                )

    stats["wall_time_s"] = round(time.time() - t_start, 2)

    # Print expected-vs-actual matrix
    print("\n[D1-sample] === expected-vs-actual summary ===", file=sys.stderr)
    print(f"{'ticker':6s} {'expected':30s} {'actual':30s} {'match':10s} {'conf':5s}", file=sys.stderr)
    for r in results:
        if r["ok"]:
            exp = r["expected_dynamics_family_a_priori"] or "(none)"
            actual = r["struct_tuple"]["dynamics_family"]
            match = "MATCH" if exp == actual else "DIFFER"
            conf = f"{r['struct_tuple']['confidence']:.2f}"
        else:
            exp = r["expected_dynamics_family_a_priori"] or "(none)"
            actual = "FAIL"
            match = "-"
            conf = "-"
        print(f"{r['ticker']:6s} {exp:30s} {actual:30s} {match:10s} {conf:5s}", file=sys.stderr)

    # Aggregate stats
    if stats["n_ok"] > 0:
        stats["avg_prompt_tokens"] = stats["total_prompt_tokens"] / stats["n_ok"]
        stats["avg_completion_tokens"] = stats["total_completion_tokens"] / stats["n_ok"]
        stats["avg_elapsed_s"] = stats["total_elapsed_s"] / stats["n_ok"]
    else:
        stats["avg_prompt_tokens"] = 0
        stats["avg_completion_tokens"] = 0
        stats["avg_elapsed_s"] = 0

    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"\n[D1-sample] wrote {out_path}", file=sys.stderr)
    print(f"[D1-sample] wrote {stats_path}", file=sys.stderr)
    print(
        f"[D1-sample] avg prompt={stats['avg_prompt_tokens']:.0f}t  "
        f"completion={stats['avg_completion_tokens']:.0f}t  "
        f"latency={stats['avg_elapsed_s']:.1f}s",
        file=sys.stderr,
    )
    return 0 if stats["n_fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
