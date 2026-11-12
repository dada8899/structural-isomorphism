/* Session #22 — G P3 (mutual-consent match + referrals + messages).

   Pairs with connections.js (P1+P2). This script owns:
     - the tab bar (4 panels: requests, referrals, messages, prefs)
     - polling the 3 inbox-style endpoints to populate badges
     - per-panel render + action handlers

   All endpoints require a session cookie — we assume connections.js has
   already gated unauthenticated users to the login form. If a fetch comes
   back 401 we fall back to a reload (the gate will catch it). */
(function () {
  'use strict';

  var esc = window.escapeHtml || function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;',
        '"': '&quot;', "'": '&#39;' }[c];
    });
  };

  function $(id) { return document.getElementById(id); }
  function show(el) { if (el) el.classList.remove('cn-hidden'); }
  function hide(el) { if (el) el.classList.add('cn-hidden'); }

  function p3Fetch(path, opts) {
    opts = opts || {};
    opts.credentials = 'same-origin';
    opts.headers = Object.assign(
      { 'Content-Type': 'application/json' }, opts.headers || {}
    );
    return fetch('/api' + path, opts).then(function (r) {
      return r.json().then(function (d) {
        return { ok: r.ok, status: r.status, d: d };
      });
    });
  }

  function flash(text, kind) {
    var box = $('cn-msg');
    if (!box) return;
    box.textContent = text;
    box.className = 'cn-msg cn-msg--' + (kind === 'ok' ? 'ok' : 'err');
    show(box);
    if (kind === 'ok') setTimeout(function () { hide(box); }, 3500);
  }

  function fmtTime(iso) {
    if (!iso) return '';
    try {
      var d = new Date(iso);
      return d.toLocaleString('zh-CN', {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
      });
    } catch (e) { return iso; }
  }

  function pill(text, kind) {
    return '<span class="cn-pill cn-pill--' + kind + '">' + esc(text) + '</span>';
  }

  // ---------------- tabs ---------------- //

  function setBadge(id, n) {
    var b = $(id);
    if (!b) return;
    if (n > 0) {
      b.textContent = n;
      show(b);
    } else {
      hide(b);
    }
  }

  function switchTab(name) {
    var tabs = document.querySelectorAll('.cn-tab');
    tabs.forEach(function (t) {
      if (t.dataset.tab === name) {
        t.classList.add('cn-tab--active');
      } else {
        t.classList.remove('cn-tab--active');
      }
    });
    var panels = document.querySelectorAll('.cn-panel');
    panels.forEach(function (p) {
      if (p.id === 'cn-panel-' + name) {
        show(p);
      } else {
        hide(p);
      }
    });
    // Lazy-load each panel's data
    if (name === 'requests') loadMatchRequests();
    if (name === 'referrals') loadReferrals();
    if (name === 'messages') loadMessages();
    if (name === 'prefs') loadPrefs();
  }

  function bindTabs() {
    var bar = $('cn-tabs');
    if (!bar) return;
    bar.addEventListener('click', function (e) {
      if (e.target && e.target.dataset && e.target.dataset.tab) {
        switchTab(e.target.dataset.tab);
      }
    });
  }

  // ---------------- match requests ---------------- //

  function renderMatchRequestPending(r) {
    var el = document.createElement('div');
    el.className = 'cn-row';
    el.innerHTML =
      '<div class="cn-row__top">' +
        '<div>' +
          '<p class="cn-row__title">有人想跟你建立连接</p>' +
          '<p class="cn-row__sub">对方匿名 · ' + esc(fmtTime(r.created_at)) + '</p>' +
        '</div>' + pill('待你回应', 'pending') +
      '</div>' +
      (r.note ? '<p class="cn-row__body">附言：' + esc(r.note) + '</p>' : '') +
      '<div class="cn-row__actions">' +
        '<button class="cn-btn cn-btn--primary" data-act="accept">接受</button>' +
        '<button class="cn-btn" data-act="decline">拒绝</button>' +
      '</div>';
    el.querySelector('[data-act="accept"]').addEventListener('click', function () {
      respondMatch(r.id, true);
    });
    el.querySelector('[data-act="decline"]').addEventListener('click', function () {
      respondMatch(r.id, false);
    });
    return el;
  }

  function renderMatchRequestSent(r) {
    var statusKind = r.status === 'accepted' ? 'accepted' :
                     r.status === 'declined' ? 'declined' : 'pending';
    var statusText = r.status === 'accepted' ? '对方已接受' :
                     r.status === 'declined' ? '对方已拒绝' : '等待对方回应';
    var el = document.createElement('div');
    el.className = 'cn-row';
    el.innerHTML =
      '<div class="cn-row__top">' +
        '<div>' +
          '<p class="cn-row__title">发给 ' + esc(r.other_email) + '</p>' +
          '<p class="cn-row__sub">' + esc(fmtTime(r.created_at)) + '</p>' +
        '</div>' + pill(statusText, statusKind) +
      '</div>' +
      (r.note ? '<p class="cn-row__body">附言：' + esc(r.note) + '</p>' : '');
    return el;
  }

  function renderMatchAccepted(m) {
    var el = document.createElement('div');
    el.className = 'cn-row';
    el.innerHTML =
      '<div class="cn-row__top">' +
        '<div>' +
          '<p class="cn-row__title">' + esc(m.other_email) + '</p>' +
          '<p class="cn-row__sub">match 于 ' + esc(fmtTime(m.responded_at)) + '</p>' +
        '</div>' + pill('已连接', 'accepted') +
      '</div>' +
      '<div class="cn-row__actions">' +
        '<button class="cn-btn" data-act="message">写一条消息</button>' +
      '</div>';
    el.querySelector('[data-act="message"]').addEventListener('click', function () {
      switchTab('messages');
      var input = $('cn-msg-to');
      if (input) { input.value = m.other_email; input.focus(); }
    });
    return el;
  }

  function respondMatch(rid, accept) {
    var path = '/connections/match-requests/' + encodeURIComponent(rid) +
      (accept ? '/accept' : '/decline');
    p3Fetch(path, { method: 'POST' }).then(function (res) {
      if (!res.ok) {
        flash(res.d.error || '操作失败', 'err');
        return;
      }
      flash(accept ? '已接受，对方现在可以看到你的身份' : '已拒绝', 'ok');
      loadMatchRequests();
    });
  }

  function emptyMsg(text) {
    var d = document.createElement('div');
    d.className = 'cn-empty';
    d.textContent = text;
    return d;
  }

  function loadMatchRequests() {
    Promise.all([
      p3Fetch('/connections/match-requests/pending'),
      p3Fetch('/connections/match-requests/sent'),
      p3Fetch('/connections/match-requests/accepted'),
    ]).then(function (results) {
      var pending = (results[0].ok && results[0].d.match_requests) || [];
      var sent = (results[1].ok && results[1].d.match_requests) || [];
      var accepted = (results[2].ok && results[2].d.matches) || [];

      var pBox = $('cn-requests-pending');
      pBox.innerHTML = '';
      if (pending.length === 0) {
        pBox.appendChild(emptyMsg('暂无待处理请求。'));
      } else {
        pending.forEach(function (r) { pBox.appendChild(renderMatchRequestPending(r)); });
      }
      var sBox = $('cn-requests-sent');
      sBox.innerHTML = '';
      // 只显示非 declined（隐藏冷处理状态对发送方更友好）
      var visibleSent = sent.filter(function (r) { return r.status !== 'declined'; });
      if (visibleSent.length === 0) {
        sBox.appendChild(emptyMsg('你还没有发出过 match 请求。'));
      } else {
        visibleSent.forEach(function (r) { sBox.appendChild(renderMatchRequestSent(r)); });
      }
      var aBox = $('cn-requests-accepted');
      aBox.innerHTML = '';
      if (accepted.length === 0) {
        aBox.appendChild(emptyMsg('还没有达成 match。'));
      } else {
        accepted.forEach(function (m) { aBox.appendChild(renderMatchAccepted(m)); });
      }

      setBadge('cn-badge-requests', pending.length);
    });
  }

  // ---------------- referrals ---------------- //

  function renderReferralRow(r) {
    var el = document.createElement('div');
    el.className = 'cn-row';
    var isCompleted = !!r.completed_at;
    var roleText = r.role === 'referrer' ? '你撮合了' :
                   r.role === 'referee_a' ? esc(r.referrer_email) + ' 把你引荐给了' :
                   esc(r.referrer_email) + ' 把你引荐给了';
    var otherSide = r.role === 'referee_a' ? r.referee_b_email :
                    r.role === 'referee_b' ? r.referee_a_email :
                    esc(r.referee_a_email) + ' 与 ' + esc(r.referee_b_email);
    var mineStatus =
      r.role === 'referee_a' ? r.status_a :
      r.role === 'referee_b' ? r.status_b : null;
    var headerPill;
    if (isCompleted) {
      headerPill = pill('双方都接受', 'accepted');
    } else if (mineStatus === 'pending') {
      headerPill = pill('待你回应', 'pending');
    } else if (mineStatus === 'declined') {
      headerPill = pill('你已拒绝', 'declined');
    } else if (mineStatus === 'accepted') {
      headerPill = pill('已接受，等对方', 'pending');
    } else {
      headerPill = pill('进行中', 'pending');
    }

    el.innerHTML =
      '<div class="cn-row__top">' +
        '<div>' +
          '<p class="cn-row__title">' + roleText + ' ' + esc(otherSide) + '</p>' +
          '<p class="cn-row__sub">' + esc(fmtTime(r.created_at)) + '</p>' +
        '</div>' + headerPill +
      '</div>' +
      (r.reason ? '<p class="cn-row__body">理由：' + esc(r.reason) + '</p>' : '');

    if (r.role !== 'referrer' && mineStatus === 'pending') {
      var actions = document.createElement('div');
      actions.className = 'cn-row__actions';
      actions.innerHTML =
        '<button class="cn-btn cn-btn--primary" data-act="accept">接受引荐</button>' +
        '<button class="cn-btn" data-act="decline">拒绝</button>';
      actions.querySelector('[data-act="accept"]').addEventListener('click', function () {
        respondReferral(r.id, true);
      });
      actions.querySelector('[data-act="decline"]').addEventListener('click', function () {
        respondReferral(r.id, false);
      });
      el.appendChild(actions);
    }
    return el;
  }

  function respondReferral(rid, accept) {
    var path = '/connections/referrals/' + encodeURIComponent(rid) +
      (accept ? '/accept' : '/decline');
    p3Fetch(path, { method: 'POST' }).then(function (res) {
      if (!res.ok) {
        flash(res.d.error || '操作失败', 'err');
        return;
      }
      if (accept && res.d.completed) {
        flash('引荐成功！双方现在可以互通了。', 'ok');
      } else if (accept) {
        flash('已接受，等待对方回应。', 'ok');
      } else {
        flash('已拒绝引荐。', 'ok');
      }
      loadReferrals();
    });
  }

  function loadReferrals() {
    p3Fetch('/connections/referrals').then(function (res) {
      var list = (res.ok && res.d.referrals) || [];
      var box = $('cn-referrals-list');
      box.innerHTML = '';
      if (list.length === 0) {
        box.appendChild(emptyMsg('还没有引荐。'));
      } else {
        list.forEach(function (r) { box.appendChild(renderReferralRow(r)); });
      }
      // Badge: pending action for me (referee with pending status)
      var pending = list.filter(function (r) {
        return (r.role === 'referee_a' && r.status_a === 'pending') ||
               (r.role === 'referee_b' && r.status_b === 'pending');
      });
      setBadge('cn-badge-referrals', pending.length);
    });
  }

  function bindReferralForm() {
    var form = $('cn-referral-form');
    if (!form) return;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var a = ($('cn-ref-a').value || '').trim();
      var b = ($('cn-ref-b').value || '').trim();
      var reason = ($('cn-ref-reason').value || '').trim();
      if (!a || !b) return;
      p3Fetch('/connections/referral', {
        method: 'POST',
        body: JSON.stringify({
          referee_a_email: a,
          referee_b_email: b,
          reason: reason || null,
        }),
      }).then(function (res) {
        if (!res.ok) {
          flash(res.d.error || '发起引荐失败', 'err');
          return;
        }
        flash('引荐已发起，等待双方回应。', 'ok');
        form.reset();
        loadReferrals();
      });
    });
  }

  // ---------------- messages ---------------- //

  function renderComposer(matches) {
    var wrap = $('cn-composer-wrap');
    if (!wrap) return;
    if (!matches || matches.length === 0) {
      wrap.innerHTML =
        '<div class="cn-empty">还没有 match 的人——先在<strong>Match 请求</strong> tab 等接受。</div>';
      return;
    }
    var options = matches.map(function (m) {
      return '<option value="' + esc(m.other_email) + '">' +
        esc(m.other_email) + '</option>';
    }).join('');
    wrap.innerHTML =
      '<div class="cn-composer">' +
        '<label class="cn-form__label" for="cn-msg-to">发给</label>' +
        '<select id="cn-msg-to" class="cn-input">' + options + '</select>' +
        '<label class="cn-form__label" for="cn-msg-body" style="margin-top:10px;">' +
          '消息正文（≤500 字，每天最多 10 条；URL/电话/邮箱会被过滤）' +
        '</label>' +
        '<textarea id="cn-msg-body" class="cn-textarea" maxlength="500"></textarea>' +
        '<div class="cn-composer__row">' +
          '<button class="cn-btn cn-btn--primary" id="cn-msg-send">发送</button>' +
          '<span class="cn-counter" id="cn-msg-counter">0/500</span>' +
        '</div>' +
      '</div>';
    var bodyEl = $('cn-msg-body');
    var counter = $('cn-msg-counter');
    bodyEl.addEventListener('input', function () {
      counter.textContent = bodyEl.value.length + '/500';
    });
    $('cn-msg-send').addEventListener('click', function () {
      var to = $('cn-msg-to').value;
      var body = (bodyEl.value || '').trim();
      if (!to || !body) return;
      p3Fetch('/connections/messages', {
        method: 'POST',
        body: JSON.stringify({ to_email: to, body: body }),
      }).then(function (res) {
        if (!res.ok) {
          var msg = res.d.error || '发送失败';
          if (res.d.category) msg += '（拦截到：' + res.d.category + '）';
          flash(msg, 'err');
          return;
        }
        flash('消息已发送。', 'ok');
        bodyEl.value = '';
        counter.textContent = '0/500';
        loadMessages();
      });
    });
  }

  function renderMessage(m) {
    var el = document.createElement('div');
    el.className = 'cn-row';
    var unreadPill = m.read_at ? '' : pill('未读', 'unread');
    el.innerHTML =
      '<div class="cn-row__top">' +
        '<div>' +
          '<p class="cn-row__title">来自 ' + esc(m.from_email) + '</p>' +
          '<p class="cn-row__sub">' + esc(fmtTime(m.sent_at)) + '</p>' +
        '</div>' + unreadPill +
      '</div>' +
      '<p class="cn-row__body">' + esc(m.body) + '</p>';
    if (!m.read_at) {
      var actions = document.createElement('div');
      actions.className = 'cn-row__actions';
      actions.innerHTML = '<button class="cn-btn" data-act="read">标记已读</button>';
      actions.querySelector('[data-act="read"]').addEventListener('click', function () {
        p3Fetch('/connections/messages/' + encodeURIComponent(m.id) + '/read', {
          method: 'POST',
        }).then(function (res) {
          if (res.ok) loadMessages();
        });
      });
      el.appendChild(actions);
    }
    return el;
  }

  function loadMessages() {
    Promise.all([
      p3Fetch('/connections/match-requests/accepted'),
      p3Fetch('/connections/messages/inbox'),
    ]).then(function (results) {
      var matches = (results[0].ok && results[0].d.matches) || [];
      var msgs = (results[1].ok && results[1].d.messages) || [];

      renderComposer(matches);

      var box = $('cn-messages-inbox');
      box.innerHTML = '';
      if (msgs.length === 0) {
        box.appendChild(emptyMsg('信箱为空。'));
      } else {
        msgs.forEach(function (m) { box.appendChild(renderMessage(m)); });
      }
      var unread = msgs.filter(function (m) { return !m.read_at; }).length;
      setBadge('cn-badge-messages', unread);
    });
  }

  // ---------------- prefs ---------------- //

  function loadPrefs() {
    p3Fetch('/connections/prefs').then(function (res) {
      if (!res.ok) return;
      var p = res.d.prefs || {};
      $('cn-pref-mute').checked = !!p.mute_referrals;
      $('cn-pref-msg').checked = p.messages_open !== false;
      var box = $('cn-blocked-list');
      box.innerHTML = '';
      (p.blocked_emails || []).forEach(function (em) {
        var el = document.createElement('div');
        el.className = 'cn-row';
        el.innerHTML =
          '<div class="cn-row__top">' +
            '<div><p class="cn-row__title">' + esc(em) + '</p></div>' +
            '<button class="cn-btn" data-act="unblock">解除屏蔽</button>' +
          '</div>';
        el.querySelector('[data-act="unblock"]').addEventListener('click', function () {
          p3Fetch('/connections/prefs', {
            method: 'PATCH',
            body: JSON.stringify({ unblock_email: em }),
          }).then(function (r) {
            if (r.ok) { flash('已解除屏蔽', 'ok'); loadPrefs(); }
          });
        });
        box.appendChild(el);
      });
    });
  }

  function bindPrefs() {
    var mute = $('cn-pref-mute');
    var msg = $('cn-pref-msg');
    if (mute) {
      mute.addEventListener('change', function () {
        p3Fetch('/connections/prefs', {
          method: 'PATCH',
          body: JSON.stringify({ mute_referrals: mute.checked }),
        }).then(function (r) {
          if (r.ok) flash('偏好已保存', 'ok');
        });
      });
    }
    if (msg) {
      msg.addEventListener('change', function () {
        p3Fetch('/connections/prefs', {
          method: 'PATCH',
          body: JSON.stringify({ messages_open: msg.checked }),
        }).then(function (r) {
          if (r.ok) flash('偏好已保存', 'ok');
        });
      });
    }
    var form = $('cn-block-form');
    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var em = ($('cn-block-email').value || '').trim();
        if (!em) return;
        p3Fetch('/connections/prefs', {
          method: 'PATCH',
          body: JSON.stringify({ block_email: em }),
        }).then(function (r) {
          if (!r.ok) { flash(r.d.error || '操作失败', 'err'); return; }
          flash('已屏蔽 ' + em, 'ok');
          form.reset();
          loadPrefs();
        });
      });
    }
  }

  // ---------------- background badge polling ---------------- //

  function refreshBadges() {
    // Light counts only — full reload happens on tab switch
    p3Fetch('/connections/match-requests/pending').then(function (res) {
      if (res.ok) setBadge('cn-badge-requests', (res.d.match_requests || []).length);
    });
    p3Fetch('/connections/referrals').then(function (res) {
      if (res.ok) {
        var pending = (res.d.referrals || []).filter(function (r) {
          return (r.role === 'referee_a' && r.status_a === 'pending') ||
                 (r.role === 'referee_b' && r.status_b === 'pending');
        });
        setBadge('cn-badge-referrals', pending.length);
      }
    });
    p3Fetch('/connections/messages/inbox').then(function (res) {
      if (res.ok) {
        var unread = (res.d.messages || []).filter(function (m) { return !m.read_at; }).length;
        setBadge('cn-badge-messages', unread);
      }
    });
  }

  // ---------------- init ---------------- //

  function init() {
    bindTabs();
    bindReferralForm();
    bindPrefs();
    // Probe session first — only poll badges if logged in.
    p3Fetch('/auth/me').then(function (r) {
      if (r.ok) {
        refreshBadges();
        // Poll every 60s as a cheap proxy for push.
        setInterval(refreshBadges, 60000);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
