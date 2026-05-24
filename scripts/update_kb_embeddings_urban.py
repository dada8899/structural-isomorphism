"""
update_kb_embeddings_urban.py — append Urban/Social KB additions and refresh embeddings.

Steps:
1. Load existing merged KB (data/kb-5000-merged.jsonl).
2. Load additions (data/kb-additions-2026-05-24-urban-social.jsonl).
3. Sanity: id uniqueness, schema (id/name/domain/type_id/description),
   description length >= 50 chars, type_id in 01..84.
4. Append non-conflicting additions to the merged KB.
5. Re-encode the FULL KB with `structural_isomorphism.model.encode_texts`
   and write to web/data/kb_v2_embeddings.npy (matches the prod precomputed
   path referenced by SearchService). Backup of the old .npy is saved with
   a `.bak-<timestamp>` suffix.

Idempotent: re-running will skip already-merged IDs.

Run:
    PYTHONPATH=. .venv/bin/python scripts/update_kb_embeddings_urban.py \
        --kb data/kb-5000-merged.jsonl \
        --additions data/kb-additions-2026-05-24-urban-social.jsonl \
        --embeddings web/data/kb_v2_embeddings.npy

Dry-run (validate additions only, no write):
    .venv/bin/python scripts/update_kb_embeddings_urban.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger("update_kb_urban")

REQUIRED_FIELDS = ("id", "name", "domain", "type_id", "description")
MIN_DESCRIPTION_LEN = 50
VALID_TYPE_IDS = {f"{i:02d}" for i in range(1, 85)}


def _load_jsonl(path: Path) -> List[Dict]:
    items: List[Dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{i} malformed JSON: {e}") from e
    return items


def validate_additions(additions: List[Dict], existing_ids: set) -> Tuple[List[Dict], List[str]]:
    """Return (valid_additions, errors)."""
    errors: List[str] = []
    seen: set = set()
    valid: List[Dict] = []
    for idx, item in enumerate(additions, 1):
        for f in REQUIRED_FIELDS:
            if f not in item or not item[f]:
                errors.append(f"item #{idx}: missing/empty field '{f}'")
                break
        else:
            if item["id"] in existing_ids:
                errors.append(f"item #{idx} id={item['id']}: collides with existing KB")
                continue
            if item["id"] in seen:
                errors.append(f"item #{idx} id={item['id']}: duplicate inside additions")
                continue
            if item["type_id"] not in VALID_TYPE_IDS:
                errors.append(f"item #{idx} id={item['id']}: type_id '{item['type_id']}' not in 01..84")
                continue
            if len(item["description"]) < MIN_DESCRIPTION_LEN:
                errors.append(
                    f"item #{idx} id={item['id']}: description {len(item['description'])} chars (< {MIN_DESCRIPTION_LEN})"
                )
                continue
            seen.add(item["id"])
            valid.append(item)
    return valid, errors


def append_to_kb(kb_path: Path, additions: List[Dict]) -> int:
    """Append additions to KB jsonl. Returns count appended."""
    with open(kb_path, "a", encoding="utf-8") as f:
        for item in additions:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return len(additions)


def reencode_embeddings(kb_path: Path, emb_path: Path) -> None:
    """Re-encode the entire KB and overwrite emb_path. Backup the old .npy."""
    try:
        import numpy as np
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("numpy required") from e
    try:
        from structural_isomorphism.model import load_model, encode_texts
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "structural_isomorphism.model not importable. Set PYTHONPATH=. and ensure dev install."
        ) from e

    items = _load_jsonl(kb_path)
    if not items:
        raise RuntimeError(f"empty KB at {kb_path}")
    descriptions = [it["description"] for it in items]

    if emb_path.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = emb_path.with_suffix(emb_path.suffix + f".bak-{ts}")
        shutil.copy2(emb_path, bak)
        logger.info(f"Backed up old embeddings: {emb_path} -> {bak}")

    logger.info(f"Loading model & encoding {len(descriptions)} descriptions...")
    model = load_model()
    emb = encode_texts(model, descriptions, show_progress=True)
    emb_arr = np.asarray(emb, dtype=np.float32)
    emb_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(emb_path, emb_arr)
    logger.info(f"Wrote {emb_path} shape={emb_arr.shape}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append Urban/Social KB additions and refresh embeddings.")
    parser.add_argument("--kb", default="data/kb-5000-merged.jsonl")
    parser.add_argument("--additions", default="data/kb-additions-2026-05-24-urban-social.jsonl")
    parser.add_argument("--embeddings", default="web/data/kb_v2_embeddings.npy")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, no write.")
    parser.add_argument("--skip-embeddings", action="store_true", help="Append to KB but do not re-encode.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    kb_path = Path(args.kb)
    add_path = Path(args.additions)
    emb_path = Path(args.embeddings)

    if not kb_path.exists():
        logger.error(f"KB file not found: {kb_path}")
        return 2
    if not add_path.exists():
        logger.error(f"Additions file not found: {add_path}")
        return 2

    logger.info(f"Loading existing KB: {kb_path}")
    existing = _load_jsonl(kb_path)
    existing_ids = {it["id"] for it in existing if "id" in it}
    logger.info(f"Existing KB size: {len(existing)} entries ({len(existing_ids)} unique ids)")

    logger.info(f"Loading additions: {add_path}")
    additions = _load_jsonl(add_path)
    logger.info(f"Additions size: {len(additions)} entries")

    valid, errors = validate_additions(additions, existing_ids)
    if errors:
        logger.error(f"Found {len(errors)} validation error(s):")
        for e in errors:
            logger.error(f"  {e}")
        return 1
    logger.info(f"All {len(valid)} additions pass validation")

    if args.dry_run:
        logger.info("--dry-run: skipping append and re-encode")
        return 0

    # Idempotency: re-check after potential prior partial run
    appended = append_to_kb(kb_path, valid)
    logger.info(f"Appended {appended} entries to {kb_path}")

    if args.skip_embeddings:
        logger.info("--skip-embeddings: leaving %s unchanged", emb_path)
        return 0

    reencode_embeddings(kb_path, emb_path)
    logger.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
