/** Method reverse-search: retrieval candidates, not applicability claims. */
(function () {
  'use strict';

  var contracts = window.SecondaryToolContracts;
  var form = document.getElementById('apply-form');
  var input = document.getElementById('apply-input');
  var countEl = document.getElementById('apply-count');
  var submitBtn = document.getElementById('apply-submit');
  var statusEl = document.getElementById('apply-status');
  var resultEl = document.getElementById('apply-result');
  var signatureEl = document.getElementById('apply-signature');
  var candidatesEl = document.getElementById('apply-matches');
  var candidateCountEl = document.getElementById('apply-matches-count');
  var examplesEl = document.getElementById('apply-examples');
  var MAX_LEN = 1000;
  var activeController = null;
  var activeRequestId = null;

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
  function showStatus(kind, html) {
    statusEl.hidden = false;
    statusEl.className = 'apply-status apply-status--' + kind;
    statusEl.innerHTML = html;
  }
  function hideStatus() {
    statusEl.hidden = true;
    statusEl.textContent = '';
  }
  function setBusy(on) {
    submitBtn.disabled = on;
    submitBtn.textContent = on ? '正在检索候选…' : '查找候选领域';
  }
  function updateCount() { countEl.textContent = input.value.length + ' / ' + MAX_LEN; }

  function renderSignature(data) {
    var keywords = data.keywords.map(function (keyword) {
      return '<span class="apply-kw">' + esc(keyword) + '</span>';
    }).join('');
    var origin = data.signature_origin === 'model_generated'
      ? '模型提炼的检索签名；尚未验证。'
      : '模型提炼不可用，暂以原始描述检索。';
    signatureEl.innerHTML = '<div class="apply-signature__label">候选检索签名</div>' +
      '<p class="apply-signature__text">' + esc(data.signature) + '</p>' +
      (keywords ? '<div class="apply-signature__kws">' + keywords + '</div>' : '') +
      '<p class="apply-signature__note">' + origin + '</p>';
  }

  function buildAnalysisUrl(method, candidate) {
    var query = '请检验「' + method + '」是否适用于「' + candidate.name + '」（' +
      candidate.domain + '），并列出机制差异、失败条件和需要补的证据。';
    return window.buildAnalyzeUrl({ id: candidate.id, q: query });
  }

  function renderCandidates(method, candidates) {
    if (!candidates.length) {
      candidateCountEl.textContent = '';
      candidatesEl.innerHTML = '<div class="apply-empty">没有找到可用候选。请说明方法依赖的' +
        '结构、输入输出和失效条件后再试。</div>';
      return;
    }
    candidateCountEl.textContent = candidates.length + ' 个检索候选 · 均未验证';
    candidatesEl.innerHTML = candidates.map(function (candidate) {
      var note = candidate.candidate_note ||
        (candidate.description || '知识库记录未提供摘要；请先查看原记录。').slice(0, 120);
      return '<article class="apply-card">' +
        '<div class="apply-card__top"><span class="apply-card__domain">' +
        esc(candidate.domain || '领域未标注') + '</span>' +
        '<span class="apply-card__rel" title="仅表示本次检索顺序">候选 #' +
        candidate.retrieval_rank + '</span></div>' +
        '<h3 class="apply-card__name">' + esc(candidate.name) + '</h3>' +
        '<p class="apply-card__note">' + esc(note) + '</p>' +
        '<a class="apply-card__link" href="' + esc(buildAnalysisUrl(method, candidate)) + '">' +
        '检验是否适用 →</a></article>';
    }).join('');
  }

  async function run(rawMethod) {
    var method = canonical(rawMethod);
    if (method.length < 4) {
      showStatus('error', '请至少输入 4 个字描述方法及其工作前提。');
      resultEl.hidden = true;
      return;
    }
    if (method.length > MAX_LEN) {
      showStatus('error', '方法描述过长，请精简到 ' + MAX_LEN + ' 字以内。');
      return;
    }
    abortActive();
    var requestId = contracts.createRequestId('apply');
    var controller = new AbortController();
    activeRequestId = requestId;
    activeController = controller;
    setBusy(true);
    showStatus('loading', '<span class="apply-spinner"></span>正在提炼检索签名并寻找候选…');
    resultEl.hidden = true;
    try {
      var response = await fetch('/api/method/apply', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ method: method, top_n: 8, client_request_id: requestId }),
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
      var validated = contracts.validateApplyPayload(body, requestId, method);
      if (!validated) throw new Error('contract');
      hideStatus();
      renderSignature(validated);
      renderCandidates(method, validated.candidates);
      resultEl.hidden = false;
      resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      if (!current(requestId) || (error && error.name === 'AbortError')) return;
      var messages = {
        scope: '这里只检索方法、算法或模型的候选领域。请补充方法机制和前提。',
        rate: '请求过于频繁，请稍后再试。',
        unavailable: '候选检索服务暂时不可用，请稍后再试。',
        contract: '结果未通过完整性校验，未展示任何模型内容。请重试。'
      };
      showStatus('error', messages[error.message] || '网络异常，请检查连接后重试。');
    } finally {
      if (current(requestId)) {
        setBusy(false);
        activeController = null;
      }
    }
  }

  if (!form || !contracts) return;
  input.addEventListener('input', updateCount);
  input.addEventListener('keydown', function (event) {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault();
      run(input.value);
    }
  });
  form.addEventListener('submit', function (event) {
    event.preventDefault();
    run(input.value);
  });
  examplesEl.addEventListener('click', function (event) {
    var chip = event.target.closest('.apply-chip');
    if (!chip) return;
    input.value = chip.getAttribute('data-method') || '';
    updateCount();
    run(input.value);
  });
  try {
    var prefill = new URLSearchParams(window.location.search).get('method');
    if (prefill) {
      input.value = prefill.slice(0, MAX_LEN);
      updateCount();
      run(input.value);
    }
  } catch (error) { /* malformed URL cannot break manual input */ }
  updateCount();
  window.addEventListener('pagehide', abortActive);
}());
