"""Helpers for sanity regression tests.

Importable via `from sanity_helpers import ...` because `conftest.py`
prepends the v4/tests dir to sys.path before test collection.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VALIDATION_DIR = REPO / "v4" / "validation"
RESULTS_DIR = REPO / "v4" / "results"


def load_json_or_skip(path: Path):
    """Return parsed JSON at `path`, or pytest.skip if missing/unparseable."""
    import pytest

    if not path.exists():
        pytest.skip(f"results file missing: {path}")
    try:
        with path.open() as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        pytest.skip(f"results file unparseable {path}: {exc}")


def robust_get(d: dict, keys, default=None):
    """Return d[k] for the first k in `keys` that exists at top level.

    Used to handle field-name drift across phase result schemas (e.g.,
    `alpha` vs `alpha_fit` vs `alpha_clauset`).
    """
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d:
            return d[k]
    return default


def deep_find_alpha(d):
    """Recursively search for the first `alpha` (or similar) key inside dict d.

    Returns float or None. Used when alpha is nested inside `powerlaw_fit`,
    `clauset_fit`, `size_fit`, etc.
    """
    if not isinstance(d, dict):
        return None
    for k in ("alpha", "alpha_fit", "alpha_clauset", "α"):
        if k in d and isinstance(d[k], (int, float)):
            return float(d[k])
    for v in d.values():
        if isinstance(v, dict):
            r = deep_find_alpha(v)
            if r is not None:
                return r
    return None
