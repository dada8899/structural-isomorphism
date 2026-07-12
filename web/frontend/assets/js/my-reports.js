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

  // B Data Flywheel (Session #18) — revisit badge. A report the user has
  // not yet recorded an outcome for gets a gentle '未回访' tag nudging them
  // to come back and report whether the borrowed structure worked. A
  // report already marked outcome='worked' gets a positive '已验证' tag.
  function followupBadge(item) {
    var deadline = deadlineState(item);
    if (deadline.kind === 'overdue') {
      return '<span class="myr-card__badge myr-card__badge--overdue">已逾期</span>';
    }
    if (deadline.kind === 'today') {
      return '<span class="myr-card__badge myr-card__badge--todo">今天到期</span>';
    }
    if (item && item.followup_outcome === 'worked') {
      return '<span class="myr-card__badge myr-card__badge--verified">已验证</span>';
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
      '你生成的研究报告会自动出现在这里，方便随时回看。',
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

  function load() {
    if (loading) return;
    loading = true;
    moreBtn.disabled = true;
    var accountUrl = '/api/me/reports?limit=' + PAGE_SIZE + '&offset=' + offset;

    fetch(accountUrl, { credentials: 'include' })
      .then(function (r) {
        if (r.status === 401 || r.status === 404) {
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
        }
        if (!r.ok) throw new Error('HTTP ' + r.status);
        accountConnected = true;
        connectBtn.hidden = !getAnonId();
        connectBtn.textContent = '同步此浏览器的新报告';
        ownershipCopy.textContent = '这些报告已与你的 Structural 账户关联，可在其他已登录设备继续。';
        return r.json();
      })
      .then(function (data) {
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
      })
      .catch(function (err) {
        console.error('[my-reports] load failed:', err);
        if (offset === 0) {
          renderState('加载失败', '稍后刷新重试。若反复失败，多半是网络问题。', '重试', '/reports');
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

  if (reminderToggle) {
    reminderToggle.checked = remindersEnabled();
    reminderToggle.addEventListener('change', function () {
      try { localStorage.setItem(REMINDER_KEY, reminderToggle.checked ? 'on' : 'off'); } catch (e) {}
      updateReminderSummary();
      trackPlausible('Local Experiment Reminders Changed', { enabled: reminderToggle.checked });
    });
  }
  updateReminderSummary();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }

  window.__myReports = { reportBucket: reportBucket, deadlineState: deadlineState };
})();
