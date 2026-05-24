#!/usr/bin/env python3
"""
merge_data_layer.py

Merge a reproducible-data-layer JSONL into the main KB JSONL by joining
on `id`. Each main-KB row gets a `data_layer` field copied from the
matching layer row. Rows without a layer match are passed through
unchanged.

Default I/O:
    KB    : data/kb-5000-merged.jsonl
    layer : data/kb-reproducible-data-layer-2026-05-25.jsonl
    out   : data/kb-5000-merged-with-layer.jsonl

Usage:
    python3 scripts/merge_data_layer.py
    python3 scripts/merge_data_layer.py --dry-run
    python3 scripts/merge_data_layer.py --kb path --layer path --out path

The script never overwrites the main KB. It writes to --out (or default
location) and the user is expected to rename/replace manually.
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

DEFAULT_KB = 'data/kb-5000-merged.jsonl'
DEFAULT_LAYER = 'data/kb-reproducible-data-layer-2026-05-25.jsonl'
DEFAULT_OUT = 'data/kb-5000-merged-with-layer.jsonl'


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f'missing: {path}')
    rows = []
    with path.open('r', encoding='utf-8') as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f'{path}:{ln} invalid JSON: {e}') from e
    return rows


def index_by_id(rows: list[dict]) -> dict[str, dict]:
    idx = {}
    dupes = 0
    for r in rows:
        rid = r.get('id')
        if not rid:
            continue
        if rid in idx:
            dupes += 1
        idx[rid] = r
    if dupes:
        print(f'[warn] {dupes} duplicate ids in input (last write wins)', file=sys.stderr)
    return idx


def merge(kb_rows: list[dict], layer_rows: list[dict]) -> tuple[list[dict], dict]:
    layer_idx = index_by_id(layer_rows)
    out_rows = []
    matched = 0
    overwritten = 0
    untouched = 0
    for kb in kb_rows:
        kb_id = kb.get('id')
        if kb_id and kb_id in layer_idx:
            layer = layer_idx[kb_id]
            data_layer = layer.get('data_layer')
            if data_layer is None:
                untouched += 1
                out_rows.append(kb)
                continue
            new = dict(kb)
            if 'data_layer' in new:
                overwritten += 1
            new['data_layer'] = data_layer
            out_rows.append(new)
            matched += 1
        else:
            untouched += 1
            out_rows.append(kb)
    stats = {
        'kb_total': len(kb_rows),
        'layer_total': len(layer_rows),
        'matched': matched,
        'overwritten_existing_layer': overwritten,
        'untouched': untouched,
        'layer_no_match': len(layer_idx) - matched,
    }
    return out_rows, stats


def write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def status_breakdown(rows: list[dict]) -> dict:
    counts = Counter()
    for r in rows:
        dl = r.get('data_layer')
        if not dl:
            counts['no_data_layer'] += 1
        else:
            counts[dl.get('validation_status', 'unknown')] += 1
    return dict(counts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kb', default=DEFAULT_KB, help='main KB JSONL (read-only)')
    p.add_argument('--layer', default=DEFAULT_LAYER, help='data layer JSONL to merge in')
    p.add_argument('--out', default=DEFAULT_OUT, help='output JSONL path (will be overwritten)')
    p.add_argument('--dry-run', action='store_true', help='only print stats; do not write output')
    args = p.parse_args(argv)

    kb_path = Path(args.kb)
    layer_path = Path(args.layer)
    out_path = Path(args.out)

    kb_rows = load_jsonl(kb_path)
    layer_rows = load_jsonl(layer_path)

    merged, stats = merge(kb_rows, layer_rows)
    sb = status_breakdown(merged)

    print('=== merge_data_layer ===')
    print(f'kb        : {kb_path}  ({stats["kb_total"]} rows)')
    print(f'layer     : {layer_path}  ({stats["layer_total"]} rows)')
    print(f'matched   : {stats["matched"]}')
    print(f'overwrite : {stats["overwritten_existing_layer"]} (kb rows already had data_layer)')
    print(f'untouched : {stats["untouched"]} (no matching layer id)')
    print(f'orphans   : {stats["layer_no_match"]} (layer rows with no kb id)')
    print(f'status_dist (post-merge): {sb}')

    if args.dry_run:
        print('[dry-run] not writing output')
        return 0

    write_jsonl(merged, out_path)
    print(f'wrote     : {out_path}  ({len(merged)} rows)')
    print()
    print('User action: review the output, then rename/replace if happy:')
    print(f'    mv {out_path} {kb_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
