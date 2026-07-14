/**
 * Private cross-page navigation for user-authored research queries.
 *
 * URLs contain only public ids/options plus a random, short-lived key. The
 * destination consumes the sessionStorage record once, then moves the typed
 * context into that tab's history.state so reload/back/forward still work.
 */
(function () {
  'use strict';

  var PREFIX = 'structural_private_navigation:';
  var STATE_KEY = 'structuralPrivateNavigation';
  var KEY_TTL_MS = 15 * 60 * 1000;
  var STATE_TTL_MS = 24 * 60 * 60 * 1000;
  var MAX_PENDING = 64;
  var KEY_ATTEMPTS = 4;
  var MAX_RESEARCH_QUERY_CHARS = 8000;
  var ERROR_REGION_ID = 'private-navigation-error';
  var ENTITY_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/;
  var CONTROL_RE = /[\p{Cc}\p{Cf}\p{Cs}]/u;
  // Keep this allow-deny boundary aligned with
  // web/backend/services/input_limits.py::_DEFAULT_IGNORABLE_RANGES. Some
  // default-ignorables (for example CGJ and variation selectors) are marks,
  // not Cc/Cf controls, so Unicode category checks alone are insufficient.
  var DEFAULT_IGNORABLE_RANGES = [
    [0x00AD, 0x00AD],
    [0x034F, 0x034F],
    [0x061C, 0x061C],
    [0x115F, 0x1160],
    [0x17B4, 0x17B5],
    [0x180B, 0x180F],
    [0x200B, 0x200F],
    [0x202A, 0x202E],
    [0x2060, 0x206F],
    [0x3164, 0x3164],
    [0xFE00, 0xFE0F],
    [0xFEFF, 0xFEFF],
    [0xFFA0, 0xFFA0],
    [0x1BCA0, 0x1BCA3],
    [0x1D173, 0x1D17A],
    [0xE0000, 0xE0FFF],
  ];
  var HTML_TAG_RE = /<\s*\/?\s*(?:[A-Za-z]|!)[^>]*>/;
  var SOURCE_VALUES = [
    'home', 'history', 'example', 'class', 'phenomenon', 'suggestion',
    'rewrite', 'search_result', 'legacy', 'unknown'
  ];

  function isDefaultIgnorable(char) {
    var codepoint = char.codePointAt(0);
    return DEFAULT_IGNORABLE_RANGES.some(function (range) {
      return range[0] <= codepoint && codepoint <= range[1];
    });
  }

  function hasForbiddenUnicode(value, allowLayout) {
    for (var char of value) {
      if (allowLayout && (char === '\n' || char === '\r' || char === '\t')) continue;
      if (CONTROL_RE.test(char) || isDefaultIgnorable(char)) return true;
    }
    return false;
  }

  function safeText(value, maximum, allowLayout) {
    if (typeof value !== 'string') return '';
    var text = value.normalize('NFKC');
    if (hasForbiddenUnicode(value, allowLayout) ||
        hasForbiddenUnicode(text, allowLayout)) return '';
    text = text.trim();
    if (!text || text.length > maximum || HTML_TAG_RE.test(text)) return '';
    return text;
  }

  function safeId(value) {
    if (typeof value !== 'string') return '';
    var id = value.trim();
    return ENTITY_ID_RE.test(id) ? id : '';
  }

  function randomKey() {
    try {
      var provider = typeof globalThis !== 'undefined' ? globalThis.crypto : null;
      if (!provider || typeof provider.getRandomValues !== 'function') return '';
      var bytes = new Uint8Array(16);
      provider.getRandomValues(bytes);
      return Array.from(bytes).map(function (byte) {
        return ('0' + byte.toString(16)).slice(-2);
      }).join('');
    } catch (_) { return ''; }
  }

  function privateNavigationCopy() {
    var english = false;
    try {
      english = document.documentElement.lang.toLowerCase().indexOf('en') === 0 ||
        (window.i18n && window.i18n.getLang && window.i18n.getLang() === 'en');
    } catch (_) { /* Chinese is the safe default */ }
    return english ? {
      title: 'Could not open this research question safely',
      body: 'The browser could not create a one-time local handoff. Your question was not added to the URL and this page did not navigate. Allow secure storage for this tab, then try again.',
    } : {
      title: '无法安全打开这个研究问题',
      body: '浏览器未能建立一次性本地交接。问题没有写入网址，页面也没有跳转。请允许当前标签页使用安全存储后重试。',
    };
  }

  function announcePrivateNavigationError(code) {
    try {
      if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function' &&
          typeof CustomEvent === 'function') {
        window.dispatchEvent(new CustomEvent('structural:private-navigation-error', {
          detail: { code: String(code || 'unavailable') },
        }));
      }
    } catch (_) { /* the visible alert below remains authoritative */ }
    try {
      if (typeof document === 'undefined' || !document.createElement) return null;
      var host = document.querySelector('main') || document.body;
      if (!host) return null;
      var region = document.getElementById(ERROR_REGION_ID);
      if (!region) {
        region = document.createElement('section');
        region.id = ERROR_REGION_ID;
        region.className = 'private-navigation-error';
        region.setAttribute('role', 'alert');
        region.setAttribute('aria-live', 'assertive');
        region.setAttribute('aria-atomic', 'true');
        region.setAttribute('tabindex', '-1');
        region.style.cssText = 'max-width:720px;margin:16px auto;padding:16px 18px;border:1px solid #d6d3d1;border-radius:12px;background:#fff;color:#1c1917;box-shadow:0 8px 24px rgba(28,25,23,.06)';
        host.insertBefore(region, host.firstChild);
      }
      var copy = privateNavigationCopy();
      region.replaceChildren();
      var title = document.createElement('strong');
      title.textContent = copy.title;
      var body = document.createElement('p');
      body.textContent = copy.body;
      body.style.cssText = 'margin:6px 0 0;line-height:1.55;color:#57534e';
      region.appendChild(title);
      region.appendChild(body);
      region.dataset.errorCode = String(code || 'unavailable');
      if (typeof region.focus === 'function') region.focus({ preventScroll: false });
      return region;
    } catch (_) { return null; }
  }

  function clearPrivateNavigationError() {
    try {
      var region = document.getElementById(ERROR_REGION_ID);
      if (region) region.remove();
    } catch (_) { /* no DOM */ }
  }

  function failNavigation(code) {
    announcePrivateNavigationError(code);
    return null;
  }

  function normalizeResult(raw) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
    var id = safeId(raw.id);
    var name = safeText(raw.name, 500, true);
    var domain = safeText(raw.domain, 200, true);
    var typeId = safeText(raw.type_id, 120, false);
    var description = safeText(raw.description, 2500, true);
    if (!id || !name || !domain || !typeId || !description) return null;
    var score = typeof raw.retrieval_similarity === 'number'
      ? raw.retrieval_similarity : raw.score;
    var result = {
      id: id,
      name: name,
      domain: domain,
      type_id: typeId,
      description: description,
    };
    if (typeof score === 'number' && Number.isFinite(score) && score >= 0 && score <= 1) {
      result.retrieval_similarity = score;
    }
    return result;
  }

  function normalizeContext(raw, options) {
    options = options || {};
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
    var allowed = {
      version: true, kind: true, created_at: true, query: true,
      rewritten_query: true, lang: true, force: true, source: true,
      phenomenon_id: true, results: true
    };
    if (Object.keys(raw).some(function (key) { return !allowed[key]; })) return null;
    if (raw.version !== 1 || ['search', 'phenomenon'].indexOf(raw.kind) === -1) return null;
    if (options.kind && raw.kind !== options.kind) return null;
    if (!Number.isFinite(raw.created_at) || raw.created_at > Date.now() + 30000 ||
        Date.now() - raw.created_at > (options.state ? STATE_TTL_MS : KEY_TTL_MS)) return null;
    var query = safeText(raw.query, MAX_RESEARCH_QUERY_CHARS, true);
    if (!query) return null;
    var rewritten = raw.rewritten_query == null
      ? null : safeText(raw.rewritten_query, MAX_RESEARCH_QUERY_CHARS, true);
    if (raw.rewritten_query != null && !rewritten) return null;
    var lang = raw.lang === 'en' ? 'en' : raw.lang === 'zh' ? 'zh' : null;
    if (!lang || typeof raw.force !== 'boolean' ||
        SOURCE_VALUES.indexOf(raw.source) === -1) return null;
    var phenomenonId = raw.phenomenon_id == null ? null : safeId(raw.phenomenon_id);
    if (raw.kind === 'phenomenon' && !phenomenonId) return null;
    if (options.id && phenomenonId !== options.id) return null;
    if (raw.kind === 'search' && phenomenonId !== null) return null;
    if (!Array.isArray(raw.results) || raw.results.length > 20) return null;
    var results = raw.results.map(normalizeResult);
    if (results.some(function (item) { return !item; })) return null;
    return {
      version: 1,
      kind: raw.kind,
      created_at: raw.created_at,
      query: query,
      rewritten_query: rewritten,
      lang: lang,
      force: raw.force,
      source: raw.source,
      phenomenon_id: phenomenonId,
      results: results,
    };
  }

  function newContext(kind, options) {
    options = options || {};
    var query = safeText(options.query, MAX_RESEARCH_QUERY_CHARS, true);
    if (!query) return null;
    var phenomenonId = kind === 'phenomenon' ? safeId(options.id) : null;
    if (kind === 'phenomenon' && !phenomenonId) return null;
    var rewritten = options.rewritten_query == null
      ? null : safeText(options.rewritten_query, MAX_RESEARCH_QUERY_CHARS, true);
    if (options.rewritten_query != null && !rewritten) return null;
    var rawResults = options.results == null ? [] : options.results;
    if (!Array.isArray(rawResults) || rawResults.length > 20) return null;
    var results = rawResults.map(normalizeResult);
    if (results.some(function (item) { return !item; })) return null;
    var source = SOURCE_VALUES.indexOf(options.source) === -1 ? 'unknown' : options.source;
    return normalizeContext({
      version: 1,
      kind: kind,
      created_at: Date.now(),
      query: query,
      rewritten_query: rewritten,
      lang: options.lang === 'en' ? 'en' : 'zh',
      force: options.force === true || options.force === 1 || options.force === '1',
      source: source,
      phenomenon_id: phenomenonId,
      results: results,
    });
  }

  function pendingRecords() {
    var rows = [];
    try {
      for (var index = 0; index < sessionStorage.length; index += 1) {
        var key = sessionStorage.key(index);
        if (!key || key.indexOf(PREFIX) !== 0) continue;
        var created = 0;
        try { created = Number(JSON.parse(sessionStorage.getItem(key) || '{}').created_at) || 0; } catch (_) {}
        if (!created || Date.now() - created > KEY_TTL_MS) {
          sessionStorage.removeItem(key);
          index -= 1;
        } else {
          rows.push({ key: key, created_at: created });
        }
      }
    } catch (_) { return null; }
    return rows.sort(function (left, right) { return left.created_at - right.created_at; });
  }

  function storeContext(context) {
    if (!context) return '';
    try {
      var rows = pendingRecords();
      if (!rows) return '';
      while (rows.length >= MAX_PENDING) {
        var oldest = rows.shift().key;
        sessionStorage.removeItem(oldest);
        if (sessionStorage.getItem(oldest) !== null) return '';
      }
      var serialized = JSON.stringify(context);
      for (var attempt = 0; attempt < KEY_ATTEMPTS; attempt += 1) {
        var key = randomKey();
        if (!key) return '';
        var storageKey = PREFIX + key;
        if (sessionStorage.getItem(storageKey) !== null) continue;
        sessionStorage.setItem(storageKey, serialized);
        if (sessionStorage.getItem(storageKey) !== serialized) {
          try { sessionStorage.removeItem(storageKey); } catch (_) {}
          return '';
        }
        return key;
      }
      return '';
    } catch (_) { return ''; }
  }

  function publicSearchParams(options) {
    var params = new URLSearchParams();
    if (options && options.lang === 'en') params.set('lang', 'en');
    if (options && (options.force === true || options.force === 1 || options.force === '1')) params.set('force', '1');
    return params;
  }

  function buildPrivateSearchUrl(options) {
    options = options || {};
    var context = newContext('search', options);
    if (!context) return failNavigation('invalid_context');
    var params = publicSearchParams(options);
    var key = storeContext(context);
    if (!key) return failNavigation('secure_handoff_unavailable');
    params.set('context', key);
    var query = params.toString();
    clearPrivateNavigationError();
    return query ? '/search?' + query : '/search';
  }

  function buildPrivatePhenomenonUrl(options) {
    options = options || {};
    var id = safeId(options.id);
    if (!id) return failNavigation('invalid_context');
    var context = newContext('phenomenon', options);
    if (!context) return failNavigation('invalid_context');
    var params = publicSearchParams(options);
    var key = storeContext(context);
    if (!key) return failNavigation('secure_handoff_unavailable');
    params.set('context', key);
    var query = params.toString();
    clearPrivateNavigationError();
    return '/phenomenon/' + encodeURIComponent(id) + (query ? '?' + query : '');
  }

  function consumePrivateNavigationContext(key, options) {
    if (!/^[0-9a-f]{16,64}$/.test(String(key || ''))) return null;
    var raw = null;
    try {
      raw = sessionStorage.getItem(PREFIX + key);
      if (!raw) return null;
      sessionStorage.removeItem(PREFIX + key);
      if (sessionStorage.getItem(PREFIX + key) !== null) return null;
    } catch (_) { return null; }
    try { return normalizeContext(JSON.parse(raw), options); } catch (_) { return null; }
  }

  function currentState(options) {
    try {
      return normalizeContext(history.state && history.state[STATE_KEY], {
        kind: options && options.kind,
        id: options && options.id,
        state: true,
      });
    } catch (_) { return null; }
  }

  function cleanCurrentUrl() {
    var url = new URL(window.location.href);
    ['context', 'q', 'from_query', 'text_a'].forEach(function (name) {
      url.searchParams.delete(name);
    });
    return url.pathname + url.search + url.hash;
  }

  function currentUrlHas(name) {
    try { return new URL(window.location.href).searchParams.has(name); } catch (_) { return false; }
  }

  function rejectPrivateNavigation(code) {
    try {
      var state = history.state && typeof history.state === 'object'
        ? Object.assign({}, history.state) : {};
      delete state[STATE_KEY];
      history.replaceState(state, '', cleanCurrentUrl());
    } catch (_) { /* best-effort URL cleanup; UI remains fail closed */ }
    return failNavigation(code);
  }

  function commitPrivateNavigationState(context, options) {
    context = normalizeContext(context, {
      kind: options && options.kind,
      id: options && options.id,
      state: true,
    });
    if (!context) return null;
    try {
      var state = history.state && typeof history.state === 'object'
        ? Object.assign({}, history.state) : {};
      state[STATE_KEY] = context;
      history.replaceState(state, '', cleanCurrentUrl());
    } catch (_) { return null; }
    clearPrivateNavigationError();
    return context;
  }

  function resolvePrivateNavigationContext(options) {
    options = options || {};
    var hasLegacy = Boolean(options.legacyQuery) || currentUrlHas('q') ||
      currentUrlHas('from_query') || currentUrlHas('text_a');
    if (hasLegacy) return rejectPrivateNavigation('legacy_query_rejected');

    var keyPresent = currentUrlHas('context') || options.key != null && options.key !== '';
    var key = options.key || '';
    if (keyPresent) {
      var consumed = consumePrivateNavigationContext(key, options);
      if (!consumed) return rejectPrivateNavigation('handoff_expired_or_used');
      var committed = commitPrivateNavigationState(consumed, options);
      if (!committed) return rejectPrivateNavigation('history_commit_failed');
      return committed;
    }

    var context = currentState(options);
    if (context) return commitPrivateNavigationState(context, options);
    return rejectPrivateNavigation('context_unavailable');
  }

  function updatePrivateNavigationState(patch, options) {
    var existing = currentState(options || {});
    if (!existing || !patch || typeof patch !== 'object' || Array.isArray(patch)) return null;
    var allowed = { rewritten_query: true, results: true, force: true, lang: true };
    if (Object.keys(patch).some(function (key) { return !allowed[key]; })) return null;
    return commitPrivateNavigationState(Object.assign({}, existing, patch), options || {});
  }

  var api = {
    buildPrivateSearchUrl: buildPrivateSearchUrl,
    buildPrivatePhenomenonUrl: buildPrivatePhenomenonUrl,
    consumePrivateNavigationContext: consumePrivateNavigationContext,
    resolvePrivateNavigationContext: resolvePrivateNavigationContext,
    commitPrivateNavigationState: commitPrivateNavigationState,
    updatePrivateNavigationState: updatePrivateNavigationState,
    announcePrivateNavigationError: announcePrivateNavigationError,
    clearPrivateNavigationError: clearPrivateNavigationError,
    MAX_RESEARCH_QUERY_CHARS: MAX_RESEARCH_QUERY_CHARS,
  };
  if (typeof window !== 'undefined') Object.assign(window, api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
}());
