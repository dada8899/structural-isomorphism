"""F5 (W7-D / W5-A §4.4 b) — null distribution for the r_shape ratio.

The paper reports r_shape = 1.11 across 7 SOC systems as "excellent universal
collapse" (where < 2 is the borrowed threshold). Scholar reviewer flagged that
this threshold is from within-system finite-size scaling and does not transfer
cross-domain. There is no sampling distribution under the null hypothesis
"no real shared shape across systems".

This script implements the Gaussian-surrogate null suggested in scholar review
§4.4(b): under H0 = "no real shared shape", each system's log-y row is an
independent Gaussian fluctuation with the system's empirical mean and stddev
(but no cross-system alignment of the shape). We then row-center and compute
the same r_shape ratio on each surrogate. The empirical p_left = fraction of
null r_shape values <= observed measures whether the observed collapse is
unusually good vs the null.

  1. Load the 7 systems' rescaled (log-binned, x' = s/s*, y' = s*^{alpha-1} p̂(s))
     curves from v4/validation/soc-universal-collapse/results.json
  2. For each replicate, draw N_systems x N_bins independent N(mu_i, sigma_i^2)
     where mu_i, sigma_i are the empirical row mean and stddev of system i
  3. Row-center and recompute r_shape on each replicate
  4. Compare observed 1.11 to the null distribution

Also provided as a sanity check: a within-row column-shuffle null, which is
trivially degenerate (the r_shape statistic is invariant under independent
within-row column permutations), demonstrating *why* the Gaussian-surrogate
formulation is the relevant null.

Output:
  paper/figures/methodology/F5_r_shape_null.pdf / .png
  paper/figures/methodology/F5_r_shape_null_data.json

Usage:
    python paper/figures/methodology/generate_F5.py [--n-perm 10000] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

THIS = Path(__file__).resolve()
HERE = THIS.parent
ROOT = THIS.parents[3]
COLLAPSE_RESULTS = (
    ROOT / "v4" / "validation" / "soc-universal-collapse" / "results.json"
)
OUT_DATA = HERE / "F5_r_shape_null_data.json"
OUT_PDF = HERE / "F5_r_shape_null.pdf"
OUT_PNG = HERE / "F5_r_shape_null.png"


def build_matrix() -> tuple[np.ndarray, list[str], dict]:
    """Build the (n_systems, n_bins) log-y' matrix on a shared grid.

    Returns: (matrix, system_names, full_results_dict)
    """
    if not COLLAPSE_RESULTS.exists():
        raise FileNotFoundError(
            f"Required input missing: {COLLAPSE_RESULTS}. "
            "Run v4/validation/soc-universal-collapse/polish_collapse.py first."
        )

    data = json.loads(COLLAPSE_RESULTS.read_text())
    per_system = data.get("per_system", {})

    # Same procedure as collapse_quality(): collect (x_rescaled, y_rescaled),
    # log them, project onto a shared log-spaced x' grid.
    x_mins, x_maxs = [], []
    raw_xy = []
    names = []
    for name, info in per_system.items():
        if not info.get("ok"):
            continue
        r = info.get("rescale_99pctl") or {}
        x_r = np.asarray(r.get("x_rescaled", []), dtype=float)
        y_r = np.asarray(r.get("y_rescaled", []), dtype=float)
        keep = (y_r > 0) & np.isfinite(y_r) & (x_r > 0)
        if keep.sum() < 4:
            continue
        x = x_r[keep]
        y = y_r[keep]
        order = np.argsort(x)
        x = x[order]
        y = y[order]
        raw_xy.append((np.log(x), np.log(y)))
        names.append(name)
        x_mins.append(float(np.log(x).min()))
        x_maxs.append(float(np.log(x).max()))

    n_bins = 20
    log_lo = max(x_mins) if x_mins else 0.0
    log_hi = min(x_maxs) if x_maxs else 0.0
    if log_lo >= log_hi:
        log_lo = min(x_mins)
        log_hi = max(x_maxs)
    log_grid = np.linspace(log_lo, log_hi, n_bins)

    matrix = []
    sys_names = []
    for (log_x, log_y), name in zip(raw_xy, names):
        in_range = (log_grid >= log_x.min()) & (log_grid <= log_x.max())
        row = np.full(n_bins, np.nan)
        row[in_range] = np.interp(log_grid[in_range], log_x, log_y)
        matrix.append(row)
        sys_names.append(name)

    mat = np.asarray(matrix)
    return mat, sys_names, data


def compute_r_shape(mat: np.ndarray) -> float:
    """Compute the shape-normalized cross/within variance ratio.

    Mirrors the formula in v4/validation/soc-universal-collapse/polish_collapse.py
    (`collapse_quality`).

    IMPORTANT FINDING (F5 / W7-D): when the matrix has no NaNs and shape (S, B),
    this ratio is mathematically equal to ((B-1)/B) * (S/(S-1)) regardless of
    the underlying data. The "r_shape ~ 1.11" headline in the paper is the
    combinatorial constant for S=7, B=20 (= 19/20 * 7/6 = 133/120 ~ 1.1083).
    The F5 null computation reveals this near-degeneracy.
    """
    row_means = np.nanmean(mat, axis=1, keepdims=True)
    mat_shape = mat - row_means
    cross_var_shape = np.nanvar(mat_shape, axis=0, ddof=1)
    mean_curve = np.nanmean(mat_shape, axis=0)
    deviations = mat_shape - mean_curve
    within_var = np.nanvar(deviations, axis=1, ddof=1)
    cross = float(np.mean(cross_var_shape[np.isfinite(cross_var_shape)]))
    within = float(np.mean(within_var[np.isfinite(within_var)]))
    if within <= 0:
        return float("inf")
    return cross / within


def compute_shape_collapse_rmse(mat: np.ndarray) -> float:
    """Alternative shape-collapse statistic: RMSE of row-centered curves vs mean.

    After row-centering each system's log-y curve, compute the per-cell squared
    deviation from the cross-system mean shape, then RMSE across all (system,
    bin) cells. Smaller = better collapse. This is NOT identically equal to a
    combinatorial constant and DOES depend on the data.

    Returns: sqrt(mean((row_centered[i,j] - mean_curve[j])^2)) over finite cells.
    """
    row_means = np.nanmean(mat, axis=1, keepdims=True)
    mat_shape = mat - row_means
    mean_curve = np.nanmean(mat_shape, axis=0, keepdims=True)
    sq = (mat_shape - mean_curve) ** 2
    finite = sq[np.isfinite(sq)]
    if len(finite) == 0:
        return float("inf")
    return float(np.sqrt(np.mean(finite)))


def null_distribution_gaussian_surrogate_rmse(
    mat: np.ndarray, n_perm: int = 10000, seed: int = 42
) -> np.ndarray:
    """Generate null distribution of the shape-collapse RMSE statistic.

    Under H0 = "no shared shape", each system's log-y row is independent
    N(mu_i, sigma_i^2). We then compute compute_shape_collapse_rmse on each
    replicate.
    """
    rng = np.random.default_rng(seed)
    n_sys, n_bins = mat.shape
    row_mu = np.array([np.nanmean(mat[s]) for s in range(n_sys)])
    row_sigma = np.array([np.nanstd(mat[s], ddof=1) for s in range(n_sys)])
    finite_mask = np.isfinite(mat)

    r_null = np.zeros(n_perm)
    for i in range(n_perm):
        surr = np.full_like(mat, np.nan, dtype=float)
        for s in range(n_sys):
            idx = np.flatnonzero(finite_mask[s])
            if len(idx) < 2 or not np.isfinite(row_sigma[s]) or row_sigma[s] <= 0:
                surr[s, idx] = row_mu[s]
                continue
            surr[s, idx] = rng.normal(loc=row_mu[s], scale=row_sigma[s], size=len(idx))
        r_null[i] = compute_shape_collapse_rmse(surr)
    return r_null


def null_distribution_gaussian_surrogate(
    mat: np.ndarray, n_perm: int = 10000, seed: int = 42
) -> np.ndarray:
    """Generate r_shape null via independent-Gaussian-surrogate per system.

    Under H0 = "no shared shape", each system's log-y row is modeled as
    independent N(mu_i, sigma_i^2) where mu_i and sigma_i^2 are the empirical
    mean and variance of the actual log-y row. This preserves each system's
    location and dispersion in log-y space but destroys any column-aligned
    shape structure across systems.

    We then row-center and compute r_shape on each surrogate replicate.

    Note: the simpler within-row column-permutation null is degenerate — the
    r_shape statistic is mathematically invariant under independent within-row
    permutations of the column index (both numerator and denominator only
    involve per-row variances and per-column variances averaged over the
    column index, which are unchanged by column permutation). The Gaussian
    surrogate is the appropriate null for "cross-system shape alignment is
    unusually good".
    """
    rng = np.random.default_rng(seed)
    n_sys, n_bins = mat.shape
    # Per-system empirical mean and std (over the finite columns)
    row_mu = np.array([np.nanmean(mat[s]) for s in range(n_sys)])
    row_sigma = np.array([np.nanstd(mat[s], ddof=1) for s in range(n_sys)])
    # Mask of which cells are finite (only generate at those columns)
    finite_mask = np.isfinite(mat)

    r_null = np.zeros(n_perm)
    for i in range(n_perm):
        surr = np.full_like(mat, np.nan, dtype=float)
        for s in range(n_sys):
            idx = np.flatnonzero(finite_mask[s])
            if len(idx) < 2 or not np.isfinite(row_sigma[s]) or row_sigma[s] <= 0:
                surr[s, idx] = row_mu[s]
                continue
            surr[s, idx] = rng.normal(loc=row_mu[s], scale=row_sigma[s], size=len(idx))
        r_null[i] = compute_r_shape(surr)
    return r_null


def null_distribution_permutation_sanity(
    mat: np.ndarray, n_perm: int = 200, seed: int = 42
) -> np.ndarray:
    """Within-row column-permutation null — DEGENERATE, kept for sanity check.

    The r_shape statistic is invariant under independent within-row column
    permutations (proof: both the column-wise variance and the row-centered
    deviation variance are sums over (row, col) cells of the same set of
    deviations, and column permutation only reorders the sum).
    """
    rng = np.random.default_rng(seed)
    n_sys, n_bins = mat.shape
    r_null = np.zeros(n_perm)
    for i in range(n_perm):
        shuffled = mat.copy()
        for s in range(n_sys):
            row = shuffled[s]
            finite_idx = np.flatnonzero(np.isfinite(row))
            if len(finite_idx) < 2:
                continue
            perm = rng.permutation(finite_idx)
            shuffled[s, finite_idx] = row[perm]
        r_null[i] = compute_r_shape(shuffled)
    return r_null


# Backwards-compat alias used by main() / tests
null_distribution = null_distribution_gaussian_surrogate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-perm", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    print(f"[F5] loading collapse matrix from {COLLAPSE_RESULTS.name}...")
    mat, names, data = build_matrix()
    n_sys, n_bins = mat.shape
    print(f"[F5] matrix shape: {mat.shape} systems: {names}")

    # Statistic A: paper's r_shape (combinatorial-constant artifact)
    r_obs = compute_r_shape(mat)
    combinatorial_constant = ((n_bins - 1) / n_bins) * (n_sys / (n_sys - 1))
    print(f"[F5] observed r_shape = {r_obs:.6f}")
    print(
        f"[F5] combinatorial constant ((B-1)/B)*(S/(S-1)) "
        f"= ({n_bins - 1}/{n_bins})*({n_sys}/{n_sys - 1}) = "
        f"{combinatorial_constant:.6f}"
    )
    r_shape_is_artifact = abs(r_obs - combinatorial_constant) < 0.02
    print(
        f"[F5] r_shape is combinatorial artifact: {r_shape_is_artifact} "
        f"(diff = {abs(r_obs - combinatorial_constant):.4f})"
    )

    # Statistic B: shape-collapse RMSE (data-dependent)
    rmse_obs = compute_shape_collapse_rmse(mat)
    print(f"[F5] observed shape-collapse RMSE = {rmse_obs:.4f}")

    # Null distribution on the RMSE statistic
    print(f"[F5] running {args.n_perm} Gaussian-surrogate null on RMSE...")
    r_null = null_distribution_gaussian_surrogate_rmse(
        mat, n_perm=args.n_perm, seed=args.seed
    )

    # Sanity: degenerate r_shape null (proves degeneracy)
    print("[F5] running 200-rep r_shape null (degenerate, for confirmation)...")
    r_shape_null = null_distribution_permutation_sanity(
        mat, n_perm=200, seed=args.seed
    )
    print(
        f"[F5] r_shape null: mean={r_shape_null.mean():.6f} "
        f"std={r_shape_null.std():.2e} "
        f"unique={len(np.unique(np.round(r_shape_null, 8)))}"
    )

    # RMSE p-values
    p_left = float((np.sum(r_null <= rmse_obs) + 1) / (len(r_null) + 1))
    p_right = float((np.sum(r_null >= rmse_obs) + 1) / (len(r_null) + 1))
    two_sided = float(min(1.0, 2 * min(p_left, p_right)))

    print(f"[F5] null RMSE mean = {r_null.mean():.4f}, std = {r_null.std():.4f}")
    print(f"[F5] p_left (RMSE_obs <= null) = {p_left:.4g}")
    print(f"[F5] p_right (RMSE_obs >= null) = {p_right:.4g}")
    print(f"[F5] two-sided p = {two_sided:.4g}")

    # Plot: two panels — (a) RMSE histogram with observed, (b) sanity r_shape null
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.4))

    ax = axes[0]
    ax.hist(
        r_null, bins=60, color="#9aa0a6", edgecolor="white", alpha=0.85,
        density=True, label=f"null (n={args.n_perm})",
    )
    ax.axvline(rmse_obs, color="#d62728", lw=2.2,
               label=f"observed RMSE = {rmse_obs:.3f}")
    ax.axvline(np.median(r_null), color="#1f77b4", lw=1.2, ls="--",
               alpha=0.85, label=f"null median = {np.median(r_null):.3f}")
    ax.set_xlabel("shape-collapse RMSE (log-y units, row-centered)")
    ax.set_ylabel("density")
    ax.set_title(
        "(a) Shape-collapse RMSE vs Gaussian-surrogate null\n"
        f"p_left = {p_left:.3g}, p_right = {p_right:.3g}"
    )
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    # Range hack for degenerate null
    width = max(0.001, 2 * abs(r_obs - combinatorial_constant) + 0.05)
    bins = np.linspace(combinatorial_constant - width,
                       combinatorial_constant + width, 30)
    ax.hist(
        r_shape_null, bins=bins, color="#9aa0a6", edgecolor="white", alpha=0.85,
        density=True, label="r_shape null (200 reps)",
    )
    ax.axvline(r_obs, color="#d62728", lw=2.2,
               label=f"observed r_shape = {r_obs:.4f}")
    ax.axvline(combinatorial_constant, color="#2ca02c", lw=1.6, ls=":",
               label=f"((B-1)/B)(S/(S-1)) = {combinatorial_constant:.4f}")
    ax.set_xlabel(r"r_shape (paper formula)")
    ax.set_ylabel("density")
    ax.set_title(
        "(b) Paper's r_shape statistic is a combinatorial artifact\n"
        f"null std = {r_shape_null.std():.2e}"
    )
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUT_PDF, bbox_inches="tight", dpi=140)
    plt.savefig(OUT_PNG, bbox_inches="tight", dpi=140)
    plt.close(fig)
    print(f"[F5] wrote {OUT_PDF}")
    print(f"[F5] wrote {OUT_PNG}")

    OUT_DATA.write_text(json.dumps({
        "n_perm": args.n_perm,
        "seed": args.seed,
        "matrix_shape": list(mat.shape),
        "systems": names,
        "r_shape_obs": float(r_obs),
        "combinatorial_constant_BminusBoverB_x_SoverSminus1": float(
            combinatorial_constant
        ),
        "r_shape_is_combinatorial_artifact": bool(r_shape_is_artifact),
        "r_shape_null_mean": float(r_shape_null.mean()),
        "r_shape_null_std": float(r_shape_null.std()),
        "rmse_obs": float(rmse_obs),
        "rmse_null_mean": float(r_null.mean()),
        "rmse_null_std": float(r_null.std()),
        "rmse_null_p5": float(np.percentile(r_null, 5)),
        "rmse_null_p95": float(np.percentile(r_null, 95)),
        "p_left_rmse": p_left,
        "p_right_rmse": p_right,
        "p_two_sided_rmse": two_sided,
        "key_finding": (
            "The paper's r_shape statistic (1.11 across 7 systems on 20 bins) "
            "is mathematically identical to ((B-1)/B)*(S/(S-1)) regardless of "
            "the underlying data — i.e. it does not distinguish real shape "
            "collapse from random Gaussian rows. We substitute the "
            "shape-collapse RMSE for a meaningful test."
        ),
    }, indent=2))
    print(f"[F5] wrote {OUT_DATA}")


if __name__ == "__main__":
    main()
