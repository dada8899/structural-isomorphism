// history-sidebar.js — anonymous local search history sidebar (Perplexity-style)
// Self-contained widget: injects own CSS + DOM, reads from window.getHistory().
// Depends on: utils.js (getHistory, Storage). Safe to include via <script src="..."> on any page.
//
// localStorage keys:
//   structural_history             (existing) — search entries written by search.js
//   structural_sidebar_collapsed   (new)     — desktop collapsed state ("1" | "0")
//
// Public API:
//   window.HistorySidebar.refresh()  // re-render after a write
//   window.HistorySidebar.toggle()
//   window.HistorySidebar.openDrawer()
//   window.HistorySidebar.closeDrawer()

(function () {
  'use strict';

  if (window.HistorySidebar) return; // idempotent

  var COLLAPSED_KEY = 'structural_sidebar_collapsed';
  var EXAMPLE_QUERIES = [
    '为什么团队氛围崩了就回不去？',
    '月活下降 7% 怎么找根因？',
    '一些谣言为什么会突然爆？',
  ];

  // ---------- CSS injection ----------
  var CSS = `
.history-sidebar {
  position: fixed;
  left: 0; top: 0; bottom: 0;
  width: 240px;
  background: #FAFAF9;
  border-right: 1px solid #E4E4E7;
  display: flex;
  flex-direction: column;
  z-index: 90;
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  transition: width 0.18s ease, transform 0.18s ease;
}
.history-sidebar__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #E4E4E7;
  flex-shrink: 0;
}
.history-sidebar__title {
  font-size: 13px;
  font-weight: 600;
  color: #18181B;
  letter-spacing: 0.02em;
}
.history-sidebar__toggle {
  background: transparent;
  border: 0;
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  color: #71717A;
  font-size: 14px;
  line-height: 1;
}
.history-sidebar__toggle:hover { background: #F4F4F5; color: #18181B; }
.history-sidebar__body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 8px 16px;
}
.history-entry {
  display: block;
  padding: 10px 12px;
  border-radius: 8px;
  text-decoration: none;
  color: inherit;
  position: relative;
  cursor: pointer;
  border: 1px solid transparent;
}
.history-entry:hover {
  background: #FFFFFF;
  border-color: #E4E4E7;
}
.history-entry__query {
  font-size: 13px;
  color: #18181B;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}
.history-entry__time {
  font-size: 11px;
  color: #A1A1AA;
  margin-top: 4px;
}
.history-entry__delete {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: transparent;
  border: 0;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
  color: #A1A1AA;
  opacity: 0;
  transition: opacity 0.12s;
  font-size: 14px;
  line-height: 1;
}
.history-entry:hover .history-entry__delete { opacity: 1; }
.history-entry__delete:hover { background: #FEF2F2; color: #DC2626; }
.history-sidebar__footer {
  padding: 10px 16px;
  border-top: 1px solid #E4E4E7;
  font-size: 11px;
  color: #A1A1AA;
  flex-shrink: 0;
}
.history-sidebar__clear {
  background: transparent;
  border: 0;
  color: #71717A;
  cursor: pointer;
  font-size: 11px;
  padding: 0;
}
.history-sidebar__clear:hover { color: #DC2626; }
.history-sidebar__empty {
  padding: 16px 12px;
}
.history-sidebar__empty-text {
  font-size: 12px;
  color: #71717A;
  margin: 0 0 12px;
  line-height: 1.5;
}
.history-sidebar__example {
  display: block;
  font-size: 13px;
  color: #18181B;
  padding: 10px 12px;
  background: #FFFFFF;
  border: 1px solid #E4E4E7;
  border-radius: 8px;
  margin-bottom: 8px;
  text-decoration: none;
  line-height: 1.45;
  cursor: pointer;
}
.history-sidebar__example:hover {
  border-color: #2563EB;
  color: #2563EB;
}

/* Mobile hamburger trigger (always-visible floating button) */
.history-sidebar__trigger {
  position: fixed;
  bottom: 20px;
  left: 16px;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: #18181B;
  color: #FFFFFF;
  border: 0;
  cursor: pointer;
  z-index: 95;
  box-shadow: 0 4px 12px rgba(0,0,0,0.12);
  font-size: 18px;
  line-height: 1;
  display: none;
}
.history-sidebar__trigger:hover { background: #2563EB; }

/* Desktop: sidebar always visible; body padding-left pushes content */
@media (min-width: 1024px) {
  body.has-history-sidebar { padding-left: 240px; }
  body.has-history-sidebar.history-sidebar-collapsed { padding-left: 56px; }
  body.has-history-sidebar .site-header { padding-left: 0; }
  body.history-sidebar-collapsed .history-sidebar { width: 56px; }
  body.history-sidebar-collapsed .history-sidebar__title,
  body.history-sidebar-collapsed .history-sidebar__body,
  body.history-sidebar-collapsed .history-sidebar__footer { display: none; }
}

/* Mobile: sidebar off-canvas drawer */
@media (max-width: 1023px) {
  .history-sidebar { transform: translateX(-100%); width: 280px; }
  .history-sidebar--open { transform: translateX(0); box-shadow: 4px 0 24px rgba(0,0,0,0.15); }
  .history-sidebar__trigger { display: flex; align-items: center; justify-content: center; }
  body.has-history-sidebar.history-sidebar--drawer-open { overflow: hidden; }
}

.history-sidebar__backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.32);
  z-index: 89;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.18s;
}
.history-sidebar__backdrop--visible {
  opacity: 1;
  pointer-events: auto;
}
@media (min-width: 1024px) {
  .history-sidebar__backdrop { display: none; }
}
`;

  function injectStyle() {
    if (document.getElementById('history-sidebar-style')) return;
    var style = document.createElement('style');
    style.id = 'history-sidebar-style';
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  // ---------- DOM build ----------
  function buildSidebarDOM() {
    var aside = document.createElement('aside');
    aside.className = 'history-sidebar';
    aside.id = 'history-sidebar';
    aside.setAttribute('aria-label', '最近的查询');
    aside.innerHTML =
      '<div class="history-sidebar__header">' +
        '<span class="history-sidebar__title">最近的查询</span>' +
        '<button class="history-sidebar__toggle" type="button" aria-label="收起" title="收起/展开">‹</button>' +
      '</div>' +
      '<div class="history-sidebar__body" id="history-sidebar-body"></div>' +
      '<div class="history-sidebar__footer">' +
        '<button class="history-sidebar__clear" type="button">清空历史</button>' +
      '</div>';
    return aside;
  }

  function buildBackdrop() {
    var bd = document.createElement('div');
    bd.className = 'history-sidebar__backdrop';
    bd.id = 'history-sidebar-backdrop';
    return bd;
  }

  function buildTrigger() {
    var btn = document.createElement('button');
    btn.className = 'history-sidebar__trigger';
    btn.id = 'history-sidebar-trigger';
    btn.type = 'button';
    btn.setAttribute('aria-label', '打开历史');
    btn.innerHTML = '☰';
    return btn;
  }

  // ---------- Rendering ----------
  function timeAgo(ts) {
    if (!ts) return '';
    var diffSec = Math.floor((Date.now() - ts) / 1000);
    if (diffSec < 60) return '刚刚';
    if (diffSec < 3600) return Math.floor(diffSec / 60) + ' 分钟前';
    if (diffSec < 86400) return Math.floor(diffSec / 3600) + ' 小时前';
    if (diffSec < 604800) return Math.floor(diffSec / 86400) + ' 天前';
    var d = new Date(ts);
    return (d.getMonth() + 1) + '-' + d.getDate();
  }

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderEmpty(body) {
    body.innerHTML =
      '<div class="history-sidebar__empty">' +
        '<p class="history-sidebar__empty-text">你用过的查询会出现在这里。试试看：</p>' +
        EXAMPLE_QUERIES.map(function (q) {
          return '<a class="history-sidebar__example" href="/search?q=' + encodeURIComponent(q) + '">' + escapeHtml(q) + '</a>';
        }).join('') +
      '</div>';
  }

  function renderList(body, list) {
    body.innerHTML = list.map(function (entry) {
      var q = escapeHtml(entry.query);
      var url = '/search?q=' + encodeURIComponent(entry.query);
      return (
        '<a class="history-entry" href="' + url + '" data-query="' + q + '">' +
          '<div class="history-entry__query">' + q + '</div>' +
          '<div class="history-entry__time">' + timeAgo(entry.timestamp) + '</div>' +
          '<button class="history-entry__delete" type="button" aria-label="删除" title="删除">×</button>' +
        '</a>'
      );
    }).join('');
  }

  // Local cache of the last merged list so a remote fetch doesn't have to
  // race the initial render. localStorage stays authoritative.
  var _remoteCache = null;

  function _useRemote() {
    try { return localStorage.getItem('structural_use_remote_history') === '1'; } catch (e) { return false; }
  }

  // Merge two lists by query string (case-insensitive), keeping the most
  // recent timestamp from either source. localStorage entries win on tie
  // so user-local writes never get clobbered by a stale remote row.
  function mergeHistoryLists(localList, remoteList) {
    var bucket = {};
    var order = [];
    function add(entry, isLocal) {
      if (!entry || !entry.query) return;
      var key = String(entry.query).trim().toLowerCase();
      if (!key) return;
      if (bucket[key]) {
        // Merge: keep newer timestamp, prefer local entry's other fields.
        var existing = bucket[key];
        var existingTs = Number(existing.timestamp || 0);
        var entryTs = Number(entry.timestamp || 0);
        if (entryTs > existingTs && !isLocal) existing.timestamp = entryTs;
        return;
      }
      bucket[key] = {
        query: String(entry.query),
        rewritten_query: entry.rewritten_query || null,
        timestamp: Number(entry.timestamp || 0),
      };
      order.push(key);
    }
    // Local first → wins on dedupe.
    (localList || []).forEach(function (e) { add(e, true); });
    (remoteList || []).forEach(function (e) { add(e, false); });
    return order
      .map(function (k) { return bucket[k]; })
      .sort(function (a, b) { return (b.timestamp || 0) - (a.timestamp || 0); });
  }

  // Convert backend history rows (kind ∈ {ask,search,analyze}, created_at as
  // ISO string) into the sidebar's expected shape.
  function _normaliseRemote(rows) {
    if (!Array.isArray(rows)) return [];
    var out = [];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i] || {};
      if (!r.query) continue;
      // created_at may be ISO string or sqlite-style "YYYY-MM-DD HH:MM:SS"
      var ts = 0;
      if (r.created_at) {
        var d = new Date(r.created_at);
        if (!isNaN(d.getTime())) ts = d.getTime();
      }
      out.push({ query: r.query, rewritten_query: null, timestamp: ts });
    }
    return out;
  }

  function fetchRemoteHistory() {
    if (!_useRemote()) return Promise.resolve(null);
    if (!window.getDeviceId) return Promise.resolve(null);
    return fetch('/api/history?limit=20', {
      method: 'GET',
      headers: { 'X-Device-ID': window.getDeviceId() },
      credentials: 'same-origin',
    })
      .then(function (res) {
        if (!res.ok) throw new Error('history fetch ' + res.status);
        return res.json();
      })
      .then(function (data) {
        _remoteCache = _normaliseRemote(data && data.items);
        return _remoteCache;
      })
      .catch(function (err) {
        if (window.console && console.warn) console.warn('[history-sidebar] remote fetch failed:', err);
        return null;
      });
  }

  function refresh() {
    var body = document.getElementById('history-sidebar-body');
    if (!body) return;
    var local = (window.getHistory && window.getHistory()) || [];
    // Dual-source: if remote is enabled and we have a cached snapshot,
    // merge it in. localStorage is the source of truth.
    var list = local;
    if (_useRemote() && _remoteCache) {
      list = mergeHistoryLists(local, _remoteCache);
    }
    if (!list.length) renderEmpty(body);
    else renderList(body, list);
  }

  // ---------- Removal helper ----------
  function removeFromHistory(query) {
    if (!window.getHistory || !window.Storage) return;
    var list = window.getHistory();
    var next = list.filter(function (e) { return !e || !e.query || e.query.trim().toLowerCase() !== String(query).trim().toLowerCase(); });
    window.Storage.set('structural_history', next);
  }

  function clearAll() {
    if (window.Storage) window.Storage.set('structural_history', []);
  }

  // ---------- Toggle / drawer state ----------
  function toggleCollapsed() {
    var isCollapsed = document.body.classList.toggle('history-sidebar-collapsed');
    try { localStorage.setItem(COLLAPSED_KEY, isCollapsed ? '1' : '0'); } catch (e) {}
  }

  function openDrawer() {
    var sb = document.getElementById('history-sidebar');
    var bd = document.getElementById('history-sidebar-backdrop');
    if (sb) sb.classList.add('history-sidebar--open');
    if (bd) bd.classList.add('history-sidebar__backdrop--visible');
    document.body.classList.add('history-sidebar--drawer-open');
  }

  function closeDrawer() {
    var sb = document.getElementById('history-sidebar');
    var bd = document.getElementById('history-sidebar-backdrop');
    if (sb) sb.classList.remove('history-sidebar--open');
    if (bd) bd.classList.remove('history-sidebar__backdrop--visible');
    document.body.classList.remove('history-sidebar--drawer-open');
  }

  function isMobile() { return window.innerWidth < 1024; }

  // ---------- Wire up ----------
  function init() {
    if (document.getElementById('history-sidebar')) return;
    injectStyle();
    document.body.appendChild(buildSidebarDOM());
    document.body.appendChild(buildBackdrop());
    document.body.appendChild(buildTrigger());
    document.body.classList.add('has-history-sidebar');

    // Restore collapsed state
    try {
      if (localStorage.getItem(COLLAPSED_KEY) === '1') {
        document.body.classList.add('history-sidebar-collapsed');
      }
    } catch (e) {}

    // Toggle button: collapse on desktop, close drawer on mobile
    var toggleBtn = document.querySelector('.history-sidebar__toggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', function () {
        if (isMobile()) closeDrawer();
        else toggleCollapsed();
      });
    }

    // Trigger button (mobile only) opens drawer
    var trigger = document.getElementById('history-sidebar-trigger');
    if (trigger) trigger.addEventListener('click', openDrawer);

    // Backdrop tap closes drawer
    var bd = document.getElementById('history-sidebar-backdrop');
    if (bd) bd.addEventListener('click', closeDrawer);

    // Delegated click on body for entries + delete + clear + examples
    document.getElementById('history-sidebar-body').addEventListener('click', function (e) {
      var del = e.target.closest && e.target.closest('.history-entry__delete');
      if (del) {
        e.preventDefault();
        e.stopPropagation();
        var entry = del.closest('.history-entry');
        if (entry) {
          removeFromHistory(entry.getAttribute('data-query') || '');
          refresh();
        }
      }
    });

    var clear = document.querySelector('.history-sidebar__clear');
    if (clear) {
      clear.addEventListener('click', function () {
        if (window.confirm('确定清空所有历史？')) {
          clearAll();
          refresh();
        }
      });
    }

    // Listen for storage events from other tabs
    window.addEventListener('storage', function (ev) {
      if (ev.key === 'structural_history') refresh();
    });

    // Listen for visibility change (re-render on tab return)
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) refresh();
    });

    refresh();

    // Async: pull remote history if opted-in; re-render after merge.
    if (_useRemote()) {
      fetchRemoteHistory().then(function (rows) {
        if (rows && rows.length) refresh();
      });
    }
  }

  // Public API
  window.HistorySidebar = {
    init: init,
    refresh: refresh,
    toggle: toggleCollapsed,
    openDrawer: openDrawer,
    closeDrawer: closeDrawer,
    fetchRemote: fetchRemoteHistory,
    mergeHistoryLists: mergeHistoryLists,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
