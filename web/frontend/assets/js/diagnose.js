/**
 * Structural — 结构诊断 (feature F, Session ***REMOVED***18).
 *
 * Vanilla JS, no dependencies. Posts a free-text situation description to
 * POST /api/diagnose and renders the structural-diagnosis report. Handles
 * loading / error / empty states. The backend whitelists every structural
 * state, so this file only renders what it is given.
 */
(function () {
  'use strict';

  var MAX_LEN = 1500;

  // --- element refs -------------------------------------------------------
  var $ = function (id) { return document.getElementById(id); };

  var inputSection = $('diagnose-input-section');
  var loadingEl = $('diagnose-loading');
  var errorEl = $('diagnose-error');
  var reportEl = $('diagnose-report');

  var form = $('diagnose-form');
  var textarea = $('diagnose-textarea');
  var countEl = $('diagnose-count');
  var submitBtn = $('diagnose-submit');
  var timerEl = $('diagnose-timer');

  var errorTitle = $('diagnose-error-title');
  var errorMsg = $('diagnose-error-msg');
  var retryBtn = $('diagnose-retry');
  var againBtn = $('diagnose-again');

  var _timerHandle = null;

  // --- view-state switching ----------------------------------------------
  function show(el) {
    [inputSection, loadingEl, errorEl, reportEl].forEach(function (node) {
      if (!node) return;
      node.hidden = node !== el;
    });
  }

  function showInput() {
    stopTimer();
    show(inputSection);
  }

  function startTimer() {
    var t0 = Date.now();
    if (timerEl) timerEl.textContent = '已等待 0s';
    _timerHandle = window.setInterval(function () {
      var secs = Math.floor((Date.now() - t0) / 1000);
      if (timerEl) timerEl.textContent = '已等待 ' + secs + 's';
    }, 1000);
  }

  function stopTimer() {
    if (_timerHandle) {
      window.clearInterval(_timerHandle);
      _timerHandle = null;
    }
  }

  // --- char counter -------------------------------------------------------
  function updateCount() {
    var len = textarea.value.length;
    countEl.textContent = len + ' / ' + MAX_LEN;
    countEl.classList.toggle('is-over', len >= MAX_LEN);
  }

  // --- rendering ----------------------------------------------------------
  function renderList(ulEl, items) {
    ulEl.textContent = '';
    (items || []).forEach(function (text) {
      var li = document.createElement('li');
      li.textContent = text;
      ulEl.appendChild(li);
    });
  }

  // --- reference case -----------------------------------------------------
  // Render the same-structure real KB phenomenon. Two shapes:
  //   - a real KB hit (has id) → deep-linkable to /phenomenon/{id};
  //   - a class-hub fallback (id is empty) → shown as text, no link.
  // Absent / null reference → the whole block stays hidden.
  function renderReference(ref) {
    var blockEl = $('diagnose-reference');
    if (!blockEl) return;

    if (!ref || !ref.name) {
      blockEl.hidden = true;
      return;
    }

    var domainEl = $('diagnose-reference-domain');
    var nameEl = $('diagnose-reference-name');
    var linkEl = $('diagnose-reference-link');
    var arrowEl = $('diagnose-reference-arrow');
    var noteEl = $('diagnose-reference-note');

    if (ref.domain) {
      domainEl.textContent = ref.domain;
      domainEl.hidden = false;
    } else {
      domainEl.hidden = true;
    }
    nameEl.textContent = ref.name;

    // Deep link only when the case carries a real KB id.
    if (ref.id) {
      linkEl.setAttribute('href', '/phenomenon/' + encodeURIComponent(ref.id));
      linkEl.classList.add('is-linked');
      if (arrowEl) arrowEl.hidden = false;
    } else {
      linkEl.removeAttribute('href');
      linkEl.classList.remove('is-linked');
      if (arrowEl) arrowEl.hidden = true;
    }

    // Optional one-line "how that case evolved" note.
    if (ref.note) {
      noteEl.textContent = ref.note;
      noteEl.hidden = false;
    } else {
      noteEl.hidden = true;
    }

    blockEl.hidden = false;
  }

  function renderReport(data) {
    var primary = data.primary_state || {};

    $('diagnose-state-name').textContent = primary.name || '（未识别）';
    $('diagnose-state-def').textContent = primary.definition || '';

    var signalEl = $('diagnose-state-signal');
    if (primary.typical_signal) {
      signalEl.textContent = '典型信号：' + primary.typical_signal;
      signalEl.hidden = false;
    } else {
      signalEl.hidden = true;
    }

    // Confidence — render as a percentage badge.
    var confEl = $('diagnose-confidence');
    if (typeof primary.confidence === 'number') {
      var pct = Math.round(primary.confidence * 100);
      confEl.textContent = '判定把握 ' + pct + '%';
      confEl.hidden = false;
    } else {
      confEl.hidden = true;
    }

    $('diagnose-reasoning').textContent = data.reasoning || '';
    $('diagnose-evolution').textContent = data.evolution || '';

    // Same-structure real reference case (KB-anchored).
    renderReference(data.reference_case);

    // Signals — hide the whole block if empty.
    var signals = data.signals_to_watch || [];
    $('diagnose-signals-block').hidden = signals.length === 0;
    renderList($('diagnose-signals'), signals);

    // Recommendations — hide the whole block if empty.
    var recos = data.recommendations || [];
    $('diagnose-reco-block').hidden = recos.length === 0;
    renderList($('diagnose-recommendations'), recos);

    // Secondary state — optional.
    var secEl = $('diagnose-secondary');
    var secondary = data.secondary_state;
    if (secondary && secondary.name) {
      $('diagnose-secondary-name').textContent = secondary.name;
      $('diagnose-secondary-def').textContent = secondary.definition || '';
      secEl.hidden = false;
    } else {
      secEl.hidden = true;
    }

    show(reportEl);
    stopTimer();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function showError(message) {
    stopTimer();
    errorTitle.textContent = '诊断没能完成';
    errorMsg.textContent = message || '请稍后重试。';
    show(errorEl);
  }

  // --- submission ---------------------------------------------------------
  function runDiagnosis(situation) {
    show(loadingEl);
    startTimer();

    fetch('/api/diagnose', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ situation: situation }),
    })
      .then(function (resp) {
        return resp.json().then(function (body) {
          return { ok: resp.ok, status: resp.status, body: body };
        });
      })
      .then(function (res) {
        if (res.ok) {
          renderReport(res.body);
          return;
        }
        // Surface the backend's own message when present.
        var detail = (res.body && res.body.detail) || '';
        if (res.status === 503) {
          showError(detail || '结构诊断服务当前不可用，请稍后重试。');
        } else if (res.status === 422) {
          showError(detail || '描述不符合要求，请调整后重试。');
        } else if (res.status === 429) {
          showError('请求过于频繁，请稍后再试。');
        } else {
          showError(detail || '诊断失败（错误 ' + res.status + '），请稍后重试。');
        }
      })
      .catch(function () {
        showError('网络连接出现问题，请检查后重试。');
      });
  }

  function handleSubmit(e) {
    e.preventDefault();
    var situation = textarea.value.trim();
    if (situation.length < 12) {
      // Empty / too-short — keep user on the input view with inline hint.
      textarea.focus();
      textarea.classList.add('is-invalid');
      countEl.textContent = '描述太短，请把处境说得更完整一些';
      countEl.classList.add('is-over');
      return;
    }
    runDiagnosis(situation);
  }

  // --- wiring -------------------------------------------------------------
  function init() {
    if (!form) return;

    updateCount();
    textarea.addEventListener('input', function () {
      textarea.classList.remove('is-invalid');
      updateCount();
    });

    form.addEventListener('submit', handleSubmit);

    // Quick-example buttons.
    document.querySelectorAll('.diagnose-example').forEach(function (btn) {
      btn.addEventListener('click', function () {
        textarea.value = btn.getAttribute('data-example') || '';
        textarea.classList.remove('is-invalid');
        updateCount();
        textarea.focus();
      });
    });

    if (retryBtn) retryBtn.addEventListener('click', showInput);
    if (againBtn) againBtn.addEventListener('click', showInput);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
