#!/usr/bin/env python3
"""
normalize_kb_additions.py

Normalise the `type_id` field across the Wave 2 KB addition JSONL files
(`data/kb-additions-2026-05-25-<class>.jsonl`, excluding the long-tail batch).

Two safe transforms only:

  1. Zero-fill numeric strings: "6" -> "06", "7" -> "07".
     The main KB (`data/kb-5000-merged.jsonl`) uses two-digit IDs in the
     range 01..84, so the un-padded ones are clearly mistakes.

  2. Detect class-name strings (non-numeric, e.g. "rfp",
     "extreme_value_tail_class") and FLAG them. These belong to a
     different taxonomy (universality classes in
     `web/frontend/assets/data/universality-classes.json`), not the
     84-row structural-type taxonomy that the KB uses. We do NOT silently
     guess a numeric mapping; user decides whether to coin a new ID or
     fall back.

Default mode is `--dry-run`. Without `--apply` no file is touched.
When `--apply` is given, each modified file is rewritten in-place and a
`.bak` sibling is left behind.

Usage:
    python3 scripts/normalize_kb_additions.py --dry-run
    python3 scripts/normalize_kb_additions.py --apply
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
from collections import Counter
from typing import Dict, List, Tuple


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
MAIN_KB = os.path.join(REPO_ROOT, "data", "kb-5000-merged.jsonl")
ADDITIONS_GLOB = os.path.join(REPO_ROOT, "data", "kb-additions-2026-05-25-*.jsonl")
LONG_TAIL_BASENAME = "kb-additions-2026-05-25-long-tail-batch.jsonl"


def load_main_kb_type_ids(path: str) -> set:
    ids = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                ids.add(json.loads(line).get("type_id"))
    return {t for t in ids if t is not None}


def classify(type_id: str, valid_ids: set) -> str:
    """Return one of: ok / zerofill / unmapped_classname / unknown."""
    if type_id is None:
        return "unknown"
    if type_id in valid_ids:
        return "ok"
    if type_id.isdigit() and type_id.zfill(2) in valid_ids:
        return "zerofill"
    # non-numeric → almost certainly a universality-class name slipped in
    return "unmapped_classname"


def normalise_entry(entry: dict, valid_ids: set) -> Tuple[dict, str]:
    """Return (new_entry, action). `action` is one of:
        unchanged / zerofilled / flagged
    """
    t = entry.get("type_id")
    kind = classify(t, valid_ids)
    if kind == "ok":
        return entry, "unchanged"
    if kind == "zerofill":
        new = dict(entry)
        new["type_id"] = t.zfill(2)
        return new, "zerofilled"
    # unmapped_classname / unknown
    return entry, "flagged"


def process(files: List[str], valid_ids: set, apply: bool) -> Dict[str, dict]:
    report: Dict[str, dict] = {}
    for fp in files:
        actions = Counter()
        flagged_examples: List[Tuple[str, str]] = []  # (type_id, name)
        new_lines: List[str] = []
        with open(fp, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    new_lines.append(line)
                    continue
                entry = json.loads(line)
                old_t = entry.get("type_id")
                new_entry, action = normalise_entry(entry, valid_ids)
                actions[action] += 1
                if action == "flagged":
                    flagged_examples.append((old_t, entry.get("name", "?")))
                new_lines.append(
                    json.dumps(new_entry, ensure_ascii=False) + "\n"
                )

        report[fp] = {
            "actions": dict(actions),
            "flagged_examples": flagged_examples[:3],
            "flagged_total": actions["flagged"],
        }

        if apply and actions["zerofilled"] > 0:
            shutil.copy2(fp, fp + ".bak")
            with open(fp, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Actually rewrite files (default: dry-run only)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit dry-run (default behaviour anyway)",
    )
    ap.add_argument(
        "--main-kb",
        default=MAIN_KB,
        help=f"Main KB JSONL (default: {os.path.relpath(MAIN_KB, REPO_ROOT)})",
    )
    args = ap.parse_args()

    if not os.path.exists(args.main_kb):
        print(f"ERROR: main KB not found at {args.main_kb}", file=sys.stderr)
        return 2

    valid_ids = load_main_kb_type_ids(args.main_kb)
    print(f"Main KB unique type_id count: {len(valid_ids)}")

    files = sorted(glob.glob(ADDITIONS_GLOB))
    files = [f for f in files if os.path.basename(f) != LONG_TAIL_BASENAME]
    print(f"Wave 2 addition files: {len(files)}")

    report = process(files, valid_ids, apply=args.apply)

    total = Counter()
    for fp, info in report.items():
        for k, v in info["actions"].items():
            total[k] += v
        marker = "" if info["flagged_total"] == 0 else "  FLAGGED"
        print(
            f"  {os.path.basename(fp):60s}  "
            f"{info['actions']}{marker}"
        )
        for ex in info["flagged_examples"]:
            print(f"      sample: type_id={ex[0]!r}  name={ex[1][:60]!r}")

    print()
    print("=== Totals ===")
    for k in ("unchanged", "zerofilled", "flagged"):
        print(f"  {k:12s} {total[k]}")
    print()
    if args.apply:
        print("APPLIED: zerofill fixes written in-place; .bak files created.")
    else:
        print("DRY-RUN: no file written. Re-run with --apply to commit changes.")
    if total["flagged"] > 0:
        print(
            f"\n{total['flagged']} entries left UNCHANGED with non-numeric "
            f"type_id (e.g. 'rfp', 'extreme_value_tail_class'). These belong "
            f"to the universality-class taxonomy, not the 84-row KB structural "
            f"taxonomy. User decision required: coin new type_id or remap."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
