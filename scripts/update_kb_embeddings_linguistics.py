"""Incremental KB embedding update — Linguistics expansion 2026-05-24.

Reads new entries from data/kb-additions-2026-05-24-linguistics.jsonl,
encodes their `description` field with the same SentenceTransformer
checkpoint used for the existing precomputed embedding files, and appends
the new vectors to both:

  - web/data/kb_embeddings.npy        (L2-normalized, used by deploy.sh prod)
  - web/data/kb_v2_embeddings.npy     (un-normalized, used by /api/v2 path)

The ID-order JSON sidecars are updated in lockstep so that the i-th row of
the .npy still corresponds to ids[i].

Idempotency
-----------
Re-running the script is safe: IDs already present in the sidecar are
skipped (we only encode + append the *new* ones). The dry-run mode does
not write anything; it just prints the planned diff.

Why this script exists
----------------------
Re-encoding the whole KB takes ~5 min and burns OpenAI/HF bandwidth even
when only 150/4475 entries (3.4%) changed. This incremental path is the
norm for any small KB expansion in this repo. The full re-encode is
reserved for model checkpoint swaps.

Usage
-----
    # Dry-run — print what would change but write nothing
    PYTHONPATH=. .venv/bin/python scripts/update_kb_embeddings_linguistics.py --dry-run

    # Apply — encode + append + write sidecars
    PYTHONPATH=. .venv/bin/python scripts/update_kb_embeddings_linguistics.py --apply

    # Custom additions file
    PYTHONPATH=. .venv/bin/python scripts/update_kb_embeddings_linguistics.py \
        --apply --additions data/some-other-additions.jsonl

The script never touches the source KB jsonl files; merging the additions
into the main `kb-5000-merged.jsonl` is a separate, deliberately manual
step (review first, append later).
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

# We deliberately avoid `from structural_isomorphism.model import ...` here:
# a parallel session is doing a git-history scrub on that package and may
# leave it temporarily un-importable. SentenceTransformer direct.
from sentence_transformers import SentenceTransformer  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ADDITIONS = ROOT / "data" / "kb-additions-2026-05-24-linguistics.jsonl"
WEB_DATA = ROOT / "web" / "data"

# Two embedding targets (different normalization / model checkpoints).
TARGETS = [
    {
        "name": "kb_embeddings",
        "npy": WEB_DATA / "kb_embeddings.npy",
        "ids": WEB_DATA / "kb_embeddings_ids.json",
        "normalize": True,
        # Same checkpoint as the rest of kb_embeddings.npy (norms all = 1.0,
        # matches model.encode_texts default).
    },
    {
        "name": "kb_v2_embeddings",
        "npy": WEB_DATA / "kb_v2_embeddings.npy",
        "ids": WEB_DATA / "kb_v2_embeddings_ids.json",
        "normalize": False,  # existing rows have norms ~18; preserve scale
    },
]

# Model checkpoint priority (first that loads wins).
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


def _load_additions(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Additions file missing: {path}")
    items: list[dict] = []
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
            items.append(rec)
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
            f"Embedding row count {emb.shape[0]} != ids count {len(ids)} "
            f"for {npy_path}"
        )
    return emb, ids


def _load_model() -> SentenceTransformer:
    last_err: Exception | None = None
    for candidate in MODEL_CANDIDATES:
        try:
            logging.info(f"Loading model: {candidate}")
            t0 = time.time()
            model = SentenceTransformer(candidate)
            logging.info(f"Model ready ({time.time() - t0:.1f}s) — {candidate}")
            return model
        except Exception as e:  # noqa: BLE001
            logging.debug(f"  failed: {e}")
            last_err = e
    raise RuntimeError(
        f"Could not load any embedding checkpoint. Last error: {last_err}"
    )


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
    """Return (records_to_encode, ids_already_present)."""
    present = set(existing_ids)
    new: list[dict] = []
    skip: list[str] = []
    for rec in additions:
        if rec["id"] in present:
            skip.append(rec["id"])
        else:
            new.append(rec)
    return new, skip


def update_one_target(
    target: dict,
    additions: list[dict],
    model: SentenceTransformer,
    apply: bool,
) -> dict:
    """Encode and append for a single embedding file. Returns a summary."""
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
        # Atomic-ish swap: write .tmp, then rename.
        tmp_npy = target["npy"].with_suffix(target["npy"].suffix + ".tmp")
        tmp_ids = target["ids"].with_suffix(target["ids"].suffix + ".tmp")
        np.save(tmp_npy, new_emb)
        with open(tmp_ids, "w", encoding="utf-8") as f:
            json.dump(new_ids, f, ensure_ascii=False, indent=2)
        tmp_npy.replace(target["npy"])
        tmp_ids.replace(target["ids"])
        logging.info(f"[{name}] wrote {target['npy']} ({new_emb.shape})")
    else:
        logging.info(f"[{name}] DRY-RUN — would write {new_emb.shape} rows (no files touched)")

    return {
        "target": name,
        "added": len(to_encode),
        "skipped": len(already),
        "final_rows": new_emb.shape[0],
        "applied": apply,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--additions", type=Path, default=DEFAULT_ADDITIONS,
                        help=f"JSONL file with new entries (default: {DEFAULT_ADDITIONS.relative_to(ROOT)})")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Plan only, do not write (DEFAULT — safe).")
    parser.add_argument("--apply", action="store_true",
                        help="Actually encode and write the files.")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)

    apply = args.apply
    if apply and args.dry_run:
        # --apply overrides --dry-run; the default for --dry-run is True so we
        # can't distinguish "user passed --dry-run" from "we defaulted to it".
        # Treat --apply as authoritative.
        pass

    additions = _load_additions(args.additions)
    logging.info(f"Loaded {len(additions)} candidate entries from {args.additions}")

    if not apply:
        logging.warning("DRY-RUN — pass --apply to actually write files")
        # In dry-run we still want to load the model so the user sees the
        # full plan; this is the slow step (~13s) so it's the only reason a
        # user might pass --verbose to skip the apply later.
        model = _load_model()
    else:
        model = _load_model()

    summary = []
    for target in TARGETS:
        summary.append(update_one_target(target, additions, model, apply=apply))

    print("\n=== Summary ===")
    for s in summary:
        print(json.dumps(s, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
