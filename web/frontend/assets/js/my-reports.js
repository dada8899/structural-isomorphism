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
  var REMINDER_KEY = 'structural_local_reminders';
  var TERMINAL_EXPERIMENTS = ['completed', 'stopped', 'abandoned'];

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function getAnonId() {
    try { return localStorage.getItem('anonId') || ''; } catch (e) { return ''; }
  }

  function trackPlausible(event, props) {
    try {
      if (typeof window.plausible === 'function') {
        window.plausible(event, props ? { props: props } : undefined);
      }
    } catch (e) { /* ignore */ }
  }

  function safeLocalHref(value, fallback) {
    var href = String(value || '').trim();
    if (!href.startsWith('/') || href.startsWith('//') || href.indexOf('\\') !== -1) return fallback;
    return href;
  }

  function localFavorites() {
    try {
      var parsed = JSON.parse(localStorage.getItem('structural_favorites') || '[]');
      return Array.isArray(parsed) ? parsed.slice(0, 100) : [];
    } catch (_error) { return []; }
  }

  function favoriteLink(label, href, kind) {
    return '<a class="myr-favorite" href="' + escapeHtml(href) + '"' +
      (href.indexOf('https://') === 0 ? ' target="_blank" rel="noopener"' : '') +
      '><span>' + escapeHtml(label) + '</span><span class="myr-favorite__source">' + escapeHtml(kind) + '</span></a>';
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

  function renderFavorites(accountTickers) {
    if (!favoritesEl || credentialLocked) return;
    var local = localFavorites();
    var links = local.map(function (item) {
      var label = item.query || item.b_name || item.b_id || '未命名候选';
      return favoriteLink(label, safeLocalHref(item.analyze_url, '/'), '本机研究收藏');
    });
    (accountTickers || []).forEach(function (ticker) {
      if (!/^[A-Za-z0-9._-]{1,20}$/.test(ticker)) return;
      links.push(favoriteLink(
        ticker,
        'https://phase.bytedance.city/company/' + encodeURIComponent(ticker),
        'Phase 子产品账户收藏'
      ));
    });
    favoritesEl.innerHTML = links.length
      ? links.join('')
      : '<span class="myr-state__hint">还没有收藏。选择候选或在 Phase 中收藏公司后，会出现在这里。</span>';
  }

  function loadFavorites(authenticated) {
    if (!favoritesEl || credentialLocked) return;
    if (!authenticated) {
      if (favoritesCopy) favoritesCopy.textContent = '当前显示这台浏览器的研究收藏；登录后还会显示账户收藏。';
      renderFavorites([]);
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
        if (favoritesCopy) favoritesCopy.textContent = '同时显示本机研究收藏和账户中的 Phase 子产品收藏，并明确标注来源。';
        renderFavorites(Array.isArray(data.tickers) ? data.tickers : []);
      })
      .catch(function (error) {
        if (error && error.message === 'credential_conflict') {
          lockCredentialAssets();
          return;
        }
        if (credentialLocked) return;
        if (favoritesCopy) favoritesCopy.textContent = '账户收藏暂时无法读取；本机收藏仍然可用。';
        renderFavorites([]);
      });
  }

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
        console.error('[my-reports] identity classification failed:', error);
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
    var href = item.share_token
      ? '/report/share/' + escapeHtml(item.share_token)
      : '/report/' + id;
    return (
      '<a class="myr-card" href="' + href + '">' +
        '<div class="myr-card__head">' +
          '<p class="myr-card__query">' + escapeHtml(item.query || '（未命名查询）') + '</p>' +
          followupBadge(item) +
        '</div>' +
        meta +
      '</a>'
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
      trackPlausible('Report List Viewed', { count: 0 });
      return;
    }
    appendItems(items);
    offset += items.length;
    hasMoreItems = !!(data && data.has_more);
    moreBtn.hidden = !hasMoreItems;
    moreBtn.disabled = false;
    updateReminderSummary();
    trackPlausible('Report List Viewed', { count: offset });
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

      if (reports.kind === 'ok') {
        commitReportData(reports.data);
      } else {
        renderState('报告暂时无法读取', '账户身份已确认，但报告服务暂时不可用。收藏状态仍单独显示。', '重试', '/reports');
      }

      if (favorites.kind === 'ok') {
        if (favoritesCopy) favoritesCopy.textContent = '同时显示本机研究收藏和账户中的 Phase 子产品收藏，并明确标注来源。';
        renderFavorites(Array.isArray(favorites.data.tickers) ? favorites.data.tickers : []);
      } else {
        if (favoritesCopy) favoritesCopy.textContent = '账户收藏暂时无法读取；本机收藏仍然可用。';
        renderFavorites([]);
      }
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
        console.error('[my-reports] load failed:', err);
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
    if (reminderToggle && !reminderToggle.__myrWired) {
      reminderToggle.__myrWired = true;
      reminderToggle.checked = remindersEnabled();
      reminderToggle.addEventListener('change', function () {
        try { localStorage.setItem(REMINDER_KEY, reminderToggle.checked ? 'on' : 'off'); } catch (e) {}
        updateReminderSummary();
        trackPlausible('Local Experiment Reminders Changed', { enabled: reminderToggle.checked });
      });
    }
    updateReminderSummary();
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
