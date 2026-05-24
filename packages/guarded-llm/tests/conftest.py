"""pytest config for guarded-llm tests."""

import sys
from pathlib import Path

# Make `import guarded_llm` work whether or not the package is pip-installed.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
