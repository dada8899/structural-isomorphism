#!/usr/bin/env python3
"""
Build tier-2 candidate pool from v2m-top5.jsonl (94 pairs).
Excludes the 19 A-grade already in a_discoveries.json.
Enriches with KB a_id/b_id lookup.

Output: web/data/a_discoveries_tier2.json
"""
import json
from pathlib import Path
from datetime import date

ROOT = Path(__file__).parent.parent
KB_FILE = ROOT / "data" / "kb-5000-merged.jsonl"
TOP5 = ROOT / "results" / "v2m-top5.jsonl"
WEB_DATA = Path.home() / "Projects" / "structural-isomorphism" / "web" / "data"
A_GRADE = WEB_DATA / "a_discoveries.json"
TARGET = WEB_DATA / "a_discoveries_tier2.json"


def main():
    # KB name → id lookup
    kb = {}
    with open(KB_FILE) as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                kb[item["name"]] = item["id"]
    print(f"KB: {len(kb)} phenomena")

    # Load A-grade pairs so we can dedupe
    with open(A_GRADE) as f:
        a_data = json.load(f)
    a_pairs = set()
    for x in a_data.get("discoveries", []):
        a_pairs.add((x.get("a_name"), x.get("b_name")))
        a_pairs.add((x.get("b_name"), x.get("a_name")))
    print(f"A-grade pairs to exclude: {len(a_data.get('discoveries', []))}")

    # Load top5 tier
    with open(TOP5) as f:
        top5 = [json.loads(l) for l in f if l.strip()]
    print(f"top5 pool: {len(top5)} pairs")

    # Filter out A-grade, sort by similarity desc, enrich with KB ids
    tier2 = []
    missing_ids = 0
    for x in top5:
        a_name = x.get("a_name", "")
        b_name = x.get("b_name", "")
        if (a_name, b_name) in a_pairs:
            continue
        a_id = kb.get(a_name)
        b_id = kb.get(b_name)
        if not a_id or not b_id:
            missing_ids += 1
            continue

        sim = x.get("similarity") or x.get("_score") or 0
        # Normalize: model gives cosine similarity 0-1
        tier2.append({
            "a_id": a_id,
            "b_id": b_id,
            "a_name": a_name,
            "b_name": b_name,
            "a_domain": x.get("a_domain", ""),
            "b_domain": x.get("b_domain", ""),
            "similarity": round(float(sim), 4),
            "potential": x.get("potential", ""),
            "value_type": x.get("value_type", ""),
            "reason": x.get("reason", ""),
            "verdict": x.get("verdict", ""),
        })

    # Sort by similarity desc and rank 1..N
    tier2.sort(key=lambda x: x["similarity"], reverse=True)
    for i, x in enumerate(tier2, 1):
        x["rank"] = i

    print(f"tier2 final: {len(tier2)} (skipped: missing_ids={missing_ids})")

    # Write
    payload = {
        "generated_at": str(date.today()),
        "source": "v2m-top5.jsonl (excluding A-grade)",
        "count": len(tier2),
        "discoveries": tier2,
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with open(TARGET, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"wrote {TARGET}")

    print("\n=== top 5 of tier2 preview ===")
    for x in tier2[:5]:
        print(f"  #{x['rank']} [sim={x['similarity']:.3f}] {x['a_name']} × {x['b_name']}")
        print(f"       {x['a_domain']} ↔ {x['b_domain']}")
        if x.get('reason'): print(f"       {x['reason'][:100]}")


if __name__ == "__main__":
    main()
