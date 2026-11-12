#!/usr/bin/env python3
"""Merge 5 batch outputs into one + compute distribution stats.

Reads companies_batch_a{a,b,c,d,e}_out.jsonl and writes:
  - structtuples_2026-05-13.jsonl   (concatenated, in canonical AAPL...order)
  - batch_run_2026-05-13_stats.md   (dynamics_family / state distribution +
                                      cost / agreement w/ a-priori)
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
OUT_DIR = HERE
BATCHES = ["aa", "ab", "ac", "ad", "ae"]
DATE = "2026-05-13"

# DeepSeek v4-pro pricing (estimated from research / OpenRouter listing).
# Use conservative defaults if unsure; mark in stats.
# DeepSeek API direct (https://api.deepseek.com pricing 2026):
#   v4-pro: $0.55/M prompt (cache miss), $0.07/M prompt (cache hit), $2.19/M completion
PRICE_PROMPT_MISS = 0.55 / 1_000_000
PRICE_PROMPT_HIT = 0.07 / 1_000_000
PRICE_COMPLETION = 2.19 / 1_000_000


def main() -> None:
    rows = []
    parse_failures = []
    for b in BATCHES:
        path = OUT_DIR / f"companies_batch_{b}_out.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                parse_failures.append((str(path), str(e)))
                continue
            rows.append(d)

    # Write merged jsonl
    merged_path = OUT_DIR / f"structtuples_{DATE}.jsonl"
    with merged_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Stats
    n = len(rows)
    n_ok = sum(1 for r in rows if r.get("ok"))
    n_fail = n - n_ok

    fam_counter = Counter()
    state_counter = Counter()
    agreement = Counter()
    fam_by_expected = defaultdict(Counter)

    total_prompt = 0
    total_prompt_cache_hit = 0
    total_completion = 0
    total_attempts = 0
    total_elapsed = 0.0

    for r in rows:
        if not r.get("ok"):
            continue
        st = r.get("struct_tuple") or {}
        fam = st.get("dynamics_family", "unknown")
        state = st.get("critical_point_state", "unknown")
        fam_counter[fam] += 1
        state_counter[state] += 1

        expected = r.get("expected_dynamics_family_a_priori")
        if expected:
            if expected == fam:
                agreement["match"] += 1
            else:
                agreement["differ"] += 1
            fam_by_expected[expected][fam] += 1
        else:
            agreement["no_prior"] += 1

        u = r.get("usage") or {}
        prompt = u.get("prompt_tokens", 0)
        hit = u.get("prompt_cache_hit_tokens", 0)
        comp = u.get("completion_tokens", 0)
        total_prompt += prompt
        total_prompt_cache_hit += hit
        total_completion += comp
        total_attempts += r.get("attempts", 0)
        total_elapsed += r.get("elapsed_s", 0.0)

    miss = total_prompt - total_prompt_cache_hit
    cost = (
        miss * PRICE_PROMPT_MISS
        + total_prompt_cache_hit * PRICE_PROMPT_HIT
        + total_completion * PRICE_COMPLETION
    )

    # Markdown report
    lines = []
    lines.append(f"# D1 batch run {DATE} — stats\n")
    lines.append(f"## Counts\n")
    lines.append(f"- rows processed: **{n}**")
    lines.append(f"- ok: **{n_ok}**")
    lines.append(f"- failed: **{n_fail}**")
    if parse_failures:
        lines.append(f"- JSON parse failures during merge: {len(parse_failures)}")
    lines.append("")

    lines.append("## Dynamics family distribution (ok rows)\n")
    lines.append("| family | count | pct |")
    lines.append("|---|---:|---:|")
    for fam, c in fam_counter.most_common():
        pct = c / max(n_ok, 1) * 100
        lines.append(f"| {fam} | {c} | {pct:.1f}% |")
    lines.append("")

    lines.append("## Critical-point state distribution (ok rows)\n")
    lines.append("| state | count | pct |")
    lines.append("|---|---:|---:|")
    for s, c in state_counter.most_common():
        pct = c / max(n_ok, 1) * 100
        lines.append(f"| {s} | {c} | {pct:.1f}% |")
    lines.append("")

    lines.append("## Agreement with a-priori expectation\n")
    total_with_prior = agreement["match"] + agreement["differ"]
    if total_with_prior > 0:
        match_pct = agreement["match"] / total_with_prior * 100
        lines.append(f"- match: **{agreement['match']}** ({match_pct:.1f}% of {total_with_prior} priored rows)")
        lines.append(f"- differ: {agreement['differ']}")
    lines.append(f"- no_prior: {agreement['no_prior']}")
    lines.append("")

    if fam_by_expected:
        lines.append("### LLM family vs a-priori (where prior exists)\n")
        lines.append("| a-priori expected | LLM assigned | count |")
        lines.append("|---|---|---:|")
        for exp_fam, fams in sorted(fam_by_expected.items()):
            for fam, c in fams.most_common():
                marker = " ✓" if fam == exp_fam else ""
                lines.append(f"| {exp_fam} | {fam}{marker} | {c} |")
        lines.append("")

    lines.append("## LLM cost (DeepSeek v4-pro direct API, estimated)\n")
    lines.append(f"- prompt tokens total: {total_prompt:,}")
    lines.append(f"- prompt cache hit: {total_prompt_cache_hit:,} ({total_prompt_cache_hit/max(total_prompt,1)*100:.1f}%)")
    lines.append(f"- completion tokens: {total_completion:,}")
    lines.append(f"- estimated cost: **${cost:.4f}** USD")
    lines.append(f"  - prompt miss @ ${PRICE_PROMPT_MISS*1e6:.2f}/M: ${miss*PRICE_PROMPT_MISS:.4f}")
    lines.append(f"  - prompt hit  @ ${PRICE_PROMPT_HIT*1e6:.2f}/M: ${total_prompt_cache_hit*PRICE_PROMPT_HIT:.4f}")
    lines.append(f"  - completion  @ ${PRICE_COMPLETION*1e6:.2f}/M: ${total_completion*PRICE_COMPLETION:.4f}")
    lines.append(f"- total LLM attempts: {total_attempts} (avg {total_attempts/max(n_ok,1):.2f}/row)")
    lines.append(f"- total elapsed (sum across parallel batches): {total_elapsed:.1f}s")
    lines.append("")

    lines.append(f"## Output\n")
    lines.append(f"- merged jsonl: `structtuples_{DATE}.jsonl` ({n} rows)\n")

    report_path = OUT_DIR / f"batch_run_{DATE}_stats.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"merged -> {merged_path} ({n} rows, {n_ok} ok)")
    print(f"stats  -> {report_path}")
    print(f"cost estimate: ${cost:.4f}")


if __name__ == "__main__":
    main()
