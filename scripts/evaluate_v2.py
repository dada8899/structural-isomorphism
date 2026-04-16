"""
V2 Model Evaluation: Compare V1 vs V2 model on the same test set.
"""
import json
import numpy as np
from collections import defaultdict
from pathlib import Path
from sentence_transformers import SentenceTransformer, util

DATA_FILE = Path(__file__).parent.parent / "data" / "clean-expanded.jsonl"
V1_MODEL = Path(__file__).parent.parent / "models" / "structural-v1"
V2_MODEL = Path(__file__).parent.parent / "models" / "structural-v2"
BASE_MODEL = "shibing624/text2vec-base-chinese"

print("Loading data...")
type_descriptions = defaultdict(list)
all_descriptions = []
all_type_ids = []

with open(DATA_FILE) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        item = json.loads(line)
        type_descriptions[item["type_id"]].append(item["description"])
        all_descriptions.append(item["description"])
        all_type_ids.append(item["type_id"])

print(f"Loaded {len(all_descriptions)} descriptions, {len(type_descriptions)} types")

# Sample subset for speed (1000 random)
import random
random.seed(42)
indices = random.sample(range(len(all_descriptions)), min(1000, len(all_descriptions)))
sub_descriptions = [all_descriptions[i] for i in indices]
sub_type_ids = [all_type_ids[i] for i in indices]
print(f"Using {len(sub_descriptions)} samples")

print("\nEncoding with V1 model...")
v1 = SentenceTransformer(str(V1_MODEL))
v1_emb = v1.encode(sub_descriptions, show_progress_bar=True, convert_to_numpy=True)

print("\nEncoding with V2 model...")
v2 = SentenceTransformer(str(V2_MODEL))
v2_emb = v2.encode(sub_descriptions, show_progress_bar=True, convert_to_numpy=True)

# Silhouette
from sklearn.metrics import silhouette_score
unique_types = sorted(set(sub_type_ids))
type_to_num = {t: i for i, t in enumerate(unique_types)}
labels = np.array([type_to_num[t] for t in sub_type_ids])

v1_sil = silhouette_score(v1_emb, labels, metric='cosine')
v2_sil = silhouette_score(v2_emb, labels, metric='cosine')

print("\n=== Silhouette Score ===")
print(f"V1: {v1_sil:.4f}")
print(f"V2: {v2_sil:.4f}")
print(f"Improvement: {v2_sil - v1_sil:+.4f}")

# Retrieval@5
def retrieval_at_k(embeddings, k=5, n_queries=200):
    type_indices = defaultdict(list)
    for i, tid in enumerate(sub_type_ids):
        type_indices[tid].append(i)

    hits, total = 0, 0
    query_indices = random.sample(range(len(sub_descriptions)), min(n_queries, len(sub_descriptions)))
    for qi in query_indices:
        query_type = sub_type_ids[qi]
        sims = util.cos_sim(embeddings[qi], embeddings)[0]
        top_indices = sims.argsort(descending=True)[1:k+1]
        for idx in top_indices:
            if sub_type_ids[idx] == query_type:
                hits += 1
            total += 1
    return hits / total if total > 0 else 0

print("\n=== Retrieval@5 ===")
v1_r5 = retrieval_at_k(v1_emb, k=5)
v2_r5 = retrieval_at_k(v2_emb, k=5)
print(f"V1: {v1_r5:.1%}")
print(f"V2: {v2_r5:.1%}")
print(f"Improvement: {(v2_r5 - v1_r5)*100:+.1f}%")

# Intra/Inter
def sample_sims(embeddings, n=500):
    intra, inter = [], []
    type_indices = defaultdict(list)
    for i, tid in enumerate(sub_type_ids):
        type_indices[tid].append(i)
    for _ in range(n):
        tid = random.choice(list(type_indices.keys()))
        if len(type_indices[tid]) < 2: continue
        i, j = random.sample(type_indices[tid], 2)
        intra.append(float(util.cos_sim(embeddings[i], embeddings[j])))
    for _ in range(n):
        tid1, tid2 = random.sample(list(type_indices.keys()), 2)
        i = random.choice(type_indices[tid1])
        j = random.choice(type_indices[tid2])
        inter.append(float(util.cos_sim(embeddings[i], embeddings[j])))
    return np.array(intra), np.array(inter)

print("\n=== Intra/Inter ===")
v1_intra, v1_inter = sample_sims(v1_emb)
v2_intra, v2_inter = sample_sims(v2_emb)
print(f"V1: intra={v1_intra.mean():.4f} inter={v1_inter.mean():.4f} gap={v1_intra.mean()-v1_inter.mean():.4f}")
print(f"V2: intra={v2_intra.mean():.4f} inter={v2_inter.mean():.4f} gap={v2_intra.mean()-v2_inter.mean():.4f}")

# Save results
results = {
    "v1_silhouette": v1_sil,
    "v2_silhouette": v2_sil,
    "v1_retrieval_5": v1_r5,
    "v2_retrieval_5": v2_r5,
    "v1_intra_mean": float(v1_intra.mean()),
    "v1_inter_mean": float(v1_inter.mean()),
    "v1_gap": float(v1_intra.mean() - v1_inter.mean()),
    "v2_intra_mean": float(v2_intra.mean()),
    "v2_inter_mean": float(v2_inter.mean()),
    "v2_gap": float(v2_intra.mean() - v2_inter.mean()),
}
with open(Path(__file__).parent.parent / "results" / "v1-vs-v2-comparison.json", "w") as f:
    json.dump(results, f, indent=2)
print("\nResults saved")
