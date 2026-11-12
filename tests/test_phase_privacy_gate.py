"""Independent release gate for Phase privacy boundaries."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_phase_waitlist_neither_sends_nor_persists_referrer() -> None:
    form = _read("web/phase-detector/components/WaitlistForm.tsx")
    api = _read("v4/product/d1_phase_detector/api/main.py")
    assert "document.referrer" not in form
    assert 'form.set("referrer"' not in form
    assert 'if "referrer" in submitted' in api
    assert "referrer is not accepted" in api
    assert "UPDATE waitlist SET referrer = NULL" in api
    assert "INSERT INTO waitlist (email, source, placement, referrer)" not in api


def test_phase_analytics_is_route_event_and_property_allowlisted() -> None:
    analytics = _read("web/phase-detector/lib/analytics.ts")
    consent = _read("web/phase-detector/components/CookieConsent.tsx")
    package = _read("web/phase-detector/package.json")
    lock = _read("web/phase-detector/pnpm-lock.yaml")
    tracker = _read("web/phase-detector/components/NewsletterLinkTracker.tsx")
    pricing = _read("web/phase-detector/components/PricingTable.tsx")
    onboarding = _read("web/phase-detector/components/OnboardingTour.tsx")
    for route in (
        '"/about"', '"/backtest"', '"/companies"', '"/compare"',
        '"/methodology"', '"/newsletter"', '"/offline"', '"/pricing"',
        '"/universality"', '"/zh"',
    ):
        assert route in analytics
    assert "PUBLIC_ANALYTICS_ROUTES" in analytics
    assert "PUBLIC_DYNAMIC_ANALYTICS_ROUTES" in analytics
    assert "SENSITIVE_ROUTE" not in analytics
    assert "function publicAnalyticsPath(" in analytics
    assert "PUBLIC_ANALYTICS_ROUTES.has(canonical)" in analytics
    assert "PUBLIC_DYNAMIC_ANALYTICS_ROUTES.has(canonical)" in analytics
    assert "PHASE_DETECTOR_TICKERS.map" in analytics
    assert "ISSUES.map" in analytics
    assert "PHASE_DETECTOR_UNIVERSALITY_CLASSES.map" in analytics
    assert "EVENT_PROP_ALLOWLIST" in analytics
    assert "export function normalizeAnalyticsPath(" in analytics
    assert "MAX_PATH_DECODE_ROUNDS = 3" in analytics
    assert "decodeURIComponent(decoded)" in analytics
    assert 'decoded.includes("//")' in analytics
    assert 'segment === "." || segment === ".."' in analytics
    assert "sanitizeAnalyticsEvent(name, props)" in analytics
    assert "if (!safeUrl) return" in analytics
    assert "allowed.has(key)" in analytics
    assert "canonicalAnalyticsUrl" in analytics
    assert "url: safeUrl" in analytics
    assert "analyticsRouteIsSafe(pathname)" in consent
    assert 'import("@plausible-analytics/tracker")' in consent
    assert '"@plausible-analytics/tracker": "0.4.5"' in package
    assert "@plausible-analytics/tracker" in lock and "0.4.5" in lock
    package_resolutions = lock[lock.index("packages:"):lock.index("snapshots:")]
    assert "'@plausible-analytics/tracker@0.4.5':" in package_resolutions
    assert (
        "resolution: {integrity: "
        "sha512-6BfAGejXY+YA3Cw6LYT2Zpn4hTxDtPQAawFsYUsQCOg78wIS5C4deAGXTfJffa5VleMWITv5lpJ/EYuQBl1tPA==}"
        in package_resolutions
    )
    assert 'endpoint: PLAUSIBLE_ENDPOINT' in consent
    assert "autoCapturePageviews: false" in consent
    assert "transformRequest: privacyTransform" in consent
    assert "bindToWindow: true" in consent
    assert 'tracker.track("pageview", { url: safeUrl })' in consent
    assert "/js/script.js" not in consent
    assert "document.createElement" not in consent
    assert "analyticsTransportEnabled = false" in consent
    assert "window.plausible = blockedPlausible" in consent
    assert "u: safeUrl" in consent
    assert "d: PLAUSIBLE_DOMAIN" in consent
    assert "sanitizeAnalyticsEvent(raw.n, raw.p)" in consent
    assert "safe.p = Object.fromEntries" in consent
    assert "safe.v = raw.v" in consent
    assert "...payload" not in consent
    assert "function installAnalyticsFetchGuard" in consent
    assert "normalizeAnalyticsPath," in consent
    assert "function normalizedAnalyticsHostname(" in consent
    assert '.replace(/\\.+$/, "")' in consent
    assert "function effectiveAnalyticsPort(" in consent
    assert "function equivalentAnalyticsAuthority(" in consent
    assert 'typeof candidate.url === "string"' in consent
    assert 'typeof candidate.href === "string"' in consent
    assert "if (!requestHostname) return baseFetch(input, init)" in consent
    assert "requestHostname !== protectedHostname" in consent
    assert "!equivalentAuthority" in consent
    assert "const requestPath = normalizeAnalyticsPath(requestUrl.pathname)" in consent
    assert "const protectedPath = normalizeAnalyticsPath(protectedEndpoint.pathname)" in consent
    assert "if (!requestPath || !protectedPath) return ignoredAnalyticsResponse()" in consent
    assert "requestPath !== protectedPath" in consent
    assert "requestTarget.raw !== protectedEndpoint.href" in consent
    assert "requestUrl.href !== protectedEndpoint.href" in consent
    assert "return baseFetch(input, init)" in consent
    assert "!analyticsTransportEnabled || !analyticsRouteIsSafe()" in consent
    assert "const safePayload = privacyTransform(payload)" in consent
    assert "if (!safePayload) return ignoredAnalyticsResponse()" in consent
    assert "window.fetch = guardedFetch" in consent
    request_target = consent[
        consent.index("function analyticsRequestTarget(") : consent.index(
            "\n}\n\nfunction installAnalyticsFetchGuard",
            consent.index("function analyticsRequestTarget("),
        )
    ]
    assert "input instanceof URL" not in request_target
    assert "input instanceof Request" not in request_target
    initialize = consent[consent.index("function initializedTracker"):consent.index(
        "\n}\n\nfunction loadPlausible", consent.index("function initializedTracker")
    )]
    assert initialize.index("installAnalyticsFetchGuard()") < initialize.index(
        "tracker.init("
    )
    transform = consent[consent.index("function privacyTransform"):consent.index(
        "\n}\n\nfunction ignoredAnalyticsResponse", consent.index("function privacyTransform")
    )]
    assert "isDNT()" in transform
    for raw_field in ("referrer", "ref"):
        assert raw_field not in transform
    assert "safe.r" not in transform
    sanitizer = "sanitizeAnalyticsEvent"
    assert f"export function {sanitizer}(" in analytics
    assert analytics.count(f"{sanitizer}(name, props)") == 1
    assert consent.count(f"{sanitizer}(raw.n, raw.p)") == 1
    assert "destination: coarseDestination(dest)" in tracker
    assert "url: a.href" not in tracker
    assert "window.plausible" not in pricing
    assert "window.plausible" not in onboarding
    assert "trackEvent(Events.ResearchPreviewInterest" in pricing
    assert "trackEvent(name, props)" in onboarding


def test_phase_dnt_and_consent_schema_fail_closed_at_transport() -> None:
    consent = _read("web/phase-detector/components/CookieConsent.tsx")
    read_consent = consent[
        consent.index("function readConsent(") : consent.index(
            "\n}\n\nfunction writeConsent", consent.index("function readConsent(")
        )
    ]
    load = consent[
        consent.index("function loadPlausible(") : consent.index(
            "\n}\n\nfunction unloadPlausible", consent.index("function loadPlausible(")
        )
    ]
    persist = consent[
        consent.index("const persistAndApply") : consent.index(
            "\n\n  const acceptAll", consent.index("const persistAndApply")
        )
    ]
    guard = consent[
        consent.index("function installAnalyticsFetchGuard(") : consent.index(
            "\n}\n\nfunction initializedTracker", consent.index("function installAnalyticsFetchGuard(")
        )
    ]

    for required in (
        'typeof candidate.analytics !== "boolean"',
        "candidate.marketing !== false",
        "candidate.essential !== true",
        "!Number.isFinite(candidate.timestamp)",
    ):
        assert required in read_consent
    assert "isDNT()" in load
    assert "a && !isDNT()" in persist
    assert "isDNT() || !analyticsTransportEnabled" in guard
    assert "const acceptAll = () => persistAndApply(true)" in consent


def test_phase_company_route_registry_equals_product_artifact() -> None:
    artifact = json.loads(
        _read("v4/product/d1_phase_detector/data/ews_results.json")
    )
    sitemap_data = _read("web/phase-detector/lib/sitemap-data.ts")
    block = sitemap_data.split(
        "export const PHASE_DETECTOR_TICKERS: string[] = [", 1
    )[1].split("];", 1)[0]
    registered = re.findall(r'"([A-Z0-9.-]+)"', block)

    assert len(registered) == len(set(registered))
    assert registered == sorted(artifact)
    assert set(registered) == set(artifact)


def test_phase_api_has_content_free_request_correlation() -> None:
    main = _read("v4/product/d1_phase_detector/api/main.py")
    middleware = _read("v4/product/d1_phase_detector/api/privacy_middleware.py")
    assert "app.add_middleware(PrivacyRequestContextMiddleware)" in main
    assert "x-request-id" in middleware.lower()
    for allowed in ("request_id", "request_method", "route_template", "error_type"):
        assert f'"{allowed}"' in middleware
    for forbidden in ('scope.get("path"', "query_string", "referer", "user-agent"):
        assert forbidden not in middleware.lower()


def test_phase_runtime_requires_the_shared_privacy_hmac_root() -> None:
    example = _read("web/backend/.env.example")
    identifiers = _read("web/backend/services/privacy_identifiers.py")
    assert "STRUCTURAL_PRIVACY_HMAC_KEY=" in example
    assert "STRUCTURAL_PRIVACY_HMAC_KEY" in identifiers
    assert '_CANONICAL_KEY_RE = re.compile(r"^[0-9a-f]{64}$")' in identifiers
    assert "unquoted lowercase 64-hex" in identifiers
    assert "secrets.token_hex(32)" in example
    assert "identifier-key.v2" in identifiers
    assert 'f"{purpose}:v2:{digest}"' in identifiers
