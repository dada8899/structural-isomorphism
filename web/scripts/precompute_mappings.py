"""
Precompute top-N LLM mappings for high-similarity discoveries.

Run this to populate the mapping cache before launching the product.
Saves time and money by generating cached explanations for popular pairs.

Usage:
    python3 scripts/precompute_mappings.py --count 20
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path.home() / "projects" / "structural-isomorphism"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "backend" / ".env")

from services.cache import MappingCache
from services.llm_service import LLMService


async def main(count: int):
    discoveries_file = (
        Path.home()
        / "projects"
        / "structural-isomorphism"
        / "results"
        / "v2-discoveries-expanded.jsonl"
    )
    if not discoveries_file.exists():
        print(f"Discoveries file not found: {discoveries_file}")
        return

    discoveries = []
    with open(discoveries_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                discoveries.append(json.loads(line))

    print(f"Loaded {len(discoveries)} discoveries")
    discoveries = discoveries[:count]
    print(f"Will precompute {len(discoveries)} mappings")

    cache_file = Path(__file__).parent.parent / "data" / "mapping_cache.jsonl"
    cache = MappingCache(cache_file)
    llm = LLMService()

    for i, d in enumerate(discoveries, 1):
        a_id = d.get("a_id", "")
        b_id = d.get("b_id", "")
        if cache.get(a_id, b_id):
            print(f"[{i}/{len(discoveries)}] Cached: {a_id} ↔ {b_id}")
            continue

        a = {
            "id": a_id,
            "name": d.get("a_name", ""),
            "domain": d.get("a_domain", ""),
            "description": d.get("a_description", ""),
        }
        b = {
            "id": b_id,
            "name": d.get("b_name", ""),
            "domain": d.get("b_domain", ""),
            "description": d.get("b_description", ""),
        }
        sim = d.get("similarity", 0.0)

        print(f"[{i}/{len(discoveries)}] Generating: {a['name']} ({a['domain']}) ↔ {b['name']} ({b['domain']})")
        mapping = await llm.generate_mapping(a, b, sim)
        if mapping and mapping.get("structure_name") != "结构分析暂不可用":
            cache.put(a_id, b_id, mapping)
            print(f"  ✓ {mapping.get('structure_name')}")
        else:
            print(f"  ✗ Failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()
    asyncio.run(main(args.count))
