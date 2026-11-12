#!/usr/bin/env python3
"""V0.4 validation — scale_free_percolation_class.

Pipeline:
  D1. Barabási-Albert simulated networks at multiple N (textbook anchor)
  D2. CAIDA AS-level Internet topology (real, undirected)
  D3. SNAP MUSAE GitHub mutual-follow network (real, undirected)

Methods:
  M1. Degree distribution gamma fit (Clauset-Shalizi-Newman MLE) + xmin scan
  M2. Bond percolation simulation -> finite-cluster size distribution P(s)
       -> Clauset MLE tail exponent tau' near pc
  M3. Finite-size scaling collapse: largest-cluster S(p) / N^(beta/nu) across N
  M4. Targeted attack (hub removal) vs random failure -> dual robustness/fragility

Compare tau' against percolation_connectivity baseline tau = 187/91 = 2.055 (2D
lattice RSW universality, Stauffer-Aharony). Newman 2002 PRE 66:016128 +
Cohen-Erez-ben-Avraham-Havlin 2000 PRL 85:4626 predict for SF networks with
degree exponent gamma in (2, 4):
     tau_SF = (2*gamma - 1) / (gamma - 1)
     gamma = 3.0 -> tau_SF = 2.50
     gamma = 2.5 -> tau_SF = 2.67
     gamma = 2.1 -> tau_SF = 2.91
   These should be NOT equal to mean-field/lattice tau in [2.00, 2.20].

Outputs:
  results.json  - all numeric verdicts
  verdict.txt   - one-line decision
  data/         - cached raw networks
  run.log       - stdout/stderr trail
"""
from __future__ import annotations

import bz2
import csv
import json
import logging
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import networkx as nx
from scipy import stats

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DATA.mkdir(parents=True, exist_ok=True)
LOG_FILE = HERE / "run.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("sfp")

RNG = np.random.default_rng(20260525)


# ============================================================
# Clauset-Shalizi-Newman power-law MLE for discrete data
# ============================================================
def clauset_alpha_mle(x: np.ndarray, xmin: float) -> Tuple[float, float, int]:
    """Continuous MLE estimator (also a good approx for discrete tail).

    Returns:
        alpha  - exponent
        se     - asymptotic SE
        n_tail - number of points used
    """
    tail = x[x >= xmin]
    n = tail.size
    if n < 10:
        return float("nan"), float("nan"), n
    s = np.sum(np.log(tail / xmin))
    if s <= 0:
        return float("nan"), float("nan"), n
    alpha = 1.0 + n / s
    se = (alpha - 1.0) / math.sqrt(n)
    return alpha, se, n


def clauset_ks_distance(x: np.ndarray, xmin: float, alpha: float) -> float:
    tail = np.sort(x[x >= xmin])
    n = tail.size
    if n < 10 or not math.isfinite(alpha) or alpha <= 1:
        return float("nan")
    emp_cdf = np.arange(1, n + 1) / n
    th_cdf = 1.0 - (tail / xmin) ** (1.0 - alpha)
    return float(np.max(np.abs(emp_cdf - th_cdf)))


def fit_powerlaw_xmin_scan(
    x: np.ndarray, xmin_candidates: Optional[List[float]] = None
) -> Dict[str, float]:
    """Scan xmin to minimise KS distance, then return MLE alpha."""
    x = np.asarray(x, dtype=float)
    x = x[(x > 0) & np.isfinite(x)]
    if x.size < 50:
        return {
            "alpha": float("nan"),
            "se": float("nan"),
            "xmin": float("nan"),
            "ks": float("nan"),
            "n_tail": 0,
        }
    if xmin_candidates is None:
        # Combine quantile grid + small-integer grid (cluster sizes are discrete,
        # singletons dominate the bulk and must be excluded by xmin >= 2 typically).
        uniq = np.unique(x)
        xmax = float(np.max(x))
        # Always include a small-integer ladder + quantile grid, regardless of unique-count.
        small = [v for v in [2, 3, 4, 5, 7, 10, 15, 20, 30, 50, 100, 200, 500]
                 if v < xmax]
        qg = list(np.quantile(x, np.linspace(0.05, 0.90, 20))) if x.size > 0 else []
        cands = set()
        for v in qg + small:
            try:
                fv = float(v)
                if fv > 0 and fv < xmax:
                    cands.add(round(fv, 4))
            except (TypeError, ValueError):
                continue
        # also include some unique values (largest ones often best for heavy tails)
        if uniq.size > 0:
            for v in uniq[: min(uniq.size, 50)]:
                cands.add(round(float(v), 4))
        xmin_candidates = sorted(cands)
        if not xmin_candidates:
            xmin_candidates = [1.0]
    best = {
        "alpha": float("nan"),
        "se": float("nan"),
        "xmin": float("nan"),
        "ks": float("inf"),
        "n_tail": 0,
    }
    for xm in xmin_candidates:
        if xm <= 0:
            continue
        a, s, n = clauset_alpha_mle(x, xm)
        if not math.isfinite(a):
            continue
        ks = clauset_ks_distance(x, xm, a)
        if not math.isfinite(ks):
            continue
        if ks < best["ks"]:
            best = {"alpha": a, "se": s, "xmin": float(xm), "ks": ks, "n_tail": int(n)}
    if not math.isfinite(best["ks"]):
        best["ks"] = float("nan")
    return best


# ============================================================
# Self-test on Pareto positive controls
# ============================================================
def positive_control_pareto() -> Dict[str, float]:
    """Self-test: draw N=10000 from Pareto(b=2.5), recover alpha."""
    out = {}
    for true_alpha in (2.5, 3.0):
        b = true_alpha
        # scipy.stats.pareto: x >= 1 with shape b, P(X>x)=x^-b -> tail exponent alpha = b+1
        # In Clauset convention P(X>=x) ~ x^-(alpha-1), so observed alpha = b+1.
        sample = stats.pareto.rvs(b=b, size=10_000, random_state=RNG)
        fit = fit_powerlaw_xmin_scan(sample)
        # Expected alpha = b+1 in Clauset notation. (verify)
        out[f"pareto_b={true_alpha}"] = {
            "expected_alpha": true_alpha + 1.0,
            "fit_alpha": fit["alpha"],
            "fit_ks": fit["ks"],
            "abs_err": abs(fit["alpha"] - (true_alpha + 1.0))
            if math.isfinite(fit["alpha"])
            else float("nan"),
        }
    log.info("Positive control Pareto: %s", out)
    return out


# ============================================================
# Dataset loaders
# ============================================================
def load_ba(n: int, m: int) -> nx.Graph:
    g = nx.barabasi_albert_graph(n, m, seed=int(RNG.integers(0, 1 << 30)))
    return g


def load_caida(path: Path) -> nx.Graph:
    g = nx.Graph()
    with bz2.open(path, "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.strip().split("|")
            if len(parts) < 2:
                continue
            try:
                u, v = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            if u != v:
                g.add_edge(u, v)
    return g


def load_github(edges_csv: Path) -> nx.Graph:
    g = nx.Graph()
    with open(edges_csv, "r") as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if len(row) < 2:
                continue
            try:
                u, v = int(row[0]), int(row[1])
            except ValueError:
                continue
            if u != v:
                g.add_edge(u, v)
    return g


# ============================================================
# Bond percolation simulation
# ============================================================
def bond_percolate(g: nx.Graph, p: float, rng: random.Random) -> List[int]:
    """Return a list of connected-component sizes after retaining each edge with prob p."""
    # Union-Find
    parent = {n: n for n in g.nodes()}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        parent[ra] = rb

    for u, v in g.edges():
        if rng.random() < p:
            union(u, v)
    sizes: Dict[int, int] = {}
    for n in g.nodes():
        r = find(n)
        sizes[r] = sizes.get(r, 0) + 1
    return list(sizes.values())


def percolation_sweep(
    g: nx.Graph,
    p_grid: np.ndarray,
    n_reps: int,
    seed: int,
    tag: str,
) -> Dict[str, np.ndarray]:
    """For each p, run n_reps replicates. Track <s_max>/N and cluster-size distribution at each p."""
    rng = random.Random(seed)
    n = g.number_of_nodes()
    s_max_mean = np.zeros_like(p_grid, dtype=float)
    s_max_var = np.zeros_like(p_grid, dtype=float)
    all_finite_sizes_per_p: List[List[int]] = []
    for i, p in enumerate(p_grid):
        smaxes = []
        finite_pool = []
        for r in range(n_reps):
            sizes = bond_percolate(g, p, rng)
            sizes.sort(reverse=True)
            smax = sizes[0] if sizes else 0
            smaxes.append(smax)
            # exclude the giant cluster from cluster-size distribution
            for s in sizes[1:]:
                finite_pool.append(s)
        s_max_mean[i] = np.mean(smaxes) / n
        s_max_var[i] = np.var(smaxes) / (n * n)
        all_finite_sizes_per_p.append(finite_pool)
        log.info("[%s] p=%.3f S/N=%.4f var/N^2=%.2e nrep=%d finite_pool=%d",
                 tag, p, s_max_mean[i], s_max_var[i], n_reps, len(finite_pool))
    return {
        "p_grid": p_grid,
        "s_max_mean": s_max_mean,
        "s_max_var": s_max_var,
        "finite_sizes": all_finite_sizes_per_p,
    }


def estimate_pc_and_tau(
    sweep: Dict[str, np.ndarray], min_clusters: int = 50
) -> Dict[str, float]:
    """Locate pc as argmax of S_max variance; fit tau' on cluster distribution at pc."""
    p_grid = sweep["p_grid"]
    var = sweep["s_max_var"]
    # smooth with 3-point moving average to mute jitter
    if var.size >= 3:
        smooth = np.convolve(var, np.ones(3) / 3.0, mode="same")
    else:
        smooth = var
    i_pc = int(np.argmax(smooth))
    pc = float(p_grid[i_pc])

    # cluster sizes at pc (and one bin either side for robustness)
    pool = []
    for di in (-1, 0, 1):
        j = i_pc + di
        if 0 <= j < len(sweep["finite_sizes"]):
            pool.extend(sweep["finite_sizes"][j])
    arr = np.array(pool, dtype=float)
    if arr.size < min_clusters:
        return {
            "pc": pc,
            "i_pc": i_pc,
            "tau_prime": float("nan"),
            "tau_se": float("nan"),
            "tau_ks": float("nan"),
            "n_clusters": int(arr.size),
            "status": "INCONCLUSIVE_few_clusters",
        }
    fit = fit_powerlaw_xmin_scan(arr)
    return {
        "pc": pc,
        "i_pc": i_pc,
        "tau_prime": fit["alpha"],
        "tau_se": fit["se"],
        "tau_ks": fit["ks"],
        "tau_xmin": fit["xmin"],
        "n_clusters": int(arr.size),
        "n_tail": fit["n_tail"],
        "status": "OK",
    }


# ============================================================
# Finite-size scaling — multiple BA sizes
# ============================================================
def fss_collapse_BA(sizes: List[int], m: int, p_grid: np.ndarray, n_reps: int) -> Dict:
    """Run percolation on BA at multiple N -> empirical S(p, N).

    For SF networks with gamma in [2, 3]: pc -> 0 as N -> infty.
    For gamma > 3: pc tends to constant (mean-field-like).
    Track pc(N) and beta/nu via S_max(pc) ~ N^(-beta/nu).
    """
    out = {"sizes": sizes, "pc": [], "tau_prime": [], "s_max_at_pc": [], "gamma": []}
    for N in sizes:
        g = load_ba(N, m)
        # gamma fit on this snapshot
        degs = np.array([d for _, d in g.degree()], dtype=float)
        gf = fit_powerlaw_xmin_scan(degs)
        out["gamma"].append(gf["alpha"])
        sweep = percolation_sweep(g, p_grid, n_reps, seed=42 + N, tag=f"BA-N={N}")
        est = estimate_pc_and_tau(sweep)
        out["pc"].append(est["pc"])
        out["tau_prime"].append(est["tau_prime"])
        out["s_max_at_pc"].append(float(sweep["s_max_mean"][est["i_pc"]]))
        log.info("BA N=%d gamma=%.3f pc=%.4f tau'=%.3f Smax/N@pc=%.4f",
                 N, gf["alpha"], est["pc"], est["tau_prime"],
                 sweep["s_max_mean"][est["i_pc"]])
    # estimate beta/nu via log-log fit of (1 - S_max_at_pc) or S_max_at_pc itself
    # Standard FSS: at pc, S/N ~ N^(-beta/nu). Note this is geometric / heuristic on
    # one-dimensional pc, but useful as numerical anchor.
    Ns = np.array(out["sizes"], dtype=float)
    Ss = np.array(out["s_max_at_pc"], dtype=float)
    if np.any(Ss <= 0) or np.any(~np.isfinite(Ss)):
        out["beta_over_nu"] = float("nan")
    else:
        slope, intercept, r, _, se = stats.linregress(np.log(Ns), np.log(Ss))
        out["beta_over_nu"] = -float(slope)
        out["beta_over_nu_se"] = float(se)
        out["beta_over_nu_r2"] = float(r ** 2)
    return out


# ============================================================
# Hub vs random attack
# ============================================================
def attack_curves(g: nx.Graph, mode: str, n_steps: int = 50, seed: int = 0) -> Dict:
    """Remove fraction f of nodes by mode in {'targeted','random'}; track largest CC."""
    rng = random.Random(seed)
    g2 = g.copy()
    n0 = g2.number_of_nodes()
    if mode == "targeted":
        order = sorted(g2.nodes(), key=lambda v: -g2.degree(v))
    else:
        order = list(g2.nodes())
        rng.shuffle(order)
    fs = []
    smaxs = []
    chunk = max(1, len(order) // n_steps)
    for i in range(0, len(order), chunk):
        to_remove = order[i : i + chunk]
        g2.remove_nodes_from(to_remove)
        if g2.number_of_nodes() == 0:
            break
        cc = max((len(c) for c in nx.connected_components(g2)), default=0)
        f = 1.0 - g2.number_of_nodes() / n0
        fs.append(f)
        smaxs.append(cc / n0)
    arr_f = np.array(fs)
    arr_s = np.array(smaxs)
    # define fc = first f where S/N < 0.01
    crit_idx = np.argmax(arr_s < 0.01) if np.any(arr_s < 0.01) else len(arr_s) - 1
    return {
        "mode": mode,
        "f": arr_f.tolist(),
        "smax_over_N": arr_s.tolist(),
        "fc": float(arr_f[crit_idx]) if len(arr_f) > 0 else float("nan"),
    }


# ============================================================
# Per-dataset full pipeline
# ============================================================
def analyze_network(g: nx.Graph, name: str, n_reps: int, p_grid: np.ndarray) -> Dict:
    n_nodes = g.number_of_nodes()
    n_edges = g.number_of_edges()
    log.info("[%s] N=%d E=%d <k>=%.2f", name, n_nodes, n_edges, 2 * n_edges / max(1, n_nodes))

    # Degree distribution
    degs = np.array([d for _, d in g.degree()], dtype=float)
    gamma_fit = fit_powerlaw_xmin_scan(degs)
    log.info("[%s] gamma=%.3f +/- %.3f xmin=%.0f KS=%.3f n_tail=%d",
             name, gamma_fit["alpha"], gamma_fit["se"], gamma_fit["xmin"],
             gamma_fit["ks"], gamma_fit["n_tail"])

    # Bond percolation
    sweep = percolation_sweep(g, p_grid, n_reps, seed=hash(name) & 0xFFFFFFFF, tag=name)
    perc = estimate_pc_and_tau(sweep)

    # Theoretical SF tau prediction
    # Newman 2002 PRE 66:016128 eq.(4): tau = (2*gamma - 1)/(gamma - 1)
    # (Cohen-Erez-ben-Avraham-Havlin 2000 PRL 85:4626 same exponent).
    gam = gamma_fit["alpha"]
    if math.isfinite(gam) and gam > 1.0:
        tau_theory_SF = (2 * gam - 1) / (gam - 1)
    else:
        tau_theory_SF = float("nan")

    # Attacks (only feasible on networks under ~1e5 nodes within time budget)
    if n_nodes < 80_000:
        atk_targ = attack_curves(g, "targeted", seed=1)
        atk_rand = attack_curves(g, "random", seed=2)
    else:
        atk_targ, atk_rand = {"skipped": True}, {"skipped": True}

    return {
        "name": name,
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "mean_degree": 2 * n_edges / max(1, n_nodes),
        "gamma_fit": gamma_fit,
        "percolation": perc,
        "tau_theory_SF_from_gamma": tau_theory_SF,
        "sweep_p": p_grid.tolist(),
        "sweep_smax": sweep["s_max_mean"].tolist(),
        "sweep_var": sweep["s_max_var"].tolist(),
        "attack_targeted": atk_targ,
        "attack_random": atk_rand,
    }


# ============================================================
# Main
# ============================================================
def main() -> int:
    t0 = time.time()
    results: Dict = {
        "class": "scale_free_percolation_class",
        "date": "2026-05-25",
        "agent": "Wave 2B sub-agent",
        "positive_control": {},
        "datasets": {},
        "fss_BA": {},
        "verdict": {},
    }

    # 0. Positive control
    results["positive_control"] = positive_control_pareto()

    # 1. BA simulated (small-medium for speed in 90 min budget)
    log.info("=== D1: BA simulated ===")
    p_grid_dense = np.linspace(0.02, 0.40, 20)
    g_ba = load_ba(20_000, m=3)
    results["datasets"]["BA_N20000_m3"] = analyze_network(
        g_ba, "BA_N20000_m3", n_reps=8, p_grid=p_grid_dense
    )

    # 2. CAIDA AS (real)
    log.info("=== D2: CAIDA AS ===")
    caida_path = DATA / "caida-20260501.as-rel.txt.bz2"
    if caida_path.exists():
        g_caida = load_caida(caida_path)
        # CAIDA can be ~75k nodes -> moderate; use fewer reps
        results["datasets"]["CAIDA_AS_20260501"] = analyze_network(
            g_caida, "CAIDA_AS_20260501", n_reps=4, p_grid=p_grid_dense
        )
    else:
        log.warning("CAIDA file not present; skip")

    # 3. GitHub follow network
    log.info("=== D3: GitHub MUSAE ===")
    gh_edges = DATA / "git_web_ml" / "musae_git_edges.csv"
    if gh_edges.exists():
        g_gh = load_github(gh_edges)
        results["datasets"]["GitHub_MUSAE"] = analyze_network(
            g_gh, "GitHub_MUSAE", n_reps=4, p_grid=p_grid_dense
        )
    else:
        log.warning("GitHub edges file not present; skip")

    # 4. FSS collapse on BA family
    log.info("=== M3: FSS collapse on BA ===")
    results["fss_BA"] = fss_collapse_BA(
        sizes=[2_000, 5_000, 10_000, 20_000],
        m=3,
        p_grid=np.linspace(0.04, 0.32, 12),
        n_reps=4,
    )

    # 4b. Lattice control — 2D square lattice (textbook tau = 187/91 ~= 2.055)
    log.info("=== D4: 2D square-lattice control ===")
    L = 200  # 40k nodes
    g_lat = nx.grid_2d_graph(L, L)
    # relabel to ints for our union-find
    g_lat = nx.convert_node_labels_to_integers(g_lat)
    p_grid_lat = np.linspace(0.40, 0.60, 12)  # bond pc(2D-square) = 0.5
    results["datasets"]["2D_square_lattice_L200"] = analyze_network(
        g_lat, "2D_square_lattice_L200", n_reps=4, p_grid=p_grid_lat
    )

    # 4c. Erdős-Rényi null — random graph with matched <k>
    log.info("=== D5: Erdős-Rényi null ===")
    g_er = nx.gnm_random_graph(20_000, 60_000,
                                seed=int(RNG.integers(0, 1 << 30)))
    # ER pc = 1/<k> with bond percolation; <k>=6 => pc=1/6
    results["datasets"]["ER_N20000_E60000"] = analyze_network(
        g_er, "ER_N20000_E60000", n_reps=4, p_grid=np.linspace(0.05, 0.35, 12)
    )

    # 5. Verdict synthesis
    # Labels: SF candidates we want to test; controls used as reference.
    SF_DATASETS = {"BA_N20000_m3", "CAIDA_AS_20260501", "GitHub_MUSAE"}
    CONTROL_DATASETS = {"2D_square_lattice_L200", "ER_N20000_E60000"}
    LATTICE_TAU_LO, LATTICE_TAU_HI = 2.00, 2.20  # 2D Ising / lattice tau = 187/91 ~ 2.055
    KS_OK = 0.20  # max tolerable KS on tau' fit; above this fit is unreliable

    verdict = {}
    for name, d in results["datasets"].items():
        gam = d["gamma_fit"]["alpha"]
        gam_ks = d["gamma_fit"]["ks"]
        tau_prime = d["percolation"]["tau_prime"]
        tau_ks = d["percolation"]["tau_ks"]
        tau_th = d["tau_theory_SF_from_gamma"]
        # Scale-free: gamma in [2.0, 3.5] AND degree-fit KS reasonably small
        is_sf = (
            math.isfinite(gam)
            and 2.0 <= gam <= 3.5
            and math.isfinite(gam_ks)
            and gam_ks < 0.10
        )
        # tau' meaningful only if KS within tolerance
        tau_reliable = math.isfinite(tau_prime) and math.isfinite(tau_ks) and tau_ks < KS_OK
        if tau_reliable:
            distinct = tau_prime < LATTICE_TAU_LO or tau_prime > LATTICE_TAU_HI
        else:
            distinct = None  # unreliable fit
        role = "SF_candidate" if name in SF_DATASETS else (
            "control" if name in CONTROL_DATASETS else "unknown")
        verdict[name] = {
            "role": role,
            "gamma": gam,
            "gamma_ks": gam_ks,
            "is_scale_free": bool(is_sf),
            "tau_prime": tau_prime,
            "tau_ks": tau_ks,
            "tau_reliable": bool(tau_reliable),
            "tau_theory_SF_Cohen": tau_th,
            "tau_distinct_from_lattice": distinct,
        }
    results["verdict"] = verdict

    # SF datasets: must be SF (otherwise FAIL).
    sf_class_confirmed = all(
        verdict[n]["is_scale_free"] for n in SF_DATASETS if n in verdict
    )
    # Are reliable SF tau' values distinct from the lattice band?
    sf_tau_reliable_distinct = [
        verdict[n]["tau_distinct_from_lattice"]
        for n in SF_DATASETS
        if n in verdict and verdict[n]["tau_reliable"]
    ]
    # Control sanity: lattice should show tau' near 2.055 (we'll just record it).
    lat_tau = verdict.get("2D_square_lattice_L200", {}).get("tau_prime", float("nan"))
    er_tau = verdict.get("ER_N20000_E60000", {}).get("tau_prime", float("nan"))

    if not sf_class_confirmed:
        decision = (
            "FAIL: SF candidates do not all sit in gamma in [2.0, 3.5] with KS<0.10"
        )
    elif not sf_tau_reliable_distinct:
        decision = (
            "INCONCLUSIVE: no SF dataset gave a reliable tau' (KS too high); "
            "MERGE-vs-SPLIT undecidable on cluster-tau axis alone"
        )
    elif all(sf_tau_reliable_distinct):
        decision = (
            f"SPLIT: SF cluster tau' outside lattice band [2.00,2.20] "
            f"(lattice control tau'={lat_tau:.3f}); class is mechanistically distinct"
        )
    elif not any(sf_tau_reliable_distinct):
        decision = (
            "MERGE: SF tau' overlaps lattice band -> fold into percolation_connectivity"
        )
    else:
        decision = "MIXED: SF tau' partially distinct; KEEP-with-caveats"
    # Strengthen with attack-asymmetry signature: SF networks should have
    # fragility ratio (f_c^random / f_c^targeted) much greater than 1; lattices
    # and ER do not.
    def fragility(d):
        t = d.get("attack_targeted", {})
        r = d.get("attack_random", {})
        if "skipped" in t or "skipped" in r:
            return None
        tc, rc = t.get("fc"), r.get("fc")
        if tc and tc > 0 and rc is not None:
            return rc / tc
        return None
    frag = {n: fragility(d) for n, d in results["datasets"].items()}
    results["fragility_ratios"] = frag
    sf_fragility = [frag[n] for n in SF_DATASETS if frag.get(n) is not None]
    ctrl_fragility = [frag[n] for n in CONTROL_DATASETS if frag.get(n) is not None]
    if sf_fragility and ctrl_fragility:
        sf_mean = float(np.mean(sf_fragility))
        ctrl_mean = float(np.mean(ctrl_fragility))
        results["fragility_signature"] = {
            "SF_mean": sf_mean,
            "control_mean": ctrl_mean,
            "ratio_SF_over_control": sf_mean / max(ctrl_mean, 1e-9),
        }
    results["decision"] = decision
    log.info("DECISION: %s", decision)

    # Persist
    out_path = HERE / "results.json"

    def safe(o):
        if isinstance(o, (np.ndarray,)):
            return o.tolist()
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        if isinstance(o, dict):
            return {k: safe(v) for k, v in o.items()}
        if isinstance(o, list):
            return [safe(v) for v in o]
        if isinstance(o, float) and not math.isfinite(o):
            return None
        return o

    with open(out_path, "w") as f:
        json.dump(safe(results), f, indent=2, default=str)
    with open(HERE / "verdict.txt", "w") as f:
        f.write(decision + "\n")
    log.info("wrote %s and verdict.txt (wall %.1fs)", out_path, time.time() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
