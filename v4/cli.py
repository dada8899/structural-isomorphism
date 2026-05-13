#!/usr/bin/env python3
"""structural-isomorphism v4 unified CLI.

A thin dispatch layer over v4/validation/<phase>/*.py analyze scripts.
The underlying scripts are not modified — this just wraps them and
adds `list` / `status` / orchestration helpers.

Usage:
    python v4/cli.py list
    python v4/cli.py status
    python v4/cli.py validate <slug>
    python v4/cli.py validate --all
    python v4/cli.py collapse
    python v4/cli.py calibrate
    python v4/cli.py critic
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO = Path(__file__).resolve().parent.parent
V4 = REPO / "v4"
VAL = V4 / "validation"
RESULTS = V4 / "results"
SCRIPTS = V4 / "scripts"
LIB = V4 / "lib"


# ---------------------------------------------------------------------------
# Phase registry
# ---------------------------------------------------------------------------
#
# Each phase points at:
#   dir       — subdir under v4/validation/
#   scripts   — ordered list of analyze scripts to run when `v4 validate <slug>`
#   results   — primary results JSON file(s) read by `v4 status`
#   label     — human-readable phase label
#
# Note: a few phases don't have a single canonical analyze.py:
#   - earthquake: Gutenberg-Richter fit + Omori decay split into 2 scripts
#   - stockmarket: single combined fetch_and_analyze.py
#   - neural: extract_nwb_avalanches.py then analyze_avalanches.py
#   - null-controls: generate_and_analyze.py
# ---------------------------------------------------------------------------

PHASES: dict[str, dict[str, Any]] = {
    "earthquake": {
        "dir": "soc-earthquake",
        "scripts": ["gutenberg_richter.py", "omori_decay.py"],
        "results": ["gr_results.json", "omori_results.json"],
        "label": "Phase 1 — USGS earthquakes (Gutenberg-Richter + Omori)",
    },
    "stockmarket": {
        "dir": "soc-stockmarket",
        "scripts": ["fetch_and_analyze.py"],
        "results": ["gr_results.json", "omori_results.json"],
        "label": "Phase 2 — S&P 500 daily returns",
    },
    "defi": {
        "dir": "soc-defi",
        "scripts": ["analyze.py"],
        "results": ["gr_results.json", "omori_results.json", "multiprotocol_results.json"],
        "label": "Phase 3 — DeFi liquidations (Aave/Compound/Maker)",
    },
    "neural": {
        "dir": "soc-neural",
        "scripts": ["analyze_avalanches.py"],
        "results": ["neural_results.json"],
        "label": "Phase 4 — Neural avalanches (DANDI)",
    },
    "null-controls": {
        "dir": "null-controls",
        "scripts": ["generate_and_analyze.py"],
        "results": ["null_results.json"],
        "label": "Phase 5 — Null controls (synthetic non-SOC datasets)",
    },
    "github-stars": {
        "dir": "soc-github-stars",
        "scripts": ["analyze.py"],
        "results": ["github_results.json"],
        "label": "Phase 6 — GitHub repo stargazers (preferential attachment)",
    },
    "bank-failures": {
        "dir": "soc-bank-failures",
        "scripts": ["analyze.py"],
        "results": ["bank_results.json"],
        "label": "Phase 8 — FDIC US bank failures 1934-2026",
    },
    "wildfire": {
        "dir": "soc-wildfire",
        "scripts": ["analyze.py"],
        "results": ["wildfire_results.json"],
        "label": "Phase 10 — NIFC US wildfires 2010s-2024",
    },
    "solar": {
        "dir": "soc-solar",
        "scripts": ["analyze.py"],
        "results": ["solar_results.json"],
        "label": "Phase 11 — NOAA GOES solar flares",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def venv_python() -> str:
    """Pick the project venv Python if present, else fall back to sys.executable."""
    candidate = REPO / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def phase_dir(slug: str) -> Path:
    return VAL / PHASES[slug]["dir"]


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _first(*candidates: Any) -> Any:
    """Return the first non-None candidate."""
    for c in candidates:
        if c is not None:
            return c
    return None


def _extract_summary(slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort pull of (alpha, alpha_ci, n_total, n_tail, verdict)
    from a phase's primary results JSON.

    Different phases store these under different keys; we walk the
    common nesting points and pick the first match.
    """
    # candidate sub-objects that may hold the powerlaw fit
    fit_keys = [
        "powerlaw_fit",
        "clauset_fit",
        "clauset_powerlaw_fit",
        "powerlaw_fit_assets",
        "powerlaw_fit_peak_flux",
        "size_fit",
    ]
    fit: dict[str, Any] = {}
    for k in fit_keys:
        v = payload.get(k)
        if isinstance(v, dict):
            fit = v
            break

    alpha = _first(fit.get("alpha"), payload.get("alpha"), payload.get("b_value"))
    sigma_alpha = _first(fit.get("sigma_alpha"), payload.get("sigma_alpha"))
    n_total = _first(fit.get("n_total"), payload.get("n_total"), payload.get("n_total_events"),
                     payload.get("n_avalanches"), payload.get("n_failures"),
                     payload.get("n_total_fires"), payload.get("n_total_flares"),
                     payload.get("n_repos"))
    n_tail = _first(fit.get("n_tail"), payload.get("n_tail"))

    # bootstrap CI – multiple shapes
    alpha_ci = None
    bs = payload.get("bootstrap_ci") or fit.get("bootstrap_ci")
    if isinstance(bs, dict):
        lo = _first(bs.get("alpha_ci_lo"), bs.get("ci_lo"), bs.get("alpha_lo"))
        hi = _first(bs.get("alpha_ci_hi"), bs.get("ci_hi"), bs.get("alpha_hi"))
        if lo is not None and hi is not None:
            alpha_ci = (lo, hi)
    if alpha_ci is None and isinstance(payload.get("b_95_CI_bootstrap"), list):
        ci = payload["b_95_CI_bootstrap"]
        if len(ci) == 2:
            alpha_ci = tuple(ci)

    # verdict — phase-specific fallbacks
    verdict = payload.get("verdict")
    if verdict is None:
        if slug == "null-controls":
            verdict = payload.get("pipeline_robustness")
        elif "alpha_within_prediction" in payload:
            verdict = "CONFIRMED" if payload["alpha_within_prediction"] else "DEVIATING"

    return {
        "alpha": alpha,
        "sigma_alpha": sigma_alpha,
        "alpha_ci": alpha_ci,
        "n_total": n_total,
        "n_tail": n_tail,
        "verdict": verdict,
    }


def _fmt(v: Any, prec: int = 3) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, tuple) and len(v) == 2:
        return f"[{v[0]:.{prec}f}, {v[1]:.{prec}f}]"
    if isinstance(v, float):
        return f"{v:.{prec}f}"
    return str(v)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_list(_args: argparse.Namespace) -> int:
    print(f"Available phases ({len(PHASES)}):")
    print()
    for slug, meta in PHASES.items():
        print(f"  {slug:<14}  {meta['label']}")
        print(f"  {'':<14}  dir: v4/validation/{meta['dir']}")
        print(f"  {'':<14}  scripts: {', '.join(meta['scripts'])}")
        print()
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    print(f"v4 phase status (results dir: v4/validation/<phase>/)\n")
    header = f"{'phase':<14} {'alpha':>10} {'CI':>22} {'n_total':>10} {'n_tail':>8}  verdict"
    print(header)
    print("-" * len(header))

    parsed = 0
    for slug, meta in PHASES.items():
        # try each candidate results file, take first that loads
        payload: dict[str, Any] | None = None
        for r in meta["results"]:
            payload = _load_json(phase_dir(slug) / r)
            if payload is not None:
                break
        if payload is None:
            print(f"{slug:<14} {'N/A':>10} {'N/A':>22} {'N/A':>10} {'N/A':>8}  (no results.json)")
            continue
        s = _extract_summary(slug, payload)
        parsed += 1
        print(
            f"{slug:<14} "
            f"{_fmt(s['alpha']):>10} "
            f"{_fmt(s['alpha_ci']):>22} "
            f"{_fmt(s['n_total'], 0):>10} "
            f"{_fmt(s['n_tail'], 0):>8}  "
            f"{s['verdict'] or 'N/A'}"
        )

    print()
    b2 = RESULTS / "B2_calibration_summary.md"
    if b2.exists():
        print(f"B2 calibration summary: {b2.relative_to(REPO)}  ({b2.stat().st_size} bytes)")
    print(f"Phases with parseable results: {parsed}/{len(PHASES)}")
    return 0


def _run_script(script_path: Path, cwd: Path) -> int:
    """Run an analyze script with the project venv + PYTHONPATH=v4/lib."""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{LIB}{os.pathsep}{existing}" if existing else str(LIB)

    print(f"\n>>> {script_path.relative_to(REPO)}  (cwd={cwd.relative_to(REPO)})")
    try:
        proc = subprocess.run(
            [venv_python(), str(script_path)],
            cwd=str(cwd),
            env=env,
        )
        return proc.returncode
    except FileNotFoundError as e:
        print(f"!! script missing: {e}", file=sys.stderr)
        return 127


def _validate_one(slug: str) -> int:
    meta = PHASES[slug]
    pdir = phase_dir(slug)
    if not pdir.exists():
        print(f"!! phase dir missing: {pdir}", file=sys.stderr)
        return 2

    rc_total = 0
    for script in meta["scripts"]:
        sp = pdir / script
        if not sp.exists():
            print(f"!! script not found: {sp.relative_to(REPO)}", file=sys.stderr)
            rc_total = max(rc_total, 2)
            continue
        rc = _run_script(sp, pdir)
        if rc != 0:
            print(f"!! {slug}/{script} exited non-zero: {rc}", file=sys.stderr)
            rc_total = max(rc_total, rc)

    # Quick check: did expected results files materialize?
    for r in meta["results"]:
        rp = pdir / r
        if rp.exists():
            print(f"   ✓ {rp.relative_to(REPO)} ({rp.stat().st_size} bytes)")
        else:
            print(f"   ! missing: {rp.relative_to(REPO)}", file=sys.stderr)
    return rc_total


def cmd_validate(args: argparse.Namespace) -> int:
    if args.all:
        rc = 0
        for slug in PHASES:
            print(f"\n========== {slug} ==========")
            rc = max(rc, _validate_one(slug))
        return rc

    slug = args.slug
    if slug is None:
        print("error: provide <slug> or --all", file=sys.stderr)
        print(f"available slugs: {', '.join(PHASES)}", file=sys.stderr)
        return 2
    if slug not in PHASES:
        print(f"error: unknown phase '{slug}'", file=sys.stderr)
        print(f"available slugs: {', '.join(PHASES)}", file=sys.stderr)
        return 2

    return _validate_one(slug)


def cmd_collapse(_args: argparse.Namespace) -> int:
    sp = SCRIPTS / "universal_collapse.py"
    if not sp.exists():
        print(f"!! script not found: {sp.relative_to(REPO)}", file=sys.stderr)
        return 2
    return _run_script(sp, REPO)


def cmd_calibrate(_args: argparse.Namespace) -> int:
    sp = SCRIPTS / "calibrate_predictions_ci.py"
    if not sp.exists():
        print(f"!! script not found: {sp.relative_to(REPO)}", file=sys.stderr)
        return 2
    return _run_script(sp, REPO)


def cmd_critic(_args: argparse.Namespace) -> int:
    # Prefer printing the latest summary if it exists (LLM critic produces
    # layer3_critic_summary.md). No-LLM fallback = just show the summary.
    summary = RESULTS / "layer3_critic_summary.md"
    if summary.exists():
        print(f"# {summary.relative_to(REPO)}\n")
        try:
            print(summary.read_text(encoding="utf-8"))
        except OSError as e:
            print(f"!! failed to read {summary}: {e}", file=sys.stderr)
            return 1
        return 0

    print(
        "No B1 critic summary found at v4/results/layer3_critic_summary.md.\n"
        "Run the layer-3 critic pipeline first (LLM call, not wrapped here).",
        file=sys.stderr,
    )
    return 2


# ---------------------------------------------------------------------------
# Argparse entrypoint
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="v4",
        description="structural-isomorphism v4 unified CLI (validation phase runner + status).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list available validation phases").set_defaults(func=cmd_list)
    sub.add_parser("status", help="show latest verdict + α for each phase").set_defaults(func=cmd_status)

    pv = sub.add_parser("validate", help="run a phase's analyze script(s)")
    pv.add_argument("slug", nargs="?", help="phase slug (see `v4 list`)")
    pv.add_argument("--all", action="store_true", help="run every phase serially")
    pv.set_defaults(func=cmd_validate)

    sub.add_parser("collapse", help="run v4/scripts/universal_collapse.py").set_defaults(func=cmd_collapse)
    sub.add_parser("calibrate", help="run v4/scripts/calibrate_predictions_ci.py").set_defaults(func=cmd_calibrate)
    sub.add_parser("critic", help="print latest B1 critic summary").set_defaults(func=cmd_critic)

    return p


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
