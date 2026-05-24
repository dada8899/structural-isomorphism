#!/usr/bin/env python3
"""
generate_manifest.py — idempotent MANIFEST.json builder for the bundle.

Walks the bundle root (the directory two levels up from this script) and
records, for every file:
  - posix relative path (relative to bundle root)
  - sha256
  - size_bytes
  - license (CC-BY-4.0 for *data* files; MIT for *.py / *.ipynb / *.yaml schemas)
  - schema_ref (the section in README.md that documents this file's columns)

Idempotency: file order is deterministic (sorted by relpath); JSON is dumped
with sort_keys=True so identical content -> identical bytes.

Excludes itself + any other files under repro/_cache/ from the manifest.

Usage:
  python repro/generate_manifest.py
  # writes MANIFEST.json at the bundle root
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

BUNDLE = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {"__pycache__", "_cache", ".pytest_cache", ".ipynb_checkpoints", "out"}
EXCLUDE_FILE_PREFIXES = (".DS_Store",)

# Heuristic: filename pattern -> license + schema reference
def classify(relpath: str) -> tuple[str, Optional[str]]:
    p = relpath.lower()
    if p.endswith((".py", ".ipynb", ".toml", ".cff")) or p.endswith("makefile"):
        license_id = "MIT"
    elif p.endswith((".yaml", ".yml", ".md", ".txt")):
        # schema YAMLs are MIT (machine-readable code); docs/README are CC-BY-4.0
        if "/taxonomy/classes/" in p or p.endswith(("schema.md", "schema.yaml")):
            license_id = "MIT"
        else:
            license_id = "CC-BY-4.0"
    elif p.endswith((".jsonl", ".json", ".csv", ".parquet", ".npy", ".nwb")):
        license_id = "CC-BY-4.0"
    else:
        license_id = "CC-BY-4.0"

    # Schema cross-references
    schema_ref: Optional[str] = None
    if p.endswith(".jsonl"):
        if "taxonomy" in p:
            schema_ref = "README.md#5-schemas-taxonomy-jsonl"
        elif "results" in p or "layer3" in p or "layer4" in p or "b3" in p:
            schema_ref = "README.md#5-schemas-results-jsonl"
        elif "registry" in p or "null" in p:
            schema_ref = "README.md#5-schemas-nulls-jsonl"
        else:
            schema_ref = "README.md#5-schemas-jsonl"
    elif p.endswith(".csv"):
        schema_ref = "README.md#5-schemas-csv"
    elif p.endswith(".yaml") and "/taxonomy/" in p:
        schema_ref = "README.md#5-schemas-class-yaml"
    return license_id, schema_ref


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_files(root: Path):
    for base, dirs, files in os.walk(root):
        # in-place prune of excluded dirs
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        files = sorted(f for f in files if not f.startswith(EXCLUDE_FILE_PREFIXES))
        for fname in files:
            yield Path(base) / fname


def detect_git_commit(repo_root: Path) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return None


def main():
    manifest_path = BUNDLE / "MANIFEST.json"
    entries = []
    total_bytes = 0

    for fpath in iter_files(BUNDLE):
        rel = fpath.relative_to(BUNDLE).as_posix()
        # skip the manifest itself + this script's pycache
        if rel == "MANIFEST.json":
            continue
        size = fpath.stat().st_size
        digest = sha256_file(fpath)
        license_id, schema_ref = classify(rel)
        entries.append({
            "path": rel,
            "sha256": digest,
            "size_bytes": size,
            "license": license_id,
            "schema_ref": schema_ref,
        })
        total_bytes += size

    # Repo provenance
    repo_root = BUNDLE.parents[2]  # dataset/v1/<bundle> -> repo root
    git_commit = detect_git_commit(repo_root) or os.environ.get("GIT_COMMIT_SHA", "unknown")

    # Sort entries deterministically
    entries.sort(key=lambda e: e["path"])

    manifest = {
        "schema": "structural-isomorphism-zenodo-benchmark-v1",
        "version": "1.0.0",
        "title": "structural-isomorphism cross-domain SOC + universality benchmark",
        "release_date": "2026-05-15",
        "git_commit": git_commit,
        "license_data": "CC-BY-4.0",
        "license_code": "MIT",
        "doi_placeholder": "10.5281/zenodo.PLACEHOLDER",
        "files_count": len(entries),
        "size_bytes_total": total_bytes,
        "size_human": f"{total_bytes / 1024 / 1024:.2f} MB",
        "sha256_alg": "sha256",
        "files": entries,
    }
    # Compute aggregate sha256 over the file-entry blob (gives a single
    # "bundle hash" that downstream pins can lock against).
    blob = json.dumps([{"path": e["path"], "sha256": e["sha256"], "size_bytes": e["size_bytes"]}
                       for e in entries], sort_keys=True).encode()
    manifest["bundle_sha256"] = hashlib.sha256(blob).hexdigest()

    # Idempotent write — sort_keys + indent
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {manifest_path}")
    print(f"  files={len(entries)}  size={manifest['size_human']}")
    print(f"  bundle_sha256={manifest['bundle_sha256'][:16]}...")


if __name__ == "__main__":
    main()
