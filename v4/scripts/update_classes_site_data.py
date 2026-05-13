#!/usr/bin/env python3
"""Update web/frontend/assets/data/universality-classes.json with Phase 6/8/10/11 verified results.

Adds new predictions (status=verified) to:
  - soc_threshold_cascade: + wildfire, solar, bank-failures (3 new)
  - preferential_attachment: + github-stars (1 new)

Also copies paper.md from each verified phase into web/frontend/assets/data/papers/<slug>.md.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SITE_JSON = REPO / "web" / "frontend" / "assets" / "data" / "universality-classes.json"
PAPER_OUT = REPO / "web" / "frontend" / "assets" / "data" / "papers"
PAPER_OUT.mkdir(parents=True, exist_ok=True)


NEW_PREDICTIONS = {
    "soc_threshold_cascade": [
        {
            "target": "NIFC Interagency 美国野火事件 (21,022 fires, 2010s-2024)",
            "target_en": "NIFC Interagency US wildfire catalog (21,022 fires, 2010s-2024)",
            "prediction": "Clauset α(acres) = 1.660 ± 0.017，bootstrap 95% CI [1.381, 1.808]，落在 Drossel-Schwabl band [1.3, 2.5]",
            "prediction_en": "Clauset α(acres) = 1.660 ± 0.017, bootstrap 95% CI [1.381, 1.808], inside Drossel-Schwabl band [1.3, 2.5]",
            "test_method": "Clauset MLE + bootstrap n=100 + Omori on inter-fire times after 95th-pctl mainshocks + matched-n null control",
            "data_source": "NIFC Interagency Fire Perimeter History (opendata.arcgis.com)",
            "data_source_en": "NIFC Interagency Fire Perimeter History (opendata.arcgis.com)",
            "sample_size": "21,022 fires / 1,591 tail events above xmin=1,199 acres",
            "paper_target": "Layer 5 Phase 10 — wildfire SOC validation",
            "paper_target_en": "Layer 5 Phase 10 — wildfire SOC validation",
            "status": "✅ 已验证 (2026-05-13)",
            "status_en": "✅ Verified (2026-05-13)",
            "rationale": "经典 SOC 系统 (Drossel-Schwabl 1992 / Malamud 1998 PNAS). α 落在预测带，但 lognormal 也合理 (R=-4.73 caveat)。Omori p=0.24 反映季节强迫而非应力释放。",
            "rationale_en": "Classic SOC system (Drossel-Schwabl 1992 / Malamud 1998 PNAS). α inside predicted band but lognormal alternative also fits (R=-4.73 caveat). Shallow Omori p=0.24 reflects seasonal forcing rather than stress relaxation.",
            "paper_url": "/paper/soc-wildfire-2026-05-13",
            "paper_title": "Wildfire size distribution exhibits SOC: cross-validation of pipeline on Drossel-Schwabl class",
        },
        {
            "target": "NOAA GOES X 射线太阳耀斑目录 2000-2016 (29,907 events)",
            "target_en": "NOAA GOES X-ray solar flare catalog 2000-2016 (29,907 events)",
            "prediction": "Clauset α(peak flux) = 2.194 ± 0.018, bootstrap 95% CI [2.159, 2.248], 落在 Lu-Hamilton 1991 band [1.5, 2.5]; vs lognormal inconclusive (R=+0.44)",
            "prediction_en": "Clauset α(peak flux) = 2.194 ± 0.018, bootstrap 95% CI [2.159, 2.248], inside Lu-Hamilton 1991 band [1.5, 2.5]; vs lognormal inconclusive (R=+0.44)",
            "test_method": "Clauset MLE + bootstrap n=100 + IAT power-law + Omori on X-class flare windows + matched-n null",
            "data_source": "NOAA NGDC GOES-XRS report archive 2000-2016",
            "data_source_en": "NOAA NGDC GOES-XRS report archive 2000-2016",
            "sample_size": "29,907 unique flares / 4,336 tail events above xmin=5.2e-6 W/m² (~M0.5)",
            "paper_target": "Layer 5 Phase 11 — solar flare SOC validation",
            "paper_target_en": "Layer 5 Phase 11 — solar flare SOC validation",
            "status": "✅ 已验证 (2026-05-13)",
            "status_en": "✅ Verified (2026-05-13)",
            "rationale": "Lu-Hamilton 1991 经典 SOC 系统。本队列中最干净的 SOC 确认——lognormal 没击败。Omori p≈0 (state-dependent Poisson / Wheatland 2000)，size 信号和时间信号在 solar flare 上解耦。",
            "rationale_en": "Lu-Hamilton 1991 canonical SOC system. Cleanest SOC confirmation in the cohort — lognormal cannot be ruled out but is not preferred. Omori p≈0 (state-dependent Poisson / Wheatland 2000), size and temporal signatures decouple.",
            "paper_url": "/paper/soc-solar-2026-05-13",
            "paper_title": "Solar X-ray flares revisited: independent SOC validation via Layer-5 pipeline",
        },
        {
            "target": "FDIC 美国银行倒闭事件 1934-2026 (3,960 failures)",
            "target_en": "FDIC US bank failures 1934-2026 (3,960 failures)",
            "prediction": "Clauset α(assets) = 1.899 ± 0.045, bootstrap 95% CI [1.763, 2.047], 落在 Diamond-Dybvig / Eisenberg-Noe band [1.4, 2.5]",
            "prediction_en": "Clauset α(assets) = 1.899 ± 0.045, bootstrap 95% CI [1.763, 2.047], inside Diamond-Dybvig / Eisenberg-Noe band [1.4, 2.5]",
            "test_method": "Clauset MLE + bootstrap n=100 + era-split (pre-crisis/crisis/post) + Omori after 99th-pctl + matched-n null",
            "data_source": "FDIC banks.data.fdic.gov public API (4,114 raw / 3,960 with valid assets)",
            "data_source_en": "FDIC banks.data.fdic.gov public API (4,114 raw / 3,960 with valid assets)",
            "sample_size": "3,960 failures across 92 years / 406 tail events above xmin=$627M",
            "paper_target": "Layer 5 Phase 8 — bank failures (Diamond-Dybvig sub-class)",
            "paper_target_en": "Layer 5 Phase 8 — bank failures (Diamond-Dybvig sub-class)",
            "status": "✅ 已验证 (2026-05-13)",
            "status_en": "✅ Verified (2026-05-13)",
            "rationale": "首次明确针对 V4 Louvain L01 sub-community (Diamond-Dybvig) 实证。92 年数据 + 1980s S&L 危机主导。与 DeFi (Phase 3) 同 sub-class, 跨 1000× 时间尺度同一签名。",
            "rationale_en": "First explicit empirical validation of V4 Louvain L01 sub-community (Diamond-Dybvig). 92 years of data, dominated by 1980s S&L crisis. Same sub-class signature as DeFi (Phase 3) across a 1000× time-scale difference.",
            "paper_url": "/paper/soc-bank-failures-2026-05-13",
            "paper_title": "FDIC bank failure size distribution: Diamond-Dybvig SOC sub-class on 92 years of US data",
        },
    ],
    "preferential_attachment": [
        {
            "target": "GitHub 仓库 star 数 (8,398 repos, stratified sample 250-500k stars)",
            "target_en": "GitHub repository star counts (8,398 repos, stratified sample 250-500k stars)",
            "prediction": "Clauset α(stars) = 2.867 ± 0.050, bootstrap 95% CI [2.781, 3.000], 完美对齐 Barabási-Albert α=3 asymptote",
            "prediction_en": "Clauset α(stars) = 2.867 ± 0.050, bootstrap 95% CI [2.781, 3.000], perfectly aligns with Barabási-Albert α=3 asymptote",
            "test_method": "Clauset MLE (discrete) + bootstrap n=100 + per-language sub-fits + matched-n null",
            "data_source": "GitHub Search API stratified by `stars:>N` buckets (10 buckets spanning 100→500k)",
            "data_source_en": "GitHub Search API stratified by `stars:>N` buckets (10 buckets spanning 100→500k)",
            "sample_size": "8,398 unique repos / 1,417 tail events above xmin=25,585 stars",
            "paper_target": "Layer 5 Phase 6 — preferential_attachment class first verification",
            "paper_target_en": "Layer 5 Phase 6 — preferential_attachment class first verification",
            "status": "✅ 已验证 (2026-05-13)",
            "status_en": "✅ Verified (2026-05-13)",
            "rationale": "首次实证 preferential_attachment 普适类。每语言独立确认 (JS=3.00 / C++=2.98 / TS=2.85 / Py=2.75 / Go=2.65 / Java=2.61)，均落在 BA 带。",
            "rationale_en": "First empirical confirmation of preferential_attachment universality class. Per-language fits all in BA band (JS=3.00, C++=2.98, TS=2.85, Python=2.75, Go=2.65, Java=2.61).",
            "paper_url": "/paper/soc-github-stars-2026-05-13",
            "paper_title": "Repository popularity on GitHub follows preferential-attachment universality",
        },
    ],
}


PAPER_COPIES = {
    "soc-wildfire-2026-05-13": REPO / "v4" / "validation" / "soc-wildfire" / "paper.md",
    "soc-solar-2026-05-13": REPO / "v4" / "validation" / "soc-solar" / "paper.md",
    "soc-bank-failures-2026-05-13": REPO / "v4" / "validation" / "soc-bank-failures" / "paper.md",
    "soc-github-stars-2026-05-13": REPO / "v4" / "validation" / "soc-github-stars" / "paper.md",
}


def main():
    d = json.load(SITE_JSON.open())
    classes = {c["class_id"]: c for c in d["classes"]}

    for class_id, new_preds in NEW_PREDICTIONS.items():
        if class_id not in classes:
            print(f"[skip] class_id {class_id} not present in site data")
            continue
        cls = classes[class_id]
        existing_targets = {p.get("target_en") for p in cls.get("predictions", [])}
        added = 0
        for p in new_preds:
            if p["target_en"] in existing_targets:
                continue
            cls.setdefault("predictions", []).append(p)
            added += 1
        print(f"[ok] {class_id}: added {added} predictions ({len(cls['predictions'])} total)")

    # Update meta
    d["meta"]["last_updated"] = "2026-05-13"
    d["meta"]["layer5_phase_count"] = d["meta"].get("layer5_phase_count", 5) + 4

    # Update stats — count predictions by status
    total_verified = 0
    for c in d["classes"]:
        for p in c.get("predictions", []):
            if "verified" in p.get("status_en", "").lower() or "✅" in p.get("status", ""):
                total_verified += 1
    d["stats"]["verified_predictions"] = total_verified
    print(f"[stats] total verified predictions: {total_verified}")

    with SITE_JSON.open("w") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f"Wrote {SITE_JSON}")

    # Copy papers
    for slug, src in PAPER_COPIES.items():
        if not src.exists():
            print(f"[skip-copy] {src} missing")
            continue
        dst = PAPER_OUT / f"{slug}.md"
        shutil.copy(src, dst)
        print(f"[copy] {src.name} → {dst.relative_to(REPO)}")


if __name__ == "__main__":
    main()
