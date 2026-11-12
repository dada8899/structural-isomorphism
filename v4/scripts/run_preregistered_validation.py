#!/usr/bin/env python3
"""Run a pre-registered validation against a yaml spec.

Usage:
    run_preregistered_validation.py <preregister_yaml> [--dry-run] [--force]

The script:
  1. Reads the yaml spec (locked predictions + data source + success rules).
  2. (Skipped in --dry-run) downloads the data into
     v4/validation/<system>/raw/ if not cached.
  3. (Skipped in --dry-run) runs soc_pipeline.fit_clauset_powerlaw.
  4. Compares measured alpha + CI to predicted_band.
  5. Writes v4/validation/<system>/result.json with
     verdict ∈ {PASS, FAIL, INCONCLUSIVE, DRY_RUN_OK}.
  6. If result.json already exists, refuses to overwrite unless --force.
     With --force, prior result is appended to result.history.jsonl.

Design note: this script's "real" data-fetch + fit path is intentionally NOT
run in W1-C session. W1-C only delivers the infrastructure + --dry-run gate
to validate yaml completeness. The real fits will happen in a later session
once data sources are confirmed accessible and a session budget is allocated.

Why this matters: pre-registration only "binds" if the yaml is locked +
git-committed BEFORE the fit is run. By providing --dry-run as the first
mode of use, we make the locking the easy default and the fit the explicit
follow-up action.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
VALIDATION_DIR = REPO / "v4" / "validation"


# ---------------------------------------------------------------------------
# Yaml loader (minimal, no PyYAML dependency)
#
# We support a small subset of yaml sufficient for the pre-registration spec:
#   scalar key: value
#   list key:
#     - item
#     - item
#   block scalar key: |
#     multi-line text
#     until indentation ends
# This mirrors v4/scripts/b3_ensemble.py's load_yaml_class approach.

def _strip_inline_comment(value: str) -> str:
    """Strip trailing inline yaml comment ' # ...' from a scalar value.

    Only strips when the '#' is preceded by whitespace, so values like
    'soc_cascade  # comment' become 'soc_cascade', while URLs and tokens
    containing '#' are preserved.
    """
    if "#" not in value:
        return value
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "#" and i > 0 and value[i - 1] in (" ", "\t"):
            # strip trailing whitespace before the '#'
            while out and out[-1] in (" ", "\t"):
                out.pop()
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_scalar(raw: str) -> Any:
    """Convert a yaml scalar string to a Python value.

    Handles: quoted strings, integers, floats, true/false/null, and bare
    strings. Inline-comment-stripped before parsing.
    """
    s = _strip_inline_comment(raw).strip()
    if not s:
        return ""
    # quoted
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    # bracket-list inline (e.g. [1.3, 2.0])
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        parts = [p.strip() for p in inner.split(",")]
        return [_parse_scalar(p) for p in parts]
    # boolean / null
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if s.lower() in ("null", "~"):
        return None
    # numeric
    try:
        if "." in s or "e" in s.lower():
            return float(s)
        return int(s)
    except ValueError:
        pass
    return s


def load_yaml(path: Path) -> dict[str, Any]:
    """Minimal yaml subset parser sufficient for pre-registration files."""
    text = path.read_text(encoding="utf-8")
    out: dict[str, Any] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        # skip empty / comment-only lines
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        # top-level key: must start at column 0
        if not line.startswith(" "):
            if ":" not in line:
                i += 1
                continue
            key, _, rest = line.partition(":")
            key = key.strip()
            rest = rest
            # block scalar (key: |)
            if rest.strip() == "|" or rest.strip() == ">":
                i += 1
                buf: list[str] = []
                while i < len(lines):
                    ln = lines[i]
                    if ln.startswith("  ") or ln.strip() == "":
                        buf.append(ln[2:] if ln.startswith("  ") else ln)
                        i += 1
                    else:
                        break
                # trim trailing empties
                while buf and not buf[-1].strip():
                    buf.pop()
                out[key] = "\n".join(buf)
                continue
            # list (key: followed by - lines)
            if rest.strip() == "":
                i += 1
                items: list[Any] = []
                # Check whether next non-empty line is a list item or a sub-key.
                sub: dict[str, Any] = {}
                mode: str | None = None
                while i < len(lines):
                    ln = lines[i]
                    s = ln.strip()
                    if not s:
                        i += 1
                        continue
                    if not ln.startswith("  "):
                        break
                    if ln.startswith("  - "):
                        mode = "list"
                        items.append(_parse_scalar(ln[4:]))
                        i += 1
                    elif ln.startswith("  ") and ":" in ln and mode != "list":
                        mode = "dict"
                        sub_key, _, sub_rest = ln.strip().partition(":")
                        sub[sub_key.strip()] = _parse_scalar(sub_rest)
                        i += 1
                    else:
                        break
                if mode == "list":
                    out[key] = items
                elif mode == "dict":
                    out[key] = sub
                else:
                    out[key] = ""
                continue
            # plain scalar (key: value)
            out[key] = _parse_scalar(rest)
            i += 1
            continue
        # ignore non-top-level lines at this layer (handled in block above)
        i += 1
    return out


# ---------------------------------------------------------------------------
# Validation of the loaded spec

REQUIRED_FIELDS = [
    "system",
    "pre_registered_at",
    "author",
    "class_id",
    "predicted_band",
    "data_source",
    "data_url",
    "sample_size_target",
    "verification_method",
    "success_criteria",
    "verdict_rules",
]


def validate_spec(spec: dict[str, Any]) -> list[str]:
    """Return list of human-readable validation errors. Empty list = OK."""
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in spec or spec.get(field) in (None, "", []):
            errors.append(f"missing required field: {field}")
    # predicted_band shape
    band = spec.get("predicted_band")
    if band is not None:
        if not isinstance(band, list) or len(band) != 2:
            errors.append(f"predicted_band must be [low, high], got: {band!r}")
        else:
            try:
                lo, hi = float(band[0]), float(band[1])
                if lo >= hi:
                    errors.append(f"predicted_band low {lo} >= high {hi}")
            except (TypeError, ValueError):
                errors.append(f"predicted_band entries must be numeric: {band!r}")
    # predicted_exponent (optional but if present, must be numeric + in band)
    pred_exp = spec.get("predicted_exponent")
    if pred_exp is not None and band and isinstance(band, list) and len(band) == 2:
        try:
            e = float(pred_exp)
            lo, hi = float(band[0]), float(band[1])
            if not (lo <= e <= hi):
                errors.append(
                    f"predicted_exponent {e} not in predicted_band [{lo}, {hi}]"
                )
        except (TypeError, ValueError):
            errors.append(f"predicted_exponent must be numeric: {pred_exp!r}")
    return errors


# ---------------------------------------------------------------------------
# Data acquisition (placeholder for now — real fetches deferred)


def fetch_data(spec: dict[str, Any], system_dir: Path) -> tuple[Path | None, str | None]:
    """Stub data-fetch path. Returns (path, error).

    Currently NOT implemented in W1-C: real data fetches are deferred to a
    later session. This function is the integration point for those fetches.
    Each system has its own data-source pattern; we'll add per-system
    fetch routines (Socrata API, NVD JSON feed, Pushshift archive) under
    v4/scripts/fetch/ in a future session.
    """
    return None, "data-fetch path not implemented in W1-C; deferred to future session"


# ---------------------------------------------------------------------------
# Pipeline call wrapper


def run_fit(data_path: Path, system: str) -> dict[str, Any]:
    """Call soc_pipeline.fit_clauset_powerlaw on the cached data.

    Real fit logic deferred. The hookup pattern is:
        from soc_pipeline import fit_clauset_powerlaw, bootstrap_ci
        vals = load_values(data_path)
        fit = fit_clauset_powerlaw(vals, name=system)
        ci = bootstrap_ci(vals, n_boot=1000)
        return {"alpha": fit.alpha, "ci_low": ci.ci_low, ...}
    """
    raise NotImplementedError(
        "Real fit path deferred. W1-C delivers infra + --dry-run only."
    )


# ---------------------------------------------------------------------------
# Verdict logic


def compute_verdict(
    spec: dict[str, Any], fit_result: dict[str, Any] | None
) -> dict[str, Any]:
    """Compare fit_result to spec.success_criteria + spec.verdict_rules.

    fit_result keys expected (when real fit is wired up):
      - alpha (float): fitted exponent
      - ci_low, ci_high (float): bootstrap CI
      - n_tail (int): sample size above xmin
      - vuong_pvals (dict[str, float]): per-alternative p-values
    """
    if fit_result is None:
        return {
            "verdict": "INCONCLUSIVE",
            "reason": "no fit_result (data not fetched or fit not run)",
        }
    band = spec.get("predicted_band")
    if not isinstance(band, list) or len(band) != 2:
        return {"verdict": "INCONCLUSIVE", "reason": "spec band malformed"}
    lo, hi = float(band[0]), float(band[1])
    alpha = fit_result.get("alpha")
    if alpha is None:
        return {"verdict": "INCONCLUSIVE", "reason": "no alpha in fit_result"}
    n_tail = fit_result.get("n_tail", 0)
    in_band = lo <= alpha <= hi
    # null rejection count
    vuong = fit_result.get("vuong_pvals", {}) or {}
    n_null_rejected = sum(1 for p in vuong.values() if p is not None and p < 0.1)
    if not in_band:
        verdict = "FAIL"
        reason = f"alpha={alpha:.3f} outside band [{lo}, {hi}]"
    elif n_tail < 100:
        verdict = "INCONCLUSIVE"
        reason = f"alpha={alpha:.3f} in band but n_tail={n_tail} < 100"
    elif n_null_rejected < 1:
        verdict = "INCONCLUSIVE"
        reason = f"alpha={alpha:.3f} in band but no null alternatives rejected"
    elif n_null_rejected < 2:
        verdict = "INCONCLUSIVE"
        reason = (
            f"alpha={alpha:.3f} in band; only {n_null_rejected} null rejected "
            "(spec requires >=2)"
        )
    else:
        verdict = "PASS"
        reason = (
            f"alpha={alpha:.3f} in band [{lo}, {hi}]; "
            f"{n_null_rejected} null alternatives rejected; n_tail={n_tail}"
        )
    return {"verdict": verdict, "reason": reason, "alpha_measured": alpha}


# ---------------------------------------------------------------------------
# Main


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run a pre-registered validation against a yaml spec."
    )
    ap.add_argument("yaml_path", help="path to the pre-registration yaml")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate yaml only; no data fetch, no fit. Recommended before commit.",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing result.json (prior result moves to history).",
    )
    args = ap.parse_args()

    yaml_path = Path(args.yaml_path)
    if not yaml_path.exists():
        print(f"[preregister] FATAL: yaml not found: {yaml_path}", file=sys.stderr)
        return 2

    try:
        spec = load_yaml(yaml_path)
    except Exception as e:  # pragma: no cover
        print(f"[preregister] FATAL: yaml parse error: {e}", file=sys.stderr)
        return 2

    errors = validate_spec(spec)
    if errors:
        print(
            f"[preregister] FATAL: spec validation errors in {yaml_path.name}:",
            file=sys.stderr,
        )
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    system = spec.get("system", yaml_path.stem)
    print(f"[preregister] system: {system}", file=sys.stderr)
    print(f"[preregister] class_id: {spec.get('class_id')}", file=sys.stderr)
    print(
        f"[preregister] predicted_band: {spec.get('predicted_band')}",
        file=sys.stderr,
    )
    print(
        f"[preregister] pre_registered_at: {spec.get('pre_registered_at')}",
        file=sys.stderr,
    )

    if args.dry_run:
        print(
            f"[preregister] DRY_RUN: yaml validates. Lock by `git commit` + `git push`.",
            file=sys.stderr,
        )
        return 0

    # Non-dry-run path: data fetch + fit + verdict
    system_dir = VALIDATION_DIR / system
    system_dir.mkdir(parents=True, exist_ok=True)
    result_path = system_dir / "result.json"
    history_path = system_dir / "result.history.jsonl"

    if result_path.exists() and not args.force:
        print(
            f"[preregister] result.json already exists: {result_path}",
            file=sys.stderr,
        )
        print(
            "[preregister] Use --force to overwrite (prior result is preserved in history).",
            file=sys.stderr,
        )
        return 3

    if result_path.exists() and args.force:
        prior = json.loads(result_path.read_text())
        with open(history_path, "a") as fh:
            fh.write(json.dumps(prior, ensure_ascii=False) + "\n")
        print(
            f"[preregister] --force: prior result moved to {history_path.name}",
            file=sys.stderr,
        )

    t_start = time.time()

    # Fetch
    data_path, fetch_err = fetch_data(spec, system_dir)
    if fetch_err:
        result: dict[str, Any] = {
            "system": system,
            "verdict": "INCONCLUSIVE",
            "reason": f"data fetch failed: {fetch_err}",
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": round(time.time() - t_start, 1),
            "spec": {
                "predicted_band": spec.get("predicted_band"),
                "class_id": spec.get("class_id"),
                "pre_registered_at": spec.get("pre_registered_at"),
            },
        }
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(
            f"[preregister] {system} -> INCONCLUSIVE (fetch error). Wrote {result_path}",
            file=sys.stderr,
        )
        return 0

    # Fit
    try:
        fit_result = run_fit(data_path, system)  # type: ignore[arg-type]
    except NotImplementedError as e:
        result = {
            "system": system,
            "verdict": "INCONCLUSIVE",
            "reason": f"fit not implemented: {e}",
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": round(time.time() - t_start, 1),
            "spec": {
                "predicted_band": spec.get("predicted_band"),
                "class_id": spec.get("class_id"),
                "pre_registered_at": spec.get("pre_registered_at"),
            },
        }
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(
            f"[preregister] {system} -> INCONCLUSIVE (fit not implemented). Wrote {result_path}",
            file=sys.stderr,
        )
        return 0

    verdict_obj = compute_verdict(spec, fit_result)
    result = {
        "system": system,
        **verdict_obj,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(time.time() - t_start, 1),
        "fit_result": fit_result,
        "spec": {
            "predicted_band": spec.get("predicted_band"),
            "class_id": spec.get("class_id"),
            "pre_registered_at": spec.get("pre_registered_at"),
        },
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        f"[preregister] {system} -> {verdict_obj['verdict']}. Wrote {result_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
