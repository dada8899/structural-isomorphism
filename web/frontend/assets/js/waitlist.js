// W8-D: Waitlist signup handler for the main site (vanilla JS, no build step).
//
// Posts to the Phase Detector backend /api/waitlist endpoint. Same CORS config
// allows POST from structural.bytedance.city. Also fires Plausible custom
// events when the script is loaded.

(function () {
  "use strict";

  // Allow override via <script data-api-base="..."> if needed.
  // Default: production phase backend (proxied through phase.bytedance.city).
  var DEFAULT_API_BASE = "https://phase.bytedance.city";
  function getApiBase() {
    var s = document.currentScript;
    if (s && s.dataset && s.dataset.apiBase) return s.dataset.apiBase;
    var m = document.querySelector('meta[name="phase-api-base"]');
    if (m && m.content) return m.content;
    return DEFAULT_API_BASE;
  }

  // Public, debouncable tracking helper. Safe if Plausible isn't loaded.
  window.trackEvent = window.trackEvent || function (name, props) {
    try {
      if (typeof window.plausible === "function") {
        window.plausible(name, props ? { props: props } : undefined);
      }
    } catch (e) {
      /* swallow */
    }
  };

  function setStatus(el, text, kind) {
    if (!el) return;
    el.textContent = text || "";
    el.classList.remove("is-ok", "is-dup", "is-err");
    if (kind) el.classList.add("is-" + kind);
  }

  function init() {
    var form = document.getElementById("waitlist-form");
    if (!form) return;

    var input = form.querySelector('input[name="email"]');
    var btn = form.querySelector('button[type="submit"]');
    var status = document.getElementById("waitlist-status");
    var apiBase = getApiBase();

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (!input) return;
      var email = (input.value || "").trim();
      if (!email) {
        setStatus(status, "请输入邮箱", "err");
        return;
      }

      btn.disabled = true;
      input.disabled = true;
      setStatus(status, "提交中…", "");

      var body = new URLSearchParams();
      body.set("email", email);
      body.set("source", "main_site");
      body.set("placement", "home");
      if (document.referrer) body.set("referrer", document.referrer);

      fetch(apiBase + "/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      })
        .then(function (res) {
          if (!res.ok) {
            window.trackEvent("waitlist_error", { source: "main_site", status: res.status });
            if (res.status === 422) {
              setStatus(status, "邮箱格式不正确", "err");
            } else {
              setStatus(status, "提交失败：" + res.status, "err");
            }
            btn.disabled = false;
            input.disabled = false;
            return null;
          }
          return res.json();
        })
        .then(function (data) {
          if (!data) return;
          if (data.created) {
            window.trackEvent("waitlist_signup", { source: "main_site", placement: "home" });
            setStatus(status, "✓ 已加入，正在跳转…", "ok");
            setTimeout(function () {
              window.location.href = "/thank-you";
            }, 400);
          } else {
            window.trackEvent("waitlist_duplicate", { source: "main_site" });
            setStatus(status, "✓ 这个邮箱已经在名单上了。", "dup");
            btn.disabled = false;
            input.disabled = false;
          }
        })
        .catch(function (err) {
          window.trackEvent("waitlist_error", { source: "main_site", status: "network" });
          setStatus(status, "网络错误，请稍后重试", "err");
          btn.disabled = false;
          input.disabled = false;
        });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
