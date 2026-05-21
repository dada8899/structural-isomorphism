/**
 * Structural — Structural stress-test page (Session ***REMOVED***18, feature E).
 *
 * Submits one analogy / strategic claim to POST /api/stress-test and renders
 * the falsification result: source vs target, per-correspondence stress
 * results, the weakest link, and a PASS / FAIL / CONDITIONAL verdict.
 */
(function () {
  'use strict';

  var VERDICT_LABEL = { PASS: '成立', FAIL: '不成立', CONDITIONAL: '有条件成立' };

  function esc(s) {
    return (window.escapeHtml ? window.escapeHtml(s) : String(s == null ? '' : s));
  }

  function $(id) { return document.getElementById(id); }

  function trackPlausible(event, props) {
    try {
      if (typeof window.plausible === 'function') {
        window.plausible(event, props ? { props: props } : undefined);
      }
    } catch (e) { /* telemetry must not throw */ }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var claimEl = $('stress-claim');
    var submitEl = $('stress-submit');
    var errorEl = $('stress-error');
    var loadingEl = $('stress-loading');
    var resultEl = $('stress-result');

    if (!claimEl || !submitEl) return;

    // Example chips fill the textarea (do not auto-submit — let user read).
    var examples = $('stress-examples');
    if (examples) {
      examples.addEventListener('click', function (e) {
        var btn = e.target.closest('.stress-chip');
        if (!btn) return;
        claimEl.value = btn.getAttribute('data-claim') || '';
        claimEl.focus();
      });
    }

    function showError(msg) {
      errorEl.textContent = msg;
      errorEl.hidden = false;
    }
    function clearError() {
      errorEl.hidden = true;
      errorEl.textContent = '';
    }

    function setLoading(on) {
      loadingEl.hidden = !on;
      submitEl.disabled = on;
      claimEl.disabled = on;
    }

    function renderResult(data) {
      // --- verdict ---
      var verdict = (data.verdict || 'CONDITIONAL').toUpperCase();
      var vKey = verdict.toLowerCase();
      var verdictWrap = $('stress-verdict');
      var verdictBadge = $('stress-verdict-badge');
      verdictWrap.className = 'stress-verdict stress-verdict--' + vKey;
      verdictBadge.className = 'stress-verdict__badge stress-verdict__badge--' + vKey;
      verdictBadge.textContent = verdict + ' · ' + (VERDICT_LABEL[verdict] || '');
      $('stress-verdict-reason').textContent = data.verdict_reason || '';

      // --- source vs target ---
      $('stress-source').textContent = data.source || '（未识别）';
      $('stress-target').textContent = data.target || '（未识别）';

      // --- correspondences ---
      var list = $('stress-corr-list');
      list.innerHTML = '';
      var corrs = Array.isArray(data.structural_correspondences)
        ? data.structural_correspondences : [];
      if (corrs.length === 0) {
        var li = document.createElement('li');
        li.className = 'stress-corr stress-corr--breaks';
        li.innerHTML = '<p class="stress-corr__stress" style="padding-left:0">'
          + '模型未能拆出可压测的结构对应关系。</p>';
        list.appendChild(li);
      } else {
        corrs.forEach(function (c) {
          var holds = c && c.holds === true;
          var li = document.createElement('li');
          li.className = 'stress-corr ' + (holds ? 'stress-corr--holds' : 'stress-corr--breaks');
          li.innerHTML =
            '<div class="stress-corr__head">'
            + '<span class="stress-corr__mark">' + (holds ? '✓' : '✕') + '</span>'
            + '<span class="stress-corr__claim">' + esc(c.claim) + '</span>'
            + '</div>'
            + '<p class="stress-corr__stress">' + esc(c.stress_result) + '</p>';
          list.appendChild(li);
        });
      }

      // --- weakest link ---
      $('stress-weakest-text').textContent = data.weakest_link || '（未指出）';

      // --- precedent (real KB phenomenon backing the weakest link) ---
      // Degrades gracefully: when precedent is null the block stays hidden
      // and the verdict still reads fine on its own.
      var precWrap = $('stress-precedent');
      var prec = data.precedent;
      if (prec && prec.phenomenon_id && prec.failure_precedent) {
        $('stress-precedent-domain').textContent = prec.domain || '';
        $('stress-precedent-name').textContent = prec.phenomenon_name || '';
        $('stress-precedent-link').href =
          '/phenomenon/' + encodeURIComponent(prec.phenomenon_id);
        $('stress-precedent-failure').textContent = prec.failure_precedent;
        precWrap.hidden = false;
      } else {
        precWrap.hidden = true;
      }

      resultEl.hidden = false;
    }

    function submit() {
      clearError();
      var claim = (claimEl.value || '').trim();
      if (claim.length < 4) {
        showError('请输入一个完整的类比或判断（至少 4 个字）。');
        return;
      }
      if (claim.length > 600) {
        showError('内容过长（上限 600 字），请精简。');
        return;
      }

      resultEl.hidden = true;
      setLoading(true);
      trackPlausible('StressTest Submit');

      apiFetch('/stress-test', {
        method: 'POST',
        body: JSON.stringify({ claim: claim }),
      })
        .then(function (data) {
          setLoading(false);
          renderResult(data);
          trackPlausible('StressTest Result', { verdict: data.verdict || 'NA' });
        })
        .catch(function (err) {
          setLoading(false);
          var msg = String(err && err.message || '');
          // apiFetch throws "API <status>: <text>" — surface a clean message.
          if (msg.indexOf('API 503') !== -1) {
            showError('压力测试服务当前不可用（LLM 无响应）。请稍后重试。');
          } else if (msg.indexOf('API 422') !== -1) {
            showError('输入无法处理，请检查你的类比是否完整。');
          } else if (msg.indexOf('API 429') !== -1) {
            showError('请求过于频繁，请稍后再试。');
          } else {
            showError('压力测试失败，请稍后重试。');
          }
          trackPlausible('StressTest Error');
        });
    }

    submitEl.addEventListener('click', submit);
    // Cmd/Ctrl + Enter submits from the textarea.
    claimEl.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        submit();
      }
    });
  });
})();
