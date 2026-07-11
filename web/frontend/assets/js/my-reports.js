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
  var offset = 0;
  var loading = false;

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

  var BUCKETS = [
    { id: 'today', title: '今天', hint: '今天创建，尚未进入实验的报告' },
    { id: 'week', title: '本周', hint: '近 7 天创建，可以决定下一步的报告' },
    { id: 'waiting', title: '等待推进', hint: '已规划、进行中、等待结果或超过 7 天尚未处理' },
    { id: 'completed', title: '已完成', hint: '已记录有效、部分有效、无效或放弃的结果' }
  ];

  function reportBucket(item, now) {
    var outcome = item && item.followup_outcome;
    var status = item && item.followup_status;
    if ((outcome && outcome !== 'too_early') || status === 'abandoned') return 'completed';
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
    var meta =
      '<div class="myr-card__meta">' +
        '<span>📅 ' + escapeHtml(fmtDate(item.created_at)) + '</span>' +
        '<span>👁 ' + (parseInt(item.view_count, 10) || 0) + ' 次浏览</span>' +
        (item.lang ? '<span class="myr-card__lang">' + escapeHtml(item.lang) + '</span>' : '') +
      '</div>';
    return (
      '<a class="myr-card" href="/report/' + id + '">' +
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
  }

  function load() {
    if (loading) return;
    var anonId = getAnonId();
    if (!anonId) { showEmpty(); return; }

    loading = true;
    moreBtn.disabled = true;
    var url = '/api/reports/mine?limit=' + PAGE_SIZE + '&offset=' + offset;

    fetch(url, { headers: { 'X-Anon-Id': anonId } })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
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
        moreBtn.hidden = !(data && data.has_more);
        moreBtn.disabled = false;
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

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }

  window.__myReports = { reportBucket: reportBucket };
})();
