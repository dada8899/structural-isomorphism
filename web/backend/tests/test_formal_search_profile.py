"""Formal retrieval constructor probes with tiny synthetic artifacts only."""
from pathlib import Path
import hashlib
import json
import sys
from types import ModuleType

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
for path in (ROOT, ROOT / "web/backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from services import search_service


def make_bundle(path):
    path.mkdir(exist_ok=True)
    kb = path / "kb.jsonl"
    kb.write_text('\n'.join(json.dumps(row) for row in [
        {"id": "one", "name": "queue", "description": "queue feedback delay"},
        {"id": "two", "name": "flow", "description": "flow capacity bottleneck"},
    ]) + '\n')
    vectors = path / "vectors.npy"
    np.save(vectors, np.ones((2, 3), dtype=np.float32))
    directory = path / "model"
    directory.mkdir()
    for name in ("config.json", "modules.json", "tokenizer.json", "model.safetensors"):
        (directory / name).write_text("constructor-spy-fixture-not-real-model")
    manifest = path / "manifest.json"
    files = {"data_dir": str(path), "kb_file": kb.name, "model_path": str(directory),
             "precomputed_embeddings": str(vectors), "artifact_manifest": str(manifest)}
    refresh_bundle(files)
    return files


def refresh_bundle(files):
    root = Path(files["data_dir"])
    kb = root / files["kb_file"]
    vectors = np.load(files["precomputed_embeddings"], allow_pickle=False)
    rows = [json.loads(line) for line in kb.read_text().splitlines() if line]
    def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1, "artifact_id": "formal-constructor-fixture",
        "kb": {"row_count": len(rows), "unique_id_count": len({row["id"] for row in rows}), "sha256": digest(kb)},
        "embeddings": {"shape": list(vectors.shape), "dtype": str(vectors.dtype), "sha256": digest(files["precomputed_embeddings"])},
        "model": {"id": "spy-model", "required_files": {
            p.name: digest(p) for p in Path(files["model_path"]).iterdir() if p.is_file()
        }},
    }
    Path(files["artifact_manifest"]).write_text(json.dumps(manifest))


@pytest.fixture
def bundle(tmp_path):
    return make_bundle(tmp_path / "bundle")


@pytest.fixture
def encoder(monkeypatch):
    package = ModuleType("sentence_transformers")
    calls = []

    class Encoder:
        def get_sentence_embedding_dimension(self):return 3
        def encode(self, *a, **k):raise AssertionError("unexpected corpus re-encoding")

    def construct(*a, **k):
        calls.append((a, k))
        return Encoder()

    package.SentenceTransformer = construct
    monkeypatch.setitem(sys.modules, "sentence_transformers", package)
    return calls, Encoder


def test_formal_real_service_uses_actual_loader_and_approved_non768_vectors(bundle, encoder):
    service = search_service.SearchService(**bundle, formal=True)
    assert service.kb_size == 2 and service._embeddings.shape == (2, 3)
    assert service._bm25 is not None and service._bm25_corpus_len == 2
    assert encoder[0][0][1] == {"device": "cpu", "local_files_only": True, "token": False, "trust_remote_code": False}
    assert service.artifact["artifact_id"] == "formal-constructor-fixture"


@pytest.mark.parametrize("key", ["data_dir", "model_path", "precomputed_embeddings", "artifact_manifest"])
def test_formal_requires_all_explicit_existing_local_paths(bundle, encoder, key):
    bundle[key] = None
    with pytest.raises(RuntimeError):search_service.SearchService(**bundle, formal=True)
    assert encoder[0] == []


@pytest.mark.parametrize("fault", ["missing-model", "bad-hash", "missing-vectors", "bad-shape", "nan", "integer", "duplicate-id", "empty-kb", "bad-json", "unreadable"])
def test_formal_artifact_failures_do_not_construct_or_encode(bundle, encoder, monkeypatch, fault):
    root = Path(bundle["data_dir"])
    if fault == "missing-model":(Path(bundle["model_path"]) / "config.json").unlink()
    elif fault == "bad-hash":(Path(bundle["model_path"]) / "config.json").write_text("changed")
    elif fault == "missing-vectors":Path(bundle["precomputed_embeddings"]).unlink()
    elif fault == "bad-shape":
        np.save(bundle["precomputed_embeddings"], np.ones((2,), dtype=np.float32));refresh_bundle(bundle)
    elif fault == "nan":
        np.save(bundle["precomputed_embeddings"], np.full((2, 3), np.nan, dtype=np.float32));refresh_bundle(bundle)
    elif fault == "integer":
        np.save(bundle["precomputed_embeddings"], np.ones((2, 3), dtype=np.int32));refresh_bundle(bundle)
    elif fault == "duplicate-id":
        (root / "kb.jsonl").write_text('{"id":"same","description":"queue"}\n' * 2);refresh_bundle(bundle)
    elif fault == "empty-kb":
        (root / "kb.jsonl").write_text("");refresh_bundle(bundle)
    elif fault == "bad-json":(root / "kb.jsonl").write_text("not JSON\n")
    else:
        original = Path.open
        def denied(path, *a, **k):
            if path == Path(bundle["artifact_manifest"]):raise PermissionError("fixture unreadable")
            return original(path, *a, **k)
        monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(RuntimeError):search_service.SearchService(**bundle, formal=True)
    assert encoder[0] == []


@pytest.mark.parametrize("fault", ["exception", "none", "nonfinite-scores"])
def test_formal_bm25_failure_never_downgrades(bundle, encoder, monkeypatch, fault):
    import rank_bm25
    def broken(*a, **k):
        if fault == "exception":raise RuntimeError("fixture index failure")
        if fault == "none":return None
        return type("BadIndex", (), {"get_scores": lambda *_: np.array([np.nan, 0])})()
    monkeypatch.setattr(rank_bm25, "BM25Okapi", broken)
    with pytest.raises(RuntimeError, match="BM25"):search_service.SearchService(**bundle, formal=True)


def test_formal_rejects_char_tokenizer_fallback(bundle, encoder, monkeypatch):
    monkeypatch.setattr(search_service, "_JIEBA", None)
    with pytest.raises(RuntimeError):search_service.SearchService(**bundle, formal=True)
    assert encoder[0] == []


def test_formal_rejects_changed_vector_payload_after_manifest_validation(bundle, encoder, monkeypatch):
    original = search_service.np.load
    calls = []
    def changed(path, *a, **k):
        calls.append(k)
        if len(calls) > 1:return np.ones((2, 4), dtype=np.float32)
        return original(path, *a, **k)
    monkeypatch.setattr(search_service.np, "load", changed)
    with pytest.raises(RuntimeError, match="precomputed"):search_service.SearchService(**bundle, formal=True)
    assert encoder[0] == []


def test_formal_rejects_model_dimension_mismatch(bundle, encoder, monkeypatch):
    monkeypatch.setattr(encoder[1], "get_sentence_embedding_dimension", lambda self: 4)
    with pytest.raises(RuntimeError, match="dimension"):search_service.SearchService(**bundle, formal=True)


def test_formal_does_not_discover_or_accept_unbound_struct_index(bundle, encoder):
    outside = Path(bundle["data_dir"]).parent / "v3/results/kb-expanded-struct.jsonl"
    outside.parent.mkdir(parents=True)
    outside.write_text('{"phenomenon_id":"one","unapproved":true}\n')
    service = search_service.SearchService(**bundle, formal=True)
    assert service._struct_by_id == {}
    before = len(encoder[0])
    with pytest.raises(RuntimeError):
        search_service.SearchService(**bundle, formal=True, struct_file=str(outside))
    assert len(encoder[0]) == before


@pytest.mark.parametrize("fault", ["model-files", "model-id", "symlink", "bool-schema", "nontext-artifact"])
def test_formal_manifest_rejects_incomplete_identity_and_escape(bundle, encoder, fault):
    manifest = Path(bundle["artifact_manifest"])
    value = json.loads(manifest.read_text())
    if fault == "model-files":value["model"]["required_files"] = {}
    elif fault == "model-id":value["model"]["id"] = ""
    elif fault == "bool-schema":value["schema_version"] = True
    elif fault == "nontext-artifact":value["artifact_id"] = True
    else:
        config = Path(bundle["model_path"]) / "config.json"
        outside = Path(bundle["data_dir"]).parent / "outside.json"
        outside.write_bytes(config.read_bytes())
        config.unlink()
        config.symlink_to(outside)
    manifest.write_text(json.dumps(value))
    with pytest.raises(RuntimeError):search_service.SearchService(**bundle, formal=True)
    assert encoder[0] == []


def test_development_still_reencodes_when_no_precomputed_matrix(bundle, encoder, monkeypatch):
    seen = []
    monkeypatch.setattr(search_service, "encode_texts", lambda *_a, **_k: seen.append(True) or np.ones((2, 3), dtype=np.float32))
    args = {k: v for k, v in bundle.items() if k not in ("artifact_manifest", "precomputed_embeddings")}
    service = search_service.SearchService(**args)
    assert service.kb_size == 2 and seen == [True]
    assert encoder[0][0][1] == {}
