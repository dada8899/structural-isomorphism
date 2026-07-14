"""W15-A: smoke tests for the Pydantic → TypeScript pipeline.

Guards:
  1. `web/backend/schemas.py` exposes every public model expected by
     the frontend.
  2. The committed `web/phase-detector/lib/api-types.ts` advertises a
     matching exported interface for each Python class.

These tests are intentionally cheap (no shelling out to pydantic2ts) so
they can run on the slim Python-only CI matrix. The actual regeneration
+ diff check lives in `.github/workflows/types-sync.yml`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_PATH = REPO_ROOT / "web" / "backend" / "schemas.py"
TS_PATH = REPO_ROOT / "web" / "phase-detector" / "lib" / "api-types.ts"


def test_types_workflow_tracks_its_locked_generator_requirements() -> None:
    workflow_path = REPO_ROOT / ".github/workflows/types-sync.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    workflow_data = yaml.safe_load(workflow)
    generator = (REPO_ROOT / "scripts/gen_ts_types.sh").read_text(
        encoding="utf-8"
    )
    safe_generator = (REPO_ROOT / "scripts/generate_ts_types.py").read_text(
        encoding="utf-8"
    )
    checker = (REPO_ROOT / "scripts/check_ts_types.sh").read_text(
        encoding="utf-8"
    )

    triggers = workflow_data.get("on", workflow_data.get(True))
    assert triggers["pull_request"] == {"branches": ["main"]}
    assert triggers["push"] == {"branches": ["main"]}
    assert "paths" not in triggers["pull_request"]
    assert "paths" not in triggers["push"]
    assert "python -m pip install -r scripts/requirements-types.txt" in workflow
    assert "npm ci --ignore-scripts --no-audit --no-fund --prefix scripts/types-generator" in workflow
    assert "bash scripts/gen_ts_types.sh" in workflow
    assert 'JSON2TS_VERSION = "15.0.4"' in safe_generator
    assert "--json2ts-cmd" not in generator
    assert "os.system" not in safe_generator
    assert "subprocess.run" in safe_generator
    assert "legacy command overrides are forbidden" in generator
    assert '("pydantic", "pydantic-to-typescript")' in generator
    assert "version mismatch" in generator
    assert 'TMP_OUTPUT="$(mktemp -t structural-api-types.XXXXXX)"' in checker
    assert 'OUT="$TMP_OUTPUT" bash scripts/gen_ts_types.sh' in checker
    assert 'cmp -s "$COMMITTED" "$TMP_OUTPUT"' in checker


def test_types_node_dependency_tree_is_content_locked() -> None:
    tool_root = REPO_ROOT / "scripts" / "types-generator"
    package = json.loads((tool_root / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((tool_root / "package-lock.json").read_text(encoding="utf-8"))
    expected = {"json-schema-to-typescript": "15.0.4"}

    assert package["dependencies"] == expected
    assert lock["lockfileVersion"] == 3
    assert lock["packages"][""]["dependencies"] == expected
    assert lock["packages"]["node_modules/json-schema-to-typescript"]["version"] == "15.0.4"
    for name, metadata in lock["packages"].items():
        if not name or metadata.get("link"):
            continue
        assert metadata.get("integrity"), f"missing lock integrity for {name}"


def test_safe_generator_binds_runtime_files_and_uses_argument_vectors() -> None:
    source = (REPO_ROOT / "scripts" / "generate_ts_types.py").read_text(
        encoding="utf-8"
    )

    assert "JSON2TS_CLI_SHA256" in source
    assert "expected_binary.is_relative_to(package_root)" in source
    assert "declared_binary.is_symlink()" in source
    assert "node must be a native executable" in source
    assert "Path(identity.stdout.strip()).resolve() != node" in source
    assert "str(node), str(json2ts)" in source
    assert "os.system" not in source


def test_legacy_json2ts_shell_command_override_fails_before_execution(tmp_path) -> None:
    marker = tmp_path / "command-executed"
    environment = os.environ.copy()
    environment["JSON2TS_CMD"] = f"/usr/bin/true; /usr/bin/touch {marker}"
    environment["JSON2TS_PACKAGE_JSON"] = str(tmp_path / "forged-package.json")
    environment["OUT"] = str(tmp_path / "api-types.ts")
    completed = subprocess.run(
        ["bash", "scripts/gen_ts_types.sh"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 2
    assert "legacy command overrides are forbidden" in completed.stderr
    assert not marker.exists()

# Public surface the frontend relies on. Keep alphabetically sorted to
# minimise merge noise when adding new models.
EXPECTED_MODELS = sorted(
    [
        "AnswerDone",
        "AskMeta",
        "AskRequest",
        "AssessRequest",
        "CandidateMapping",
        "CheckoutBody",
        "CheckoutResponse",
        "CompaniesResponse",
        "Company",
        "CookieConsent",
        "DailyResponse",
        "DiscoveriesResponse",
        "ErrorReportBody",
        "HistoryRecord",
        "HistoryRecordRequest",
        "HistoryResponse",
        "KBCard",
        "MappingRequest",
        "MappingResponse",
        "Phase",
        "PhasesResponse",
        "PhenomenonResponse",
        "PrivacyDeleteRequest",
        "PrivacyDeleteResponse",
        "PrivacyExportRequest",
        "PrivacyExportResponse",
        "ProblemDetailEnvelope",
        "SearchRequest",
        "SearchResponse",
        "SearchResult",
        "SubscribeBody",
        "SynthesizeRequest",
        "Verdict",
    ]
)


def _load_schemas_module():
    """Load `web/backend/schemas.py` by path so the test doesn't require
    PYTHONPATH gymnastics or the full FastAPI app import chain.
    """
    spec = importlib.util.spec_from_file_location(
        "structural_schemas_under_test", SCHEMAS_PATH
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_schemas_file_exists() -> None:
    assert SCHEMAS_PATH.exists(), f"missing {SCHEMAS_PATH}"


def test_generated_ts_file_exists() -> None:
    assert TS_PATH.exists(), (
        f"missing {TS_PATH} — run `bash scripts/gen_ts_types.sh`"
    )


def test_generated_ts_is_non_empty() -> None:
    content = TS_PATH.read_text(encoding="utf-8")
    assert len(content) > 200, "api-types.ts looks suspiciously small"
    assert "tslint:disable" in content or "eslint-disable" in content, (
        "expected the pydantic2ts boilerplate header"
    )


def test_generated_ts_describes_legacy_surfaces_as_retired() -> None:
    """Generated comments are public API copy, not harmless source notes."""
    content = TS_PATH.read_text(encoding="utf-8")
    lowered = content.lower()

    for forbidden in (
        "phase 1 mock code",
        "always '123456'",
        'always "123456"',
        "self-service dsar",
        "mock-stripe checkout body",
    ):
        assert forbidden not in lowered, (
            f"stale public contract {forbidden!r}; regenerate from schemas.py"
        )

    assert re.search(r"mock[\s_-]*code", content, re.IGNORECASE) is None, (
        "generated public types must not describe a retired verification "
        "fixture as a mock-code authentication flow"
    )

    assert "Production returns HTTP 410 and has no checkout" in content
    assert "Legacy development-only query shape for GET /api/privacy/export" in content
    assert "Legacy development-only query shape for DELETE /api/privacy/delete" in content


def _ts_interface_fields(content: str, model_name: str) -> set[str]:
    match = re.search(
        rf"^export interface {re.escape(model_name)} \{{(.*?)^\}}$",
        content,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"generated interface {model_name!r} missing"
    return set(re.findall(r"^  ([A-Za-z_][A-Za-z0-9_]*)\??:", match.group(1), re.MULTILINE))


def test_legacy_shared_models_are_the_runtime_response_models() -> None:
    """The TS source models must be the route models, not stale mirrors."""
    backend = REPO_ROOT / "web" / "backend"
    sys.path.insert(0, str(backend))
    try:
        import schemas as canonical  # noqa: WPS433
        from api import checkout_mock  # noqa: WPS433
        from api.privacy import delete, export  # noqa: WPS433

        assert checkout_mock.LegacyCheckoutResponse is canonical.CheckoutResponse
        assert export.LegacyPrivacyExportResponse is canonical.PrivacyExportResponse
        assert delete.LegacyPrivacyDeleteResponse is canonical.PrivacyDeleteResponse
    finally:
        try:
            sys.path.remove(str(backend))
        except ValueError:
            pass


def test_generated_legacy_response_field_sets_match_runtime_contracts() -> None:
    content = TS_PATH.read_text(encoding="utf-8")
    expected = {
        "CheckoutResponse": {
            "status", "reason", "customer_id", "checkout_session_id",
            "tier", "interval", "amount_usd",
        },
        "PrivacyExportResponse": {
            "ok", "exported_at", "email", "session_id", "data",
        },
        "PrivacyDeleteResponse": {
            "ok", "deleted_at", "removed", "email_confirmation",
        },
    }
    for model_name, fields in expected.items():
        assert _ts_interface_fields(content, model_name) == fields


@pytest.mark.parametrize("model_name", EXPECTED_MODELS)
def test_pydantic_model_present(model_name: str) -> None:
    """Every model the frontend imports must exist in schemas.py."""
    mod = _load_schemas_module()
    assert hasattr(mod, model_name), (
        f"schemas.py missing public model {model_name!r}"
    )


@pytest.mark.parametrize("model_name", EXPECTED_MODELS)
def test_ts_interface_present(model_name: str) -> None:
    """Every Pydantic model must surface as an exported TS interface."""
    content = TS_PATH.read_text(encoding="utf-8")
    pattern = rf"^export\s+(interface|type)\s+{re.escape(model_name)}\b"
    assert re.search(pattern, content, re.MULTILINE), (
        f"api-types.ts missing exported interface {model_name!r} — "
        f"regenerate with `bash scripts/gen_ts_types.sh`"
    )


def test_ts_export_count_floor() -> None:
    """Belt-and-braces floor: at least 15 TS exports.

    Catches degenerate cases where the generator wrote a near-empty file
    because the schemas module failed to load (without surfacing the
    error in CI).
    """
    content = TS_PATH.read_text(encoding="utf-8")
    matches = re.findall(
        r"^export\s+(?:interface|type)\s+\w+", content, re.MULTILINE
    )
    assert len(matches) >= 15, (
        f"only {len(matches)} TS exports — expected >= 15"
    )


def test_no_any_for_critical_fields() -> None:
    """Spot-check: AskRequest.query and CheckoutBody.email must be typed
    as `string`, not `any`. Catches accidental loosening from the
    Pydantic side (e.g. switching to `Field(...)` with no type).
    """
    content = TS_PATH.read_text(encoding="utf-8")
    # Find AskRequest block and check `query` is string
    ask = re.search(
        r"interface AskRequest \{([^}]*)\}", content, re.DOTALL
    )
    assert ask, "AskRequest block missing"
    assert re.search(r"\bquery\s*:\s*string\b", ask.group(1)), (
        "AskRequest.query should be `string`"
    )

    checkout = re.search(
        r"interface CheckoutBody \{([^}]*)\}", content, re.DOTALL
    )
    assert checkout, "CheckoutBody block missing"
    assert re.search(r"\bemail\s*:\s*string\b", checkout.group(1)), (
        "CheckoutBody.email should be `string`"
    )
