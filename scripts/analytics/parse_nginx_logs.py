#!/usr/bin/env python3
"""Parse nginx combined-format access logs into a privacy-friendly weekly report.

Backup analytics while Plausible self-hosted instance is not yet deployed
(W4-B G3, 2026-05-13). Standalone — Python 3.8+, no third-party deps.

Usage:
    python3 parse_nginx_logs.py /var/log/nginx/access.log
    python3 parse_nginx_logs.py /var/log/nginx/access.log -o analytics/weekly_2026-05-13.md
    python3 parse_nginx_logs.py /var/log/nginx/access.log --days 7 --output -

Privacy:
    - IPs are hashed (sha256 truncated, daily-rotated salt) before uniqueness counting.
      Raw IPs never reach the output. Hash + day salt = each visitor uncorrelatable
      across days, which is fine for "rough unique visitors per day" + bad for
      session tracking (intentional).
    - User-Agent is bucketed (bot / mobile / desktop), never recorded verbatim.

Output: Markdown report covering N most recent days.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional, TextIO

# nginx default combined log format:
#   $remote_addr - $remote_user [$time_local] "$request"
#       $status $body_bytes_sent "$http_referer" "$http_user_agent"
LOG_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ '
    r'\[(?P<ts>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<path>\S+) \S+" '
    r'(?P<status>\d{3}) (?P<size>\S+) '
    r'"(?P<referer>[^"]*)" '
    r'"(?P<ua>[^"]*)"'
)

# Bot UA fingerprint — coarse, intentional. We just want to subtract them.
BOT_UA_RE = re.compile(
    r'bot|crawler|spider|slurp|bing|google|yahoo|duckduck|baidu|yandex|'
    r'curl|wget|python-requests|httpclient|scrapy|facebookexternalhit|'
    r'preview|monitor|uptimerobot|pingdom|ahrefs|semrush',
    re.IGNORECASE,
)
MOBILE_UA_RE = re.compile(r'mobile|android|iphone|ipad', re.IGNORECASE)

# Static-asset paths we don't count as "page views".
STATIC_EXT_RE = re.compile(
    r'\.(css|js|png|jpe?g|gif|svg|ico|woff2?|ttf|map|webp|avif)(\?|$)',
    re.IGNORECASE,
)


def _open_log(path: Path) -> TextIO:
    """Open a log file, transparently handling .gz."""
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def _parse_ts(raw: str) -> Optional[datetime]:
    """Parse nginx %d/%b/%Y:%H:%M:%S %z timestamps."""
    try:
        return datetime.strptime(raw, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None


def _hash_ip(ip: str, day_key: str) -> str:
    """Daily-rotated salted hash. Returns short hex (12 chars)."""
    salted = f"{day_key}|{ip}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()[:12]


def _classify_ua(ua: str) -> str:
    if BOT_UA_RE.search(ua):
        return "bot"
    if MOBILE_UA_RE.search(ua):
        return "mobile"
    return "desktop"


def _is_page(path: str) -> bool:
    """Heuristic: count only "page" requests, not static assets / API calls."""
    if STATIC_EXT_RE.search(path):
        return False
    if path.startswith("/api/") or path.startswith("/assets/"):
        return False
    return True


def _normalize_referer(ref: str) -> str:
    if not ref or ref == "-":
        return "(direct)"
    # strip query string for sanity
    return ref.split("?", 1)[0]


def parse_log(
    fp: TextIO,
    since: datetime,
) -> Iterator[dict]:
    """Yield parsed log records newer than `since`."""
    for line in fp:
        m = LOG_RE.match(line)
        if not m:
            continue
        ts = _parse_ts(m.group("ts"))
        if ts is None or ts < since:
            continue
        yield {
            "ts": ts,
            "ip": m.group("ip"),
            "method": m.group("method"),
            "path": m.group("path"),
            "status": int(m.group("status")),
            "referer": _normalize_referer(m.group("referer")),
            "ua": m.group("ua"),
        }


def aggregate(records: Iterable[dict]) -> dict:
    pages: Counter = Counter()
    referers: Counter = Counter()
    daily_uniques: dict[str, set] = defaultdict(set)
    daily_pageviews: Counter = Counter()
    ua_buckets: Counter = Counter()
    status_buckets: Counter = Counter()
    bot_hits = 0
    total_hits = 0

    for r in records:
        total_hits += 1
        status_buckets[f"{r['status'] // 100}xx"] += 1

        ua_kind = _classify_ua(r["ua"])
        if ua_kind == "bot":
            bot_hits += 1
            # bots still counted in 5xx etc but NOT in pageviews / uniques
            continue

        if r["method"] not in ("GET", "HEAD"):
            continue
        if not _is_page(r["path"]):
            continue
        if r["status"] >= 400:
            continue

        day_key = r["ts"].astimezone(timezone.utc).strftime("%Y-%m-%d")
        pages[r["path"]] += 1
        referers[r["referer"]] += 1
        daily_uniques[day_key].add(_hash_ip(r["ip"], day_key))
        daily_pageviews[day_key] += 1
        ua_buckets[ua_kind] += 1

    return {
        "pages": pages,
        "referers": referers,
        "daily_uniques": {k: len(v) for k, v in daily_uniques.items()},
        "daily_pageviews": dict(daily_pageviews),
        "ua_buckets": ua_buckets,
        "status_buckets": status_buckets,
        "bot_hits": bot_hits,
        "total_hits": total_hits,
    }


def render_markdown(agg: dict, since: datetime, until: datetime) -> str:
    lines: list[str] = []
    lines.append("# Nginx access log — weekly analytics")
    lines.append("")
    lines.append(
        f"Window: `{since.strftime('%Y-%m-%d')}` → `{until.strftime('%Y-%m-%d')}` "
        f"(UTC, {(until - since).days} days)"
    )
    lines.append("")
    lines.append("> Privacy: IPs hashed with day-rotated salt; bots excluded "
                 "from pageviews/uniques. See `parse_nginx_logs.py` header.")
    lines.append("")

    # daily table
    lines.append("## Daily traffic")
    lines.append("")
    lines.append("| Day | Pageviews | Unique visitors (est.) |")
    lines.append("|---|---:|---:|")
    days = sorted(set(agg["daily_pageviews"]) | set(agg["daily_uniques"]))
    for d in days:
        pv = agg["daily_pageviews"].get(d, 0)
        uv = agg["daily_uniques"].get(d, 0)
        lines.append(f"| {d} | {pv} | {uv} |")
    lines.append("")

    # top pages
    lines.append("## Top 10 pages")
    lines.append("")
    if agg["pages"]:
        lines.append("| # | Path | Hits |")
        lines.append("|---:|---|---:|")
        for i, (path, hits) in enumerate(agg["pages"].most_common(10), 1):
            lines.append(f"| {i} | `{path}` | {hits} |")
    else:
        lines.append("_no page requests in window_")
    lines.append("")

    # top referers
    lines.append("## Top 10 referers")
    lines.append("")
    if agg["referers"]:
        lines.append("| # | Referer | Hits |")
        lines.append("|---:|---|---:|")
        for i, (ref, hits) in enumerate(agg["referers"].most_common(10), 1):
            lines.append(f"| {i} | `{ref}` | {hits} |")
    else:
        lines.append("_no referers in window_")
    lines.append("")

    # UA + status breakdown
    lines.append("## Device & status mix")
    lines.append("")
    lines.append("| Bucket | Count |")
    lines.append("|---|---:|")
    for k in ("desktop", "mobile"):
        lines.append(f"| ua/{k} | {agg['ua_buckets'].get(k, 0)} |")
    for code, n in sorted(agg["status_buckets"].items()):
        lines.append(f"| status/{code} | {n} |")
    lines.append(f"| bot hits (filtered) | {agg['bot_hits']} |")
    lines.append(f"| total log lines parsed | {agg['total_hits']} |")
    lines.append("")

    return "\n".join(lines) + "\n"


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("log", type=Path, help="Path to nginx access log (.log or .gz)")
    p.add_argument(
        "--days", type=int, default=7,
        help="Window size in days (default 7)",
    )
    p.add_argument(
        "-o", "--output", default=None,
        help="Output markdown path. Use '-' for stdout. Default: "
             "analytics_weekly_<today>.md in current dir.",
    )
    args = p.parse_args(argv)

    if not args.log.exists():
        print(f"[parse_nginx_logs] log file not found: {args.log}", file=sys.stderr)
        return 2

    until = datetime.now(timezone.utc)
    since = until - timedelta(days=args.days)

    try:
        with _open_log(args.log) as fp:
            agg = aggregate(parse_log(fp, since))
    except OSError as exc:
        print(f"[parse_nginx_logs] read failed: {exc}", file=sys.stderr)
        return 3

    report = render_markdown(agg, since, until)

    if args.output == "-":
        sys.stdout.write(report)
        return 0

    out_path = Path(args.output) if args.output else Path(
        f"analytics_weekly_{until.strftime('%Y-%m-%d')}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"[parse_nginx_logs] wrote {out_path} "
          f"({agg['total_hits']} log lines, {len(agg['pages'])} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
