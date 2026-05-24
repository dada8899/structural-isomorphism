"""
Update KB embeddings with the X1 Neuroscience expansion (2026-05-24).

X1 audit identified Neuroscience as one of the top-3 sparsest discipline ×
type_id cells. This script appends pre-computed embeddings for the 80 new
neuroscience entries in `data/kb-additions-2026-05-24-neuroscience.jsonl`
to the existing `web/data/kb_embeddings.npy` store (and the parallel
`kb_embeddings_ids.json` ID file), preserving the index alignment with the
SearchService KB loader.

Behaviour:
- Idempotent: if a given addition id already appears in the embeddings ID
  list, it is skipped.
- Writes a backup of the existing .npy / .json files alongside (.bak) before
  overwriting.
- Mirrors the X1-Ling pipeline standard: encode descriptions only (matches
  precompute_embeddings.py), normalisation handled by the SearchService at
  query time (see `relevance_score` comment in search_service.py).

Usage:
    PYTHONPATH=. .venv/bin/python scripts/update_kb_embeddings_neuroscience.py

Outputs:
    web/data/kb_embeddings.npy         (updated, appended rows)
    web/data/kb_embeddings_ids.json    (updated, appended ids)
    web/data/kb_embeddings.npy.bak     (backup of pre-update file)
    web/data/kb_embeddings_ids.json.bak

This script is **idempotent and side-effect-only**. It does NOT modify the
KB JSONL files themselves — those live under `data/`. A separate (manual)
concatenation step is required to merge the additions into the active KB
file (`data/kb-expanded.jsonl` or `data/kb-5000-merged.jsonl`).
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

logger = logging.getLogger("update_kb_embeddings_neuroscience")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ADDITIONS_FILE = REPO / "data" / "kb-additions-2026-05-24-neuroscience.jsonl"
EMBEDDINGS_NPY = REPO / "web" / "data" / "kb_embeddings.npy"
EMBEDDINGS_IDS = REPO / "web" / "data" / "kb_embeddings_ids.json"
MODEL_PATH = REPO / "models" / "structural-v1"


def _load_additions() -> list[dict]:
    if not ADDITIONS_FILE.exists():
        raise FileNotFoundError(f"Missing additions file: {ADDITIONS_FILE}")
    rows: list[dict] = []
    with open(ADDITIONS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    logger.info(f"Loaded {len(rows)} addition rows from {ADDITIONS_FILE}")
    return rows


def _load_existing_ids() -> list[str]:
    if not EMBEDDINGS_IDS.exists():
        logger.warning(f"No existing IDs file at {EMBEDDINGS_IDS}; starting empty")
        return []
    with open(EMBEDDINGS_IDS, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_existing_embeddings(expected_n: int) -> np.ndarray | None:
    if not EMBEDDINGS_NPY.exists():
        logger.warning(f"No existing embeddings at {EMBEDDINGS_NPY}; starting empty")
        return None
    arr = np.load(EMBEDDINGS_NPY)
    if arr.shape[0] != expected_n:
        logger.error(
            "Existing embedding shape %s does not match IDs len %d; refusing to update",
            arr.shape,
            expected_n,
        )
        raise RuntimeError("embedding / id length mismatch — aborting")
    return arr


def _filter_new(rows: list[dict], existing_ids: list[str]) -> list[dict]:
    existing = set(existing_ids)
    new_rows = [r for r in rows if r["id"] not in existing]
    skipped = len(rows) - len(new_rows)
    if skipped:
        logger.info(f"{skipped} additions already in embeddings ID list — skipping")
    return new_rows


def _encode(rows: list[dict]) -> np.ndarray:
    """Encode descriptions using the same pipeline as precompute_embeddings.py."""
    from structural_isomorphism.model import encode_texts, load_model

    logger.info(f"Loading model from {MODEL_PATH}")
    model = load_model(model_path=str(MODEL_PATH) if MODEL_PATH.exists() else None)
    descriptions = [r["description"] for r in rows]
    logger.info(f"Encoding {len(descriptions)} descriptions...")
    emb = encode_texts(model, descriptions, show_progress=True)
    arr = np.asarray(emb, dtype=np.float32)
    logger.info(f"New embeddings shape: {arr.shape}")
    return arr


def _backup(path: Path) -> None:
    if path.exists():
        bak = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, bak)
        logger.info(f"Backed up {path.name} -> {bak.name}")


def main() -> int:
    additions = _load_additions()
    existing_ids = _load_existing_ids()
    existing_arr = _load_existing_embeddings(len(existing_ids))

    new_rows = _filter_new(additions, existing_ids)
    if not new_rows:
        logger.info("Nothing to encode — all additions already indexed")
        return 0

    new_emb = _encode(new_rows)

    if existing_arr is not None:
        if existing_arr.shape[1] != new_emb.shape[1]:
            raise RuntimeError(
                f"Embedding dim mismatch: existing {existing_arr.shape[1]} vs new {new_emb.shape[1]}"
            )
        merged = np.concatenate([existing_arr, new_emb], axis=0)
    else:
        merged = new_emb

    merged_ids = existing_ids + [r["id"] for r in new_rows]
    assert merged.shape[0] == len(merged_ids), "post-merge length invariant violated"

    _backup(EMBEDDINGS_NPY)
    _backup(EMBEDDINGS_IDS)

    EMBEDDINGS_NPY.parent.mkdir(parents=True, exist_ok=True)
    np.save(EMBEDDINGS_NPY, merged)
    with open(EMBEDDINGS_IDS, "w", encoding="utf-8") as f:
        json.dump(merged_ids, f, ensure_ascii=False)

    logger.info(
        "Updated embeddings: %d -> %d entries (+%d). File: %s",
        len(existing_ids),
        len(merged_ids),
        len(new_rows),
        EMBEDDINGS_NPY,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
