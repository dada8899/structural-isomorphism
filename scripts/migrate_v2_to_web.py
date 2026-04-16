#!/usr/bin/env python3
"""
Migrate v2m-final-ranked.jsonl (19 A-grade) to the web product's
a_discoveries.json format. Backs up v1 first.

Source:  results/v2m-final-ranked.jsonl
KB:      data/kb-5000-merged.jsonl (for name → id lookup)
Target:  web/data/a_discoveries.json
Backup:  web/data/a_discoveries_v1_backup.json
"""
import json
import shutil
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
V2_FILE = ROOT / "results" / "v2m-final-ranked.jsonl"
KB_FILE = ROOT / "data" / "kb-5000-merged.jsonl"
WEB_DATA = Path.home() / "Projects" / "structural-isomorphism" / "web" / "data"
TARGET = WEB_DATA / "a_discoveries.json"
BACKUP = WEB_DATA / "a_discoveries_v1_backup.json"

LITERATURE_STATUS_MAP = {
    "unexplored": "未有先例",
    "unexplored-novel": "未有先例",
    "partially-explored": "部分探索",
    "partial-explored": "部分探索",
    "partial": "部分探索",
    "widely-studied": "已广泛讨论",
    "known": "已广泛讨论",
    "well-known": "已广泛讨论",
}


def map_lit_status(value):
    if not value:
        return "未知"
    v = str(value).strip().lower()
    return LITERATURE_STATUS_MAP.get(v, value)


def main():
    # 1. Load KB → name:id lookup
    kb_name_to_id = {}
    with open(KB_FILE) as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                kb_name_to_id[item["name"]] = item["id"]
    print(f"KB loaded: {len(kb_name_to_id)} phenomena")

    # 2. Load v2 A-grade
    with open(V2_FILE) as f:
        items = [json.loads(l) for l in f if l.strip()]
    print(f"v2 A-grade loaded: {len(items)} items")

    # 3. Sort by final_weighted_score desc and renumber rank 1..N
    items.sort(key=lambda x: x.get("final_weighted_score", 0), reverse=True)

    lit_status_seen = set()
    out = []
    missing = []
    for i, it in enumerate(items, start=1):
        a_name = it.get("a_name", "")
        b_name = it.get("b_name", "")
        a_id = kb_name_to_id.get(a_name)
        b_id = kb_name_to_id.get(b_name)
        if not a_id or not b_id:
            missing.append((a_name, b_name, a_id, b_id))

        iso_conf = it.get("isomorphism_confidence", 0)
        # Normalize 0-1 float to 0-100 int
        if isinstance(iso_conf, float) and iso_conf <= 1.0:
            iso_conf = round(iso_conf * 100)
        else:
            try:
                iso_conf = int(round(float(iso_conf)))
            except (TypeError, ValueError):
                iso_conf = 0

        lit = it.get("literature_status")
        lit_status_seen.add(str(lit).lower() if lit else "<empty>")

        out.append({
            # === Core display fields (used by existing discoveries.js) ===
            "rank": i,
            "a_id": a_id or "",
            "b_id": b_id or "",
            "a_name": a_name,
            "b_name": b_name,
            "a_domain": it.get("a_domain", ""),
            "b_domain": it.get("b_domain", ""),
            "final_score": round(it.get("final_weighted_score", 0), 2),
            "isomorphism_confidence": iso_conf,
            "literature_status": map_lit_status(lit),
            "one_line_verdict": it.get("paper_title", ""),
            "equations": it.get("equations", ""),
            "literature_detail": it.get("risk", ""),
            "execution_plan": it.get("execution_plan", ""),
            "impact_scope": it.get("impact_scope", ""),
            "impact_detail": it.get("practical_value", ""),
            "time_estimate": it.get("time_estimate", ""),
            "solo_feasible": bool(it.get("solo_feasible", False)),

            # === New v2-specific fields (shown in expanded detail) ===
            "rating": it.get("rating", "A"),
            "paper_title": it.get("paper_title", ""),
            "target_venue": it.get("target_venue", ""),
            "isomorphism_depth": it.get("isomorphism_depth"),
            "blocking_mechanisms": it.get("blocking_mechanisms", ""),
            "full_analysis": it.get("full_analysis", ""),
            "dim_scores": {
                "novelty": it.get("novelty"),
                "rigor": it.get("rigor"),
                "feasibility": it.get("feasibility"),
                "impact": it.get("impact"),
                "writability": it.get("writability"),
            },
            "v2_final_score": it.get("final_score"),
            "v2_weighted_score": it.get("final_weighted_score"),
        })

    # 4. Backup v1
    if TARGET.exists() and not BACKUP.exists():
        shutil.copy(TARGET, BACKUP)
        print(f"Backed up v1 → {BACKUP}")

    # 5. Write new
    payload = {
        "generated_at": str(date.today()),
        "schema_version": "v2.0",
        "source": "v2m-final-ranked.jsonl",
        "count": len(out),
        "discoveries": out,
    }
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    with open(TARGET, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {TARGET}: {len(out)} items")

    # 6. Report
    print("\n=== Literature status distribution (as received) ===")
    for s in sorted(lit_status_seen):
        print(f"  '{s}'")
    if missing:
        print(f"\n=== MISSING KB IDs ({len(missing)}) ===")
        for a, b, aid, bid in missing:
            print(f"  {a} → {aid} | {b} → {bid}")
    else:
        print("\nAll 19 items joined to KB successfully ✓")

    print("\n=== Preview (top 5) ===")
    for item in out[:5]:
        print(f"  #{item['rank']} [{item['final_score']}] {item['a_name']} × {item['b_name']}")
        print(f"       {item['a_domain']} ↔ {item['b_domain']}")


if __name__ == "__main__":
    main()
