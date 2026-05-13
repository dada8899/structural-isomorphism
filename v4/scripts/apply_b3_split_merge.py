"""Apply B3 ensemble verdicts (SPLIT/MERGE/REJECT/KEEP) to taxonomy yaml files.

Reads:
  v4/results/B3_taxonomy_v2.jsonl  — final per-class verdicts
  v4/taxonomy/classes/*.yaml       — current class definitions

Writes:
  v4/taxonomy/classes/<class>_<subname>.yaml — new SPLIT children
  v4/taxonomy/classes/<class>.yaml           — updated with b3_status / b3_verdict / b3_action_taken
  v4/taxonomy/B1_B3_split_merge_summary.md   — human-readable change log

Run from repo root: python3 v4/scripts/apply_b3_split_merge.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CLASSES_DIR = REPO_ROOT / "v4" / "taxonomy" / "classes"
B3_JSONL = REPO_ROOT / "v4" / "results" / "B3_taxonomy_v2.jsonl"
SUMMARY_MD = REPO_ROOT / "v4" / "taxonomy" / "B1_B3_split_merge_summary.md"


# ---------------------------------------------------------------------------
# Verdict normalization: B3 consensus wins over B1 when they disagree
# (per CLAUDE.md ensemble-review policy — multi-model B3 trumps single-pass B1)
# ---------------------------------------------------------------------------

def normalize_verdict(final_verdict: str, b3_consensus: str) -> str:
    """Collapse final_verdict variants to one of KEEP / REJECT / SPLIT / MERGE.

    Policy: B3 multi-model consensus wins over B1 single-pass (per CLAUDE.md).
    Defer to b3_consensus directly — it already reflects majority of 3 reviewers.
    """
    return b3_consensus.upper()


# ---------------------------------------------------------------------------
# Split / Merge plans
# Hand-authored from B3 ensemble rationales (see v4/results/B3_ensemble_review.jsonl)
# ---------------------------------------------------------------------------

SPLIT_PLANS: dict[str, list[dict]] = {
    "adverse_selection_unraveling_class": [
        {
            "suffix": "akerlof_lemons",
            "display_name": "Akerlof lemons unraveling (hidden quality + price-driven exit)",
            "display_name_zh": "Akerlof 柠檬市场逆向选择",
            "hub_phenomenon": "Hidden quality + price-conditional expectation equilibrium p* = E[q|p*] producing monotone exit of high-quality types.",
            "split_rationale": "Akerlof-specific: hidden quality with conditional-expectation equilibrium. Spiral of silence and echo chambers share only surface dynamics and were removed.",
            "members_kept": ["used car lemons", "labor market signaling", "insurance adverse selection"],
        },
        {
            "suffix": "spiral_of_silence",
            "display_name": "Spiral of silence (social conformity + fear-of-isolation cascade)",
            "display_name_zh": "沉默的螺旋 (社会从众级联)",
            "hub_phenomenon": "Perceived minority opinions self-silence under conformity pressure; majority view amplifies via positive feedback on visibility.",
            "split_rationale": "Different mechanism from adverse selection: no hidden quality dimension, driven by conformity pressure and fear of isolation (Noelle-Neumann).",
            "members_kept": ["public opinion polarization", "self-censorship in authoritarian regimes"],
        },
        {
            "suffix": "echo_chamber_filter",
            "display_name": "Echo chamber / filter-bubble collapse (algorithmic relevance feedback)",
            "display_name_zh": "回音室 / 信息茧房 (算法过滤反馈)",
            "hub_phenomenon": "Recommendation algorithm reinforces engagement-correlated views, collapsing exposure diversity over time.",
            "split_rationale": "Driven by algorithmic relevance feedback, not adverse selection or conformity. Distinct class.",
            "members_kept": ["social media filter bubbles", "personalized news feed polarization"],
        },
    ],
    "leaky_integrate_fire_threshold_class": [
        {
            "suffix": "lif_reset",
            "display_name": "Leaky integrate-and-fire with reset (Lapicque LIF + token bucket)",
            "display_name_zh": "漏积分-激发-重置 (经典 LIF)",
            "hub_phenomenon": "dV/dt = -(V - V_rest)/τ + I/C, with V → V_reset upon V ≥ V_threshold (discrete reset, refractory period).",
            "split_rationale": "Full LIF mechanism: leaky integration + threshold + DISCRETE RESET. Excludes Piezo1 (conformational gating, no reset) and hedonic treadmill (continuous adaptation).",
            "members_kept": ["Lapicque cortical neuron", "network token bucket / leaky bucket rate limiter", "dripping faucet"],
        },
        {
            "suffix": "threshold_adaptation",
            "display_name": "Threshold-only adaptation (gating without reset)",
            "display_name_zh": "无重置的阈值适应 (门控适应)",
            "hub_phenomenon": "Variable accumulates against threshold but lacks discrete-event reset; relaxation is continuous gating or homeostatic adaptation.",
            "split_rationale": "Distinguished from LIF by absence of reset step. Piezo1 and hedonic treadmill belong here.",
            "members_kept": ["Piezo1 mechanosensitive gating", "hedonic treadmill adaptation"],
        },
    ],
    "sir_contagion_network_class": [
        {
            "suffix": "sir_epidemic",
            "display_name": "SIR epidemic on network (recovery + R0 threshold)",
            "display_name_zh": "网络 SIR 流行病 (恢复 + R0 阈值)",
            "hub_phenomenon": "Kermack-McKendrick SIR: dS/dt = -βSI, dI/dt = βSI - γI, dR/dt = γI; epidemic threshold R0 = β⟨k⟩/γ > 1; final size obeys R∞/N = 1 - exp(-R0·R∞/N).",
            "split_rationale": "True SIR requires recovery compartment with γ > 0 and final-size law. Excludes balance-sheet financial cascades.",
            "members_kept": ["drug-resistant bacteria spread", "measles outbreak", "COVID transmission"],
        },
        {
            "suffix": "balance_sheet_cascade",
            "display_name": "Balance-sheet contagion cascade (no-recovery clearing equilibrium)",
            "display_name_zh": "资产负债表传染级联 (无恢复，清算均衡)",
            "hub_phenomenon": "Eisenberg-Noe clearing vectors: defaults are absorbing, no recovery compartment. Critical threshold is leverage/capital-ratio based, not γ-based.",
            "split_rationale": "Financial contagion lacks recovery; mechanism is threshold cascade on exposure graph, not SIR.",
            "members_kept": ["CDS counterparty cascade", "OTC derivatives contagion", "interbank exposure default cascade"],
        },
    ],
    "motter_lai_network_cascade": [
        {
            "suffix": "conserved_load",
            "display_name": "Motter-Lai conservative load redistribution cascade",
            "display_name_zh": "Motter-Lai 守恒负载再分配级联",
            "hub_phenomenon": "Node capacity C_i = (1+α)L_i^(0). Failed node's load redistributes to neighbors conservatively; over-capacity triggers further failure. Cascade size τ ∈ [1.5, 2.0] near α_c.",
            "split_rationale": "Conserved-load redistribution with capacity thresholds. Excludes neighbor-fraction Watts cascades (no load conservation).",
            "members_kept": ["power grid blackout cascade", "building progressive collapse", "Eisenberg-Noe financial cascade (conserved version)"],
        },
        {
            "suffix": "threshold_contagion",
            "display_name": "Watts threshold contagion (neighbor-fraction activation, non-conserved)",
            "display_name_zh": "Watts 阈值传染 (邻居比例激活, 非守恒)",
            "hub_phenomenon": "Each node activates when fraction of active neighbors exceeds threshold φ_i. No conserved quantity flows; cascade size distribution differs from Motter-Lai.",
            "split_rationale": "Non-conserved, neighbor-fraction activation. Distinct universality class from Motter-Lai.",
            "members_kept": ["Watts threshold model on social networks", "DeFi liquidation cascades (leverage-driven, non-conserved)", "social media virality cascades"],
        },
    ],
    "percolation_connectivity": [
        {
            "suffix": "geometric_lattice",
            "display_name": "Geometric percolation on low-dimensional lattice (dimension-dependent exponents)",
            "display_name_zh": "几何渗流 (低维格点, 维度相关指数)",
            "hub_phenomenon": "P_∞ ∝ (p - p_c)^β with β, ν, γ determined by lattice dimension (e.g., 2D: β = 5/36, ν = 4/3).",
            "split_rationale": "Lattice geometry sets exponent values. Excludes mean-field on complex networks.",
            "members_kept": ["porous media fluid flow", "oil reservoir percolation", "2D site/bond percolation"],
        },
        {
            "suffix": "mean_field_network",
            "display_name": "Mean-field percolation on complex networks (MF exponents)",
            "display_name_zh": "复杂网络上的平均场渗流",
            "hub_phenomenon": "Giant component emerges at ⟨k²⟩/⟨k⟩ = 2; mean-field exponents β = 1, γ = 1 independent of underlying topology.",
            "split_rationale": "Mean-field universality, distinct from lattice geometric percolation.",
            "members_kept": ["epidemic threshold on random networks", "social identity contagion threshold", "scale-free network giant component"],
        },
    ],
}

# Merge plans: each maps source class → target class id (the parent it folds into).
# motter_lai_network_cascade_social is a special case: the parent is being SPLIT,
# so we redirect it into motter_lai_network_cascade__threshold_contagion child.
MERGE_PLANS: dict[str, str] = {
    "gardner_collins_toggle_switch_Th1Th2": "gardner_collins_toggle_switch",
    "gardner_collins_toggle_switch_apoptosis": "gardner_collins_toggle_switch",
    "motter_lai_network_cascade_social": "motter_lai_network_cascade__threshold_contagion",
    "hysteresis_first_order_transition_fertility": "hysteresis_first_order_transition",
}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def load_verdicts() -> dict[str, dict]:
    out: dict[str, dict] = {}
    with B3_JSONL.open() as f:
        for line in f:
            d = json.loads(line)
            out[d["class_id"]] = d
    return out


def load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def dump_yaml(path: Path, data: dict) -> None:
    with path.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, width=120)


def annotate_in_place(path: Path, verdict_row: dict, action: str) -> dict:
    """Add b3_status / b3_verdict / b3_action_taken without disturbing existing fields.

    Returns the mutated yaml dict (also written back to disk).
    """
    d = load_yaml(path)
    norm = normalize_verdict(verdict_row["final_verdict"], verdict_row["b3_consensus"])
    status_map = {
        "KEEP": "VERIFIED_B3",
        "REJECT": "REJECTED_B3",
        "SPLIT": "SPLIT_B3",
        "MERGE": "MERGED_B3",
    }
    d["b3_status"] = status_map[norm]
    d["b3_verdict"] = verdict_row["final_verdict"]
    d["b3_consensus"] = verdict_row["b3_consensus"]
    d["b3_avg_confidence"] = verdict_row["b3_avg_confidence"]
    d["b3_action_taken"] = action
    if norm == "REJECT":
        d["rejection_reason"] = (
            f"B3 ensemble consensus={verdict_row['b3_consensus']} "
            f"(avg confidence {verdict_row['b3_avg_confidence']:.2f}); "
            f"final verdict {verdict_row['final_verdict']}. "
            "Retained as historical record per CLAUDE.md (no class deletion)."
        )
    dump_yaml(path, d)
    return d


def build_split_child(parent_yaml: dict, parent_id: str, plan: dict, verdict_row: dict) -> dict:
    child = copy.deepcopy(parent_yaml)
    child_id = f"{parent_id}__{plan['suffix']}"
    child["class_id"] = child_id
    child["status"] = "speculative"
    child["b3_status"] = "SPLIT_B3_CHILD"
    child["parent_class"] = parent_id
    child["split_from"] = parent_id
    child["split_rationale"] = plan["split_rationale"]
    child["display_name"] = plan["display_name"]
    child["display_name_zh"] = plan["display_name_zh"]
    child["hub_phenomenon"] = plan["hub_phenomenon"]
    child["members_kept_after_split"] = plan["members_kept"]
    child["b3_verdict"] = verdict_row["final_verdict"]
    child["b3_avg_confidence"] = verdict_row["b3_avg_confidence"]
    # Inherited positive/negative/edge examples remain — flagged for review.
    child["needs_b4_review"] = (
        "Inherited B4 examples from parent. Filter / re-curate after split."
    )
    return child


def main() -> int:
    verdicts = load_verdicts()

    summary_rows: list[dict] = []
    new_files: list[str] = []

    # 1) Apply SPLITs first (so MERGE targets can point at split children).
    for parent_id, plans in SPLIT_PLANS.items():
        parent_path = CLASSES_DIR / f"{parent_id}.yaml"
        if not parent_path.exists():
            print(f"WARN: split parent not found: {parent_path}", file=sys.stderr)
            continue
        vr = verdicts[parent_id]
        action = f"split into {len(plans)} children: " + ", ".join(
            f"{parent_id}__{p['suffix']}" for p in plans
        )
        parent_yaml = annotate_in_place(parent_path, vr, action)
        # Mark parent explicitly as superseded.
        parent_yaml["superseded_by_split"] = [f"{parent_id}__{p['suffix']}" for p in plans]
        dump_yaml(parent_path, parent_yaml)

        for plan in plans:
            child_id = f"{parent_id}__{plan['suffix']}"
            child_path = CLASSES_DIR / f"{child_id}.yaml"
            child = build_split_child(parent_yaml, parent_id, plan, vr)
            dump_yaml(child_path, child)
            new_files.append(child_path.name)
            summary_rows.append({
                "action": "SPLIT_CHILD",
                "class_id": child_id,
                "parent": parent_id,
                "verdict": vr["final_verdict"],
                "confidence": vr["b3_avg_confidence"],
            })
        summary_rows.append({
            "action": "SPLIT_PARENT",
            "class_id": parent_id,
            "parent": "",
            "verdict": vr["final_verdict"],
            "confidence": vr["b3_avg_confidence"],
        })

    # 2) Apply MERGEs.
    for source_id, target_id in MERGE_PLANS.items():
        src_path = CLASSES_DIR / f"{source_id}.yaml"
        if not src_path.exists():
            print(f"WARN: merge source not found: {src_path}", file=sys.stderr)
            continue
        vr = verdicts[source_id]
        action = f"merged into {target_id} (kept as historical pointer)"
        src_yaml = annotate_in_place(src_path, vr, action)
        src_yaml["merged_into"] = target_id
        src_yaml["b3_status"] = "MERGED_B3"
        dump_yaml(src_path, src_yaml)
        summary_rows.append({
            "action": "MERGE_SOURCE",
            "class_id": source_id,
            "parent": target_id,
            "verdict": vr["final_verdict"],
            "confidence": vr["b3_avg_confidence"],
        })

        # Annotate the merge target with `merged_from` (target is either an existing
        # parent yaml or a SPLIT child we just created).
        tgt_path = CLASSES_DIR / f"{target_id}.yaml"
        if not tgt_path.exists():
            print(f"WARN: merge target yaml not found: {tgt_path}", file=sys.stderr)
            continue
        tgt = load_yaml(tgt_path)
        merged_from = tgt.get("merged_from") or []
        if source_id not in merged_from:
            merged_from.append(source_id)
        tgt["merged_from"] = merged_from
        dump_yaml(tgt_path, tgt)

    # 3) Annotate REJECT classes.
    for cid, vr in verdicts.items():
        if cid in SPLIT_PLANS or cid in MERGE_PLANS:
            continue
        norm = normalize_verdict(vr["final_verdict"], vr["b3_consensus"])
        cpath = CLASSES_DIR / f"{cid}.yaml"
        if not cpath.exists():
            print(f"WARN: yaml not found: {cpath}", file=sys.stderr)
            continue
        if norm == "REJECT":
            annotate_in_place(cpath, vr, "rejected per B3 consensus; kept as historical record")
            summary_rows.append({
                "action": "REJECT",
                "class_id": cid,
                "parent": "",
                "verdict": vr["final_verdict"],
                "confidence": vr["b3_avg_confidence"],
            })
        elif norm == "KEEP":
            annotate_in_place(cpath, vr, "verified by B3 consensus; class kept as-is")
            summary_rows.append({
                "action": "KEEP",
                "class_id": cid,
                "parent": "",
                "verdict": vr["final_verdict"],
                "confidence": vr["b3_avg_confidence"],
            })
        else:  # SPLIT / MERGE that fell through above (shouldn't happen)
            print(f"WARN: unhandled verdict for {cid}: {norm}", file=sys.stderr)

    # 4) Write summary markdown.
    lines: list[str] = []
    lines.append("# B1 ⊗ B3 Split / Merge / Reject / Keep — Summary")
    lines.append("")
    lines.append("> Generated by `v4/scripts/apply_b3_split_merge.py` from `v4/results/B3_taxonomy_v2.jsonl`.")
    lines.append("> Per CLAUDE.md ensemble-review policy: when B1 single-pass and B3 multi-model consensus disagree, B3 wins.")
    lines.append("")

    def section(title: str, action: str) -> None:
        rows = [r for r in summary_rows if r["action"] == action]
        if not rows:
            return
        lines.append(f"## {title} ({len(rows)})")
        lines.append("")
        lines.append("| class_id | parent / target | B3 final_verdict | B3 avg conf |")
        lines.append("|---|---|---|---|")
        for r in rows:
            lines.append(
                f"| `{r['class_id']}` | {r['parent'] or '—'} | {r['verdict']} | {r['confidence']:.2f} |"
            )
        lines.append("")

    section("KEEP — VERIFIED_B3", "KEEP")
    section("SPLIT — parents superseded by children", "SPLIT_PARENT")
    section("SPLIT — new child classes", "SPLIT_CHILD")
    section("MERGE — sources folded into targets", "MERGE_SOURCE")
    section("REJECT — kept as historical record", "REJECT")

    lines.append("## File-level changes")
    lines.append("")
    lines.append(f"- New yaml files: {len(new_files)}")
    for name in sorted(new_files):
        lines.append(f"  - `v4/taxonomy/classes/{name}`")
    lines.append("")
    lines.append("## Net taxonomy count")
    lines.append("")
    before = len(list(CLASSES_DIR.glob("*.yaml"))) - len(new_files)
    after = len(list(CLASSES_DIR.glob("*.yaml")))
    lines.append(f"- Before: {before} yaml files")
    lines.append(f"- After:  {after} yaml files  (Δ = +{after - before})")
    lines.append("")
    lines.append("Note: REJECT and MERGE source files are retained as historical pointers (with `b3_status: REJECTED_B3` / `MERGED_B3`), not deleted, per CLAUDE.md no-data-loss policy.")
    lines.append("")

    SUMMARY_MD.write_text("\n".join(lines))
    print(f"Wrote summary: {SUMMARY_MD}")
    print(f"New files: {len(new_files)}")
    print(f"Final yaml count: {len(list(CLASSES_DIR.glob('*.yaml')))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
