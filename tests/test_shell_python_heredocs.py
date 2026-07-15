from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.check_shell_python_heredocs import (
    extract_python_heredocs,
    validate_repository,
    validate_shell_script,
)


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "scripts" / "deploy-vps.sh"
RUNTIME_HELPER = ROOT / "scripts" / "deploy-versioned-runtime.sh"


def test_all_shell_python_heredocs_compile_without_shell_interpolation() -> None:
    blocks, issues = validate_repository(ROOT)

    assert len(blocks) >= 20
    assert not issues, "\n".join(issue.render(ROOT) for issue in issues)


def test_gate_detects_indentation_and_shell_interpolation(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.sh"
    invalid.write_text(
        "#!/usr/bin/env bash\n"
        "python3 - <<'PY'\n"
        "  for value in (1,):\n"
        "      print(value)\n"
        "PY\n"
        "python3 - <<PYEOF\n"
        "print('$UNSAFE_EXPANSION')\n"
        "PYEOF\n",
        encoding="utf-8",
    )

    blocks, issues = validate_shell_script(invalid)

    assert len(blocks) == 2
    assert any("unexpected indent" in issue.message for issue in issues)
    assert any("shell-interpolated" in issue.message for issue in issues)


def test_gate_strips_tabs_and_ignores_non_python_heredocs(tmp_path: Path) -> None:
    valid = tmp_path / "valid.sh"
    valid.write_text(
        "#!/usr/bin/env bash\n"
        "python3 - <<-'PY'\n"
        "\tfor value in (1,):\n"
        "\t    print(value)\n"
        "\tPY\n"
        "cat <<'EOF'\n"
        "this is not Python: ${ALLOWED_TEXT}\n"
        "EOF\n",
        encoding="utf-8",
    )

    blocks, issues = validate_shell_script(valid)

    assert len(blocks) == 1
    assert blocks[0].strip_tabs is True
    assert not issues


def test_gate_excludes_continued_shell_clause_from_python_body(tmp_path: Path) -> None:
    valid = tmp_path / "continued.sh"
    valid.write_text(
        "#!/usr/bin/env bash\n"
        "python3 - <<'PY' \\\n"
        "  || echo failed\n"
        "print('compiled')\n"
        "PY\n",
        encoding="utf-8",
    )

    blocks, issues = validate_shell_script(valid)

    assert not issues
    assert len(blocks) == 1
    assert blocks[0].source == "print('compiled')\n"


def test_production_runtime_fingerprint_block_executes_exactly(tmp_path: Path) -> None:
    blocks, parse_issues = extract_python_heredocs(DEPLOY)
    assert not parse_issues
    fingerprint = next(
        block
        for block in blocks
        if "EXPECTED_RUNTIME_ID" in block.command
        and "PUBLIC_RUNTIME_ATTESTATION" in block.command
    )
    assert fingerprint.quoted

    git_sha = "0123456789abcdef0123456789abcdef01234567"
    resolved_graph_sha = "b" * 64
    content_sha = "c" * 64
    freeze_sha = hashlib.sha256(
        (
            f"resolved_graph_sha256={resolved_graph_sha}\n"
            f"runtime_content_sha256={content_sha}\n"
        ).encode("ascii")
    ).hexdigest()
    runtime_id = "cpython-311-" + "a" * 64 + "-" + freeze_sha
    deployed_at = "2026-07-14T00:00:00Z"
    shared = {
        "schema_version": 2,
        "python_version": "3.11.6",
        "python_abi": "cpython-311",
        "runtime_id": runtime_id,
        "requirements_sha256": "a" * 64,
        "resolved_graph_sha256": resolved_graph_sha,
        "runtime_content_sha256": content_sha,
        "installed_freeze_sha256": freeze_sha,
        "fastapi": "0.115.14",
        "pydantic": "2.6.1",
        "starlette": "0.46.2",
        "uvicorn": "0.27.1",
    }
    attestation = {
        **shared,
        "git_sha": git_sha,
        "deployed_at": deployed_at,
    }
    version = dict(attestation)
    attestation_path = tmp_path / "runtime-attestation.json"
    attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
    environment = {
        **os.environ,
        "VERSION_JSON": json.dumps(version),
        "EXPECTED_GIT_SHA": git_sha,
        "EXPECTED_RUNTIME_ID": runtime_id,
        "PUBLIC_RUNTIME_ATTESTATION": str(attestation_path),
    }

    matching = subprocess.run(
        [sys.executable, "-c", fingerprint.source],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert matching.returncode == 0, matching.stderr

    version["fastapi"] = "0.0.0"
    environment["VERSION_JSON"] = json.dumps(version)
    mismatched = subprocess.run(
        [sys.executable, "-c", fingerprint.source],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert mismatched.returncode != 0
    assert "AssertionError" in mismatched.stderr


def test_public_runtime_attestation_block_executes_exactly(tmp_path: Path) -> None:
    blocks, parse_issues = extract_python_heredocs(RUNTIME_HELPER)
    assert not parse_issues
    publisher = next(
        block
        for block in blocks
        if "public runtime attestation requires a full Git SHA" in block.source
    )
    assert publisher.quoted

    source = tmp_path / "release-attestation.json"
    output = tmp_path / "runtime-attestation.json"
    git_sha = "0123456789abcdef0123456789abcdef01234567"
    deployed_at = "2026-07-14T00:00:00Z"
    source_payload = {
        "schema_version": 2,
        "runtime_id": "cpython-311-" + "a" * 64 + "-" + "d" * 64,
        "requirements_sha256": "a" * 64,
        "resolved_graph_sha256": "b" * 64,
        "runtime_content_sha256": "c" * 64,
        "installed_freeze_sha256": "d" * 64,
    }
    source.write_text(json.dumps(source_payload), encoding="utf-8")
    stale = output.with_name(f"{output.name}.tmp.stale")
    stale.write_text("partial", encoding="utf-8")

    success = subprocess.run(
        [
            sys.executable,
            "-c",
            publisher.source,
            str(source),
            str(output),
            git_sha,
            deployed_at,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert success.returncode == 0, success.stderr
    assert not stale.exists()
    assert json.loads(output.read_text(encoding="utf-8")) == {
        **source_payload,
        "git_sha": git_sha,
        "deployed_at": deployed_at,
    }

    output.unlink()
    prefix_only = subprocess.run(
        [
            sys.executable,
            "-c",
            publisher.source,
            str(source),
            str(output),
            git_sha[:12],
            deployed_at,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert prefix_only.returncode != 0
    assert "requires a full Git SHA" in prefix_only.stderr
    assert not output.exists()
