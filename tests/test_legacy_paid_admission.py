"""Actual FastAPI handlers; only embedding/KB inputs and secret/log loaders
are fixture boundaries. No real credentials, provider HTTP, DB users or model.
"""
import asyncio
import importlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import types
import urllib.request
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web/backend"
sys.path.insert(0, str(BACKEND))


@pytest.fixture
def app_env(monkeypatch, tmp_path):
    import dotenv
    import logging_config
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(logging_config, "configure_logging", lambda *a, **k: None)
    monkeypatch.setenv("STRUCTURAL_ENV", "dev")
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key-never-sent")
    monkeypatch.setenv("AUTH_DATA_DIR", str(tmp_path / "auth"))
    # Embedding boundary only. SearchService.search/_fused_scores remain real.
    model = types.ModuleType("structural_isomorphism.model")
    model.load_model = lambda *a, **k: (_ for _ in ()).throw(AssertionError("unexpected model startup"))
    model.encode_texts = lambda *a, **k: (_ for _ in ()).throw(AssertionError("unexpected model startup"))
    monkeypatch.setitem(sys.modules, "structural_isomorphism.model", model)
    main = importlib.import_module("main")
    import numpy as np
    from services.search_service import SearchService
    from services.cache import MappingCache
    from schemas import CandidateMapping
    from api import analyze, mapping, search, phenomenon
    svc = SearchService.__new__(SearchService)
    svc.kb = [{"id": "p1", "name": "反馈候选", "domain": "控制", "type_id": "1", "description": "响应变化出现延迟反馈。"},
              {"id": "p2", "name": "排队候选", "domain": "运营", "type_id": "1", "description": "流程在负载变化后出现等待。"}]
    svc.kb_by_id = {r["id"]: r for r in svc.kb}
    svc.idx_by_id = {r["id"]: i for i, r in enumerate(svc.kb)}
    svc._embeddings = np.array([[1., 0.], [0., 1.]])
    svc._bm25 = None
    svc._struct_by_id = {}
    svc._encode_query_cached = lambda query: np.array([[1., 0.]])
    monkeypatch.setitem(main.app_state, "search", svc)
    monkeypatch.setitem(main.app_state, "artifact", {"artifact_id": "synthetic-artifact"})
    from services.rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", False)  # unrelated test throttling
    monkeypatch.setattr(mapping, "_cache", MappingCache(tmp_path / "mapping.jsonl", validator=lambda x: CandidateMapping.model_validate(x).model_dump(mode="json")))
    monkeypatch.setattr(analyze, "_cache", MappingCache(tmp_path / "analysis.jsonl", schema_version=analyze._DEEP_CACHE_SCHEMA))
    monkeypatch.setattr(analyze, "_report_store", None)
    monkeypatch.setattr(search, "get_pairs_for", lambda *a, **k: [])
    monkeypatch.setattr(search, "has_pairs", lambda *a, **k: False)
    monkeypatch.setattr(phenomenon, "get_pairs_for", lambda *a, **k: [])
    from services import translation
    monkeypatch.setattr(translation, "_TRANSLATE_CACHE", {})
    # TestClient has no lifespan context: do not load models/user stores/mail.
    from fastapi.testclient import TestClient
    client = TestClient(main.app, follow_redirects=False)
    yield main, client, svc, tmp_path
    client.close()


@pytest.fixture
def no_sender(monkeypatch, app_env):
    import httpx
    def fail(*a, **k): raise AssertionError("unexpected provider/network preparation")
    spies = [Mock(side_effect=fail) for _ in range(3)]
    monkeypatch.setattr(httpx, "AsyncClient", spies[0])
    monkeypatch.setattr(urllib.request, "urlopen", spies[1])
    monkeypatch.setattr(socket.socket, "connect", spies[2])
    yield spies
    assert all(v.call_count == 0 for v in spies)


def assert_unavailable(response):
    assert response.status_code == 503, response.text
    assert response.json()["code"] == "FEATURE_UNAVAILABLE", response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "text/event-stream" not in response.headers["content-type"]
    assert response.json()["retryable"] is False


@pytest.fixture
def no_preparation(monkeypatch, app_env):
    _, _, svc, _ = app_env
    def fail(*a, **k): raise AssertionError("pure validation reached generation/retrieval preparation")
    checks = []
    for name in ("get_by_id", "search", "encode_query"):
        spy = Mock(side_effect=fail); monkeypatch.setattr(svc, name, spy); checks.append(spy)
    for module_name, names in {
        "ask": ("_get_llm", "AskOrchestrator"), "analyze": ("_init", "_query_binding", "_analyze_stream_response"),
        "method_search": ("run_method_search",), "stress_test": ("run_stress_test",),
        "diagnose": ("run_diagnosis",), "struct_lint": ("lint_document", "StreamingResponse"),
        "synthesize": ("_get_llm", "_canonical_top_results"),
    }.items():
        module = importlib.import_module("api." + module_name)
        for name in names:
            spy = Mock(side_effect=fail); monkeypatch.setattr(module, name, spy); checks.append(spy)
    yield checks
    assert all(spy.call_count == 0 for spy in checks)


@pytest.mark.parametrize("path,body,status", [
    ("/api/ask/stream", {"query": "x"*8001}, 422),
    ("/api/ask/stream", {"query": "2 + 2 等于多少"}, 422),
    ("/api/analyze/stream", {"b_id": "p2", "text_a": "2 + 2 等于多少"}, 422),
    ("/api/method/apply", {"method": "2 + 2 等于多少，请直接告诉我答案"}, 422),
    ("/api/stress-test", {"claim": "2 + 2 等于多少，请直接告诉我答案"}, 422),
    ("/api/diagnose", {"situation": "2 + 2 等于多少，请直接告诉我答案"}, 422),
    ("/api/struct-lint", {"document": "   \n"}, 400),
    ("/api/struct-lint/stream", {"document": "   \n"}, 400),
    ("/api/struct-lint", {"document": "x"*20001}, 400),
    ("/api/struct-lint/stream", {"document": "x"*20001}, 400),
    ("/api/struct-lint", {"document": "2 + 2 等于多少，请直接告诉我答案"}, 422),
    ("/api/struct-lint/stream", {"document": "2 + 2 等于多少，请直接告诉我答案"}, 422),
    ("/api/synthesize", {"query": "反馈延迟", "results": []}, 422),
    ("/api/synthesize/stream", {"query": "反馈延迟", "results": []}, 422),
])
def test_pure_validation_is_http_before_deny_or_preparation(app_env, no_sender, no_preparation, path, body, status):
    _, client, _, _ = app_env
    reply = client.post(path, json=body)
    assert reply.status_code == status, reply.text
    assert "text/event-stream" not in reply.headers["content-type"]
    assert "event: meta" not in reply.text and "event: done" not in reply.text


@pytest.mark.parametrize("path,body", [
    ("/api/ask/stream", {"query": "2 + 2 等于多少"}),
    ("/api/analyze/stream", {"b_id": "p2", "text_a": "2 + 2 等于多少"}),
])
def test_invalid_caller_identity_precedes_oos(app_env, no_sender, no_preparation, monkeypatch, path, body):
    _, client, _, _ = app_env
    monkeypatch.setenv("STRUCTURAL_API_TOKENS", "free:synthetic-valid-caller")
    invalid = client.post(path, json=body, headers={"Authorization": "Bearer synthetic-invalid-caller"})
    assert invalid.status_code == 401, invalid.text
    valid = client.post(path, json=body, headers={"Authorization": "Bearer synthetic-valid-caller"})
    assert valid.status_code == 422, valid.text


def test_search_oos_remains_local_even_when_rewrite_requested(app_env, no_sender, no_preparation):
    _, client, _, _ = app_env
    reply = client.post("/api/search", json={"query": "2 + 2 等于多少", "rewrite": True})
    assert reply.status_code == 200
    assert reply.json()["out_of_scope"] is True and reply.json()["results"] == []


@pytest.mark.parametrize("endpoint", ["synthesize", "synthesize_stream"])
def test_direct_synthesis_empty_results_retains_400_before_model(app_env, no_sender, no_preparation, endpoint):
    from api import synthesize
    from starlette.requests import Request
    from fastapi import HTTPException
    import inspect
    # Internal/direct callers can bypass Pydantic; preserve this old cheap check.
    data = synthesize.SynthesizeRequest.model_construct(query="反馈延迟", results=[], rewritten_query=None, lang="zh")
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1234)})
    with pytest.raises(HTTPException) as error:
        asyncio.run(inspect.unwrap(getattr(synthesize, endpoint))(request, data))
    assert error.value.status_code == 400


@pytest.mark.parametrize("path,body", [
    ("/api/ask/stream", {"query": "为什么反馈系统出现延迟响应"}),
    ("/api/analyze/stream", {"a_id": "p1", "b_id": "p2", "persist": 0}),
    ("/api/mapping", {"a_id": "p1", "b_id": "p2"}),
    ("/api/mapping/stream", {"a_id": "p1", "b_id": "p2"}),
    ("/api/mapping/stream", {"text_a": "为什么反馈出现延迟", "b_id": "p2"}),
    ("/api/synthesize", {"query": "反馈出现延迟", "results": [{"id": "p1"}]}),
    ("/api/synthesize/stream", {"query": "反馈出现延迟", "results": [{"id": "p1"}]}),
    ("/api/search", {"query": "反馈出现延迟", "rewrite": True}),
    ("/api/search/assess", {"query": "反馈出现延迟"}),
    ("/api/method/apply", {"method": "研究响应延迟与负反馈控制的关系"}),
    ("/api/stress-test", {"claim": "该流程可能类似控制系统反馈"}),
    ("/api/struct-lint", {"document": "我们需要检验流程中的延迟反馈机制及其适用边界"}),
    ("/api/struct-lint/stream", {"document": "我们需要检验流程中的延迟反馈机制及其适用边界"}),
    ("/api/diagnose", {"situation": "流程出现延迟反馈，尚未确认原因。"}),
])
def test_actual_api_rejects_before_sse_and_model_preparation(app_env, no_sender, path, body):
    main, client, _, _ = app_env
    assert_unavailable(client.post(path, json=body))


@pytest.mark.parametrize("production", [False, True])
def test_phase_seven_routes_and_direct_helpers_refuse(app_env, no_sender, monkeypatch, production):
    main, client, _, _ = app_env
    monkeypatch.setattr(main, "_IS_PROD", production)
    from errors import LegacyPaidUnavailable
    paths = ["redteam", "deep-report", "analogy", "analogy-detail", "analogy-detail/stream", "analogy/stream", "memo/stream"]
    for path in paths: assert_unavailable(client.post("/phase/api/" + path, json={}))
    with pytest.raises(LegacyPaidUnavailable): asyncio.run(main._phase_urlopen_json(object(), 1))
    for name in ("phase_api_analogy_detail_stream", "phase_api_analogy_stream", "phase_api_memo_stream"):
        with pytest.raises(LegacyPaidUnavailable): asyncio.run(getattr(main, name)(None))


def test_real_local_search_and_english_original_still_work(app_env, no_sender):
    _, client, svc, _ = app_env
    expected = svc.search("反馈出现延迟", top_k=5)
    reply = client.post("/api/search", json={"query": "反馈出现延迟", "rewrite": False, "top_k": 5})
    assert reply.status_code == 200, reply.text
    assert [r["id"] for r in reply.json()["results"]] == [r["id"] for r in expected]
    reply = client.get("/api/phenomenon/p1?lang=en")
    assert reply.status_code == 200, reply.text
    assert reply.json()["phenomenon"]["name"] == "反馈候选"
    assert reply.headers["X-Translation-Policy"] == "cache-only; original-on-miss"
    for path in ("/privacy", "/auth/login", "/api/diagnose/states"):
        assert client.get(path).status_code == 200, path


def test_source_bound_public_mapping_cache_is_read_only(app_env, no_sender):
    _, client, svc, tmp = app_env
    from api import mapping
    from services.llm_service import LLMService
    cached = LLMService()._fallback_mapping(svc.kb[0], svc.kb[1], .5)
    from services.cache import mapping_source_binding
    frozen = mapping_source_binding(svc.kb[0], svc.kb[1], "synthetic-artifact")
    mapping._cache.put_bound("p1", "p2", cached, binding=frozen, lang="zh")
    original = (tmp / "mapping.jsonl").read_bytes()
    from services.cache import MappingCache
    from schemas import CandidateMapping
    mapping._cache = MappingCache(tmp / "mapping.jsonl", validator=lambda v: CandidateMapping.model_validate(v).model_dump(mode="json"))
    reply = client.post("/api/mapping", json={"a_id": "p1", "b_id": "p2"})
    assert reply.status_code == 200, reply.text
    assert reply.json()["from_cache"] is True
    stream = client.post("/api/mapping/stream", json={"a_id": "p1", "b_id": "p2"})
    assert stream.status_code == 200 and '"from_cache": true' in stream.text
    assert (tmp / "mapping.jsonl").read_bytes() == original
    assert_unavailable(client.post("/api/mapping", json={"a_id": "p1", "b_id": "p2", "lang": "en"}))


@pytest.mark.parametrize("route", ["/api/mapping", "/api/mapping/stream"])
@pytest.mark.parametrize("change", ["source_name", "source_description", "target_name", "target_description", "artifact"])
def test_mapping_frozen_disk_binding_rejects_changes_before_and_after_restart(app_env, no_sender, route, change):
    main, client, svc, tmp = app_env
    from api import mapping
    from services.cache import MappingCache, mapping_source_binding
    from services.llm_service import LLMService
    from schemas import CandidateMapping
    candidate = LLMService()._fallback_mapping(svc.kb[0], svc.kb[1], .5)
    frozen = mapping_source_binding(svc.kb[0], svc.kb[1], main.app_state["artifact"]["artifact_id"])
    mapping._cache.put_bound("p1", "p2", candidate, binding=frozen, lang="zh")
    body = {"a_id": "p1", "b_id": "p2"}
    assert client.post(route, json=body).status_code == 200
    original = (tmp / "mapping.jsonl").read_bytes()
    if change == "artifact":
        main.app_state["artifact"]["artifact_id"] = "different-artifact"
    else:
        side, field = change.split("_", 1)
        svc.kb[0 if side == "source" else 1][field] = "Changed current record"
    assert_unavailable(client.post(route, json=body))
    mapping._cache = MappingCache(tmp / "mapping.jsonl", validator=lambda v: CandidateMapping.model_validate(v).model_dump(mode="json"))
    assert_unavailable(client.post(route, json=body))
    assert (tmp / "mapping.jsonl").read_bytes() == original
    row = json.loads(original)
    assert row["binding"] == frozen  # no read-time signing or overwrite


@pytest.mark.parametrize("route", ["/api/mapping", "/api/mapping/stream"])
def test_unbound_legacy_mapping_row_is_not_retroactively_signed(app_env, no_sender, route):
    _, client, svc, tmp = app_env
    from api import mapping
    from services.cache import MappingCache
    from services.llm_service import LLMService
    from schemas import CandidateMapping
    candidate = LLMService()._fallback_mapping(svc.kb[0], svc.kb[1], .5)
    mapping._cache.put("p1", "p2", candidate, lang="zh")
    original = (tmp / "mapping.jsonl").read_bytes()
    body = {"a_id": "p1", "b_id": "p2"}
    assert_unavailable(client.post(route, json=body))
    mapping._cache = MappingCache(tmp / "mapping.jsonl", validator=lambda v: CandidateMapping.model_validate(v).model_dump(mode="json"))
    assert_unavailable(client.post(route, json=body))
    assert "binding" not in json.loads(original)
    assert (tmp / "mapping.jsonl").read_bytes() == original


def test_deep_cache_exact_artifact_binding_before_sse_and_no_new_persist(app_env, no_sender):
    _, client, svc, tmp = app_env
    from api import analyze
    from services.deep_report import GeneratedDeepReportV2, SourceBinding, bind_deep_report
    spec = importlib.util.spec_from_file_location("legacy_fixture_data", BACKEND / "tests/deep_report_fixtures.py")
    fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
    payload = fixture.report_payload()
    payload["your_problem_breakdown"]["fingerprint_revision"] = None
    payload = json.loads(json.dumps(payload).replace("kb-source", "kb:p1"))
    binding = SourceBinding(source_kb_id="p1", source_record_sha256=analyze._record_digest(svc.kb[0]), kb_artifact_id="synthetic-artifact", target_kind="kb", target_kb_id="p2", query_binding=None,
        fingerprint_sha256=None, fingerprint_revision=None, lang="zh", model_id=analyze.ASK_MODEL, prompt_version="deep-report-v2", schema_version="deep-analysis-report-v2")
    refs = [analyze._source_ref(svc.kb[0], lang="zh"), analyze._source_ref(svc.kb[1], lang="zh", target=True)]
    cached = bind_deep_report(GeneratedDeepReportV2.model_validate(payload), source_binding=binding, source_refs=refs, source_record=svc.kb[0]).model_dump(mode="json")
    key = analyze._cache_identity(source_record_sha256=analyze._record_digest(svc.kb[0]), target_record_sha256=analyze._record_digest(svc.kb[1]), artifact_id="synthetic-artifact", model_id=analyze.ASK_MODEL)
    analyze._cache.put(key, "p2", cached, lang="zh")
    original = (tmp / "analysis.jsonl").read_bytes()
    reply = client.post("/api/analyze/stream", json={"a_id": "p1", "b_id": "p2", "persist": 1})
    assert reply.status_code == 200, reply.text
    assert '"from_cache": true' in reply.text and "event: persisted" not in reply.text
    assert analyze._report_store is None
    assert (tmp / "analysis.jsonl").read_bytes() == original
    svc.kb[0]["description"] = "Changed source version"
    assert_unavailable(client.post("/api/analyze/stream", json={"a_id": "p1", "b_id": "p2"}))


def test_package_exception_reaches_actual_app_problem_handler(app_env, no_sender):
    main, client, _, _ = app_env
    package_errors = importlib.import_module("web.backend.errors")
    async def forbidden(): package_errors.deny_legacy_paid()
    # A test-owned route using the actual app handlers, removed after the test.
    previous = list(main.app.router.routes)
    main.app.add_api_route("/test-legacy-package-error", forbidden, methods=["GET"])
    try: assert_unavailable(client.get("/test-legacy-package-error"))
    finally: main.app.router.routes[:] = previous
