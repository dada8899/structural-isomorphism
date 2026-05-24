#!/usr/bin/env python3
"""
merge_kb_additions.py

Unified merge helper for the 2026-05-25 KB extension waves.

Inputs (all optional, but at least one of `--additions` / `--long-tail` /
`--layer` should be given):

  --main <jsonl>          baseline KB (default: data/kb-5000-merged.jsonl)
  --additions <glob>      Wave 2 class addition files. Each entry that
                          does not collide with an existing main-KB
                          entry (by `id`) is appended.
  --long-tail <jsonl>     Wave 3C long-tail batch. Same dedup-by-id rule.
  --layer <jsonl>         Wave 3B reproducible-data-layer overlay. For
                          each entry whose `id` matches an existing main
                          KB entry, the `data_layer` field is merged in.
                          Non-matching ids are appended.
  --output <jsonl>        output path. Required when `--apply`.
  --apply                 actually write `--output` (default: dry-run).

The script never modifies `--main` in place.

Usage:
    python3 scripts/merge_kb_additions.py \
        --main data/kb-5000-merged.jsonl \
        --additions "data/kb-additions-2026-05-25-*.jsonl" \
        --layer data/kb-reproducible-data-layer-2026-05-25.jsonl \
        --long-tail data/kb-additions-2026-05-25-long-tail-batch.jsonl \
        --output data/kb-5333-merged-2026-05-25.jsonl \
        --dry-run

Note: `--additions` glob includes the long-tail file too. If you pass
`--long-tail` separately, exclude it from `--additions` (or this script
will dedup it anyway via id).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import OrderedDict
from typing import Dict, List, Tuple


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DEFAULT_MAIN = os.path.join(REPO_ROOT, "data", "kb-5000-merged.jsonl")


def load_jsonl(path: str) -> List[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def index_by_id(entries: List[dict]) -> "OrderedDict[str, dict]":
    out: "OrderedDict[str, dict]" = OrderedDict()
    for e in entries:
        eid = e.get("id")
        if eid is None:
            continue
        out[eid] = e
    return out


def merge_additions(
    main: "OrderedDict[str, dict]",
    additions: List[dict],
    label: str,
) -> Tuple[int, int]:
    """Append entries from `additions` that don't collide by id.
    Returns (added, skipped_dup)."""
    added = 0
    skipped = 0
    for e in additions:
        eid = e.get("id")
        if eid is None:
            # no id: treat as always-add, key on a synthetic name
            key = f"__noid__{label}__{added}"
            main[key] = e
            added += 1
            continue
        if eid in main:
            skipped += 1
            continue
        main[eid] = e
        added += 1
    return added, skipped


def merge_layer(
    main: "OrderedDict[str, dict]",
    layer: List[dict],
) -> Tuple[int, int]:
    """Merge `data_layer` overlay into matching ids; append unmatched.
    Returns (updated, appended)."""
    updated = 0
    appended = 0
    for e in layer:
        eid = e.get("id")
        if eid is not None and eid in main:
            target = main[eid]
            if "data_layer" in e:
                target["data_layer"] = e["data_layer"]
                updated += 1
            else:
                # nothing to overlay; entry already matches, leave alone
                pass
        else:
            key = eid if eid is not None else f"__layer_noid__{appended}"
            main[key] = e
            appended += 1
    return updated, appended


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--main", default=DEFAULT_MAIN)
    ap.add_argument(
        "--additions",
        action="append",
        default=[],
        help="Glob pattern; can be repeated.",
    )
    ap.add_argument("--long-tail", default=None)
    ap.add_argument("--layer", default=None)
    ap.add_argument("--output", default=None)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="(default behaviour anyway)",
    )
    args = ap.parse_args()

    if not os.path.exists(args.main):
        print(f"ERROR: main KB missing: {args.main}", file=sys.stderr)
        return 2

    main_entries = load_jsonl(args.main)
    print(f"Loaded main KB: {len(main_entries)} entries from {args.main}")
    merged = index_by_id(main_entries)
    starting = len(merged)

    # additions globs (exclude long-tail explicitly if given separately
    # to avoid double-counting)
    long_tail_basename = (
        os.path.basename(args.long_tail) if args.long_tail else None
    )
    addition_files: List[str] = []
    for pat in args.additions:
        addition_files.extend(sorted(glob.glob(pat)))
    if long_tail_basename:
        addition_files = [
            f for f in addition_files
            if os.path.basename(f) != long_tail_basename
        ]

    total_added = 0
    total_skipped = 0
    for fp in addition_files:
        entries = load_jsonl(fp)
        added, skipped = merge_additions(
            merged, entries, label=os.path.basename(fp)
        )
        print(
            f"  additions  {os.path.basename(fp):60s} "
            f"+{added:3d}  skipped_dup={skipped}"
        )
        total_added += added
        total_skipped += skipped

    layer_updated = 0
    layer_appended = 0
    if args.layer:
        layer_entries = load_jsonl(args.layer)
        layer_updated, layer_appended = merge_layer(merged, layer_entries)
        print(
            f"  layer      {os.path.basename(args.layer):60s} "
            f"updated={layer_updated} appended={layer_appended}"
        )

    longtail_added = 0
    longtail_skipped = 0
    if args.long_tail:
        lt_entries = load_jsonl(args.long_tail)
        longtail_added, longtail_skipped = merge_additions(
            merged, lt_entries, label=os.path.basename(args.long_tail)
        )
        print(
            f"  long-tail  {os.path.basename(args.long_tail):60s} "
            f"+{longtail_added:3d}  skipped_dup={longtail_skipped}"
        )

    ending = len(merged)
    print()
    print("=== Merge summary ===")
    print(f"  main baseline                          {starting}")
    print(f"  additions added                        +{total_added}")
    print(f"  additions skipped (dup id)             {total_skipped}")
    if args.layer:
        print(f"  layer entries with data_layer merged   {layer_updated}")
        print(f"  layer entries appended (unmatched)     {layer_appended}")
    if args.long_tail:
        print(f"  long-tail appended                     +{longtail_added}")
        print(f"  long-tail skipped (dup id)             {longtail_skipped}")
    print(f"  ----")
    print(f"  final merged total                     {ending}")
    print()

    if args.apply:
        if not args.output:
            print("ERROR: --apply requires --output", file=sys.stderr)
            return 2
        if os.path.exists(args.output):
            print(
                f"ERROR: refusing to overwrite existing {args.output}",
                file=sys.stderr,
            )
            return 2
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            for v in merged.values():
                f.write(json.dumps(v, ensure_ascii=False) + "\n")
        print(f"WROTE {ending} entries -> {args.output}")
    else:
        print(
            f"DRY-RUN: no output written. Re-run with "
            f"`--apply --output <path>` to commit."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
