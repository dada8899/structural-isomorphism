/**
 * Structural — C2 structural lint page (Session ***REMOVED***18).
 *
 * Posts a document to /api/struct-lint and renders the extracted
 * structural claims with failure modes + risk levels. Pure vanilla JS.
 */
(function () {
  'use strict';

  var MAX_CHARS = 20000;

  // --- element refs ---
  var elInput = document.getElementById('lint-input');
  var elLoading = document.getElementById('lint-loading');
  var elError = document.getElementById('lint-error');
  var elResult = document.getElementById('lint-result');

  var elTextarea = document.getElementById('lint-textarea');
  var elCharCount = document.getElementById('lint-charcount');
  var elSubmit = document.getElementById('lint-submit');
  var elInputError = document.getElementById('lint-input-error');

  var elLoadingTimer = document.getElementById('lint-loading-timer');
  var elErrorMsg = document.getElementById('lint-error-msg');
  var elRetry = document.getElementById('lint-retry');

  var elSummaryText = document.getElementById('lint-summary-text');
  var elClaims = document.getElementById('lint-claims');
  var elResultCount = document.getElementById('lint-result-count');
  var elAgain = document.getElementById('lint-again');

  var _timerInterval = null;

  // --- view switching ---
  function showOnly(section) {
    [elInput, elLoading, elError, elResult].forEach(function (el) {
      if (el) el.hidden = el !== section;
    });
  }

  // --- escape untrusted text before injecting into innerHTML ---
  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  // --- char counter ---
  function updateCharCount() {
    var n = elTextarea.value.length;
    elCharCount.textContent = n + ' / ' + MAX_CHARS;
    elCharCount.classList.toggle('lint-charcount--over', n > MAX_CHARS);
  }

  // --- loading timer ---
  function startTimer() {
    var t0 = Date.now();
    elLoadingTimer.textContent = '已等待 0s';
    _timerInterval = setInterval(function () {
      var s = Math.floor((Date.now() - t0) / 1000);
      elLoadingTimer.textContent = '已等待 ' + s + 's';
    }, 1000);
  }
  function stopTimer() {
    if (_timerInterval) {
      clearInterval(_timerInterval);
      _timerInterval = null;
    }
  }

  // --- claim type / risk label maps ---
  var TYPE_LABEL = {
    assumption: '隐含假设',
    analogy: '跨域类比',
    causal_judgment: '因果判断'
  };
  var RISK_LABEL = { high: '高风险', medium: '中风险', low: '低风险' };

  // --- structural-isomorphism anchor block ---
  // Each claim may carry an `isomorph`: a real KB phenomenon whose
  // underlying structure matches the claim. This is the product's moat —
  // the failure mode above is grounded on this real cross-domain anchor,
  // not free-form LLM speculation. Null when the KB found nothing.
  function renderIsomorph(iso) {
    if (!iso || !iso.id) return '';
    var pct = Math.round((Number(iso.relevance) || 0) * 100);
    var meta = esc(iso.domain || '') +
      (pct ? ' · 结构相似度 ' + pct + '%' : '');
    var desc = iso.description
      ? '<div class="lint-iso__desc">' + esc(iso.description) + '</div>'
      : '';
    return '' +
      '<div class="lint-iso">' +
        '<div class="lint-iso__label">结构同构现象（来自知识库）</div>' +
        '<div class="lint-iso__body">' +
          '<a class="lint-iso__name" href="/phenomenon/' +
            encodeURIComponent(iso.id) + '">' + esc(iso.name) + '</a>' +
          '<span class="lint-iso__meta">' + meta + '</span>' +
          desc +
          '<a class="lint-iso__analyze" href="/analyze?id=' +
            encodeURIComponent(iso.id) + '">用这个现象做深度迁移分析 →</a>' +
        '</div>' +
      '</div>';
  }

  function renderClaim(claim) {
    var risk = RISK_LABEL[claim.risk_level] ? claim.risk_level : 'medium';
    var typeLabel = TYPE_LABEL[claim.claim_type] || claim.claim_type;

    var html = '' +
      '<div class="lint-claim lint-claim--' + risk + '">' +
        '<div class="lint-claim__head">' +
          '<span class="lint-tag lint-tag--type">' + esc(typeLabel) + '</span>' +
          '<span class="lint-tag lint-tag--risk-' + risk + '">' + RISK_LABEL[risk] + '</span>' +
        '</div>' +
        '<p class="lint-claim__quote">“' + esc(claim.quote) + '”</p>' +
        '<div class="lint-claim__row">' +
          '<div class="lint-claim__row-label">底层结构</div>' +
          '<div class="lint-claim__row-text">' + esc(claim.structure) + '</div>' +
        '</div>' +
        renderIsomorph(claim.isomorph) +
        '<div class="lint-claim__row">' +
          '<div class="lint-claim__row-label">失效模式</div>' +
          '<div class="lint-claim__row-text">' + esc(claim.failure_mode) + '</div>' +
        '</div>' +
        '<div class="lint-claim__row lint-claim__row--suggestion">' +
          '<div class="lint-claim__row-label">对冲建议</div>' +
          '<div class="lint-claim__row-text">' + esc(claim.suggestion) + '</div>' +
        '</div>' +
      '</div>';
    return html;
  }

  function renderResult(data) {
    elSummaryText.textContent = data.summary || '';
    var claims = Array.isArray(data.claims) ? data.claims : [];

    if (claims.length === 0) {
      elResultCount.textContent = '未发现结构性主张';
      elClaims.innerHTML =
        '<p class="lint-claim__row-text" style="padding:8px 4px;">' +
        '这份文档里没有抽取到明确的隐含假设、类比或因果判断。' +
        '</p>';
    } else {
      elResultCount.textContent = '共 ' + claims.length + ' 条';
      elClaims.innerHTML = claims.map(renderClaim).join('');
    }
    showOnly(elResult);
  }

  function showError(msg) {
    stopTimer();
    elErrorMsg.textContent = msg || '请稍后重试。';
    showOnly(elError);
  }

  // --- submit handler ---
  async function runLint() {
    var doc = elTextarea.value.trim();
    elInputError.hidden = true;

    if (!doc) {
      elInputError.textContent = '请先粘贴一段文档内容。';
      elInputError.hidden = false;
      return;
    }
    if (doc.length > MAX_CHARS) {
      elInputError.textContent = '文档过长，最多 ' + MAX_CHARS + ' 字符。';
      elInputError.hidden = false;
      return;
    }

    showOnly(elLoading);
    startTimer();

    try {
      var resp = await fetch('/api/struct-lint', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ document: doc })
      });

      var body = null;
      try { body = await resp.json(); } catch (e) { body = null; }

      if (!resp.ok) {
        var msg = (body && body.message) ||
          (resp.status === 503
            ? '结构 lint 服务暂时不可用，请稍后重试。'
            : '请求失败（' + resp.status + '）。');
        showError(msg);
        return;
      }

      stopTimer();
      renderResult(body || { summary: '', claims: [] });
    } catch (e) {
      showError('网络错误，请检查连接后重试。');
    }
  }

  // --- reset to input view ---
  function backToInput() {
    stopTimer();
    elInputError.hidden = true;
    showOnly(elInput);
  }

  // --- wire events ---
  if (elTextarea) {
    elTextarea.addEventListener('input', updateCharCount);
    updateCharCount();
  }
  if (elSubmit) elSubmit.addEventListener('click', runLint);
  if (elRetry) elRetry.addEventListener('click', backToInput);
  if (elAgain) elAgain.addEventListener('click', backToInput);

  // Cmd/Ctrl + Enter submits.
  if (elTextarea) {
    elTextarea.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        runLint();
      }
    });
  }
})();
