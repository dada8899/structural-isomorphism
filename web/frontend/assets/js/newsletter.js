// Session #9 W2-A: beta-site newsletter signup (vanilla JS, no build step).
//
// Posts to /api/newsletter/subscribe on the same origin (beta backend),
// unlike waitlist.js which targets the phase backend.
//
// Usage:
//     <div id="newsletter-here"></div>
//     <script src="/assets/js/newsletter.js"></script>
//     <script>
//       window.mountNewsletter("newsletter-here", "start-here-essay-end");
//     </script>
//
// Source must match a value in newsletter.py::_ALLOWED_SOURCES.

(function () {
  "use strict";

  var EMAIL_RE = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/;

  // Plausible-safe event tracker. Prefers central window.analytics.track
  // (W9-C, /assets/js/analytics.js) when loaded; falls back to inline
  // window.plausible() so this file still works on pages that don't include
  // analytics.js (legacy or stripped-down landing pages).
  function trackEvent(name, props) {
    try {
      if (window.analytics && typeof window.analytics.track === "function") {
        window.analytics.track(name, props);
        return;
      }
      if (typeof window.plausible === "function") {
        window.plausible(name, props ? { props: props } : undefined);
      }
    } catch (_) { /* swallow */ }
  }

  // Per-placement copy. Keep all strings here so designers can tweak without
  // grepping templates. Tone target: 克制 / 不营销。
  var COPY = {
    "start-here-essay-end": {
      eyebrow: "不定期研究更新",
      title: "你已读完，想继续跟进研究进展吗？",
      body: "有新的方法、复核进展或公开负结果时，我们会发送一封简短更新。",
      placeholder: "you@example.com",
      cta: "获取更新",
      fineprint: "免费 · 不定期 · 可随时退订",
    },
    "learn-end": {
      eyebrow: "不定期研究更新",
      title: "想继续跟进方法与复核进展？",
      body: "有新的方法、复核进展或公开负结果时，我们会发送一封简短更新。",
      placeholder: "you@example.com",
      cta: "获取更新",
      fineprint: "免费 · 不定期 · 可随时退订",
    },
    "discoveries-top": {
      eyebrow: "不定期研究更新",
      title: "想跟进候选的验证进展？",
      body: "候选完成来源复核或实证检验时发送更新；未通过的结果也会公开。",
      placeholder: "you@example.com",
      cta: "获取更新",
      fineprint: "免费 · 不定期 · 可随时退订",
    },
  };

  // Generic fallback when an unknown source is passed.
  var DEFAULT_COPY = {
    eyebrow: "不定期研究更新",
    title: "跟进候选与复核进展",
    body: "有新的方法、复核进展或公开负结果时，我们会发送一封简短更新。",
    placeholder: "you@example.com",
    cta: "获取更新",
    fineprint: "免费 · 不定期 · 可随时退订",
  };

  function buildMarkup(copy, idSuffix) {
    var inputId = "newsletter-email-" + idSuffix;
    var statusId = "newsletter-status-" + idSuffix;
    return (
      '<div class="newsletter-card">' +
        '<span class="newsletter-eyebrow">' + copy.eyebrow + "</span>" +
        '<h2 class="newsletter-title">' + copy.title + "</h2>" +
        '<p class="newsletter-body">' + copy.body + "</p>" +
        '<form class="newsletter-form" novalidate>' +
          '<label class="sr-only" for="' + inputId + '">Email</label>' +
          '<input class="newsletter-input" id="' + inputId + '"' +
            ' name="email" type="email" autocomplete="email" required' +
            ' placeholder="' + copy.placeholder + '">' +
          '<button class="newsletter-button" type="submit">' +
            copy.cta +
          "</button>" +
        "</form>" +
        '<p class="newsletter-status" id="' + statusId + '" role="status"' +
          ' aria-live="polite"></p>' +
        '<p class="newsletter-fineprint">' + copy.fineprint + "</p>" +
      "</div>"
    );
  }

  function setStatus(el, text, kind) {
    if (!el) return;
    el.textContent = text || "";
    el.classList.remove("is-ok", "is-dup", "is-err");
    if (kind) el.classList.add("is-" + kind);
  }

  // Session #9 W4-C: client-side request timeout. Without this, a hung
  // /api/newsletter/subscribe leaves the UI stuck on "提交中…" forever — W3-A
  // e2e observed exactly this (15s wait, still showing 提交中…). The backend
  // itself is fast (<5ms), but prod nginx / cold-start / network blips can
  // leave the request hanging. 10s is generous; real responses come in <100ms.
  var REQUEST_TIMEOUT_MS = 10000;

  function attachHandlers(root, source) {
    var form = root.querySelector(".newsletter-form");
    if (!form) return;
    var input = form.querySelector("input[name='email']");
    var btn = form.querySelector("button[type='submit']");
    var status = root.querySelector(".newsletter-status");

    // Guard against double-submits within the same in-flight request — the
    // disabled button is the primary defence, but a determined user pressing
    // Enter rapidly could still race. This boolean is the belt to that
    // suspenders.
    var inFlight = false;

    function unlock() {
      btn.disabled = false;
      input.disabled = false;
      inFlight = false;
    }

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (!input) return;
      if (inFlight) return;
      var email = (input.value || "").trim();

      // Client-side validation — cheap UX feedback; server validates again.
      if (!email) {
        setStatus(status, "请输入邮箱", "err");
        return;
      }
      if (!EMAIL_RE.test(email) || email.length > 200) {
        setStatus(status, "邮箱格式不正确", "err");
        return;
      }

      inFlight = true;
      btn.disabled = true;
      input.disabled = true;
      setStatus(status, "提交中…", "");

      // AbortController + setTimeout — older browsers without AbortController
      // (IE11-ish) won't time out, but on those we already lose CSS anyway.
      var controller = (typeof AbortController === "function")
        ? new AbortController()
        : null;
      var timedOut = false;
      var timer = setTimeout(function () {
        timedOut = true;
        if (controller) controller.abort();
      }, REQUEST_TIMEOUT_MS);

      var fetchOpts = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email, source: source }),
      };
      if (controller) fetchOpts.signal = controller.signal;

      fetch("/api/newsletter/subscribe", fetchOpts)
        .then(function (res) {
          clearTimeout(timer);
          // Server returns 200 for both created + duplicate; only 4xx/5xx
          // are real failures.
          if (!res.ok) {
            trackEvent("newsletter_error", { source: source, status: res.status });
            if (res.status === 400) {
              setStatus(status, "邮箱格式不正确", "err");
            } else {
              setStatus(status, "提交失败：" + res.status, "err");
            }
            unlock();
            return null;
          }
          // Parse defensively — if backend ever returns non-JSON 200 (e.g.
          // an upstream HTML error page squeezed through), .json() throws
          // and we fall into .catch() showing "网络错误".
          return res.json();
        })
        .then(function (data) {
          if (!data) return;
          if (data.created) {
            trackEvent("newsletter_signup", { source: source });
            setStatus(status, "✓ 已加入；有经复核的研究更新时会通知你。", "ok");
            // Clear input on success so users see clean state, not their email
            // sticking around (which could confuse "did it submit?")
            try { input.value = ""; } catch (_) { /* swallow */ }
            // Keep button disabled on success — nothing more to submit.
            // But leave inFlight=false so the form is dormant, not "loading".
            inFlight = false;
          } else if (data.ok) {
            trackEvent("newsletter_duplicate", { source: source });
            setStatus(status, "✓ 这个邮箱已经订阅过了。", "dup");
            // Re-enable so user can switch email if they mis-typed.
            unlock();
          } else {
            setStatus(status, "提交失败，请稍后重试", "err");
            unlock();
          }
        })
        .catch(function (err) {
          clearTimeout(timer);
          if (timedOut) {
            trackEvent("newsletter_error", { source: source, status: "timeout" });
            setStatus(status, "请求超时，请稍后重试", "err");
          } else {
            trackEvent("newsletter_error", { source: source, status: "network" });
            setStatus(status, "网络错误，请稍后重试", "err");
          }
          unlock();
        });
    });
  }

  // Public API — mount once per container.
  window.mountNewsletter = function (containerId, source) {
    var root = document.getElementById(containerId);
    if (!root) return;
    // Idempotent: skip if already mounted (defensive against double-include).
    if (root.dataset.newsletterMounted === "1") return;

    var copy = COPY[source] || DEFAULT_COPY;
    // Suffix DOM ids with containerId to allow multiple mounts on one page
    // without collision (currently we use 1 per page, but cheap to support).
    root.innerHTML = buildMarkup(copy, containerId);
    root.dataset.newsletterMounted = "1";
    attachHandlers(root, source);
  };
})();
