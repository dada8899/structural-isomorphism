"""The shared SSO router must load under both beta and Phase import layouts."""

import importlib
from pathlib import Path


def test_phase_api_imports_shared_sso_router() -> None:
    module = importlib.import_module("v4.product.d1_phase_detector.api.main")
    assert module.app.title


def test_phase_deploy_tracks_shared_auth_dependencies() -> None:
    workflow = (Path(__file__).parents[1] / ".github/workflows/deploy-phase-detector.yml").read_text()
    for dependency in (
        "web/backend/api/auth.py",
        "web/backend/api/sso.py",
        "web/backend/api/favorites.py",
        "web/backend/api/report_account.py",
        "web/backend/auth/**",
        "web/backend/errors.py",
        "web/backend/services/account_data_registry.py",
        "web/backend/services/auth_store.py",
        "web/backend/services/candidate_origin.py",
        "web/backend/services/report_store.py",
        "web/backend/services/sqlite_utils.py",
        "web/backend/services/sso_store.py",
    ):
        assert f"- '{dependency}'" in workflow


def test_phase_dependency_contract_builds_the_account_registry() -> None:
    workflow = (Path(__file__).parents[1] / ".github/workflows/deploy-phase-detector.yml").read_text()
    assert "from web.backend.api.auth import _account_registry" in workflow
    assert "_account_registry().manifest()" in workflow


def test_phase_runtime_locks_shared_account_dependencies() -> None:
    requirements = (
        Path(__file__).parents[1] / "v4/product/d1_phase_detector/api/requirements.txt"
    ).read_text().splitlines()
    assert "starlette==0.46.2" in requirements
    assert "PyJWT==2.12.1" in requirements
    assert "slowapi==0.1.9" in requirements
    assert "structlog==25.5.0" in requirements


def test_phase_deploy_checks_the_beta_env_target_mode() -> None:
    script = (Path(__file__).parents[1] / "scripts/deploy-phase-detector-vps.sh").read_text()
    assert "stat -Lc '%a' \"$BETA_ENV_FILE\"" in script


def test_phase_package_can_build_the_full_account_deletion_registry() -> None:
    auth = importlib.import_module("web.backend.api.auth")
    registry = auth._account_registry()
    assert [asset["name"] for asset in registry.manifest()] == [
        "favorites", "claimed_reports", "authentication",
    ]
