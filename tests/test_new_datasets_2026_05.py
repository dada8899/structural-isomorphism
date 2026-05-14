"""Sanity-check the 2 new empirical datasets added in Wave 11-E.

Newly added (session #10):
    - v4/validation/soc-solar-wind/   (Phase 14: solar-wind speed bursts)
    - v4/validation/soc-github-resolution/  (Phase 15: GitHub issue resolution times)

The tests exercise:
1. JSONL file exists, parses, and has >= 100 records
2. Each record has the required schema
3. The frozen SOC pipeline can run to completion on the numeric tail
   (do NOT assert verdict — see CLAUDE.md "honest reporting")
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Make soc-pipeline importable
SRC = REPO_ROOT / "packages" / "soc-pipeline" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SOLAR_WIND = REPO_ROOT / "v4" / "validation" / "soc-solar-wind" / "solar_wind_bursts.jsonl"
GITHUB = REPO_ROOT / "v4" / "validation" / "soc-github-resolution" / "github_resolutions.jsonl"


# --- Solar wind ---


def test_solar_wind_file_exists() -> None:
    assert SOLAR_WIND.is_file(), f"missing {SOLAR_WIND}; run fetch_solar_wind.py first"


def test_solar_wind_jsonl_parses() -> None:
    rows = []
    with SOLAR_WIND.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    assert len(rows) >= 100, f"need >= 100 bursts; got {len(rows)}"


def test_solar_wind_schema() -> None:
    required = {
        "burst_id",
        "start_ts",
        "end_ts",
        "duration_s",
        "peak_speed_kms",
        "integrated_excess_kms_s",
    }
    with SOLAR_WIND.open() as fh:
        first = json.loads(next(line for line in fh if line.strip()))
    missing = required - set(first.keys())
    assert not missing, f"solar-wind record missing fields: {missing}"


def test_solar_wind_pipeline_runs() -> None:
    """Frozen SOC pipeline runs to completion. Do not assert verdict."""
    from soc_pipeline import validate

    sizes = []
    with SOLAR_WIND.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            v = r.get("integrated_excess_kms_s")
            if v and v > 0:
                sizes.append(v)
    assert len(sizes) >= 100
    v = validate(np.array(sizes), label="test_solar_wind", expected_band=(1.8, 2.4), n_boot=50)
    assert v.verdict in ("PASS", "FAIL", "INCONCLUSIVE"), (
        f"unexpected verdict: {v.verdict}"
    )
    assert v.alpha is not None and np.isfinite(v.alpha)


# --- GitHub resolution ---


def test_github_file_exists() -> None:
    assert GITHUB.is_file(), f"missing {GITHUB}; run fetch_github_resolutions.py first"


def test_github_jsonl_parses() -> None:
    rows = []
    with GITHUB.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    assert len(rows) >= 100, f"need >= 100 issues; got {len(rows)}"


def test_github_schema() -> None:
    required = {"repo", "issue_number", "created_at", "closed_at", "resolution_s"}
    with GITHUB.open() as fh:
        first = json.loads(next(line for line in fh if line.strip()))
    missing = required - set(first.keys())
    assert not missing, f"github record missing fields: {missing}"


def test_github_resolution_positive() -> None:
    """All durations must be strictly positive (closed_at > created_at)."""
    with GITHUB.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            v = r.get("resolution_s")
            assert v is not None and v > 0, (
                f"resolution_s must be positive; got {v} for issue {r.get('issue_number')}"
            )


def test_github_pipeline_runs() -> None:
    """Frozen SOC pipeline runs to completion. Do not assert verdict."""
    from soc_pipeline import validate

    durations = []
    with GITHUB.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            v = r.get("resolution_s")
            if v and v > 0:
                durations.append(v)
    assert len(durations) >= 100
    v = validate(
        np.array(durations),
        label="test_github_resolution",
        expected_band=(1.5, 3.0),
        n_boot=50,
    )
    assert v.verdict in ("PASS", "FAIL", "INCONCLUSIVE")
    assert v.alpha is not None and np.isfinite(v.alpha)
