"""The shared SSO router must load under both beta and Phase import layouts."""

import importlib


def test_phase_api_imports_shared_sso_router() -> None:
    module = importlib.import_module("v4.product.d1_phase_detector.api.main")
    assert module.app.title
