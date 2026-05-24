"""F3 (W7-D / W5-A §3.3) — Apply FWER correction to all per-system p-values.

Harvests the Vuong LR p-values from every per-system validation results JSON,
applies Bonferroni / Bonferroni-Holm / Benjamini-Hochberg corrections, and
writes:

  v4/results/F3_fwer_corrected.jsonl  — per-test corrected rows
  v4/results/F3_fwer_summary.json     — summary by alpha + which verdicts flip

Reference: scholar-review W5-A §3.3 ("Multiple comparisons / familywise error
rate is nowhere controlled. 13 systems x at least 2 LR tests each + 7-system
BIC + universal collapse + 4 nulls = at minimum 30 statistical decisions...
At nominal alpha=0.05 per test, an FWER above 0.5 is likely.").

Usage:
    PYTHONPATH=. python v4/scripts/F3_apply_fwer_correction.py
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

# Allow `v4.lib.multitest_correction` import without install
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v4.lib.multitest_correction import (  # noqa: E402
    benjamini_hochberg,
    bonferroni,
    bonferroni_holm,
)


VALIDATION = ROOT / "v4" / "validation"
RESULTS = ROOT / "v4" / "results"

# Per-system file map + path inside JSON to the powerlaw_fit dict
SYSTEMS = [
    ("earthquake", "soc-earthquake/gr_results.json", None),  # uses b-test, special
    ("stockmarket", "soc-stockmarket/gr_results.json", "clauset_fit"),
    ("defi_aave", "soc-defi/multiprotocol_results.json", "aave_v2.power_law"),
    ("defi_compound", "soc-defi/multiprotocol_results.json", "compound_v2.power_law"),
    ("defi_maker", "soc-defi/multiprotocol_results.json", "maker_dog.power_law"),
    ("wildfire", "soc-wildfire/wildfire_results.json", "powerlaw_fit"),
    ("solar", "soc-solar/solar_results.json", "powerlaw_fit_peak_flux"),
    ("bank_failure", "soc-bank-failures/bank_results.json", "powerlaw_fit_assets"),
    ("github_stars", "soc-github-stars/github_results.json", "powerlaw_fit"),
    ("wikipedia", "soc-wikipedia-views/wikipedia_results.json", "powerlaw_fit"),
    ("power_grid_mw", "soc-power-grid/power_grid_results.json", "mw_loss"),
    ("power_grid_cust", "soc-power-grid/power_grid_results.json", "customers_affected"),
]


def _safe_get(d: dict, *keys: str) -> object:
    """Nested dict get; returns None if any key missing."""
    cur: object = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
        if cur is None:
            return None
    return cur


def _coerce_p(v: object) -> float | None:
    """Pull a numeric p-value from possibly-nested fields. Some files use
    'compare_vs_lognormal_p', some use 'vs_lognormal_p', etc."""
    if v is None:
        return None
    try:
        f = float(v)
    except Exception:
        return None
    if not math.isfinite(f):
        return None
    return max(0.0, min(1.0, f))


def harvest_pvalues() -> list[dict]:
    """Return list of {system, test, p_value, alt_winner} rows."""
    out: list[dict] = []
    for name, relpath, key in SYSTEMS:
        path = VALIDATION / relpath
        if not path.exists():
            print(f"[skip] {name}: {path} missing")
            continue
        try:
            data = json.loads(path.read_text())
        except Exception as exc:
            print(f"[skip] {name}: parse error: {exc}")
            continue

        if key is not None:
            # Support dotted path (e.g., "aave_v2.power_law")
            cur: object = data
            for part in key.split("."):
                if not isinstance(cur, dict):
                    cur = None
                    break
                cur = cur.get(part)
                if cur is None:
                    break
            fit = cur
            # For mw_loss / customers_affected (power-grid), the LR-test
            # lives under e.g. data["mw_loss"]["fit"]
            if isinstance(fit, dict) and "fit" in fit:
                fit = fit["fit"]
        else:
            fit = data

        if not isinstance(fit, dict):
            print(f"[skip] {name}: no fit dict at key {key}")
            continue

        # Pull p-values; handle both "vs_lognormal_p" and "compare_vs_lognormal_p"
        ln_p = (
            fit.get("vs_lognormal_p")
            or fit.get("compare_vs_lognormal_p")
            or fit.get("lr_lognormal_p")
        )
        ln_R = (
            fit.get("vs_lognormal_R")
            or fit.get("compare_vs_lognormal_R")
            or fit.get("lr_lognormal_R")
        )
        exp_p = (
            fit.get("vs_exponential_p")
            or fit.get("compare_vs_exponential_p")
            or fit.get("lr_exponential_p")
        )
        exp_R = (
            fit.get("vs_exponential_R")
            or fit.get("compare_vs_exponential_R")
            or fit.get("lr_exponential_R")
        )

        # Verdict label
        winner = fit.get("vs_powerlaw_lognormal_winner") or fit.get("winner") or "n/a"
        alpha_hat = fit.get("alpha")
        n_tail = fit.get("n_tail")

        for test_name, p, R in (
            ("Vuong vs lognormal", _coerce_p(ln_p), ln_R),
            ("Vuong vs exponential", _coerce_p(exp_p), exp_R),
        ):
            if p is None:
                continue
            out.append(
                {
                    "system": name,
                    "test": test_name,
                    "p_value": p,
                    "lr_R": float(R) if R is not None else None,
                    "alpha_hat": (float(alpha_hat) if alpha_hat else None),
                    "n_tail": (int(n_tail) if n_tail else None),
                    "ln_vs_pl_winner": winner,
                    "source_file": relpath,
                }
            )

    # Earthquake: special-case GR fit uses b-value; the canonical test is
    # whether the global b ∈ literature band. There is no Vuong-LR p here.
    # We do include a synthetic "literature-band-consistency" entry:
    eq_file = VALIDATION / "soc-earthquake" / "gr_results.json"
    if eq_file.exists():
        try:
            d = json.loads(eq_file.read_text())
            b = d.get("b_value")
            if b is not None:
                # If b ∈ [0.9, 1.1] band, treat the within-band as
                # decisive evidence (p->0 for band-consistency); not a Vuong-LR.
                # We do NOT add this to the FWER family since it's not a hypothesis
                # test in the LR sense. Skip.
                pass
        except Exception:
            pass

    # Scheffer block-bootstrap (2 tests)
    sch_file = VALIDATION / "scheffer-lake" / "lake_results.json"
    if sch_file.exists():
        try:
            d = json.loads(sch_file.read_text())
            bb = d.get("block_bootstrap", {})
            for label, key in (
                ("Scheffer AR1 block-bootstrap", "p_block_bootstrap_ar1"),
                ("Scheffer Var block-bootstrap", "p_block_bootstrap_var"),
            ):
                p = _coerce_p(bb.get(key))
                if p is not None:
                    out.append(
                        {
                            "system": "scheffer_lake_fox_river",
                            "test": label,
                            "p_value": p,
                            "lr_R": None,
                            "alpha_hat": None,
                            "n_tail": bb.get("n_boot"),
                            "ln_vs_pl_winner": "n/a",
                            "source_file": "scheffer-lake/lake_results.json",
                        }
                    )
        except Exception as exc:
            print(f"[skip-scheffer] {exc}")

    return out


@dataclass
class FwerSummary:
    n_tests: int
    n_significant_raw: int
    n_significant_bonferroni: int
    n_significant_holm: int
    n_significant_bh: int


def main():
    print("[F3] harvesting p-values from per-system validation files...")
    rows = harvest_pvalues()
    print(f"[F3] {len(rows)} (system, test) p-value rows collected")

    pvalues = [r["p_value"] for r in rows]
    alpha = 0.05

    bonf = bonferroni(pvalues, alpha=alpha)
    holm = bonferroni_holm(pvalues, alpha=alpha)
    bh = benjamini_hochberg(pvalues, alpha=alpha)

    # Attach corrections to each row
    for i, r in enumerate(rows):
        r["p_bonferroni"] = bonf.p_adjusted[i]
        r["p_holm"] = holm.p_adjusted[i]
        r["p_bh"] = bh.p_adjusted[i]
        r["reject_raw"] = bool(r["p_value"] <= alpha)
        r["reject_bonferroni"] = bool(bonf.reject[i])
        r["reject_holm"] = bool(holm.reject[i])
        r["reject_bh"] = bool(bh.reject[i])
        # Did the verdict flip from raw to Holm?
        r["verdict_flip_raw_to_holm"] = r["reject_raw"] != r["reject_holm"]

    # Write JSONL
    out_jsonl = RESULTS / "F3_fwer_corrected.jsonl"
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"[F3] wrote {out_jsonl} ({len(rows)} rows)")

    # Summary
    summary = {
        "n_tests": len(rows),
        "alpha": alpha,
        "fwer_naive": 1.0 - (1.0 - alpha) ** len(rows),
        "n_significant_raw": sum(r["reject_raw"] for r in rows),
        "n_significant_bonferroni": sum(r["reject_bonferroni"] for r in rows),
        "n_significant_holm": sum(r["reject_holm"] for r in rows),
        "n_significant_bh": sum(r["reject_bh"] for r in rows),
        "verdict_flips_raw_to_holm": [
            {"system": r["system"], "test": r["test"], "p_raw": r["p_value"],
             "p_holm": r["p_holm"]}
            for r in rows if r["verdict_flip_raw_to_holm"]
        ],
        "n_verdict_flips_raw_to_holm": sum(
            r["verdict_flip_raw_to_holm"] for r in rows
        ),
    }
    out_summary = RESULTS / "F3_fwer_summary.json"
    out_summary.write_text(json.dumps(summary, indent=2))
    print(f"[F3] wrote {out_summary}")
    print("[F3] SUMMARY:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
