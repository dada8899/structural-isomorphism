"""pytest configuration for v4 sanity tests.

Sets up sys.path so:
  - `from soc_pipeline import ...` works without install
  - `from sanity_helpers import ...` works in test modules
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "v4" / "lib"))
sys.path.insert(0, str(Path(__file__).parent))  # allows `from sanity_helpers import ...`
