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
power-law distribution, so this module uses `scipy.optimize.curve_fit` on the
mean curve (not a sample distribution) and returns parameters + residual R^2.

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
  number near the floor blows up under log. Curve_fit with sensible bounds
  and an initial guess derived from the data is empirically more stable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import curve_fit

__all__ = [
    "LearningCurveResult",
    "fit_learning_curve",
    "power_law_with_floor",
]


def power_law_with_floor(C: np.ndarray, A: float, alpha: float, L_inf: float) -> np.ndarray:
    """Chinchilla / Kaplan functional form: L(C) = A * C^(-alpha) + L_inf.

    Vectorized over C. Used as the model for `curve_fit`.
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
        alpha_se: Standard error on alpha from the curve_fit covariance.
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
        If None, derived from data: L_inf0 = 0.9 * min(loss);
        alpha0 = 0.3; A0 fitted from the smallest-C point.
    max_nfev : int
        Hard cap on Levenberg-Marquardt function evaluations.

    Returns
    -------
    LearningCurveResult

    Notes
    -----
    * Filters non-finite and non-positive entries before fitting.
    * If fewer than 4 valid points remain, returns `error="too_few_points"`.
    * If curve_fit raises (ill-conditioned / max_nfev hit), the error string
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

    # Build initial guess from the data
    if initial_guess is None:
        # Step 1: estimate L_inf as slightly below the minimum loss
        L_min = float(L.min())
        L_inf0 = max(L_inf_bounds[0] + 1e-6, 0.95 * L_min)
        if L_min > 1e-3:
            L_inf0 = min(L_inf0, L_min - 1e-3)
        L_inf0 = float(np.clip(L_inf0, L_inf_bounds[0], L_inf_bounds[1] - 1e-6))

        # Step 2: estimate alpha via OLS on log(L - L_inf0) vs log(C).
        # This is far more accurate than blind alpha0=0.3 when curves span
        # several orders of magnitude in C.
        residual = L - L_inf0
        good = residual > 0
        if good.sum() >= 2:
            logC = np.log(C[good])
            logR = np.log(residual[good])
            slope, intercept = np.polyfit(logC, logR, 1)
            alpha0 = float(np.clip(-slope, alpha_bounds[0] + 1e-4, alpha_bounds[1] - 1e-4))
            A0 = float(np.exp(intercept))
        else:
            alpha0 = 0.3
            i_small = int(np.argmin(C))
            A0 = max(1e-6, (float(L[i_small]) - L_inf0) * (float(C[i_small]) ** alpha0))
        A0 = float(np.clip(A0, A_bounds[0], A_bounds[1]))
        initial_guess = (A0, alpha0, L_inf0)

    lo = [A_bounds[0], alpha_bounds[0], L_inf_bounds[0]]
    hi = [A_bounds[1], alpha_bounds[1], L_inf_bounds[1]]

    try:
        popt, pcov = curve_fit(
            power_law_with_floor,
            C,
            L,
            p0=initial_guess,
            bounds=(lo, hi),
            max_nfev=max_nfev,
        )
    except Exception as exc:  # noqa: BLE001 — curve_fit raises various
        return LearningCurveResult(
            name=name,
            n_points=n,
            C_range=(C_min, C_max),
            error=f"curve_fit_failed: {type(exc).__name__}: {exc}",
        )

    A_hat, alpha_hat, L_inf_hat = (float(p) for p in popt)
    # Standard errors from covariance diagonal (if positive-definite)
    try:
        perr = np.sqrt(np.maximum(np.diag(pcov), 0.0))
        A_se, alpha_se, L_inf_se = (float(p) for p in perr)
    except Exception:  # noqa: BLE001
        A_se = alpha_se = L_inf_se = None

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
    )
