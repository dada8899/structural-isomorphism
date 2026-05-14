"""
Verify Next.js build report (First Load JS per route) is under the
`first_load_js_kb` threshold from perf-budget.json.

Run AFTER `pnpm build` so .next/build-manifest.json + .next/app-build-manifest.json
exist. We parse the textual build output (captured to a file) since the
authoritative size numbers are emitted there.

Usage:
    pnpm build 2>&1 | tee /tmp/build.log
    .venv/bin/python scripts/perf_check_bundle.py \\
        --build-log /tmp/build.log --budget perf-budget.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROUTE_LINE = re.compile(
    r"^(?:├|└|│)?\s*[○ƒ]\s+(/\S+)\s+([0-9.]+)\s+(B|kB|MB)\s+([0-9.]+)\s+(B|kB|MB)"
)


def to_kb(value: float, unit: str) -> float:
    if unit == "B":
        return value / 1024
    if unit == "kB":
        return value
    if unit == "MB":
        return value * 1024
    return value


def parse_build_log(path: Path) -> list[tuple[str, float, float]]:
    """Return [(route, route_size_kb, first_load_js_kb), ...]."""
    rows: list[tuple[str, float, float]] = []
    for line in path.read_text().splitlines():
        m = ROUTE_LINE.match(line.lstrip())
        if not m:
            continue
        route, route_size, route_unit, fl_size, fl_unit = m.groups()
        rows.append(
            (route, to_kb(float(route_size), route_unit), to_kb(float(fl_size), fl_unit))
        )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-log", required=True)
    parser.add_argument("--budget", required=True)
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    rows = parse_build_log(Path(args.build_log))
    if not rows:
        print("No routes parsed from build log — pattern mismatch.", file=sys.stderr)
        sys.exit(2)

    budget = json.loads(Path(args.budget).read_text())
    limit = budget["thresholds"].get("first_load_js_kb", 200)

    failures = [(r, fl) for r, _, fl in rows if fl > limit]

    print(f"Parsed {len(rows)} routes from build log; budget {limit} kB")
    for route, route_kb, fl_kb in rows:
        flag = " FAIL" if fl_kb > limit else ""
        print(f"  {route:40} route={route_kb:>6.1f} kB  First Load JS={fl_kb:>6.1f} kB{flag}")

    if args.markdown:
        md = [f"# Bundle size check (budget: {limit} kB First Load JS)\n"]
        if failures:
            md.append("## Status: FAIL\n")
        else:
            md.append("## Status: PASS\n")
        md.append("| Route | Route size | First Load JS | Status |")
        md.append("|---|---:|---:|:---:|")
        for route, route_kb, fl_kb in rows:
            status = " FAIL" if fl_kb > limit else " OK"
            md.append(f"| `{route}` | {route_kb:.1f} kB | {fl_kb:.1f} kB | {status} |")
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text("\n".join(md))

    if failures:
        print(f"\n{len(failures)} routes over budget:")
        for route, fl_kb in failures:
            print(f"  {route}: {fl_kb:.1f} kB > {limit} kB")
        sys.exit(1)

    print("All routes under bundle budget.")


if __name__ == "__main__":
    main()
