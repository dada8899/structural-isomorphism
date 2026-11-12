"""Regression guard for scripts/perf_check_bundle.py route-line regex.

Captures real Next.js 14.2.x build output formats so the perf-budget CI
gate doesn't silently fail open the way it did pre-W13-B fix (root route
"/" and the "┌" tree corner were both unmatched by the original regex).

Test fixtures below are verbatim slices of `pnpm build` output from
Next.js 14.2.35 with the phase-detector app.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load scripts/perf_check_bundle.py without making scripts/ a package
_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "perf_check_bundle.py"
_spec = importlib.util.spec_from_file_location("perf_check_bundle", _SCRIPT_PATH)
_module = importlib.util.module_from_spec(_spec)
sys.modules["perf_check_bundle"] = _module
assert _spec.loader is not None
_spec.loader.exec_module(_module)

ROUTE_LINE = _module.ROUTE_LINE
to_kb = _module.to_kb
parse_build_log = _module.parse_build_log


# Verbatim Next.js 14.2.35 build output from `pnpm build` (W13-B perf gate).
# Includes root corner "┌", middle branches "├", terminator "└", and
# both static "○" and dynamic "ƒ" markers.
NEXT_14_2_35_FIXTURE = """\
Route (app)                              Size     First Load JS
┌ ○ /                                    4.17 kB         111 kB
├ ○ /_not-found                          161 B          87.6 kB
├ ○ /about                               803 B          96.9 kB
├ ○ /api/backtest-cumulative             0 B                0 B
├ ƒ /company/[ticker]                    6.01 kB         109 kB
├ ○ /compare                             3.48 kB         107 kB
├ ƒ /universality/[class_id]             8.06 kB         104 kB
└ ○ /zh                                  3.35 kB         110 kB
+ First Load JS shared by all            87.4 kB
  ├ chunks/4222-1c743b87bc386d54.js      31.7 kB
  └ other shared chunks (total)          2.08 kB


○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
"""


# Older Next.js 14.2.15 format — visually identical in this respect.
NEXT_14_2_15_FIXTURE = """\
Route (app)                              Size     First Load JS
┌ ○ /                                    3.50 kB         105 kB
├ ○ /pricing                             2.50 kB        98.0 kB
└ ƒ /admin/[id]                          1.20 kB         102 kB
+ First Load JS shared by all            85.0 kB
"""


def _parse_string(s: str):
    rows = []
    for line in s.splitlines():
        m = ROUTE_LINE.match(line.lstrip())
        if not m:
            continue
        route, route_size, route_unit, fl_size, fl_unit = m.groups()
        rows.append(
            (route, to_kb(float(route_size), route_unit), to_kb(float(fl_size), fl_unit))
        )
    return rows


def test_root_route_matches():
    """Root '/' route must be captured (regression: '\\S+' rejected lone /)."""
    rows = _parse_string(NEXT_14_2_35_FIXTURE)
    routes = [r for r, _, _ in rows]
    assert "/" in routes, f"missing '/' route, got: {routes}"


def test_root_corner_tree_char_matches():
    """The '┌' tree-corner char on the first row must not block matching."""
    line = "┌ ○ /                                    4.17 kB         111 kB"
    m = ROUTE_LINE.match(line.lstrip())
    assert m is not None, "'┌' corner char should be allowed by regex"
    assert m.group(1) == "/"


def test_dynamic_route_marker_matches():
    """Dynamic-route 'ƒ' marker must be recognised alongside static '○'."""
    line = "├ ƒ /company/[ticker]                    6.01 kB         109 kB"
    m = ROUTE_LINE.match(line.lstrip())
    assert m is not None
    assert m.group(1) == "/company/[ticker]"


def test_byte_unit_route_matches():
    """Routes with bytes (B) instead of kB on route size still match."""
    line = "├ ○ /_not-found                          161 B          87.6 kB"
    m = ROUTE_LINE.match(line.lstrip())
    assert m is not None
    route, sz, unit, fl, fl_unit = m.groups()
    assert (route, unit, fl_unit) == ("/_not-found", "B", "kB")
    assert to_kb(float(sz), unit) < 1.0  # 161 B = ~0.157 kB


def test_full_fixture_route_count():
    """Full 14.2.35 fixture should parse exactly 8 routes."""
    rows = _parse_string(NEXT_14_2_35_FIXTURE)
    assert len(rows) == 8, f"expected 8 routes, got {len(rows)}: {rows}"


def test_14_2_15_fixture_parses():
    """Older 14.2.15 format must still parse identically."""
    rows = _parse_string(NEXT_14_2_15_FIXTURE)
    routes = [r for r, _, _ in rows]
    assert routes == ["/", "/pricing", "/admin/[id]"], f"got {routes}"


def test_shared_chunk_lines_ignored():
    """'+ First Load JS shared by all' and chunk lines must NOT match."""
    noise = [
        "+ First Load JS shared by all            87.4 kB",
        "  ├ chunks/4222-1c743b87bc386d54.js      31.7 kB",
        "  └ other shared chunks (total)          2.08 kB",
        "○  (Static)   prerendered as static content",
        "ƒ  (Dynamic)  server-rendered on demand",
        "Route (app)                              Size     First Load JS",
    ]
    for line in noise:
        m = ROUTE_LINE.match(line.lstrip())
        assert m is None, f"line should NOT match but did: {line!r}"


def test_to_kb_conversions():
    assert to_kb(1024, "B") == 1.0
    assert to_kb(50, "kB") == 50.0
    assert to_kb(1, "MB") == 1024.0


def test_parse_build_log_file(tmp_path: Path):
    """End-to-end: parse_build_log on a temp file containing the fixture."""
    p = tmp_path / "build.log"
    p.write_text(NEXT_14_2_35_FIXTURE)
    rows = parse_build_log(p)
    assert len(rows) == 8
    # Root route must be there and have ~111 kB First Load JS
    root_rows = [r for r in rows if r[0] == "/"]
    assert len(root_rows) == 1
    assert 110.0 <= root_rows[0][2] <= 112.0
