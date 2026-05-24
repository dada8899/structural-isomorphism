#!/usr/bin/env python3
"""
compute_manifest.py — Compute manifest.json for dataset/v1.

Walks all files (resolving symlinks), records: relative path, byte size, sha256.
Aggregates totals into manifest top-level fields.

Run from repo root or from dataset/v1/.
Output: dataset/v1/manifest.json
"""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # dataset/v1/
REPO_ROOT = ROOT.parent.parent
MANIFEST_PATH = ROOT / "manifest.json"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def walk_dataset():
    """Yield (relative_path_str, resolved_real_path, size, sha) for every file under ROOT.

    Symlinks are followed. The relative_path is keyed off ROOT (dataset/v1/...).
    We intentionally skip directories themselves.
    """
    for dirpath, dirnames, filenames in os.walk(ROOT, followlinks=True):
        # Skip ourselves writing manifest.json mid-walk
        for fn in filenames:
            full = Path(dirpath) / fn
            try:
                # Resolve to real file (follow symlinks)
                real = full.resolve(strict=True)
            except (FileNotFoundError, OSError):
                continue
            try:
                size = real.stat().st_size
            except OSError:
                continue
            rel = full.relative_to(ROOT).as_posix()
            yield rel, real, size


def main():
    files = []
    total_size = 0
    # First pass — list all files w/ size only (sha256 only on smaller files to keep manifest small)
    SHA_MAX_BYTES = 50 * 1024 * 1024  # 50 MB cap on sha256 for huge data files
    for rel, real, size in walk_dataset():
        if rel == "manifest.json":
            continue
        entry = {
            "path": rel,
            "size_bytes": size,
            "is_symlink": (ROOT / rel).is_symlink(),
        }
        if size <= SHA_MAX_BYTES:
            entry["sha256"] = sha256_file(real)
        else:
            entry["sha256"] = None
            entry["sha256_skipped_reason"] = f"file > {SHA_MAX_BYTES} bytes"
        files.append(entry)
        total_size += size

    files.sort(key=lambda x: x["path"])

    # Counts
    systems_count = len([f for f in files if f["path"].startswith("systems/")
                         and f["path"].count("/") == 1 + 1  # systems/<slot>/<file>
                         and f["path"].endswith("paper.md")])
    null_count = sum(1 for slot in ["gaussian", "exponential", "poisson", "poisson_omori"]
                     if (ROOT / "null_controls" / slot / "results.json").exists())
    taxonomy_classes_count = sum(1 for _ in (ROOT / "taxonomy" / "classes").iterdir()
                                  if _.suffix in (".yaml", ".yml"))
    tests_count = sum(1 for p in (ROOT / "tests" / "sanity").rglob("test_*.py"))

    manifest = {
        "schema": "structural-isomorphism-dataset-v1",
        "version": "1.0.0",
        "title": "Cross-domain SOC validation dataset",
        "doi_placeholder": "10.5281/zenodo.XXXXXXX",
        "release_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "license_data": "CC-BY-4.0",
        "license_code": "MIT",
        "git_commit": "607906c",  # main HEAD when bundle assembled (W8-A)
        "systems_count": systems_count,
        "null_controls_count": null_count,
        "taxonomy_classes_count": taxonomy_classes_count,
        "tests_count": tests_count,
        "files_count": len(files),
        "size_bytes_total": total_size,
        "size_human": f"{total_size / 1024 / 1024:.2f} MB",
        "sha256_alg": "sha256",
        "files": files,
    }

    with open(MANIFEST_PATH, "w") as fp:
        json.dump(manifest, fp, indent=2)
    # Console summary
    print(f"manifest written: {MANIFEST_PATH}")
    print(f"  systems_count          = {manifest['systems_count']}")
    print(f"  null_controls_count    = {manifest['null_controls_count']}")
    print(f"  taxonomy_classes_count = {manifest['taxonomy_classes_count']}")
    print(f"  tests_count            = {manifest['tests_count']}")
    print(f"  files_count            = {manifest['files_count']}")
    print(f"  size_bytes_total       = {manifest['size_bytes_total']} ({manifest['size_human']})")


if __name__ == "__main__":
    main()
