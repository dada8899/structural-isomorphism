#!/usr/bin/env python3
"""Strip head-internal shared boilerplate from Wave 3 C public-health entries.

Background
----------
Pipeline-2 (commit 599341e) rewrote 117 entries' boilerplate SUFFIXES. The
SESSION-24 audit (e) caught a related leak: 23 public-health entries share
the EXACT 30-char string "该干预的成本效益(QALY/DALY)评估是政策决策核心" as a
connector phrase INSIDE the preserved head — same embedding-pollution risk
as the suffix boilerplate, but pipeline-2's head-vs-tail validator
deliberately allowed it (only forbidden substrings in the LLM-generated
TAIL were rejected).

This script removes the shared phrase deterministically (no LLM cost) from
both additions file and master KB. Idempotent.

Usage
-----
    .venv/bin/python scripts/strip_wave3c_head_collisions.py --dry-run
    .venv/bin/python scripts/strip_wave3c_head_collisions.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ADDITIONS_FILE = REPO / "data" / "kb-additions-2026-05-25-long-tail-batch.jsonl"
MASTER_KB = REPO / "data" / "kb-5000-merged.jsonl"

# Exact shared substring + variants observed in audit (e).
# All 23 public-health entries have this verbatim; deterministic removal
# preserves all per-entry mechanism content (which follows after).
STRIP_PATTERNS = [
    "该干预的成本效益(QALY/DALY)评估是政策决策核心。",
    " 该干预的成本效益(QALY/DALY)评估是政策决策核心。",   # leading space variant
    "该干预的成本效益(QALY/DALY)评估是政策决策核心",      # no terminal period
]


def strip_pattern(desc: str) -> tuple[str, bool]:
    """Return (new_desc, modified)."""
    new = desc
    modified = False
    for pat in STRIP_PATTERNS:
        if pat in new:
            new = new.replace(pat, "")
            modified = True
            break  # only one pattern per desc (the variants are mutually exclusive)
    # collapse double-spaces / orphaned punctuation
    new = new.replace("  ", " ").replace("。 。", "。").replace(". 。", "。").strip()
    return new, modified


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        ap.error("specify --dry-run or --apply")

    rows = [json.loads(l) for l in open(ADDITIONS_FILE)]
    modified_count = 0
    samples = []
    for r in rows:
        desc = r.get("description", "")
        new, mod = strip_pattern(desc)
        if mod:
            modified_count += 1
            r["description"] = new
            if len(samples) < 2:
                samples.append((r["id"], desc, new))

    print(f"additions modified: {modified_count}", file=sys.stderr)
    for sid, orig, new in samples:
        print(f"\n  {sid}", file=sys.stderr)
        print(f"  ORIG ({len(orig)}): ...{orig[max(0,len(orig)-180):]}", file=sys.stderr)
        print(f"  NEW  ({len(new)}): ...{new[max(0,len(new)-180):]}", file=sys.stderr)

    if args.dry_run:
        return

    # ---- write back ----
    bak = ADDITIONS_FILE.with_suffix(".jsonl.bak-pre-head-strip")
    if not bak.exists():
        bak.write_bytes(ADDITIONS_FILE.read_bytes())
        print(f"\nbacked up additions to {bak}", file=sys.stderr)

    with open(ADDITIONS_FILE, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # cascade to master KB
    archive = MASTER_KB.with_name(MASTER_KB.name + ".archive-pre-head-strip")
    if not archive.exists():
        archive.write_bytes(MASTER_KB.read_bytes())
        print(f"archived master KB to {archive}", file=sys.stderr)

    target_ids = {r["id"] for r in rows if "成本效益" not in r.get("description", "")}
    # Re-scan master KB for any entries needing strip
    master_rows = [json.loads(l) for l in open(MASTER_KB)]
    n_master_upd = 0
    for r in master_rows:
        desc = r.get("description", "")
        new, mod = strip_pattern(desc)
        if mod:
            r["description"] = new
            n_master_upd += 1
    with open(MASTER_KB, "w") as f:
        for r in master_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"updated {n_master_upd} entries in master KB ({MASTER_KB})", file=sys.stderr)


if __name__ == "__main__":
    main()
