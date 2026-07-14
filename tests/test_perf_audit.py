import json
import subprocess

import pytest

from scripts.perf_audit import (
    ARM_TRUSTED_INTERACTION_SCRIPT,
    INIT_SCRIPT,
    INP_MODE_EVENT_TIMING,
    INP_MODE_THRESHOLD_BOUND,
    NAV_INTERACTION,
    PAGES,
    READ_TRUSTED_INTERACTION_SCRIPT,
    compute_inp_proxy,
)


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
        {"name": "click", "startTime": 100, "duration": 900, "interactionId": 0},
        {"name": "click", "startTime": 1100, "duration": 80, "interactionId": 7},
    ]
    loaf = [
        {"start": 200, "duration": 700},
        {"start": 1080, "duration": 140},
    ]

    assert compute_inp_proxy(
        events, loaf, 1000, 1600,
        trusted_interaction_count=1, event_timing_supported=True,
    ) == (140, INP_MODE_EVENT_TIMING)


def test_compute_inp_proxy_requires_a_valid_interaction_window():
    events = [{
        "name": "click", "startTime": 100, "duration": 50, "interactionId": 1,
    }]

    with pytest.raises(ValueError, match="window"):
        compute_inp_proxy(
            events, [], 200, 100,
            trusted_interaction_count=1, event_timing_supported=True,
        )
    with pytest.raises(ValueError, match="evidence"):
        compute_inp_proxy(
            events, [], 200, 300,
            trusted_interaction_count=0, event_timing_supported=True,
        )
    with pytest.raises(ValueError, match="evidence"):
        compute_inp_proxy(
            events, [], 200, 300,
            trusted_interaction_count=2, event_timing_supported=True,
        )


def test_compute_inp_proxy_excludes_loaf_outside_window_boundaries():
    loaf = [
        {"start": 50, "duration": 49},
        {"start": 301, "duration": 100},
        {"start": 90, "duration": 20},
    ]

    assert compute_inp_proxy(
        [], loaf, 100, 300,
        trusted_interaction_count=1, event_timing_supported=True,
    ) == (20, INP_MODE_THRESHOLD_BOUND)


def test_fast_trusted_click_without_event_entry_never_reports_zero():
    assert compute_inp_proxy(
        [], [], 100, 300,
        trusted_interaction_count=1, event_timing_supported=True,
    ) == (16, INP_MODE_THRESHOLD_BOUND)
    assert compute_inp_proxy(
        [], [{"start": 120, "duration": 35}], 100, 300,
        trusted_interaction_count=1, event_timing_supported=True,
    ) == (35, INP_MODE_THRESHOLD_BOUND)


def test_long_eligible_event_with_zero_interaction_id_is_conservative():
    events = [{
        "name": "pointerup", "startTime": 150, "duration": 800,
        "interactionId": 0,
    }]
    assert compute_inp_proxy(
        events, [], 100, 300,
        trusted_interaction_count=1, event_timing_supported=True,
    ) == (800, INP_MODE_EVENT_TIMING)


def test_loaf_first_ui_timestamp_is_merged_conservatively():
    loaf = [{
        "start": 500, "duration": 90, "firstUIEventTimestamp": 150,
    }]
    assert compute_inp_proxy(
        [], loaf, 100, 300,
        trusted_interaction_count=1, event_timing_supported=True,
    ) == (90, INP_MODE_THRESHOLD_BOUND)


def test_init_script_flushes_queued_event_observer_records():
    runner = r"""
global.window = global;
global.localStorage = { setItem() {} };
global.performance = { timeOrigin: 0, now: () => 100 };
global.PerformanceEventTiming = function PerformanceEventTiming() {};
const observers = [];
class FakePerformanceObserver {
  constructor(callback) {
    this.callback = callback;
    this.records = [];
    observers.push(this);
  }
  observe(options) { this.options = options; }
  takeRecords() {
    const records = this.records;
    this.records = [];
    return records;
  }
}
FakePerformanceObserver.supportedEntryTypes = ['event'];
global.PerformanceObserver = FakePerformanceObserver;
eval(process.argv[1]);
const observer = observers.find(item => item.options?.type === 'event');
const loafObserver = observers.find(
  item => item.options?.type === 'long-animation-frame'
);
observer.records.push({
  name: 'click', duration: 24, processingStart: 10,
  startTime: 8, interactionId: 7,
});
loafObserver.records.push({
  startTime: 4, duration: 60, firstUIEventTimestamp: 12,
});
const flushed = window.__perf.flushEventRecords();
const flushedLoaf = window.__perf.flushLoafRecords();
console.log(JSON.stringify({
  flushed,
  flushedLoaf,
  remaining: observer.records.length,
  events: window.__perf.events,
  loaf: window.__perf.loaf,
  supported: window.__perf.eventTimingSupported,
  threshold: window.__perf.eventTimingThresholdMs,
}));
"""
    completed = subprocess.run(
        ["node", "-e", runner, INIT_SCRIPT], text=True,
        capture_output=True, check=True,
    )
    result = json.loads(completed.stdout)
    assert result == {
        "flushed": 1,
        "flushedLoaf": 1,
        "remaining": 0,
        "events": [{
            "name": "click", "duration": 24, "processingStart": 10,
            "startTime": 8, "interactionId": 7,
        }],
        "loaf": [{
            "start": 4, "duration": 60, "firstUIEventTimestamp": 12,
        }],
        "supported": True,
        "threshold": 16,
    }


def test_trusted_click_handshake_rejects_untrusted_dispatch():
    runner = r"""
global.window = global;
let now = 100;
global.performance = { now: () => ++now };
window.__perf = {
  trustedInteractionCount: 0,
  trustedPointerDownTimestamp: 0,
  trustedPointerUpTimestamp: 0,
  trustedInteractionTimestamp: 0,
  trustedInteractionArmed: false,
};
class FakeElement {
  constructor() { this.handlers = {}; }
  addEventListener(name, handler) { this.handlers[name] = handler; }
  removeEventListener(name, handler) {
    if (this.handlers[name] === handler) this.handlers[name] = null;
  }
  dispatch(name, isTrusted) {
    const handler = this.handlers[name];
    if (handler) handler({ isTrusted });
  }
}
const arm = eval(`(${process.argv[1]})`);
const read = eval(`(${process.argv[2]})`);
const element = new FakeElement();
const armed = arm(element);
element.dispatch('pointerdown', false);
element.dispatch('pointerup', false);
element.dispatch('click', false);
const afterUntrusted = read(element);
element.dispatch('pointerdown', true);
element.dispatch('pointerup', true);
element.dispatch('click', true);
const afterTrusted = read(element);
element.dispatch('pointerdown', true);
element.dispatch('pointerup', true);
element.dispatch('click', true);
const afterSecondTrusted = read(element);
console.log(JSON.stringify({
  armed, afterUntrusted, afterTrusted, afterSecondTrusted,
}));
"""
    completed = subprocess.run(
        [
            "node", "-e", runner,
            ARM_TRUSTED_INTERACTION_SCRIPT,
            READ_TRUSTED_INTERACTION_SCRIPT,
        ],
        text=True, capture_output=True, check=True,
    )
    result = json.loads(completed.stdout)
    assert result["armed"] == {"armed": True}
    assert result["afterUntrusted"] == {
        "count": 0, "pointerDownTimestamp": 0, "pointerUpTimestamp": 0,
        "timestamp": 0, "armed": True,
    }
    assert result["afterTrusted"] == {
        "count": 1, "pointerDownTimestamp": 101, "pointerUpTimestamp": 102,
        "timestamp": 103, "armed": False,
    }
    assert result["afterSecondTrusted"] == result["afterTrusted"]
