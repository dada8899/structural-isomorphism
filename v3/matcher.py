"""
V3 Structural Matcher — score pairs by StructTuple field match.
"""
import json
from pathlib import Path
from itertools import combinations

V3_DIR = Path(__file__).parent

# Dynamics family similarity matrix — related families are not identical but close
# Specificity weight per family: catch-all families get downweighted to avoid
# dominating the top because they include too many phenomena.
FAMILY_SPECIFICITY = {
    # Generic catch-alls (logistic/saturating = most common dynamics)
    "ODE1_saturating": 0.4,
    "ODE1_linear": 0.4,
    "ODE1_exponential_growth": 0.6,
    "ODE1_exponential_decay": 0.6,
    "ODE1_logistic": 0.5,
    "Stochastic_process": 0.5,
    "Random_walk": 0.6,
    "Unknown": 0.0,
}
# All other specific families get specificity 1.0


def family_specificity(family: str) -> float:
    return FAMILY_SPECIFICITY.get(family, 1.0)


DYNAMICS_SIMILARITY = {
    # Groups of closely related families (mutual similarity 0.7 if not identical)
    "ode1_group": {
        "ODE1_linear", "ODE1_exponential_growth", "ODE1_exponential_decay",
        "ODE1_logistic", "ODE1_saturating",
    },
    "ode2_group": {
        "ODE2_damped_oscillation", "ODE2_undamped_oscillation",
    },
    "pde_group": {
        "PDE_reaction_diffusion", "PDE_wave", "PDE_diffusion",
    },
    "phase_transition_group": {
        "Phase_transition_1st", "Phase_transition_2nd", "Fold_bifurcation",
        "Hopf_bifurcation", "Bistable_switch", "Hysteresis_loop",
        "Percolation_threshold",
    },
    "network_group": {
        "Network_cascade", "Percolation_network",
    },
    "stochastic_group": {
        "Stochastic_process", "Random_walk", "Markov_chain", "Markov_decision",
    },
    "game_group": {
        "Game_theoretic_equilibrium", "Self_fulfilling_prophecy",
    },
    "heavy_tail_group": {
        "Power_law_distribution", "Heavy_tail_extremal",
    },
    "delayed_group": {
        "DDE_delayed_feedback",
    },
}


def dynamics_sim(a: str, b: str) -> float:
    if not a or not b or a == "Unknown" or b == "Unknown":
        return 0.0
    if a == b:
        return 1.0
    for group in DYNAMICS_SIMILARITY.values():
        if a in group and b in group:
            return 0.7
    return 0.0


def field_match(a, b, field, default=""):
    va = a.get(field, default)
    vb = b.get(field, default)
    if not va or not vb:
        return 0.0
    if va == "unknown" or vb == "unknown":
        return 0.0
    return 1.0 if va == vb else 0.0


def timescale_sim(a, b):
    ta = a.get("timescale_log10_s")
    tb = b.get("timescale_log10_s")
    if ta is None or tb is None:
        return 0.5  # unknown - neutral
    diff = abs(ta - tb)
    # Exp decay: same scale=1.0, 3 orders diff=0.5, 6 orders diff=0.25
    return 2 ** (-diff / 3)


def timescale_gap_reject(a, b, max_gap: int = 8) -> bool:
    """Hard reject if timescales differ by more than max_gap orders of magnitude."""
    ta = a.get("timescale_log10_s")
    tb = b.get("timescale_log10_s")
    if ta is None or tb is None:
        return False
    return abs(ta - tb) > max_gap


def equation_quality(item) -> float:
    """DDE/PDE families need canonical_equation for full credit (quantitative check).
    Soft penalty: missing equation reduces to 0.8 rather than 0.5, so genuine
    PDE/DDE pairs aren't dropped from top 20 just because the extractor didn't
    emit a canonical_equation string."""
    eq = item.get("canonical_equation", "") or ""
    if len(eq.strip()) >= 5 and any(c in eq for c in ["d/dt", "∂", "dx/dt", "dN/dt", "dT/dt", "/dt", "="]):
        return 1.0
    return 0.8


def score_pair(a, b):
    """Return (score, components) for a StructTuple pair."""
    # Skip same-domain pairs (not cross-domain)
    if a.get("domain") == b.get("domain"):
        return -1.0, {"reason": "same_domain"}

    fam_a = a.get("dynamics_family", "")
    fam_b = b.get("dynamics_family", "")
    ds = dynamics_sim(fam_a, fam_b)
    if ds == 0.0:
        # hard gate: no dynamics overlap → cannot be same family
        return 0.0, {"reason": "dynamics_mismatch", "dynamics_sim": 0.0}

    # Hard timescale gating: reject if scales differ by more than 8 orders of magnitude
    # EXCEPT for PDE families — diffusion/wave math is scale-invariant (same equation
    # whether electrons in ns or water in years). Only apply gate to ODE/DDE/Markov etc.
    is_pde_family = fam_a.startswith("PDE_") and fam_b.startswith("PDE_")
    if not is_pde_family and timescale_gap_reject(a, b):
        return 0.0, {"reason": "timescale_gap", "dynamics_sim": ds}

    # Specificity: catch-all families (ODE1_saturating etc.) get downweighted
    spec = min(family_specificity(fam_a), family_specificity(fam_b))

    # Equation quality: families requiring quantitative equations (DDE, PDE, ODE2)
    # get penalty if one side lacks canonical_equation
    eq_sensitive = fam_a.startswith(("DDE_", "PDE_", "ODE2_"))
    if eq_sensitive:
        eq_quality = min(equation_quality(a), equation_quality(b))
    else:
        eq_quality = 1.0

    ds_weighted = ds * spec * eq_quality

    fb = field_match(a, b, "feedback_topology")
    bb = field_match(a, b, "boundary_behavior")
    ts = timescale_sim(a, b)

    # weighted score: dynamics (specificity-adjusted) dominates, others modulate
    score = 0.55 * ds_weighted + 0.15 * fb + 0.15 * bb + 0.15 * ts
    return score, {
        "dynamics_sim": ds,
        "specificity": spec,
        "eq_quality": eq_quality,
        "dynamics_weighted": round(ds_weighted, 2),
        "feedback_match": fb,
        "boundary_match": bb,
        "timescale_sim": round(ts, 2),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(V3_DIR / "sample-opus-50.jsonl"))
    ap.add_argument("--topk", type=int, default=20)
    ap.add_argument("--out", default=str(V3_DIR / "v3-top20.jsonl"))
    args = ap.parse_args()

    items = [json.loads(l) for l in open(args.input)]
    print(f"Loaded {len(items)} StructTuples from {args.input}")

    pairs = []
    for i, j in combinations(range(len(items)), 2):
        a, b = items[i], items[j]
        score, comp = score_pair(a, b)
        if score <= 0:
            continue
        pairs.append({
            "score": round(score, 3),
            "a_id": a.get("phenomenon_id", ""),
            "a_name": a.get("name", ""),
            "a_domain": a.get("domain", ""),
            "a_dynamics": a.get("dynamics_family", ""),
            "b_id": b.get("phenomenon_id", ""),
            "b_name": b.get("name", ""),
            "b_domain": b.get("domain", ""),
            "b_dynamics": b.get("dynamics_family", ""),
            "components": comp,
        })

    pairs.sort(key=lambda x: -x["score"])
    print(f"Total cross-domain pairs with dynamics match: {len(pairs)}")
    print(f"\nTop {args.topk}:")
    for r, p in enumerate(pairs[:args.topk], 1):
        print(f"  {r:2d}. {p['score']:.3f}  [{p['a_dynamics']}]  {p['a_name']} × {p['b_name']}")

    with open(args.out, "w") as f:
        for p in pairs[:args.topk]:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"\nSaved top {args.topk} to {args.out}")


if __name__ == "__main__":
    main()
