"""Session #17 V3.3 — /api/search out-of-scope gate.

Before V3.3 the search endpoint had NO scope check: "今天天气怎么样" still
returned 12 candidates. /ask and /analyze both gate; search now matches
that contract.

The gate runs the deterministic services.scope_guard BEFORE touching
app_state["search"], so the refusal path needs no search service at all.
For the in-scope path we register a tiny fake search service.

Run:
    PYTHONPATH=web/backend:. .venv/bin/python -m pytest \
        web/backend/tests/test_search_scope_gate.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class _FakeSearchService:
    """Returns one same-domain + one cross-domain result with V2/V3 fields."""

    def search(self, _query, top_k=12):
        return [
            {
                "id": "p1", "name": "用户留存衰减", "domain": "组织管理",
                "type_id": "06", "description": "...",
                "score": 0.8, "relevance": 0.84,
                "cross_domain": False, "surface_domain": "组织管理",
            },
            {
                "id": "p4", "name": "磁滞损耗", "domain": "电气工程",
                "type_id": "06", "description": "...",
                "score": 0.5, "relevance": 0.69,
                "cross_domain": True, "surface_domain": "组织管理",
            },
        ]


@pytest.fixture
def client(monkeypatch):
    from api import search as search_api

    monkeypatch.setattr(
        "main.app_state", {"search": _FakeSearchService()}, raising=False
    )
    # Neuter the rate limiter so a multi-request test file doesn't trip it.
    for _mod in ("services.rate_limit", "middleware.rate_limit"):
        try:
            import importlib
            _lim = getattr(importlib.import_module(_mod), "limiter", None)
            if _lim is not None:
                _lim.reset()
        except Exception:
            pass

    app = FastAPI()
    app.include_router(search_api.router, prefix="/api")
    return TestClient(app)


# --------- V3.3 — out-of-scope refusal --------- #


@pytest.mark.parametrize("q", [
    "1+1=?",
    "你好",
    "今天天气怎么样",  # the canonical V3.3 bug example
])
def test_out_of_scope_query_returns_no_results(client, q):
    r = client.post("/api/search", json={"query": q})
    assert r.status_code == 200
    body = r.json()
    assert body["out_of_scope"] is True
    assert body["count"] == 0
    assert body["results"] == []
    assert body["scope_reason"] in {"arithmetic", "chitchat", "trivia"}


def test_out_of_scope_response_shape_is_stable(client):
    """Refusal response keeps the same top-level keys as a normal one so
    the frontend can render uniformly."""
    r = client.post("/api/search", json={"query": "1+1=?"})
    body = r.json()
    for key in ("query", "results", "count", "assessment", "stats",
                "v2_pairs_for_top", "out_of_scope", "scope_reason"):
        assert key in body


# --------- in-scope path still works + carries V2 fields --------- #


def test_in_scope_query_returns_results_with_v2_fields(client):
    r = client.post("/api/search", json={"query": "用户留存率每月下降为什么"})
    assert r.status_code == 200
    body = r.json()
    assert body["out_of_scope"] is False
    assert body["count"] == 2
    for res in body["results"]:
        assert "relevance" in res
        assert "cross_domain" in res
        assert "surface_domain" in res


def test_in_scope_stats_carry_cross_domain_summary(client):
    r = client.post("/api/search", json={"query": "用户留存率每月下降为什么"})
    stats = r.json()["stats"]
    assert stats["surface_domain"] == "组织管理"
    assert stats["cross_domain_count"] == 1
    assert stats["same_domain_count"] == 1
