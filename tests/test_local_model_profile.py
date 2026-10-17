"""Constructor-only formal model profile; no real library/model is loaded."""
from pathlib import Path
import sys
from types import ModuleType

import pytest

from structural_isomorphism import model


@pytest.fixture
def constructor(monkeypatch):
    calls = []
    package = ModuleType("sentence_transformers")
    package.SentenceTransformer = lambda *a, **k: calls.append((a, k)) or object()
    monkeypatch.setitem(sys.modules, "sentence_transformers", package)
    return package, calls


def test_formal_constructor_is_explicit_even_with_remote_environment(tmp_path, monkeypatch, constructor):
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("HF_TOKEN", "implicit-token-canary")
    package, calls = constructor
    model.load_model(str(tmp_path), formal=True)
    assert calls == [((str(tmp_path.resolve()),), {
        "device": "cpu", "local_files_only": True, "token": False,
        "trust_remote_code": False,
    })]


@pytest.mark.parametrize("path", [None, "namespace/model", ".", "https://example.invalid/model"])
def test_formal_rejects_implicit_and_remote_paths_before_constructor(path, constructor):
    with pytest.raises(RuntimeError):
        model.load_model(path, formal=True)
    assert constructor[1] == []


@pytest.mark.parametrize("device", ["cuda", "mps", "auto"])
def test_formal_rejects_non_cpu_device(tmp_path, device, constructor):
    with pytest.raises(RuntimeError):
        model.load_model(str(tmp_path), device=device, formal=True)
    assert constructor[1] == []


def test_formal_requires_existing_directory(tmp_path, constructor):
    path = tmp_path / "missing"
    with pytest.raises(RuntimeError):
        model.load_model(str(path), formal=True)
    path.write_text("not a directory")
    with pytest.raises(RuntimeError):
        model.load_model(str(path), formal=True)
    assert constructor[1] == []


def test_formal_unreadable_directory_does_not_reach_constructor(tmp_path, monkeypatch, constructor):
    original = Path.resolve

    def deny(path, *a, **k):
        if path == tmp_path:
            raise PermissionError("private-directory-canary")
        return original(path, *a, **k)

    monkeypatch.setattr(Path, "resolve", deny)
    with pytest.raises(RuntimeError, match="directory is unavailable"):
        model.load_model(str(tmp_path), formal=True)
    assert constructor[1] == []


def test_formal_load_error_never_tries_second_model_or_logs_excerpt(tmp_path, monkeypatch, caplog, constructor):
    package, calls = constructor

    def fail(*a, **k):
        calls.append((a, k))
        raise OSError("private-loader-canary")

    monkeypatch.setattr(package, "SentenceTransformer", fail)
    with pytest.raises(RuntimeError, match="could not be loaded") as error:
        model.load_model(str(tmp_path), formal=True)
    assert len(calls) == 1
    assert "private-loader-canary" not in str(error.value) + caplog.text


def test_development_fallback_and_device_are_not_changed(tmp_path, monkeypatch, constructor):
    package, calls = constructor
    monkeypatch.setattr(model, "DEFAULT_LOCAL_MODEL", tmp_path / "absent")
    sentinel = object()

    def old_behavior(path, **kwargs):
        calls.append((path, kwargs))
        if path == model.DEFAULT_HF_MODEL:
            raise OSError("fixture Hub unavailable")
        return sentinel

    monkeypatch.setattr(package, "SentenceTransformer", old_behavior)
    assert model.load_model(device="mps") is sentinel
    assert calls == [(model.DEFAULT_HF_MODEL, {"device": "mps"}), (model.DEFAULT_BASE_MODEL, {"device": "mps"})]
