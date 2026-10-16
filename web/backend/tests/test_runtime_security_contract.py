"""Release dependency compatibility and actual file-serving regressions."""
from __future__ import annotations

import importlib.metadata as metadata
from pathlib import Path
import re
import sys

from fastapi.testclient import TestClient
from packaging.requirements import Requirement
from pydantic import TypeAdapter, ValidationError
import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _pins(path: Path) -> dict[str, str]:
    return {
        name.lower().replace("_", "-"): version
        for name, version in re.findall(
            r"^([A-Za-z0-9_-]+)(?:\[[^]]+\])?==([^\s#]+)",
            path.read_text(), re.MULTILINE,
        )
    }


def test_security_candidate_is_installed_and_declared_for_both_services():
    expected = {
        "fastapi": "0.135.0", "starlette": "1.3.1", "pydantic": "2.7.4",
        "python-multipart": "0.0.32", "pyjwt": "2.15.1",
    }
    for path in [BACKEND / "requirements.txt", ROOT / "v4/product/d1_phase_detector/api/requirements.txt"]:
        pins = _pins(path)
        for name, version in expected.items():
            assert pins[name] == version
            assert metadata.version(name) == version


def test_fastapi_official_requirements_accept_actual_schema_runtime():
    checked = set()
    for raw in metadata.requires("fastapi") or []:
        requirement = Requirement(raw)
        if requirement.name not in {"starlette", "pydantic"}:
            continue
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        assert metadata.version(requirement.name) in requirement.specifier
        checked.add(requirement.name)
    assert checked == {"starlette", "pydantic"}


@pytest.mark.parametrize("url,relative", [
    ("/", "index.html"),
    ("/assets/css/reset.css", "assets/css/reset.css"),
])
def test_main_file_and_static_range_paths_serve_bounded_correct_content(url, relative):
    import main

    assert Path(main.__file__).resolve() == BACKEND / "main.py"
    expected = (ROOT / "web/frontend" / relative).read_bytes()
    # No lifespan: this probe exercises real public file routes, not models.
    client = TestClient(main.app)
    try:
        ordinary = client.get(url)
        assert ordinary.status_code == 200
        assert ordinary.content == expected
        partial = client.get(url, headers={"Range": "bytes=0-4"})
        assert partial.status_code == 206
        assert partial.content == expected[:5]
        assert partial.headers["Content-Range"] == f"bytes 0-4/{len(expected)}"
        # Many duplicate overlaps must preserve the same range semantics.
        # No wall-clock threshold: runner load is not a complexity proof.
        repeated = client.get(url, headers={"Range": "bytes=" + ",".join(["0-4"] * 2048)})
        assert repeated.status_code == 206
        assert repeated.content == expected[:5]
        assert repeated.headers["Content-Range"] == partial.headers["Content-Range"]
        invalid = client.get(url, headers={"Range": f"bytes={len(expected) + 1}-"})
        assert invalid.status_code == 416
    finally:
        client.close()


def test_existing_null_only_evidence_constraints_remain_null_only():
    from schemas import DiscoveryEvidenceCandidate, DiscoveryEvidenceSource

    for model, field in [(DiscoveryEvidenceCandidate, "score"), (DiscoveryEvidenceSource, "label")]:
        adapter = TypeAdapter(model.model_fields[field].annotation)
        assert adapter.validate_python(None) is None
        with pytest.raises(ValidationError):
            adapter.validate_python("not-null")


def test_main_validation_error_does_not_echo_new_default_input_or_ctx():
    import main

    client = TestClient(main.app)
    try:
        response = client.post("/api/search", json={"query": {"private-input-canary": "value"}})
        assert response.status_code == 422
        assert response.headers["content-type"].startswith("application/problem+json")
        assert "private-input-canary" not in response.text
        errors = response.json()["errors"]
        assert errors
        assert all(set(item) == {"loc", "msg", "type"} for item in errors)
    finally:
        client.close()
