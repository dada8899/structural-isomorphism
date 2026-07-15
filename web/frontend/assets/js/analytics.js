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

  // Convenience registry for the placements that load this helper. The
  // consent transport remains the sole authoritative event/property policy.
  // Naming convention:
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

    WAITLIST_SIGNUP: "waitlist_signup",
    WAITLIST_DUPLICATE: "waitlist_duplicate",
    WAITLIST_ERROR: "waitlist_error",
    THANK_YOU_VIEW: "thank_you_view",
    THANK_YOU_SHARE: "thank_you_share",
  };

  // Validate event names defensively — Plausible silently drops invalid names,
  // which makes debugging hard. The warning stays content-free so event names
  // supplied by callers never reach browser telemetry.
  function isKnownEvent(name) {
    for (var k in EVENTS) {
      if (EVENTS[k] === name) return true;
    }
    return false;
  }

  function track(name, props) {
    if (!name || typeof name !== "string") return;
    if (!isKnownEvent(name)) {
      return;
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
      // Never export a raw href: it may carry search terms, capability tokens
      // or campaign identifiers. The coarse destination is sufficient for
      // aggregate link usefulness.
      try {
        props.destination = new URL(target.href, window.location.href).origin === window.location.origin
          ? "same_origin" : "external";
      } catch (_) {
        return;
      }
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
