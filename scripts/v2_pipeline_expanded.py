"""
V2 Pipeline on expanded 4443-phenomenon knowledge base.
Uses existing V1 model (Silhouette 0.85).
"""
import json
import time
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer, util

PROJECT_DIR = Path(__file__).parent.parent
MODEL_DIR = PROJECT_DIR / "models" / "structural-v1"
KB_FILE = PROJECT_DIR / "data" / "kb-expanded.jsonl"
OUTPUT_DIR = PROJECT_DIR / "results"

# Higher threshold since we have more data
SIMILARITY_THRESHOLD = 0.70
TOP_N_OUTPUT = 5000  # Output top 5000 for screening

def main():
    print("=" * 60)
    print("V2 Pipeline on Expanded KB")
    print("=" * 60)

    # Load KB
    print("\nLoading knowledge base...")
    kb = []
    with open(KB_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    kb.append(json.loads(line))
                except:
                    pass
    print(f"Loaded {len(kb)} phenomena")

    # Load model
    print(f"\nLoading V1 model from {MODEL_DIR}...")
    model = SentenceTransformer(str(MODEL_DIR))

    # Encode all phenomena
    print(f"\nEncoding {len(kb)} phenomena...")
    start = time.time()
    descriptions = [item['description'] for item in kb]
    embeddings = model.encode(
        descriptions,
        show_progress_bar=True,
        convert_to_numpy=True,
        batch_size=64,
    )
    print(f"Encoding done in {time.time()-start:.1f}s")

    # Compute all pairwise similarities in chunks to save memory
    print("\nComputing pairwise similarities...")
    start = time.time()
    n = len(kb)
    pairs = []

    # Process in chunks
    chunk_size = 500
    total_chunks = (n + chunk_size - 1) // chunk_size
    processed = 0

    for chunk_i in range(total_chunks):
        i_start = chunk_i * chunk_size
        i_end = min(i_start + chunk_size, n)
        chunk_emb = embeddings[i_start:i_end]

        # Compute sim with ALL items (including self)
        sim_matrix = util.cos_sim(chunk_emb, embeddings).numpy()

        for li, i in enumerate(range(i_start, i_end)):
            for j in range(i + 1, n):
                sim = float(sim_matrix[li][j])
                if sim >= SIMILARITY_THRESHOLD:
                    # Skip same type/domain
                    if kb[i].get('type_id') == kb[j].get('type_id'):
                        continue
                    if kb[i].get('domain') == kb[j].get('domain'):
                        continue
                    pairs.append({
                        'i': i, 'j': j, 'similarity': sim,
                    })
        processed = i_end
        if chunk_i % 2 == 0:
            print(f"  Processed {processed}/{n} ({len(pairs)} pairs found)")

    # Sort by similarity
    pairs.sort(key=lambda x: -x['similarity'])
    print(f"\nTotal pairs above {SIMILARITY_THRESHOLD}: {len(pairs)}")
    print(f"Similarity computation: {time.time()-start:.1f}s")

    # Save full results and top N
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Convert to full records
    full_pairs = []
    for rank, p in enumerate(pairs, 1):
        a, b = kb[p['i']], kb[p['j']]
        full_pairs.append({
            'rank': rank,
            'similarity': p['similarity'],
            'a_id': a.get('id', ''),
            'a_name': a.get('name', ''),
            'a_domain': a.get('domain', ''),
            'a_type_id': a.get('type_id', ''),
            'a_description': a.get('description', ''),
            'b_id': b.get('id', ''),
            'b_name': b.get('name', ''),
            'b_domain': b.get('domain', ''),
            'b_type_id': b.get('type_id', ''),
            'b_description': b.get('description', ''),
        })

    # Save all
    with open(OUTPUT_DIR / 'v2-discoveries-expanded.jsonl', 'w') as f:
        for p in full_pairs:
            f.write(json.dumps(p, ensure_ascii=False) + '\n')
    print(f"\nSaved: results/v2-discoveries-expanded.jsonl ({len(full_pairs)} pairs)")

    # Top N
    with open(OUTPUT_DIR / 'v2-discoveries-expanded-top5000.jsonl', 'w') as f:
        for p in full_pairs[:TOP_N_OUTPUT]:
            f.write(json.dumps(p, ensure_ascii=False) + '\n')
    print(f"Saved: results/v2-discoveries-expanded-top5000.jsonl")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Phenomena: {n}")
    print(f"  Total pair checks: {n*(n-1)//2:,}")
    print(f"  High-similarity cross-domain pairs: {len(pairs):,}")
    print(f"  Top {TOP_N_OUTPUT} saved for screening")

if __name__ == '__main__':
    main()
