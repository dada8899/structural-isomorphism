"""pytest configuration for v4 sanity tests.

sys.path setup:
  - Repo root is prepended so `from v4.lib.llm_guardrail import ...` works
    (canonical dotted-path import for the deprecated shim modules).
  - `v4/tests/` is prepended so `from sanity_helpers import ...` works.
  - `v4/lib/` is APPENDED (not prepended) so tests can import the real
    non-shim modules (`embedding_bridge`, `embedding_finetune`,
    `multitest_correction`) via bare names. The append-order is critical:
    v4/lib/ also contains DEPRECATED shim modules (`soc_pipeline.py`,
    `llm_guardrail.py`, `llm_schemas.py`) which re-export from
    `packages/*`. If v4/lib were prepended, those shims would shadow the
    editable-installed real packages and break `from soc_pipeline import
    ...` with a self-import ImportError (the bug fixed in this PR).

    Tests that intentionally exercise the shim path (e.g.
    test_llm_guardrail.py) import via `v4.lib.llm_guardrail` directly
    instead of bare `import llm_guardrail`.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Prepend repo root for `from v4.lib.X import ...` imports.
sys.path.insert(0, str(REPO))

# Prepend tests dir for `from sanity_helpers import ...`.
sys.path.insert(0, str(Path(__file__).parent))

# Append v4/lib (NOT prepend) so editable real packages win over shims.
_v4_lib = str(REPO / "v4" / "lib")
if _v4_lib not in sys.path:
    sys.path.append(_v4_lib)
