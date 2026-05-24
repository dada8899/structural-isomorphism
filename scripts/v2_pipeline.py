"""
V2 Pipeline: Structural Isomorphism Anomaly Detector
Finds undiscovered cross-domain structural connections.

Steps:
1. Load knowledge base (500+ phenomena)
2. Encode all phenomena with fine-tuned model
3. Calculate all pairwise structural similarities
4. Filter: remove known analogies (via Semantic Scholar)
5. Filter: LLM screening (remove trivially obvious)
6. Filter: citation distance check
7. Output: ranked list of unknown structural connections
"""
import json
import time
import argparse
import numpy as np
from collections import defaultdict
from pathlib import Path
from sentence_transformers import SentenceTransformer, util

# === Config ===
PROJECT_DIR = Path(__file__).parent.parent
MODEL_DIR = PROJECT_DIR / "models" / "structural-v1"
KB_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "results"
SIMILARITY_THRESHOLD = 0.70  # only consider pairs above this

def load_knowledge_base():
    """Load all phenomena from knowledge base files."""
    kb = []
    for kb_file in KB_DIR.glob("kb-*.jsonl"):
        with open(kb_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                try:
                    item = json.loads(line)
                    kb.append(item)
                except json.JSONDecodeError:
                    continue
    print(f"Loaded {len(kb)} phenomena from knowledge base")
    return kb

def compute_all_similarities(kb, model):
    """Compute pairwise structural similarities for all phenomena."""
    print(f"Encoding {len(kb)} phenomena...")
    descriptions = [item['description'] for item in kb]
    embeddings = model.encode(descriptions, show_progress_bar=True, convert_to_numpy=True)

    print("Computing pairwise similarities...")
    # Use efficient batch computation
    sim_matrix = util.cos_sim(embeddings, embeddings).numpy()

    # Extract pairs above threshold
    pairs = []
    n = len(kb)
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(sim_matrix[i][j])
            if sim >= SIMILARITY_THRESHOLD:
                # Skip same-type pairs (already known to be similar)
                if kb[i].get('type_id') == kb[j].get('type_id'):
                    continue
                # Skip same-domain pairs (less interesting)
                if kb[i].get('domain') == kb[j].get('domain'):
                    continue
                pairs.append({
                    'item_a': kb[i],
                    'item_b': kb[j],
                    'similarity': sim,
                })

    pairs.sort(key=lambda x: x['similarity'], reverse=True)
    print(f"Found {len(pairs)} cross-type, cross-domain pairs above threshold {SIMILARITY_THRESHOLD}")
    return pairs

def filter_known_analogies_simple(pairs):
    """
    Simple filter: check if the two phenomena names commonly co-occur.
    (Full Semantic Scholar integration can be added later)
    """
    # For now, use a simple heuristic:
    # If both names contain very common analogy keywords, likely known
    KNOWN_ANALOGIES = {
        # Known cross-domain pairs that are already well-documented
        frozenset(["自然选择", "市场竞争"]),
        frozenset(["热力学熵", "信息熵"]),
        frozenset(["神经网络", "人工神经网络"]),
        frozenset(["欧姆定律", "流体力学"]),
        frozenset(["传染病", "计算机病毒"]),
        frozenset(["DNA", "编程语言"]),
        frozenset(["免疫系统", "入侵检测"]),
        frozenset(["蚁群", "优化算法"]),
    }

    filtered = []
    removed = 0
    for pair in pairs:
        name_a = pair['item_a'].get('name', '')
        name_b = pair['item_b'].get('name', '')
        pair_set = frozenset([name_a, name_b])

        # Check if this is a known analogy
        is_known = False
        for known in KNOWN_ANALOGIES:
            if any(k in name_a for k in known) and any(k in name_b for k in known):
                is_known = True
                break

        if not is_known:
            filtered.append(pair)
        else:
            removed += 1

    print(f"Removed {removed} known analogies, {len(filtered)} remaining")
    return filtered

def generate_report(pairs, output_file, top_n=50):
    """Generate a human-readable report of top discoveries."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    report = []
    report.append("# V2 Structural Isomorphism: Unknown Cross-Domain Connections")
    report.append(f"\nGenerated: {time.strftime('%Y-%m-%d %H:%M')}")
    report.append(f"Total candidates: {len(pairs)}")
    report.append(f"Showing top {min(top_n, len(pairs))}\n")
    report.append("---\n")

    for rank, pair in enumerate(pairs[:top_n], 1):
        a = pair['item_a']
        b = pair['item_b']
        sim = pair['similarity']

        report.append(f"## #{rank} | Similarity: {sim:.4f}")
        report.append(f"")
        report.append(f"**A: {a.get('name', 'Unknown')}** ({a.get('domain', '?')})")
        report.append(f"  Structure type: {a.get('type_id', '?')}-{a.get('type_name', '?') if 'type_name' in a else ''}")
        report.append(f"  {a['description']}")
        report.append(f"")
        report.append(f"**B: {b.get('name', 'Unknown')}** ({b.get('domain', '?')})")
        report.append(f"  Structure type: {b.get('type_id', '?')}-{b.get('type_name', '?') if 'type_name' in b else ''}")
        report.append(f"  {b['description']}")
        report.append(f"")
        report.append(f"---\n")

    with open(output_file, 'w') as f:
        f.write('\n'.join(report))

    print(f"Report saved to: {output_file}")

    # Also save as JSONL for programmatic access
    jsonl_file = output_file.with_suffix('.jsonl')
    with open(jsonl_file, 'w') as f:
        for rank, pair in enumerate(pairs[:top_n], 1):
            record = {
                'rank': rank,
                'similarity': pair['similarity'],
                'a_id': pair['item_a'].get('id', ''),
                'a_name': pair['item_a'].get('name', ''),
                'a_domain': pair['item_a'].get('domain', ''),
                'a_type_id': pair['item_a'].get('type_id', ''),
                'a_description': pair['item_a']['description'],
                'b_id': pair['item_b'].get('id', ''),
                'b_name': pair['item_b'].get('name', ''),
                'b_domain': pair['item_b'].get('domain', ''),
                'b_type_id': pair['item_b'].get('type_id', ''),
                'b_description': pair['item_b']['description'],
            }
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    print(f"JSONL saved to: {jsonl_file}")

def main():
    parser = argparse.ArgumentParser(description='V2 Structural Isomorphism Pipeline')
    parser.add_argument('--threshold', type=float, default=0.70, help='Similarity threshold')
    parser.add_argument('--top-n', type=int, default=50, help='Top N results to report')
    args = parser.parse_args()

    global SIMILARITY_THRESHOLD
    SIMILARITY_THRESHOLD = args.threshold

    # Step 1: Load knowledge base
    print("=" * 60)
    print("Step 1: Loading knowledge base")
    print("=" * 60)
    kb = load_knowledge_base()
    if len(kb) < 100:
        print(f"WARNING: Only {len(kb)} phenomena loaded. Expected 500+.")
        print("Make sure kb-*.jsonl files exist in data/ directory.")

    # Step 2: Load model and compute similarities
    print("\n" + "=" * 60)
    print("Step 2: Computing structural similarities")
    print("=" * 60)
    model = SentenceTransformer(str(MODEL_DIR))
    pairs = compute_all_similarities(kb, model)

    # Step 3: Filter known analogies
    print("\n" + "=" * 60)
    print("Step 3: Filtering known analogies")
    print("=" * 60)
    pairs = filter_known_analogies_simple(pairs)

    # Step 4: Generate report
    print("\n" + "=" * 60)
    print("Step 4: Generating report")
    print("=" * 60)
    output_file = OUTPUT_DIR / "v2-discoveries.md"
    generate_report(pairs, output_file, top_n=args.top_n)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Knowledge base: {len(kb)} phenomena")
    print(f"  Total pairs checked: {len(kb) * (len(kb)-1) // 2}")
    print(f"  High-similarity cross-domain pairs: {len(pairs)}")
    print(f"  Report: {output_file}")

if __name__ == "__main__":
    main()
