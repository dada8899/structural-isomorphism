/**
 * Structural — My Reports list page (session #17).
 *
 * Lists the reports persisted under this device's anonId via
 * GET /api/reports/mine. Soft-privacy only: a different device / cleared
 * storage starts fresh — anyone with a share token can still read a report.
 */
(function () {
  'use strict';

  var PAGE_SIZE = 20;
  var listEl = document.getElementById('myr-list');
  var moreBtn = document.getElementById('myr-more');
  var connectBtn = document.getElementById('myr-connect');
  var connectError = document.getElementById('myr-connect-error');
  var ownershipCopy = document.getElementById('myr-ownership-copy');
  var offset = 0;
  var loading = false;
  var accountConnected = false;
  var loadedItems = [];
  var hasMoreItems = false;
  var reminderToggle = document.getElementById('myr-reminder-toggle');
  var reminderSummary = document.getElementById('myr-reminder-summary');
  var favoritesEl = document.getElementById('myr-favorites');
  var favoritesCopy = document.getElementById('myr-favorites-copy');
  var accountEl = document.getElementById('myr-account');
  var credentialLocked = false;
  var localFeaturesEnabled = false;
  var currentAccountFavorites = { tickers: [], bookmarks: [] };
  var displayedFavorites = [];
  var favoriteMessages = {};
  var REMINDER_KEY = 'structural_local_reminders';
  var TERMINAL_EXPERIMENTS = ['completed', 'stopped', 'abandoned'];
  var ENTITY_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/;
  var DISCOVERY_ID_RE = /^discovery-[0-9a-f]{16}$/;
  var BOOKMARK_ID_RE = /^bm_[0-9a-f]{24}$/;
  var TICKER_RE = /^[A-Z0-9][A-Z0-9.\-]{0,19}$/;
  var CONTROL_RE = /[\p{Cc}\p{Cf}]/u;
  var HTML_TAG_RE = /<\s*\/?\s*(?:[A-Za-z]|!)[^>]*>/;
  var MAX_RESEARCH_QUERY_CHARS = (window.StructuralInputLimits &&
    window.StructuralInputLimits.researchQueryChars) || 8000;

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function tr(key, fallback) {
    try {
      if (window.i18n && typeof window.i18n.t === 'function') {
        var value = window.i18n.t(key);
        if (value && value !== key) return value;
      }
    } catch (_error) {}
    return fallback;
  }

  function getAnonId() {
    try { return localStorage.getItem('anonId') || ''; } catch (e) { return ''; }
  }

  function originCandidateHref(origin) {
    if (!origin || origin.contract_version !== 'discovery-candidate-v2' ||
        !/^discovery-[0-9a-f]{16}$/.test(origin.discovery_id || '') ||
        ['priority_review', 'candidate_pool'].indexOf(origin.tier) === -1 ||
        !origin.pair ||
        !/^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/.test(origin.pair.a_id || '') ||
        !/^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/.test(origin.pair.b_id || '') ||
        origin.pair.a_id === origin.pair.b_id) return '';
    return '/discoveries?candidate=' + encodeURIComponent(origin.discovery_id);
  }

  function localFavorites() {
    try {
      var parsed = JSON.parse(localStorage.getItem('structural_favorites') || '[]');
      if (!Array.isArray(parsed)) return [];
      var changed = false;
      var migrated = parsed.slice(0, 100).map(function (raw) {
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return raw;
        var legacy = legacyAnalysisFromHref(raw.analyze_url || raw.server_href);
        if (!legacy.recognized) return raw;
        var next = Object.assign({}, raw);
        var query = safeText(raw.query, MAX_RESEARCH_QUERY_CHARS, true) || legacy.query;
        var targetId = safeText(raw.b_id, 120) || safeText(raw.target_id, 120) || legacy.targetId;
        var sourceId = safeText(raw.a_id, 120) || safeText(raw.source_id, 120) || legacy.sourceId;
        if (query) next.query = query;
        if (ENTITY_ID_RE.test(targetId || '')) {
          next.b_id = targetId;
          next.analyze_url = safeAnalysisHref(targetId);
        } else {
          delete next.analyze_url;
        }
        if (sourceId && ENTITY_ID_RE.test(sourceId)) next.a_id = sourceId;
        if (Object.prototype.hasOwnProperty.call(next, 'server_href')) delete next.server_href;
        changed = changed || JSON.stringify(next) !== JSON.stringify(raw);
        return next;
      });
      if (changed) writeLocalFavorites(migrated);
      return migrated;
    } catch (_error) { return []; }
  }

  function writeLocalFavorites(items) {
    try { localStorage.setItem('structural_favorites', JSON.stringify(items.slice(0, 100))); } catch (_error) {}
  }

  function safeText(value, max, allowLayout) {
    if (typeof value !== 'string') return '';
    var text = value.normalize('NFKC').trim();
    if (!text || text.length > max || HTML_TAG_RE.test(text)) return '';
    for (var char of text) {
      if (!CONTROL_RE.test(char)) continue;
      if (allowLayout && (char === '\n' || char === '\r' || char === '\t')) continue;
      return '';
    }
    return text;
  }

  function safeAnalysisHref(targetId) {
    return ENTITY_ID_RE.test(targetId || '')
      ? '/analyze?id=' + encodeURIComponent(targetId)
      : '';
  }

  function legacyAnalysisFromHref(value) {
    if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || value.indexOf('\\') !== -1) return { recognized: false };
    try {
      var parsed = new URL(value, window.location.origin);
      if (parsed.origin !== window.location.origin || ['/analyze', '/analyze.html'].indexOf(parsed.pathname) === -1) return { recognized: false };
      var sourceId = safeText(parsed.searchParams.get('a_id'), 120);
      var targetId = safeText(parsed.searchParams.get('id'), 120);
      return {
        recognized: true,
        sourceId: ENTITY_ID_RE.test(sourceId) ? sourceId : null,
        targetId: ENTITY_ID_RE.test(targetId) ? targetId : '',
        query: safeText(
          parsed.searchParams.get('q') || parsed.searchParams.get('text_a'),
          MAX_RESEARCH_QUERY_CHARS,
          true
        )
      };
    } catch (_error) { return { recognized: false }; }
  }

  function normalizeFingerprint(raw, query) {
    if (raw == null) return null;
    if (typeof raw !== 'object' || Array.isArray(raw)) return null;
    var allowed = {
      source_query: true, summary: true, variables: true,
      constraints: true, unknowns: true, revision: true
    };
    if (Object.keys(raw).some(function (key) { return !allowed[key]; })) return null;
    var sourceQuery = safeText(raw.source_query, MAX_RESEARCH_QUERY_CHARS, true);
    var summary = safeText(raw.summary, 1000, true);
    if (!sourceQuery || sourceQuery !== query || !summary || summary.length < 8) return null;
    var normalized = { source_query: sourceQuery, summary: summary };
    for (var field of ['variables', 'constraints', 'unknowns']) {
      var values = raw[field] == null ? [] : raw[field];
      if (!Array.isArray(values) || values.length > 12) return null;
      var cleaned = values.map(function (item) { return safeText(item, 120); });
      if (cleaned.some(function (item) { return !item; })) return null;
      normalized[field] = cleaned;
    }
    var revision = raw.revision == null ? 1 : raw.revision;
    if (!Number.isInteger(revision) || revision < 1 || revision > 1000) return null;
    normalized.revision = revision;
    return normalized;
  }

  function normalizeOrigin(raw) {
    var id = raw && raw.origin_discovery_id;
    var contract = raw && raw.origin_contract_version;
    if (id == null && contract == null) return null;
    if (!DISCOVERY_ID_RE.test(id || '') || contract !== 'discovery-candidate-v2') return false;
    return { origin_discovery_id: id, origin_contract_version: contract };
  }

  function structuralIdentity(query, sourceId, targetId, fingerprint, origin) {
    return 'structural:' + JSON.stringify([
      query, sourceId, targetId, fingerprint || null, origin || null
    ]);
  }

  function normalizeLocalBookmark(raw, index) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
    var legacy = legacyAnalysisFromHref(raw.analyze_url || raw.server_href);
    var query = safeText(raw.query, MAX_RESEARCH_QUERY_CHARS, true) || legacy.query;
    var sourceId = safeText(raw.a_id, 120) || safeText(raw.source_id, 120) || legacy.sourceId || null;
    var targetId = safeText(raw.b_id, 120) || safeText(raw.target_id, 120) || legacy.targetId || '';
    if (sourceId && !ENTITY_ID_RE.test(sourceId)) return null;
    if (!ENTITY_ID_RE.test(targetId) || !query) return null;
    var href = safeAnalysisHref(targetId);
    if (!href) return null;
    var title = safeText(raw.b_name, 240) || safeText(raw.title, 240) || query.slice(0, 240);
    var fingerprint = normalizeFingerprint(raw.fingerprint, query);
    if (raw.fingerprint != null && !fingerprint) return null;
    var origin = normalizeOrigin(raw);
    if (origin === false) return null;
    return {
      identity: structuralIdentity(query, sourceId, targetId, fingerprint, origin),
      storage: 'local',
      localIndex: index,
      kind: 'structural_analysis',
      title: title,
      query: query,
      sourceId: sourceId,
      targetId: targetId,
      fingerprint: fingerprint,
      origin: origin,
      href: href,
      sourceLabel: tr('page.reports.favorite_source_local', 'Structural · 本机'),
      payload: {
        kind: 'structural_analysis', title: title, query: query,
        source_id: sourceId, target_id: targetId,
        ...(fingerprint ? { fingerprint: fingerprint } : {}),
        ...(origin || {})
      }
    };
  }

  function normalizeAccountBookmark(bookmark) {
    if (!bookmark || typeof bookmark !== 'object' || !BOOKMARK_ID_RE.test(bookmark.bookmark_id || '')) return null;
    if (bookmark.kind === 'structural_analysis') {
      var allowed = {
        schema_version: true, bookmark_id: true, kind: true, title: true,
        query: true, source_id: true, target_id: true, fingerprint: true,
        origin_discovery_id: true, origin_contract_version: true,
        href: true, source: true, created_at: true
      };
      if (Object.keys(bookmark).some(function (key) { return !allowed[key]; }) ||
          bookmark.schema_version !== 'bookmark-v2' || bookmark.source !== 'Structural') return null;
      var query = safeText(bookmark.query, MAX_RESEARCH_QUERY_CHARS, true);
      var sourceId = bookmark.source_id === null ? null : safeText(bookmark.source_id, 120);
      var targetId = safeText(bookmark.target_id, 120);
      var title = safeText(bookmark.title, 240);
      if (!query || !title || (bookmark.source_id !== null && !sourceId) || !ENTITY_ID_RE.test(targetId)) return null;
      var fingerprint = normalizeFingerprint(bookmark.fingerprint, query);
      if (bookmark.fingerprint != null && !fingerprint) return null;
      var origin = normalizeOrigin(bookmark);
      if (origin === false) return null;
      var href = safeAnalysisHref(targetId);
      if (!href || bookmark.href !== href) return null;
      return {
        identity: structuralIdentity(query, sourceId, targetId, fingerprint, origin),
        storage: 'account', bookmarkId: bookmark.bookmark_id,
        kind: bookmark.kind, title: title, query: query,
        sourceId: sourceId, targetId: targetId, fingerprint: fingerprint,
        origin: origin, href: href,
        sourceLabel: tr('page.reports.favorite_source_account', 'Structural · 账户收藏')
      };
    }
    if (bookmark.kind === 'phase_company') {
      var ticker = safeText(bookmark.title, 20);
      if (!TICKER_RE.test(ticker)) return null;
      var phaseHref = 'https://phase.bytedance.city/company/' + encodeURIComponent(ticker);
      if (bookmark.href !== phaseHref) return null;
      return {
        identity: 'phase:' + ticker, storage: 'account',
        bookmarkId: bookmark.bookmark_id, kind: bookmark.kind,
        title: ticker, ticker: ticker, href: phaseHref,
        sourceLabel: tr('page.reports.favorite_source_phase', 'Phase 子产品账户收藏')
      };
    }
    return null;
  }

  function legacyPhaseBookmark(ticker) {
    var normalized = safeText(ticker, 20).toUpperCase();
    if (!TICKER_RE.test(normalized)) return null;
    return {
      identity: 'phase:' + normalized, storage: 'account', kind: 'phase_company',
      title: normalized, ticker: normalized,
      href: 'https://phase.bytedance.city/company/' + encodeURIComponent(normalized),
      sourceLabel: tr('page.reports.favorite_source_phase', 'Phase 子产品账户收藏')
    };
  }

  function normalizedAccountFavorites(data) {
    var result = [];
    var seen = {};
    var bookmarks = data && Array.isArray(data.bookmarks) ? data.bookmarks : [];
    bookmarks.forEach(function (raw) {
      var item = normalizeAccountBookmark(raw);
      if (item && !seen[item.identity]) { seen[item.identity] = true; result.push(item); }
    });
    // Compatibility with a pre-v2 response during a rolling deploy. The v2
    // server emits Phase items in bookmarks; old servers still expose tickers.
    (data && Array.isArray(data.tickers) ? data.tickers : []).forEach(function (ticker) {
      var item = legacyPhaseBookmark(ticker);
      if (item && !seen[item.identity]) { seen[item.identity] = true; result.push(item); }
    });
    return result;
  }

  function favoriteCard(item, index) {
    var external = item.href.indexOf('https://') === 0;
    var message = favoriteMessages[item.identity] === 'remove_failed'
      ? tr('page.reports.favorite_remove_failed', '移除没有完成；收藏仍然保留。')
      : favoriteMessages[item.identity] === 'open_failed'
        ? '浏览器未能建立安全的本地交接；问题没有写入链接，请允许当前标签页使用会话存储后重试。'
        : '';
    return '<article class="myr-favorite" data-favorite-kind="' + escapeHtml(item.kind) + '">' +
      '<a class="myr-favorite__open" data-open-favorite="' + index + '" href="' + escapeHtml(item.href) + '" aria-label="' + escapeHtml(tr('page.reports.favorite_open', '打开收藏')) + '：' + escapeHtml(item.title) + '"' +
      (external ? ' target="_blank" rel="noopener"' : '') + '>' +
      '<span class="myr-favorite__title">' + escapeHtml(item.title) + '</span>' +
      '<span class="myr-favorite__source">' + escapeHtml(item.sourceLabel) + '</span></a>' +
      '<button type="button" class="myr-favorite__remove" data-remove-bookmark="' + index + '" aria-label="' + escapeHtml(tr('page.reports.favorite_remove', '移除收藏')) + '：' + escapeHtml(item.title) + '">' + escapeHtml(tr('page.reports.favorite_remove_short', '移除')) + '</button>' +
      (message ? '<span class="myr-favorite__status" role="alert">' + escapeHtml(message) + '</span>' : '') +
      '</article>';
  }

  function renderFavorites(accountData) {
    if (!favoritesEl || credentialLocked || !localFeaturesEnabled) return;
    currentAccountFavorites = accountData || { tickers: [], bookmarks: [] };
    var accountItems = normalizedAccountFavorites(currentAccountFavorites);
    var seen = {};
    accountItems.forEach(function (item) { seen[item.identity] = true; });
    var localItems = localFavorites().map(normalizeLocalBookmark).filter(Boolean).filter(function (item) {
      return !seen[item.identity];
    });
    displayedFavorites = accountItems.concat(localItems);
    favoritesEl.innerHTML = displayedFavorites.length
      ? displayedFavorites.map(favoriteCard).join('')
      : '<span class="myr-state__hint">' + escapeHtml(tr('page.reports.favorites_empty', '还没有收藏。保存结构分析或在 Phase 收藏公司后，会出现在这里。')) + '</span>';
  }

  function readProblem(response) {
    return response.json().catch(function () { return {}; });
  }

  function isCredentialConflict(response, problem) {
    return !!response && [401, 404, 409].indexOf(response.status) !== -1 &&
      !!problem && problem.error === 'credential_conflict';
  }

  function lockCredentialAssets() {
    credentialLocked = true;
    localFeaturesEnabled = false;
    connectBtn.hidden = true;
    if (accountEl) {
      accountEl.innerHTML = '<p class="myr-state__hint">检测到两个不同账户的登录凭据。为避免操作错账户，所有账户资产保持锁定。</p>' +
        '<div class="myr-account-actions"><a href="/auth/login?next=%2Freports">重新确认账户</a></div>';
    }
    if (favoritesCopy) favoritesCopy.textContent = '账户身份需要重新确认；收藏保持锁定，未读取本机或任何账户资产。';
    if (favoritesEl) favoritesEl.innerHTML = '<span class="myr-state__hint">重新确认账户后再显示收藏。</span>';
    if (reminderSummary) {
      reminderSummary.textContent = '账户身份需要重新确认；未读取本机实验提醒。';
    }
    renderState(
      '需要确认当前账户',
      '浏览器里存在两个不同账户的登录凭据。为避免读取或修改错误账户，研究资产已保持锁定。',
      '重新确认账户',
      '/auth/login?next=%2Freports'
    );
  }

  function loadFavorites(authenticated) {
    if (!favoritesEl || credentialLocked) return;
    if (!authenticated) {
      if (favoritesCopy) favoritesCopy.textContent = tr('page.reports.favorites_anonymous', '当前显示这台浏览器的研究收藏；登录后可同步并跨设备恢复。');
      renderFavorites({ tickers: [], bookmarks: [] });
      return;
    }
    fetch('/api/favorites', { credentials: 'same-origin' })
      .then(function (response) {
        if (response.ok) return response.json();
        return readProblem(response).then(function (problem) {
          if (isCredentialConflict(response, problem)) throw new Error('credential_conflict');
          throw new Error('HTTP ' + response.status);
        });
      })
      .then(function (data) {
        if (credentialLocked) return;
        if (favoritesCopy) favoritesCopy.textContent = tr('page.reports.favorites_account', '正在显示本机与账户收藏；账户收藏可在其他已登录设备恢复。');
        renderFavorites(data);
      })
      .catch(function (error) {
        if (error && error.message === 'credential_conflict') {
          lockCredentialAssets();
          return;
        }
        if (credentialLocked) return;
        if (favoritesCopy) favoritesCopy.textContent = tr('page.reports.favorites_read_failed', '账户收藏暂时无法读取；本机收藏仍然可用。');
        renderFavorites({ tickers: [], bookmarks: [] });
      });
  }

  function syncLocalFavorites(accountData) {
    if (credentialLocked) return Promise.resolve({ kind: 'conflict' });
    var rawLocal = localFavorites();
    var submitted = rawLocal.map(normalizeLocalBookmark).filter(Boolean);
    if (!submitted.length) {
      renderFavorites(accountData);
      return Promise.resolve({ kind: 'ok', data: accountData });
    }
    return fetch('/api/favorites/merge', {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tickers: [],
        bookmarks: submitted.map(function (item) { return item.payload; })
      })
    }).then(function (response) {
      if (!response.ok) {
        return readProblem(response).then(function (problem) {
          if (isCredentialConflict(response, problem)) return { kind: 'conflict' };
          return { kind: 'error', status: response.status };
        });
      }
      return response.json().then(function (data) { return { kind: 'ok', data: data }; });
    }).catch(function () { return { kind: 'error', status: 0 }; })
      .then(function (result) {
        if (result.kind === 'conflict') {
          lockCredentialAssets();
          return result;
        }
        if (result.kind !== 'ok') {
          if (favoritesCopy) favoritesCopy.textContent = tr('page.reports.favorites_sync_failed', '账户同步暂时不可用；本机收藏仍完整保留，可继续使用。');
          renderFavorites(accountData);
          return result;
        }

        var confirmed = {};
        (Array.isArray(result.data.confirmed_bookmark_ids) ? result.data.confirmed_bookmark_ids : [])
          .forEach(function (id) { if (BOOKMARK_ID_RE.test(id)) confirmed[id] = true; });
        var confirmedIdentities = {};
        (Array.isArray(result.data.bookmarks) ? result.data.bookmarks : []).forEach(function (raw) {
          var normalized = normalizeAccountBookmark(raw);
          if (normalized && normalized.bookmarkId && confirmed[normalized.bookmarkId]) {
            confirmedIdentities[normalized.identity] = true;
          }
        });
        var remaining = rawLocal.filter(function (raw, index) {
          var normalized = normalizeLocalBookmark(raw, index);
          return !normalized || !confirmedIdentities[normalized.identity];
        });
        // Local pending entries are removed only after the server echoes both
        // a typed bookmark and its ID in confirmed_bookmark_ids.
        writeLocalFavorites(remaining);
        var dropped = Array.isArray(result.data.dropped_bookmark_ids)
          ? result.data.dropped_bookmark_ids.length : 0;
        if (favoritesCopy) {
          favoritesCopy.textContent = dropped
            ? tr('page.reports.favorites_partial', '部分收藏已同步到账户；达到配额的项目仍保存在本机。')
            : tr('page.reports.favorites_synced', '收藏已与账户同步，可在其他已登录设备恢复。');
        }
        renderFavorites(result.data);
        return result;
      });
  }

  if (favoritesEl) favoritesEl.addEventListener('click', function (event) {
    var openLink = event.target.closest('[data-open-favorite]');
    if (openLink && !credentialLocked) {
      var openIndex = Number(openLink.getAttribute('data-open-favorite'));
      var openItem = displayedFavorites[openIndex];
      if (openItem && openItem.kind === 'structural_analysis') {
        event.preventDefault();
        if (typeof window.buildAnalyzeUrl !== 'function') {
          favoriteMessages[openItem.identity] = 'open_failed';
          renderFavorites(currentAccountFavorites);
          return;
        }
        var destination = window.buildAnalyzeUrl({
          id: openItem.targetId,
          a_id: openItem.sourceId,
          q: openItem.query,
          fingerprint: openItem.fingerprint,
          ...(openItem.origin || {})
        });
        try {
          if (!new URL(destination, window.location.origin).searchParams.get('handoff')) {
            favoriteMessages[openItem.identity] = 'open_failed';
            renderFavorites(currentAccountFavorites);
            return;
          }
        } catch (_error) {
          favoriteMessages[openItem.identity] = 'open_failed';
          renderFavorites(currentAccountFavorites);
          return;
        }
        delete favoriteMessages[openItem.identity];
        window.location.assign(destination);
        return;
      }
    }
    var button = event.target.closest('[data-remove-bookmark]');
    if (!button || button.disabled || credentialLocked) return;
    var index = Number(button.getAttribute('data-remove-bookmark'));
    var item = displayedFavorites[index];
    if (!item) return;

    if (item.storage === 'local') {
      var raw = localFavorites();
      var remaining = raw.filter(function (candidate, rawIndex) {
        var normalized = normalizeLocalBookmark(candidate, rawIndex);
        return !normalized || normalized.identity !== item.identity;
      });
      writeLocalFavorites(remaining);
      delete favoriteMessages[item.identity];
      renderFavorites(currentAccountFavorites);
      return;
    }

    var endpoint = item.bookmarkId
      ? '/api/favorites/bookmarks/' + encodeURIComponent(item.bookmarkId)
      : '/api/favorites/' + encodeURIComponent(item.ticker || '');
    button.disabled = true;
    button.textContent = tr('page.reports.favorite_removing', '移除中…');
    fetch(endpoint, { method: 'DELETE', credentials: 'include' })
      .then(function (response) {
        if (!response.ok) {
          return readProblem(response).then(function (problem) {
            if (isCredentialConflict(response, problem)) throw new Error('credential_conflict');
            throw new Error('HTTP ' + response.status);
          });
        }
        if (item.bookmarkId) {
          currentAccountFavorites.bookmarks = (currentAccountFavorites.bookmarks || []).filter(function (rawBookmark) {
            return rawBookmark && rawBookmark.bookmark_id !== item.bookmarkId;
          });
        }
        if (item.ticker) {
          currentAccountFavorites.tickers = (currentAccountFavorites.tickers || []).filter(function (ticker) {
            return ticker !== item.ticker;
          });
        }
        delete favoriteMessages[item.identity];
        renderFavorites(currentAccountFavorites);
        favoritesEl.setAttribute('tabindex', '-1');
        favoritesEl.focus();
      })
      .catch(function (error) {
        if (error && error.message === 'credential_conflict') {
          lockCredentialAssets();
          return;
        }
        favoriteMessages[item.identity] = 'remove_failed';
        renderFavorites(currentAccountFavorites);
        var retry = favoritesEl.querySelector('[data-remove-bookmark="' + index + '"]');
        if (retry) retry.focus();
      });
  });

  function downloadAccountData(button) {
    var accountStatus = document.getElementById('myr-account-status');
    button.disabled = true;
    fetch('/api/me/export', { credentials: 'same-origin' })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        var blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        var url = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = 'structural-account-export.json';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      })
      .catch(function () { if (accountStatus) accountStatus.textContent = '导出失败，请稍后重试。'; })
      .finally(function () { button.disabled = false; });
  }

  function wireAccountActions() {
    var exportButton = document.getElementById('myr-export');
    var logoutButton = document.getElementById('myr-logout');
    var deleteForm = document.getElementById('myr-delete-form');
    var status = document.getElementById('myr-account-status');
    if (exportButton) exportButton.addEventListener('click', function () { downloadAccountData(exportButton); });
    if (logoutButton) logoutButton.addEventListener('click', function () {
      logoutButton.disabled = true;
      fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' })
        .then(function (response) { if (!response.ok) throw new Error(); window.location.reload(); })
        .catch(function () { status.textContent = '退出失败，会话仍保留；请稍后重试。'; logoutButton.disabled = false; });
    });
    if (deleteForm) deleteForm.addEventListener('submit', function (event) {
      event.preventDefault();
      var input = document.getElementById('myr-delete-confirmation');
      var button = document.getElementById('myr-delete');
      if (!input || input.value !== 'DELETE') { status.textContent = '请输入 DELETE 才能永久删除。'; if (input) input.focus(); return; }
      button.disabled = true;
      fetch('/api/me/delete', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmation: 'DELETE' })
      }).then(function (response) {
        if (!response.ok) throw new Error();
        try { localStorage.removeItem('structural_favorites'); } catch (_error) {}
        window.location.assign('/?account=deleted');
      }).catch(function () { status.textContent = '删除没有完成，账户与数据仍保留。请稍后重试。'; button.disabled = false; });
    });
  }

  function loadAccount() {
    if (!accountEl) return Promise.resolve({ kind: 'unavailable' });
    return fetch('/api/auth/me', { credentials: 'same-origin' })
      .then(function (response) {
        if ([401, 404, 409].indexOf(response.status) !== -1) {
          return readProblem(response).then(function (problem) {
            if (isCredentialConflict(response, problem)) return { kind: 'conflict' };
            if (response.status === 401 || response.status === 404) return { kind: 'anonymous' };
            throw new Error('HTTP ' + response.status);
          });
        }
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json().then(function (data) {
          return data && data.user
            ? { kind: 'authenticated', user: data.user }
            : { kind: 'anonymous' };
        });
      })
      .then(function (identity) {
        if (identity.kind === 'conflict') {
          lockCredentialAssets();
          return identity;
        }
        if (identity.kind === 'anonymous') {
          accountEl.innerHTML = '<p class="myr-state__hint">尚未登录。本机报告和收藏不会自动跨设备同步。</p>' +
            '<div class="myr-account-actions"><a href="/auth/login?next=%2Freports">登录以同步</a></div>';
          return identity;
        }
        var user = identity.user;
        accountEl.innerHTML = '<p class="myr-account-email">' + escapeHtml(user.email || '') + '</p>' +
          '<div class="myr-account-actions"><button type="button" id="myr-export">导出我的数据</button>' +
          '<button type="button" id="myr-logout">退出登录</button><span id="myr-account-status" role="status" aria-live="polite"></span></div>' +
          '<details class="myr-account-danger"><summary>永久删除账户与关联数据</summary>' +
          '<form id="myr-delete-form" class="myr-delete-form"><label for="myr-delete-confirmation">此操作不可撤销。输入 <strong>DELETE</strong>，删除账户、会话、账户收藏和已认领报告。</label>' +
          '<input id="myr-delete-confirmation" autocomplete="off" spellcheck="false" aria-describedby="myr-account-status">' +
          '<button id="myr-delete" type="submit">永久删除</button></form></details>';
        wireAccountActions();
        return identity;
      })
      .catch(function (error) {
        console.error('[my-reports] identity classification failed');
        accountEl.innerHTML = '<p class="myr-state__hint">暂时无法确认账户状态。为避免读错资产，本机与账户研究均未读取。</p>';
        if (favoritesCopy) favoritesCopy.textContent = '身份确认失败；未读取本机或账户收藏。';
        if (favoritesEl) favoritesEl.innerHTML = '<span class="myr-state__hint">确认身份后再显示收藏。</span>';
        if (reminderSummary) reminderSummary.textContent = '身份确认失败；未读取本机实验提醒。';
        renderState('暂时无法确认账户', '没有读取本机或账户报告。请刷新后重试。', '重试', '/reports');
        return { kind: 'unavailable' };
      });
  }

  function fmtDate(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  }

  function remindersEnabled() {
    try {
      var value = localStorage.getItem(REMINDER_KEY);
      return value === null || value === 'on';
    } catch (e) { return true; }
  }

  function parseLocalDate(value) {
    var match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
    if (!match) return null;
    var date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    if (date.getFullYear() !== Number(match[1]) || date.getMonth() !== Number(match[2]) - 1 || date.getDate() !== Number(match[3])) return null;
    return date;
  }

  function deadlineState(item, now) {
    if (!item || item.followup_status === 'abandoned' || (item.followup_outcome && item.followup_outcome !== 'too_early') || TERMINAL_EXPERIMENTS.indexOf(item.experiment_status) !== -1) return { kind: 'done', days: null };
    if (!item.experiment_deadline) return { kind: 'none', days: null };
    var deadline = parseLocalDate(item.experiment_deadline);
    if (!deadline) return { kind: 'invalid', days: null };
    var current = now ? new Date(now) : new Date();
    var todayDay = Date.UTC(current.getFullYear(), current.getMonth(), current.getDate());
    var deadlineDay = Date.UTC(deadline.getFullYear(), deadline.getMonth(), deadline.getDate());
    var days = (deadlineDay - todayDay) / 86400000;
    if (days < 0) return { kind: 'overdue', days: days };
    if (days === 0) return { kind: 'today', days: 0 };
    if (days <= 3) return { kind: 'soon', days: days };
    return { kind: 'future', days: days };
  }

  function deadlineLabel(item) {
    var state = deadlineState(item);
    if (state.kind === 'overdue') return { text: '已逾期 ' + Math.abs(state.days) + ' 天', css: 'myr-card__deadline--overdue' };
    if (state.kind === 'today') return { text: '今天到期', css: 'myr-card__deadline--soon' };
    if (state.kind === 'soon') return { text: state.days + ' 天后到期', css: 'myr-card__deadline--soon' };
    if (state.kind === 'future') return { text: '截止 ' + item.experiment_deadline, css: '' };
    if (state.kind === 'invalid') return { text: '日期无效，请修正', css: 'myr-card__deadline--overdue' };
    if (state.kind === 'none' && item && item.has_followup) return { text: '未设置截止日期', css: '' };
    return null;
  }

  function updateReminderSummary() {
    if (!reminderSummary) return;
    var enabled = remindersEnabled();
    var overdue = loadedItems.filter(function (item) { return deadlineState(item).kind === 'overdue'; }).length;
    var soon = loadedItems.filter(function (item) { return ['today', 'soon'].indexOf(deadlineState(item).kind) !== -1; }).length;
    var status = overdue || soon ? overdue + ' 个实验已逾期，' + soon + ' 个将在 3 天内到期。' : '当前没有即将到期的实验。';
    var main = enabled ? status : '本地提醒已关闭；' + status;
    if (hasMoreItems) main += ' 计数仅含当前已加载的报告。';
    reminderSummary.innerHTML = escapeHtml(main) + '<span class="myr-reminder-panel__privacy">仅在这台设备打开 Structural 时提示，不发送邮件或系统通知。</span>';
    if (reminderToggle) reminderToggle.checked = enabled;
  }

  var BUCKETS = [
    { id: 'today', title: '今天', hint: '今天创建，尚未进入实验的报告' },
    { id: 'week', title: '本周', hint: '近 7 天创建，可以决定下一步的报告' },
    { id: 'waiting', title: '等待推进', hint: '已规划、进行中、等待结果或超过 7 天尚未处理' },
    { id: 'completed', title: '已完成', hint: '已记录有效、部分有效、无效或放弃的结果' }
  ];

  function reportBucket(item, now) {
    var outcome = item && item.followup_outcome;
    var status = item && item.followup_status;
    if ((outcome && outcome !== 'too_early') || status === 'abandoned' || TERMINAL_EXPERIMENTS.indexOf(item && item.experiment_status) !== -1) return 'completed';
    if (item && item.has_followup) return 'waiting';
    var created = new Date(item && item.created_at);
    if (isNaN(created.getTime())) return 'waiting';
    var current = now || new Date();
    if (created.toDateString() === current.toDateString()) return 'today';
    var age = current.getTime() - created.getTime();
    if (age >= 0 && age < 7 * 24 * 60 * 60 * 1000) return 'week';
    return 'waiting';
  }

  function bucketEl(id) {
    var existing = document.getElementById('myr-bucket-' + id);
    if (existing) return existing.querySelector('[data-bucket-items]');
    var meta = BUCKETS.find(function (bucket) { return bucket.id === id; });
    if (!meta) return null;
    var section = document.createElement('section');
    section.id = 'myr-bucket-' + id;
    section.className = 'myr-bucket';
    section.setAttribute('aria-labelledby', section.id + '-title');
    section.innerHTML =
      '<div class="myr-bucket__head">' +
        '<h2 id="' + section.id + '-title">' + escapeHtml(meta.title) + '</h2>' +
        '<p>' + escapeHtml(meta.hint) + '</p>' +
      '</div>' +
      '<div class="myr-bucket__items" data-bucket-items></div>';
    var index = BUCKETS.findIndex(function (bucket) { return bucket.id === id; });
    var next = null;
    for (var i = index + 1; i < BUCKETS.length; i += 1) {
      next = document.getElementById('myr-bucket-' + BUCKETS[i].id);
      if (next) break;
    }
    listEl.insertBefore(section, next);
    return section.querySelector('[data-bucket-items]');
  }

  // User-reported outcomes stay distinct from independent mechanism evidence.
  function followupBadge(item) {
    var deadline = deadlineState(item);
    if (deadline.kind === 'overdue') {
      return '<span class="myr-card__badge myr-card__badge--overdue">已逾期</span>';
    }
    if (deadline.kind === 'today') {
      return '<span class="myr-card__badge myr-card__badge--todo">今天到期</span>';
    }
    if (item && item.followup_outcome === 'worked') {
      return '<span class="myr-card__badge myr-card__badge--verified">用户记录有效</span>';
    }
    if (item && item.followup_outcome === 'partial') {
      return '<span class="myr-card__badge myr-card__badge--verified">部分有效</span>';
    }
    if (item && (item.followup_outcome === 'no_effect' || item.followup_status === 'abandoned')) {
      return '<span class="myr-card__badge myr-card__badge--todo">无效</span>';
    }
    if (item && item.followup_status === 'in_progress') {
      return '<span class="myr-card__badge myr-card__badge--todo">进行中</span>';
    }
    return '<span class="myr-card__badge myr-card__badge--todo">待回访</span>';
  }

  function cardHtml(item) {
    // id is a server-minted opaque token, but escape it anyway — it lands
    // in an href; never trust a field straight into the DOM.
    var id = escapeHtml(item.id);
    var due = deadlineLabel(item);
    var meta =
      '<div class="myr-card__meta">' +
        '<span>📅 ' + escapeHtml(fmtDate(item.created_at)) + '</span>' +
        '<span>👁 ' + (parseInt(item.view_count, 10) || 0) + ' 次浏览</span>' +
        (item.lang ? '<span class="myr-card__lang">' + escapeHtml(item.lang) + '</span>' : '') +
        (due ? '<span class="myr-card__deadline ' + due.css + '">' + escapeHtml(due.text) + '</span>' : '') +
      '</div>';
    // Library navigation always uses the authenticated/anonymous owner route.
    // Share capabilities are minted and revealed only on one opened report.
    var href = '/report/' + id;
    var originHref = originCandidateHref(item.origin_candidate);
    var originAction = originHref
      ? '<a class="myr-card__origin" href="' + originHref + '">' +
          '<span>源候选</span><strong>返回精选发现</strong>' +
        '</a>'
      : '';
    var consentAction = accountConnected && item.publish_to_insights
      ? '<div class="myr-card__privacy">' +
          '<span>公开聚合已暂停；该报告仍保留旧同意记录。</span>' +
          '<button type="button" data-withdraw-insights-consent="' + id + '">撤回同意</button>' +
        '</div>'
      : '';
    var deleteAction = accountConnected
      ? '<div class="myr-card__report-actions" data-report-actions="' + id + '">' +
          '<span data-delete-status aria-live="polite">删除后分享链接也会立即失效。</span>' +
          '<div class="myr-card__report-buttons">' +
            '<button type="button" class="myr-card__delete" data-delete-report="' + id + '" aria-label="删除报告：' + escapeHtml(item.query || '未命名查询') + '">删除报告</button>' +
          '</div>' +
        '</div>'
      : '';
    return (
      '<div class="myr-card-wrap">' +
        '<a class="myr-card" href="' + href + '">' +
          '<div class="myr-card__head">' +
            '<p class="myr-card__query">' + escapeHtml(item.query || '（未命名查询）') + '</p>' +
            followupBadge(item) +
          '</div>' +
          meta +
        '</a>' +
        originAction + consentAction + deleteAction +
      '</div>'
    );
  }

  function renderState(title, hint, ctaText, ctaHref) {
    listEl.innerHTML =
      '<div class="myr-state">' +
        '<p class="myr-state__title">' + escapeHtml(title) + '</p>' +
        '<p class="myr-state__hint">' + escapeHtml(hint) + '</p>' +
        (ctaText ? '<a class="myr-state__cta" href="' + escapeHtml(ctaHref) + '">' +
          escapeHtml(ctaText) + '</a>' : '') +
      '</div>';
    moreBtn.hidden = true;
  }

  function showEmpty() {
    renderState(
      '还没有保存的报告',
      '你选择保存的研究报告会出现在这里，方便继续实验和记录结果。',
      '去生成第一份报告', '/'
    );
  }

  function appendItems(items) {
    // First page replaces the skeleton; later pages append.
    if (offset === 0) {
      listEl.innerHTML = '';
    }
    items.forEach(function (item) {
      var target = bucketEl(reportBucket(item));
      if (target) target.insertAdjacentHTML('beforeend', cardHtml(item));
    });
    loadedItems = loadedItems.concat(items);
    updateReminderSummary();
  }

  function commitReportData(data) {
    var items = (data && data.items) || [];
    if (offset === 0 && items.length === 0) {
      showEmpty();
      return;
    }
    appendItems(items);
    offset += items.length;
    hasMoreItems = !!(data && data.has_more);
    moreBtn.hidden = !hasMoreItems;
    moreBtn.disabled = false;
    updateReminderSummary();
  }

  function stageAuthenticatedEndpoint(url) {
    return fetch(url, { credentials: 'include' })
      .then(function (response) {
        if ([401, 404, 409].indexOf(response.status) !== -1) {
          return readProblem(response).then(function (problem) {
            if (isCredentialConflict(response, problem)) return { kind: 'conflict' };
            return { kind: 'error', status: response.status };
          });
        }
        if (!response.ok) return { kind: 'error', status: response.status };
        return response.json()
          .then(function (data) { return { kind: 'ok', data: data }; })
          .catch(function () { return { kind: 'error', status: response.status }; });
      })
      .catch(function () { return { kind: 'error', status: 0 }; });
  }

  function loadAuthenticatedAssetsAtomically() {
    loading = true;
    moreBtn.disabled = true;
    var reportsUrl = '/api/me/reports?limit=' + PAGE_SIZE + '&offset=' + offset;
    return Promise.all([
      stageAuthenticatedEndpoint(reportsUrl),
      stageAuthenticatedEndpoint('/api/favorites')
    ]).then(function (staged) {
      var reports = staged[0];
      var favorites = staged[1];
      if (reports.kind === 'conflict' || favorites.kind === 'conflict') {
        lockCredentialAssets();
        return;
      }

      // Commit begins only after both credential-bearing endpoints have
      // completed without a conflict. Local assets are unread before here.
      enableLocalFeatures();
      accountConnected = true;
      connectBtn.hidden = !getAnonId();
      connectBtn.textContent = '同步此浏览器的新报告';
      ownershipCopy.textContent = '这些报告已与你的 Structural 账户关联，可在其他已登录设备继续。';

      var favoriteCommit;
      if (favorites.kind === 'ok') {
        favoriteCommit = syncLocalFavorites(favorites.data);
      } else {
        if (favoritesCopy) favoritesCopy.textContent = '账户收藏暂时无法读取；本机收藏仍然可用。';
        renderFavorites({ tickers: [], bookmarks: [] });
        favoriteCommit = Promise.resolve({ kind: 'error' });
      }

      return favoriteCommit.then(function (syncResult) {
        if (syncResult && syncResult.kind === 'conflict') return;
        if (reports.kind === 'ok') {
          commitReportData(reports.data);
        } else {
          renderState('报告暂时无法读取', '账户身份已确认，但报告服务暂时不可用。收藏状态仍单独显示。', '重试', '/reports');
        }
      });
    }).finally(function () {
      loading = false;
    });
  }

  function load() {
    if (loading) return;
    loading = true;
    moreBtn.disabled = true;
    var accountUrl = '/api/me/reports?limit=' + PAGE_SIZE + '&offset=' + offset;

    fetch(accountUrl, { credentials: 'include' })
      .then(function (r) {
        if ([401, 404, 409].indexOf(r.status) !== -1) {
          return readProblem(r).then(function (problem) {
            if (isCredentialConflict(r, problem)) throw new Error('credential_conflict');
            if (r.status === 409) throw new Error('HTTP ' + r.status);
            var anonId = getAnonId();
            connectBtn.hidden = !anonId;
            ownershipCopy.textContent = anonId
              ? '当前显示这台浏览器保存的报告。登录后可主动同步到其他设备。'
              : '登录后可在不同设备继续已同步的报告。';
            if (!anonId) return { items: [], has_more: false };
            return fetch('/api/reports/mine?limit=' + PAGE_SIZE + '&offset=' + offset, {
              headers: { 'X-Anon-Id': anonId }
            }).then(function (legacy) {
              if (!legacy.ok) throw new Error('HTTP ' + legacy.status);
              return legacy.json();
            });
          });
        }
        if (!r.ok) throw new Error('HTTP ' + r.status);
        accountConnected = true;
        connectBtn.hidden = !getAnonId();
        connectBtn.textContent = '同步此浏览器的新报告';
        ownershipCopy.textContent = '这些报告已与你的 Structural 账户关联，可在其他已登录设备继续。';
        return r.json();
      })
      .then(function (data) {
        if (credentialLocked) return;
        commitReportData(data);
      })
      .catch(function (err) {
        console.error('[my-reports] load failed');
        if (offset === 0) {
          if (err && err.message === 'credential_conflict') {
            lockCredentialAssets();
          } else {
            renderState('加载失败', '稍后刷新重试。若反复失败，多半是网络问题。', '重试', '/reports');
          }
        } else {
          moreBtn.disabled = false;
          moreBtn.textContent = '加载失败，点击重试';
        }
      })
      .finally(function () { loading = false; });
  }

  moreBtn.addEventListener('click', function () {
    moreBtn.textContent = '加载更多';
    load();
  });

  listEl.addEventListener('click', function (event) {
    var button = event.target.closest('[data-withdraw-insights-consent]');
    if (button) {
      var consentReportId = button.getAttribute('data-withdraw-insights-consent');
      if (!consentReportId || button.disabled) return;
      button.disabled = true;
      button.textContent = '撤回中…';
      fetch('/api/me/reports/' + encodeURIComponent(consentReportId) + '/insights-consent', {
        method: 'DELETE', credentials: 'include'
      }).then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      }).then(function () {
        var row = button.closest('.myr-card__privacy');
        if (row) row.innerHTML = '<span role="status">已撤回；该报告结果保持私密。</span>';
        loadedItems.forEach(function (item) {
          if (item.id === consentReportId) item.publish_to_insights = false;
        });
      }).catch(function () {
        button.disabled = false;
        button.textContent = '重试撤回';
        var row = button.closest('.myr-card__privacy');
        var message = row && row.querySelector('[data-withdraw-error]');
        if (!message && row) {
          row.insertAdjacentHTML('beforeend', '<span data-withdraw-error role="alert">撤回失败，旧同意不变。</span>');
        }
      });
      return;
    }

    var cancelDelete = event.target.closest('[data-cancel-delete-report]');
    if (cancelDelete) {
      var cancelRow = cancelDelete.closest('[data-report-actions]');
      var armedButton = cancelRow && cancelRow.querySelector('[data-delete-report]');
      var cancelStatus = cancelRow && cancelRow.querySelector('[data-delete-status]');
      if (armedButton) {
        armedButton.removeAttribute('data-delete-armed');
        armedButton.textContent = '删除报告';
        armedButton.focus();
      }
      if (cancelStatus) {
        cancelStatus.textContent = '删除后分享链接也会立即失效。';
        cancelStatus.removeAttribute('role');
      }
      cancelDelete.remove();
      return;
    }

    var deleteButton = event.target.closest('[data-delete-report]');
    if (!deleteButton || deleteButton.disabled) return;
    var reportId = deleteButton.getAttribute('data-delete-report');
    var actionRow = deleteButton.closest('[data-report-actions]');
    var deleteStatus = actionRow && actionRow.querySelector('[data-delete-status]');
    var buttonGroup = deleteButton.closest('.myr-card__report-buttons');
    if (!reportId || !actionRow || !deleteStatus || !buttonGroup) return;
    if (!deleteButton.hasAttribute('data-delete-armed')) {
      deleteButton.setAttribute('data-delete-armed', 'true');
      deleteButton.textContent = '确认永久删除';
      deleteStatus.removeAttribute('role');
      deleteStatus.textContent = '此操作不可撤销；报告、实验记录、反馈和分享链接都会删除。';
      buttonGroup.insertAdjacentHTML(
        'afterbegin',
        '<button type="button" data-cancel-delete-report>取消</button>'
      );
      deleteButton.focus();
      return;
    }

    deleteButton.disabled = true;
    var cancel = buttonGroup.querySelector('[data-cancel-delete-report]');
    if (cancel) cancel.disabled = true;
    deleteButton.textContent = '正在删除…';
    deleteStatus.textContent = '正在删除报告并使分享链接失效…';
    fetch('/api/me/reports/' + encodeURIComponent(reportId), {
      method: 'DELETE', credentials: 'include'
    }).then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    }).then(function (result) {
      if (!result || result.share_revoked !== true) throw new Error('incomplete deletion');
      var wrapper = actionRow.closest('.myr-card-wrap');
      var bucket = actionRow.closest('.myr-bucket');
      loadedItems = loadedItems.filter(function (item) { return item.id !== reportId; });
      if (wrapper) wrapper.remove();
      if (bucket && !bucket.querySelector('.myr-card-wrap')) bucket.remove();
      if (loadedItems.length === 0) showEmpty();
      updateReminderSummary();
      // Keep tabindex=-1 after focusing the updated list/empty state. It is
      // programmatically focusable but remains outside the sequential Tab
      // order; removing it immediately makes Chromium drop focus to <body>.
      listEl.setAttribute('tabindex', '-1');
      listEl.focus();
    }).catch(function () {
      deleteButton.disabled = false;
      if (cancel) cancel.disabled = false;
      deleteButton.textContent = '重试永久删除';
      deleteStatus.textContent = '删除没有完成；报告和分享链接仍然保留。';
      deleteStatus.setAttribute('role', 'alert');
      // Disabling the active button moves keyboard focus to <body> in
      // Chromium. Restore it after re-enabling so Space/Enter can retry the
      // destructive action without forcing the user to traverse the page.
      deleteButton.focus();
    });
  });

  connectBtn.addEventListener('click', function () {
    var anonId = getAnonId();
    if (!anonId) return;
    connectBtn.disabled = true;
    connectError.hidden = true;
    fetch('/api/reports/anon-proof', {
      method: 'POST', credentials: 'include', headers: { 'X-Anon-Id': anonId }
    }).then(function (response) {
      if (!response.ok) throw new Error('proof');
      if (!accountConnected) {
        window.location.assign('/api/sso/start');
        return null;
      }
      return fetch('/api/me/reports/claim', {
        method: 'POST', credentials: 'include'
      }).then(function (claimResponse) {
        if (!claimResponse.ok) throw new Error('claim');
        window.location.reload();
      });
    }).catch(function () {
      connectBtn.disabled = false;
      connectError.textContent = '无法准备同步。报告仍保留在本浏览器，请稍后重试。';
      connectError.hidden = false;
    });
  });

  function enableLocalFeatures() {
    localFeaturesEnabled = true;
    if (reminderToggle && !reminderToggle.__myrWired) {
      reminderToggle.__myrWired = true;
      reminderToggle.checked = remindersEnabled();
      reminderToggle.addEventListener('change', function () {
        try { localStorage.setItem(REMINDER_KEY, reminderToggle.checked ? 'on' : 'off'); } catch (e) {}
        updateReminderSummary();
      });
    }
    updateReminderSummary();
  }

  if (window.i18n && typeof window.i18n.onChange === 'function') {
    window.i18n.onChange(function () {
      if (!credentialLocked && localFeaturesEnabled) renderFavorites(currentAccountFavorites);
    });
  }

  loadAccount().then(function (identity) {
    if (!identity || identity.kind === 'conflict' || identity.kind === 'unavailable') return;
    if (identity.kind === 'authenticated') {
      loadAuthenticatedAssetsAtomically();
      return;
    }
    enableLocalFeatures();
    loadFavorites(false);
    load();
  });

  window.__myReports = { reportBucket: reportBucket, deadlineState: deadlineState };
})();
