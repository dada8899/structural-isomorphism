"""Fixed service entrypoint for an isolated root-owned worker release."""
import sys

sys.path.insert(0, "/opt/structural-first-answer/release")

from web.backend.research.local_answer_service import main

raise SystemExit(main())
