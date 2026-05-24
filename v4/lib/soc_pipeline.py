"""DEPRECATED — use `soc_pipeline` package.

Historical entry point for the V4 SOC pipeline. The implementation has been
extracted into the standalone PyPI-ready package `soc-pipeline` (under
`packages/soc-pipeline/`).

To migrate:

    # before
    from v4.lib.soc_pipeline import fit_clauset_powerlaw

    # after
    pip install -e packages/soc-pipeline
    from soc_pipeline import fit_clauset_powerlaw

The wildcard re-export below preserves backward compatibility for any caller
that still imports from this path. The `fit_clauset_powerlaw` re-export from
the new package returns a `FitResult` dataclass; call `.to_dict()` to get the
legacy dict view used in V4 scripts.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "v4.lib.soc_pipeline is deprecated; install and import from `soc_pipeline` "
    "(packages/soc-pipeline) instead.",
    DeprecationWarning,
    stacklevel=2,
)

try:
    from soc_pipeline import (  # noqa: F401
        FitResult,
        bootstrap_ci,
        fit_clauset_powerlaw as _new_fit,
        synthetic_null,
        verdict_from_alpha_band,
    )
    from soc_pipeline.omori import (  # noqa: F401
        bin_and_omori_from_events,
        fit_omori_p as omori_from_aftershock_stack,
    )

    def fit_clauset_powerlaw(vals, name="values", discrete=False):
        """Legacy wrapper returning the old dict shape."""
        return _new_fit(vals, name=name, discrete=discrete).to_dict()

    def run_size_null_controls(seed: int = 42, n: int = 20_000):
        """Legacy wrapper around synthetic_null returning dict shape."""
        out = {}
        cases = synthetic_null(n=n, seed=seed)
        for k, case in cases.items():  # type: ignore[union-attr]
            out[k] = case.fit.to_dict()
        out["all_rejected"] = all(case.correctly_rejected for case in cases.values())  # type: ignore[union-attr]
        return out

    def bootstrap_alpha_ci(vals, n_boot=200, seed=42, discrete=False,
                            ci_pct=(2.5, 97.5)):
        """Legacy wrapper around bootstrap_ci returning dict shape."""
        r = bootstrap_ci(vals, n_boot=n_boot, seed=seed, discrete=discrete,
                         ci_pct=ci_pct)
        if r.error:
            return None
        return {
            "alpha_mean": r.alpha_mean,
            "alpha_median": r.alpha_median,
            "alpha_std": r.alpha_std,
            "ci_low": r.ci_low,
            "ci_high": r.ci_high,
            "n_boot_succeeded": r.n_boot_succeeded,
        }
except ImportError:
    # Package not installed yet — keep this module importable but no-op.
    pass
