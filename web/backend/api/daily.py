"""GET /api/daily — 今日发现（3 组跨领域同构）"""
import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter

router = APIRouter(tags=["daily"])

_discoveries: Optional[List[dict]] = None


def _load_discoveries():
    global _discoveries
    if _discoveries is not None:
        return _discoveries

    data_dir = os.getenv("STRUCTURAL_DATA_DIR", "")
    # Original v2 discoveries jsonl (preferred — has full a/b descriptions)
    results_dir = Path(data_dir).parent / "results" if data_dir else None
    candidates = []
    if results_dir:
        candidates = [
            results_dir / "v2-discoveries-expanded-top5000.jsonl",
            results_dir / "v2-discoveries-expanded.jsonl",
            results_dir / "v2-discoveries.jsonl",
        ]

    _discoveries = []
    for p in candidates:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            _discoveries.append(json.loads(line))
                        except Exception:
                            pass
            break

    # Fallback: the A-grade curated discoveries the /api/discoveries endpoint
    # uses. This is the file that's actually shipped to VPS.
    if not _discoveries:
        a_path = Path(__file__).parent.parent.parent / "data" / "a_discoveries.json"
        if a_path.exists():
            try:
                with open(a_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                _discoveries = payload.get("discoveries", []) or []
            except Exception:
                pass

    return _discoveries


@router.get("/daily")
async def daily_discoveries():
    from main import app_state

    discoveries = _load_discoveries()
    if not discoveries:
        return {"date": str(date.today()), "discoveries": []}

    svc = app_state.get("search")

    # Pick 3 deterministically based on today's date
    seed = int(hashlib.md5(str(date.today()).encode()).hexdigest()[:8], 16)
    n = len(discoveries)

    # Pick 3 diverse indexes
    picks = []
    offset = seed % n
    stride = max(1, n // 3)
    for i in range(3):
        idx = (offset + i * stride) % n
        d = discoveries[idx]

        # Enrich from search service when fields are missing (a_discoveries.json
        # doesn't ship type_id / description — look them up from the KB).
        a_id = d.get("a_id", "")
        b_id = d.get("b_id", "")
        a_full = svc.get_by_id(a_id) if svc and a_id else None
        b_full = svc.get_by_id(b_id) if svc and b_id else None

        # Similarity: prefer explicit similarity, fall back to confidence/100
        sim = d.get("similarity")
        if sim is None:
            conf = d.get("isomorphism_confidence")
            if conf is not None:
                sim = float(conf) / 100.0
            else:
                sim = 0.0

        picks.append({
            "a": {
                "id": a_id,
                "name": d.get("a_name") or (a_full or {}).get("name", ""),
                "domain": d.get("a_domain") or (a_full or {}).get("domain", ""),
                "type_id": d.get("a_type_id") or (a_full or {}).get("type_id", ""),
                "description": d.get("a_description") or (a_full or {}).get("description", ""),
            },
            "b": {
                "id": b_id,
                "name": d.get("b_name") or (b_full or {}).get("name", ""),
                "domain": d.get("b_domain") or (b_full or {}).get("domain", ""),
                "type_id": d.get("b_type_id") or (b_full or {}).get("type_id", ""),
                "description": d.get("b_description") or (b_full or {}).get("description", ""),
            },
            "similarity": round(float(sim), 4),
        })

    return {"date": str(date.today()), "discoveries": picks}
