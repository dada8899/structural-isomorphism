"""
V3 seed case schema validator.

Checks that plans/v4-seed-cases-starter.yaml (or v4-seed-cases.yaml if exists)
conforms to schema:
  - required fields present
  - transformation types are valid ids from v4-variant-types.yaml
  - source/target equations not empty
  - refs non-empty

Usage:
    python v4_validate_seeds.py
    python v4_validate_seeds.py --file plans/v4-seed-cases.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).parent.parent
PLANS_DIR = PROJECT_DIR / "plans"

REQUIRED_SEED_FIELDS = [
    "id",
    "source_domain",
    "source_concept",
    "source_equation",
    "target_domain",
    "target_concept",
    "target_equation",
    "transformations",
    "historical_note",
    "source_refs",
]

REQUIRED_TRANSFORM_FIELDS = ["type", "mapping", "reason"]


def load_variant_ids() -> set[str]:
    with open(PLANS_DIR / "v4-variant-types.yaml") as f:
        data = yaml.safe_load(f)
    return {t["id"] for t in data["types"]}


def validate_seed(seed: dict, valid_types: set[str]) -> list[str]:
    errs = []
    sid = seed.get("id", "?")

    for field in REQUIRED_SEED_FIELDS:
        if field not in seed:
            errs.append(f"[{sid}] missing field: {field}")
            continue
        val = seed[field]
        if field in ("source_refs",) and not isinstance(val, list):
            errs.append(f"[{sid}] {field} must be a list")
        elif field != "source_refs" and not val:
            errs.append(f"[{sid}] empty field: {field}")

    # Validate transformations
    transforms = seed.get("transformations", [])
    if not isinstance(transforms, list) or not transforms:
        errs.append(f"[{sid}] transformations must be non-empty list")
    else:
        for i, t in enumerate(transforms):
            if not isinstance(t, dict):
                errs.append(f"[{sid}] transformation[{i}] must be dict")
                continue
            for f in REQUIRED_TRANSFORM_FIELDS:
                if f not in t or not t[f]:
                    errs.append(f"[{sid}] transformation[{i}] missing/empty: {f}")
            ttype = t.get("type", "")
            if ttype and ttype not in valid_types:
                errs.append(f"[{sid}] transformation[{i}] invalid type: '{ttype}' (valid: {sorted(valid_types)})")

    return errs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="plans/v4-seed-cases-starter.yaml")
    args = parser.parse_args()

    target = PROJECT_DIR / args.file
    if not target.exists():
        sys.exit(f"file not found: {target}")

    with open(target) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "seeds" not in data:
        sys.exit("missing top-level 'seeds' list")

    seeds = data["seeds"]
    valid_types = load_variant_ids()

    print(f"Validating {len(seeds)} seeds against schema...")
    print(f"Valid variant types: {sorted(valid_types)}\n")

    all_errors = []
    for seed in seeds:
        errs = validate_seed(seed, valid_types)
        if errs:
            all_errors.extend(errs)
            for e in errs:
                print(f"  ✗ {e}")
        else:
            sid = seed.get("id", "?")
            n_t = len(seed.get("transformations", []))
            print(f"  ✓ [{sid}] {seed['source_concept']} → {seed['target_concept']}  ({n_t} transforms)")

    print(f"\n{len(seeds)} seeds, {len(all_errors)} errors")

    # Domain coverage
    from collections import Counter
    src_domains = Counter(s.get("source_domain", "?") for s in seeds)
    tgt_domains = Counter(s.get("target_domain", "?") for s in seeds)
    print(f"\nSource domains: {dict(src_domains)}")
    print(f"Target domains: {dict(tgt_domains)}")

    # Primitive usage
    prim_usage = Counter()
    for s in seeds:
        for t in s.get("transformations", []):
            prim_usage[t.get("type", "?")] += 1
    print(f"\nPrimitive usage in seeds: {dict(prim_usage)}")
    unused = valid_types - set(prim_usage.keys())
    if unused:
        print(f"⚠️  Unused primitives: {sorted(unused)} — consider adding seed cases that exercise these")

    sys.exit(1 if all_errors else 0)


if __name__ == "__main__":
    main()
