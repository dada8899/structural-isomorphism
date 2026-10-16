"""Power-law learning-curve fitting for neural-network training dynamics.

Models the Chinchilla / Hoffmann-2022 / Kaplan-2020 functional form for LLM
training-loss vs compute (or vs model size / vs tokens):

    L(C) = A * C^(-alpha) + L_inf

where:
    C        = compute (FLOPs), or model size N (params), or tokens D
    L_inf    = irreducible loss floor (entropy of natural text)
    alpha    = scaling-law exponent (Chinchilla reports ~0.32-0.34 for C)
    A        = prefactor (sets the curve height)

This is **not** event-size power-law (which lives in `fit.py` via Clauset MLE).
Learning curves have a *floor* (L_inf) which cannot be modelled by a pure
power-law distribution. This module fits bounded nonlinear least squares on
the mean curve (not a sample distribution), with explicit scaling and an
analytic Jacobian, and returns parameters + residual R^2.

Reference
---------
- Kaplan, J. et al. (2020). "Scaling Laws for Neural Language Models." arXiv:2001.08361.
- Hoffmann, J. et al. (2022). "Training Compute-Optimal Large Language Models."
  arXiv:2203.15556 ("Chinchilla").
- Hestness, J. et al. (2017). "Deep Learning Scaling is Predictable, Empirically."
  arXiv:1712.00409 (the first systematic power-law learning-curve paper).

Design notes
------------
* This module is *standalone* — it does NOT register itself in
  `soc_pipeline.__init__` because event-size validate() pipelines should not
  silently pick up a function with mismatched semantics. Callers import it
  explicitly:

      >>> from soc_pipeline.learning_curve import fit_learning_curve
      >>> r = fit_learning_curve(compute, loss)
      >>> print(r.alpha, r.L_inf, r.R2)

* All fits are done in linear space on `L`, not in log-log space. Log-log
  fitting biases the floor `L_inf` toward zero because subtracting a small
  number near the floor blows up under log. Bounded least squares with explicit derivatives
  avoids finite-difference errors in badly scaled raw prefactors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import numpy as np
from scipy.optimize import least_squares

__all__ = [
    "LearningCurveResult",
    "fit_learning_curve",
    "power_law_with_floor",
]


def power_law_with_floor(C: np.ndarray, A: float, alpha: float, L_inf: float) -> np.ndarray:
    """Chinchilla / Kaplan functional form: L(C) = A * C^(-alpha) + L_inf.

    Vectorized over C. Also used for independent residual checks.
    """
    C = np.asarray(C, dtype=float)
    # guard against C <= 0
    with np.errstate(divide="ignore", invalid="ignore"):
        out = A * np.power(C, -alpha) + L_inf
    return out


@dataclass
class LearningCurveResult:
    """Result of a power-law learning-curve fit.

    Attributes:
        alpha: Scaling-law exponent (positive; L decreases as C^-alpha).
        A: Prefactor (sets the height of the power-law part).
        L_inf: Irreducible loss floor (asymptotic loss as C -> inf).
        alpha_se: Local linearized standard error, absent at an active bound or deficient rank.
        A_se: Standard error on A.
        L_inf_se: Standard error on L_inf.
        R2: Coefficient of determination on (loss, predicted loss).
        residual_rms: Root-mean-square residual on loss.
        n_points: Number of (C, loss) points fed to the fit.
        C_range: (C_min, C_max) used in the fit.
        name: Caller-provided label.
        error: If non-None, fit failed and other fields are unset.
        extra: Misc fields preserved for downstream JSON serialization.
    """

    alpha: float | None = None
    A: float | None = None
    L_inf: float | None = None
    alpha_se: float | None = None
    A_se: float | None = None
    L_inf_se: float | None = None
    R2: float | None = None
    residual_rms: float | None = None
    n_points: int = 0
    C_range: tuple[float, float] | None = None
    name: str = "curve"
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable view (for results.json output)."""
        d = {
            "name": self.name,
            "alpha": self.alpha,
            "A": self.A,
            "L_inf": self.L_inf,
            "alpha_se": self.alpha_se,
            "A_se": self.A_se,
            "L_inf_se": self.L_inf_se,
            "R2": self.R2,
            "residual_rms": self.residual_rms,
            "n_points": self.n_points,
            "C_range": list(self.C_range) if self.C_range else None,
        }
        if self.error:
            d["error"] = self.error
        if self.extra:
            d["extra"] = self.extra
        return d


def fit_learning_curve(
    compute: np.ndarray,
    loss: np.ndarray,
    *,
    name: str = "curve",
    alpha_bounds: tuple[float, float] = (0.01, 2.0),
    L_inf_bounds: tuple[float, float] = (0.0, 10.0),
    A_bounds: tuple[float, float] = (1e-12, 1e12),
    initial_guess: tuple[float, float, float] | None = None,
    max_nfev: int = 20000,
) -> LearningCurveResult:
    """Fit L(C) = A * C^(-alpha) + L_inf to (compute, loss) pairs.

    Parameters
    ----------
    compute : array-like
        Independent variable (FLOPs, params N, or tokens D). Must be > 0.
    loss : array-like
        Dependent variable (training/validation loss in nats or bits).
        Must be > 0 and (in practice) bounded above by some entropy.
    name : str
        Label echoed back in the result (model name / series id).
    alpha_bounds : (lo, hi)
        Bounds for the exponent. Chinchilla reports ~0.32-0.34; we widen to
        [0.01, 2.0] to cover Kaplan's L(N), L(D), L(C) variants and other
        domains.
    L_inf_bounds : (lo, hi)
        Bounds for the irreducible loss floor. Default [0, 10] covers
        natural-language entropies (~1.5-3 nats per token).
    A_bounds : (lo, hi)
        Bounds for the prefactor. Spans many orders of magnitude because
        C can be 1e15..1e25 FLOPs and L is O(1)..O(10).
    initial_guess : (A0, alpha0, L_inf0) or None
        If None, deterministic exponent starts are scaled from the smallest-C
        point. A supplied guess uses the same original physical bounds.
    max_nfev : int
        Hard cap on trust-region function evaluations per deterministic start.

    Returns
    -------
    LearningCurveResult

    Notes
    -----
    * Filters non-finite and non-positive entries before fitting.
    * If fewer than 4 valid points remain, returns `error="too_few_points"`.
    * If all bounded optimizer starts fail, the error string
      is captured and other fields are left None.
    """
    C = np.asarray(compute, dtype=float).ravel()
    L = np.asarray(loss, dtype=float).ravel()

    if C.shape != L.shape:
        return LearningCurveResult(
            name=name, error=f"shape_mismatch C={C.shape} L={L.shape}"
        )

    mask = np.isfinite(C) & np.isfinite(L) & (C > 0) & (L > 0)
    C, L = C[mask], L[mask]
    n = int(C.size)
    if n < 4:
        return LearningCurveResult(
            name=name,
            n_points=n,
            error="too_few_points (need >=4 after filtering)",
        )

    C_min = float(C.min())
    C_max = float(C.max())

    # Canonical order avoids reduction- and finite-difference dependence on
    # caller row order. Work in log(A), not the badly scaled raw prefactor.
    order = np.lexsort((L, C))
    C, L = C[order], L[order]
    log_C = np.log(C)
    log_C0 = math.fsum(float(value) for value in log_C) / n
    centered_log_C = log_C - log_C0
    try:
        if not (0 < A_bounds[0] < A_bounds[1]):
            raise ValueError("A bounds must be finite, positive and increasing")
        lower = np.array([math.log(A_bounds[0]), alpha_bounds[0], L_inf_bounds[0]])
        upper = np.array([math.log(A_bounds[1]), alpha_bounds[1], L_inf_bounds[1]])
        if not np.all(np.isfinite([lower, upper])) or np.any(lower >= upper):
            raise ValueError("all bounds must be finite and increasing")
        if C_min == C_max:
            raise ValueError("constant compute cannot identify a learning curve")
    except (ValueError, TypeError, OverflowError) as exc:
        return LearningCurveResult(
            name=name, n_points=n, C_range=(C_min, C_max),
            error=f"invalid_fit_domain: {exc}",
        )

    def prediction(parameters: np.ndarray) -> np.ndarray:
        log_A, alpha, floor = parameters
        # B=A*C0**(-alpha) is derived rather than separately bounded. Thus
        # the caller's original A bounds are preserved exactly in log space.
        power = np.exp(log_A - alpha * log_C0) * np.exp(-alpha * centered_log_C)
        return power + floor

    def residual(parameters: np.ndarray) -> np.ndarray:
        return prediction(parameters) - L

    def jacobian(parameters: np.ndarray) -> np.ndarray:
        log_A, alpha, _ = parameters
        power = np.exp(log_A - alpha * log_C0) * np.exp(-alpha * centered_log_C)
        return np.column_stack((power, -log_C * power, np.ones(n)))

    starts = []
    if initial_guess is not None:
        try:
            A0, alpha0, floor0 = initial_guess
            start = np.array([math.log(A0), alpha0, floor0], dtype=float)
            if not np.all(np.isfinite(start)) or np.any(start < lower) or np.any(start > upper):
                raise ValueError("initial guess is outside the declared bounds")
            starts.append(start)
        except (ValueError, TypeError, OverflowError) as exc:
            return LearningCurveResult(
                name=name, n_points=n, C_range=(C_min, C_max),
                error=f"invalid_initial_guess: {exc}",
            )
    else:
        floor0 = float(np.clip(0.95 * L.min(), lower[2], upper[2]))
        for alpha0 in (0.1, 0.3, 0.6, 1.0):
            alpha0 = float(np.clip(alpha0, lower[1], upper[1]))
            amplitude0 = max(float(L[0]) - floor0, np.finfo(float).tiny)
            log_A0 = float(np.clip(math.log(amplitude0) + alpha0 * log_C[0], lower[0], upper[0]))
            starts.append(np.array([log_A0, alpha0, floor0]))

    solutions = []
    failures = []
    for start in starts:
        try:
            result = least_squares(
                residual, start, jac=jacobian, bounds=(lower, upper),
                x_scale="jac", max_nfev=max_nfev,
                ftol=1e-12, xtol=1e-12, gtol=1e-12,
            )
            if result.success and np.all(np.isfinite(result.x)):
                solutions.append(result)
            else:
                failures.append(str(result.message))
        except Exception as exc:  # noqa: BLE001 — numerical failures are results
            failures.append(f"{type(exc).__name__}: {exc}")
    if not solutions:
        return LearningCurveResult(
            name=name, n_points=n, C_range=(C_min, C_max),
            error=f"least_squares_failed: {'; '.join(failures)}",
        )
    optimum = min(solutions, key=lambda item: math.fsum(float(v) ** 2 for v in item.fun))
    log_A_hat, alpha_hat, L_inf_hat = (float(value) for value in optimum.x)
    A_hat = math.exp(log_A_hat)

    # A covariance in raw (A, alpha, floor) coordinates can truncate the
    # prefactor direction and report spuriously tiny A_se. Diagnose and
    # calculate in the actual scaled optimizer coordinates; active-bound or
    # rank-deficient fits do not have an unconstrained Gaussian covariance.
    J = jacobian(optimum.x)
    singular_values = np.linalg.svd(J, compute_uv=False)
    cutoff = np.finfo(float).eps * max(J.shape) * singular_values[0]
    rank = int(np.count_nonzero(singular_values > cutoff))
    condition = float(singular_values[0] / singular_values[-1]) if singular_values[-1] > 0 else None
    boundaries = [
        label for index, label in enumerate(("A", "alpha", "L_inf"))
        if math.isclose(float(optimum.x[index]), float(lower[index]), rel_tol=1e-8, abs_tol=1e-8)
        or math.isclose(float(optimum.x[index]), float(upper[index]), rel_tol=1e-8, abs_tol=1e-8)
    ]
    A_se = alpha_se = L_inf_se = None
    covariance_status = "not_reported_active_bound" if boundaries else "not_reported_rank_deficient"
    if not boundaries and condition is not None and condition > 1 / math.sqrt(np.finfo(float).eps):
        covariance_status = "not_reported_ill_conditioned"
    if rank == 3 and not boundaries and condition is not None and condition <= 1 / math.sqrt(np.finfo(float).eps) and n > 3:
        _, sv, vt = np.linalg.svd(J, full_matrices=False)
        covariance = (vt.T / sv**2) @ vt
        covariance *= math.fsum(float(value) ** 2 for value in optimum.fun) / (n - 3)
        standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0.0))
        converted = [A_hat * standard_errors[0], standard_errors[1], standard_errors[2]]
        if np.all(np.isfinite(converted)):
            A_se, alpha_se, L_inf_se = (float(value) for value in converted)
            covariance_status = "local_linearization_only"
    diagnostics = {
        "estimator": "log-amplitude-analytic-jacobian-v1",
        "optimizer_parameterization": ["log_A", "alpha", "L_inf"],
        "original_A_bounds": list(A_bounds),
        "jacobian_rank": rank,
        "jacobian_condition": condition if condition is not None and math.isfinite(condition) else None,
        "active_bounds": boundaries,
        "bound_hit": bool(boundaries),
        "parameter_identifiability": (
            "weak_or_unestablished"
            if boundaries or rank < 3 or condition is None
            or condition > 1 / math.sqrt(np.finfo(float).eps)
            else "local_linearized_diagnostic_only"
        ),
        "covariance_status": covariance_status,
        "uncertainty_interpretation": "local diagnostic, not an inference eligibility claim",
    }

    L_pred = power_law_with_floor(C, A_hat, alpha_hat, L_inf_hat)
    resid = L - L_pred
    ss_res = float(np.sum(resid * resid))
    ss_tot = float(np.sum((L - L.mean()) ** 2))
    R2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None
    rms = float(np.sqrt(ss_res / n))

    return LearningCurveResult(
        name=name,
        alpha=alpha_hat,
        A=A_hat,
        L_inf=L_inf_hat,
        alpha_se=alpha_se,
        A_se=A_se,
        L_inf_se=L_inf_se,
        R2=R2,
        residual_rms=rms,
        n_points=n,
        C_range=(C_min, C_max),
        extra={"fit_diagnostics": diagnostics},
    )
