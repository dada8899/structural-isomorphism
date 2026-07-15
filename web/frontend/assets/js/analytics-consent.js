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
  var BANNER_ID = 'analytics-consent';
  var ANALYTICS_ENDPOINT = 'https://plausible.bytedance.city/api/event';
  var ANALYTICS_DOMAIN = 'beta.structural.bytedance.city';
  var transportGeneration = 0;
  var transportEnabled = false;
  var installedPlausible = null;
  var pageviewUrl = '';

  // This is the only outbound analytics schema. A known event does not gain
  // arbitrary properties: each accepted value is reduced to a coarse enum,
  // boolean, bounded number or public record id before it reaches the wire.
  var EVENT_POLICIES = {
    pageview: {},
    thank_you_view: { source: ['enum', 'main_site'] },
    thank_you_share: { channel: ['enum', 'copy_link', 'x', 'linkedin'] },
    waitlist_signup: {
      source: ['enum', 'main_site', 'homepage-hero'],
      placement: ['enum', 'home', 'homepage-hero']
    },
    waitlist_duplicate: { source: ['enum', 'main_site', 'homepage-hero'] },
    waitlist_error: {
      source: ['enum', 'main_site', 'homepage-hero'],
      status: ['status']
    },
    newsletter_signup: { source: ['newsletter_source'] },
    newsletter_duplicate: { source: ['newsletter_source'] },
    newsletter_error: {
      source: ['newsletter_source'],
      status: ['status']
    },
    newsletter_archive_view: { issue: ['issue'] },
    newsletter_link_click: {
      issue: ['issue'],
      destination: ['enum', 'same_origin', 'external']
    },
    newsletter_unsubscribe_click: { issue: ['issue'] },
    input_warn_threshold: { limit: ['integer', 1, 10000], len: ['integer', 0, 10000] },
    input_hit_cap: { limit: ['integer', 1, 10000] },
    example_chip_clicked: { position: ['integer', 1, 20] },
    fingerprint_review_opened: { length: ['integer', 0, 10000] },
    fingerprint_skipped: { length: ['integer', 0, 10000] },
    fingerprint_confirmed: {
      variables: ['integer', 0, 20],
      constraints: ['integer', 0, 20],
      unknowns: ['integer', 0, 20]
    },
    ask_submitted: {
      length: ['integer', 0, 10000],
      source: ['enum', 'empty', 'chip', 'deeplink', 'followup']
    },
    input_too_long_server: {
      limit: ['integer', 1, 10000],
      received: ['integer', 0, 100000]
    },
    retrieval_done: {
      count: ['integer', 0, 1000],
      retrieval_ms: ['number', 0, 3600000],
      latency_ms: ['number', 0, 3600000]
    },
    candidate_selected: {
      phenomenon_id: ['public_id'],
      position: ['integer', 1, 30]
    },
    candidate_view: { count: ['integer', 0, 30] },
    kb_cards_received: {
      count: ['integer', 0, 1000],
      latency_ms: ['number', 0, 3600000]
    },
    citation_click: {
      phenomenon_id: ['public_id'],
      position: ['integer', 0, 100],
      surface: ['enum', 'kb_card_source', 'citation_bar', 'inline']
    },
    first_validated_answer_chunk: { latency_ms: ['number', 0, 3600000] },
    answer_completed: {
      chars: ['integer', 0, 1000000],
      citations_count: ['integer', 0, 1000],
      latency_ms: ['number', 0, 3600000]
    },
    similar_card_clicked: { card_idx: ['integer', 0, 100] },
    deep_analysis_triggered: {
      from_thread_item: ['boolean'],
      phenomenon_id: ['public_id'],
      persist_opt_in: ['boolean']
    },
    followup_clicked: { question_idx: ['integer', 0, 100] },
    discoveries_loaded: {
      count: ['integer', 0, 100000],
      latency_ms: ['number', 0, 3600000]
    },
    glossary_tooltip_opened: { term: ['glossary_term'] },
    stress_test_submit: {},
    stress_test_result: {
      outcome: ['enum', 'not_broken_in_screen', 'breaks_in_screen', 'condition_dependent']
    },
    stress_test_error: {},
    insights_page_viewed: {}
  };

  var NEWSLETTER_SOURCES = [
    'start-here-essay-end', 'learn-end', 'discoveries-top'
  ];
  var GLOSSARY_TERMS = [
    '临界翻转', '临界级联', '临界放缓', '临界边缘', '普适类', '标度律',
    '临界假说', '相变', '标度形式', '涌现', '反馈环', '阈值效应',
    '幂律分布', '幂律', '自组织临界', '结构同构', '级联'
  ];
  var SENSITIVE_ROUTE_FAMILIES = [
    'analyze', 'report', 'reports',
    'auth', 'auth-login', 'auth-verify', 'auth-callback',
    'invite', 'invitation', 'reset', 'verify', 'claim', 'connect', 'callback',
    'oauth', 'sso', 'account', 'me'
  ];
  var ANALYTICS_PUBLIC_ROUTES = [
    '/', '/index', '/about', '/apply', '/classes', '/diagnose', '/discoveries',
    '/insights', '/learn', '/lint', '/methods', '/papers', '/phenomenon',
    '/pricing', '/privacy', '/search', '/start-here', '/stress-test', '/taxonomy-v2',
    '/thank-you', '/tools', '/whitespace'
  ];
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
        /^\/report(?:\.html)?(?:\/|$)/.test(path) ||
        routeFamilyIsSensitive(path) ||
        pathnameContainsCapability(path)
      ) && analyticsRouteIsPublic(path);
    } catch (_) {
      return false;
    }
  }

  function readChoice() {
    try {
      var parsed = JSON.parse(window.localStorage.getItem(CONSENT_KEY));
      if (!parsed || parsed.version !== CONSENT_VERSION ||
          parsed.essential !== true || parsed.marketing !== false ||
          typeof parsed.analytics !== 'boolean' ||
          ['explicit', 'dnt'].indexOf(parsed.source) === -1 ||
          (parsed.analytics && parsed.source !== 'explicit')) {
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

  function canonicalPageUrl() {
    try {
      var current = new URL(window.location.href);
      if (current.protocol !== 'https:' && current.protocol !== 'http:') return '';
      return current.origin + current.pathname;
    } catch (_) {
      return '';
    }
  }

  function pathnameContainsCapability(pathname) {
    try {
      var decodedPath = safelyDecodePath(pathname);
      if (decodedPath === null) return true;
      return decodedPath.split('/').some(function (segment) {
        if (!segment) return false;
        if (segment.indexOf('@') !== -1) return true;
        if (/^[A-Fa-f0-9]{8}-(?:[A-Fa-f0-9]{4}-){3}[A-Fa-f0-9]{12}$/.test(segment)) return true;
        if (jwtLikeToken(segment)) return true;
        if (dottedOpaqueToken(segment)) return true;
        if (/^[A-Fa-f0-9]{24,}$/.test(segment)) return true;
        if (/^(?:sk|key|token|secret)[-_][A-Za-z0-9_-]{12,}$/i.test(segment)) return true;
        if (segment.length >= 32 && /^[A-Za-z0-9_-]+$/.test(segment) &&
            /[a-z]/.test(segment) && /[A-Z]/.test(segment) && /[0-9]/.test(segment)) {
          return true;
        }
        return segment.length >= 32 &&
          (/^[a-z0-9]+$/.test(segment) || /^[A-Z0-9]+$/.test(segment)) &&
          characterEntropy(segment) >= 4;
      });
    } catch (_) {
      return true;
    }
  }

  function routeFamilyIsSensitive(pathname) {
    try {
      var decoded = safelyDecodePath(pathname);
      if (decoded === null) return true;
      var first = decoded.split('/').filter(Boolean)[0] || '';
      first = first.toLowerCase().replace(/\.html$/, '');
      return SENSITIVE_ROUTE_FAMILIES.indexOf(first) !== -1;
    } catch (_) {
      return true;
    }
  }

  function safelyDecodePath(pathname) {
    try {
      var decoded = pathname;
      for (var round = 0; round < 3; round += 1) {
        var next = decodeURIComponent(decoded);
        if (next === decoded) return decoded;
        decoded = next;
      }
      // A remaining escape after bounded decoding is ambiguous and may hide
      // another route or credential layer. Refuse analytics for that path.
      return /%[0-9A-Fa-f]{2}/.test(decoded) ? null : decoded;
    } catch (_) {
      return null;
    }
  }

  function analyticsRouteIsPublic(pathname) {
    var decoded = safelyDecodePath(pathname);
    if (decoded === null || decoded.indexOf('//') !== -1) return false;
    var normalized = decoded.length > 1 ? decoded.replace(/\/+$/, '') : decoded;
    if (/\.html$/i.test(normalized)) normalized = normalized.slice(0, -5);
    normalized = normalized.toLowerCase();
    if (ANALYTICS_PUBLIC_ROUTES.indexOf(normalized) !== -1) return true;

    var paper = decoded.match(/^\/paper\/([^/]+)\/?$/);
    if (paper) {
      return paper[1].length >= 8 && paper[1].length <= 120 &&
        /^[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]$/.test(paper[1]) &&
        /[._-]/.test(paper[1]);
    }
    var phenomenon = decoded.match(/^\/phenomenon\/([^/]+)\/?$/);
    return Boolean(phenomenon && publicPhenomenonId(phenomenon[1]));
  }

  function publicPhenomenonId(value) {
    // Published KB record ids are short, structured labels such as sci-001.
    // Treat every other dynamic value as private/unknown instead of trying to
    // distinguish an arbitrary semantic slug from a capability token.
    return typeof value === 'string' && value.length <= 16 &&
      /^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*-\d{3}$/.test(value);
  }

  function characterEntropy(value) {
    var counts = {};
    for (var i = 0; i < value.length; i += 1) {
      counts[value[i]] = (counts[value[i]] || 0) + 1;
    }
    return Object.keys(counts).reduce(function (entropy, character) {
      var probability = counts[character] / value.length;
      return entropy - probability * (Math.log(probability) / Math.log(2));
    }, 0);
  }

  function dottedOpaqueToken(segment) {
    if (segment.length < 32 || segment.indexOf('.') === -1) return false;
    var parts = segment.split('.');
    if (parts.length < 2 || parts.some(function (part) {
      return part.length < 6 || !/^[A-Za-z0-9_-]+$/.test(part);
    })) return false;
    return characterEntropy(parts.join('')) >= 4;
  }

  function jwtLikeToken(segment) {
    var parts = segment.split('.');
    if (parts.length !== 3 || parts.some(function (part) {
      return part.length < 8 || !/^[A-Za-z0-9_-]+$/.test(part);
    })) return false;
    return (parts[0].indexOf('eyJ') === 0 && parts[1].indexOf('eyJ') === 0) ||
      characterEntropy(parts.join('')) >= 4;
  }

  function valueAllowed(value, rule) {
    var kind = rule[0];
    if (kind === 'enum') {
      return typeof value === 'string' && rule.slice(1).indexOf(value) !== -1
        ? value : undefined;
    }
    if (kind === 'boolean') {
      return typeof value === 'boolean' ? value : undefined;
    }
    if (kind === 'number' || kind === 'integer') {
      if (typeof value !== 'number' || !Number.isFinite(value)) return undefined;
      if (kind === 'integer' && !Number.isInteger(value)) return undefined;
      return value >= rule[1] && value <= rule[2] ? value : undefined;
    }
    if (kind === 'status') {
      if (typeof value === 'number' && Number.isInteger(value) && value >= 100 && value <= 599) {
        return value;
      }
      return ['network', 'timeout'].indexOf(value) !== -1 ? value : undefined;
    }
    if (kind === 'newsletter_source') {
      return typeof value === 'string' && NEWSLETTER_SOURCES.indexOf(value) !== -1
        ? value : undefined;
    }
    if (kind === 'issue') {
      return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$/.test(value) &&
        !/[A-Fa-f0-9]{24,}/.test(value)
        ? value : undefined;
    }
    if (kind === 'public_id') {
      return value !== 'unknown' && publicPhenomenonId(value)
        ? value : undefined;
    }
    if (kind === 'glossary_term') {
      return typeof value === 'string' && GLOSSARY_TERMS.indexOf(value) !== -1
        ? value : undefined;
    }
    return undefined;
  }

  function sanitizeProps(name, rawProps) {
    var policy = EVENT_POLICIES[name];
    if (!policy) return null;
    var clean = {};
    if (!rawProps || typeof rawProps !== 'object' || Array.isArray(rawProps)) return clean;
    Object.keys(policy).forEach(function (key) {
      if (!Object.prototype.hasOwnProperty.call(rawProps, key)) return;
      var value = valueAllowed(rawProps[key], policy[key]);
      if (value !== undefined) clean[key] = value;
    });
    return clean;
  }

  function transportIsAllowed(generation) {
    if (!transportEnabled || generation !== transportGeneration) return false;
    if (!analyticsRouteIsSafe() || dntEnabled()) return false;
    var choice = readChoice();
    return Boolean(choice && choice.analytics === true);
  }

  function postEvent(name, options, generation) {
    if (!transportIsAllowed(generation)) return;
    if (!Object.prototype.hasOwnProperty.call(EVENT_POLICIES, name)) return;
    if (typeof window.fetch !== 'function') return;
    var url = canonicalPageUrl();
    if (!url) return;
    var rawProps = options && typeof options === 'object' ? options.props : null;
    var props = sanitizeProps(name, rawProps);
    if (props === null) return;
    // The public Plausible Events API uses these expanded keys. Compact
    // tracker keys are an implementation detail of the packaged browser SDK.
    var payload = { name: name, url: url, domain: ANALYTICS_DOMAIN };
    if (Object.keys(props).length) payload.props = props;
    try {
      var request = window.fetch(ANALYTICS_ENDPOINT, {
        method: 'POST',
        mode: 'cors',
        credentials: 'omit',
        referrer: '',
        referrerPolicy: 'no-referrer',
        keepalive: true,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (request && typeof request.catch === 'function') request.catch(function () {});
    } catch (_) {}
  }

  function unloadPlausible() {
    transportEnabled = false;
    transportGeneration += 1;
    pageviewUrl = '';
    try { delete window.plausible; } catch (_) { window.plausible = undefined; }
    installedPlausible = null;
  }

  function loadPlausible() {
    if (!analyticsRouteIsSafe() || dntEnabled() || installedPlausible) return;
    var choice = readChoice();
    if (!choice || choice.analytics !== true) return;
    transportGeneration += 1;
    var generation = transportGeneration;
    transportEnabled = true;
    installedPlausible = function (name, options) {
      if (typeof name !== 'string') return;
      postEvent(name, options, generation);
    };
    installedPlausible.s = 'direct';
    window.plausible = installedPlausible;
    var currentUrl = canonicalPageUrl();
    if (currentUrl && currentUrl !== pageviewUrl) {
      pageviewUrl = currentUrl;
      postEvent('pageview', undefined, generation);
    }
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
