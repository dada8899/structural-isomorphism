/**
 * Structural — Reasoning timeline (shared UX component).
 *
 * Renders the backend pipeline as a live, step-by-step timeline that lights
 * up as work happens, instead of a single opaque spinner. Built to fix the
 * "圈在转、不知道后面发生了什么、没耐心等" problem: the moment a question is
 * submitted the whole pipeline is painted (pending steps greyed out), and
 * each step flips to active → done with its own elapsed timer + a short
 * detail line ("命中 5 个现象", "正在生成答案…").
 *
 * Self-contained, no module imports, no deps — attaches a single factory to
 * `window` per project convention (mirrors utils/buildAnalyzeUrl.js).
 *
 *   var tl = window.createReasoningTimeline(containerEl, { lang: 'zh' });
 *   tl.setStages([{ key: 'retrieve', label: '检索知识库' }, ...]);
 *   tl.setActive('retrieve');
 *   tl.setDone('retrieve', '命中 5 个现象');
 *   tl.finish();                 // collapse to a compact "用时 4.2s · 5 步" row
 *
 * Status model per step: pending → active → done | skipped | error.
 * All transitions are idempotent and monotonic — `setDone` on an already
 * finished step is a no-op, and a step never moves backwards out of a
 * terminal state. This lets a caller drive the timeline from EITHER the new
 * `stage` SSE events OR a best-effort mapping of legacy events without
 * double-driving or flicker.
 */
(function () {
  'use strict';

  var TERMINAL = { done: 1, skipped: 1, error: 1 };

  function esc(s) {
    if (typeof window.escapeHtml === 'function') return window.escapeHtml(s);
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function now() {
    return (typeof performance !== 'undefined' && performance.now)
      ? performance.now() : Date.now();
  }

  function fmtSecs(ms) {
    if (ms == null) return '';
    var s = ms / 1000;
    return (s < 10 ? s.toFixed(1) : Math.round(s)) + 's';
  }

  // One shared ticker drives the live elapsed readout on every active step
  // across all timelines on the page, so we never leak per-instance intervals.
  var instances = [];
  var ticker = null;
  function startTicker() {
    if (ticker) return;
    ticker = setInterval(function () {
      var anyActive = false;
      for (var i = 0; i < instances.length; i++) {
        if (instances[i]._tick()) anyActive = true;
      }
      if (!anyActive) { clearInterval(ticker); ticker = null; }
    }, 100);
  }

  function createReasoningTimeline(container, opts) {
    opts = opts || {};
    var lang = (opts.lang || 'zh').slice(0, 2);
    var labels = lang === 'en'
      ? { thinking: 'Working…', done: 'Done', step: 'steps', took: 'took', detailsShow: 'details', detailsHide: 'hide' }
      : { thinking: '正在推进…', done: '完成', step: '步', took: '用时', detailsShow: '展开过程', detailsHide: '收起' };

    var root = document.createElement('div');
    root.className = 'rt';
    root.setAttribute('role', 'status');
    root.setAttribute('aria-live', 'polite');
    root.innerHTML =
      '<div class="rt__head" hidden>' +
        '<button type="button" class="rt__toggle" aria-expanded="false">' +
          '<svg class="rt__toggle-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>' +
          '<span class="rt__summary"></span>' +
        '</button>' +
      '</div>' +
      '<ol class="rt__steps"></ol>';

    if (container) container.appendChild(root);

    var stepsEl = root.querySelector('.rt__steps');
    var headEl = root.querySelector('.rt__head');
    var toggleEl = root.querySelector('.rt__toggle');
    var summaryEl = root.querySelector('.rt__summary');

    var steps = {};   // key -> { key, status, startedAt, durationMs, el, ... }
    var order = [];
    var t0 = now();
    var finished = false;

    toggleEl.addEventListener('click', function () {
      var collapsed = root.classList.toggle('rt--collapsed');
      toggleEl.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    });

    function stepHtml(key, label) {
      return (
        '<li class="rt-step rt-step--pending" data-key="' + esc(key) + '">' +
          '<span class="rt-step__marker" aria-hidden="true">' +
            '<span class="rt-step__spinner"></span>' +
            '<svg class="rt-step__check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 13l4 4L19 7"/></svg>' +
            '<svg class="rt-step__skip" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M6 12h12"/></svg>' +
            '<svg class="rt-step__err" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>' +
          '</span>' +
          '<span class="rt-step__body">' +
            '<span class="rt-step__label">' + esc(label) + '</span>' +
            '<span class="rt-step__detail"></span>' +
          '</span>' +
          '<span class="rt-step__time"></span>' +
        '</li>'
      );
    }

    function setStages(list) {
      if (!list || !list.length) return;
      stepsEl.innerHTML = list.map(function (s) {
        return stepHtml(s.key, s.label || s.key);
      }).join('');
      order = [];
      steps = {};
      list.forEach(function (s) {
        var el = stepsEl.querySelector('.rt-step[data-key="' + cssEsc(s.key) + '"]');
        steps[s.key] = { key: s.key, status: 'pending', startedAt: null, durationMs: null, el: el };
        order.push(s.key);
      });
    }

    function ensureStages(list) {
      if (!order.length) setStages(list);
    }

    function cssEsc(s) {
      if (window.CSS && CSS.escape) return CSS.escape(s);
      return String(s).replace(/["\\\]]/g, '\\$&');
    }

    function applyStatus(st, status, detail) {
      var el = st.el;
      if (!el) return;
      el.classList.remove('rt-step--pending', 'rt-step--active', 'rt-step--done', 'rt-step--skipped', 'rt-step--error');
      el.classList.add('rt-step--' + status);
      if (detail != null && detail !== '') {
        el.querySelector('.rt-step__detail').textContent = detail;
      }
    }

    function transition(key, status, detail) {
      var st = steps[key];
      if (!st) {
        // Unknown key arriving mid-stream — append it so nothing is lost.
        stepsEl.insertAdjacentHTML('beforeend', stepHtml(key, key));
        var el = stepsEl.querySelector('.rt-step[data-key="' + cssEsc(key) + '"]:last-child');
        st = steps[key] = { key: key, status: 'pending', startedAt: null, durationMs: null, el: el };
        order.push(key);
      }
      // Monotonic: never leave a terminal state.
      if (TERMINAL[st.status]) return;
      if (status === 'active') {
        if (st.status === 'active') { if (detail) applyStatus(st, 'active', detail); return; }
        st.status = 'active';
        st.startedAt = now();
        applyStatus(st, 'active', detail);
        startTicker();
        return;
      }
      // Terminal transition (done | skipped | error).
      if (st.startedAt == null) st.startedAt = now();
      st.durationMs = now() - st.startedAt;
      st.status = status;
      applyStatus(st, status, detail);
      var timeEl = st.el && st.el.querySelector('.rt-step__time');
      if (timeEl && status === 'done') timeEl.textContent = fmtSecs(st.durationMs);
    }

    function _tick() {
      var active = false;
      for (var i = 0; i < order.length; i++) {
        var st = steps[order[i]];
        if (st.status === 'active' && st.el) {
          active = true;
          var t = st.el.querySelector('.rt-step__time');
          if (t) t.textContent = fmtSecs(now() - st.startedAt);
        }
      }
      return active;
    }

    // Mark the in-flight step (or, failing that, the first un-started step)
    // as errored — used when the stream dies mid-pipeline so the timeline
    // shows a red stop at the exact failure point instead of a frozen spin.
    function failActive(detail) {
      var target = null;
      for (var i = 0; i < order.length; i++) {
        if (steps[order[i]].status === 'active') { target = order[i]; break; }
      }
      if (!target) {
        for (var j = 0; j < order.length; j++) {
          if (steps[order[j]].status === 'pending') { target = order[j]; break; }
        }
      }
      if (target) transition(target, 'error', detail);
    }

    function finish(opts2) {
      if (finished) return;
      finished = true;
      var errorMode = !!(opts2 && opts2.error);
      // A lingering `active` step on a clean finish was making real progress,
      // so close it as done. On error finish we touch nothing — failActive()
      // already painted the failure point, and pending steps stay pending
      // (honest: they never ran) rather than being falsely marked complete.
      if (!errorMode) {
        order.forEach(function (k) {
          if (steps[k].status === 'active') transition(k, 'done');
        });
      }
      var totalMs = now() - t0;
      var doneCount = order.filter(function (k) { return steps[k].status === 'done'; }).length;
      var summary = (opts2 && opts2.summary) ||
        (labels.took + ' ' + fmtSecs(totalMs) + ' · ' + doneCount + ' ' + labels.step);
      summaryEl.textContent = summary;
      headEl.hidden = false;
      // Collapse by default once finished — the answer is the focus now.
      if (!opts2 || opts2.collapse !== false) {
        root.classList.add('rt--collapsed');
        toggleEl.setAttribute('aria-expanded', 'false');
      }
      root.classList.add('rt--finished');
    }

    var api = {
      el: root,
      setStages: setStages,
      ensureStages: ensureStages,
      setActive: function (k, d) { transition(k, 'active', d); return api; },
      setDone: function (k, d) { transition(k, 'done', d); return api; },
      setSkipped: function (k, d) { transition(k, 'skipped', d); return api; },
      setError: function (k, d) { transition(k, 'error', d); return api; },
      failActive: failActive,
      setDetail: function (k, d) {
        var st = steps[k];
        if (st && st.el && d != null) st.el.querySelector('.rt-step__detail').textContent = d;
        return api;
      },
      isFinished: function () { return finished; },
      finish: finish,
      _tick: _tick,
    };

    instances.push(api);
    return api;
  }

  window.createReasoningTimeline = createReasoningTimeline;
})();
