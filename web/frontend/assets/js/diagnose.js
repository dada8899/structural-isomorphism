/** Structural diagnosis: source-bound candidate state, never a probability. */
(function () {
  'use strict';

  var contracts = window.SecondaryToolContracts;
  var MAX_LEN = 1500;
  var activeController = null;
  var activeRequestId = null;
  var timerHandle = null;
  function $(id) { return document.getElementById(id); }
  function canonical(value) {
    return String(value || '').normalize('NFKC').replace(/\s+/g, ' ').trim();
  }

  var inputSection = $('diagnose-input-section');
  var loadingEl = $('diagnose-loading');
  var errorEl = $('diagnose-error');
  var reportEl = $('diagnose-report');
  var form = $('diagnose-form');
  var textarea = $('diagnose-textarea');
  var countEl = $('diagnose-count');
  var timerEl = $('diagnose-timer');
  var errorTitle = $('diagnose-error-title');
  var errorMsg = $('diagnose-error-msg');
  var retryBtn = $('diagnose-retry');
  var againBtn = $('diagnose-again');

  function current(requestId) { return requestId && requestId === activeRequestId; }
  function abortActive() {
    if (activeController) activeController.abort();
    activeController = null;
    activeRequestId = null;
  }
  function show(section) {
    [inputSection, loadingEl, errorEl, reportEl].forEach(function (node) {
      if (node) node.hidden = node !== section;
    });
  }
  function stopTimer() {
    if (timerHandle) window.clearInterval(timerHandle);
    timerHandle = null;
  }
  function startTimer() {
    stopTimer();
    var started = Date.now();
    if (timerEl) timerEl.textContent = '已等待 0s';
    timerHandle = window.setInterval(function () {
      if (timerEl) timerEl.textContent = '已等待 ' + Math.floor((Date.now() - started) / 1000) + 's';
    }, 1000);
  }
  function showInput() {
    abortActive();
    stopTimer();
    show(inputSection);
    if (textarea) textarea.focus();
  }
  function showError(message) {
    stopTimer();
    errorTitle.textContent = '诊断没能完成';
    errorMsg.textContent = message || '请稍后重试。';
    show(errorEl);
  }
  function updateCount() {
    var length = textarea.value.length;
    countEl.textContent = length + ' / ' + MAX_LEN;
    countEl.classList.toggle('is-over', length >= MAX_LEN);
  }
  function renderList(target, items) {
    target.textContent = '';
    items.forEach(function (item) {
      var row = document.createElement('li');
      row.textContent = item;
      target.appendChild(row);
    });
  }
  function renderReference(reference) {
    var block = $('diagnose-reference');
    if (!reference) {
      block.hidden = true;
      return;
    }
    var domain = $('diagnose-reference-domain');
    domain.textContent = reference.domain || '领域未标注';
    domain.hidden = false;
    $('diagnose-reference-name').textContent = reference.name;
    var link = $('diagnose-reference-link');
    link.href = '/phenomenon/' + encodeURIComponent(reference.id);
    link.classList.add('is-linked');
    $('diagnose-reference-arrow').hidden = false;
    var note = $('diagnose-reference-note');
    note.textContent = reference.candidate_note ||
      '这是内部知识库的检索候选；需要核查状态变量、时间尺度和干预边界。';
    note.hidden = false;
    block.hidden = false;
  }
  function renderReport(data) {
    var primary = data.primary_state;
    $('diagnose-state-name').textContent = primary.name;
    $('diagnose-state-def').textContent = primary.definition;
    $('diagnose-state-signal').textContent = '典型模式：' + primary.typical_signal;
    $('diagnose-state-signal').hidden = false;
    var badge = $('diagnose-status');
    badge.textContent = '模型生成候选 · 待现实数据核查';
    badge.hidden = false;
    $('diagnose-reasoning').textContent = data.reasoning;
    $('diagnose-evolution').textContent = data.evolution;
    renderReference(data.candidate_reference);
    $('diagnose-signals-block').hidden = data.signals_to_watch.length === 0;
    renderList($('diagnose-signals'), data.signals_to_watch);
    $('diagnose-reco-block').hidden = data.recommendations.length === 0;
    renderList($('diagnose-recommendations'), data.recommendations);
    var secondary = data.secondary_state;
    $('diagnose-secondary').hidden = !secondary;
    if (secondary) {
      $('diagnose-secondary-name').textContent = secondary.name;
      $('diagnose-secondary-def').textContent = secondary.definition;
    }
    stopTimer();
    show(reportEl);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function runDiagnosis(situation) {
    abortActive();
    var requestId = contracts.createRequestId('diagnose');
    var controller = new AbortController();
    activeRequestId = requestId;
    activeController = controller;
    show(loadingEl);
    startTimer();
    try {
      var response = await fetch('/api/diagnose', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ situation: situation, client_request_id: requestId }),
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
      var validated = contracts.validateDiagnosePayload(body, requestId, situation);
      if (!validated) throw new Error('contract');
      renderReport(validated);
    } catch (error) {
      if (!current(requestId) || (error && error.name === 'AbortError')) return;
      var messages = {
        scope: '这里只分析组织、团队或项目处境。请补充参与者、反馈和变化过程。',
        rate: '请求过于频繁，请稍后再试。',
        unavailable: '结构诊断暂时不可用，请稍后重试。',
        contract: '结果未通过完整性校验，未展示任何模型内容。请重试。'
      };
      showError(messages[error.message] || '网络连接出现问题，请检查后重试。');
    } finally {
      if (current(requestId)) activeController = null;
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    var situation = canonical(textarea.value);
    if (situation.length < 12) {
      textarea.focus();
      textarea.classList.add('is-invalid');
      countEl.textContent = '描述太短，请把处境说得更完整一些';
      countEl.classList.add('is-over');
      return;
    }
    runDiagnosis(situation);
  }

  function init() {
    if (!form || !contracts) return;
    updateCount();
    textarea.addEventListener('input', function () {
      textarea.classList.remove('is-invalid');
      updateCount();
    });
    form.addEventListener('submit', handleSubmit);
    document.querySelectorAll('.diagnose-example').forEach(function (button) {
      button.addEventListener('click', function () {
        textarea.value = button.getAttribute('data-example') || '';
        textarea.classList.remove('is-invalid');
        updateCount();
        textarea.focus();
      });
    });
    if (retryBtn) retryBtn.addEventListener('click', showInput);
    if (againBtn) againBtn.addEventListener('click', showInput);
    window.addEventListener('pagehide', abortActive);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
}());
