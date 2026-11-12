#!/usr/bin/env python3
"""
Build a reverse index from v2m-top4plus.jsonl (761 cross-domain pairs).

Output: web/data/v2_pairs_index.json with shape:
{
  "by_id": {
    "<phenomenon_id>": [
      {
        "other_id":     "...",
        "other_name":   "...",
        "other_domain": "...",
        "self_role":    "a" | "b",
        "score":        5,
        "similarity":   0.884,
        "reason":       "...",
        "value_type":   "transferable_mechanism",
        "potential":    5
      },
      ...
    ]
  },
  "stats": { "total_pairs": 761, "phenomena_with_pairs": N, "max_pairs_per_phenom": M }
}

Each pair appears under BOTH a_id and b_id (so any phenomenon can look up
its full neighborhood without scanning).
"""
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
KB_FILE = ROOT / "data" / "kb-5000-merged.jsonl"
TOP4_FILE = ROOT / "results" / "v2m-top4plus.jsonl"
WEB_DATA = Path.home() / "Projects" / "structural-isomorphism" / "web" / "data"
OUT = WEB_DATA / "v2_pairs_index.json"


def main():
    # KB lookup
    kb_name_to_id = {}
    with open(KB_FILE) as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                kb_name_to_id[item["name"]] = item["id"]
    print(f"KB: {len(kb_name_to_id)} phenomena")

    # Load all pairs
    with open(TOP4_FILE) as f:
        pairs = [json.loads(l) for l in f if l.strip()]
    print(f"v2 pairs loaded: {len(pairs)}")

    by_id: dict = defaultdict(list)
    skipped = 0
    for p in pairs:
        a_name = p.get("a_name", "")
        b_name = p.get("b_name", "")
        a_id = kb_name_to_id.get(a_name)
        b_id = kb_name_to_id.get(b_name)
        if not a_id or not b_id:
            skipped += 1
            continue
        # `_score` is numeric (4 or 5). `potential` is sometimes a string label
        # like "高" / "中" / "低" — keep it as a string and don't coerce.
        try:
            score = int(p.get("_score") or 0)
        except (TypeError, ValueError):
            score = 0
        sim = p.get("similarity") or 0
        reason = p.get("reason", "")
        value_type = p.get("value_type", "")
        potential = p.get("potential", "")

        # Index under a_id with b as the "other"
        by_id[a_id].append({
            "other_id": b_id,
            "other_name": b_name,
            "other_domain": p.get("b_domain", ""),
            "self_role": "a",
            "score": int(score),
            "similarity": round(float(sim), 4),
            "reason": reason,
            "value_type": value_type,
            "potential": potential,
        })
        # Index under b_id with a as the "other"
        by_id[b_id].append({
            "other_id": a_id,
            "other_name": a_name,
            "other_domain": p.get("a_domain", ""),
            "self_role": "b",
            "score": int(score),
            "similarity": round(float(sim), 4),
            "reason": reason,
            "value_type": value_type,
            "potential": potential,
        })

    # Sort each phenomenon's neighborhood by similarity desc
    for k in by_id:
        by_id[k].sort(key=lambda x: x["similarity"], reverse=True)

    # Stats
    max_pairs = max(len(v) for v in by_id.values()) if by_id else 0
    hub_phenomena = sorted(by_id.items(), key=lambda kv: -len(kv[1]))[:10]
    print(f"\nIndexed {len(by_id)} phenomena ({skipped} pairs skipped due to missing IDs)")
    print(f"Max pairs per phenomenon: {max_pairs}")
    print("\nTop 10 hub phenomena (most cross-domain pairs):")
    for pid, prs in hub_phenomena:
        print(f"  {pid:18s} ({len(prs):3d} pairs)")

    payload = {
        "schema_version": "v2pairs-1.0",
        "by_id": dict(by_id),
        "stats": {
            "total_pairs": len(pairs),
            "indexed_pairs": len(pairs) - skipped,
            "phenomena_with_pairs": len(by_id),
            "max_pairs_per_phenom": max_pairs,
        },
    }
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(payload, f, ensure_ascii=False)
    size_kb = OUT.stat().st_size / 1024
    print(f"\nWrote {OUT} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
