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
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_PATH = REPO_ROOT / "web" / "backend" / "schemas.py"
TS_PATH = REPO_ROOT / "web" / "phase-detector" / "lib" / "api-types.ts"

# Public surface the frontend relies on. Keep alphabetically sorted to
# minimise merge noise when adding new models.
EXPECTED_MODELS = sorted(
    [
        "AnswerDone",
        "AskMeta",
        "AskRequest",
        "AssessRequest",
        "CheckoutBody",
        "CheckoutResponse",
        "CompaniesResponse",
        "Company",
        "CookieConsent",
        "ErrorReportBody",
        "HistoryRecord",
        "HistoryRecordRequest",
        "HistoryResponse",
        "KBCard",
        "MappingRequest",
        "Phase",
        "PhasesResponse",
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
