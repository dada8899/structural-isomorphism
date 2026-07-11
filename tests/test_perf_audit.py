from scripts.perf_audit import INIT_SCRIPT, NAV_INTERACTION, PAGES, compute_inp_proxy


def test_every_route_uses_the_responsive_visible_navigation_interaction():
    assert ":visible" in NAV_INTERACTION
    assert "cmdk-trigger-desktop" in NAV_INTERACTION
    assert "mobile-nav-toggle" in NAV_INTERACTION
    assert all(selector == NAV_INTERACTION for _, _, selector in PAGES)


def test_route_audit_excludes_separately_tested_first_visit_overlays():
    assert "phase_tour_seen" in INIT_SCRIPT
    assert "cookie_consent_v1" in INIT_SCRIPT
    assert "analytics: false" in INIT_SCRIPT


def test_compute_inp_proxy_ignores_loading_loaf_and_untrusted_events():
    events = [
        {"startTime": 100, "duration": 900, "interactionId": 0},
        {"startTime": 1100, "duration": 80, "interactionId": 7},
    ]
    loaf = [
        {"start": 200, "duration": 700},
        {"start": 1080, "duration": 140},
    ]

    assert compute_inp_proxy(events, loaf, 1000, 1600) == 140


def test_compute_inp_proxy_requires_a_valid_interaction_window():
    events = [{"startTime": 100, "duration": 50, "interactionId": 1}]

    assert compute_inp_proxy(events, [], 200, 100) == 0
    assert compute_inp_proxy(events, [], 200, 300) == 0


def test_compute_inp_proxy_excludes_loaf_outside_window_boundaries():
    loaf = [
        {"start": 50, "duration": 49},
        {"start": 301, "duration": 100},
        {"start": 90, "duration": 20},
    ]

    assert compute_inp_proxy([], loaf, 100, 300) == 20
