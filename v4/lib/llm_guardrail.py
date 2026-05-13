"""DEPRECATED — use the `guarded_llm` package instead.

This module is a thin compatibility shim re-exporting the same symbols
from `guarded_llm.guardrail`. It is kept for one release cycle so existing
imports inside the V4 pipeline don't break. New code should import from
`guarded_llm` directly:

    from guarded_llm import guardrailed_llm_call, state_machine_fix, validate_json

See `packages/guarded-llm/` for source / tests / docs.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "v4.lib.llm_guardrail is deprecated; import from `guarded_llm` instead.",
    DeprecationWarning,
    stacklevel=2,
)

from guarded_llm.guardrail import (  # noqa: E402, F401
    state_machine_fix,
    validate_json,
    guardrailed_llm_call,
    GuardrailResult,
)

__all__ = [
    "state_machine_fix",
    "validate_json",
    "guardrailed_llm_call",
    "GuardrailResult",
]
