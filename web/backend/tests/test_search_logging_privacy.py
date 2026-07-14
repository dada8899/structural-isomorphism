"""Privacy contract for retrieval startup and method-search telemetry."""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


_BACKEND = Path(__file__).resolve().parent.parent
_ROOT = _BACKEND.parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services import method_search_service as method_search  # noqa: E402
from services import search_service  # noqa: E402


_INCIDENT_RE = re.compile(r"^[0-9a-f]{32}$")
_LOG_LEVELS = {"debug", "info", "warning", "error", "exception", "critical"}
_SAFE_FIELDS = {"count", "kb_count", "error_type", "incident_id"}
_CANARIES = (
    "query-canary-a116cf",
    "Bearer-token-canary-6f922c",
    "privacy-canary@example.test",
)


@pytest.mark.parametrize(
    ("package_module", "top_level_module"),
    (
        ("web.backend.services.search_service", "services.search_service"),
        ("web.backend.services.method_search_service", "services.method_search_service"),
        ("web.backend.api.method_search", "api.method_search"),
    ),
)
def test_retrieval_modules_import_in_both_supported_topologies(
    package_module: str,
    top_level_module: str,
) -> None:
    commands = (
        f"import {package_module}",
        (
            "import sys; "
            "sys.path.insert(0, 'web/backend'); "
            f"import {top_level_module}"
        ),
    )
    for command in commands:
        completed = subprocess.run(
            [sys.executable, "-c", command],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, (
            f"import topology failed for {package_module}: {completed.stderr}"
        )


class _RecordingLogger:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def _record(self, level: str, event: str, *args, **fields) -> None:
        assert not args, "privacy-safe log calls must not use formatting arguments"
        self.entries.append({"level": level, "event": event, **fields})

    def debug(self, event: str, *args, **fields) -> None:
        self._record("debug", event, *args, **fields)

    def info(self, event: str, *args, **fields) -> None:
        self._record("info", event, *args, **fields)

    def warning(self, event: str, *args, **fields) -> None:
        self._record("warning", event, *args, **fields)

    def error(self, event: str, *args, **fields) -> None:
        self._record("error", event, *args, **fields)


def _logger_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id == "logger"
            and node.func.attr in _LOG_LEVELS
        ):
            calls.append(node)
    return calls


@pytest.mark.parametrize(
    "relative_path",
    (
        "services/search_service.py",
        "services/method_search_service.py",
        "api/method_search.py",
    ),
)
def test_retrieval_log_calls_use_constant_allowlisted_events(relative_path: str) -> None:
    path = _BACKEND / relative_path
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    assert "import logging" not in source
    imports_by_level = {
        node.level: {alias.name for alias in node.names}
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "logging_config"
    }
    assert {"get_logger", "new_incident_id"} <= imports_by_level.get(0, set())
    assert {"get_logger", "new_incident_id"} <= imports_by_level.get(2, set())

    calls = _logger_calls(path)
    assert calls
    for call in calls:
        assert len(call.args) == 1
        event = call.args[0]
        assert isinstance(event, ast.Constant) and isinstance(event.value, str)
        assert event.value.startswith(("retrieval.", "startup."))
        assert all(keyword.arg in _SAFE_FIELDS for keyword in call.keywords)


def _assert_private_entries(entries: list[dict]) -> None:
    payload = json.dumps(entries, ensure_ascii=False, default=str)
    for canary in _CANARIES:
        assert canary not in payload
    for entry in entries:
        assert entry["event"].startswith(("retrieval.", "startup."))
        assert set(entry) <= {"level", "event", *_SAFE_FIELDS}
        if "error_type" in entry:
            assert isinstance(entry.get("error_type"), str)
            assert _INCIDENT_RE.fullmatch(entry.get("incident_id", ""))


def test_search_service_never_logs_raw_paths_or_parse_exceptions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    recorder = _RecordingLogger()
    data_dir = tmp_path / _CANARIES[0]
    data_dir.mkdir()
    kb_name = f"{_CANARIES[2]}.jsonl"
    (data_dir / kb_name).write_text(
        f'{{"id":"{_CANARIES[1]}"\n'
        '{"id":"kb-safe","name":"安全条目","description":"描述","domain":"测试"}\n',
        encoding="utf-8",
    )
    embeddings_path = tmp_path / _CANARIES[1]
    embeddings_path.mkdir()
    struct_path = tmp_path / _CANARIES[2]
    struct_path.mkdir()

    monkeypatch.setattr(search_service, "logger", recorder)
    monkeypatch.setattr(search_service, "load_model", lambda model_path=None: object())
    monkeypatch.setattr(
        search_service,
        "encode_texts",
        lambda model, texts, show_progress=False: np.zeros((len(texts), 2), dtype=np.float32),
    )
    monkeypatch.setitem(
        sys.modules,
        "rank_bm25",
        SimpleNamespace(BM25Okapi=lambda corpus: object()),
    )

    service = search_service.SearchService(
        data_dir=str(data_dir),
        kb_file=kb_name,
        precomputed_embeddings=str(embeddings_path),
        struct_file=str(struct_path),
    )
    assert service.kb_size == 1

    missing = search_service.SearchService.__new__(search_service.SearchService)
    missing.data_dir = data_dir
    missing.kb_file = f"missing-{_CANARIES[1]}.jsonl"
    missing.kb = []
    missing.kb_by_id = {}
    missing.idx_by_id = {}
    missing._load_kb()

    _assert_private_entries(recorder.entries)
    assert {entry["event"] for entry in recorder.entries} >= {
        "retrieval.kb_record_invalid",
        "retrieval.embeddings_load_failed",
        "retrieval.struct_index_load_failed",
        "startup.kb_file_missing",
    }


@pytest.mark.anyio
async def test_method_search_never_logs_raw_prompts_or_exception_messages(
    monkeypatch,
) -> None:
    from services import llm_client

    recorder = _RecordingLogger()

    async def fail_with_private_message(**kwargs):
        raise RuntimeError(" ".join(_CANARIES))

    monkeypatch.setattr(method_search, "logger", recorder)
    monkeypatch.setattr(llm_client, "llm_available", lambda: True)
    monkeypatch.setattr(llm_client, "complete_json", fail_with_private_message)

    signature = await method_search.extract_signature(_CANARIES[0])
    notes = await method_search.annotate_matches(
        {"signature": _CANARIES[1]},
        [
            {
                "id": "kb-safe",
                "name": _CANARIES[2],
                "domain": "测试",
                "description": _CANARIES[0],
            }
        ],
    )

    assert signature["llm"] is False
    assert notes == {}
    _assert_private_entries(recorder.entries)
    assert [entry["event"] for entry in recorder.entries] == [
        "retrieval.method_signature_failed",
        "retrieval.method_annotation_failed",
    ]
    assert all(entry["error_type"] == "RuntimeError" for entry in recorder.entries)


@pytest.fixture
def anyio_backend():
    return "asyncio"
