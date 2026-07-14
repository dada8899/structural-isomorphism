"""
Performance audit — Core Web Vitals (LCP, CLS, INP, TBT) across phase-detector
pages and viewports.

Drives a real Chromium via Playwright; collects:
  * LCP via PerformanceObserver(type: 'largest-contentful-paint')
  * CLS via PerformanceObserver(type: 'layout-shift') with the standard
    session-window accumulation (we keep the running total which is the
    standard CLS metric for monitoring).
  * TBT (total blocking time) via PerformanceObserver(type: 'longtask')
    summing (duration - 50) across the FCP→TTI window. Practical proxy:
    we sum all longtasks during a fixed observation window (5s after load).
  * INP — proxied inside an explicit trusted-interaction window. The audit
    clicks a visible control through Playwright, then considers Event Timing
    entries with an interactionId and LoAF entries overlapping that window.
  * Transfer size + JS bytes via Performance.getEntries (resource).

Usage:
    .venv/bin/python scripts/perf_audit.py --base http://localhost:3017 \\
        --pages all --viewport both --out docs/performance/perf-audit.json

Pages list mirrors the W12-A accessibility audit so before/after comparisons
make sense.
"""
from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
import statistics
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

# 10 pages mirroring W12-A audit. Use the same real navigation interaction on
# every route so CI fixtures and responsive layouts remain comparable. The
# ``:visible`` clause selects Cmd+K on desktop and the menu toggle on mobile;
# a missing control is still a failed run rather than a synthetic 0 ms.
NAV_INTERACTION = (
    'button[data-testid="cmdk-trigger-desktop"]:visible, '
    'button[data-testid="mobile-nav-toggle"]:visible'
)
PAGES: list[tuple[str, str, str]] = [
    ("landing", "/", NAV_INTERACTION),
    ("companies", "/companies", NAV_INTERACTION),
    ("company_AAPL", "/company/AAPL", NAV_INTERACTION),
    ("universality", "/universality", NAV_INTERACTION),
    ("universality_class", "/universality/self_organized_criticality", NAV_INTERACTION),
    ("compare", "/compare?tickers=AAPL,TSLA", NAV_INTERACTION),
    ("pricing", "/pricing", NAV_INTERACTION),
    ("backtest", "/backtest", NAV_INTERACTION),
    ("about", "/about", NAV_INTERACTION),
    ("methodology", "/methodology", NAV_INTERACTION),
]

VIEWPORTS = {
    "desktop": {"width": 1280, "height": 800, "isMobile": False},
    "mobile": {"width": 390, "height": 844, "isMobile": True},
}

_EVIDENCE_ERROR_TYPES = frozenset({
    "AssertionError", "AttributeError", "AuditFailure", "Error", "Exception",
    "KeyError", "KeyboardInterrupt", "OSError", "RunFinalizationError",
    "RuntimeError", "SystemExit", "TimeoutError", "TypeError", "ValueError",
})
_EVIDENCE_METHODS = frozenset({
    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS",
})
_EVIDENCE_ROUTES = frozenset({
    "/api/analyze/stream", "/api/auth/me", "/api/discoveries",
    "/api/favorites", "/api/me/export", "/api/me/reports", "/api/search",
    "/api/search/assess", "/api/synthesize/stream",
})
EVENT_TIMING_THRESHOLD_MS = 16
PINNED_CHROMIUM_MAJOR = 147
PINNED_PLAYWRIGHT_VERSION = "1.59.0"
EVENT_TIMING_CALIBRATION = "chromium_147_threshold_16"
INP_MODE_EVENT_TIMING = "event_timing_observed"
INP_MODE_THRESHOLD_BOUND = "trusted_click_threshold_bound"


class RunFinalizationError(RuntimeError):
    """Evidence publication and browser cleanup both failed."""

    def __init__(self, publish_exc: BaseException, cleanup_exc: BaseException):
        super().__init__("run evidence publish and browser cleanup failed")
        self.publish_error_type = type(publish_exc).__name__
        self.cleanup_error_type = type(cleanup_exc).__name__


# Inject before any page script runs so we catch every relevant entry.
INIT_SCRIPT = r"""
// Audit route content and controls, not first-visit overlays. Onboarding and
// cookie consent have their own interaction tests; otherwise the late-mounted
// consent paragraph becomes the LCP element and measures CMP hydration rather
// than the requested route.
try { localStorage.setItem('phase_tour_seen', 'true'); } catch (e) {}
try {
  localStorage.setItem('cookie_consent_v1', JSON.stringify({
    essential: true, analytics: false, marketing: false, version: 1, timestamp: 0
  }));
} catch (e) {}

window.__perf = {
  lcp: 0,
  lcpElement: null,
  lcpElementText: null,
  cls: 0,
  clsEntries: [],
  longTasks: [],   // {start, duration}
  loaf: [],        // long animation frames
  loafObserver: null,
  flushLoafRecords: null,
  events: [],      // event timing entries
  eventTimingSupported: false,
  eventTimingThresholdMs: 16,
  eventObserver: null,
  flushEventRecords: null,
  trustedInteractionCount: 0,
  trustedPointerDownTimestamp: 0,
  trustedPointerUpTimestamp: 0,
  trustedInteractionTimestamp: 0,
  trustedInteractionArmed: false,
  navStart: performance.timeOrigin,
};

try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      // LCP keeps the latest (largest) candidate
      window.__perf.lcp = e.startTime;
      window.__perf.lcpElement = e.element ? (e.element.tagName + (e.element.id ? '#' + e.element.id : '')) : null;
      window.__perf.lcpElementText = e.element ? (e.element.textContent || '').trim().slice(0, 160) : null;
    }
  }).observe({ type: 'largest-contentful-paint', buffered: true });
} catch (e) {}

try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (!e.hadRecentInput) {
        window.__perf.cls += e.value;
        window.__perf.clsEntries.push({ value: e.value, startTime: e.startTime });
      }
    }
  }).observe({ type: 'layout-shift', buffered: true });
} catch (e) {}

try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      window.__perf.longTasks.push({ start: e.startTime, duration: e.duration });
    }
  }).observe({ type: 'longtask', buffered: true });
} catch (e) {}

try {
  const recordLoafEntries = (entries) => {
    for (const e of entries) {
      window.__perf.loaf.push({
        start: e.startTime,
        duration: e.duration,
        firstUIEventTimestamp: e.firstUIEventTimestamp || 0,
      });
    }
  };
  const loafObserver = new PerformanceObserver((list) => {
    recordLoafEntries(list.getEntries());
  });
  loafObserver.observe({ type: 'long-animation-frame', buffered: true });
  window.__perf.loafObserver = loafObserver;
  window.__perf.flushLoafRecords = () => {
    const records = loafObserver.takeRecords();
    recordLoafEntries(records);
    return records.length;
  };
} catch (e) {}

try {
  const supportsEventTiming = (
    typeof PerformanceEventTiming !== 'undefined'
    && Array.isArray(PerformanceObserver.supportedEntryTypes)
    && PerformanceObserver.supportedEntryTypes.includes('event')
  );
  if (!supportsEventTiming) throw new Error('event timing unsupported');
  const recordEventEntries = (entries) => {
    for (const e of entries) {
      window.__perf.events.push({
        name: e.name,
        duration: e.duration,
        processingStart: e.processingStart,
        startTime: e.startTime,
        interactionId: e.interactionId || 0,
      });
    }
  };
  const eventObserver = new PerformanceObserver((list) => {
    recordEventEntries(list.getEntries());
  });
  eventObserver.observe({
    type: 'event', buffered: true, durationThreshold: 16
  });
  window.__perf.eventObserver = eventObserver;
  window.__perf.eventTimingSupported = true;
  window.__perf.flushEventRecords = () => {
    const records = eventObserver.takeRecords();
    recordEventEntries(records);
    return records.length;
  };
} catch (e) {
  window.__perf.eventTimingSupported = false;
  window.__perf.eventObserver = null;
  window.__perf.flushEventRecords = null;
}
"""

ARM_TRUSTED_INTERACTION_SCRIPT = r"""
(element) => {
  const perf = window.__perf;
  if (!perf || perf.trustedInteractionArmed === true) return { armed: false };
  perf.trustedInteractionCount = 0;
  perf.trustedPointerDownTimestamp = 0;
  perf.trustedPointerUpTimestamp = 0;
  perf.trustedInteractionTimestamp = 0;
  perf.trustedInteractionArmed = true;
  const removeListeners = () => {
    element.removeEventListener('pointerdown', onTrustedPointerDown, true);
    element.removeEventListener('pointerup', onTrustedPointerUp, true);
    element.removeEventListener('click', onTrustedClick, true);
  };
  const onTrustedPointerDown = (event) => {
    if (event.isTrusted !== true) return;
    perf.trustedPointerDownTimestamp = performance.now();
  };
  const onTrustedPointerUp = (event) => {
    if (
      event.isTrusted !== true
      || perf.trustedPointerDownTimestamp <= 0
    ) return;
    perf.trustedPointerUpTimestamp = performance.now();
  };
  const onTrustedClick = (event) => {
    if (event.isTrusted !== true) return;
    const now = performance.now();
    if (
      perf.trustedPointerDownTimestamp <= 0
      || perf.trustedPointerUpTimestamp < perf.trustedPointerDownTimestamp
      || now < perf.trustedPointerUpTimestamp
    ) return;
    perf.trustedInteractionCount += 1;
    perf.trustedInteractionTimestamp = now;
    perf.trustedInteractionArmed = false;
    removeListeners();
  };
  element.addEventListener('pointerdown', onTrustedPointerDown, true);
  element.addEventListener('pointerup', onTrustedPointerUp, true);
  element.addEventListener('click', onTrustedClick, true);
  return { armed: true };
}
"""

READ_TRUSTED_INTERACTION_SCRIPT = r"""
(element) => {
  void element;
  const perf = window.__perf;
  const count = Number.isInteger(perf?.trustedInteractionCount)
    ? perf.trustedInteractionCount : 0;
  const timestamp = Number.isFinite(perf?.trustedInteractionTimestamp)
    ? perf.trustedInteractionTimestamp : 0;
  return {
    count,
    pointerDownTimestamp: perf?.trustedPointerDownTimestamp || 0,
    pointerUpTimestamp: perf?.trustedPointerUpTimestamp || 0,
    timestamp,
    armed: perf?.trustedInteractionArmed === true,
  };
}
"""

FLUSH_EVENT_TIMING_SCRIPT = r"""
async () => {
  const perf = window.__perf;
  await new Promise(resolve => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => setTimeout(resolve, 0));
    });
  });
  const flushedCount = typeof perf?.flushEventRecords === 'function'
    ? perf.flushEventRecords() : 0;
  const flushedLoafCount = typeof perf?.flushLoafRecords === 'function'
    ? perf.flushLoafRecords() : 0;
  const match = navigator.userAgent.match(/(?:HeadlessChrome|Chrome)\/(\d+)\./);
  const chromiumMajor = match ? Number(match[1]) : 0;
  return {
    eventTimingSupported: perf?.eventTimingSupported === true,
    eventTimingThresholdMs: perf?.eventTimingThresholdMs,
    trustedInteractionCount: perf?.trustedInteractionCount,
    flushedEventCount: flushedCount,
    flushedLoafCount,
    animationFrameFlushCount: 2,
    chromiumMajor,
  };
}
"""


def compute_tbt(long_tasks: list[dict[str, float]], fcp_ms: float, max_ms: float) -> float:
    """Total Blocking Time: sum(duration - 50) for longtasks within [FCP, TTI].

    We use [FCP, FCP + 5000] as the observation window since TTI is expensive to
    compute reliably from synthetic data.
    """
    tbt = 0.0
    for t in long_tasks:
        start = t["start"]
        dur = t["duration"]
        # Clip to observation window
        win_start = fcp_ms
        win_end = max_ms
        clipped_start = max(start, win_start)
        clipped_end = min(start + dur, win_end)
        if clipped_end <= clipped_start:
            continue
        effective = clipped_end - clipped_start
        if effective > 50:
            tbt += effective - 50
    return tbt


def compute_inp_proxy(
    events: list[dict[str, float]],
    loaf: list[dict[str, float]],
    window_start_ms: float,
    window_end_ms: float,
    *,
    trusted_interaction_count: int,
    event_timing_supported: bool,
    threshold_ms: float = EVENT_TIMING_THRESHOLD_MS,
) -> tuple[float, str]:
    """Return a conservative trusted-click INP proxy and its closed mode."""
    if window_end_ms <= window_start_ms:
        raise ValueError("invalid trusted interaction window")
    if trusted_interaction_count != 1 or event_timing_supported is not True:
        raise ValueError("trusted interaction evidence is required")
    if threshold_ms != EVENT_TIMING_THRESHOLD_MS:
        raise ValueError("unexpected Event Timing threshold")
    eligible_event_names = {"click", "pointerdown", "pointerup"}
    event_durations = [
        float(entry["duration"])
        for entry in events
        if entry.get("name") in eligible_event_names
        and float(entry.get("duration") or 0) >= threshold_ms
        and window_start_ms <= float(entry["startTime"]) <= window_end_ms
    ]
    loaf_durations = [
        float(entry["duration"])
        for entry in loaf
        if (
            (
                float(entry["start"]) <= window_end_ms
                and float(entry["start"]) + float(entry["duration"])
                >= window_start_ms
            )
            or window_start_ms
            <= float(entry.get("firstUIEventTimestamp") or 0)
            <= window_end_ms
        )
    ]
    if event_durations:
        return max(event_durations + loaf_durations), INP_MODE_EVENT_TIMING
    return (
        max([float(threshold_ms), *loaf_durations]),
        INP_MODE_THRESHOLD_BOUND,
    )


def collect_resource_sizes(resources: list[dict[str, Any]]) -> dict[str, float]:
    js_bytes = 0
    css_bytes = 0
    img_bytes = 0
    other_bytes = 0
    for r in resources:
        size = r.get("transferSize") or 0
        url = r.get("name", "")
        resource_path = urlsplit(url).path.lower()
        if resource_path.endswith(".js") or "/_next/static/chunks/" in resource_path:
            js_bytes += size
        elif resource_path.endswith(".css"):
            css_bytes += size
        elif any(
            resource_path.endswith(ext)
            for ext in (".png", ".jpg", ".jpeg", ".webp", ".avif", ".svg", ".gif")
        ):
            img_bytes += size
        else:
            other_bytes += size
    return {
        "js_kb": round(js_bytes / 1024, 1),
        "css_kb": round(css_bytes / 1024, 1),
        "img_kb": round(img_bytes / 1024, 1),
        "other_kb": round(other_bytes / 1024, 1),
        "total_kb": round((js_bytes + css_bytes + img_bytes + other_bytes) / 1024, 1),
    }


def _safe_route_path(value: Any) -> str:
    """Map request paths to the audit's closed route vocabulary."""
    try:
        path = urlsplit(str(value or "")).path
    except ValueError:
        return "/:unknown_api"
    return path if path in _EVIDENCE_ROUTES else "/:unknown_api"


def _safe_exception_type(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if name in _EVIDENCE_ERROR_TYPES else "unknown_error_type"


def _request_summary(setup_state: Any) -> dict[str, Any]:
    """Return bounded request evidence; never persist bodies, URLs, or values."""
    state = setup_state if isinstance(setup_state, dict) else {}
    api_counts = []
    for key, count in state.get("api_counts", {}).items():
        if not isinstance(key, tuple) or len(key) != 2 or type(count) is not int:
            continue
        method = str(key[0]).upper()
        api_counts.append({
            "method": method if method in _EVIDENCE_METHODS else "UNKNOWN",
            "path": _safe_route_path(key[1]),
            "count": max(0, count),
        })
    api_counts.sort(key=lambda item: (item["method"], item["path"]))
    return {
        "api_counts": api_counts,
        "invalid_api_count": len(state.get("invalid_api", [])),
        "unknown_request_count": len(state.get("unknown_requests", [])),
        "page_error_count": len(state.get("page_errors", [])),
        "bad_static_response_count": len(state.get("bad_static_responses", [])),
    }


def _run_error_sample(
    *,
    run_index: int,
    stage: str,
    code: str,
    exc: Exception | None,
    setup_state: Any,
    started: float,
    timings: dict[str, float],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = time.monotonic()
    evidence = {
        "run_index": run_index,
        "audit_status": "failed",
        "stage": stage,
        "error": code,
        "error_detail": {
            "code": code,
            "type": _safe_exception_type(exc) if exc is not None else None,
        },
        "timings_ms": {
            **timings,
            "elapsed": round((now - started) * 1000, 1),
        },
        "request_summary": _request_summary(setup_state),
    }
    if extra:
        evidence["error_detail"].update(extra)
    return evidence


def audit_one(
    p,
    base_url: str,
    path: str,
    viewport_name: str,
    viewport: dict[str, Any],
    interaction_selector: str,
    runs: int = 1,
    page_setup: Callable[[Any, str, int], Any] | None = None,
    ready_selector: str | None = None,
    page_validator: Callable[[Any, Any], None] | None = None,
    post_interaction_validator: Callable[[Any, Any, dict[str, Any]], None] | None = None,
    interaction_mode: str = "in_page",
    run_evidence_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if runs < 1:
        raise ValueError("runs must be at least 1")
    if interaction_mode not in {"in_page", "new_tab"}:
        raise ValueError("interaction_mode must be 'in_page' or 'new_tab'")
    results: list[dict[str, Any]] = []

    def upsert_evidence(sample: dict[str, Any]) -> None:
        """Publish one replay-safe state for a run and keep one memory row."""
        snapshot = copy.deepcopy(sample)
        if run_evidence_sink is not None:
            run_evidence_sink(copy.deepcopy(snapshot))
        for index, existing in enumerate(results):
            if existing.get("run_index") == snapshot.get("run_index"):
                results[index] = snapshot
                break
        else:
            results.append(snapshot)

    def is_cancellation(exc: BaseException) -> bool:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            return True
        members = getattr(exc, "exceptions", ())
        return isinstance(members, tuple) and any(
            is_cancellation(member) for member in members
        )

    def finalize_run(
        primary: dict[str, Any], browser: Any | None,
    ) -> None:
        """Checkpoint primary evidence before cleanup, then upsert its outcome.

        The pending checkpoint is deliberately durable before ``close``. A
        hung or killed cleanup therefore leaves an incomplete state that the
        release gate rejects, while retaining the primary stage and error.
        """
        primary_status = primary.get("audit_status", "failed")
        pending = {
            **primary,
            "primary_audit_status": primary_status,
            "audit_status": primary_status,
            "cleanup_status": "pending",
            "cleanup_attempted": browser is not None,
            "evidence_revision": 1,
        }
        try:
            upsert_evidence(pending)
        except BaseException as publish_exc:
            cleanup_exc: BaseException | None = None
            if browser is not None:
                try:
                    browser.close()
                except BaseException as exc:
                    cleanup_exc = exc
            if cleanup_exc is not None:
                if is_cancellation(cleanup_exc):
                    raise cleanup_exc from publish_exc
                if is_cancellation(publish_exc):
                    raise publish_exc from cleanup_exc
                raise RunFinalizationError(
                    publish_exc, cleanup_exc
                ) from publish_exc
            raise

        final = copy.deepcopy(pending)
        cleanup_exc: BaseException | None = None
        try:
            if browser is not None:
                browser.close()
        except BaseException as exc:
            cleanup_exc = exc
            final["audit_status"] = "failed"
            final["cleanup_status"] = "failed"
            final["cleanup_error"] = {
                "code": "browser_close_failed",
                "type": _safe_exception_type(exc),
            }
        else:
            final["cleanup_status"] = "passed"
        final["evidence_revision"] = 2
        try:
            upsert_evidence(final)
        except BaseException as publish_exc:
            if cleanup_exc is not None:
                if is_cancellation(cleanup_exc):
                    raise cleanup_exc from publish_exc
                if is_cancellation(publish_exc):
                    raise publish_exc from cleanup_exc
                raise RunFinalizationError(
                    publish_exc, cleanup_exc
                ) from publish_exc
            raise
        if cleanup_exc is not None and is_cancellation(cleanup_exc):
            raise cleanup_exc

    for run in range(runs):
        run_started = time.monotonic()
        stage_started = run_started
        timings: dict[str, float] = {}

        def mark(stage: str) -> None:
            nonlocal stage_started
            now = time.monotonic()
            timings[stage] = round((now - stage_started) * 1000, 1)
            stage_started = now

        browser = None
        try:
            browser = p.chromium.launch(headless=True)
            playwright_version = importlib.metadata.version("playwright")
            browser_major = int(str(browser.version).split(".", 1)[0])
            context = browser.new_context(
                viewport={"width": viewport["width"], "height": viewport["height"]},
                is_mobile=viewport["isMobile"],
                device_scale_factor=2 if viewport["isMobile"] else 1,
                # Throttle CPU 4x to simulate mid-tier mobile when on mobile viewport
            )
            # CPU throttling via CDP for mobile
            page = context.new_page()
            page.add_init_script(INIT_SCRIPT)
            mark("browser_setup")
        except Exception as exc:
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="browser_setup", code="browser_setup_failed",
                exc=exc, setup_state=None, started=run_started, timings=timings,
            ), browser)
            continue
        if (
            playwright_version != PINNED_PLAYWRIGHT_VERSION
            or browser_major != PINNED_CHROMIUM_MAJOR
        ):
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="browser_setup",
                code="event_timing_calibration_failed", exc=None,
                setup_state=None, started=run_started, timings=timings,
            ), browser)
            continue

        setup_state = None
        if page_setup is not None:
            try:
                setup_state = page_setup(page, viewport_name, run)
                mark("page_setup")
            except Exception as exc:
                finalize_run(_run_error_sample(
                    run_index=run + 1, stage="page_setup", code="page_setup_failed",
                    exc=exc, setup_state=setup_state, started=run_started,
                    timings=timings,
                ), browser)
                continue
        else:
            mark("page_setup")

        try:
            if viewport["isMobile"]:
                cdp = context.new_cdp_session(page)
                cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
                # Simulate slow 4G
                cdp.send(
                    "Network.emulateNetworkConditions",
                    {
                        "offline": False,
                        "latency": 150,
                        "downloadThroughput": 1.5 * 1024 * 1024 / 8,
                        "uploadThroughput": 750 * 1024 / 8,
                    },
                )
            mark("profile_setup")
        except Exception as exc:
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="profile_setup", code="profile_setup_failed",
                exc=exc, setup_state=setup_state, started=run_started,
                timings=timings,
            ), browser)
            continue

        url = f"{base_url}{path}"
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            status = response.status if response else 0
            mark("navigation")
        except Exception as exc:
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="navigation", code="navigation_failed",
                exc=exc, setup_state=setup_state, started=run_started,
                timings=timings,
            ), browser)
            continue
        if not 200 <= status < 300:
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="navigation", code="navigation_http_error",
                exc=None, setup_state=setup_state, started=run_started,
                timings=timings, extra={"http_status": status},
            ), browser)
            continue

        # Next.js keeps background connections alive, so ``networkidle`` burns
        # the full timeout on every run. The load event plus a bounded settle
        # window captures late paint/layout work without turning 60 samples
        # into a 20-minute CI job.
        try:
            page.wait_for_load_state("load", timeout=5000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(1000)
            mark("load_settle")
        except Exception as exc:
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="load_settle", code="load_settle_failed",
                exc=exc, setup_state=setup_state, started=run_started,
                timings=timings,
            ), browser)
            continue

        if ready_selector is not None:
            try:
                page.locator(ready_selector).first.wait_for(
                    state="visible", timeout=10000
                )
                mark("ready_selector")
            except Exception as exc:
                finalize_run(_run_error_sample(
                    run_index=run + 1, stage="ready_selector",
                    code="ready_selector_failed", exc=exc,
                    setup_state=setup_state, started=run_started, timings=timings,
                ), browser)
                continue
        else:
            mark("ready_selector")

        if page_validator is not None:
            try:
                page_validator(page, setup_state)
                mark("pre_measure_validation")
            except Exception as exc:
                finalize_run(_run_error_sample(
                    run_index=run + 1, stage="pre_measure_validation",
                    code="page_validation_failed", exc=exc,
                    setup_state=setup_state, started=run_started, timings=timings,
                ), browser)
                continue
        else:
            mark("pre_measure_validation")

        # Use a trusted Playwright click. In-page interactions keep the current
        # document so its Event Timing entries remain observable. Navigation-
        # only surfaces open the real link in a new tab and prove the target
        # loaded instead of turning the anchor into a no-op.
        interaction_start_ms = 0.0
        interaction_end_ms = 0.0
        interaction_details: dict[str, Any] = {"mode": interaction_mode}
        try:
            candidate = page.locator(interaction_selector).first
            if interaction_mode == "in_page":
                page.evaluate(
                    """
                    () => {
                      document.addEventListener('click', event => {
                        if (event.target.closest('a')) event.preventDefault();
                      }, { capture: true, once: true });
                    }
                    """
                )
            else:
                tag_name = candidate.evaluate("element => element.tagName")
                if tag_name != "A":
                    raise RuntimeError("new-tab interaction requires an anchor")
                candidate.evaluate("element => { element.target = '_blank'; }")
            arm_state = candidate.evaluate(ARM_TRUSTED_INTERACTION_SCRIPT)
            if not isinstance(arm_state, dict) or arm_state.get("armed") is not True:
                raise RuntimeError("trusted click handshake could not be armed")
            interaction_start_ms = page.evaluate("performance.now()")
            if interaction_mode == "new_tab":
                with context.expect_page(timeout=3000) as popup_info:
                    candidate.click(timeout=3000)
                handshake = candidate.evaluate(READ_TRUSTED_INTERACTION_SCRIPT)
                popup = popup_info.value
                popup.wait_for_load_state("domcontentloaded", timeout=5000)
                interaction_details.update(
                    {"popup_created": True, "destination_url": popup.url}
                )
                page.wait_for_timeout(100)
                popup.close()
            else:
                candidate.click(timeout=3000)
                handshake = candidate.evaluate(READ_TRUSTED_INTERACTION_SCRIPT)
            if (
                not isinstance(handshake, dict)
                or type(handshake.get("count")) is not int
                or handshake["count"] != 1
                or type(handshake.get("pointerDownTimestamp")) not in {int, float}
                or type(handshake.get("pointerUpTimestamp")) not in {int, float}
                or type(handshake.get("timestamp")) not in {int, float}
                or handshake["pointerDownTimestamp"] <= 0
                or handshake["pointerUpTimestamp"] < handshake["pointerDownTimestamp"]
                or handshake["timestamp"] <= 0
                or handshake["timestamp"] < handshake["pointerUpTimestamp"]
                or handshake.get("armed") is not False
            ):
                raise RuntimeError("trusted click handshake failed")
            page.wait_for_timeout(500)
            interaction_end_ms = page.evaluate("performance.now()")
            if not (
                interaction_start_ms
                <= float(handshake["pointerDownTimestamp"])
                <= float(handshake["pointerUpTimestamp"])
                <= float(handshake["timestamp"])
                <= interaction_end_ms
            ):
                raise RuntimeError("trusted click fell outside interaction window")
            mark("interaction")
        except Exception as exc:
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="interaction", code="interaction_failed",
                exc=exc, setup_state=setup_state, started=run_started,
                timings=timings,
            ), browser)
            continue

        # Compute FCP from paint entries
        try:
            fcp_ms = page.evaluate(
                """
                () => {
                  const entry = performance.getEntriesByType('paint').find(e => e.name === 'first-contentful-paint');
                  return entry ? entry.startTime : 0;
                }
            """
            )
            mark("paint_measurement")
        except Exception as exc:
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="paint_measurement",
                code="paint_measurement_failed", exc=exc,
                setup_state=setup_state, started=run_started, timings=timings,
            ), browser)
            continue

        # Observe the complete documented five-second TBT window.  Waiting a
        # fixed second after load can silently miss late application work,
        # especially when the mobile network and CPU throttles are active.
        try:
            observation_end_ms = fcp_ms + 5000
            now_ms = float(page.evaluate("performance.now()"))
            if now_ms < observation_end_ms:
                page.wait_for_timeout(int(observation_end_ms - now_ms) + 1)
            mark("observation_window")
        except Exception as exc:
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="observation_window",
                code="observation_failed", exc=exc,
                setup_state=setup_state, started=run_started, timings=timings,
            ), browser)
            continue

        # Validate again after the complete observation window. A late API,
        # console error, or malformed state must not escape merely because the
        # pre-interaction page was initially valid.
        if page_validator is not None:
            try:
                page_validator(page, setup_state)
                mark("post_measure_validation")
            except Exception as exc:
                finalize_run(_run_error_sample(
                    run_index=run + 1, stage="post_measure_validation",
                    code="post_measure_validation_failed", exc=exc,
                    setup_state=setup_state, started=run_started, timings=timings,
                ), browser)
                continue
        else:
            mark("post_measure_validation")
        if post_interaction_validator is not None:
            try:
                post_interaction_validator(page, setup_state, interaction_details)
                mark("interaction_validation")
            except Exception as exc:
                finalize_run(_run_error_sample(
                    run_index=run + 1, stage="interaction_validation",
                    code="interaction_validation_failed", exc=exc,
                    setup_state=setup_state, started=run_started, timings=timings,
                ), browser)
                continue
        else:
            mark("interaction_validation")

        try:
            event_state = page.evaluate(FLUSH_EVENT_TIMING_SCRIPT)
            mark("event_timing_flush")
        except Exception as exc:
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="event_timing",
                code="event_timing_flush_failed", exc=exc,
                setup_state=setup_state, started=run_started, timings=timings,
            ), browser)
            continue
        if (
            not isinstance(event_state, dict)
            or event_state.get("eventTimingSupported") is not True
        ):
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="event_timing",
                code="event_timing_unsupported", exc=None,
                setup_state=setup_state, started=run_started, timings=timings,
            ), browser)
            continue
        event_timing_threshold_ms = event_state.get("eventTimingThresholdMs")
        if (
            type(event_timing_threshold_ms) not in {int, float}
            or event_timing_threshold_ms != EVENT_TIMING_THRESHOLD_MS
        ):
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="event_timing",
                code="event_timing_protocol_invalid", exc=None,
                setup_state=setup_state, started=run_started, timings=timings,
            ), browser)
            continue
        trusted_interaction_count = event_state.get("trustedInteractionCount")
        if (
            type(trusted_interaction_count) is not int
            or trusted_interaction_count != 1
        ):
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="event_timing",
                code="trusted_interaction_missing", exc=None,
                setup_state=setup_state, started=run_started, timings=timings,
            ), browser)
            continue
        flushed_event_count = event_state.get("flushedEventCount")
        if type(flushed_event_count) is not int or flushed_event_count < 0:
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="event_timing",
                code="event_timing_protocol_invalid", exc=None,
                setup_state=setup_state, started=run_started, timings=timings,
            ), browser)
            continue
        flushed_loaf_count = event_state.get("flushedLoafCount")
        if type(flushed_loaf_count) is not int or flushed_loaf_count < 0:
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="event_timing",
                code="event_timing_protocol_invalid", exc=None,
                setup_state=setup_state, started=run_started, timings=timings,
            ), browser)
            continue
        if (
            event_state.get("animationFrameFlushCount") != 2
            or event_state.get("chromiumMajor") != browser_major
        ):
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="event_timing",
                code="event_timing_calibration_failed", exc=None,
                setup_state=setup_state, started=run_started, timings=timings,
            ), browser)
            continue

        try:
            perf = page.evaluate("() => JSON.parse(JSON.stringify(window.__perf))")
            resources = page.evaluate(
                """
                () => performance.getEntriesByType('resource').map(r => ({
                  name: r.name,
                  transferSize: r.transferSize,
                  encodedBodySize: r.encodedBodySize,
                  duration: r.duration,
                  initiatorType: r.initiatorType,
                }))
            """
            )

            # Navigation timing
            nav = page.evaluate(
                """
                () => {
                  const n = performance.getEntriesByType('navigation')[0];
                  if (!n) return null;
                  return {
                    domContentLoadedEventEnd: n.domContentLoadedEventEnd,
                    loadEventEnd: n.loadEventEnd,
                    responseEnd: n.responseEnd,
                    transferSize: n.transferSize,
                  };
                }
            """
            )
            mark("metric_collection")
        except Exception as exc:
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="metric_collection",
                code="metric_collection_failed", exc=exc,
                setup_state=setup_state, started=run_started, timings=timings,
            ), browser)
            continue

        long_tasks = perf.get("longTasks", [])
        loaf = perf.get("loaf", [])
        events = perf.get("events", [])
        interaction_events = [
            event for event in events
            if event.get("name") in {"click", "pointerdown", "pointerup"}
            and float(event.get("duration") or 0) >= EVENT_TIMING_THRESHOLD_MS
            and interaction_start_ms <= float(event["startTime"]) <= interaction_end_ms
        ]

        try:
            # TBT calculation
            tbt = compute_tbt(long_tasks, fcp_ms, fcp_ms + 5000)
            inp_proxy, inp_observation_mode = compute_inp_proxy(
                events, loaf, interaction_start_ms, interaction_end_ms,
                trusted_interaction_count=trusted_interaction_count,
                event_timing_supported=True,
                threshold_ms=event_timing_threshold_ms,
            )
            sizes = collect_resource_sizes(resources)
            mark("metric_computation")
            sample = {
                "run_index": run + 1,
                "audit_status": "passed",
                "stage": "complete",
                "status": status,
                "lcp_ms": round(perf.get("lcp", 0), 1),
                "lcp_element": perf.get("lcpElement"),
                "lcp_element_text_length": len(perf.get("lcpElementText") or ""),
                "cls": round(perf.get("cls", 0), 4),
                "fcp_ms": round(fcp_ms, 1),
                "tbt_ms": round(tbt, 1),
                "inp_proxy_ms": round(inp_proxy, 1),
                "long_task_count": len(long_tasks),
                "long_task_total_ms": round(sum(t["duration"] for t in long_tasks), 1),
                "loaf_count": len(loaf),
                "event_count": len(events),
                "interaction_event_count": len(interaction_events),
                "event_timing_flushed_count": flushed_event_count,
                "loaf_flushed_count": flushed_loaf_count,
                "trusted_interaction_count": trusted_interaction_count,
                "trusted_interaction_window_verified": True,
                "trusted_pointer_sequence_verified": True,
                "event_timing_supported": True,
                "event_timing_threshold_ms": event_timing_threshold_ms,
                "event_timing_calibration": EVENT_TIMING_CALIBRATION,
                "observer_animation_frame_flush_count": 2,
                "inp_observation_mode": inp_observation_mode,
                "interaction_selector": interaction_selector,
                "interaction_details": interaction_details,
                "transfer_kb": sizes,
                "resource_count": len(resources),
                "dom_loaded_ms": round(nav["domContentLoadedEventEnd"], 1) if nav else 0,
                "load_event_ms": round(nav["loadEventEnd"], 1) if nav else 0,
                "timings_ms": {
                    **timings,
                    "elapsed": round((time.monotonic() - run_started) * 1000, 1),
                },
                "request_summary": _request_summary(setup_state),
            }
        except Exception as exc:
            finalize_run(_run_error_sample(
                run_index=run + 1, stage="metric_computation",
                code="metric_computation_failed", exc=exc,
                setup_state=setup_state, started=run_started, timings=timings,
            ), browser)
            continue

        finalize_run(sample, browser)

    # Aggregate runs (median for stability)
    errors = [
        result for result in results
        if result.get("audit_status") != "passed"
        or result.get("cleanup_status") != "passed"
    ]
    if len(results) != runs or errors:
        return {
            "error": f"{len(errors)} of {runs} runs failed",
            "run_errors": errors,
            "runs": runs,
            "successful_runs": len(results) - len(errors),
            "raw_runs": results,
        }

    def median(key: str) -> float:
        return round(statistics.median([r[key] for r in results if isinstance(r.get(key), (int, float))]), 2)

    transfer_keys = ("js_kb", "css_kb", "img_kb", "other_kb", "total_kb")
    transfer_median = {
        key: round(statistics.median([r["transfer_kb"][key] for r in results]), 2)
        for key in transfer_keys
    }
    inp_modes = {result["inp_observation_mode"] for result in results}

    agg = {
        "runs": runs,
        "status": results[-1]["status"],
        "lcp_ms": median("lcp_ms"),
        "lcp_element": results[-1].get("lcp_element"),
        "lcp_element_text_length": results[-1].get("lcp_element_text_length"),
        "cls": median("cls"),
        "fcp_ms": median("fcp_ms"),
        "tbt_ms": median("tbt_ms"),
        "inp_proxy_ms": median("inp_proxy_ms"),
        "inp_observation_mode": (
            next(iter(inp_modes)) if len(inp_modes) == 1 else "mixed_trusted_modes"
        ),
        "trusted_interaction_count": min(
            result["trusted_interaction_count"] for result in results
        ),
        "trusted_interaction_window_verified": all(
            result["trusted_interaction_window_verified"] is True
            for result in results
        ),
        "event_timing_supported": all(
            result["event_timing_supported"] is True for result in results
        ),
        "event_timing_threshold_ms": EVENT_TIMING_THRESHOLD_MS,
        "interaction_event_count": min(
            result["interaction_event_count"] for result in results
        ),
        "event_timing_flushed_count": sum(
            result["event_timing_flushed_count"] for result in results
        ),
        "loaf_flushed_count": sum(
            result["loaf_flushed_count"] for result in results
        ),
        "trusted_pointer_sequence_verified": all(
            result["trusted_pointer_sequence_verified"] is True
            for result in results
        ),
        "event_timing_calibration": EVENT_TIMING_CALIBRATION,
        "observer_animation_frame_flush_count": 2,
        "long_task_count": results[-1]["long_task_count"],
        "long_task_total_ms": results[-1]["long_task_total_ms"],
        "transfer_kb": transfer_median,
        "resource_count": results[-1]["resource_count"],
        "dom_loaded_ms": results[-1]["dom_loaded_ms"],
        "load_event_ms": results[-1]["load_event_ms"],
        "raw_runs": results if runs > 1 else None,
    }
    return agg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:3017", help="base URL")
    parser.add_argument("--pages", default="all", help="comma-separated page keys or 'all'")
    parser.add_argument("--viewport", default="both", choices=["desktop", "mobile", "both"])
    parser.add_argument("--out", default="docs/performance/perf-audit.json")
    parser.add_argument("--runs", type=int, default=1, help="median across N runs")
    args = parser.parse_args()

    if args.pages == "all":
        selected = PAGES
    else:
        keys = set(args.pages.split(","))
        selected = [(k, p, s) for k, p, s in PAGES if k in keys]

    viewports = {"desktop": "desktop", "mobile": "mobile"} if args.viewport == "both" else {args.viewport: args.viewport}

    print(f"Auditing {len(selected)} pages × {len(viewports)} viewports = {len(selected) * len(viewports)} runs (base: {args.base})", flush=True)
    print(f"  pages={[k for k, _, _ in selected]}", flush=True)

    out: dict[str, Any] = {
        "base_url": args.base,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "runs_per_page": args.runs,
        "pages": {},
    }

    with sync_playwright() as p:
        failed = False
        for key, path, selector in selected:
            out["pages"][key] = {"path": path}
            for vp_name in viewports:
                vp = VIEWPORTS[vp_name]
                t0 = time.time()
                result = audit_one(
                    p, args.base, path, vp_name, vp, selector, runs=args.runs
                )
                failed = failed or "error" in result
                elapsed = time.time() - t0
                out["pages"][key][vp_name] = result
                print(
                    f"  [{vp_name:7}] {key:24} {path:40} LCP={result.get('lcp_ms', 0):>6.0f}ms CLS={result.get('cls', 0):.3f} TBT={result.get('tbt_ms', 0):>5.0f}ms INP*={result.get('inp_proxy_ms', 0):>5.0f}ms JS={result.get('transfer_kb', {}).get('js_kb', 0):>5.0f}KB ({elapsed:.1f}s)",
                    flush=True,
                )

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"\nWrote {args.out}", flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
