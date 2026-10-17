"""Formal retrieval constructor probes with tiny synthetic artifacts only."""
from pathlib import Path
import hashlib
import json
import sys
import os
from types import SimpleNamespace
from types import ModuleType

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
for path in (ROOT, ROOT / "web/backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from services import search_service, artifact_manifest


def make_bundle(path):
    path.mkdir(exist_ok=True)
    path = path.resolve()
    kb = path / "kb-expanded.jsonl"
    kb.write_text('\n'.join(json.dumps(row) for row in [
        {"id": "one", "name": "queue", "description": "queue feedback delay"},
        {"id": "two", "name": "flow", "description": "flow capacity bottleneck"},
    ]) + '\n')
    vectors = path / "kb_v2_embeddings.npy"
    np.save(vectors, np.ones((2, 3), dtype=np.float32))
    directory = path / "structural-v2"
    directory.mkdir()
    (directory / "1_Pooling").mkdir()
    configs = {
        "config.json": {"model_type": "bert", "architectures": ["BertModel"]},
        "modules.json": [
            {"idx": 0, "name": "0", "path": "", "type": "sentence_transformers.base.modules.transformer.Transformer"},
            {"idx": 1, "name": "1", "path": "1_Pooling", "type": "sentence_transformers.sentence_transformer.modules.pooling.Pooling"},
        ],
        "tokenizer.json": {}, "tokenizer_config.json": {"tokenizer_class": "BertTokenizer"},
        "config_sentence_transformers.json": {}, "sentence_bert_config.json": {},
        "1_Pooling/config.json": {},
    }
    for name, value in configs.items():
        (directory / name).write_text(json.dumps(value))
    (directory / "README.md").write_text("synthetic fixture")
    (directory / "model.safetensors").write_bytes(b"constructor-spy-not-real-weights")
    manifest = path.parent / (path.name + "-runtime-v2.json")
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
    model = Path(files["model_path"])
    hashes = {name: digest(model / name) for name in sorted(artifact_manifest.FORMAL_MODEL_FILES)}
    common = {
        "artifact_id": "formal-constructor-fixture",
        "kb": {"filename": kb.name, "row_count": len(rows), "unique_id_count": len({row["id"] for row in rows}), "sha256": digest(kb)},
        "embeddings": {"filename": Path(files["precomputed_embeddings"]).name,
                       "shape": list(vectors.shape), "dtype": str(vectors.dtype), "sha256": digest(files["precomputed_embeddings"])},
        "generation": {},
    }
    legacy = dict(common, schema_version=1, model={"id": "spy-model", "required_files": {
        name: hashes[name] for name in ("config.json", "modules.json", "tokenizer.json", "model.safetensors")
    }})
    (root / "manifest.json").write_text(json.dumps(legacy))
    (root / "kb_v2_embeddings_ids.json").write_text(json.dumps([row["id"] for row in rows]))
    specs = [{"path": name, "bytes": (root / name).stat().st_size, "sha256": digest(root / name)}
             for name in sorted(artifact_manifest.FORMAL_PAYLOAD_FILES)]
    total = sum(spec["bytes"] for spec in specs)
    transfer = {"artifact_id": common["artifact_id"], "schema_version": 1, "files": specs, "total_bytes": total}
    transfer_bytes = (json.dumps(transfer, sort_keys=True, separators=(",", ":")) + "\n").encode()
    manifest = dict(common, schema_version=2, model={"id": "spy-model", "required_files": hashes},
                    payload={"files": specs, "total_bytes": total, "exact_members": True},
                    source_binding={"payload_files": 13, "model_files": 9,
                                    "legacy_production_manifest_sha256": digest(root / "manifest.json"),
                                    "transfer_manifest_sha256": hashlib.sha256(transfer_bytes).hexdigest()})
    Path(files["artifact_manifest"]).write_text(json.dumps(manifest))


@pytest.fixture(autouse=True)
def synthetic_readonly_mount(monkeypatch):
    # Unit tests only: no mount or real model is created. Linux deployment must
    # separately prove the actual readonly namespace and closed writer aliases.
    monkeypatch.setattr(os, "fstatvfs", lambda _fd: SimpleNamespace(f_flag=os.ST_RDONLY))


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
    service.close()
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
        (root / "kb-expanded.jsonl").write_text('{"id":"same","description":"queue"}\n' * 2);refresh_bundle(bundle)
    elif fault == "empty-kb":
        (root / "kb-expanded.jsonl").write_text("");refresh_bundle(bundle)
    elif fault == "bad-json":(root / "kb-expanded.jsonl").write_text("not JSON\n")
    else:
        original = os.open
        def denied(path, *a, **k):
            if path == Path(bundle["artifact_manifest"]).name:raise PermissionError("fixture unreadable")
            return original(path, *a, **k)
        monkeypatch.setattr(os, "open", denied)
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
    original = artifact_manifest.open_formal_artifact_bundle
    def changed(*a, **k):
        snapshot = original(*a, **k)
        # Original P2 reproduction: same shape/dtype, entirely different values.
        np.save(bundle["precomputed_embeddings"], np.full((2, 3), 9, dtype=np.float32))
        return snapshot
    monkeypatch.setattr(artifact_manifest, "open_formal_artifact_bundle", changed)
    service = search_service.SearchService(**bundle, formal=True)
    try:
        assert np.array_equal(service._embeddings, np.ones((2, 3), dtype=np.float32))
        assert not service._embeddings.flags.writeable
    finally:
        service.close()


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
    service.close()


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


def test_formal_same_row_count_kb_replacement_uses_verified_snapshot(bundle, encoder, monkeypatch):
    original = artifact_manifest.open_formal_artifact_bundle
    def changed(*a, **k):
        snapshot = original(*a, **k)
        kb = Path(bundle['data_dir']) / bundle['kb_file']
        rows = [dict(row, description='unvalidated same-row replacement') for row in snapshot.rows]
        kb.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
        return snapshot
    monkeypatch.setattr(artifact_manifest, 'open_formal_artifact_bundle', changed)
    service = search_service.SearchService(**bundle, formal=True)
    try:
        assert service.kb[0]['description'] == 'queue feedback delay'
        assert service.kb_by_id['one'] is service.kb[0]
    finally:
        service.close()


@pytest.mark.parametrize('when', ['after-validation', 'during-constructor'])
def test_formal_weight_replacement_cannot_publish_ready(bundle, encoder, monkeypatch, when):
    weight = Path(bundle['model_path']) / 'model.safetensors'
    if when == 'after-validation':
        original = artifact_manifest.open_formal_artifact_bundle
        def changed(*a, **k):
            snapshot = original(*a, **k)
            weight.write_bytes(b'X' * weight.stat().st_size)
            return snapshot
        monkeypatch.setattr(artifact_manifest, 'open_formal_artifact_bundle', changed)
    else:
        original = sys.modules['sentence_transformers'].SentenceTransformer
        def changed(*a, **k):
            weight.write_bytes(b'X' * weight.stat().st_size)
            return original(*a, **k)
        monkeypatch.setattr(sys.modules['sentence_transformers'], 'SentenceTransformer', changed)
    with pytest.raises(RuntimeError):
        search_service.SearchService(**bundle, formal=True)
    assert len(encoder[0]) == (when == 'during-constructor')


@pytest.mark.parametrize('name', sorted(artifact_manifest.FORMAL_MODEL_FILES))
def test_formal_each_approved_model_file_is_mandatory(bundle, encoder, name):
    manifest = Path(bundle['artifact_manifest'])
    value = json.loads(manifest.read_text())
    # Keep the file on disk: removing only its binding must also fail.
    del value['model']['required_files'][name]
    manifest.write_text(json.dumps(value))
    with pytest.raises(RuntimeError):
        search_service.SearchService(**bundle, formal=True)
    assert encoder[0] == []


@pytest.mark.parametrize('fault', [
    'extra-weights', 'extra-directory', 'extra-config', 'duplicate-member', 'member-escape',
    'duplicate-json', 'symlink', 'hardlink', 'fifo', 'missing-ids', 'wrong-ids',
    'bool-total', 'bad-transfer', 'bad-legacy', 'module-type', 'module-escape',
    'config-auto-map', 'tokenizer-path', 'nonreadonly', 'v1',
])
def test_formal_closed_payload_rejects_unbound_or_unsafe_inputs(bundle, encoder, monkeypatch, fault):
    root, model = Path(bundle['data_dir']), Path(bundle['model_path'])
    path = Path(bundle['artifact_manifest'])
    value = json.loads(path.read_text())
    if fault == 'extra-weights':(model / 'pytorch_model.bin').write_bytes(b'unbound')
    elif fault == 'extra-directory':(root / 'extra').mkdir()
    elif fault == 'extra-config':(model / 'config.alternate.json').write_text('{}')
    elif fault == 'duplicate-member':value['payload']['files'][-1] = value['payload']['files'][0]
    elif fault == 'member-escape':value['payload']['files'][0]['path'] = '../outside'
    elif fault == 'duplicate-json':
        path.write_text('{"schema_version":2,' + path.read_text()[1:])
    elif fault in ('symlink', 'hardlink', 'fifo'):
        target = model / 'config.json'
        saved = root.parent / 'outside.json'
        saved.write_bytes(target.read_bytes())
        target.unlink()
        if fault == 'symlink':target.symlink_to(saved)
        elif fault == 'hardlink':os.link(saved, target)
        else:os.mkfifo(target)
    elif fault == 'missing-ids':(root / 'kb_v2_embeddings_ids.json').unlink()
    elif fault == 'wrong-ids':
        (root / 'kb_v2_embeddings_ids.json').write_text('["two","one"]')
        # Bind the wrong-order bytes: semantic ID validation still rejects.
        spec = next(s for s in value['payload']['files'] if s['path'] == 'kb_v2_embeddings_ids.json')
        spec.update(bytes=(root / spec['path']).stat().st_size,
                    sha256=hashlib.sha256((root / spec['path']).read_bytes()).hexdigest())
        rebind_transfer(value)
    elif fault == 'bool-total':value['payload']['total_bytes'] = True
    elif fault == 'bad-transfer':value['source_binding']['transfer_manifest_sha256'] = '0' * 64
    elif fault == 'bad-legacy':value['source_binding']['legacy_production_manifest_sha256'] = '0' * 64
    elif fault in ('module-type', 'module-escape'):
        modules = json.loads((model / 'modules.json').read_text())
        modules[1]['type' if fault == 'module-type' else 'path'] = 'unbound.Custom' if fault == 'module-type' else '../outside'
        (model / 'modules.json').write_text(json.dumps(modules))
        refresh_bundle(bundle)
        value = json.loads(path.read_text())
    elif fault in ('config-auto-map', 'tokenizer-path'):
        config_path = model / ('config.json' if fault == 'config-auto-map' else 'tokenizer_config.json')
        config = json.loads(config_path.read_text())
        config['auto_map' if fault == 'config-auto-map' else 'tokenizer_file'] = '/outside/custom'
        config_path.write_text(json.dumps(config))
        refresh_bundle(bundle)
        value = json.loads(path.read_text())
    elif fault == 'nonreadonly':
        monkeypatch.setattr(os, 'fstatvfs', lambda _fd: SimpleNamespace(f_flag=0))
    elif fault == 'v1':value['schema_version'] = 1
    if fault != 'duplicate-json':path.write_text(json.dumps(value))
    with pytest.raises(RuntimeError):
        search_service.SearchService(**bundle, formal=True)
    assert encoder[0] == []


def rebind_transfer(value):
    payload = value['payload']
    payload['total_bytes'] = sum(s['bytes'] for s in payload['files'])
    transfer = {'artifact_id': value['artifact_id'], 'files': payload['files'],
                'schema_version': 1, 'total_bytes': payload['total_bytes']}
    value['source_binding']['transfer_manifest_sha256'] = hashlib.sha256(
        (json.dumps(transfer, sort_keys=True, separators=(',', ':')) + '\n').encode()
    ).hexdigest()


def test_formal_renamed_source_directory_keeps_constructor_fd_anchor(bundle, encoder, monkeypatch):
    original = artifact_manifest.open_formal_artifact_bundle
    moved = Path(bundle['data_dir']).with_name('original-verified-directory')
    def changed(*a, **k):
        snapshot = original(*a, **k)
        Path(bundle['data_dir']).rename(moved)
        Path(bundle['data_dir']).mkdir()
        (Path(bundle['data_dir']) / 'unbound').write_text('replacement')
        return snapshot
    monkeypatch.setattr(artifact_manifest, 'open_formal_artifact_bundle', changed)
    service = search_service.SearchService(**bundle, formal=True)
    snapshot = service._formal_snapshot
    fd = snapshot.model_fd
    try:
        assert encoder[0][0][0] == (f'/proc/self/fd/{fd}',)
        file_fd = os.open('config.json', os.O_RDONLY, dir_fd=fd)
        try:
            assert json.loads(os.read(file_fd, 4096))['model_type'] == 'bert'
        finally:
            os.close(file_fd)
    finally:
        service.close()
    with pytest.raises(OSError):os.fstat(fd)
    service.close()  # Idempotent cleanup.


@pytest.mark.parametrize('fault', ['hash', 'model', 'dimension', 'bm25'])
def test_formal_failure_closes_every_opened_artifact_fd(bundle, encoder, monkeypatch, fault):
    opened = []
    original = os.open
    def tracked(*a, **k):
        fd = original(*a, **k)
        opened.append(fd)
        return fd
    monkeypatch.setattr(os, 'open', tracked)
    if fault == 'hash':(Path(bundle['model_path']) / 'config.json').write_text('bad')
    elif fault == 'model':
        def failed(*_a, **_k):raise OSError('fixture constructor failed')
        monkeypatch.setattr(sys.modules['sentence_transformers'], 'SentenceTransformer', failed)
    elif fault == 'dimension':
        monkeypatch.setattr(encoder[1], 'get_sentence_embedding_dimension', lambda self: 9)
    else:
        import rank_bm25
        monkeypatch.setattr(rank_bm25, 'BM25Okapi', lambda *_a, **_k: None)
    with pytest.raises(RuntimeError):search_service.SearchService(**bundle, formal=True)
    assert opened
    for fd in set(opened):
        with pytest.raises(OSError):os.fstat(fd)
