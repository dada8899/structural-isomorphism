"""Public Analyze paths must not expose user outcome aggregates."""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.report_store import ReportStore  # noqa: E402


def test_public_count_and_card_compatibility_paths_are_removed():
    for removed in (
        "count_human_verified", "verified_isomorphisms",
        "stuck_structures", "insights_summary",
    ):
        assert not hasattr(ReportStore, removed)
    assert not (_BACKEND / "services" / "verified_isomorphisms.py").exists()


def test_analyze_source_has_no_human_aggregate_contract():
    source = (_BACKEND / "api" / "analyze.py").read_text(encoding="utf-8")
    assert "human_verified_count" not in source
    assert "human_verified_recent" not in source
    assert "human_verified_for" not in source
    assert "USER_RECORDED_OUTCOME" not in source


def test_analyze_frontend_has_no_human_aggregate_badge():
    source = (
        _BACKEND.parent / "frontend" / "assets" / "js" / "analyze.js"
    ).read_text(encoding="utf-8")
    assert "human_verified_count" not in source
    assert "cred-badge__chip--human" not in source
