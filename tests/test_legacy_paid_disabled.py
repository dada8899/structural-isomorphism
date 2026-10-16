"""Legacy sender closure with synthetic credentials, no provider requests."""
import asyncio
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request
from unittest.mock import Mock

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web/backend"
sys.path.insert(0, str(BACKEND))


def consume(value):
    async def run():
        if inspect.isasyncgen(value):
            try: return await anext(value)
            finally: await value.aclose()
        return await value
    return asyncio.run(run())


@pytest.fixture
def sender_spies(monkeypatch):
    # Resolve annotations before replacing a client constructor with a spy.
    for namespace in ("services", "web.backend.services"):
        for module in ("llm_service", "llm_client", "ask_orchestrator", "translation"):
            importlib.import_module(namespace + "." + module)
    def forbidden(*args, **kwargs): raise AssertionError("unexpected network/client construction")
    spies = {"client": Mock(side_effect=forbidden), "post": Mock(side_effect=forbidden), "stream": Mock(side_effect=forbidden), "urlopen": Mock(side_effect=forbidden)}
    async_client_type = httpx.AsyncClient
    monkeypatch.setattr(async_client_type, "post", spies["post"])
    monkeypatch.setattr(async_client_type, "stream", spies["stream"])
    monkeypatch.setattr(httpx, "AsyncClient", spies["client"])
    monkeypatch.setattr(urllib.request, "urlopen", spies["urlopen"])
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    yield spies
    assert all(s.call_count == 0 for s in spies.values())


@pytest.mark.parametrize("topology", ["services", "web.backend.services"])
@pytest.mark.parametrize("mode", ["prod", "dev"])
def test_every_legacy_sender_refuses_with_fake_key_and_model_variants(monkeypatch, sender_spies, topology, mode):
    service = importlib.import_module(topology + ".llm_service")
    client = importlib.import_module(topology + ".llm_client")
    ask_module = importlib.import_module(topology + ".ask_orchestrator")
    translation = importlib.import_module(topology + ".translation")
    errors = importlib.import_module("errors")
    monkeypatch.setenv("STRUCTURAL_ENV", mode)
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-not-a-real-key")
    monkeypatch.setenv("LLM_MODEL", "synthetic-model-override")
    monkeypatch.setenv("OPENROUTER_URL", "https://example.invalid/never-called")
    for module in (service, client, ask_module, translation):
        monkeypatch.setattr(module, "OPENROUTER_URL", "https://example.invalid/module-override")
    with pytest.raises(errors.LegacyPaidUnavailable): service._get_http_client()
    model = service.LLMService()
    assert model.api_key == ""
    model.api_key = "synthetic-preexisting-instance-key"
    assert client.llm_available() is False
    calls = [model.rewrite_query("synthetic"), model.assess_and_rewrite("synthetic"), model.generate_mapping({}, {}, .5),
             model.stream_mapping({}, {}, .5), model.synthesize_answer("x", None, []), model.stream_synthesize_answer("x", None, []),
             model.stream_deep_analysis({}, {}, source_refs=[]), client.complete_json(system="x", user="x"), client.complete_text(system="x", user="x"),
             client.stream_text(system="x", user="x"), translation._llm_translate_batch([{"id": "fixture"}])]
    orchestrator = ask_module.AskOrchestrator(search_service=object(), llm=model)
    calls += [orchestrator.stream("synthetic query"), orchestrator._call_llm_once("x"), orchestrator._call_llm_stream("x"),
              orchestrator._llm_answer_with_retry("x", [], "zh"), orchestrator._stream_llm_answer_with_retry("x", [], "zh")]
    for value in calls:
        with pytest.raises(errors.LegacyPaidUnavailable) as exc: consume(value)
        assert exc.value.status == 503
        assert exc.value.to_dict()["code"] == "FEATURE_UNAVAILABLE"


def test_client_construction_and_all_sends_stay_zero(sender_spies):
    from services.llm_service import LLMService, _get_http_client
    from services import llm_client, translation
    from services.ask_orchestrator import AskOrchestrator
    from errors import LegacyPaidUnavailable
    with pytest.raises(LegacyPaidUnavailable): _get_http_client()
    model = LLMService()
    calls = [model.assess_and_rewrite("x"), model.generate_mapping({}, {}, .9), model.stream_mapping({}, {}, .9),
             model.synthesize_answer("x", None, []), model.stream_synthesize_answer("x", None, []), model.stream_deep_analysis({}, {}, source_refs=[]),
             llm_client.complete_json(system="x", user="x"), llm_client.complete_text(system="x", user="x"), llm_client.stream_text(system="x", user="x"),
             AskOrchestrator(object(), model)._call_llm_once("x"), AskOrchestrator(object(), model)._call_llm_stream("x"), translation._llm_translate_batch([])]
    for value in calls:
        with pytest.raises(LegacyPaidUnavailable): consume(value)


def test_translation_only_accepts_existing_source_bound_public_cache(monkeypatch, sender_spies):
    from services import translation
    item = {"id": "kb1", "name": "原文", "domain": "物理", "type_id": "1", "description": "未翻译描述"}
    monkeypatch.setattr(translation, "_TRANSLATE_CACHE", {})
    assert consume(translation.translate_kb_item(item, "en")) == item
    assert consume(translation.translate_kb_items([item], "zh")) == [item]
    payload = {k: item.get(k) for k in ("id", "name", "domain", "description", "type_id")}
    source_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    translation._TRANSLATE_CACHE["kb1"] = {"schema_version": "legacy-public-translation-v1", "source_digest": source_hash,
        "translation": {"name": "Cached original", "domain": "Physics", "description": "Existing source-bound text"}}
    assert consume(translation.translate_kb_item(item, "en"))["name"] == "Cached original"
    changed = {**item, "description": "不同版本"}
    assert consume(translation.translate_kb_item(changed, "en")) == changed
    assert item["name"] == "原文"


def test_problem_class_identity_is_shared_by_flat_and_package_imports():
    flat = importlib.import_module("errors")
    package = importlib.import_module("web.backend.errors")
    assert flat is package
    assert flat.LegacyPaidUnavailable is package.LegacyPaidUnavailable


def test_package_first_import_also_uses_actual_problem_handler():
    code = '''
import importlib
package = importlib.import_module("web.backend.errors")
flat = importlib.import_module("errors")
assert package is flat
from fastapi import FastAPI
from fastapi.testclient import TestClient
app = FastAPI()
flat.install_problem_handlers(app)
@app.get("/closed")
async def closed(): package.deny_legacy_paid()
with TestClient(app) as client:
    response = client.get("/closed")
    assert response.status_code == 503
    assert response.json()["code"] == "FEATURE_UNAVAILABLE"
'''
    # Fresh minimal process environment; do not inherit credentials or .env.
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(BACKEND) + ":" + str(ROOT)},
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
