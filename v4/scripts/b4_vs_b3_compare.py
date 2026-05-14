#!/usr/bin/env python3
"""Compare B4 DeepSeek-rerun ensemble verdicts to B3 taxonomy.

Loads:
  - v4/results/B3_taxonomy_v2.jsonl  (per-class B3 consensus)
  - v4/results/B4_deepseek_ensemble.jsonl  (per-class 3 reviewer verdicts)

Optionally also loads (for triangulation):
  - v4/results/B4_heterogeneous_ensemble.jsonl  (original B4 from session #7)

Outputs a markdown diff report:
  - v4/results/B4_deepseek_vs_B3_diff.md

Metrics:
  - per-class B4 consensus (majority of 3 reviewers, UNCLEAR if no majority)
  - 3/3 unanimous count, 2/3 majority count, all-disagree count
  - B4 vs B3 AGREE / DIFFER rate
  - Optional: B4-deepseek vs original-B4 AGREE rate (if original file present)
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
B3_TAX_DEFAULT = REPO / "v4" / "results" / "B3_taxonomy_v2.jsonl"
B4_DS_DEFAULT = REPO / "v4" / "results" / "B4_deepseek_ensemble.jsonl"
B4_ORIG_DEFAULT = REPO / "v4" / "results" / "B4_heterogeneous_ensemble.jsonl"
OUT_DEFAULT = REPO / "v4" / "results" / "B4_deepseek_vs_B3_diff.md"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def consensus_of(verdicts: list[str]) -> tuple[str, str]:
    """Return (consensus, agreement_pattern).
    agreement_pattern in {'3/3', '2/3', 'all-disagree'}.
    """
    # Strip ERROR / PARSE_FAIL from consensus computation but mark pattern
    real = [v for v in verdicts if v not in {"ERROR", "PARSE_FAIL"}]
    if not real:
        return "UNCLEAR", "all-disagree"
    counts = Counter(real)
    most, n_most = counts.most_common(1)[0]
    if n_most == len(real) == 3:
        return most, "3/3"
    if n_most >= 2:
        return most, "2/3"
    return "UNCLEAR", "all-disagree"


def aggregate_per_class(rows: list[dict]) -> dict[str, dict]:
    by_class: dict[str, list[dict]] = {}
    for r in rows:
        by_class.setdefault(r["class_id"], []).append(r)
    out: dict[str, dict] = {}
    for cid, recs in by_class.items():
        verdicts = [r["verdict"] for r in recs]
        consensus, pattern = consensus_of(verdicts)
        avg_conf = sum(r.get("confidence", 0.0) for r in recs) / max(1, len(recs))
        out[cid] = {
            "verdicts": verdicts,
            "consensus": consensus,
            "pattern": pattern,
            "avg_conf": avg_conf,
            "reviewer_ids": [r.get("model_id", "") for r in recs],
            "records": recs,
        }
    return out


def normalize_b3_consensus(b3_row: dict) -> str:
    """B3 taxonomy stores final_verdict like 'KEEP_strong', 'SPLIT_strong',
    'CONTESTED(B1=KEEP,B3=REJECT)' etc. Extract the B3 consensus column
    directly."""
    return str(b3_row.get("b3_consensus", "UNCLEAR")).upper()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b3", default=str(B3_TAX_DEFAULT))
    ap.add_argument("--b4-deepseek", default=str(B4_DS_DEFAULT))
    ap.add_argument("--b4-original", default=str(B4_ORIG_DEFAULT))
    ap.add_argument("--output", default=str(OUT_DEFAULT))
    args = ap.parse_args()

    b3_rows = load_jsonl(Path(args.b3))
    b4_ds_rows = load_jsonl(Path(args.b4_deepseek))
    b4_orig_rows = load_jsonl(Path(args.b4_original))

    b3_by_class = {r["class_id"]: r for r in b3_rows}
    b4_ds_agg = aggregate_per_class(b4_ds_rows)
    b4_orig_agg = aggregate_per_class(b4_orig_rows) if b4_orig_rows else {}

    # ---- compute agreement metrics ----
    classes_ordered = sorted(b3_by_class.keys())
    rows_out: list[dict] = []
    for cid in classes_ordered:
        b3_v = normalize_b3_consensus(b3_by_class[cid])
        b4_ds = b4_ds_agg.get(cid, {})
        b4_v = b4_ds.get("consensus", "MISSING")
        pattern = b4_ds.get("pattern", "n/a")
        b4_orig_v = b4_orig_agg.get(cid, {}).get("consensus", "")
        rows_out.append({
            "class_id": cid,
            "b3": b3_v,
            "b4_deepseek": b4_v,
            "pattern": pattern,
            "b4_orig": b4_orig_v,
            "b4_ds_verdicts": b4_ds.get("verdicts", []),
            "b4_ds_conf": b4_ds.get("avg_conf", 0.0),
        })

    pattern_counter: Counter = Counter()
    agree_b3 = 0
    agree_orig = 0
    have_orig_count = 0
    for r in rows_out:
        pattern_counter[r["pattern"]] += 1
        if r["b3"] == r["b4_deepseek"]:
            agree_b3 += 1
        if r["b4_orig"]:
            have_orig_count += 1
            if r["b4_orig"] == r["b4_deepseek"]:
                agree_orig += 1

    n = len(rows_out)

    # ---- write markdown ----
    lines: list[str] = []
    lines.append("# B4 DeepSeek heterogeneous ensemble vs B3 — diff report")
    lines.append("")
    lines.append("**Date**: 2026-05-14 (session #8 rerun, DeepSeek-only no OpenRouter)")
    lines.append("")
    lines.append(
        "**Setup**: 3 DeepSeek direct-API reviewers — pro T=0.0 (rigorous), "
        "flash T=0.0 (rigorous), pro T=0.7 (chat-baseline). DeepSeek-chat / "
        "DeepSeek-reasoner unavailable on this account; v4-pro / v4-flash "
        "substituted with 3 temperature / system-prompt variations."
    )
    lines.append("")
    lines.append("## Per-class verdict diff")
    lines.append("")
    header = "| class_id | B3 | B4-deepseek | pattern | B4-orig | reviewers (v_A / v_B / v_C) |"
    lines.append(header)
    lines.append("|" + "|".join(["---"] * 6) + "|")
    for r in rows_out:
        v_str = " / ".join(r["b4_ds_verdicts"]) if r["b4_ds_verdicts"] else "—"
        lines.append(
            f"| `{r['class_id']}` | {r['b3']} | **{r['b4_deepseek']}** | "
            f"{r['pattern']} | {r['b4_orig'] or '—'} | {v_str} |"
        )
    lines.append("")

    lines.append("## Aggregate metrics")
    lines.append("")
    lines.append(f"- **Classes compared**: {n}")
    lines.append(f"- **3/3 unanimous**: {pattern_counter.get('3/3', 0)} ({pattern_counter.get('3/3', 0)/max(1,n)*100:.0f}%)")
    lines.append(f"- **2/3 majority**: {pattern_counter.get('2/3', 0)} ({pattern_counter.get('2/3', 0)/max(1,n)*100:.0f}%)")
    lines.append(f"- **All-disagree (no majority)**: {pattern_counter.get('all-disagree', 0)} ({pattern_counter.get('all-disagree', 0)/max(1,n)*100:.0f}%)")
    lines.append("")
    lines.append(f"- **B4-deepseek vs B3 AGREE**: {agree_b3} / {n} ({agree_b3/max(1,n)*100:.0f}%)")
    lines.append(f"- **B4-deepseek vs B3 DIFFER**: {n-agree_b3} / {n} ({(n-agree_b3)/max(1,n)*100:.0f}%)")
    if have_orig_count:
        lines.append(
            f"- **B4-deepseek vs B4-original AGREE**: {agree_orig} / {have_orig_count} "
            f"({agree_orig/max(1,have_orig_count)*100:.0f}%)"
        )
    lines.append("")

    # ---- B4 verdict distribution ----
    lines.append("## B4-deepseek consensus distribution")
    lines.append("")
    b4_dist: Counter = Counter(r["b4_deepseek"] for r in rows_out)
    for k in ("KEEP", "REJECT", "SPLIT", "MERGE", "UNCLEAR"):
        lines.append(f"- **{k}**: {b4_dist.get(k, 0)}")
    lines.append("")

    # ---- interpretation ----
    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "### Q1: Is the original B4 (62% disagree) replicable with a different "
        "third-reviewer config?"
    )
    lines.append("")
    if have_orig_count:
        orig_agree_pct = agree_orig / max(1, have_orig_count) * 100
        if orig_agree_pct >= 80:
            verdict_q1 = (
                f"YES — B4-deepseek matches B4-original on {orig_agree_pct:.0f}% of "
                "classes. The 'B3 over-estimates verdict stability' finding is "
                "robust across DeepSeek configurations."
            )
        elif orig_agree_pct >= 60:
            verdict_q1 = (
                f"PARTIALLY — B4-deepseek matches B4-original on {orig_agree_pct:.0f}% "
                "of classes. The qualitative finding (B3 over-estimates stability) "
                "is similar but the specific verdict pattern shifts with reviewer config."
            )
        else:
            verdict_q1 = (
                f"NO — B4-deepseek matches B4-original on only {orig_agree_pct:.0f}% of "
                "classes. Third-reviewer config (T=0.7 chat baseline vs T=1.0 "
                "cross-domain physicist persona) materially changes the verdict."
            )
    else:
        verdict_q1 = "Cannot compare — B4-original (B4_heterogeneous_ensemble.jsonl) not found."
    lines.append(verdict_q1)
    lines.append("")

    lines.append("### Q2: Is 'DeepSeek 3-config' an acceptable heterogeneity proxy?")
    lines.append("")
    unanimous = pattern_counter.get("3/3", 0)
    no_majority = pattern_counter.get("all-disagree", 0)
    if unanimous / max(1, n) >= 0.7:
        verdict_q2 = (
            f"**WEAK PROXY** — {unanimous}/{n} ({unanimous/max(1,n)*100:.0f}%) classes "
            "got 3/3 unanimous within DeepSeek, suggesting within-vendor heterogeneity "
            "is too low; this rerun probes a narrow slice of the disagreement surface. "
            "True cross-architecture (Kimi / Claude / Gemini) probe remains necessary "
            "for V&V claims."
        )
    elif no_majority / max(1, n) >= 0.2:
        verdict_q2 = (
            f"**REASONABLE PROXY** — only {unanimous}/{n} unanimous and "
            f"{no_majority}/{n} all-disagree; DeepSeek configs disagree enough that "
            "the ensemble surfaces real verdict uncertainty. Cross-architecture probe "
            "would still strengthen claims but isn't a blocker."
        )
    else:
        verdict_q2 = (
            f"**MIXED** — {unanimous}/{n} unanimous, {pattern_counter.get('2/3',0)}/{n} "
            f"2/3 majority, {no_majority}/{n} all-disagree. Heterogeneity is present "
            "but moderate; useful as a confidence indicator, less so as a robust "
            "cross-architecture replacement."
        )
    lines.append(verdict_q2)
    lines.append("")

    lines.append("## Methodology notes")
    lines.append("")
    lines.append(
        "- DeepSeek-chat / DeepSeek-reasoner unavailable on this account "
        "(api.deepseek.com/models returns only deepseek-v4-pro / deepseek-v4-flash). "
        "Substituted with 3 temperature / system-prompt variations of v4-pro/v4-flash."
    )
    lines.append(
        "- Cost budget: $5 USD enforced via per-call running-total check; "
        "actual spend logged in script stderr."
    )
    lines.append(
        "- Consensus rule: majority (>=2/3) for KEEP/REJECT/SPLIT/MERGE; "
        "else UNCLEAR. Identical to B3/B4 for compatibility."
    )
    lines.append(
        "- ERROR / PARSE_FAIL records (if any) are excluded from consensus "
        "computation; pattern is 'all-disagree' if all 3 fail."
    )
    lines.append("")

    Path(args.output).write_text("\n".join(lines))
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
