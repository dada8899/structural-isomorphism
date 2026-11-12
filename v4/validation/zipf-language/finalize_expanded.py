#!/usr/bin/env python3
"""Once the expanded fetchers (parquet and API) have all completed, this
script replaces the original wiki_<lang>.txt files with their expanded
counterparts (preserving the old as wiki_<lang>_original.txt).

Triggered manually after fetch_corpora_expanded.py + fetch_wiki_parquet.py.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

RAW = Path(__file__).resolve().parent / "raw"
LOG_PATH = Path(__file__).resolve().parent / "fetch_log_finalized.json"


def main() -> None:
    log = {"swapped": [], "skipped": [], "missing": []}
    for lang in ["en", "zh", "ar", "hi", "es"]:
        small = RAW / f"wiki_{lang}.txt"
        big   = RAW / f"wiki_{lang}_expanded.txt"
        backup = RAW / f"wiki_{lang}_original.txt"

        if not big.exists():
            log["missing"].append(lang)
            print(f"[{lang}] no expanded file at {big}; skip", file=sys.stderr)
            continue

        big_bytes = big.stat().st_size
        small_bytes = small.stat().st_size if small.exists() else 0

        if big_bytes < small_bytes:
            log["skipped"].append({"lang": lang, "reason": "expanded < original",
                                    "expanded_bytes": big_bytes,
                                    "original_bytes": small_bytes})
            print(f"[{lang}] expanded ({big_bytes}) < original ({small_bytes}); skip",
                  file=sys.stderr)
            continue

        if small.exists() and not backup.exists():
            shutil.copy(small, backup)
        shutil.copy(big, small)
        log["swapped"].append({"lang": lang, "expanded_bytes": big_bytes,
                                "original_bytes": small_bytes,
                                "backup": backup.name})
        print(f"[{lang}] swapped: {small_bytes} -> {big_bytes} bytes",
              file=sys.stderr)

    LOG_PATH.write_text(json.dumps(log, indent=2, ensure_ascii=False))
    print(f"\nLog: {LOG_PATH}")


if __name__ == "__main__":
    main()
