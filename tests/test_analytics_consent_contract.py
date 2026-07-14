"""Fail-closed privacy contract for optional beta analytics."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "web" / "frontend"

AUTH_OR_NONPUBLIC = {
    "auth-callback.html",
    "auth-login.html",
    "auth-verify.html",
    "redesign-mockups/variant-a-perplexity-white.html",
    "redesign-mockups/variant-b-perplexity-ink.html",
}


def _relative_html() -> dict[str, str]:
    return {
        str(path.relative_to(FRONTEND)): path.read_text(encoding="utf-8")
        for path in FRONTEND.rglob("*.html")
    }


def test_every_public_beta_page_uses_consent_loader() -> None:
    pages = _relative_html()
    public = {
        name: text for name, text in pages.items() if name not in AUTH_OR_NONPUBLIC
    }

    assert len(public) == 27
    assert all(
        text.count('/assets/js/analytics-consent.js') == 1
        for text in public.values()
    )
    assert all(
        'src="https://plausible.bytedance.city/js/script.js"' not in text
        for text in pages.values()
    )
    assert all("plausible.bytedance.city" not in text for text in pages.values())
    assert "data-analytics-settings" in pages["thank-you.html"]


def test_consent_loader_is_explicit_dnt_first_and_fail_closed() -> None:
    source = (FRONTEND / "assets/js/analytics-consent.js").read_text(
        encoding="utf-8"
    )

    assert "navigator.doNotTrack" in source
    assert "analyticsRouteIsSafe()" in source
    for route in ("analyze", "reports", "report"):
        assert f"/^\\/{route}(?:\\.html)?(?:\\/|$)/" in source
    assert "dntEnabled()" in source
    assert "saveChoice(false, 'dnt')" in source
    assert "if (!analyticsRouteIsSafe() || dntEnabled() || document.getElementById(SCRIPT_ID)) return" in source
    assert "if (!saveChoice(analytics, 'explicit'))" in source
    assert "unloadPlausible();" in source
    assert "data-analytics-choice" in source
    assert "data-analytics-settings" in source
    assert "window.location.assign('/privacy#analytics')" in source
    assert "structural.lang" in source
    assert "You decide whether to share anonymous usage data" in source
    assert "beta.structural.bytedance.city" in source
    assert "plausible.bytedance.city/js/script.js" in source


def test_consent_controls_are_bilingual_and_touch_sized() -> None:
    strings = json.loads(
        (FRONTEND / "assets/data/i18n/ui.json").read_text(encoding="utf-8")
    )
    for key in (
        "analytics.title",
        "analytics.body",
        "analytics.privacy",
        "analytics.essential",
        "analytics.allow",
        "analytics.settings",
    ):
        assert strings[key]["zh"].strip()
        assert strings[key]["en"].strip()

    css = (FRONTEND / "assets/css/common.css").read_text(encoding="utf-8")
    responsive = (FRONTEND / "assets/css/responsive.css").read_text(
        encoding="utf-8"
    )
    chrome = (FRONTEND / "assets/js/site-chrome.js").read_text(encoding="utf-8")
    assert ".analytics-consent" in css
    assert "min-height: 44px" in css
    privacy_link_rule = css.split(".analytics-consent__copy a {", 1)[1].split("}", 1)[0]
    assert "display: inline-flex" in privacy_link_rule
    assert "align-items: center" in privacy_link_rule
    assert "min-height: 44px" in privacy_link_rule
    assert "@media (max-width: 640px)" in css
    assert "@media (max-width: 360px)" in responsive
    assert 'data-analytics-settings data-i18n="analytics.settings"' in chrome


def test_privacy_copy_does_not_promise_unimplemented_calendar_retention() -> None:
    policy = (ROOT / "docs/privacy-policy.md").read_text(encoding="utf-8")
    normalized_policy = " ".join(policy.split())
    phase = (ROOT / "web/phase-detector/app/privacy/page.tsx").read_text(
        encoding="utf-8"
    )

    assert "Frontend error logs are retained for up to 90 days" not in policy
    assert "Nginx access logs are retained for 14 days" not in policy
    assert "does not promise a fixed calendar retention period" in normalized_policy
    assert "no fixed public calendar period is promised" in normalized_policy
    assert "错误日志：<strong>90 天</strong>" not in phase
    assert "Nginx 访问日志：<strong>14 天</strong>" not in phase
    assert phase.count("不承诺固定天数") == 2


def test_analytics_never_derives_identifiers_from_user_query_text() -> None:
    ask = (FRONTEND / "assets/js/ask.js").read_text(encoding="utf-8")

    for forbidden in (
        "query_hash",
        "computeQueryHash",
        "fallbackHash",
        "crypto.subtle",
    ):
        assert forbidden not in ask

    assert "phenomenon_id" in ask
    assert "position: position" in ask
    assert "surface: surface" in ask


def test_report_capability_page_defends_referrer_in_html() -> None:
    report = (FRONTEND / "report.html").read_text(encoding="utf-8")

    assert '<meta name="referrer" content="no-referrer">' in report
    assert 'content="strict-origin-when-cross-origin"' not in report
    assert '/assets/js/report.js?v=20260714n2' in report
    assert '/assets/js/analytics-consent.js?v=20260714n2' in report
