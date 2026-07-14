"""E2E test for POST /api/analyze/stream (M1.4 PR #2 wiring).

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
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
from tests.deep_report_fixtures import report_payload  # noqa: E402


def _full_report(*, fingerprint_revision=None, source_ref_id="kb:b_target"):
    payload = deepcopy(report_payload())
    payload["your_problem_breakdown"]["fingerprint_revision"] = fingerprint_revision
    payload["target_domain_intro"]["corresponding_phenomenon"][
        "source_ref_ids"
    ] = [source_ref_id]
    return payload


def test_confirmed_fingerprint_schema_accepts_and_normalizes():
    from api.analyze import _parse_fingerprint

    raw = json.dumps({
        "source_query": "为什么团队恢复很慢？",
        "summary": " 团队在冲突后恢复速度持续下降 ",
        "variables": [" 信任 ", "反馈延迟"],
        "constraints": ["两周内"],
        "unknowns": [],
        "revision": 2,
    })
    parsed = _parse_fingerprint(raw, "为什么团队恢复很慢？")
    assert parsed == {
        "summary": "团队在冲突后恢复速度持续下降",
        "variables": ["信任", "反馈延迟"],
        "constraints": ["两周内"],
        "unknowns": [],
        "revision": 2,
        "provenance": "user_confirmed",
    }


@pytest.mark.parametrize("payload", [
    {"source_query": "q", "summary": "too short", "variables": [], "extra": True},
    {"source_query": "wrong", "summary": "long enough summary", "variables": []},
    {"source_query": "q", "summary": "long enough summary", "variables": ["x" * 121]},
])
def test_confirmed_fingerprint_schema_rejects_drift(payload):
    from api.analyze import _parse_fingerprint
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _parse_fingerprint(json.dumps(payload), "q")
    assert exc.value.status_code == 422


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

    def relevance_score(self, _q, _pid):
        # Session #17 V3 — analyze.py now calls this for the unified scope
        # similarity口径. Return a high in-scope value so the existing
        # query-mode tests (real cross-domain questions) keep passing the
        # scope gate. The dedicated out-of-scope tests rely on the
        # deterministic scope_guard layer, not this floor.
        if _pid == "b_target":
            return 0.85
        return 0.0

    @staticmethod
    def _cosine(_a, _b):
        # Pair-mode similarity helper. Not exercised by these query-mode
        # tests, but present so the contract matches the real service.
        return 1.0


class _FakeLLM:
    """Minimal LLMService stand-in that streams a synthetic report."""

    FALLBACK_STRUCTURE_NAME_ZH = "结构分析暂不可用"
    FALLBACK_STRUCTURE_NAME_EN = "Structural analysis unavailable"
    model = "test/deep-report-model"

    async def rewrite_query(self, text, lang="zh"):
        return text

    async def stream_deep_analysis(
        self, a, b, *, source_refs, fingerprint=None, lang="zh"
    ):
        yield {"type": "progress", "received_chars": 1024}
        yield {
            "type": "done",
            "report": _full_report(
                fingerprint_revision=fingerprint.get("revision") if fingerprint else None,
                source_ref_id=source_refs[0].source_ref_id,
            ),
        }


class _ProtocolViolatingLLM:
    model = "test/protocol-violator"

    def __init__(self, variant: str):
        self.variant = variant

    async def stream_deep_analysis(
        self, a, b, *, source_refs, fingerprint=None, lang="zh"
    ):
        report = _full_report(
            fingerprint_revision=fingerprint.get("revision") if fingerprint else None
        )
        if self.variant == "error_then_done":
            yield {"type": "error", "code": "upstream_error", "retryable": False}
            yield {"type": "done", "report": report}
        elif self.variant == "duplicate_done":
            yield {"type": "done", "report": report}
            yield {"type": "done", "report": report}
        elif self.variant == "invalid_progress":
            yield {"type": "progress", "received_chars": "1024"}
            yield {"type": "done", "report": report}
        else:
            yield {"type": "unknown", "report": report}


class _ExplodingLLM:
    model = "test/exploding-stream"

    def __init__(self):
        self.calls = 0

    async def stream_deep_analysis(
        self, a, b, *, source_refs, fingerprint=None, lang="zh"
    ):
        self.calls += 1
        yield {"type": "progress", "received_chars": 512}
        raise RuntimeError("private provider detail must not escape")


class _OverclaimLLM:
    model = "test/deep-report-model"

    def __init__(self):
        self.calls = 0

    async def stream_deep_analysis(
        self, a, b, *, source_refs, fingerprint=None, lang="zh"
    ):
        self.calls += 1
        report = _full_report(
            fingerprint_revision=999,
            source_ref_id=source_refs[0].source_ref_id,
        )
        report["shared_structure"]["intuition"] = "迁移在所有案例中均有效。"
        yield {"type": "done", "report": report}


class _PairSearchService:
    def __init__(self):
        self.rows = {
            "a_source": {
                "id": "a_source",
                "name": "Source A",
                "domain": "source-domain",
                "type_id": "T1",
                "description": "Source description",
            },
            "b_target": {
                "id": "b_target",
                "name": "Target B",
                "domain": "target-domain",
                "type_id": "T2",
                "description": "Target description",
            },
        }

    def get_by_id(self, value):
        return self.rows.get(value)


class _ForgedCache:
    def __init__(self, report):
        self.report = report
        self.get_calls = 0
        self.put_calls = 0

    def get(self, *args, **kwargs):
        self.get_calls += 1
        return deepcopy(self.report)

    def put(self, *args, **kwargs):
        self.put_calls += 1


class _CountingLLM(_FakeLLM):
    def __init__(self):
        self.calls = 0

    async def stream_deep_analysis(self, *args, **kwargs):
        self.calls += 1
        async for chunk in super().stream_deep_analysis(*args, **kwargs):
            yield chunk


class _SpySearchService(_FakeSearchService):
    def __init__(self):
        super().__init__()
        self.get_calls = 0
        self.relevance_calls = 0

    def get_by_id(self, value):
        self.get_calls += 1
        return super().get_by_id(value)

    def relevance_score(self, query, value):
        self.relevance_calls += 1
        return super().relevance_score(query, value)


class _SpyCache:
    def __init__(self):
        self.get_calls = 0
        self.put_calls = 0

    def get(self, *args, **kwargs):
        self.get_calls += 1
        return None

    def put(self, *args, **kwargs):
        self.put_calls += 1


class _SpyStore:
    def __init__(self):
        self.create_calls = 0

    def create(self, **kwargs):
        self.create_calls += 1
        raise AssertionError("ReportStore.create must not run")


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
    # neutering the limiter between tests. `@tier_limit_decorator` (in
    # api/analyze.py) binds the limiter from `services.rate_limit`, while
    # the middleware uses its own `middleware.rate_limit` Limiter — reset
    # BOTH so a multi-request test file doesn't accumulate counts and trip
    # the (post-P1-1) 10/min anonymous floor.
    for _mod in ("services.rate_limit", "middleware.rate_limit"):
        try:
            import importlib
            _lim = getattr(importlib.import_module(_mod), "limiter", None)
            if _lim is not None:
                _lim.reset()
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


def _stream_text(client, payload, headers=None) -> str:
    """Collect a streaming response into one string."""
    headers = headers or {}
    with client.stream(
        "POST",
        "/api/analyze/stream",
        json=payload,
        headers=headers,
    ) as r:
        assert r.status_code == 200, r.text
        chunks = []
        for chunk in r.iter_text():
            chunks.append(chunk)
        return "".join(chunks)


# --------- tests --------- #


def test_sensitive_get_transport_is_retired_without_echoing_query(client):
    secret = "board-plan-do-not-log"
    response = client.get(
        "/api/analyze/stream",
        params={"b_id": "b_target", "text_a": secret, "anon_id": secret},
    )
    assert response.status_code == 410
    assert response.json()["error"] == "sensitive_get_retired"
    assert secret not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_share_url_ignores_forwarded_origin_and_pins_production_host(monkeypatch):
    from api.analyze import _build_share_url

    request = Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/analyze/stream",
        "raw_path": b"/api/analyze/stream",
        "query_string": b"",
        "root_path": "",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
        "headers": [
            (b"host", b"testserver"),
            (b"x-forwarded-host", b"attacker.invalid"),
            (b"x-forwarded-proto", b"http"),
        ],
    })

    monkeypatch.setenv("STRUCTURAL_ENV", "dev")
    assert _build_share_url(request, "r_ignored", "safe-token") == (
        "http://testserver/report/share/safe-token"
    )
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    assert _build_share_url(request, "r_ignored", "safe-token") == (
        "https://beta.structural.bytedance.city/report/share/safe-token"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"b_id": "b_target", "text_a": ""},
        {"b_id": "b_target", "text_a": "ok\u0000hidden"},
        {"b_id": "b_target", "text_a": ["not", "text"]},
        {"b_id": "b_target", "text_a": "x" * 8001},
        {"b_id": "b_target", "text_a": "valid", "unexpected": True},
        {"b_id": "b_target", "text_a": "valid", "persist": True},
        {"b_id": "b_target", "text_a": "valid", "a_id": "also-set"},
    ],
)
def test_stream_body_rejects_empty_malicious_overlong_and_wrong_types(client, payload):
    response = client.post("/api/analyze/stream", json=payload)
    assert response.status_code == 422


def test_pair_mode_rejects_same_id_before_lookup_init_llm_or_cost(
    client, monkeypatch
):
    search = _SpySearchService()
    effects = {"init": 0, "cost": 0}

    def forbidden(effect):
        def fail(*args, **kwargs):
            effects[effect] += 1
            raise AssertionError(f"{effect} must not run")

        return fail

    monkeypatch.setattr("main.app_state", {"search": search}, raising=False)
    monkeypatch.setattr("api.analyze._init", forbidden("init"))
    monkeypatch.setattr("api.analyze._llm", object())
    from services.cost_ledger import ledger

    monkeypatch.setattr(ledger, "charge", forbidden("cost"))
    response = client.post(
        "/api/analyze/stream",
        json={"a_id": "b_target", "b_id": "b_target"},
    )

    assert response.status_code == 422
    assert search.get_calls == 0
    assert effects == {"init": 0, "cost": 0}


@pytest.mark.parametrize("size", [2000, 2001, 8000])
def test_stream_body_accepts_shared_research_query_boundaries(size):
    from api.analyze import AnalyzeStreamRequest

    request = AnalyzeStreamRequest.model_validate({
        "b_id": "b_target",
        "text_a": "x" * size,
    })
    assert len(request.text_a or "") == size


def test_stream_body_rejects_8001_char_query_and_fingerprint():
    from api.analyze import AnalyzeStreamRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AnalyzeStreamRequest.model_validate({
            "b_id": "b_target",
            "text_a": "x" * 8001,
        })
    with pytest.raises(ValidationError):
        AnalyzeStreamRequest.model_validate({
            "b_id": "b_target",
            "text_a": "x" * 8000,
            "fingerprint": {
                "source_query": "x" * 8001,
                "summary": "long enough summary",
            },
        })


def test_stream_body_nfkc_normalizes_before_persistence(client, isolated):
    text = _stream_text(
        client,
        {
            "b_id": "b_target",
            "text_a": "ｔｅａｍｓ　ｓｐｌｉｔ",
            "persist": 1,
            "anon_id": "nfkc-owner",
        },
    )
    persisted = next(p for n, p in _parse_sse(text) if n == "persisted")
    assert isolated.get_by_id(persisted["id"])["query"] == "teams split"


def test_persist_off_emits_no_persisted_event(client, isolated):
    """persist=0 (default) — backward compat: no `persisted` event."""
    text = _stream_text(
        client,
        {"b_id": "b_target", "text_a": "why do teams fall apart"},
    )
    events = _parse_sse(text)
    names = [n for n, _ in events]
    assert "persisted" not in names
    assert "done" in names


def test_persist_on_emits_persisted_with_share_url(client, isolated):
    text = _stream_text(
        client,
        {
            "b_id": "b_target", "text_a": "why teams split",
            "persist": 1, "anon_id": "user-A",
        },
    )
    events = _parse_sse(text)
    names = [n for n, _ in events]
    assert "persisted" in names
    persisted_payload = next(p for n, p in events if n == "persisted")
    validation_payload = next(p for n, p in events if n == "report_validated")
    meta_payload = next(p for n, p in events if n == "meta")
    assert persisted_payload["id"].startswith("r_")
    share_token = urlsplit(persisted_payload["share_url"]).path.rsplit("/", 1)[-1]
    assert re.fullmatch(r"[0-9a-f]{32}", share_token)
    assert "share_token" not in persisted_payload
    assert persisted_payload["is_partial"] is False
    assert persisted_payload["generation_id"] == validation_payload["generation_id"]
    assert persisted_payload["report_sha256"] == validation_payload["report_sha256"]
    assert meta_payload["generation_id"] == validation_payload["generation_id"]
    assert meta_payload["source_binding"]["source_kb_id"] == "b_target"
    assert meta_payload["source_refs"][0]["record_id"] == "b_target"
    # `persisted` must come BEFORE `done` so clients see the share URL
    # in the same SSE flush as completion.
    assert names.index("persisted") < names.index("done")


def test_persisted_report_readable_via_share_endpoint(client, isolated):
    text = _stream_text(
        client,
        {
            "b_id": "b_target", "text_a": "test",
            "persist": 1, "anon_id": "user-A",
        },
    )
    events = _parse_sse(text)
    persisted = next(p for n, p in events if n == "persisted")

    # Now read it back via the share endpoint.
    share_token = urlsplit(persisted["share_url"]).path.rsplit("/", 1)[-1]
    r = client.get(f"/api/report/share/{share_token}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == persisted["id"]
    assert body["payload"]["shared_structure"]["name"] == "延迟反馈候选"
    assert body["payload"]["schema_version"] == "deep-analysis-report-v2"
    assert body["payload"]["report_boundary"]["mechanism_status"] == "not_verified"


def test_persisted_row_records_creator_anon(client, isolated):
    text = _stream_text(
        client,
        {
            "b_id": "b_target", "text_a": "test",
            "persist": 1, "anon_id": "user-X",
        },
    )
    persisted = next(p for n, p in _parse_sse(text) if n == "persisted")
    raw = isolated.get_by_id(persisted["id"])
    assert raw["creator_anon_id"] == "user-X"


# --------- P0-1 end-to-end: persist → /reports/mine → /report/{id} -------- #
#
# The reviewer (SESSION-17 usability P0-1/P0-3) reported that persisting a
# report and then calling /api/reports/mine with the SAME anon-id returned
# an empty list, and /api/report/{id} 404'd. These tests close that gap:
# they drive the FULL HTTP round-trip (persist via /api/analyze/stream →
# read back via /api/reports/mine AND /api/report/{id}) so any regression
# in the anon-id persist→list→get chain fails CI, not a live dogfood run.


def test_persist_then_listed_in_reports_mine_header_anon(client, isolated):
    """persist(X-Anon-Id=X) → /api/reports/mine (X-Anon-Id=X) lists it."""
    text = _stream_text(
        client,
        {
            "b_id": "b_target", "text_a": "teams split",
            "persist": 1, "anon_id": "review-anon-3",
        },
    )
    persisted = next(p for n, p in _parse_sse(text) if n == "persisted")

    r = client.get("/api/reports/mine", headers={"X-Anon-Id": "review-anon-3"})
    assert r.status_code == 200
    body = r.json()
    ids = [it["id"] for it in body["items"]]
    assert persisted["id"] in ids, "persisted report must appear in /reports/mine"


def test_persist_then_get_report_by_id_owner(client, isolated):
    """persist(X-Anon-Id=X) → /api/report/{id} with the same anon-id → 200."""
    text = _stream_text(
        client,
        {
            "b_id": "b_target", "text_a": "teams split",
            "persist": 1, "anon_id": "review-anon-3",
        },
    )
    persisted = next(p for n, p in _parse_sse(text) if n == "persisted")

    r = client.get(
        f"/api/report/{persisted['id']}",
        headers={"X-Anon-Id": "review-anon-3"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == persisted["id"]


def test_persist_via_body_anon_id_listed_in_reports_mine(client, isolated):
    """Body-only anon identity remains compatible with the report owner API."""
    text = _stream_text(
        client,
        {
            "b_id": "b_target", "text_a": "q",
            "persist": 1, "anon_id": "review-anon-q",
        },
    )
    persisted = next(p for n, p in _parse_sse(text) if n == "persisted")

    r = client.get("/api/reports/mine", headers={"X-Anon-Id": "review-anon-q"})
    assert r.status_code == 200
    ids = [it["id"] for it in r.json()["items"]]
    assert persisted["id"] in ids


def test_get_report_by_id_wrong_anon_is_404(client, isolated):
    """A different anon-id reading someone's report → 404 (not 403)."""
    text = _stream_text(
        client,
        {
            "b_id": "b_target", "text_a": "q",
            "persist": 1, "anon_id": "owner-anon",
        },
    )
    persisted = next(p for n, p in _parse_sse(text) if n == "persisted")

    r = client.get(
        f"/api/report/{persisted['id']}",
        headers={"X-Anon-Id": "someone-else"},
    )
    assert r.status_code == 404


# --------- P1-3: out-of-scope gate on /api/analyze/stream --------- #


def test_analyze_refuses_arithmetic_query(client, isolated):
    """"1+1=?" must NOT generate a report — emits a terminal `error`."""
    text = _stream_text(
        client,
        {"b_id": "b_target", "text_a": "1+1=?"},
    )
    events = _parse_sse(text)
    names = [n for n, _ in events]
    assert "error" in names
    assert "section" not in names, "off-topic query must not produce sections"
    err = next(p for n, p in events if n == "error")
    assert err["code"] == "out_of_scope"


def test_analyze_refuses_chitchat_query(client, isolated):
    text = _stream_text(
        client,
        {"b_id": "b_target", "text_a": "你好"},
    )
    events = _parse_sse(text)
    assert "error" in [n for n, _ in events]


def test_raw_oos_stops_before_init_kb_cache_llm_store_and_cost(
    client, monkeypatch
):
    search = _SpySearchService()
    cache = _SpyCache()
    store = _SpyStore()
    effects = {"init": 0, "llm": 0, "cost": 0}

    def forbidden(effect):
        def fail(*args, **kwargs):
            effects[effect] += 1
            raise AssertionError(f"{effect} must not run")

        return fail

    class ForbiddenLLM:
        model = "test/forbidden"

        async def stream_deep_analysis(self, *args, **kwargs):
            forbidden("llm")()
            yield  # pragma: no cover

    monkeypatch.setattr("main.app_state", {"search": search}, raising=False)
    monkeypatch.setattr("api.analyze._init", forbidden("init"))
    monkeypatch.setattr("api.analyze._cache", cache)
    monkeypatch.setattr("api.analyze._report_store", store)
    monkeypatch.setattr("api.analyze._llm", ForbiddenLLM())
    from services.cost_ledger import ledger

    monkeypatch.setattr(ledger, "charge", forbidden("cost"))
    events = _parse_sse(
        _stream_text(client, {"b_id": "b_target", "text_a": "1+1=?"})
    )

    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["code"] == "out_of_scope"
    assert search.get_calls == 0 and search.relevance_calls == 0
    assert cache.get_calls == 0 and cache.put_calls == 0
    assert store.create_calls == 0
    assert effects == {"init": 0, "llm": 0, "cost": 0}


def test_query_persist_zero_skips_cache_and_report_store(client, monkeypatch):
    cache = _SpyCache()
    store = _SpyStore()
    monkeypatch.setattr("api.analyze._cache", cache)
    monkeypatch.setattr("api.analyze._report_store", store)
    monkeypatch.setattr("api.analyze._llm", _FakeLLM())

    events = _parse_sse(_stream_text(
        client,
        {
            "b_id": "b_target",
            "text_a": "why do teams fall apart",
            "persist": 0,
        },
    ))

    assert "done" in [name for name, _ in events]
    assert cache.get_calls == 0 and cache.put_calls == 0
    assert store.create_calls == 0


@pytest.mark.parametrize(
    "variant",
    ["error_then_done", "duplicate_done", "invalid_progress", "unknown"],
)
def test_analyze_rejects_invalid_internal_llm_stream_protocol(
    client, isolated, monkeypatch, variant
):
    from api import analyze as analyze_api

    monkeypatch.setattr(
        analyze_api,
        "_llm",
        _ProtocolViolatingLLM(variant),
        raising=False,
    )
    text = _stream_text(
        client,
        {"b_id": "b_target", "text_a": "why teams recover slowly"},
    )
    events = _parse_sse(text)
    names = [name for name, _ in events]
    assert names.count("error") == 1
    assert not {"report_validated", "section", "persisted", "done"}.intersection(names)
    error = next(payload for name, payload in events if name == "error")
    assert error["code"] == "report_protocol_failed"


def test_analyze_converts_async_generator_exception_to_one_terminal_error(
    client, isolated, monkeypatch, caplog
):
    llm = _ExplodingLLM()
    monkeypatch.setattr("api.analyze._llm", llm)

    events = _parse_sse(_stream_text(
        client,
        {"b_id": "b_target", "text_a": "why teams recover slowly"},
    ))
    names = [name for name, _ in events]

    assert llm.calls == 2
    assert names.count("error") == 1
    assert not {"report_validated", "section", "persisted", "done"}.intersection(
        names
    )
    error = next(payload for name, payload in events if name == "error")
    assert error == {
        "code": "upstream_error",
        "message": "研究草案未通过证据与来源校验，系统没有发布任何半成品。",
        "retryable": True,
    }
    assert "private provider detail must not escape" not in caplog.text


def test_api_revalidates_service_output_before_publishing(client, monkeypatch):
    llm = _OverclaimLLM()
    monkeypatch.setattr("api.analyze._llm", llm)
    events = _parse_sse(_stream_text(
        client,
        {
            "b_id": "b_target",
            "text_a": "why do teams fall apart",
            "fingerprint": {
                "source_query": "why do teams fall apart",
                "summary": "teams recover more slowly after conflict",
                "variables": [],
                "constraints": [],
                "unknowns": [],
                "revision": 2,
            },
        },
    ))
    names = [name for name, _ in events]

    assert llm.calls == 2
    assert names.count("error") == 1
    assert not {"report_validated", "section", "persisted", "done"}.intersection(
        names
    )
    assert next(payload for name, payload in events if name == "error")[
        "code"
    ] == "report_validation_failed"


def test_forged_pair_cache_binding_forces_source_bound_live_regeneration(
    client, monkeypatch
):
    from api.analyze import _record_digest

    search = _PairSearchService()
    llm = _CountingLLM()
    forged = _full_report(source_ref_id="kb:invented")
    forged.update({
        "source_binding": {
            "source_kb_id": "a_source",
            "source_record_sha256": _record_digest(search.rows["a_source"]),
            "kb_artifact_id": "unverified-dev-artifact",
            "target_kind": "kb",
            "target_kb_id": "b_target",
            "query_binding": None,
            "fingerprint_sha256": None,
            "fingerprint_revision": None,
            "lang": "zh",
            "model_id": llm.model,
            "prompt_version": "deep-report-v2",
            "schema_version": "deep-analysis-report-v2",
        },
        "report_boundary": {
            "conclusion_status": "candidate_analogy",
            "mechanism_status": "not_verified",
            "independent_review": "not_recorded",
            "literature_status": "not_checked",
        },
        "source_refs": [{
            "source_ref_id": "kb:invented",
            "source_kind": "internal_kb",
            "record_id": "invented-record",
            "label": "Invented cache source",
            "limitations": "This cache row is not server-owned evidence.",
        }],
    })
    cache = _ForgedCache(forged)
    monkeypatch.setattr("main.app_state", {"search": search}, raising=False)
    monkeypatch.setattr("api.analyze._llm", llm)
    monkeypatch.setattr("api.analyze._cache", cache)

    events = _parse_sse(_stream_text(
        client,
        {"a_id": "a_source", "b_id": "b_target"},
    ))
    names = [name for name, _ in events]
    done = next(payload for name, payload in events if name == "done")

    assert cache.get_calls == 1
    assert llm.calls == 1
    assert names.count("report_validated") == 1 and names.count("done") == 1
    assert done["from_cache"] is False
    assert [ref["record_id"] for ref in done["report"]["source_refs"]] == [
        "a_source",
        "b_target",
    ]
    source_ref_ids = set(
        done["report"]["target_domain_intro"]["corresponding_phenomenon"][
            "source_ref_ids"
        ]
    )
    assert source_ref_ids == {"kb:a_source"}


@pytest.mark.parametrize(
    ("status", "expected_code", "expected_retryable"),
    [
        (400, "provider_request_rejected", False),
        (401, "provider_auth_failed", False),
        (403, "provider_auth_failed", False),
        (404, "provider_request_rejected", False),
        (408, "upstream_timeout", True),
        (429, "provider_rate_limited", True),
        (500, "upstream_error", True),
        (503, "upstream_error", True),
    ],
)
def test_deep_provider_http_errors_are_stable_non_leaking_and_retry_safe(
    status, expected_code, expected_retryable
):
    import httpx
    from services.llm_service import (
        _classify_llm_error,
        _is_retryable_llm_error,
    )

    request = httpx.Request("POST", "https://provider.invalid/private")
    response = httpx.Response(status, request=request)
    exc = httpx.HTTPStatusError(
        "secret upstream response body and token",
        request=request,
        response=response,
    )

    code = _classify_llm_error(exc)
    assert code == expected_code
    assert _is_retryable_llm_error(exc) is expected_retryable
    assert "secret" not in code and "provider.invalid" not in code


def test_deep_remote_protocol_error_is_retryable_but_local_protocol_error_is_not():
    import httpx
    from services.llm_service import (
        _classify_llm_error,
        _is_retryable_llm_error,
    )

    remote = httpx.RemoteProtocolError("secret partial upstream response")
    local = httpx.LocalProtocolError("secret client request defect")

    assert _classify_llm_error(remote) == "upstream_error"
    assert _is_retryable_llm_error(remote) is True
    assert _classify_llm_error(local) == "upstream_error"
    assert _is_retryable_llm_error(local) is False
    assert "secret" not in _classify_llm_error(remote)


def test_analyze_retries_remote_protocol_interruption_and_fails_atomically(
    client, isolated, monkeypatch
):
    import httpx
    from api import analyze as analyze_api
    from services import llm_service

    class InterruptedClient:
        def __init__(self):
            self.calls = 0

        def stream(self, *args, **kwargs):
            self.calls += 1
            raise httpx.RemoteProtocolError("secret partial provider response")

    interrupted = InterruptedClient()
    service = llm_service.LLMService()
    service.api_key = "test-only-key"
    monkeypatch.setattr(llm_service, "_get_http_client", lambda: interrupted)
    monkeypatch.setattr(analyze_api, "_llm", service, raising=False)

    events = _parse_sse(_stream_text(
        client,
        {"b_id": "b_target", "text_a": "why teams recover slowly"},
    ))
    names = [name for name, _ in events]
    error = next(payload for name, payload in events if name == "error")

    assert interrupted.calls == 2
    assert names.count("error") == 1
    assert not {"report_validated", "section", "persisted", "done"}.intersection(
        names
    )
    assert error == {
        "code": "upstream_error",
        "message": "研究草案未通过证据与来源校验，系统没有发布任何半成品。",
        "retryable": True,
    }


def test_deep_provider_attempt_has_wall_clock_deadline_before_browser(monkeypatch):
    import asyncio
    import httpx
    from services import llm_service
    from services.deep_report import SourceRef

    observed = {}

    class SlowResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            await asyncio.sleep(1)
            yield "data: [DONE]"

    class SlowClient:
        def stream(self, *args, **kwargs):
            observed["timeout"] = kwargs["timeout"]
            return SlowResponse()

    production_timeout = llm_service.DEEP_REPORT_ATTEMPT_TIMEOUT_SECONDS
    monkeypatch.setattr(llm_service, "_get_http_client", lambda: SlowClient())
    monkeypatch.setattr(llm_service, "DEEP_REPORT_ATTEMPT_TIMEOUT_SECONDS", 0.01)
    service = llm_service.LLMService()
    service.api_key = "test-only-key"
    source_ref = SourceRef(
        source_ref_id="kb:b_target",
        source_kind="internal_kb",
        record_id="b_target",
        label="Target phenomenon",
        limitations="Internal candidate only.",
    )

    async def collect():
        return [
            chunk
            async for chunk in service.stream_deep_analysis(
                {
                    "id": "b_target",
                    "name": "Target phenomenon",
                    "domain": "test",
                    "type_id": "T",
                    "description": "Target description",
                },
                {
                    "id": "__query__",
                    "name": "Question",
                    "domain": "test",
                    "type_id": "unknown",
                    "description": "Why do teams recover slowly?",
                },
                source_refs=[source_ref],
                fingerprint=None,
                lang="zh",
            )
        ]

    chunks = asyncio.run(collect())
    assert chunks == [{
        "type": "error",
        "code": "upstream_timeout",
        "retryable": True,
    }]
    assert isinstance(observed["timeout"], httpx.Timeout)
    assert observed["timeout"].read == 0.01
    assert 110 <= production_timeout <= 120
    assert production_timeout * 2 < 300


def test_deep_prompt_separates_source_evidence_from_comparison_provenance():
    from services.deep_report import SourceRef, build_deep_report_prompt

    source_ref = SourceRef(
        source_ref_id="kb:a_source",
        source_kind="internal_kb",
        record_id="a_source",
        label="Source A",
        limitations="Internal candidate only.",
    )
    target_ref = SourceRef(
        source_ref_id="kb:b_target",
        source_kind="internal_kb",
        record_id="b_target",
        label="Target B",
        limitations="Comparison target only.",
    )
    prompt = build_deep_report_prompt(
        {
            "id": "a_source",
            "name": "Source A",
            "domain": "d1",
            "type_id": "T1",
            "description": "Source description",
        },
        {
            "id": "b_target",
            "name": "Target B",
            "domain": "d2",
            "type_id": "T2",
            "description": "Target description",
        },
        source_refs=[source_ref, target_ref],
        fingerprint=None,
        lang="zh",
    )
    context_json = prompt.split("CONTEXT_JSON:\n", 1)[1].split(
        "\n\nOUTPUT_JSON_SCHEMA:\n", 1
    )[0]
    role = json.loads(context_json)["source_role_contract"]

    assert role == {
        "source_record_ref_id": "kb:a_source",
        "comparison_target_ref_id": "kb:b_target",
        "comparison_target_is_evidence": False,
    }
    assert "must never be cited as source evidence" in prompt


# --------- P0-2: daily LLM budget circuit breaker --------- #


def test_analyze_over_budget_emits_friendly_error(client, isolated, monkeypatch):
    """When the daily cap is hit, /api/analyze/stream emits a friendly
    `error` event (code budget_exceeded), NOT a crash and NOT a report."""
    # Drive a tiny positive cap and exhaust it. Use the real singleton the
    # endpoint imports. reset() AFTER setenv so the date/count are fresh.
    monkeypatch.setenv("STRUCTURAL_LLM_DAILY_CALL_CAP", "1")
    from services.cost_ledger import ledger
    ledger.reset()
    assert ledger.snapshot()["cap"] == 1
    # First request consumes the single allowed slot (real generation).
    first = _stream_text(
        client,
        {"b_id": "b_target", "text_a": "why teams split"},
    )
    assert "section" in [n for n, _ in _parse_sse(first)]
    # Second request is over budget.
    text = _stream_text(
        client,
        {"b_id": "b_target", "text_a": "why teams split again"},
    )
    events = _parse_sse(text)
    err = next((p for n, p in events if n == "error"), None)
    assert err is not None, "over-budget request must emit an error event"
    assert err["code"] == "budget_exceeded"
    assert "section" not in [n for n, _ in events]
    ledger.reset()
