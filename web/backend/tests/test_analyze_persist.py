"""E2E test for /api/analyze/stream?persist=1 (M1.4 PR #2 wiring).

We mock LLMService.stream_deep_analysis so the test runs in milliseconds
and never hits OpenRouter. The mock yields a synthetic 9-section report.

Verifies the wiring between analyze.py and report_store.py:
  - persist=0 (default) → NO `persisted` event (backward compat)
  - persist=1 + complete report → `persisted` event with id + share_url
  - cache hit + persist=1 → `persisted` event still emitted
  - the persisted row is readable via /api/report/share/{token}
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


_FULL_REPORT = {
    "shared_structure": {"name": "Cascade", "intuition": "..."},
    "your_problem_breakdown": {"summary": "..."},
    "target_domain_intro": {"domain_name": "Physics"},
    "structural_mapping": {"rationale": "..."},
    "borrowable_insights": ["i1"],
    "how_to_combine": {"steps": ["s1"]},
    "research_directions": {"literature_status": "..."},
    "risks_and_limits": {"failure_cases": []},
    "action_plan": {"immediate_actions": []},
}


# --------- mocks --------- #


class _FakeSearchService:
    """Drop-in for SearchService used in analyze.py."""

    def __init__(self):
        self.kb_size = 1
        self.idx_by_id = {"b_target": 0}
        import numpy as np
        self._embeddings = np.array([[1.0, 0.0, 0.0]], dtype=float)

    def get_by_id(self, _id):
        if _id == "b_target":
            return {
                "id": "b_target", "name": "Target phenomenon",
                "domain": "test", "type_id": "T",
                "description": "Target description",
            }
        return None

    def encode_query(self, _q):
        import numpy as np
        return np.array([1.0, 0.0, 0.0], dtype=float)


class _FakeLLM:
    """Minimal LLMService stand-in that streams a synthetic report."""

    FALLBACK_STRUCTURE_NAME_ZH = "结构分析暂不可用"
    FALLBACK_STRUCTURE_NAME_EN = "Structural analysis unavailable"

    async def rewrite_query(self, text, lang="zh"):
        return text

    async def stream_deep_analysis(self, a, b, similarity, user_query=None, lang="zh"):
        # Emit one chunk per section, then a final done with the assembled report.
        for key, value in _FULL_REPORT.items():
            yield {"type": "section", "key": key, "data": value}
        yield {"type": "done", "report": _FULL_REPORT}


# --------- fixtures --------- #


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Wire fresh ReportStore + fake search + fake LLM into analyze.py / report.py."""
    from services.report_store import ReportStore
    from api import analyze as analyze_api
    from api import report as report_api

    fresh = ReportStore(tmp_path / "test_history.db")

    # Stub the lifespan-loaded search service.
    monkeypatch.setattr(
        analyze_api,
        "_cache",
        _NoopCache(),
        raising=False,
    )
    monkeypatch.setattr(analyze_api, "_llm", _FakeLLM(), raising=False)
    monkeypatch.setattr(analyze_api, "_report_store", fresh, raising=False)
    # Skip the cache (force live generation) for the default path.

    # The endpoint reads app_state["search"] — patch by registering
    # a tiny module-level dict.
    monkeypatch.setattr("main.app_state", {"search": _FakeSearchService()}, raising=False)

    # Share the same store with /api/report so the round-trip works.
    monkeypatch.setattr(report_api, "_store", fresh, raising=False)

    # Defeat the @tier_limit_decorator on /api/analyze/stream for tests by
    # neutering the limiter. Avoids "60/minute" noise in the suite.
    try:
        from middleware.rate_limit import limiter
        limiter.reset()
    except Exception:
        pass

    return fresh


class _NoopCache:
    def get(self, *a, **kw):
        return None

    def put(self, *a, **kw):
        return None


@pytest.fixture
def app(isolated, monkeypatch):
    """Sub-app exposing analyze + report routers (no search lifespan).

    monkeypatch is used (not direct attribute assignment) so the patch
    is rolled back at fixture teardown — leaking auth state between
    tests was causing 7 unrelated test_auth_* failures in full-suite
    runs (caught session-#16 wrap-up).
    """
    from api import analyze, report

    def _allow_all(_request):
        return "free"  # any non-None tier passes

    # Patch the symbol the analyze module already imported (the
    # function reference is bound at import time, so patching
    # services.auth.verify_api_token alone is not enough — patch
    # api.analyze.verify_api_token where it's actually called).
    monkeypatch.setattr("api.analyze.verify_api_token", _allow_all)

    a = FastAPI()
    a.include_router(analyze.router, prefix="/api")
    a.include_router(report.router, prefix="/api")
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


# --------- helpers --------- #


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """Decode SSE block text into (event_name, payload) tuples."""
    out = []
    for block in re.split(r"\n\n", text):
        block = block.strip()
        if not block:
            continue
        m = re.match(r"event:\s*(\S+)\s*\ndata:\s*(.+)$", block, re.DOTALL)
        if not m:
            continue
        try:
            data = json.loads(m.group(2))
        except json.JSONDecodeError:
            data = {"_raw": m.group(2)}
        out.append((m.group(1), data))
    return out


def _stream_text(client, url, headers=None) -> str:
    """Collect a streaming response into one string."""
    headers = headers or {}
    with client.stream("GET", url, headers=headers) as r:
        chunks = []
        for chunk in r.iter_text():
            chunks.append(chunk)
        return "".join(chunks)


# --------- tests --------- #


def test_persist_off_emits_no_persisted_event(client, isolated):
    """persist=0 (default) — backward compat: no `persisted` event."""
    text = _stream_text(
        client,
        "/api/analyze/stream?b_id=b_target&text_a=why%20do%20teams%20fall%20apart",
    )
    events = _parse_sse(text)
    names = [n for n, _ in events]
    assert "persisted" not in names
    assert "done" in names


def test_persist_on_emits_persisted_with_share_url(client, isolated):
    text = _stream_text(
        client,
        "/api/analyze/stream?b_id=b_target&text_a=why%20teams%20split&persist=1",
        headers={"X-Anon-Id": "user-A"},
    )
    events = _parse_sse(text)
    names = [n for n, _ in events]
    assert "persisted" in names
    persisted_payload = next(p for n, p in events if n == "persisted")
    assert persisted_payload["id"].startswith("r_")
    assert len(persisted_payload["share_token"]) == 32
    assert persisted_payload["share_url"].endswith(
        "/report/share/" + persisted_payload["share_token"]
    )
    assert persisted_payload["is_partial"] is False
    # `persisted` must come BEFORE `done` so clients see the share URL
    # in the same SSE flush as completion.
    assert names.index("persisted") < names.index("done")


def test_persisted_report_readable_via_share_endpoint(client, isolated):
    text = _stream_text(
        client,
        "/api/analyze/stream?b_id=b_target&text_a=test&persist=1",
        headers={"X-Anon-Id": "user-A"},
    )
    events = _parse_sse(text)
    persisted = next(p for n, p in events if n == "persisted")

    # Now read it back via the share endpoint.
    r = client.get(f"/api/report/share/{persisted['share_token']}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == persisted["id"]
    assert body["payload"]["shared_structure"]["name"] == "Cascade"
    assert body["payload"]["action_plan"]["immediate_actions"] == []


def test_persisted_row_records_creator_anon(client, isolated):
    text = _stream_text(
        client,
        "/api/analyze/stream?b_id=b_target&text_a=test&persist=1",
        headers={"X-Anon-Id": "user-X"},
    )
    persisted = next(p for n, p in _parse_sse(text) if n == "persisted")
    raw = isolated.get_by_id(persisted["id"])
    assert raw["creator_anon_id"] == "user-X"
