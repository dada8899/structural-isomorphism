/** Structural stress-test: candidate-only red-team screen. */
(function () {
  'use strict';

  var contracts = window.SecondaryToolContracts;
  var OUTCOME_LABEL = {
    not_broken_in_screen: '本轮未找到致命断点',
    breaks_in_screen: '本轮发现关键断点',
    condition_dependent: '取决于前提条件'
  };
  var OUTCOME_CLASS = {
    not_broken_in_screen: 'not-broken',
    breaks_in_screen: 'breaks',
    condition_dependent: 'conditional'
  };
  var activeController = null;
  var activeRequestId = null;

  function $(id) { return document.getElementById(id); }
  function canonical(value) {
    return String(value || '').normalize('NFKC').replace(/\s+/g, ' ').trim();
  }
  function esc(value) {
    var node = document.createElement('div');
    node.textContent = value == null ? '' : String(value);
    return node.innerHTML;
  }
  function current(requestId) { return requestId && requestId === activeRequestId; }
  function abortActive() {
    if (activeController) activeController.abort();
    activeController = null;
    activeRequestId = null;
  }
  function trackPlausible(event, props) {
    try {
      if (typeof window.plausible === 'function') {
        window.plausible(event, props ? { props: props } : undefined);
      }
    } catch (error) { /* telemetry must not affect the journey */ }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var claimEl = $('stress-claim');
    var submitEl = $('stress-submit');
    var errorEl = $('stress-error');
    var loadingEl = $('stress-loading');
    var resultEl = $('stress-result');
    if (!claimEl || !submitEl || !contracts) return;

    var examples = $('stress-examples');
    if (examples) {
      examples.addEventListener('click', function (event) {
        var button = event.target.closest('.stress-chip');
        if (!button) return;
        claimEl.value = button.getAttribute('data-claim') || '';
        claimEl.focus();
      });
    }

    function showError(message) {
      errorEl.textContent = message;
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

    function renderReference(reference) {
      var wrap = $('stress-precedent');
      if (!reference) {
        wrap.hidden = true;
        return;
      }
      $('stress-precedent-domain').textContent = reference.domain || '领域未标注';
      $('stress-precedent-name').textContent = reference.name;
      $('stress-precedent-link').href = '/phenomenon/' + encodeURIComponent(reference.id);
      $('stress-precedent-failure').textContent = reference.candidate_note ||
        '这是内部知识库的检索候选。请核查变量定义、边界条件和失效触发是否一致。';
      wrap.hidden = false;
    }

    function renderResult(data) {
      var key = data.screening_outcome;
      var classKey = OUTCOME_CLASS[key];
      var verdictWrap = $('stress-verdict');
      var verdictBadge = $('stress-verdict-badge');
      verdictWrap.className = 'stress-verdict stress-verdict--' + classKey;
      verdictBadge.className = 'stress-verdict__badge stress-verdict__badge--' + classKey;
      verdictBadge.textContent = OUTCOME_LABEL[key] + ' · 内部模型筛查';
      $('stress-verdict-reason').textContent = data.rationale;
      $('stress-source').textContent = data.source;
      $('stress-target').textContent = data.target;

      var list = $('stress-corr-list');
      list.textContent = '';
      data.structural_correspondences.forEach(function (item) {
        var notBroken = item.screening_outcome === 'not_broken';
        var row = document.createElement('li');
        row.className = 'stress-corr ' + (notBroken ? 'stress-corr--not-broken' : 'stress-corr--breaks');
        row.innerHTML = '<div class="stress-corr__head">' +
          '<span class="stress-corr__mark">' + (notBroken ? '△' : '×') + '</span>' +
          '<span class="stress-corr__claim">' + esc(item.claim) + '</span></div>' +
          '<p class="stress-corr__stress">' + esc(item.stress_result) + '</p>';
        list.appendChild(row);
      });
      $('stress-weakest-text').textContent = data.weakest_link;
      renderReference(data.candidate_reference);
      resultEl.hidden = false;
      resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    async function submit() {
      clearError();
      var claim = canonical(claimEl.value);
      if (claim.length < 4) {
        showError('请输入一个完整的类比或判断（至少 4 个字）。');
        return;
      }
      if (claim.length > 600) {
        showError('内容过长（上限 600 字），请精简。');
        return;
      }
      abortActive();
      var requestId = contracts.createRequestId('stress');
      var controller = new AbortController();
      activeRequestId = requestId;
      activeController = controller;
      resultEl.hidden = true;
      setLoading(true);
      trackPlausible('StressTest Submit');

      try {
        var response = await fetch('/api/stress-test', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ claim: claim, client_request_id: requestId }),
          signal: controller.signal
        });
        var body = null;
        try { body = await response.json(); } catch (error) { body = null; }
        if (!current(requestId)) return;
        if (!response.ok) {
          if (response.status === 422) throw new Error('scope');
          if (response.status === 429) throw new Error('rate');
          if (response.status === 503) throw new Error('unavailable');
          throw new Error('request');
        }
        var validated = contracts.validateStressPayload(body, requestId, claim);
        if (!validated) throw new Error('contract');
        renderResult(validated);
        trackPlausible('StressTest Result', { outcome: validated.screening_outcome });
      } catch (error) {
        if (!current(requestId) || (error && error.name === 'AbortError')) return;
        var messages = {
          scope: '这里只测试完整的结构类比。请补充要比较的对象和机制。',
          rate: '请求过于频繁，请稍后再试。',
          unavailable: '压力测试暂时不可用，请稍后重试。',
          contract: '结果未通过完整性校验，未展示任何模型内容。请重试。'
        };
        showError(messages[error.message] || '压力测试失败，请检查网络后重试。');
        trackPlausible('StressTest Error');
      } finally {
        if (current(requestId)) {
          setLoading(false);
          activeController = null;
        }
      }
    }

    submitEl.addEventListener('click', submit);
    claimEl.addEventListener('keydown', function (event) {
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
        event.preventDefault();
        submit();
      }
    });
    window.addEventListener('pagehide', abortActive);
  });
}());
