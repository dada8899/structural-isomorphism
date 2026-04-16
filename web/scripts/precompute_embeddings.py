"""
Precompute KB embeddings and save to a numpy file.
This allows the VPS to load pre-computed embeddings in seconds
instead of re-encoding 4475 phenomena (which takes ~10 min on CPU).

Usage:
    python3 scripts/precompute_embeddings.py
"""
import json
import os
import sys
from pathlib import Path

import numpy as np

# Path setup
REPO = Path.home() / "projects" / "structural-isomorphism"
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "backend" / ".env")

from structural_isomorphism.model import load_model, encode_texts

KB_FILE = REPO / "data" / "kb-5000-merged.jsonl"
MODEL_PATH = REPO / "models" / "structural-v1"
OUTPUT_DIR = Path(__file__).parent.parent / "data"
OUTPUT_NPY = OUTPUT_DIR / "kb_embeddings.npy"
OUTPUT_IDS = OUTPUT_DIR / "kb_embeddings_ids.json"


def main():
    print(f"Loading KB from {KB_FILE}")
    items = []
    with open(KB_FILE) as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    print(f"Loaded {len(items)} phenomena")

    print(f"Loading model from {MODEL_PATH}")
    model = load_model(model_path=str(MODEL_PATH))

    print("Encoding...")
    descriptions = [item["description"] for item in items]
    embeddings = encode_texts(model, descriptions, show_progress=True)
    print(f"Embeddings shape: {embeddings.shape}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    np.save(OUTPUT_NPY, embeddings)
    print(f"Saved embeddings to {OUTPUT_NPY} ({OUTPUT_NPY.stat().st_size / 1024 / 1024:.1f} MB)")

    # Save IDs in parallel order for verification
    ids = [item.get("id", "") for item in items]
    with open(OUTPUT_IDS, "w") as f:
        json.dump(ids, f)
    print(f"Saved {len(ids)} IDs to {OUTPUT_IDS}")


if __name__ == "__main__":
    main()
