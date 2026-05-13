"""DEPRECATED — use the `guarded_llm` package instead.

This module is a thin compatibility shim re-exporting the legacy dataclass
schemas from `guarded_llm.schemas`. It is kept for one release cycle so
existing imports inside the V4 pipeline don't break. New code should import
from `guarded_llm` directly:

    from guarded_llm import Layer3CriticVerdict, Layer4Prediction, B3EnsembleReview

See `packages/guarded-llm/` for source / tests / docs.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "v4.lib.llm_schemas is deprecated; import from `guarded_llm` instead.",
    DeprecationWarning,
    stacklevel=2,
)

from guarded_llm.schemas import (  # noqa: E402, F401
    Layer3CriticVerdict,
    Layer4Prediction,
    B3EnsembleReview,
    validate,
)

__all__ = [
    "Layer3CriticVerdict",
    "Layer4Prediction",
    "B3EnsembleReview",
    "validate",
]
