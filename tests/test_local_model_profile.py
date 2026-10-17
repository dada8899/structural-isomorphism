"""Constructor-only formal model profile; no real library/model is loaded."""
from pathlib import Path
import sys
import os
from types import SimpleNamespace
from types import ModuleType

import pytest

from structural_isomorphism import model


@pytest.fixture
def constructor(monkeypatch):
    calls = []
    package = ModuleType("sentence_transformers")
    package.SentenceTransformer = lambda *a, **k: calls.append((a, k)) or object()
    monkeypatch.setattr(os, "fstatvfs", lambda _fd: SimpleNamespace(f_flag=os.ST_RDONLY))
    monkeypatch.setitem(sys.modules, "sentence_transformers", package)
    return package, calls


def test_formal_constructor_is_explicit_even_with_remote_environment(tmp_path, monkeypatch, constructor):
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("HF_TOKEN", "implicit-token-canary")
    package, calls = constructor
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        model.load_model(f"/proc/self/fd/{fd}", formal=True, directory_fd=fd)
    finally:
        os.close(fd)
    assert calls == [((f"/proc/self/fd/{fd}",), {
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
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    def deny(_fd):raise PermissionError("private-directory-canary")
    monkeypatch.setattr(os, "fstat", deny)
    try:
        with pytest.raises(RuntimeError, match="directory is unavailable"):
            model.load_model(f"/proc/self/fd/{fd}", formal=True, directory_fd=fd)
        assert constructor[1] == []
    finally:
        os.close(fd)


def test_formal_load_error_never_tries_second_model_or_logs_excerpt(tmp_path, monkeypatch, caplog, constructor):
    package, calls = constructor

    def fail(*a, **k):
        calls.append((a, k))
        raise OSError("private-loader-canary")

    monkeypatch.setattr(package, "SentenceTransformer", fail)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(RuntimeError, match="could not be loaded") as error:
            model.load_model(f"/proc/self/fd/{fd}", formal=True, directory_fd=fd)
    finally:
        os.close(fd)
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


def test_formal_fd_anchor_is_not_resolved_back_to_source(tmp_path, monkeypatch, constructor):
    import os
    from types import SimpleNamespace
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    monkeypatch.setattr(os, 'fstatvfs', lambda _fd: SimpleNamespace(f_flag=os.ST_RDONLY))
    def forbidden(*_a, **_k):raise AssertionError('must not resolve away the FD anchor')
    monkeypatch.setattr(Path, 'resolve', forbidden)
    try:
        model.load_model(f'/proc/self/fd/{fd}', formal=True, directory_fd=fd)
        assert constructor[1][0][0] == (f'/proc/self/fd/{fd}',)
        os.fstat(fd)  # Caller owns the FD, including on loader failure.
    finally:
        os.close(fd)


def test_formal_fd_anchor_rejects_writable_mount(tmp_path, monkeypatch, constructor):
    import os
    from types import SimpleNamespace
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    monkeypatch.setattr(os, 'fstatvfs', lambda _fd: SimpleNamespace(f_flag=0))
    try:
        with pytest.raises(RuntimeError):
            model.load_model(f'/proc/self/fd/{fd}', formal=True, directory_fd=fd)
        assert constructor[1] == []
    finally:
        os.close(fd)


def test_formal_has_no_path_only_loading_shortcut(tmp_path, constructor):
    with pytest.raises(RuntimeError):
        model.load_model(str(tmp_path), formal=True)
    assert constructor[1] == []
