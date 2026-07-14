/* Session #19 — G connect-people MVP (/connections).

   Manages a logged-in user's structural fingerprints + shows "structural
   neighbors" (how many people are solving a structurally-identical but
   cross-domain problem). All identity info is hidden — L1 is "N people",
   never "who".

   Auth: relies on the magic-link session cookie (phase_session). When no
   session, shows an inline login gate. Endpoints need credentials, so all
   fetches go through cnFetch() with credentials:'same-origin'. */
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

  var VIS_LABEL = {
    L0: '私密',
    L1: '结构可发现',
    L2: '可引荐',
  };

  // --- fetch helper: always send the session cookie -------------------
  function cnFetch(path, opts) {
    opts = opts || {};
    opts.credentials = 'same-origin';
    opts.headers = Object.assign(
      { 'Content-Type': 'application/json' }, opts.headers || {}
    );
    return fetch('/api' + path, opts);
  }

  function flash(text, kind) {
    var box = $('cn-msg');
    if (!box) return;
    box.textContent = text;
    box.className = 'cn-msg cn-msg--' + (kind === 'ok' ? 'ok' : 'err');
    show(box);
    if (kind === 'ok') {
      setTimeout(function () { hide(box); }, 4000);
    }
  }

  // --- login gate -----------------------------------------------------

  function bindLogin() {
    var form = $('cn-login-form');
    if (!form) return;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var email = ($('cn-login-email').value || '').trim();
      if (!email) return;
      cnFetch('/auth/request-link', {
        method: 'POST',
        body: JSON.stringify({ email: email }),
      }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      }).then(function (res) {
        if (!res.ok) {
          flash(res.d.error || '发送失败，请稍后再试', 'err');
          return;
        }
        flash('登录链接已发送，请查收邮箱。点开链接后回到本页即可。', 'ok');
        // Dev mode: backend echoes the link so local testing needs no email.
        if (res.d.dev_link) {
          var box = $('cn-devlink');
          box.innerHTML = '开发模式登录链接：<a href="' +
            esc(res.d.dev_link) + '">' + esc(res.d.dev_link) + '</a>';
          show(box);
        }
      }).catch(function () {
        flash('网络错误，请稍后再试', 'err');
      });
    });
  }

  // --- fingerprint rendering ------------------------------------------

  function visBadge(level) {
    var lv = VIS_LABEL[level] ? level : 'L0';
    return '<span class="cn-vis cn-vis--' + lv + '">' +
      esc(VIS_LABEL[lv]) + '（' + lv + '）</span>';
  }

  function fingerprintCard(fp) {
    var card = document.createElement('div');
    card.className = 'cn-card';
    card.dataset.fid = fp.id;

    var meta = [];
    if (fp.domain) meta.push('领域：' + esc(fp.domain));
    if (fp.universality_class) meta.push('普适类：' + esc(fp.universality_class));
    if (!fp.has_embedding) meta.push('（结构向量待生成，暂不可匹配）');

    var opts = ['L0', 'L1', 'L2'].map(function (lv) {
      return '<option value="' + lv + '"' +
        (lv === fp.visibility_level ? ' selected' : '') + '>' +
        VIS_LABEL[lv] + '（' + lv + '）</option>';
    }).join('');

    card.innerHTML =
      '<div class="cn-card__head">' +
        '<div>' +
          '<p class="cn-card__summary">' + esc(fp.problem_summary) + '</p>' +
          (meta.length
            ? '<p class="cn-card__meta">' + meta.join(' · ') + '</p>' : '') +
        '</div>' +
        visBadge(fp.visibility_level) +
      '</div>' +
      '<div class="cn-card__actions">' +
        '<label style="font-size:12.5px;color:#9a958c;">可见性</label>' +
        '<select class="cn-vis-pick" data-act="vis">' + opts + '</select>' +
        '<button type="button" class="cn-btn" data-act="neighbors">看结构邻居</button>' +
        '<button type="button" class="cn-btn cn-btn--danger" data-act="delete">删除</button>' +
      '</div>' +
      '<div class="cn-neighbors cn-hidden" data-role="neighbors"></div>';

    return card;
  }

  function renderNeighbors(container, body) {
    container.innerHTML = '';
    var count = body.neighbor_count || 0;
    var head = document.createElement('div');
    head.className = 'cn-neighbor-count';
    if (count === 0) {
      head.textContent = '暂时还没有人在研究结构指纹相近的问题——' +
        '把更多问题登记成可发现的指纹，结构邻居会随用户增长出现。';
      head.style.color = '#9a958c';
      head.style.fontWeight = '400';
      container.appendChild(head);
      show(container);
      return;
    }
    head.textContent = '有 ' + count + ' 人正在研究结构指纹相近、但领域不同的问题';
    container.appendChild(head);

    (body.neighbors || []).forEach(function (n) {
      var el = document.createElement('div');
      el.className = 'cn-neighbor';
      var simPct = Math.round((n.structural_similarity || 0) * 100);
      var metaBits = [];
      if (n.domain) metaBits.push('领域：' + esc(n.domain));
      metaBits.push('结构相似度 ' + simPct + '%');
      if (n.same_universality_class) metaBits.push('内部候选分类标签相同（非机制证明）');
      el.innerHTML =
        '<div class="cn-neighbor__summary">' + esc(n.problem_summary) + '</div>' +
        '<div class="cn-neighbor__meta">' + metaBits.join(' · ') + '</div>';
      container.appendChild(el);
    });
    show(container);
  }

  // --- fingerprint actions --------------------------------------------

  function bindCardActions(card) {
    var fid = card.dataset.fid;

    card.querySelector('[data-act="vis"]').addEventListener('change', function (e) {
      var level = e.target.value;
      cnFetch('/connections/fingerprints/' + encodeURIComponent(fid), {
        method: 'PATCH',
        body: JSON.stringify({ visibility_level: level }),
      }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      }).then(function (res) {
        if (!res.ok) { flash(res.d.error || '修改失败', 'err'); return; }
        flash('可见性已更新为「' + VIS_LABEL[level] + '」', 'ok');
        loadFingerprints();
      }).catch(function () { flash('网络错误', 'err'); });
    });

    card.querySelector('[data-act="delete"]').addEventListener('click', function () {
      if (!window.confirm('确定删除这个指纹？此操作不可撤销。')) return;
      cnFetch('/connections/fingerprints/' + encodeURIComponent(fid), {
        method: 'DELETE',
      }).then(function (r) {
        if (!r.ok) { flash('删除失败', 'err'); return; }
        flash('指纹已删除', 'ok');
        loadFingerprints();
      }).catch(function () { flash('网络错误', 'err'); });
    });

    card.querySelector('[data-act="neighbors"]').addEventListener('click', function (e) {
      var btn = e.target;
      var box = card.querySelector('[data-role="neighbors"]');
      btn.disabled = true;
      btn.textContent = '计算中…';
      cnFetch('/connections/fingerprints/' + encodeURIComponent(fid) + '/neighbors')
        .then(function (r) {
          return r.json().then(function (d) { return { ok: r.ok, d: d }; });
        }).then(function (res) {
          btn.disabled = false;
          btn.textContent = '看结构邻居';
          if (!res.ok) { flash(res.d.error || '查询失败', 'err'); return; }
          renderNeighbors(box, res.d);
        }).catch(function () {
          btn.disabled = false;
          btn.textContent = '看结构邻居';
          flash('网络错误', 'err');
        });
    });
  }

  // --- load + render my fingerprints ----------------------------------

  function loadFingerprints() {
    cnFetch('/connections/fingerprints').then(function (r) {
      if (r.status === 401) { showGate(); return null; }
      return r.json();
    }).then(function (d) {
      if (!d) return;
      hide($('cn-loading'));
      var list = $('cn-list');
      list.innerHTML = '';
      var fps = d.fingerprints || [];
      if (fps.length === 0) {
        show($('cn-empty'));
        return;
      }
      hide($('cn-empty'));
      fps.forEach(function (fp) {
        var card = fingerprintCard(fp);
        list.appendChild(card);
        bindCardActions(card);
      });
    }).catch(function () {
      hide($('cn-loading'));
      flash('加载指纹失败，请刷新重试', 'err');
    });
  }

  function bindCreate() {
    var form = $('cn-create-form');
    if (!form) return;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var summary = ($('cn-summary').value || '').trim();
      if (summary.length < 4) {
        flash('问题描述太短了，再多写几个字', 'err');
        return;
      }
      var payload = { problem_summary: summary };
      var domain = ($('cn-domain').value || '').trim();
      var uclass = ($('cn-uclass').value || '').trim();
      if (domain) payload.domain = domain;
      if (uclass) payload.universality_class = uclass;

      cnFetch('/connections/fingerprints', {
        method: 'POST',
        body: JSON.stringify(payload),
      }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      }).then(function (res) {
        if (!res.ok) {
          flash(res.d.error || '登记失败', 'err');
          return;
        }
        flash('指纹已登记（默认私密）。可在下方打开「结构可发现」。', 'ok');
        form.reset();
        loadFingerprints();
      }).catch(function () { flash('网络错误', 'err'); });
    });
  }

  // --- session check + view switching ---------------------------------

  function showGate() {
    hide($('cn-app'));
    show($('cn-gate'));
  }

  function showApp() {
    hide($('cn-gate'));
    show($('cn-app'));
    loadFingerprints();
  }

  function init() {
    bindLogin();
    bindCreate();
    // Probe session: /auth/me → 200 logged in, 401 not.
    cnFetch('/auth/me').then(function (r) {
      if (r.ok) { showApp(); } else { showGate(); }
    }).catch(function () {
      // Backend unreachable — show the gate, login flow surfaces the error.
      showGate();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
