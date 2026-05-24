"""Unified KB embedding update — X3 expansion 2026-05-24.

This script generalises the linguistics pattern (scripts/update_kb_embeddings_linguistics.py)
so that *multiple* KB-additions JSONL files can be encoded in a single pass.

Why this script exists
----------------------
- X3 produced five additions JSONL files but no update scripts: climate-tipping,
  covid-omori, llm-scaling, zipf-empirical, city-zipf-empirical (78 entries total).
- The existing X1 neuroscience/urban update scripts call a `load_model()` helper
  whose default-checkpoint chain falls through to the *un-fine-tuned*
  shibing624/text2vec-base-chinese (the local models/structural-v1 directory
  does not exist on this machine). That would inject 80+105 = 185 rows into the
  precomputed embedding matrix using a different model than the rest of the
  matrix (which was built with models/structural-v2) — silently mixing two
  embedding spaces.
- We therefore (a) write this single script to handle X3, and (b) re-use it to
  re-encode the X1 neuroscience + urban additions with the *correct*
  structural-v2 checkpoint, so the entire precomputed matrix stays in one
  embedding space.

Behaviour
---------
- Loads one or more JSONL files (`--additions` flag, repeatable).
- For each target embedding file (kb_embeddings.npy & kb_v2_embeddings.npy):
  - Loads the existing matrix + ID sidecar.
  - Filters out additions whose id is already in the sidecar (idempotent).
  - Encodes the remaining descriptions with models/structural-v2.
  - Appends the new rows + ids, writes atomically via tmp + rename.
- Uses the same model checkpoint and normalize flags as the linguistics script
  (kb_embeddings: normalize=True; kb_v2_embeddings: normalize=False).

Side-effects
------------
- ONLY touches web/data/kb_embeddings*.{npy,json} and web/data/kb_v2_embeddings*.{npy,json}.
- NEVER modifies the source KB JSONLs in data/ — merging kb-5000-merged.jsonl is
  the separate manual concat step described in the session prompt.

Usage
-----
    # Dry-run (default — prints plan, no writes)
    PYTHONPATH=. .venv/bin/python scripts/update_kb_embeddings_x3.py

    # Apply all 7 remaining (X1 + X3) additions
    PYTHONPATH=. .venv/bin/python scripts/update_kb_embeddings_x3.py --apply

    # Specific additions only
    PYTHONPATH=. .venv/bin/python scripts/update_kb_embeddings_x3.py --apply \
        --additions data/kb-additions-2026-05-24-climate-tipping.jsonl \
        --additions data/kb-additions-2026-05-24-covid-omori.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Iterable

import numpy as np
from sentence_transformers import SentenceTransformer  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
WEB_DATA = ROOT / "web" / "data"

# Default: handle all 7 remaining additions (X1 neuro/urban + 5 X3 files).
DEFAULT_ADDITIONS = [
    ROOT / "data" / "kb-additions-2026-05-24-neuroscience.jsonl",
    ROOT / "data" / "kb-additions-2026-05-24-urban-social.jsonl",
    ROOT / "data" / "kb-additions-2026-05-24-climate-tipping.jsonl",
    ROOT / "data" / "kb-additions-2026-05-24-covid-omori.jsonl",
    ROOT / "data" / "kb-additions-2026-05-24-llm-scaling.jsonl",
    ROOT / "data" / "kb-additions-2026-05-24-zipf-empirical.jsonl",
    ROOT / "data" / "kb-additions-2026-05-24-city-zipf-empirical.jsonl",
]

TARGETS = [
    {
        "name": "kb_embeddings",
        "npy": WEB_DATA / "kb_embeddings.npy",
        "ids": WEB_DATA / "kb_embeddings_ids.json",
        "normalize": True,
    },
    {
        "name": "kb_v2_embeddings",
        "npy": WEB_DATA / "kb_v2_embeddings.npy",
        "ids": WEB_DATA / "kb_v2_embeddings_ids.json",
        "normalize": False,
    },
]

# Same checkpoint priority as the linguistics script.
MODEL_CANDIDATES = [
    str(ROOT / "models" / "structural-v2"),
    str(ROOT / "models" / "structural-v1"),
    "shibing624/text2vec-base-chinese",
]


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


def _load_additions(paths: list[Path]) -> list[dict]:
    items: list[dict] = []
    seen_ids: dict[str, str] = {}  # id -> source path (for collision reporting)
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Additions file missing: {path}")
        n_in_file = 0
        with open(path, encoding="utf-8") as f:
            for n, raw in enumerate(f, 1):
                raw = raw.strip()
                if not raw or raw.startswith("//"):
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValueError(f"{path}:{n} not valid JSON: {e}") from e
                for required in ("id", "description"):
                    if required not in rec:
                        raise ValueError(f"{path}:{n} missing required field: {required}")
                rid = rec["id"]
                if rid in seen_ids:
                    logging.warning(
                        f"duplicate id '{rid}' across additions files "
                        f"(first seen in {seen_ids[rid]}, now in {path}); keeping first"
                    )
                    continue
                seen_ids[rid] = str(path.name)
                items.append(rec)
                n_in_file += 1
        logging.info(f"Loaded {n_in_file:>4d} entries from {path.name}")
    return items


def _load_existing(npy_path: Path, ids_path: Path) -> tuple[np.ndarray, list[str]]:
    if not npy_path.exists():
        raise FileNotFoundError(f"Embedding npy missing: {npy_path}")
    if not ids_path.exists():
        raise FileNotFoundError(f"IDs sidecar missing: {ids_path}")
    emb = np.load(npy_path)
    ids = json.load(open(ids_path, encoding="utf-8"))
    if emb.shape[0] != len(ids):
        raise ValueError(
            f"Embedding row count {emb.shape[0]} != ids count {len(ids)} for {npy_path}"
        )
    return emb, ids


def _load_model() -> SentenceTransformer:
    last_err: Exception | None = None
    for candidate in MODEL_CANDIDATES:
        try:
            # Skip local paths that do not exist (don't accidentally pull
            # an un-fine-tuned HF model when a local one is intended-but-missing).
            if candidate.startswith(str(ROOT)) and not Path(candidate).exists():
                logging.debug(f"  skip (missing dir): {candidate}")
                continue
            logging.info(f"Loading model: {candidate}")
            t0 = time.time()
            model = SentenceTransformer(candidate)
            logging.info(f"Model ready ({time.time() - t0:.1f}s) — {candidate}")
            return model
        except Exception as e:  # noqa: BLE001
            logging.debug(f"  failed: {e}")
            last_err = e
    raise RuntimeError(f"Could not load any embedding checkpoint. Last error: {last_err}")


def _encode(
    model: SentenceTransformer,
    texts: Iterable[str],
    normalize: bool,
) -> np.ndarray:
    texts = list(texts)
    if not texts:
        return np.zeros((0, model.get_sentence_embedding_dimension() or 768), dtype=np.float32)
    out = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=normalize,
    )
    return out.astype(np.float32)


def _plan_diff(
    additions: list[dict], existing_ids: list[str]
) -> tuple[list[dict], list[str]]:
    present = set(existing_ids)
    new: list[dict] = []
    skip: list[str] = []
    for rec in additions:
        if rec["id"] in present:
            skip.append(rec["id"])
        else:
            new.append(rec)
    return new, skip


def _atomic_save_npy(path: Path, arr: np.ndarray) -> None:
    """np.save auto-appends .npy if path doesn't end with .npy — handle both cases."""
    tmp = path.with_name(path.name + ".tmp")
    np.save(tmp, arr)
    actual = tmp if tmp.exists() else Path(str(tmp) + ".npy")
    if not actual.exists():
        raise RuntimeError(f"np.save did not produce {tmp} or {tmp}.npy")
    actual.replace(path)


def update_one_target(
    target: dict,
    additions: list[dict],
    model: SentenceTransformer,
    apply: bool,
) -> dict:
    name = target["name"]
    emb_old, ids_old = _load_existing(target["npy"], target["ids"])
    to_encode, already = _plan_diff(additions, ids_old)

    logging.info(
        f"[{name}] existing rows = {emb_old.shape[0]} | "
        f"to encode = {len(to_encode)} | skip (already present) = {len(already)}"
    )

    if not to_encode:
        return {
            "target": name,
            "added": 0,
            "skipped": len(already),
            "final_rows": emb_old.shape[0],
            "applied": False,
        }

    descriptions = [r["description"] for r in to_encode]
    t0 = time.time()
    emb_new = _encode(model, descriptions, normalize=target["normalize"])
    logging.info(
        f"[{name}] encoded {len(to_encode)} in {time.time() - t0:.1f}s "
        f"(shape {emb_new.shape}, mean norm {float(np.linalg.norm(emb_new, axis=1).mean()):.4f})"
    )

    new_ids = ids_old + [r["id"] for r in to_encode]
    new_emb = np.vstack([emb_old, emb_new])
    assert new_emb.shape == (len(new_ids), emb_old.shape[1]), "row count mismatch"

    if apply:
        _atomic_save_npy(target["npy"], new_emb)
        tmp_ids = target["ids"].with_suffix(target["ids"].suffix + ".tmp")
        with open(tmp_ids, "w", encoding="utf-8") as f:
            json.dump(new_ids, f, ensure_ascii=False, indent=2)
        tmp_ids.replace(target["ids"])
        logging.info(f"[{name}] wrote {target['npy']} ({new_emb.shape})")
    else:
        logging.info(f"[{name}] DRY-RUN — would write {new_emb.shape} rows")

    return {
        "target": name,
        "added": len(to_encode),
        "skipped": len(already),
        "final_rows": new_emb.shape[0],
        "applied": apply,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--additions",
        action="append",
        type=Path,
        default=None,
        help="JSONL file with new entries (repeatable). Default: all 7 remaining files.",
    )
    parser.add_argument("--apply", action="store_true",
                        help="Actually encode and write the files (default: dry-run).")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)

    paths = args.additions if args.additions else DEFAULT_ADDITIONS
    additions = _load_additions(paths)
    logging.info(f"Total candidate entries: {len(additions)}")

    if not args.apply:
        logging.warning("DRY-RUN — pass --apply to actually write files")

    model = _load_model()

    summary = []
    for target in TARGETS:
        summary.append(update_one_target(target, additions, model, apply=args.apply))

    print("\n=== Summary ===")
    for s in summary:
        print(json.dumps(s, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
