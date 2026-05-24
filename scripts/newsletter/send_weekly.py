#!/usr/bin/env python3
"""Weekly newsletter pipeline (W8-D).

Pipeline:
    1. Read latest D1 batch (structtuples_*.jsonl) → current state.
    2. Read previous week's snapshot (last_week_state.json, persisted by this script).
    3. Diff: which tickers moved into / out of `near_critical`?
    4. Pick a spotlight company (highest extraction_confidence near_critical).
    5. Render the markdown template.
    6. Optionally send via Buttondown API (if BUTTONDOWN_API_KEY set + --send).

Usage:
    # Dry-run: emit markdown to stdout
    python scripts/newsletter/send_weekly.py --dry-run

    # Write to file (default: docs/newsletter/samples/digest-YYYY-MM-DD.md)
    python scripts/newsletter/send_weekly.py --out docs/newsletter/samples/

    # Send via Buttondown (requires BUTTONDOWN_API_KEY env)
    python scripts/newsletter/send_weekly.py --send

The "last week snapshot" lives at scripts/newsletter/state/last_week_state.json
and is updated on each successful run.

Cron entry (proposed, deploy when ready):
    0 22 * * 0  cd /root/Projects/structural-isomorphism && \\
                .venv/bin/python scripts/newsletter/send_weekly.py --send \\
                >> /var/log/newsletter.log 2>&1
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "v4" / "product" / "d1_phase_detector"
STATE_DIR = REPO_ROOT / "scripts" / "newsletter" / "state"
TEMPLATE = (
    REPO_ROOT / "docs" / "newsletter" / "templates" / "weekly-digest-template.md"
)
DEFAULT_OUT_DIR = REPO_ROOT / "docs" / "newsletter" / "samples"


def latest_structtuples_path() -> Path:
    """Find the most-recently-dated structtuples jsonl."""
    candidates = sorted(glob.glob(str(DATA_DIR / "structtuples_*.jsonl")))
    if not candidates:
        raise FileNotFoundError(
            f"no structtuples_*.jsonl found under {DATA_DIR}; run the D1 batch first"
        )
    return Path(candidates[-1])


def load_current_state(p: Path) -> dict[str, dict[str, Any]]:
    """Return ticker → {critical_point_state, dynamics_family, tldr, ...}."""
    out: dict[str, dict[str, Any]] = {}
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            st = rec.get("struct_tuple") or {}
            if not rec.get("ok") or not st:
                continue
            ticker = st.get("ticker") or rec.get("ticker")
            if not ticker:
                continue
            # Accept both schema variants for ergonomic field names.
            confidence = st.get("confidence_overall")
            if confidence is None and isinstance(st.get("confidence"), dict):
                confidence = st["confidence"].get("overall")
            elif confidence is None:
                confidence = st.get("confidence")
            tldr = st.get("tldr") or st.get("structural_summary") or ""
            out[ticker] = {
                "ticker": ticker,
                "name": st.get("company_name"),
                "sector": st.get("sector"),
                "dynamics_family": st.get("dynamics_family"),
                "critical_point_state": st.get("critical_point_state"),
                "confidence": confidence,
                "tldr": tldr,
            }
    return out


def load_last_week(state_dir: Path) -> dict[str, dict[str, Any]]:
    state_dir.mkdir(parents=True, exist_ok=True)
    p = state_dir / "last_week_state.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_state(state_dir: Path, current: dict[str, dict[str, Any]]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    p = state_dir / "last_week_state.json"
    p.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


# critical_point_state vocab is in flux across batches. Accept both v1
# (near_critical/subcritical/tipped) and v2 (approaching_critical/at_critical/
# post_critical_transition) labels. The newsletter cares about the "approaching"
# bucket regardless of exact label.
TIPPING_STATES = frozenset({"near_critical", "approaching_critical", "at_critical"})
STABLE_STATES = frozenset({"subcritical", "far_from_critical"})


def diff_states(
    last: dict[str, dict[str, Any]], current: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (entered_tipping, returned_to_stable).

    A "tipping" company has state in TIPPING_STATES; a "stable" company has
    state in STABLE_STATES. We classify a row as 'entered' if it became
    tipping this week (was stable or unknown last week), and 'returned' if
    it was tipping last week but is stable now.
    """
    entered: list[dict[str, Any]] = []
    returned: list[dict[str, Any]] = []
    for ticker, cur in current.items():
        prev = last.get(ticker)
        cur_state = (cur.get("critical_point_state") or "").lower()
        prev_state = (prev.get("critical_point_state") or "").lower() if prev else ""

        if cur_state in TIPPING_STATES and prev_state not in TIPPING_STATES:
            entered.append({**cur, "previous_state": prev_state or "unknown"})
        elif prev_state in TIPPING_STATES and cur_state in STABLE_STATES:
            returned.append({**cur, "previous_state": prev_state})
    # sort by ticker for deterministic output
    entered.sort(key=lambda r: r["ticker"])
    returned.sort(key=lambda r: r["ticker"])
    return entered, returned


def pick_spotlight(current: dict[str, dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Pick the highest-confidence 'tipping' company as spotlight."""
    candidates = [
        c
        for c in current.values()
        if (c.get("critical_point_state") or "").lower() in TIPPING_STATES
    ]
    candidates.sort(key=lambda r: r.get("confidence") or 0, reverse=True)
    return candidates[0] if candidates else None


def render_list(rows: list[dict[str, Any]], empty_msg: str) -> str:
    if not rows:
        return f"_{empty_msg}_"
    lines = []
    for r in rows:
        ticker = r["ticker"]
        name = r.get("name") or ticker
        family = r.get("dynamics_family") or "—"
        tldr = (r.get("tldr") or "").strip().replace("\n", " ")
        if len(tldr) > 220:
            tldr = tldr[:217] + "…"
        prev = r.get("previous_state") or "—"
        lines.append(
            f"- **{ticker}** ({name}) · `{family}` · was: `{prev}`\n"
            f"  > {tldr}"
        )
    return "\n".join(lines)


def render_spotlight(c: Optional[dict[str, Any]]) -> str:
    if not c:
        return "_No near-critical company this week — markets are sleepy._"
    name = c.get("name") or c["ticker"]
    tldr = (c.get("tldr") or "").strip().replace("\n", " ")
    return (
        f"**{c['ticker']} — {name}** (`{c.get('dynamics_family', '—')}`)\n\n"
        f"{tldr}"
    )


def render_digest(
    date: dt.date,
    entered: list[dict[str, Any]],
    returned: list[dict[str, Any]],
    spotlight: Optional[dict[str, Any]],
) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    spotlight_ticker = spotlight["ticker"] if spotlight else "—"
    spotlight_url = (
        f"https://phase.bytedance.city/company/{spotlight['ticker']}"
        if spotlight
        else "https://phase.bytedance.city"
    )
    return (
        template.replace("{date}", date.isoformat())
        .replace(
            "{tipping_list}",
            render_list(entered, "No new near-critical transitions this week."),
        )
        .replace(
            "{returning_list}",
            render_list(returned, "No companies dropped out of near-critical this week."),
        )
        .replace("{spotlight_ticker}", spotlight_ticker)
        .replace("{spotlight_paragraph}", render_spotlight(spotlight))
        .replace("{spotlight_url}", spotlight_url)
        .replace(
            "{reading_list}",
            (
                "- (Add 2-3 papers / blog posts per week here — TBD by the editor.)"
            ),
        )
        .replace(
            "{methodology_paragraph}",
            (
                "We use the same StructTuple schema for every company: a "
                "dynamics family (SOC / preferential attachment / fold / hysteresis / "
                "linear-quasi-equilibrium) and a critical-point state. The classification "
                "is LLM-extracted from public reports, then human-spot-checked."
            ),
        )
    )


def send_via_buttondown(markdown: str, subject: str) -> dict[str, Any]:
    """Send via Buttondown API. Requires BUTTONDOWN_API_KEY env."""
    api_key = os.environ.get("BUTTONDOWN_API_KEY")
    if not api_key:
        raise RuntimeError("BUTTONDOWN_API_KEY not set; cannot send")
    try:
        import httpx  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "httpx not installed; pip install httpx OR run with --dry-run"
        ) from e
    # https://docs.buttondown.email/api-emails-create
    res = httpx.post(
        "https://api.buttondown.email/v1/emails",
        headers={"Authorization": f"Token {api_key}"},
        json={
            "subject": subject,
            "body": markdown,
            "status": "about_to_send",
        },
        timeout=20.0,
    )
    res.raise_for_status()
    return res.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Weekly Structural Signals digest")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to structtuples jsonl (default: latest in v4/product/d1_phase_detector/)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Output directory (default: docs/newsletter/samples/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print to stdout instead of writing; do not send",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Send via Buttondown (requires BUTTONDOWN_API_KEY)",
    )
    parser.add_argument(
        "--no-state-update",
        action="store_true",
        help="Do not update last_week_state.json (useful for generating samples)",
    )
    args = parser.parse_args(argv)

    input_path = args.input or latest_structtuples_path()
    current = load_current_state(input_path)
    last_week = load_last_week(STATE_DIR)
    entered, returned = diff_states(last_week, current)
    spotlight = pick_spotlight(current)

    today = dt.date.today()
    digest = render_digest(today, entered, returned, spotlight)
    subject = f"Structural Signals — Week of {today.isoformat()}"

    if args.dry_run:
        sys.stdout.write(digest)
        return 0

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"digest-{today.isoformat()}.md"
    out_path.write_text(digest, encoding="utf-8")
    print(f"[ok] wrote {out_path}")

    if not args.no_state_update:
        write_state(STATE_DIR, current)
        print(f"[ok] updated last_week_state.json ({len(current)} tickers)")

    if args.send:
        resp = send_via_buttondown(digest, subject)
        print(f"[ok] sent via Buttondown: {resp.get('id', resp)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
