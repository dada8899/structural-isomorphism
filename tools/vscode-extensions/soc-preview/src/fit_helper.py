#!/usr/bin/env python3
"""Python helper: read a CSV, pick the first numeric column, fit Clauset 2009.

Usage:
    python3 fit_helper.py /path/to/file.csv

Emits a single JSON object to stdout:
    {"verdict": "PASS|FAIL|INCONCLUSIVE", "alpha": 2.51}
"""
from __future__ import annotations

import csv
import json
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"verdict": "ERROR", "alpha": 0.0, "error": "usage"}))
        return 2
    path = sys.argv[1]
    nums: list[float] = []
    try:
        with open(path) as f:
            reader = csv.reader(f)
            for row in reader:
                for cell in row:
                    try:
                        nums.append(float(cell))
                        break
                    except ValueError:
                        continue
    except Exception as exc:
        print(json.dumps({"verdict": "ERROR", "alpha": 0.0, "error": str(exc)}))
        return 1

    if len(nums) < 50:
        print(json.dumps({"verdict": "INCONCLUSIVE", "alpha": 0.0,
                          "error": f"too few rows: {len(nums)}"}))
        return 0

    try:
        import numpy as np
        from soc_pipeline import validate  # type: ignore
        arr = np.asarray(nums, dtype=float)
        arr = arr[np.isfinite(arr) & (arr > 0)]
        v = validate(arr, expected_band=None, n_boot=0)
        verdict = v.verdict if v.error is None else "ERROR"
        print(json.dumps({"verdict": verdict, "alpha": float(v.alpha or 0.0)}))
        return 0
    except Exception as exc:
        print(json.dumps({"verdict": "ERROR", "alpha": 0.0, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
