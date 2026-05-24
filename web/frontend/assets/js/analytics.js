// Centralized Plausible event tracking (W9-C).
//
// Each placement file (newsletter.js, ask.js, analyze.js, ...) currently
// duplicates a try/catch wrapper around window.plausible(). This file is the
// canonical wrapper + the event-name registry so naming stays consistent
// across the site.
//
// Usage:
//     <script src="/assets/js/analytics.js"></script>
//     <script>
//       window.analytics.track(window.analytics.EVENTS.NEWSLETTER_SIGNUP, {
//         source: "start-here-essay-end",
//       });
//     </script>
//
// Plausible-safe: if Plausible isn't loaded (ad-blocker, offline, dev), the
// call is a silent no-op. NEVER throws.

(function () {
  "use strict";

  // Event name registry. Add new events here; the constant is the source of
  // truth, no magic strings in placement code. Naming convention:
  //   <noun>_<verb>  e.g. newsletter_signup, ask_submit, waitlist_join
  // Lowercase + underscore; verbs in past or imperative tense.
  var EVENTS = {
    // Newsletter pipeline (W9-C)
    NEWSLETTER_SIGNUP: "newsletter_signup",
    NEWSLETTER_DUPLICATE: "newsletter_duplicate",
    NEWSLETTER_ERROR: "newsletter_error",
    NEWSLETTER_ARCHIVE_VIEW: "newsletter_archive_view",
    NEWSLETTER_LINK_CLICK: "newsletter_link_click",
    NEWSLETTER_UNSUBSCRIBE_CLICK: "newsletter_unsubscribe_click",

    // Existing (mirrors what's already inlined across ask.js / analyze.js / ...)
    ASK_SUBMIT: "ask_submit",
    ASK_ERROR: "ask_error",
    ANALYZE_SUBMIT: "analyze_submit",
    ANALYZE_ERROR: "analyze_error",
    WAITLIST_JOIN: "waitlist_join",
    PHASE_FILTER_APPLY: "apply_filter",
    PHASE_COMPANY_VIEW: "view_company",
    PHASE_SOURCE_CLICK: "click_source",

    // W10-B (session #10) — Stripe Pro mock funnel. Mirrors phase-detector
    // app/lib/analytics.ts Events. Keep both in sync when adding events.
    PRICING_VIEW: "pricing_view",
    CHECKOUT_STARTED: "checkout_started",
    CHECKOUT_COMPLETED_MOCK: "checkout_completed_mock",
    CHECKOUT_DECLINED_MOCK: "checkout_declined_mock",
    PAYWALL_MODAL_VIEW: "paywall_modal_view",
    PAYWALL_MODAL_CLICK: "paywall_modal_click",
  };

  // Validate event names defensively — Plausible silently drops invalid names,
  // which makes debugging hard. We log a console.warn in dev (Plausible-less
  // environments) when someone passes an unknown event.
  function isKnownEvent(name) {
    for (var k in EVENTS) {
      if (EVENTS[k] === name) return true;
    }
    return false;
  }

  function track(name, props) {
    if (!name || typeof name !== "string") return;
    if (!isKnownEvent(name)) {
      // Soft warning; still attempt the track (forward-compat for new events
      // not yet added to the registry).
      try {
        if (typeof console !== "undefined" && console.warn) {
          console.warn("[analytics] unknown event:", name);
        }
      } catch (_) { /* swallow */ }
    }
    try {
      if (typeof window.plausible === "function") {
        window.plausible(name, props ? { props: props } : undefined);
      }
    } catch (_) { /* swallow */ }
  }

  // Convenience helper: track all anchor clicks within a container as
  // newsletter_link_click events. Used in newsletter archive pages.
  //
  //     window.analytics.trackLinkClicks(document.querySelector(".issue-body"));
  function trackLinkClicks(container, defaultProps) {
    if (!container || !container.addEventListener) return;
    container.addEventListener("click", function (ev) {
      var target = ev.target;
      // Walk up to the closest <a> in case the user clicked a child <span>.
      while (target && target !== container && target.tagName !== "A") {
        target = target.parentNode;
      }
      if (!target || target.tagName !== "A" || !target.href) return;
      var props = defaultProps ? Object.assign({}, defaultProps) : {};
      props.href = target.href.slice(0, 200); // truncate to keep Plausible happy
      track(EVENTS.NEWSLETTER_LINK_CLICK, props);
    });
  }

  // Fire once on page load if the page is a newsletter archive view. Pages
  // opt in by setting `<body data-newsletter-issue="2026-W19">`.
  function autoFireArchiveView() {
    try {
      var issue = document.body && document.body.dataset
        ? document.body.dataset.newsletterIssue
        : null;
      if (issue) {
        track(EVENTS.NEWSLETTER_ARCHIVE_VIEW, { issue: issue });
      }
    } catch (_) { /* swallow */ }
  }

  // Public API
  window.analytics = {
    EVENTS: EVENTS,
    track: track,
    trackLinkClicks: trackLinkClicks,
  };

  // Auto-fire on DOMContentLoaded so newsletter archive pages don't need to.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", autoFireArchiveView);
  } else {
    autoFireArchiveView();
  }
})();
