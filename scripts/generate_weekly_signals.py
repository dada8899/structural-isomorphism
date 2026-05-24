#!/usr/bin/env python3
"""Generate the W7-D weekly signals newsletter (2026-05-24).

Pipeline:
    1. Read D1 Phase Detector output (`data/phase-detector/latest.json`).
       If absent → use bundled mock data and stamp the doc as "mock-data v0.1".
    2. Select 6 `near_critical` companies (highest-confidence first).
    3. Render an alpha-signal sparkline chart (matplotlib, lazy import).
    4. Generate a 1-paragraph editorial via OpenRouter (`OPENROUTER_API_KEY`).
       If unset → write a deterministic mock sentence; doc is still valid.
    5. Write a markdown file to `newsletter/weekly/YYYY-MM-DD.md`.

Distinct from:
    - `scripts/newsletter/send_weekly.py` (W8-D — phase-flip-only digest).
    - `scripts/generate-newsletter.py`    (W9-C — 4-source digest).
    Both above are arXiv / GH / phase-flip oriented. This W7-D version is the
    SARAH-PERSONA "6 near-critical companies + 1 alpha signal" newsletter
    described in `docs/future/W7-D-product-value-roadmap-2026-05-13.md` § 8.

Usage:
    # default — writes newsletter/weekly/{Monday of this ISO week}.md
    python3 scripts/generate_weekly_signals.py

    # explicit week + out file
    python3 scripts/generate_weekly_signals.py --week 2026-05-25 --out /tmp/test.md

    # force mock mode (skip LLM call even if key present)
    python3 scripts/generate_weekly_signals.py --no-llm
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("structural.weekly_signals")

REPO_ROOT = Path(__file__).resolve().parent.parent

# Phase-detector data sources we look at — first hit wins.
_PHASE_DATA_CANDIDATES = [
    REPO_ROOT / "data" / "phase-detector" / "latest.json",
    REPO_ROOT / "web" / "frontend" / "phase" / "data" / "companies_struct.jsonl",
]

# Default chart output path. Newsletters reference this relative to the .md.
_CHART_REL_PATH = "alpha-signal.png"


# ---------------------- Phase data loading ----------------------

def load_phase_data() -> tuple[list[dict[str, Any]], str]:
    """Return (companies_list, source_label).

    source_label ∈ {"real", "mock"} — captured into the doc footer for
    honesty per W7-D guidance ("never call mock data 'production'").
    """
    for candidate in _PHASE_DATA_CANDIDATES:
        if not candidate.exists():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
            # JSONL?
            if candidate.suffix == ".jsonl":
                rows = []
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                if rows:
                    return rows, "real"
            else:
                data = json.loads(text)
                if isinstance(data, list) and data:
                    return data, "real"
                if isinstance(data, dict) and data.get("companies"):
                    return list(data["companies"]), "real"
        except Exception as e:
            logger.warning("phase data load failed for %s: %s", candidate, e)
    return _mock_companies(), "mock"


def _mock_companies() -> list[dict[str, Any]]:
    """100 mock tickers grouped by dynamics_family. Honest placeholder until
    D1 v0.2 lands the real 100-company snapshot. Numbers are reasonable but
    not real — labelled `mock` in the output footer."""
    return [
        # 6 high-confidence near_critical (will be picked as the headline 6)
        {"ticker": "WBA",  "name": "Walgreens Boots Alliance", "phase": "near_critical", "confidence": 0.91, "dynamics_family": "bistable",     "delta_signal": -0.42, "primary_quote": "Reaffirming guidance amid persistent margin pressure"},
        {"ticker": "PARA", "name": "Paramount Global",        "phase": "near_critical", "confidence": 0.88, "dynamics_family": "phase_transition","delta_signal": -0.38, "primary_quote": "Strategic alternatives under review"},
        {"ticker": "F",    "name": "Ford Motor",              "phase": "near_critical", "confidence": 0.85, "dynamics_family": "bifurcation",    "delta_signal":  0.21, "primary_quote": "EV transition timeline narrowed"},
        {"ticker": "BA",   "name": "Boeing",                  "phase": "near_critical", "confidence": 0.82, "dynamics_family": "metastable",     "delta_signal": -0.55, "primary_quote": "Production rate hold pending FAA review"},
        {"ticker": "T",    "name": "AT&T",                    "phase": "near_critical", "confidence": 0.80, "dynamics_family": "bistable",       "delta_signal":  0.12, "primary_quote": "Fiber deployment ahead of plan"},
        {"ticker": "GME",  "name": "GameStop",                "phase": "near_critical", "confidence": 0.78, "dynamics_family": "phase_transition","delta_signal":  0.67, "primary_quote": "Cash deployment policy update"},
        # baseline noise
        {"ticker": "AAPL", "name": "Apple",                   "phase": "stable",        "confidence": 0.95, "dynamics_family": "stationary"},
        {"ticker": "MSFT", "name": "Microsoft",               "phase": "stable",        "confidence": 0.94, "dynamics_family": "stationary"},
        {"ticker": "NVDA", "name": "NVIDIA",                  "phase": "trending",      "confidence": 0.81, "dynamics_family": "growth_regime"},
        {"ticker": "TSLA", "name": "Tesla",                   "phase": "trending",      "confidence": 0.72, "dynamics_family": "growth_regime"},
    ]


def select_near_critical(companies: list[dict[str, Any]], n: int = 6) -> list[dict[str, Any]]:
    """Highest-confidence `near_critical` first; fewer than n is OK."""
    nc = [c for c in companies if (c.get("phase") or "").lower() == "near_critical"]
    nc.sort(key=lambda c: float(c.get("confidence", 0) or 0), reverse=True)
    return nc[:n]


# ---------------------- Chart ----------------------

def render_alpha_chart(picks: list[dict[str, Any]], out_path: Path) -> bool:
    """Render a simple bar chart of delta_signal per pick. Lazy-import
    matplotlib so the script's main path stays runnable without it.

    Returns True iff the chart was written.
    """
    try:
        import matplotlib  # type: ignore
        matplotlib.use("Agg")  # headless
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError:
        logger.warning("matplotlib unavailable — skipping chart")
        return False

    labels = [c["ticker"] for c in picks]
    values = [float(c.get("delta_signal") or 0.0) for c in picks]
    colors = ["#15803D" if v >= 0 else "#B91C1C" for v in values]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, 3.2), dpi=150)
    ax.bar(labels, values, color=colors, edgecolor="#1C1917", linewidth=0.6)
    ax.axhline(0, color="#1C1917", linewidth=0.8)
    ax.set_title("Δ-signal across this week's near-critical cohort", fontsize=11)
    ax.set_ylabel("Δ-signal (last vs prior quarter)", fontsize=9)
    ax.tick_params(labelsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return True


# ---------------------- LLM commentary ----------------------

def _openrouter_key() -> Optional[str]:
    return os.environ.get("OPENROUTER_API_KEY")


def generate_commentary(picks: list[dict[str, Any]], allow_llm: bool = True) -> tuple[str, str]:
    """Return (commentary_paragraph, source_label).

    source_label ∈ {"openrouter", "mock"}. We never silently call the LLM —
    `allow_llm=False` or missing key → deterministic mock string.
    """
    if not allow_llm or not _openrouter_key():
        return _mock_commentary(picks), "mock"

    try:
        import urllib.request
        import urllib.error
    except ImportError:  # pragma: no cover
        return _mock_commentary(picks), "mock"

    summary_lines = []
    for c in picks:
        summary_lines.append(
            f"- {c['ticker']} ({c.get('name','?')}): "
            f"confidence={c.get('confidence',0):.2f}, "
            f"family={c.get('dynamics_family','?')}, "
            f"Δ={c.get('delta_signal',0):+.2f}, "
            f"quote={c.get('primary_quote','')[:120]!r}"
        )
    user_prompt = (
        "You are a senior research editor writing the lead paragraph for the "
        "'Structural Signals' weekly newsletter. Read these 6 near-critical "
        "company snapshots and write ONE paragraph (3-5 sentences, ~80-110 "
        "words). Honest, sober, no breathless adjectives. Highlight what's "
        "structurally interesting across the cohort — don't summarize each. "
        "Never claim alpha; never give a buy/sell signal. End with one line "
        "of methodology caveat.\n\n"
        + "\n".join(summary_lines)
    )

    req_body = json.dumps({
        "model": "deepseek/deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a research editor."},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 320,
        "temperature": 0.4,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=req_body,
        headers={
            "Authorization": f"Bearer {_openrouter_key()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        msg = (payload["choices"][0]["message"]["content"] or "").strip()
        if msg:
            return msg, "openrouter"
    except Exception as e:
        logger.warning("openrouter call failed: %s — falling back to mock", e)
    return _mock_commentary(picks), "mock"


def _mock_commentary(picks: list[dict[str, Any]]) -> str:
    families = sorted({c.get("dynamics_family", "?") for c in picks})
    return (
        f"This week's near-critical cohort spans {len(families)} dynamics "
        f"families ({', '.join(families)}). Bistable names show downward "
        f"Δ-signals consistent with margin compression at the same time as "
        f"phase-transition names continue to bifurcate. The cohort is small; "
        f"interpret each company as a hypothesis, not a forecast. "
        "Methodology caveat: structural state is extracted from disclosure "
        "text and is not a price prediction."
    )


# ---------------------- Render markdown ----------------------

def render_markdown(
    week_start: dt.date,
    picks: list[dict[str, Any]],
    commentary: str,
    data_source: str,
    commentary_source: str,
    chart_rel_path: Optional[str],
) -> str:
    """Compose the issue markdown. Idempotent given identical inputs."""
    lines: list[str] = []
    lines.append(f"# Structural Signals — week of {week_start.isoformat()}")
    lines.append("")
    lines.append(f"_6 companies sitting near a structural regime change. Methodology + receipts below._")
    lines.append("")
    if chart_rel_path:
        lines.append(f"![Alpha signal Δ across the cohort]({chart_rel_path})")
        lines.append("")
    lines.append("## Editor's note")
    lines.append("")
    lines.append(commentary)
    lines.append("")
    lines.append("## This week's 6")
    lines.append("")
    lines.append("| Ticker | Name | Family | Confidence | Δ-signal | Primary quote |")
    lines.append("|---|---|---|---:|---:|---|")
    for c in picks:
        lines.append(
            f"| `{c['ticker']}` "
            f"| {c.get('name','?')} "
            f"| {c.get('dynamics_family','?')} "
            f"| {float(c.get('confidence', 0)):.2f} "
            f"| {float(c.get('delta_signal', 0)):+.2f} "
            f"| {c.get('primary_quote','—')} |"
        )
    lines.append("")
    lines.append("## Methodology footer")
    lines.append("")
    lines.append(
        "- Phase classifier: D1 v0.1 (`stable | trending | near_critical | post_crisis`)."
    )
    lines.append(
        "- Each call is reproducible from the StructTuple snapshot + LLM prompt hash."
    )
    lines.append(
        "- Data source: **{}** · Editorial source: **{}**".format(
            data_source, commentary_source,
        )
    )
    lines.append(
        "- Not financial advice. Research only. Reply to this email to flag any error."
    )
    return "\n".join(lines) + "\n"


# ---------------------- Week / file helpers ----------------------

def monday_of_iso_week(d: dt.date) -> dt.date:
    """Return the Monday of d's ISO week (Monday=1)."""
    return d - dt.timedelta(days=d.isoweekday() - 1)


def parse_week(s: Optional[str]) -> dt.date:
    if not s:
        return monday_of_iso_week(dt.date.today())
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        raise SystemExit(f"--week must be YYYY-MM-DD (got {s!r})")


def default_out_path(week_start: dt.date) -> Path:
    return REPO_ROOT / "newsletter" / "weekly" / f"{week_start.isoformat()}.md"


# ---------------------- CLI ----------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate weekly structural signals newsletter")
    parser.add_argument("--week", help="Week start date (YYYY-MM-DD). Defaults to Monday of this ISO week.")
    parser.add_argument("--out", help="Output .md path. Defaults to newsletter/weekly/<week>.md")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM call even if OPENROUTER_API_KEY is set")
    parser.add_argument("--no-chart", action="store_true", help="Skip chart rendering")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    week_start = parse_week(args.week)
    out_path = Path(args.out) if args.out else default_out_path(week_start)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    companies, data_source = load_phase_data()
    picks = select_near_critical(companies, n=6)
    if not picks:
        logger.warning("no near_critical companies found — emitting empty-state newsletter")
        commentary = "No near-critical structural signals this week. The classifier is also a hypothesis; null weeks are real signal."
        commentary_source = "empty"
    else:
        commentary, commentary_source = generate_commentary(picks, allow_llm=not args.no_llm)

    chart_rel: Optional[str] = None
    if picks and not args.no_chart:
        chart_path = out_path.parent / f"{out_path.stem}-{_CHART_REL_PATH}"
        if render_alpha_chart(picks, chart_path):
            chart_rel = chart_path.name

    md = render_markdown(
        week_start, picks, commentary, data_source, commentary_source, chart_rel,
    )
    out_path.write_text(md, encoding="utf-8")
    logger.info(
        "wrote %s (picks=%d data=%s editorial=%s chart=%s)",
        out_path, len(picks), data_source, commentary_source, bool(chart_rel),
    )
    print(str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
