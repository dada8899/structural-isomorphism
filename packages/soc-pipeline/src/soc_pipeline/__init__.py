"""SOC pipeline — Clauset 2009 power-law fitting + null controls + LR tests.

Cross-domain self-organized criticality validation in 5 lines of code.

Example:
    >>> from soc_pipeline import fit_clauset_powerlaw, bootstrap_ci
    >>> result = fit_clauset_powerlaw(event_sizes, discrete=False)
    >>> ci = bootstrap_ci(event_sizes, n_boot=200)
    >>> print(f"alpha={result.alpha:.2f}  CI=[{ci.ci_low:.2f}, {ci.ci_high:.2f}]")
"""
from __future__ import annotations

__version__ = "0.1.0"

from .fit import FitResult, fit_clauset_powerlaw
from .bootstrap import BootstrapResult, bootstrap_ci
from .null_controls import NullCase, synthetic_null
from .lr_test import LRResult, vuong_lr_test
from .universal_collapse import CollapseResult, shape_normalized_collapse
from .omori import OmoriResult, fit_omori_p, bin_and_omori_from_events
from .b_value import b_to_clauset_alpha, fit_b_value
from .time_resolution import time_resolution_sweep
from .utils import empirical_ccdf, verdict_from_alpha_band

# Register pandas `.soc` accessor (side-effect import)
from . import pandas_accessor as _pandas_accessor  # noqa: F401
from .pandas_accessor import SocAccessor, Verdict, validate

__all__ = [
    "__version__",
    # fit
    "fit_clauset_powerlaw",
    "FitResult",
    # bootstrap
    "bootstrap_ci",
    "BootstrapResult",
    # null
    "synthetic_null",
    "NullCase",
    # LR test
    "vuong_lr_test",
    "LRResult",
    # collapse
    "shape_normalized_collapse",
    "CollapseResult",
    # omori
    "fit_omori_p",
    "OmoriResult",
    "bin_and_omori_from_events",
    # b-value
    "fit_b_value",
    "b_to_clauset_alpha",
    # time resolution
    "time_resolution_sweep",
    # utils
    "empirical_ccdf",
    "verdict_from_alpha_band",
    # pandas accessor
    "SocAccessor",
    "Verdict",
    "validate",
]
