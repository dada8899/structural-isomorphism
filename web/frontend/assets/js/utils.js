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

// === Search history (localStorage) ===
// Shape: [{ query, rewritten_query, timestamp }], newest first, max 20
const HISTORY_KEY = 'structural_history';
const HISTORY_MAX = 20;

window.getHistory = () => {
  const list = window.Storage.get(HISTORY_KEY, []);
  return Array.isArray(list) ? list : [];
};

window.addToHistory = (entry) => {
  if (!entry || !entry.query) return;
  const q = String(entry.query).trim();
  if (!q) return;
  const list = window.getHistory();
  // Dedupe by query string (case-insensitive)
  const filtered = list.filter(
    (it) => !it || !it.query || it.query.trim().toLowerCase() !== q.toLowerCase()
  );
  const next = [
    {
      query: q,
      rewritten_query: entry.rewritten_query || null,
      timestamp: entry.timestamp || Date.now(),
    },
    ...filtered,
  ].slice(0, HISTORY_MAX);
  window.Storage.set(HISTORY_KEY, next);
  return next;
};

// === Favorites (localStorage) ===
// Shape: [{ query, a_id, b_id, analyze_url, timestamp }]
const FAVORITES_KEY = 'structural_favorites';
const FAVORITES_MAX = 100;

window.getFavorites = () => {
  const list = window.Storage.get(FAVORITES_KEY, []);
  return Array.isArray(list) ? list : [];
};

// Stable key for dedupe: prefer analyze_url, fall back to b_id+query
function _favKey(entry) {
  if (!entry) return '';
  if (entry.analyze_url) return entry.analyze_url;
  return `${entry.b_id || ''}::${entry.query || ''}`;
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
        analyze_url: entry.analyze_url || '',
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
  } catch (e) {
    console.warn('[renderMath] failed:', e);
  }
};
