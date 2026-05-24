#!/usr/bin/env python3
"""Phase 12 runner — universal-collapse polish.

Usage:
  PYTHONPATH=/Users/dadamini/Projects/structural-isomorphism/v4/lib \
    /Users/dadamini/Projects/structural-isomorphism/.venv/bin/python analyze.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import polish_collapse  # noqa: E402


def main() -> None:
    polish_collapse.run()


if __name__ == "__main__":
    main()
