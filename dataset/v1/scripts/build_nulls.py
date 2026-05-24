#!/usr/bin/env python3
"""Split null-controls registry into per-case results.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # dataset/v1/
NULL_DIR = ROOT / "null_controls"

NULL_MAP = {
    "null_001_gaussian_walk": "gaussian",
    "null_002_exponential": "exponential",
    "null_003_poisson_iat": "poisson",
    "null_004_poisson_omori": "poisson_omori",
}

registry_path = NULL_DIR / "_registry.jsonl"
with open(registry_path) as fp:
    for line in fp:
        case = json.loads(line)
        cid = case["case_id"]
        slot = NULL_MAP.get(cid)
        if slot is None:
            print(f"WARN: no slot for {cid}")
            continue
        target = NULL_DIR / slot / "results.json"
        with open(target, "w") as out:
            json.dump(case, out, indent=2)
        print(f"wrote {target}")
