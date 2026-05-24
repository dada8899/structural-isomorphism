#!/usr/bin/env python3
"""
build_bundle.py — copy paper.md + results.json per system slot.

Layout:
  dataset/v1/systems/<slot>/data -> symlink to v4/validation/<src>/
  dataset/v1/systems/<slot>/paper.md (copied)
  dataset/v1/systems/<slot>/results.json (copied/merged)

Run from dataset/v1/.
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # dataset/v1/
SYSTEMS = ROOT / "systems"
REPO_ROOT = ROOT.parent.parent  # repo root

# slot -> v4/validation/ subdir
SYSTEM_MAP = {
    "01_earthquake": "soc-earthquake",
    "02_stockmarket": "soc-stockmarket",
    "03_defi": "soc-defi",
    "04_neural": "soc-neural",
    "05_wildfire": "soc-wildfire",
    "06_solar": "soc-solar",
    "07_bank_failures": "soc-bank-failures",
    "08_github_stars": "soc-github-stars",
    "09_power_grid": "soc-power-grid",
    "10_wikipedia_views": "soc-wikipedia-views",
    "11_hawkes_omori": "soc-hawkes-omori",
    "12_scheffer_lake": "scheffer-lake",
    "13_hysteresis_traffic": "hysteresis-traffic",
    "14_sir_contagion": "sir-contagion",
    "15_tail_copula": "tail-copula",
    "universal_collapse": "soc-universal-collapse",
}

# Files inside each v4/validation/<src>/ that we treat as the canonical results bundle.
# We aggregate them into a single results.json per slot.
RESULT_FILE_CANDIDATES = [
    "results.json",
    "gr_results.json",
    "omori_results.json",
    "wildfire_results.json",
    "solar_results.json",
    "bank_results.json",
    "github_results.json",
    "power_grid_results.json",
    "wikipedia_results.json",
    "null_results.json",
    "lake_results.json",
    "traffic_results.json",
    "bf_1_fit.json",
    "bf_2_fit.json",
    "bf_4_fit.json",
    "bf_8_fit.json",
    "bf_16_fit.json",
]


def main():
    for slot, src in SYSTEM_MAP.items():
        slot_dir = SYSTEMS / slot
        src_dir = REPO_ROOT / "v4" / "validation" / src
        # paper.md
        paper_src = src_dir / "paper.md"
        if paper_src.exists():
            shutil.copy(paper_src, slot_dir / "paper.md")
        # results.json (aggregated)
        agg = {"slot": slot, "source_dir": str(src_dir.relative_to(REPO_ROOT))}
        any_results = False
        for cand in RESULT_FILE_CANDIDATES:
            f = src_dir / cand
            if f.exists():
                try:
                    with open(f) as fp:
                        agg[cand.replace(".json", "")] = json.load(fp)
                    any_results = True
                except Exception as e:
                    agg[cand.replace(".json", "")] = {"_error": str(e)}
        if any_results:
            with open(slot_dir / "results.json", "w") as fp:
                json.dump(agg, fp, indent=2)
        # Verdict copy if exists
        for verdict_name in [
            "VERDICT-2026-04-15.md",
            "VERDICT-2026-04-16.md",
            "VERDICT-2026-05-13.md",
        ]:
            v = src_dir / verdict_name
            if v.exists():
                shutil.copy(v, slot_dir / verdict_name)
                break

    print("Bundle systems populated.")


if __name__ == "__main__":
    main()
