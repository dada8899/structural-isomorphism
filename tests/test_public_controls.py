from scripts.check_public_controls import run
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_control_contract() -> None:
    controls, errors = run()
    assert len(controls) >= 100
    assert errors == []


def test_inventory_has_links_and_buttons() -> None:
    controls, _ = run()
    assert any(item["tag"] == "a" for item in controls)
    assert any(item["tag"] == "button" for item in controls)


def test_workbench_requires_fingerprint_and_candidate_confirmation() -> None:
    ask = (ROOT / "web/frontend/assets/js/ask.js").read_text(encoding="utf-8")
    page = (ROOT / "web/frontend/index.html").read_text(encoding="utf-8")
    assert "openFingerprintReview(q)" in ask
    assert "structural_pending_fingerprint" in ask
    assert "item._selectedCandidateId" in ask
    assert "系统不会替你默认选择 Top 1" in ask
    assert 'id="ask-fingerprint-confirm"' in page


def test_phase_build_is_network_independent() -> None:
    layout = (ROOT / "web/phase-detector/app/layout.tsx").read_text(encoding="utf-8")
    assert 'from "next/font/local"' in layout
    assert "next/font/google" not in layout


def test_phase_auth_navigation_is_wired_and_fail_closed() -> None:
    top_nav = (ROOT / "web/phase-detector/components/TopNav.tsx").read_text(encoding="utf-8")
    auth_nav = (ROOT / "web/phase-detector/components/AuthNav.tsx").read_text(encoding="utf-8")
    production_env = (ROOT / "web/phase-detector/.env.production").read_text(encoding="utf-8")
    assert 'import AuthNav from "./AuthNav"' in top_nav
    assert '<AuthNav variant="compact" />' in top_nav
    assert '<AuthNav variant="drawer" />' in top_nav
    assert 'process.env.NEXT_PUBLIC_AUTH_ENABLED !== "true"' in auth_nav
    assert 'href="/auth/login"' in auth_nav
    assert "NEXT_PUBLIC_AUTH_ENABLED=false" in production_env
