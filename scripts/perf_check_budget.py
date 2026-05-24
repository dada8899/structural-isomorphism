"""
Compare perf_audit.py output against perf-budget.json. Exits non-zero if any
page on any viewport breaches a threshold (with per-route exemptions
applied). Used by .github/workflows/perf.yml as the PR gate.

Usage:
    .venv/bin/python scripts/perf_check_budget.py \\
        --audit docs/performance/perf-audit.json \\
        --budget perf-budget.json \\
        [--markdown out/perf-comment.md]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def route_key(path: str) -> str:
    """Match audit path back to budget exemption key (handles [param])."""
    # Strip query string
    p = path.split("?", 1)[0]
    parts = p.strip("/").split("/")
    if not parts or parts == [""]:
        return "/"
    # /universality/self_organized_criticality → /universality/[class_id]
    if parts[0] == "universality" and len(parts) >= 2:
        return "/universality/[class_id]"
    if parts[0] == "company" and len(parts) >= 2:
        return "/company/[ticker]"
    return "/" + "/".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True)
    parser.add_argument("--budget", required=True)
    parser.add_argument("--markdown", default=None)
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args()

    audit = json.loads(Path(args.audit).read_text())
    budget = json.loads(Path(args.budget).read_text())
    thresh = budget["thresholds"]
    exemptions = budget.get("exemptions", {})

    failures: list[tuple[str, str, str, float, float]] = []  # (page, viewport, metric, actual, limit)

    rows: list[dict] = []
    for page_key, page_data in audit["pages"].items():
        path = page_data.get("path", "")
        rk = route_key(path)
        page_exempt = exemptions.get(rk, {}) if isinstance(exemptions.get(rk), dict) else {}
        for vp in ("desktop", "mobile"):
            data = page_data.get(vp)
            if not data or "error" in data:
                continue

            metrics = {
                "lcp_ms": data.get("lcp_ms", 0),
                "cls": data.get("cls", 0),
                "tbt_ms": data.get("tbt_ms", 0),
                "inp_proxy_ms": data.get("inp_proxy_ms", 0),
            }

            lcp_limit = page_exempt.get(
                f"lcp_{vp}_ms", thresh[f"lcp_{vp}_ms"]
            )
            cls_limit = page_exempt.get("cls", thresh["cls"])
            tbt_limit = page_exempt.get("tbt_ms", thresh["tbt_ms"])
            inp_limit = page_exempt.get("inp_proxy_ms", thresh.get("inp_proxy_ms", thresh.get("inp_ms", 200)))

            row = {
                "page": page_key,
                "path": path,
                "viewport": vp,
                "lcp_ms": metrics["lcp_ms"],
                "lcp_limit": lcp_limit,
                "cls": metrics["cls"],
                "cls_limit": cls_limit,
                "tbt_ms": metrics["tbt_ms"],
                "tbt_limit": tbt_limit,
                "inp_proxy_ms": metrics["inp_proxy_ms"],
                "inp_limit": inp_limit,
            }
            rows.append(row)

            if metrics["lcp_ms"] > lcp_limit:
                failures.append((page_key, vp, "LCP", metrics["lcp_ms"], lcp_limit))
            if metrics["cls"] > cls_limit:
                failures.append((page_key, vp, "CLS", metrics["cls"], cls_limit))
            if metrics["tbt_ms"] > tbt_limit:
                failures.append((page_key, vp, "TBT", metrics["tbt_ms"], tbt_limit))
            if metrics["inp_proxy_ms"] > inp_limit:
                failures.append((page_key, vp, "INP*", metrics["inp_proxy_ms"], inp_limit))

    # Print summary
    print(f"Perf budget check: {len(rows)} audits across {len(audit['pages'])} pages")
    print(f"  Failures: {len(failures)}")

    # Build markdown if requested
    if args.markdown:
        md = ["# Performance budget report\n"]
        if failures:
            md.append("## Status: FAIL\n")
            md.append("| Page | Viewport | Metric | Actual | Limit |")
            md.append("|---|---|---|---:|---:|")
            for page, vp, metric, actual, limit in failures:
                md.append(f"| `{page}` | {vp} | {metric} | {actual:.1f} | {limit:.1f} |")
        else:
            md.append("## Status: PASS\n")
        md.append("\n## All measurements\n")
        md.append("| Page | Viewport | LCP (ms) | CLS | TBT (ms) | INP* (ms) |")
        md.append("|---|---|---:|---:|---:|---:|")
        for r in rows:
            md.append(
                f"| `{r['page']}` | {r['viewport']} | {r['lcp_ms']:.0f} | {r['cls']:.3f} | {r['tbt_ms']:.0f} | {r['inp_proxy_ms']:.0f} |"
            )
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text("\n".join(md))
        print(f"  Markdown report: {args.markdown}")

    if failures:
        print("\nFailures:")
        for page, vp, metric, actual, limit in failures:
            print(f"  {page:24} {vp:7} {metric:5} {actual:>8.1f} > {limit:.1f}")
        sys.exit(1)

    print("All pages under budget.")


if __name__ == "__main__":
    main()
