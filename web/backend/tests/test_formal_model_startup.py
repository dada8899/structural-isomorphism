"""Main lifespan -> real SearchService -> real loader -> constructor spy."""
from pathlib import Path
import asyncio
import importlib
import sys

import pytest

from tests.test_formal_search_profile import make_bundle, encoder, synthetic_readonly_mount


@pytest.fixture
def startup(tmp_path, monkeypatch):
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("STRUCTURAL_LOG_FILE", str(tmp_path / "events.jsonl"))
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    for key in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "BUTTONDOWN_API_KEY", "STRIPE_TEST_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    module = importlib.import_module("main")
    monkeypatch.setattr(module, "_IS_PROD", True)
    monkeypatch.setattr(module.auth_api, "_validate_production_config", lambda: None)
    monkeypatch.setattr(module, "_resolve_git_sha", lambda: "1" * 40)
    monkeypatch.setattr(module, "app_state", {"search": object(), "artifact": {"artifact_id": "stale"}})
    files = make_bundle(tmp_path / "bundle")
    for key, value in {
        "STRUCTURAL_DATA_DIR": files["data_dir"], "STRUCTURAL_KB_FILE": files["kb_file"],
        "STRUCTURAL_MODEL_PATH": files["model_path"], "STRUCTURAL_PRECOMPUTED_EMBEDDINGS": files["precomputed_embeddings"],
        "STRUCTURAL_ARTIFACT_MANIFEST": files["artifact_manifest"],
    }.items():monkeypatch.setenv(key, value)
    return module, files


def test_production_lifespan_constructs_only_local_cpu_and_publishes_after_ready(startup, encoder, monkeypatch):
    module, files = startup
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("HF_TOKEN", "implicit-token-canary")
    async def run():
        async with module.lifespan(module.app):
            assert module.app_state["search"].formal is True
            assert module.app_state["artifact"]["embedding_shape"] == [2, 3]
    asyncio.run(run())
    assert len(encoder[0]) == 1
    assert encoder[0][0][1] == {"device": "cpu", "local_files_only": True, "token": False, "trust_remote_code": False}


@pytest.mark.parametrize("fault", ["no-manifest", "bad-hash", "hub-id", "load-failure", "bad-vectors", "bm25"])
def test_production_lifespan_failure_does_not_leave_stale_ready(startup, encoder, monkeypatch, fault):
    module, files = startup
    if fault == "no-manifest":monkeypatch.delenv("STRUCTURAL_ARTIFACT_MANIFEST")
    elif fault == "bad-hash":(Path(files["model_path"]) / "config.json").write_text("changed")
    elif fault == "hub-id":monkeypatch.setenv("STRUCTURAL_MODEL_PATH", "namespace/model")
    elif fault == "bad-vectors":
        import numpy as np
        np.save(files["precomputed_embeddings"], np.ones((1, 3), dtype=np.float32))
    elif fault == "bm25":
        import rank_bm25
        def failed_index(*a, **k):raise RuntimeError("fixture index unavailable")
        monkeypatch.setattr(rank_bm25, "BM25Okapi", failed_index)
    else:
        package = sys.modules["sentence_transformers"]
        def failed(*a, **k):
            encoder[0].append((a, k))
            raise OSError("fixture model unavailable")
        monkeypatch.setattr(package, "SentenceTransformer", failed)
    async def run():
        async with module.lifespan(module.app):raise AssertionError("must not become ready")
    with pytest.raises(RuntimeError):asyncio.run(run())
    assert "search" not in module.app_state and "artifact" not in module.app_state
    assert len(encoder[0]) == (1 if fault in ("load-failure", "bm25") else 0)
    assert asyncio.run(module.health(deep=1)).status_code == 503


@pytest.mark.parametrize('abort', [False, True])
def test_lifespan_closes_model_and_payload_fds_and_clears_ready(startup, encoder, abort):
    import os
    module, _files = startup
    descriptors = []
    async def run():
        async with module.lifespan(module.app):
            snapshot = module.app_state['search']._formal_snapshot
            descriptors.extend([snapshot.root_fd, snapshot.model_fd])
            for fd in descriptors:os.fstat(fd)
            if abort:raise ValueError('synthetic application failure')
    if abort:
        with pytest.raises(ValueError):asyncio.run(run())
    else:
        asyncio.run(run())
    assert 'search' not in module.app_state and 'artifact' not in module.app_state
    for fd in descriptors:
        with pytest.raises(OSError):os.fstat(fd)
    assert asyncio.run(module.health(deep=1)).status_code == 503


def test_lifespan_weight_change_after_validation_never_sets_ready(startup, encoder, monkeypatch):
    from services import artifact_manifest
    module, files = startup
    original = artifact_manifest.open_formal_artifact_bundle
    saved = []
    def changed(*a, **k):
        snapshot = original(*a, **k)
        saved.extend([snapshot.root_fd, snapshot.model_fd])
        weight = Path(files['model_path']) / 'model.safetensors'
        weight.write_bytes(b'X' * weight.stat().st_size)
        return snapshot
    monkeypatch.setattr(artifact_manifest, 'open_formal_artifact_bundle', changed)
    async def run():
        async with module.lifespan(module.app):raise AssertionError('must not become ready')
    with pytest.raises(RuntimeError):asyncio.run(run())
    assert 'search' not in module.app_state and 'artifact' not in module.app_state
    assert encoder[0] == []
    assert asyncio.run(module.health(deep=1)).status_code == 503
    import os
    for fd in saved:
        with pytest.raises(OSError):os.fstat(fd)
