/**
 * Structural — Utility functions
 */

window.$ = (sel, root = document) => root.querySelector(sel);
window.$$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

window.html = (strings, ...values) => {
  return strings.reduce((acc, str, i) => {
    const val = values[i] !== undefined ? values[i] : '';
    return acc + str + (Array.isArray(val) ? val.join('') : val);
  }, '');
};

window.escapeHtml = (s) => {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};

window.formatScore = (score) => {
  if (typeof score !== 'number') return '—';
  return `${Math.round(score * 100)}%`;
};

window.showToast = (message, duration = 3000) => {
  let toast = document.querySelector('.toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.className = 'toast';
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  requestAnimationFrame(() => toast.classList.add('visible'));
  setTimeout(() => {
    toast.classList.remove('visible');
  }, duration);
};

window.Storage = {
  get(key, fallback = null) {
    try {
      const val = localStorage.getItem(key);
      return val ? JSON.parse(val) : fallback;
    } catch {
      return fallback;
    }
  },
  set(key, val) {
    try {
      localStorage.setItem(key, JSON.stringify(val));
    } catch {}
  },
};

// === Optional remote history identity ===
// Remote history contains raw research questions and is disabled unless the
// user explicitly opts in. A device id is neither read nor created otherwise.
const DEVICE_ID_COOKIE = 'structural_device_id';
const DEVICE_ID_MAX_AGE = 60 * 60 * 24 * 365 * 2; // 2 years
const REMOTE_HISTORY_OPT_IN_KEY = 'structural_use_remote_history';
const DEVICE_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function _remoteHistoryEnabled() {
  try {
    return localStorage.getItem(REMOTE_HISTORY_OPT_IN_KEY) === '1';
  } catch (_) {
    return false;
  }
}

window.isRemoteHistoryEnabled = _remoteHistoryEnabled;

function _readCookie(name) {
  try {
    if (typeof document === 'undefined' || !document.cookie) return null;
    var parts = document.cookie.split(';');
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].trim();
      if (p.indexOf(name + '=') === 0) return decodeURIComponent(p.substring(name.length + 1));
    }
  } catch (_) {}
  return null;
}

function _writeCookie(name, value, maxAge) {
  try {
    if (typeof document === 'undefined') return false;
    var parts = [
      name + '=' + encodeURIComponent(value),
      'path=/',
      'max-age=' + maxAge,
      'SameSite=Lax',
    ];
    if (window.location && window.location.protocol === 'https:') parts.push('Secure');
    document.cookie = parts.join('; ');
    return _readCookie(name) === value;
  } catch (_) {
    return false;
  }
}

function _genUuid() {
  var secureCrypto = window.crypto;
  if (!secureCrypto) return null;
  if (typeof secureCrypto.randomUUID === 'function') {
    try {
      var uuid = secureCrypto.randomUUID();
      return DEVICE_ID_RE.test(uuid) ? uuid : null;
    } catch (_) {
      return null;
    }
  }
  if (typeof secureCrypto.getRandomValues !== 'function') return null;
  try {
    var bytes = new Uint8Array(16);
    secureCrypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    var hex = Array.prototype.map.call(bytes, function (value) {
      return value.toString(16).padStart(2, '0');
    }).join('');
    var generated = [
      hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16),
      hex.slice(16, 20), hex.slice(20),
    ].join('-');
    return DEVICE_ID_RE.test(generated) ? generated : null;
  } catch (_) {
    return null;
  }
}

window.getDeviceId = () => {
  if (!_remoteHistoryEnabled()) return null;
  var existing = _readCookie(DEVICE_ID_COOKIE);
  if (existing && DEVICE_ID_RE.test(existing)) return existing;
  var id = _genUuid();
  if (!id || !_writeCookie(DEVICE_ID_COOKIE, id, DEVICE_ID_MAX_AGE)) return null;
  return id;
};

// Fire-and-forget POST to /api/history when remote-history is enabled.
// Returns the fetch Promise so callers can await/log if they want.
window.recordHistoryRemote = (query, kind, summary) => {
  if (!_remoteHistoryEnabled()) return Promise.resolve(null);
  if (!query || !kind) return Promise.resolve(null);
  var deviceId = window.getDeviceId();
  if (!deviceId || typeof fetch !== 'function') return Promise.resolve(null);
  var body = {
    query: String(query).slice(0, 2000),
    kind: String(kind).toLowerCase(),
    result_summary: summary || null,
  };
  return fetch('/api/history', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Device-ID': deviceId,
    },
    body: JSON.stringify(body),
    credentials: 'same-origin',
  }).catch(function () {
    console.warn('[recordHistoryRemote] unavailable');
    return null;
  });
};

// === Per-tab raw search history ===
// Raw questions must not cross tabs implicitly. The legacy localStorage key is
// deleted without parsing or migrating its contents; only this tab's
// sessionStorage is used from this release onward.
const LEGACY_HISTORY_KEY = 'structural_history';
const LEGACY_HISTORY_CLEANUP_KEY = 'structural_history_local_cleanup_v2';
const HISTORY_SESSION_KEY = 'structural_tab_history_v2';
const HISTORY_MAX = 50;

function _cleanupLegacyRawHistory() {
  try {
    // Always remove the raw key, even after the marker, so an older open tab
    // cannot re-introduce private text after the first upgraded tab loads.
    localStorage.removeItem(LEGACY_HISTORY_KEY);
    var remaining = localStorage.getItem(LEGACY_HISTORY_KEY);
    if (remaining !== null) {
      // Some privacy modes/polyfills silently no-op removeItem. Overwrite the
      // legacy payload with an empty array, verify it, then try removal again.
      localStorage.setItem(LEGACY_HISTORY_KEY, '[]');
      remaining = localStorage.getItem(LEGACY_HISTORY_KEY);
      if (remaining !== '[]') return false;
      localStorage.removeItem(LEGACY_HISTORY_KEY);
      remaining = localStorage.getItem(LEGACY_HISTORY_KEY);
    }
    if (remaining !== null && remaining !== '[]') return false;
    if (localStorage.getItem(LEGACY_HISTORY_CLEANUP_KEY) !== '1') {
      localStorage.setItem(LEGACY_HISTORY_CLEANUP_KEY, '1');
    }
    return true;
  } catch (_) {
    return false;
  }
}

function _normaliseHistoryEntry(entry) {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return null;
  var query = typeof entry.query === 'string' ? entry.query.normalize('NFKC').trim() : '';
  if (!query || query.length > 8000) return null;
  var rewritten = typeof entry.rewritten_query === 'string'
    ? entry.rewritten_query.normalize('NFKC').trim().slice(0, 800)
    : null;
  var timestamp = Number(entry.timestamp || 0);
  return {
    query: query,
    rewritten_query: rewritten || null,
    timestamp: Number.isFinite(timestamp) && timestamp > 0 ? timestamp : Date.now(),
  };
}

function _readTabHistory() {
  try {
    var raw = sessionStorage.getItem(HISTORY_SESSION_KEY);
    if (!raw) return [];
    var parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(_normaliseHistoryEntry).filter(Boolean).slice(0, HISTORY_MAX);
  } catch (_) {
    return [];
  }
}

function _writeTabHistory(list) {
  try {
    var payload = JSON.stringify((list || []).slice(0, HISTORY_MAX));
    sessionStorage.setItem(HISTORY_SESSION_KEY, payload);
    return sessionStorage.getItem(HISTORY_SESSION_KEY) === payload;
  } catch (_) {
    return false;
  }
}

function _announceTabHistoryChanged() {
  try {
    if (typeof window.dispatchEvent === 'function' && typeof Event === 'function') {
      // No detail payload: listeners only need to re-read this tab's verified
      // sessionStorage. Raw questions never enter a broadcast event.
      window.dispatchEvent(new Event('structural:history-changed'));
    }
  } catch (_) {}
}

_cleanupLegacyRawHistory();

window.getHistory = () => {
  _cleanupLegacyRawHistory();
  return _readTabHistory();
};

window.addToHistory = (entry) => {
  const normalized = _normaliseHistoryEntry(entry);
  if (!normalized) return window.getHistory();
  const q = normalized.query;
  const list = window.getHistory();
  // Dedupe by query string (case-insensitive)
  const filtered = list.filter(
    (it) => !it || !it.query || it.query.trim().toLowerCase() !== q.toLowerCase()
  );
  const next = [
    {
      query: q,
      rewritten_query: normalized.rewritten_query,
      timestamp: normalized.timestamp,
    },
    ...filtered,
  ].slice(0, HISTORY_MAX);
  if (!_writeTabHistory(next)) return list;
  _announceTabHistoryChanged();
  return next;
};

window.removeFromHistory = (query) => {
  const target = typeof query === 'string' ? query.normalize('NFKC').trim().toLowerCase() : '';
  const list = window.getHistory();
  if (!target) return list;
  const next = list.filter((entry) => entry.query.toLowerCase() !== target);
  if (!_writeTabHistory(next)) return list;
  _announceTabHistoryChanged();
  return next;
};

window.clearHistory = () => {
  const list = window.getHistory();
  if (!_writeTabHistory([])) return list;
  _announceTabHistoryChanged();
  return [];
};

// === Favorites (localStorage) ===
// Shape: [{ query, a_id, b_id, analyze_url, timestamp }]
const FAVORITES_KEY = 'structural_favorites';
const FAVORITES_MAX = 100;
const FAVORITE_ENTITY_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/;

function _migrateFavorite(entry) {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return entry;
  const next = { ...entry };
  let parsed = null;
  try {
    const rawHref = typeof entry.analyze_url === 'string' ? entry.analyze_url : '';
    if (rawHref.startsWith('/') && !rawHref.startsWith('//') && !rawHref.includes('\\')) {
      const candidate = new URL(rawHref, window.location.origin);
      if (candidate.origin === window.location.origin &&
          ['/analyze', '/analyze.html'].includes(candidate.pathname)) parsed = candidate;
    }
  } catch (_) { parsed = null; }
  const query = typeof entry.query === 'string' && entry.query.trim()
    ? entry.query.normalize('NFKC').trim()
    : parsed ? (parsed.searchParams.get('q') || parsed.searchParams.get('text_a') || '').normalize('NFKC').trim() : '';
  const targetId = String(entry.b_id || entry.target_id || (parsed && parsed.searchParams.get('id')) || '').trim();
  const sourceId = String(entry.a_id || entry.source_id || (parsed && parsed.searchParams.get('a_id')) || '').trim();
  if (query) next.query = query;
  if (FAVORITE_ENTITY_ID_RE.test(targetId)) {
    next.b_id = targetId;
    next.analyze_url = '/analyze?id=' + encodeURIComponent(targetId);
  } else if (parsed) {
    delete next.analyze_url;
  }
  if (FAVORITE_ENTITY_ID_RE.test(sourceId)) next.a_id = sourceId;
  if (Object.prototype.hasOwnProperty.call(next, 'server_href')) delete next.server_href;
  return next;
}

window.getFavorites = () => {
  const list = window.Storage.get(FAVORITES_KEY, []);
  if (!Array.isArray(list)) return [];
  const migrated = list.slice(0, FAVORITES_MAX).map(_migrateFavorite);
  if (JSON.stringify(migrated) !== JSON.stringify(list)) {
    window.Storage.set(FAVORITES_KEY, migrated);
  }
  return migrated;
};

// Typed identity remains stable even though private query text is no longer
// part of analyze_url. Two questions against the same candidate stay distinct.
function _favKey(entry) {
  if (!entry) return '';
  if (entry.query && entry.b_id) {
    return JSON.stringify([
      entry.query, entry.a_id || null, entry.b_id,
      entry.fingerprint || null,
      entry.origin_discovery_id || null,
      entry.origin_contract_version || null,
    ]);
  }
  return entry.analyze_url || `${entry.b_id || ''}::${entry.query || ''}`;
}

window.isFavorited = (entry) => {
  const key = _favKey(entry);
  if (!key) return false;
  return window.getFavorites().some((it) => _favKey(it) === key);
};

// Upsert: if entry exists by key, replace it (preserving stored timestamp);
// if not, do nothing. Use this to back-fill names/metadata after async data
// becomes available, without changing the favorited state.
window.upsertFavorite = (entry) => {
  if (!entry) return { updated: false, list: window.getFavorites() };
  const key = _favKey(entry);
  if (!key) return { updated: false, list: window.getFavorites() };
  const list = window.getFavorites();
  const idx = list.findIndex((it) => _favKey(it) === key);
  if (idx < 0) return { updated: false, list };
  const merged = { ...list[idx], ...entry, timestamp: list[idx].timestamp };
  const next = [...list];
  next[idx] = merged;
  window.Storage.set(FAVORITES_KEY, next);
  return { updated: true, list: next };
};

// Toggle: if already favorited, remove it; otherwise add it.
// Returns { favorited: boolean, list: [] }
window.toggleFavorite = (entry) => {
  if (!entry) return { favorited: false, list: window.getFavorites() };
  const key = _favKey(entry);
  const list = window.getFavorites();
  const existingIdx = list.findIndex((it) => _favKey(it) === key);
  let next;
  let favorited;
  if (existingIdx >= 0) {
    next = list.filter((_, i) => i !== existingIdx);
    favorited = false;
  } else {
    next = [
      {
        query: entry.query || '',
        a_id: entry.a_id || null,
        b_id: entry.b_id || null,
        fingerprint: entry.fingerprint || null,
        origin_discovery_id: entry.origin_discovery_id || null,
        origin_contract_version: entry.origin_contract_version || null,
        analyze_url: FAVORITE_ENTITY_ID_RE.test(entry.b_id || '')
          ? '/analyze?id=' + encodeURIComponent(entry.b_id)
          : '',
        timestamp: entry.timestamp || Date.now(),
      },
      ...list,
    ].slice(0, FAVORITES_MAX);
    favorited = true;
  }
  window.Storage.set(FAVORITES_KEY, next);
  return { favorited, list: next };
};

// Inline mini-markdown renderer.
// Supports only **bold** / *italic* / `code` / \n→<br>. Output is safe HTML.
// Used for LLM text fields (main_insight, primary.reason, etc) where the model
// emits `**...**` markup but we don't want to pull in marked.js.
window.mdInline = (text) => {
  if (text == null) return '';
  let s = String(text);
  // Step 1: escape HTML so we can safely re-insert tags
  s = s.replace(/&/g, '&amp;')
       .replace(/</g, '&lt;')
       .replace(/>/g, '&gt;')
       .replace(/"/g, '&quot;')
       .replace(/'/g, '&#39;');
  // Step 2: protect inline `code` first so its contents aren't matched by bold/italic
  const codeStash = [];
  s = s.replace(/`([^`\n]+)`/g, (_, c) => {
    codeStash.push(c);
    return `\u0000CODE${codeStash.length - 1}\u0000`;
  });
  // Step 3: bold then italic (bold first so ** wins over *)
  s = s.replace(/\*\*([^\*\n]+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[^\*])\*([^\*\n]+?)\*(?!\*)/g, '$1<em>$2</em>');
  // Step 4: restore code stash
  s = s.replace(/\u0000CODE(\d+)\u0000/g, (_, i) => `<code>${codeStash[Number(i)]}</code>`);
  // Step 5: \n → <br>
  s = s.replace(/\n/g, '<br>');
  return s;
};

// Same as mdInline but splits double-newlines into <p> blocks (for multi-para text).
window.mdParagraphs = (text) => {
  if (!text) return '';
  return String(text)
    .split(/\n\s*\n/)
    .map(p => p.trim())
    .filter(Boolean)
    .map(p => `<p>${window.mdInline(p)}</p>`)
    .join('');
};

// Block-level markdown renderer.
// Handles paragraphs + bullet lists (`- ` / `* `) + ordered lists (`1. `).
// Used for fields where the LLM may emit a structured procedure like:
//   "- **数据信号**：每日完成率\n- **参数估计**：用 SciPy curve_fit\n- ..."
// Falls back to mdInline for any line that isn't a list item.
window.mdBlock = (text) => {
  if (text == null) return '';
  const src = String(text).trim();
  if (!src) return '';

  // Split into "blocks" separated by blank lines
  const blocks = src.split(/\n\s*\n+/);
  const out = [];

  const isBullet = (line) => /^\s*[-*]\s+/.test(line);
  const isOrdered = (line) => /^\s*\d+[\.、]\s+/.test(line);

  for (const block of blocks) {
    const lines = block.split('\n').map(l => l.replace(/\s+$/, ''));
    if (lines.length === 0) continue;

    // All lines bullets → <ul>
    if (lines.every(l => isBullet(l) || !l.trim())) {
      const items = lines
        .filter(l => l.trim())
        .map(l => l.replace(/^\s*[-*]\s+/, ''))
        .map(l => `<li>${window.mdInline(l)}</li>`)
        .join('');
      out.push(`<ul class="md-list">${items}</ul>`);
      continue;
    }

    // All lines ordered → <ol>
    if (lines.every(l => isOrdered(l) || !l.trim())) {
      const items = lines
        .filter(l => l.trim())
        .map(l => l.replace(/^\s*\d+[\.、]\s+/, ''))
        .map(l => `<li>${window.mdInline(l)}</li>`)
        .join('');
      out.push(`<ol class="md-list">${items}</ol>`);
      continue;
    }

    // Mixed paragraph (with possible inline newlines)
    out.push(`<p>${window.mdInline(block)}</p>`);
  }

  return out.join('');
};

// Auto-update the "我的收藏" nav badge from localStorage. Runs on every page
// because the nav link exists in every .html file.
window.updateFavBadge = () => {
  const badge = document.querySelector('[data-fav-badge]');
  if (!badge) return;
  const n = (window.getFavorites && window.getFavorites().length) || 0;
  badge.textContent = String(n);
  if (n === 0) badge.setAttribute('hidden', '');
  else badge.removeAttribute('hidden');
};

document.addEventListener('DOMContentLoaded', () => {
  window.updateFavBadge();
});

// Scroll observer for header shadow
window.initHeaderScroll = () => {
  const header = document.querySelector('.site-header');
  if (!header) return;
  const update = () => {
    if (window.scrollY > 4) {
      header.classList.add('scrolled');
    } else {
      header.classList.remove('scrolled');
    }
  };
  update();
  window.addEventListener('scroll', update, { passive: true });
};

// === Elapsed timer ===
// Updates an element's textContent every second with "已等待 Xs" style.
// Returns a stop function. Safe with null element.
window.startElapsedTimer = (el, opts = {}) => {
  if (!el) return () => {};
  const format = opts.format || ((s) => `已等待 ${s}s`);
  const start = Date.now();
  const tick = () => {
    const elapsed = Math.max(0, Math.floor((Date.now() - start) / 1000));
    el.textContent = format(elapsed);
  };
  tick();
  const id = setInterval(tick, 1000);
  return () => {
    clearInterval(id);
  };
};

// === Hourglass SVG (reusable) ===
// A small hourglass that flips every 2s. Used in "等待中" placeholders.
window.hourglassSvg = () => `
<svg class="hourglass-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <path d="M6 2h12"/>
  <path d="M6 22h12"/>
  <path d="M6 2c0 4 12 6 12 10"/>
  <path d="M18 2c0 4-12 6-12 10"/>
  <path d="M6 22c0-4 12-6 12-10"/>
  <path d="M18 22c0-4-12-6-12-10"/>
</svg>`;

// === Global math renderer ===
// Scans an element for $...$, $$...$$, \(...\), \[...\] and renders with KaTeX.
// Safe to call even if KaTeX isn't loaded yet (no-op).
window.renderMath = (element) => {
  if (!element || typeof window.renderMathInElement === 'undefined') return;
  try {
    window.renderMathInElement(element, {
      delimiters: [
        { left: '$$', right: '$$', display: true },
        { left: '$', right: '$', display: false },
        { left: '\\[', right: '\\]', display: true },
        { left: '\\(', right: '\\)', display: false },
      ],
      throwOnError: false,
      errorColor: 'var(--text-tertiary)',
      strict: false,
      trust: false,
    });
  } catch (_) {
    console.warn('[renderMath] unavailable');
  }
};
