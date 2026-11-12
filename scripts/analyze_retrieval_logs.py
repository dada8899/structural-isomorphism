"""Retrieval log analytics — quantitative view of the ask.retrieval log stream.

Reads `web/backend/logs/retrieval.jsonl` (one JSON object per line, produced by
`services.retrieval_pipeline.run_retrieval`) and emits:

  * a Markdown report   →  docs/observability/retrieval-analysis-<ts>.md
  * matplotlib figures  →  docs/observability/retrieval-analysis-<ts>/*.png

The log schema (see `_write_retrieval_log` in retrieval_pipeline.py):

    {
      "ts":               ISO-8601 UTC timestamp
      "event":            "ask.retrieval"
      "query_hash":       16-hex prefix of SHA-256(query) — privacy-preserving
      "query_len":        int, characters
      "lang_detected":    "zh" | "en" | "mixed" | other
      "expansion_used":   bool
      "translation_used": bool
      "candidate_count":  int, # of expansion variants (1 if no expansion)
      "total_recall":     int, sum |hits| across variants pre-fusion
      "fused_count":      int, post-fusion result count
      "top_5_kb_ids":     list[str], top-5 KB ids returned to caller
      "top_5_scores":     list[float], parallel to top_5_kb_ids
      "elapsed_ms":       int, end-to-end retrieval latency
    }

Usage
-----
    # Default: read web/backend/logs/retrieval.jsonl, write to docs/observability/
    PYTHONPATH=. .venv/bin/python scripts/analyze_retrieval_logs.py

    # Custom log path
    PYTHONPATH=. .venv/bin/python scripts/analyze_retrieval_logs.py \
        --log path/to/retrieval.jsonl

    # Custom output dir (will be created if missing)
    PYTHONPATH=. .venv/bin/python scripts/analyze_retrieval_logs.py \
        --out docs/observability/week-1

    # Skip figures (useful in CI where matplotlib backend may be absent)
    PYTHONPATH=. .venv/bin/python scripts/analyze_retrieval_logs.py --no-figures

Exit codes
----------
    0  — success
    1  — log file missing or empty
    2  — malformed log row(s)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = ROOT / "web" / "backend" / "logs" / "retrieval.jsonl"
DEFAULT_OUT = ROOT / "docs" / "observability"

logger = logging.getLogger("analyze_retrieval")


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        logger.error(f"Log file does not exist: {path}")
        return []
    rows: list[dict[str, Any]] = []
    n_bad = 0
    with open(path, encoding="utf-8") as f:
        for ln, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
                if rec.get("event") != "ask.retrieval":
                    # only consume rows from the retrieval pipeline
                    continue
                rows.append(rec)
            except json.JSONDecodeError as e:
                n_bad += 1
                logger.warning(f"{path}:{ln} malformed JSON: {e}")
    if n_bad:
        logger.warning(f"{n_bad} malformed log row(s) skipped")
    logger.info(f"Loaded {len(rows)} retrieval events from {path}")
    return rows


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def _pctile(xs: list[float], p: float) -> float:
    """Linear interpolation percentile. p in [0, 100]. Empty → nan."""
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = (len(s) - 1) * (p / 100.0)
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    if lo == hi:
        return float(s[lo])
    return float(s[lo] + (s[hi] - s[lo]) * (k - lo))


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"N": 0}

    lang_dist = Counter(r.get("lang_detected", "unknown") for r in rows)
    expansion_used = sum(1 for r in rows if r.get("expansion_used"))
    translation_used = sum(1 for r in rows if r.get("translation_used"))
    candidate_counts = [int(r.get("candidate_count", 0)) for r in rows]
    total_recall = [int(r.get("total_recall", 0)) for r in rows]
    fused_count = [int(r.get("fused_count", 0)) for r in rows]
    elapsed_ms = [int(r.get("elapsed_ms", 0)) for r in rows]
    query_len = [int(r.get("query_len", 0)) for r in rows]

    # Top-score distribution (rank-1 score)
    top1_scores = [
        float(r["top_5_scores"][0])
        for r in rows
        if isinstance(r.get("top_5_scores"), list) and r["top_5_scores"]
    ]
    # Score gap: top1 - top5 (proxy for "is the answer crisp or muddy")
    score_gaps: list[float] = []
    for r in rows:
        scores = r.get("top_5_scores") or []
        if len(scores) >= 5:
            try:
                score_gaps.append(float(scores[0]) - float(scores[4]))
            except (TypeError, ValueError):
                continue

    # Frequency of KB ids in top-5 (proxy for "are some entries swamping
    # the index? are we using the long tail?")
    top_ids: Counter[str] = Counter()
    rank_appearance: defaultdict[str, list[int]] = defaultdict(list)
    for r in rows:
        ids = r.get("top_5_kb_ids") or []
        for rank, kb_id in enumerate(ids, 1):
            if not kb_id:
                continue
            top_ids[kb_id] += 1
            rank_appearance[kb_id].append(rank)

    # Unique queries (by hash). Repeat-query rate is a UX signal.
    qhashes = [r.get("query_hash") for r in rows if r.get("query_hash")]
    qhash_dist = Counter(qhashes)
    repeat_share = (
        sum(1 for c in qhash_dist.values() if c > 1) / len(qhash_dist)
        if qhash_dist else 0.0
    )

    # Daily volume (UTC date bucketing).
    by_day: Counter[str] = Counter()
    for r in rows:
        ts = r.get("ts", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            by_day[dt.astimezone(timezone.utc).date().isoformat()] += 1
        except (ValueError, AttributeError):
            by_day["unknown"] += 1

    summary: dict[str, Any] = {
        "N": n,
        "lang_distribution": dict(lang_dist),
        "expansion_hit_rate": expansion_used / n,
        "translation_hit_rate": translation_used / n,
        "candidate_count": {
            "mean": _mean(candidate_counts),
            "p50": _pctile([float(x) for x in candidate_counts], 50),
            "max": max(candidate_counts) if candidate_counts else 0,
        },
        "total_recall_pre_fusion": {
            "mean": _mean([float(x) for x in total_recall]),
            "p50": _pctile([float(x) for x in total_recall], 50),
            "p95": _pctile([float(x) for x in total_recall], 95),
        },
        "fused_count": {
            "mean": _mean([float(x) for x in fused_count]),
            "p50": _pctile([float(x) for x in fused_count], 50),
        },
        "elapsed_ms": {
            "mean": _mean([float(x) for x in elapsed_ms]),
            "p50": _pctile([float(x) for x in elapsed_ms], 50),
            "p95": _pctile([float(x) for x in elapsed_ms], 95),
            "p99": _pctile([float(x) for x in elapsed_ms], 99),
            "max": max(elapsed_ms) if elapsed_ms else 0,
        },
        "query_len": {
            "mean": _mean([float(x) for x in query_len]),
            "p50": _pctile([float(x) for x in query_len], 50),
            "p95": _pctile([float(x) for x in query_len], 95),
        },
        "top1_score": {
            "mean": _mean(top1_scores),
            "p50": _pctile(top1_scores, 50),
            "p25": _pctile(top1_scores, 25),
            "p75": _pctile(top1_scores, 75),
            "n_high_confidence_gt_0.7": sum(1 for s in top1_scores if s > 0.7),
            "n_low_confidence_lt_0.3": sum(1 for s in top1_scores if s < 0.3),
        },
        "top1_minus_top5_gap": {
            "mean": _mean(score_gaps),
            "p50": _pctile(score_gaps, 50),
        },
        "kb_coverage": {
            "unique_ids_appearing_in_top5": len(top_ids),
            "top_15_most_frequent": top_ids.most_common(15),
            "share_of_top1_in_one_id": (
                max(c for c in top_ids.values()) / sum(top_ids.values())
                if top_ids else 0.0
            ),
        },
        "queries": {
            "unique": len(qhash_dist),
            "repeat_share": repeat_share,
            "most_repeated": qhash_dist.most_common(5),
        },
        "daily_volume": dict(sorted(by_day.items())),
    }
    return summary


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _fmt_num(x: Any) -> str:
    if isinstance(x, float):
        if math.isnan(x):
            return "—"
        return f"{x:.3f}" if abs(x) < 1 else f"{x:.1f}"
    return str(x)


def render_markdown(s: dict[str, Any], log_path: Path, fig_dir: Path | None) -> str:
    if s["N"] == 0:
        return (
            f"# Retrieval log analysis\n\n"
            f"**No events** in `{log_path.relative_to(ROOT) if log_path.is_relative_to(ROOT) else log_path}`.\n"
        )

    out = []
    rel = log_path.relative_to(ROOT) if log_path.is_relative_to(ROOT) else log_path
    out.append(f"# Retrieval log analysis — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}\n")
    out.append(f"Source: `{rel}`\n")
    out.append(f"**N = {s['N']} retrieval events**\n")

    out.append("## Language distribution\n")
    out.append("| lang | count | share |")
    out.append("| --- | ---: | ---: |")
    total = s["N"]
    for lang, c in sorted(s["lang_distribution"].items(), key=lambda kv: -kv[1]):
        out.append(f"| {lang} | {c} | {c/total:.1%} |")
    out.append("")

    out.append("## Expansion / translation\n")
    out.append(f"- expansion_used: **{s['expansion_hit_rate']:.1%}** of queries")
    out.append(f"- translation_used: **{s['translation_hit_rate']:.1%}** of queries")
    cc = s["candidate_count"]
    out.append(
        f"- candidate variants per query: mean={_fmt_num(cc['mean'])} / p50={_fmt_num(cc['p50'])} / max={cc['max']}\n"
    )

    out.append("## Latency (ms, end-to-end retrieval)\n")
    e = s["elapsed_ms"]
    out.append("| stat | mean | p50 | p95 | p99 | max |")
    out.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    out.append(
        f"| elapsed_ms | {_fmt_num(e['mean'])} | {_fmt_num(e['p50'])} | "
        f"{_fmt_num(e['p95'])} | {_fmt_num(e['p99'])} | {e['max']} |\n"
    )

    out.append("## Recall volume\n")
    tr, fc = s["total_recall_pre_fusion"], s["fused_count"]
    out.append("| stat | mean | p50 | p95 |")
    out.append("| --- | ---: | ---: | ---: |")
    out.append(
        f"| total_recall_pre_fusion | {_fmt_num(tr['mean'])} | "
        f"{_fmt_num(tr['p50'])} | {_fmt_num(tr['p95'])} |"
    )
    out.append(
        f"| fused_count | {_fmt_num(fc['mean'])} | {_fmt_num(fc['p50'])} | — |\n"
    )

    out.append("## Quality proxy — top-1 score\n")
    t1 = s["top1_score"]
    out.append("| stat | value |")
    out.append("| --- | ---: |")
    for k in ("mean", "p25", "p50", "p75"):
        out.append(f"| top1_score.{k} | {_fmt_num(t1[k])} |")
    out.append(f"| n_high_confidence (>0.7) | {t1['n_high_confidence_gt_0.7']} |")
    out.append(f"| n_low_confidence (<0.3) | {t1['n_low_confidence_lt_0.3']} |")
    gap = s["top1_minus_top5_gap"]
    out.append(
        f"\nTop-1 minus top-5 score gap: mean={_fmt_num(gap['mean'])} / "
        f"p50={_fmt_num(gap['p50'])} (large gap → confident top-1; "
        f"small gap → flat/muddy ranking).\n"
    )

    out.append("## KB coverage in top-5\n")
    cov = s["kb_coverage"]
    out.append(
        f"- distinct KB ids ever appearing in top-5: **{cov['unique_ids_appearing_in_top5']}**"
    )
    out.append(
        f"- single most-returned id share: {cov['share_of_top1_in_one_id']:.1%}"
    )
    out.append("\n**Top 15 most frequently returned ids**\n")
    out.append("| rank | kb_id | appearances |")
    out.append("| ---: | --- | ---: |")
    for i, (kid, c) in enumerate(cov["top_15_most_frequent"], 1):
        out.append(f"| {i} | `{kid}` | {c} |")
    out.append("")

    out.append("## Query repetition\n")
    q = s["queries"]
    out.append(f"- unique queries (by hash): **{q['unique']}**")
    out.append(f"- queries seen more than once: **{q['repeat_share']:.1%}** of distinct hashes")
    if q["most_repeated"]:
        out.append("\nMost repeated query hashes:")
        for h, c in q["most_repeated"]:
            out.append(f"  - `{h}` × {c}")
    out.append("")

    out.append("## Daily volume\n")
    out.append("| date (UTC) | events |")
    out.append("| --- | ---: |")
    for d, c in s["daily_volume"].items():
        out.append(f"| {d} | {c} |")
    out.append("")

    if fig_dir is not None:
        out.append("## Figures\n")
        for fname in [
            "lang_distribution.png",
            "elapsed_ms_hist.png",
            "top1_score_hist.png",
            "kb_id_frequency.png",
            "daily_volume.png",
        ]:
            if (fig_dir / fname).exists():
                out.append(f"![{fname}]({fig_dir.name}/{fname})")
        out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def emit_figures(rows: list[dict[str, Any]], out_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not available — skipping figures")
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Language distribution (bar chart).
    lang_dist = Counter(r.get("lang_detected", "unknown") for r in rows)
    if lang_dist:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        items = lang_dist.most_common()
        labels = [k for k, _ in items]
        values = [v for _, v in items]
        ax.bar(labels, values, color="#4682B4")
        ax.set_title("Detected language distribution")
        ax.set_ylabel("# events")
        for i, v in enumerate(values):
            ax.text(i, v, str(v), ha="center", va="bottom", fontsize=8)
        fig.tight_layout()
        fig.savefig(out_dir / "lang_distribution.png", dpi=120)
        plt.close(fig)

    # 2. Latency histogram (log-scale x to deal with tail).
    elapsed = [int(r.get("elapsed_ms", 0)) for r in rows if r.get("elapsed_ms")]
    if elapsed:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.hist(elapsed, bins=30, color="#CD5C5C", edgecolor="#440000", alpha=0.85)
        ax.set_title("Retrieval latency (ms)")
        ax.set_xlabel("elapsed_ms")
        ax.set_ylabel("# events")
        fig.tight_layout()
        fig.savefig(out_dir / "elapsed_ms_hist.png", dpi=120)
        plt.close(fig)

    # 3. Top-1 score histogram (quality proxy).
    top1 = [
        float(r["top_5_scores"][0])
        for r in rows
        if isinstance(r.get("top_5_scores"), list) and r["top_5_scores"]
    ]
    if top1:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.hist(top1, bins=20, color="#2E8B57", edgecolor="#0a3d20", alpha=0.85)
        ax.axvline(0.3, color="grey", linestyle=":", label="low-conf threshold 0.3")
        ax.axvline(0.7, color="grey", linestyle="--", label="high-conf threshold 0.7")
        ax.set_title("Top-1 retrieval score distribution")
        ax.set_xlabel("score")
        ax.set_ylabel("# events")
        ax.legend(loc="upper left", fontsize=8)
        fig.tight_layout()
        fig.savefig(out_dir / "top1_score_hist.png", dpi=120)
        plt.close(fig)

    # 4. KB id frequency (top 30 in top-5 sets).
    counter: Counter[str] = Counter()
    for r in rows:
        for kid in r.get("top_5_kb_ids") or []:
            if kid:
                counter[kid] += 1
    if counter:
        top30 = counter.most_common(30)
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.barh(
            [k for k, _ in top30][::-1],
            [v for _, v in top30][::-1],
            color="#FFA500",
            edgecolor="#7a4d00",
        )
        ax.set_title("Top-30 most-returned KB ids in top-5")
        ax.set_xlabel("appearances")
        fig.tight_layout()
        fig.savefig(out_dir / "kb_id_frequency.png", dpi=120)
        plt.close(fig)

    # 5. Daily volume.
    by_day: Counter[str] = Counter()
    for r in rows:
        ts = r.get("ts", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            by_day[dt.astimezone(timezone.utc).date().isoformat()] += 1
        except (ValueError, AttributeError):
            continue
    if by_day:
        days = sorted(by_day.items())
        fig, ax = plt.subplots(figsize=(8, 3.5))
        ax.plot(
            [d for d, _ in days],
            [c for _, c in days],
            marker="o",
            color="#6A5ACD",
        )
        ax.set_title("Daily retrieval event volume (UTC)")
        ax.set_xlabel("date")
        ax.set_ylabel("# events")
        ax.tick_params(axis="x", rotation=30)
        fig.tight_layout()
        fig.savefig(out_dir / "daily_volume.png", dpi=120)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="Path to retrieval.jsonl")
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Output dir (default: docs/observability/retrieval-analysis-<UTC-ts>)",
    )
    parser.add_argument("--no-figures", action="store_true", help="Skip matplotlib figures")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    rows = load_log(args.log)
    summary = summarise(rows)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    if args.out:
        out_dir = args.out
    else:
        out_dir = DEFAULT_OUT / f"retrieval-analysis-{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    fig_dir = out_dir / "figures" if not args.no_figures else None
    if rows and fig_dir is not None:
        emit_figures(rows, fig_dir)

    md = render_markdown(summary, args.log, fig_dir)
    report_path = out_dir / "report.md"
    report_path.write_text(md, encoding="utf-8")
    logger.info(f"Wrote report: {report_path}")

    # Also drop a machine-readable summary for downstream pipelines / dashboards.
    json_path = out_dir / "summary.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Wrote summary JSON: {json_path}")

    if not rows:
        logger.error("No retrieval events found — exiting with code 1")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
