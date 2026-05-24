#!/usr/bin/env python3
"""Generate a weekly newsletter markdown file (W9-C).

Sibling-script to scripts/newsletter/send_weekly.py:
    - send_weekly.py (W8-D): phase-flip-only digest, sent via Buttondown.
    - generate-newsletter.py (W9-C): 4-source digest (phase flips + arxiv +
      GH activity + methodology spotlight). Pipeline-only — no real send;
      CI opens a PR that humans review before publishing.

Usage:
    python scripts/generate-newsletter.py --week 2026-W19 --out docs/community/newsletters/issue-001.md
    python scripts/generate-newsletter.py --week 2026-W19 --dry-run
    python scripts/generate-newsletter.py --week 2026-W19 --spotlight ews-variance-autocorr
    python scripts/generate-newsletter.py --list-spotlights

Idempotency: same `--week` + same upstream inputs ⇒ byte-identical output.
We always parameterise *week start* (Monday of the ISO week) and never call
datetime.now() in the rendering path.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import sys
from pathlib import Path
from typing import Any, Optional

# Allow `python scripts/generate-newsletter.py` from anywhere — add this
# script's directory to sys.path so `newsletter_data_sources` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from newsletter_data_sources import (  # noqa: E402
    all_spotlight_slugs,
    fetch_arxiv_papers,
    fetch_github_activity,
    fetch_phase_flips,
    fetch_top_ask_queries,
    methodology_spotlight,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = REPO_ROOT / "docs" / "community" / "newsletters" / "template.md"

logger = logging.getLogger("newsletter.generate")


# ---------------------------------------------------------------------------
# Week-label parsing
# ---------------------------------------------------------------------------

_WEEK_RE = re.compile(r"^(\d{4})-W(\d{1,2})$")


def parse_iso_week(week_label: str) -> dt.date:
    """Parse '2026-W19' → Monday of that ISO week (as a date)."""
    m = _WEEK_RE.match(week_label.strip())
    if not m:
        raise ValueError(
            f"--week must be YYYY-Www (e.g. 2026-W19); got {week_label!r}"
        )
    year, week = int(m.group(1)), int(m.group(2))
    if not (1 <= week <= 53):
        raise ValueError(f"ISO week must be 1..53; got {week}")
    # Python 3.8+ supports date.fromisocalendar
    try:
        return dt.date.fromisocalendar(year, week, 1)
    except ValueError as e:
        raise ValueError(f"invalid ISO week {week_label}: {e}") from e


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_phase_flips_section(flips: list[dict[str, Any]]) -> str:
    if not flips:
        return (
            "_No high-confidence structural flips detected this week — markets "
            "are sleepy, or the next D1 batch hasn't landed yet._"
        )
    lines: list[str] = []
    for r in flips:
        tldr = (r.get("tldr") or "").strip()
        if len(tldr) > 240:
            tldr = tldr[:237] + "…"
        conf = r.get("confidence") or 0.0
        lines.append(
            f"- **{r['ticker']}** ({r.get('name', '?')}) · "
            f"`{r['from_state']}` → `{r['to_state']}` · "
            f"`{r.get('dynamics_family', '—')}` · confidence {conf:.2f}"
        )
        if tldr:
            lines.append(f"  > {tldr}")
    return "\n".join(lines)


def render_arxiv_section(papers: list[dict[str, Any]]) -> str:
    if not papers:
        return (
            "_No new preprints matched our SOC + universality query this week. "
            "(arXiv API may have been rate-limited; we'll catch up next week.)_"
        )
    lines: list[str] = []
    for p in papers:
        authors = p.get("authors") or []
        author_str = ", ".join(authors[:3])
        if len(authors) > 3:
            author_str += " et al."
        if not author_str:
            author_str = "(authors unavailable)"
        title = p.get("title", "(untitled)")
        url = p.get("url", "")
        one_liner = p.get("abstract_one_liner", "")
        lines.append(f"- [{title}]({url}) — *{author_str}*")
        if one_liner:
            lines.append(f"  > {one_liner}")
    return "\n".join(lines)


def render_github_section(activity: dict[str, int]) -> str:
    parts: list[str] = []
    total_stars = activity.get("total_stars", 0)
    total_forks = activity.get("total_forks", 0)
    new_issues = activity.get("new_issues", 0)
    new_prs = activity.get("new_prs_external", 0)

    parts.append(f"- ⭐ {total_stars} total stars · 🍴 {total_forks} forks")
    parts.append(f"- 📝 {new_issues} new issues this week")
    parts.append(f"- 🔀 {new_prs} external PRs this week")
    if total_stars == 0 and total_forks == 0 and new_issues == 0 and new_prs == 0:
        parts.append(
            "  _(numbers come from `gh api`; if zeros across the board, the "
            "gh CLI may be unauthenticated in CI — see workflow logs.)_"
        )
    return "\n".join(parts)


def render_ask_section(queries: list[dict[str, Any]]) -> str:
    if not queries:
        return (
            "_/api/ask query analytics are server-side and not yet exposed "
            "via the public API. Coming in W10._"
        )
    lines: list[str] = []
    for q in queries[:10]:
        lines.append(f"- _{q.get('query', '?')}_ ({q.get('count', 0)} asks)")
    return "\n".join(lines)


def render(
    template_text: str,
    *,
    week_label: str,
    week_start: dt.date,
    flips: list[dict[str, Any]],
    papers: list[dict[str, Any]],
    activity: dict[str, int],
    spotlight: dict[str, str],
    ask_queries: list[dict[str, Any]],
) -> str:
    """Substitute {{placeholders}} in the template.

    Whitespace-tolerant: `{{key}}`, `{{ key }}`, `{{  key }}` all match.
    """
    substitutions = {
        "week_label": week_label,
        "week_start": week_start.isoformat(),
        "week_end": (week_start + dt.timedelta(days=6)).isoformat(),
        "phase_flips_section": render_phase_flips_section(flips),
        "arxiv_section": render_arxiv_section(papers),
        "github_section": render_github_section(activity),
        "ask_section": render_ask_section(ask_queries),
        "spotlight_title": spotlight.get("title", ""),
        "spotlight_id": spotlight.get("id", ""),
        "spotlight_body": spotlight.get("body", ""),
    }

    def _replace(m: re.Match[str]) -> str:
        key = m.group(1).strip()
        if key not in substitutions:
            logger.warning("unknown template placeholder: %s", key)
            return m.group(0)
        return str(substitutions[key])

    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", _replace, template_text)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate Structural Signals weekly newsletter (W9-C)"
    )
    parser.add_argument(
        "--week",
        type=str,
        help="ISO week label (e.g. 2026-W19). Required unless --list-spotlights.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Output markdown path. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help=f"Template path (default: {DEFAULT_TEMPLATE.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--spotlight",
        type=str,
        default=None,
        help="Force a methodology spotlight slug (else auto-rotate by ISO week).",
    )
    parser.add_argument(
        "--phase-source",
        type=str,
        default=None,
        help="Phase data source: 'api' to hit live API, else file-diff. "
             "Default: auto-discover latest structtuples.",
    )
    parser.add_argument(
        "--phase-api-url",
        type=str,
        default="https://phase.bytedance.city/api/phases",
        help="Live phase API URL (used when --phase-source=api).",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default="dada8899/structural-isomorphism",
        help="GitHub repo slug for activity stats.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print to stdout regardless of --out (useful for previewing).",
    )
    parser.add_argument(
        "--list-spotlights",
        action="store_true",
        help="Print available methodology spotlight slugs and exit.",
    )
    parser.add_argument(
        "--skip-network",
        action="store_true",
        help="Skip arXiv + GitHub fetches; useful for CI smoke tests.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.list_spotlights:
        for slug in all_spotlight_slugs():
            print(slug)
        return 0

    if not args.week:
        parser.error("--week is required (unless using --list-spotlights)")

    try:
        week_start = parse_iso_week(args.week)
    except ValueError as e:
        parser.error(str(e))

    logger.info("generating newsletter for %s (week starts %s)", args.week, week_start)

    # --- Fetch each data source ---
    flips = fetch_phase_flips(
        api_url=(args.phase_api_url if args.phase_source == "api" else None),
    )
    logger.info("phase flips: %d", len(flips))

    if args.skip_network:
        papers: list[dict[str, Any]] = []
        activity: dict[str, int] = {
            "new_stars": 0,
            "total_stars": 0,
            "new_forks": 0,
            "total_forks": 0,
            "new_contributors": 0,
            "new_issues": 0,
            "new_prs_external": 0,
        }
    else:
        papers = fetch_arxiv_papers(week_start=week_start)
        logger.info("arxiv papers: %d", len(papers))
        activity = fetch_github_activity(repo=args.repo, week_start=week_start)
        logger.info("github activity: %s", activity)

    spotlight = methodology_spotlight(
        week_start=week_start,
        override_slug=args.spotlight,
    )
    logger.info("spotlight: %s", spotlight["id"])

    ask_queries = fetch_top_ask_queries(week_start=week_start)

    # --- Render ---
    if not args.template.exists():
        logger.error("template not found: %s", args.template)
        return 2

    template_text = args.template.read_text(encoding="utf-8")
    output = render(
        template_text,
        week_label=args.week,
        week_start=week_start,
        flips=flips,
        papers=papers,
        activity=activity,
        spotlight=spotlight,
        ask_queries=ask_queries,
    )

    # --- Emit ---
    if args.dry_run or args.out is None:
        sys.stdout.write(output)
        sys.stdout.flush()
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(output, encoding="utf-8")
    logger.info("wrote %s (%d bytes)", args.out, len(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
