"""Determinism and fail-closed tests for the committed OpenAPI artifact."""

from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GENERATOR = PROJECT_ROOT / "scripts" / "openapi_artifact.py"
BACKEND_REQUIREMENTS = PROJECT_ROOT / "web" / "backend" / "requirements.txt"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"


def _schema_runtime_python() -> str:
    """Use the explicit release-target environment when it exists locally."""
    configured = os.environ.get("STRUCTURAL_OPENAPI_TEST_PYTHON", "").strip()
    if configured:
        return configured
    dedicated = PROJECT_ROOT / ".venv-openapi" / "bin" / "python"
    return str(dedicated) if dedicated.is_file() else sys.executable


def _run(
    *args: str,
    cwd: Path,
    hash_seed: str,
    pythonpath: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = hash_seed
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)
    return subprocess.run(
        [_schema_runtime_python(), str(GENERATOR), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_generation_is_byte_deterministic_across_process_environments(tmp_path):
    artifact = tmp_path / "openapi.json"
    foreign_checkout = tmp_path / "foreign-checkout"
    foreign_checkout.mkdir()
    (foreign_checkout / "main.py").write_text(
        "raise RuntimeError('foreign main imported')\n",
        encoding="utf-8",
    )

    first = _run(
        "--stdout",
        cwd=tmp_path,
        hash_seed="random",
        pythonpath=foreign_checkout,
    )
    assert first.returncode == 0, first.stderr
    assert "Duplicate Operation ID" not in first.stderr
    first_bytes = first.stdout.encode("utf-8")
    artifact.write_bytes(first_bytes)

    second = _run("--stdout", cwd=PROJECT_ROOT, hash_seed="9173")
    assert second.returncode == 0, second.stderr
    assert "Duplicate Operation ID" not in second.stderr
    assert second.stdout.encode("utf-8") == first_bytes

    check = _run(
        "--check",
        "--artifact",
        str(artifact),
        cwd=tmp_path,
        hash_seed="42",
    )
    assert check.returncode == 0, check.stderr
    assert "Duplicate Operation ID" not in check.stderr
    assert '"event": "openapi.in_sync"' in check.stderr


def test_check_rejects_schema_drift_and_missing_artifact(tmp_path):
    artifact = tmp_path / "openapi.json"
    generated = _run(
        "--stdout",
        cwd=tmp_path,
        hash_seed="0",
    )
    assert generated.returncode == 0, generated.stderr
    artifact.write_text(generated.stdout, encoding="utf-8")

    schema = json.loads(artifact.read_text(encoding="utf-8"))
    schema["info"]["title"] = "tampered contract"
    artifact.write_text(
        f"{json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    drift = _run(
        "--check",
        "--artifact",
        str(artifact),
        cwd=tmp_path,
        hash_seed="0",
    )
    assert drift.returncode == 1
    assert '"event": "openapi.out_of_sync"' in drift.stderr

    artifact.unlink()
    missing = _run(
        "--check",
        "--artifact",
        str(artifact),
        cwd=tmp_path,
        hash_seed="0",
    )
    assert missing.returncode == 2
    assert '"event": "openapi.read_failed"' in missing.stderr


def test_cli_write_is_restricted_to_the_canonical_artifact(tmp_path):
    external = tmp_path / "outside.json"
    result = _run(
        "--write",
        "--artifact",
        str(external),
        cwd=tmp_path,
        hash_seed="0",
    )

    assert result.returncode == 2
    assert not external.exists()
    assert '"event": "openapi.invalid_target"' in result.stderr


def test_atomic_writer_does_not_follow_predictable_temp_symlink(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "openapi_artifact_atomic_test", GENERATOR,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    artifact = tmp_path / "artifact.json"
    victim = tmp_path / "victim.txt"
    victim.write_text("must remain unchanged", encoding="utf-8")
    old_predictable_name = tmp_path / f".{artifact.name}.{os.getpid()}.tmp"
    old_predictable_name.symlink_to(victim)

    assert module._write_artifact(artifact, b'{"safe":true}\n') == 0
    assert artifact.read_bytes() == b'{"safe":true}\n'
    assert victim.read_text(encoding="utf-8") == "must remain unchanged"
    assert old_predictable_name.is_symlink()


def test_canonical_write_contract_rejects_indirect_parent_paths():
    source = GENERATOR.read_text(encoding="utf-8")

    assert "directory.is_symlink()" in source
    assert "directory.resolve(strict=True) != directory" in source
    assert "_assert_canonical_write_target(artifact)" in source


def test_committed_default_artifact_matches_release_target_runtime():
    """Do not let temporary-artifact self-consistency hide committed drift."""
    checked = _run(
        "--check",
        cwd=PROJECT_ROOT,
        hash_seed="9173",
    )
    assert checked.returncode == 0, checked.stderr
    assert '"event": "openapi.in_sync"' in checked.stderr


def test_generator_enforces_release_target_fastapi_and_pydantic_pins(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "openapi_artifact_under_test", GENERATOR,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    locked = module._locked_schema_runtime_versions()
    assert locked == {
        "fastapi": "0.115.14",
        "pydantic": "2.6.1",
        "starlette": "0.46.2",
    }

    monkeypatch.setattr(
        module.importlib.metadata,
        "version",
        lambda package: "999.0.0",
    )
    with pytest.raises(RuntimeError, match="differs from the release target"):
        module._assert_schema_runtime_matches_release_target()


def test_release_target_schema_dependencies_remain_exactly_pinned():
    requirements = BACKEND_REQUIREMENTS.read_text(encoding="utf-8")
    assert "fastapi==0.115.14" in requirements
    assert "pydantic==2.6.1" in requirements
    assert "starlette==0.46.2" in requirements


def test_browser_contract_jobs_use_the_release_target_runtime_pins():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    required = (
        "fastapi==0.115.14",
        "pydantic==2.6.1",
        "starlette==0.46.2",
        "uvicorn[standard]==0.27.1",
    )
    for job_name in ("browser-product-contract", "browser-beta-surface-contract"):
        run_scripts = "\n".join(
            str(step.get("run", "")) for step in workflow["jobs"][job_name]["steps"]
        )
        for pin in required:
            assert pin in run_scripts, f"{job_name} must install {pin}"


def _generated_schema(tmp_path: Path) -> dict:
    generated = _run(
        "--stdout",
        cwd=tmp_path,
        hash_seed="20260714",
    )
    assert generated.returncode == 0, generated.stderr
    return json.loads(generated.stdout)


def _assert_nonempty_json_response(
    schema: dict, path: str, method: str, status: str = "200",
) -> dict:
    response_schema = schema["paths"][path][method]["responses"][status][
        "content"
    ]["application/json"]["schema"]
    assert response_schema, f"{method.upper()} {path} {status} has an empty schema"
    reference = response_schema.get("$ref")
    assert reference, f"{method.upper()} {path} {status} must use a typed model"
    component_name = reference.rsplit("/", 1)[-1]
    component = schema["components"]["schemas"][component_name]
    assert component.get("properties"), (
        f"{method.upper()} {path} {status} model has no typed properties"
    )
    return component


def test_analyze_stream_is_post_json_and_declares_sse_response(tmp_path):
    schema = _generated_schema(tmp_path)
    path = schema["paths"]["/api/analyze/stream"]
    assert set(path) == {"post"}
    operation = path["post"]
    request_schema = operation["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert request_schema["$ref"].endswith("/AnalyzeStreamRequest")
    response_content = operation["responses"]["200"]["content"]
    assert set(response_content) == {"text/event-stream"}
    assert response_content["text/event-stream"]["schema"] == {"type": "string"}


def test_public_semantics_keep_candidate_auth_and_legacy_boundaries(tmp_path):
    schema = _generated_schema(tmp_path)
    tags = {item["name"]: item["description"] for item in schema["tags"]}
    assert "research drafts" in tags["analyze"]
    assert "candidate-review queue" in tags["daily"]
    assert "not validated discoveries" in tags["discoveries"]

    magic_link = schema["paths"]["/api/auth/request-link"]["post"]
    assert "configured SMTP transport" in magic_link["description"]
    assert "fails closed" in magic_link["description"]

    for path, method in (
        ("/api/checkout/mock", "post"),
        ("/api/privacy/export", "get"),
        ("/api/privacy/delete", "delete"),
    ):
        operation = schema["paths"][path][method]
        assert operation["deprecated"] is True
        assert {"410", "422"} <= set(operation["responses"])
        description = operation["description"]
        assert "410" in description and "422" in description
        assert "before" in description
        _assert_nonempty_json_response(schema, path, method, "410")

    checkout = schema["paths"]["/api/checkout/mock"]["post"]["description"]
    assert "schema-valid production request" in checkout
    assert "malformed or schema-invalid body" in checkout
    for path, method in (
        ("/api/privacy/export", "get"),
        ("/api/privacy/delete", "delete"),
    ):
        description = schema["paths"][path][method]["description"]
        assert "well-formed, constraint-valid production request" in description
        assert "malformed, overlong, or otherwise constraint-invalid" in description


def test_key_account_library_and_method_success_contracts_are_typed(tmp_path):
    schema = _generated_schema(tmp_path)

    favorites = _assert_nonempty_json_response(
        schema, "/api/favorites", "get"
    )
    assert {"tickers", "bookmarks", "authenticated"} <= set(
        favorites["properties"]
    )
    _assert_nonempty_json_response(schema, "/api/favorites/merge", "post")
    for path in ("/api/favorites/bookmarks", "/api/favorites/{ticker}"):
        operation = schema["paths"][path]["post"]
        assert {"200", "201"} <= set(operation["responses"])
        _assert_nonempty_json_response(schema, path, "post", "200")
        _assert_nonempty_json_response(schema, path, "post", "201")
    for path in (
        "/api/favorites/bookmarks/{bookmark_id}",
        "/api/favorites/{ticker}",
    ):
        response = schema["paths"][path]["delete"]["responses"]["204"]
        assert "content" not in response

    for path, method in (
        ("/api/me/export", "get"),
        ("/api/me/delete", "post"),
        ("/api/me/reports", "get"),
        ("/api/reports/anon-proof", "post"),
        ("/api/me/reports/claim", "post"),
        ("/api/me/reports/{report_id}/insights-consent", "delete"),
        ("/api/me/reports/{report_id}", "delete"),
        ("/api/report/{report_id}/followup", "post"),
        ("/api/report/{report_id}/followup", "get"),
        ("/api/method/apply", "post"),
    ):
        _assert_nonempty_json_response(schema, path, method)
