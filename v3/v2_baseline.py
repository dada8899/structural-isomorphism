"""
V3 Phase 0.5: Run V2 embedding model on same 50 samples as baseline.
"""
import json
from pathlib import Path
from itertools import combinations
from sentence_transformers import SentenceTransformer, util

V3_DIR = Path(__file__).parent
PROJECT = V3_DIR.parent
V2_MODEL = PROJECT / "models" / "structural-v2"
KB = PROJECT / "data" / "kb-expanded.jsonl"

# Load 50 samples that were extracted (use Opus file as reference for IDs)
sample = [json.loads(l) for l in open(V3_DIR / "sample-opus-50.jsonl")]
ids = {x["phenomenon_id"] for x in sample}

# Find their descriptions in KB
kb_map = {}
for line in open(KB):
    p = json.loads(line)
    if p["id"] in ids:
        kb_map[p["id"]] = p

items = [kb_map[s["phenomenon_id"]] for s in sample if s["phenomenon_id"] in kb_map]
print(f"Loaded {len(items)} phenomena from KB")

# Encode
print(f"Loading V2 model from {V2_MODEL}")
model = SentenceTransformer(str(V2_MODEL))
descs = [p["description"] for p in items]
emb = model.encode(descs, show_progress_bar=True, convert_to_numpy=True)

# Pairwise sim, cross-domain only
pairs = []
for i, j in combinations(range(len(items)), 2):
    a, b = items[i], items[j]
    if a["domain"] == b["domain"]:
        continue
    sim = float(util.cos_sim(emb[i], emb[j]))
    pairs.append({
        "score": round(sim, 3),
        "a_id": a["id"],
        "a_name": a["name"],
        "a_domain": a["domain"],
        "b_id": b["id"],
        "b_name": b["name"],
        "b_domain": b["domain"],
    })

pairs.sort(key=lambda x: -x["score"])
print(f"\nTotal cross-domain pairs: {len(pairs)}")
print(f"\nTop 20:")
for r, p in enumerate(pairs[:20], 1):
    print(f"  {r:2d}. {p['score']:.3f}  {p['a_name']} × {p['b_name']}")

with open(V3_DIR / "v2-top20.jsonl", "w") as f:
    for p in pairs[:20]:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")
print(f"\nSaved top 20 to v3/v2-top20.jsonl")
