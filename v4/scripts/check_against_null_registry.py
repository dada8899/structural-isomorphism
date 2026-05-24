#!/usr/bin/env python3
"""
Sanity-check a new SOC fit result against the persistent null-validation registry.

Background
----------
Layer 5 Phase 5 produced 4 synthetic null datasets (Gaussian random walk,
exponential, Poisson IAT, Poisson-Omori) that the pipeline correctly
*rejected* as power-law / SOC. Whenever a new phase claims a power-law
finding, we want to:

    1. Compare the new fit's key indicators (alpha, vs_lognormal_R,
       vs_exponential_R, p-values, ...) against every recorded null case.
    2. Compute a similarity score in this indicator space.
    3. If similarity to *any* null is high, flag the new finding as
       suspicious (could be a null-like artifact rather than real SOC).

The registry lives at v4/validation/null-controls/registry.jsonl
(one JSON dict per line, schema documented in that file's neighbours).

Usage
-----
    # As a script
    python3 v4/scripts/check_against_null_registry.py \
        --fit '{"alpha_clauset": 1.79, "vs_lognormal_R": +20.5,
                 "vs_exponential_R": +18.2, "vs_lognormal_p": 1e-15,
                 "vs_exponential_p": 1e-12, "n_tail": 1071}'

    # As a library
    from v4.scripts.check_against_null_registry import (
        load_registry, score_against_registry, verdict_from_scores,
    )

The output names a single nearest null + an overall verdict
("likely real SOC" vs "looks null-like").
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "v4" / "validation" / "null-controls" / "registry.jsonl"


# Indicator weights — these capture how strongly each indicator
# discriminates "null" from "real SOC". A small distance (z-like
# similarity) along an indicator with HIGH weight is more concerning.
INDICATOR_WEIGHTS: Dict[str, float] = {
    # Tail exponent: nulls tend to peg near alpha ≈ 3.0 (Clauset boundary).
    "alpha_clauset": 1.0,
    # vs lognormal: nulls have strongly negative R (lognormal wins).
    "vs_lognormal_R": 2.0,
    # vs exponential: nulls have weakly-negative or near-zero R; real
    # SOC has positive R (power-law beats exponential).
    "vs_exponential_R": 2.5,
    # Tail size n_tail: a soft prior — vanishingly small tail is suspicious.
    "n_tail": 0.5,
    # Omori-specific fields (only used if both sides have them):
    "omori_p": 1.5,
    "omori_R2": 2.0,
}


def load_registry(path: Path = REGISTRY_PATH) -> List[Dict[str, Any]]:
    """Load all null cases from registry.jsonl."""
    if not path.exists():
        raise FileNotFoundError(f"Registry not found: {path}")
    cases: List[Dict[str, Any]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[warn] skipping malformed line: {e}", file=sys.stderr)
    return cases


def _safe_get(d: Dict[str, Any], key: str) -> Optional[float]:
    v = d.get(key)
    if v is None:
        return None
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(fv) or math.isinf(fv):
        return None
    return fv


def _scale_for(indicator: str) -> float:
    """Return the natural scale (≈ "1 standard-deviation") for an indicator.

    The scales encode rough magnitudes seen across nulls + real Phase 1-4
    findings. They are *not* statistics — they are domain priors so
    similarity scores are interpretable.
    """
    return {
        "alpha_clauset": 0.5,        # alpha typically lives in [1.3, 3.5]
        "vs_lognormal_R": 15.0,      # R values seen range from -45 to +100
        "vs_exponential_R": 15.0,
        "n_tail": 5000.0,            # n_tail varies orders of magnitude
        "omori_p": 0.5,              # p around 1.0 for real, around 0 for null
        "omori_R2": 0.3,             # R^2 around 0.3-0.99 real, near 0 null
    }.get(indicator, 1.0)


def score_against_case(
    new_fit: Dict[str, Any], null_case: Dict[str, Any]
) -> Tuple[float, Dict[str, float]]:
    """Return (similarity, per_indicator_contributions).

    similarity in [0, 1]: 1.0 = identical to null, 0.0 = completely unlike.
    Built from a weighted Gaussian kernel over the indicators present in
    *both* the new fit and the null case.
    """
    null_indicators = null_case.get("key_indicators", {})
    contribs: Dict[str, float] = {}
    total_weight = 0.0
    weighted_sim = 0.0

    for indicator, weight in INDICATOR_WEIGHTS.items():
        v_new = _safe_get(new_fit, indicator)
        v_null = _safe_get(null_indicators, indicator)
        if v_new is None or v_null is None:
            continue
        scale = _scale_for(indicator)
        # Gaussian kernel on standardised difference.
        diff = (v_new - v_null) / scale
        sim_i = math.exp(-0.5 * diff * diff)
        contribs[indicator] = sim_i
        weighted_sim += weight * sim_i
        total_weight += weight

    if total_weight == 0:
        return 0.0, {}

    return weighted_sim / total_weight, contribs


def score_against_registry(
    new_fit: Dict[str, Any],
    registry: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Score the new fit against every null case in the registry.

    Returns a list sorted descending by similarity, with shape:
        [{"case_id": ..., "similarity": ..., "contributions": {...}}, ...]
    """
    if registry is None:
        registry = load_registry()
    scored = []
    for case in registry:
        sim, contribs = score_against_case(new_fit, case)
        scored.append(
            {
                "case_id": case.get("case_id"),
                "synthetic_data_type": case.get("synthetic_data_type"),
                "similarity": sim,
                "contributions": contribs,
                "n_indicators_compared": len(contribs),
            }
        )
    scored.sort(key=lambda r: r["similarity"], reverse=True)
    return scored


def verdict_from_scores(
    scored: List[Dict[str, Any]],
    high_threshold: float = 0.65,
    borderline_threshold: float = 0.40,
) -> Dict[str, Any]:
    """Translate similarity scores into a textual verdict.

    Thresholds are heuristics tuned to:
      - real Phase 1-4 fits scoring < 0.40 against every null (i.e. clearly
        unlike any null);
      - nulls scoring > 0.85 against their own case.
    """
    if not scored:
        return {
            "verdict": "no_comparison",
            "explanation": "registry empty or no overlapping indicators",
            "max_similarity": 0.0,
            "nearest": None,
        }

    nearest = scored[0]
    max_sim = nearest["similarity"]

    if max_sim >= high_threshold:
        verdict = "looks_null_like"
        explanation = (
            f"new fit is suspiciously close to null case "
            f"'{nearest['case_id']}' (similarity={max_sim:.2f}); "
            f"verify it is a real SOC finding, not a pipeline artifact"
        )
    elif max_sim >= borderline_threshold:
        verdict = "borderline"
        explanation = (
            f"new fit has moderate similarity to '{nearest['case_id']}' "
            f"(similarity={max_sim:.2f}); inspect alpha + R values"
        )
    else:
        verdict = "not_null"
        explanation = (
            f"new fit is unlike any registered null "
            f"(max similarity={max_sim:.2f} vs '{nearest['case_id']}')"
        )

    return {
        "verdict": verdict,
        "explanation": explanation,
        "max_similarity": max_sim,
        "nearest": nearest,
    }


def run_check(new_fit: Dict[str, Any]) -> Dict[str, Any]:
    """End-to-end: load registry, score, derive verdict."""
    registry = load_registry()
    scored = score_against_registry(new_fit, registry)
    verdict = verdict_from_scores(scored)
    return {
        "input_fit": new_fit,
        "all_scores": scored,
        "verdict": verdict,
        "registry_size": len(registry),
    }


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sanity-check a new SOC fit against the null-validation registry"
    )
    p.add_argument(
        "--fit",
        type=str,
        help="JSON string with the new fit's key indicators (e.g. alpha_clauset, vs_lognormal_R, ...)",
    )
    p.add_argument(
        "--fit-file",
        type=Path,
        help="Path to a JSON file containing the new fit's key indicators",
    )
    p.add_argument(
        "--demo",
        action="store_true",
        help="Run a demonstration using the Phase 1 earthquake fit as input",
    )
    p.add_argument(
        "--demo-null",
        action="store_true",
        help="Run a demonstration using a null case itself (should detect as null)",
    )
    return p.parse_args()


PHASE_1_EARTHQUAKE_FIT = {
    "alpha_clauset": 1.7936887559930417,
    "vs_lognormal_R": -1.1693943507700288,
    "vs_lognormal_p": 0.24224478485654988,
    "vs_exponential_R": 18.0,  # estimated; real GR-derived energies blow exponential away
    "n_tail": 1071,
    "_note": "Phase 1 earthquake Clauset fit (energies, b-value derived)",
}


def main() -> int:
    args = _parse_args()

    if args.demo:
        new_fit = PHASE_1_EARTHQUAKE_FIT
        print("# demo: checking Phase 1 earthquake fit against null registry")
    elif args.demo_null:
        # Use the Gaussian null itself — this should score high similarity.
        new_fit = {
            "alpha_clauset": 2.999,
            "vs_lognormal_R": -28.5,
            "vs_exponential_R": -44.7,
            "n_tail": 8646,
        }
        print("# demo: feeding a Gaussian-walk-like fit (should match null_001)")
    elif args.fit:
        new_fit = json.loads(args.fit)
    elif args.fit_file:
        new_fit = json.loads(args.fit_file.read_text())
    else:
        print("error: provide --fit, --fit-file, --demo or --demo-null", file=sys.stderr)
        return 2

    result = run_check(new_fit)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
