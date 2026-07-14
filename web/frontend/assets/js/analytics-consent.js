/**
 * Structural beta analytics consent.
 *
 * Optional analytics are fail-closed: Plausible is added only after an
 * explicit choice.  DNT always wins, and storage failures fall back to the
 * essential-only path.
 */
(function () {
  'use strict';

  var CONSENT_KEY = 'cookie_consent_v1';
  var CONSENT_VERSION = 1;
  var SCRIPT_ID = 'plausible-script';
  var BANNER_ID = 'analytics-consent';
  var COPY = {
    zh: {
      title: '由你决定是否分享匿名访问统计',
      body: '必要功能始终可用。允许后才会加载自托管、无 Cookie 的 Plausible；不记录搜索内容，也不做跨站追踪。',
      privacy: '查看隐私说明',
      essential: '仅必要功能',
      allow: '允许匿名分析',
      settings: '分析设置'
    },
    en: {
      title: 'You decide whether to share anonymous usage data',
      body: 'Essential features always work. Self-hosted, cookieless Plausible loads only after you allow it; search content is not recorded and there is no cross-site tracking.',
      privacy: 'Read the privacy notice',
      essential: 'Essential only',
      allow: 'Allow anonymous analytics',
      settings: 'Analytics settings'
    }
  };

  function preferredLanguage() {
    try {
      var queryLanguage = new URL(window.location.href).searchParams.get('lang');
      if (queryLanguage === 'en' || queryLanguage === 'zh') return queryLanguage;
    } catch (_) {}
    try {
      if (window.localStorage.getItem('structural.lang') === 'en') return 'en';
    } catch (_) {}
    return (document.documentElement.lang || '').toLowerCase() === 'en' ? 'en' : 'zh';
  }

  function applySettingsLabels() {
    var label = COPY[preferredLanguage()].settings;
    document.querySelectorAll('[data-analytics-settings]').forEach(function (control) {
      control.textContent = label;
    });
  }

  function dntEnabled() {
    var values = [navigator.doNotTrack, window.doNotTrack, navigator.msDoNotTrack];
    return values.some(function (value) {
      return value === '1' || String(value).toLowerCase() === 'yes';
    });
  }

  function analyticsRouteIsSafe() {
    try {
      // Analyze input, account research history, owner report ids and public
      // share tokens are all private research surfaces.  Existing consent
      // must never turn into a pageview or third-party request on any variant
      // (including a trailing slash or a concrete id/token route).
      var path = window.location.pathname || '';
      return !(
        /^\/analyze(?:\.html)?(?:\/|$)/.test(path) ||
        /^\/reports(?:\.html)?(?:\/|$)/.test(path) ||
        /^\/report(?:\.html)?(?:\/|$)/.test(path)
      );
    } catch (_) {
      return false;
    }
  }

  function readChoice() {
    try {
      var parsed = JSON.parse(window.localStorage.getItem(CONSENT_KEY));
      if (!parsed || parsed.version !== CONSENT_VERSION || typeof parsed.analytics !== 'boolean') {
        return null;
      }
      return parsed;
    } catch (_) {
      return null;
    }
  }

  function saveChoice(analytics, source) {
    try {
      window.localStorage.setItem(CONSENT_KEY, JSON.stringify({
        version: CONSENT_VERSION,
        essential: true,
        analytics: Boolean(analytics),
        marketing: false,
        source: source,
        timestamp: new Date().toISOString()
      }));
      return true;
    } catch (_) {
      return false;
    }
  }

  function unloadPlausible() {
    var script = document.getElementById(SCRIPT_ID);
    if (script) script.remove();
    try { delete window.plausible; } catch (_) { window.plausible = undefined; }
  }

  function loadPlausible() {
    if (!analyticsRouteIsSafe() || dntEnabled() || document.getElementById(SCRIPT_ID)) return;
    var script = document.createElement('script');
    script.id = SCRIPT_ID;
    script.defer = true;
    script.async = true;
    script.dataset.domain = 'beta.structural.bytedance.city';
    script.src = 'https://plausible.bytedance.city/js/script.js';
    document.head.appendChild(script);
  }

  function closeBanner() {
    var banner = document.getElementById(BANNER_ID);
    if (banner) banner.remove();
  }

  function choose(analytics) {
    closeBanner();
    if (!saveChoice(analytics, 'explicit')) {
      unloadPlausible();
      return;
    }
    if (analytics) loadPlausible();
    else unloadPlausible();
  }

  function openBanner() {
    closeBanner();
    if (!analyticsRouteIsSafe()) {
      // The global footer still exposes an "Analytics settings" control on
      // sensitive pages.  Make it a functional privacy link without ever
      // constructing analytics UI or loading Plausible in this route.
      window.location.assign('/privacy#analytics');
      return;
    }
    var copy = COPY[preferredLanguage()];
    var banner = document.createElement('section');
    banner.id = BANNER_ID;
    banner.className = 'analytics-consent';
    banner.setAttribute('role', 'region');
    banner.setAttribute('aria-labelledby', 'analytics-consent-title');
    banner.innerHTML =
      '<div class="analytics-consent__copy">' +
        '<strong id="analytics-consent-title" data-i18n="analytics.title">' + copy.title + '</strong>' +
        '<span><span data-i18n="analytics.body">' + copy.body + '</span> ' +
          '<a href="/privacy" data-i18n="analytics.privacy">' + copy.privacy + '</a></span>' +
      '</div>' +
      '<div class="analytics-consent__actions">' +
        '<button type="button" data-analytics-choice="false" data-i18n="analytics.essential">' + copy.essential + '</button>' +
        '<button type="button" class="analytics-consent__allow" data-analytics-choice="true" data-i18n="analytics.allow">' + copy.allow + '</button>' +
      '</div>';
    document.body.appendChild(banner);
    try {
      if (window.i18n && typeof window.i18n.render === 'function') {
        window.i18n.render();
      }
    } catch (_) {}
  }

  document.addEventListener('click', function (event) {
    var choice = event.target.closest('[data-analytics-choice]');
    if (choice) {
      choose(choice.getAttribute('data-analytics-choice') === 'true');
      return;
    }
    if (event.target.closest('[data-analytics-settings]')) openBanner();
  });

  function init() {
    applySettingsLabels();
    if (!analyticsRouteIsSafe()) {
      unloadPlausible();
      closeBanner();
      return;
    }
    if (dntEnabled()) {
      saveChoice(false, 'dnt');
      unloadPlausible();
      closeBanner();
      return;
    }
    var choice = readChoice();
    if (!choice) {
      openBanner();
      return;
    }
    if (choice.analytics) loadPlausible();
    else unloadPlausible();
  }

  window.StructuralAnalytics = {
    open: openBanner,
    refreshLabels: applySettingsLabels
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
