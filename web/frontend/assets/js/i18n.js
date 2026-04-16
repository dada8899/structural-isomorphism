/**
 * i18n.js — minimal client-side i18n for the chrome (header/footer/nav).
 *
 * Responsibilities:
 *   - Pick the active language from URL (?lang=en) > localStorage > default "zh".
 *   - Fetch /assets/data/i18n/ui.json into window.__i18n_strings (merged with any
 *     pre-existing entries, e.g. future content registries).
 *   - Translate DOM elements tagged with [data-i18n] (textContent) and
 *     [data-i18n-attr="attr:key.path,..."] (attribute values).
 *   - Expose window.i18n.setLang(lang) for the toggle button.
 *
 * Fallback rule: if the current language has no entry for a given key, the
 * element's original textContent (cached from the initial render) is restored.
 * That means other agents can ship untranslated Chinese content and it still
 * renders correctly.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'structural.lang';
  var DEFAULT_LANG = 'zh';
  var SUPPORTED = ['zh', 'en'];
  var UI_JSON_URL = '/assets/data/i18n/ui.json';
  var CONTENT_JSON_URL = '/assets/data/i18n/content.json';

  // Global strings registry — may be pre-populated by other scripts loaded
  // before this one (e.g. a page-specific content bundle). We merge into it
  // rather than overwrite.
  window.__i18n_strings = window.__i18n_strings || { zh: {}, en: {} };

  var state = {
    lang: DEFAULT_LANG,
    ready: false,
    listeners: []
  };

  // ---------- lang resolution ----------

  function readInitialLang() {
    try {
      var url = new URL(window.location.href);
      var qs = url.searchParams.get('lang');
      if (qs && SUPPORTED.indexOf(qs) !== -1) return qs;
    } catch (e) { /* URL may not be available in very old browsers */ }
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored && SUPPORTED.indexOf(stored) !== -1) return stored;
    } catch (e) { /* localStorage disabled */ }
    return DEFAULT_LANG;
  }

  function persistLang(lang) {
    try { localStorage.setItem(STORAGE_KEY, lang); } catch (e) { /* noop */ }
  }

  function applyHtmlLangAttr(lang) {
    var root = document.documentElement;
    if (!root) return;
    root.setAttribute('lang', lang === 'en' ? 'en' : 'zh-CN');
  }

  // ---------- registry access ----------

  function mergeStrings(extra) {
    if (!extra || typeof extra !== 'object') return;
    SUPPORTED.forEach(function (l) {
      var src = extra[l];
      if (!src || typeof src !== 'object') return;
      var dst = window.__i18n_strings[l] = window.__i18n_strings[l] || {};
      Object.keys(src).forEach(function (k) { dst[k] = src[k]; });
    });
  }

  /**
   * UI JSON uses a flat key->{zh, en} shape; internally we flatten to per-lang
   * dictionaries so lookup is O(1).
   */
  function ingestUiJson(raw) {
    if (!raw || typeof raw !== 'object') return;
    Object.keys(raw).forEach(function (key) {
      var row = raw[key];
      if (!row || typeof row !== 'object') return;
      SUPPORTED.forEach(function (l) {
        if (typeof row[l] === 'string') {
          window.__i18n_strings[l] = window.__i18n_strings[l] || {};
          window.__i18n_strings[l][key] = row[l];
        }
      });
    });
  }

  function lookup(key, lang) {
    var dict = window.__i18n_strings[lang];
    if (dict && typeof dict[key] === 'string') return dict[key];
    // fall back to zh if target lang missing (keeps page usable pre-translation)
    var zh = window.__i18n_strings.zh;
    if (zh && typeof zh[key] === 'string') return zh[key];
    return null;
  }

  // ---------- DOM translation ----------

  // Cache original text so we can restore it when a key has no translation.
  function cacheOriginal(el, kind) {
    var attrName = kind === 'text' ? 'data-i18n-orig' : 'data-i18n-orig-' + kind;
    if (el.hasAttribute(attrName)) return el.getAttribute(attrName);
    var val;
    if (kind === 'text') val = el.textContent;
    else val = el.getAttribute(kind) || '';
    el.setAttribute(attrName, val);
    return val;
  }

  function translateTextNodes(root, lang) {
    var nodes = root.querySelectorAll('[data-i18n]');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var key = el.getAttribute('data-i18n');
      if (!key) continue;
      var original = cacheOriginal(el, 'text');
      var translated = lookup(key, lang);
      el.textContent = translated !== null ? translated : original;
    }
  }

  function translateAttrs(root, lang) {
    var nodes = root.querySelectorAll('[data-i18n-attr]');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var spec = el.getAttribute('data-i18n-attr');
      if (!spec) continue;
      var pairs = spec.split(',');
      for (var j = 0; j < pairs.length; j++) {
        var pair = pairs[j].trim();
        if (!pair) continue;
        var colon = pair.indexOf(':');
        if (colon === -1) continue;
        var attr = pair.slice(0, colon).trim();
        var key = pair.slice(colon + 1).trim();
        if (!attr || !key) continue;
        var original = cacheOriginal(el, attr);
        var translated = lookup(key, lang);
        el.setAttribute(attr, translated !== null ? translated : original);
      }
    }
  }

  function updateLangLabels(lang) {
    // The toggle's inner label should show the OTHER language as the action.
    var labels = document.querySelectorAll('[data-i18n-lang-label]');
    for (var i = 0; i < labels.length; i++) {
      labels[i].textContent = lang === 'zh' ? 'EN' : '中';
    }
  }

  function render() {
    var root = document.body || document.documentElement;
    if (!root) return;
    applyHtmlLangAttr(state.lang);
    translateTextNodes(root, state.lang);
    translateAttrs(root, state.lang);
    updateLangLabels(state.lang);
    state.listeners.forEach(function (fn) {
      try { fn(state.lang); } catch (e) { /* swallow */ }
    });
  }

  // ---------- public API ----------

  function setLang(lang) {
    if (SUPPORTED.indexOf(lang) === -1) return;
    if (lang === state.lang) return;
    state.lang = lang;
    persistLang(lang);
    render();
  }

  function toggleLang() {
    setLang(state.lang === 'zh' ? 'en' : 'zh');
  }

  function onChange(fn) {
    if (typeof fn === 'function') state.listeners.push(fn);
  }

  function getLang() { return state.lang; }

  function t(key) {
    var v = lookup(key, state.lang);
    return v !== null ? v : key;
  }

  window.i18n = {
    setLang: setLang,
    toggleLang: toggleLang,
    getLang: getLang,
    onChange: onChange,
    t: t,
    mergeStrings: mergeStrings,
    render: render
  };

  // ---------- bootstrap ----------

  function wireToggleButton() {
    var btn = document.getElementById('lang-toggle');
    if (!btn || btn.__i18nWired) return;
    btn.__i18nWired = true;
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      toggleLang();
    });
  }

  function loadUiJson() {
    return fetch(UI_JSON_URL, { credentials: 'same-origin' })
      .then(function (res) {
        if (!res.ok) throw new Error('ui.json ' + res.status);
        return res.json();
      })
      .then(function (data) { ingestUiJson(data); })
      .catch(function (err) {
        if (window.console && console.warn) {
          console.warn('[i18n] failed to load ui.json:', err);
        }
      });
  }

  function loadContentJson() {
    return fetch(CONTENT_JSON_URL, { credentials: 'same-origin' })
      .then(function (res) {
        if (!res.ok) throw new Error('content.json ' + res.status);
        return res.json();
      })
      .then(function (data) { ingestUiJson(data); })
      .catch(function (err) {
        if (window.console && console.warn) {
          console.warn('[i18n] failed to load content.json:', err);
        }
      });
  }

  function boot() {
    state.lang = readInitialLang();
    applyHtmlLangAttr(state.lang);
    wireToggleButton();
    // Initial render with whatever strings exist synchronously (may be empty);
    // originals get cached so re-render after fetch is correct.
    render();
    Promise.all([loadUiJson(), loadContentJson()]).then(function () {
      state.ready = true;
      render();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
