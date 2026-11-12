/**
 * Structural — C2 structural lint page (Session #18).
 *
 * Posts a document to /api/struct-lint and renders the extracted
 * structural claims with failure modes + risk levels. Pure vanilla JS.
 */
(function () {
  'use strict';

  var contracts = window.SecondaryToolContracts;
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
  var elExamples = document.getElementById('lint-examples');

  var elLoadingTimer = document.getElementById('lint-loading-timer');
  var elLoadingHint = document.querySelector('#lint-loading .lint-loading__hint');
  var elErrorMsg = document.getElementById('lint-error-msg');
  var elRetry = document.getElementById('lint-retry');

  var elSummaryText = document.getElementById('lint-summary-text');
  var elClaims = document.getElementById('lint-claims');
  var elResultCount = document.getElementById('lint-result-count');
  var elAgain = document.getElementById('lint-again');

  var _timerInterval = null;
  var _stream = null;  // active POST stream for the current lint run
  var _activeRequestId = null;

  // --- default loading hint, restored on each new run ---
  var _DEFAULT_HINT = elLoadingHint ? elLoadingHint.textContent : '';

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
  var PRIORITY_LABEL = { high: '优先复核', medium: '建议复核', low: '常规复核' };

  // Optional KB candidate reference. It is a retrieval lead only and does
  // not change or validate the model-generated screen above it.
  function renderCandidate(candidate) {
    if (!candidate || !candidate.id) return '';
    var meta = esc(candidate.domain || '领域未标注') +
      ' · 本次检索候选 #' + candidate.retrieval_rank;
    var desc = candidate.description
      ? '<div class="lint-iso__desc">' + esc(candidate.description) + '</div>'
      : '';
    return '' +
      '<div class="lint-iso">' +
        '<div class="lint-iso__label">知识库候选参照（未验证）</div>' +
        '<div class="lint-iso__body">' +
          '<a class="lint-iso__name" href="/phenomenon/' +
            encodeURIComponent(candidate.id) + '">' + esc(candidate.name) + '</a>' +
          '<span class="lint-iso__meta">' + meta + '</span>' +
          desc +
          '<a class="lint-iso__analyze" href="/analyze?id=' +
            encodeURIComponent(candidate.id) + '">检验这个候选是否适用 →</a>' +
        '</div>' +
      '</div>';
  }

  function renderClaim(claim) {
    var priority = PRIORITY_LABEL[claim.review_priority] ? claim.review_priority : 'medium';
    var typeLabel = TYPE_LABEL[claim.claim_type] || claim.claim_type;

    var html = '' +
      '<div class="lint-claim lint-claim--' + priority + '">' +
        '<div class="lint-claim__head">' +
          '<span class="lint-tag lint-tag--type">' + esc(typeLabel) + '</span>' +
          '<span class="lint-tag lint-tag--risk-' + priority + '">' + PRIORITY_LABEL[priority] + '</span>' +
        '</div>' +
        '<p class="lint-claim__quote">“' + esc(claim.quote) + '”</p>' +
        '<div class="lint-claim__row">' +
          '<div class="lint-claim__row-label">底层结构</div>' +
          '<div class="lint-claim__row-text">' + esc(claim.structure) + '</div>' +
        '</div>' +
        renderCandidate(claim.reference_candidate) +
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

  // --- close any live stream ---
  function closeStream() {
    if (_stream) {
      try { _stream.close(); } catch (e) { /* ignore */ }
      _stream = null;
    }
  }

  // --- update the loading-block hint with live stage progress ---
  function setLoadingHint(text) {
    if (elLoadingHint) elLoadingHint.textContent = text || _DEFAULT_HINT;
  }

  function decodeEventBlock(block) {
    var eventName = 'message';
    var data = [];
    block.split(/\r?\n/).forEach(function (line) {
      if (line.indexOf('event:') === 0) eventName = line.slice(6).trim();
      if (line.indexOf('data:') === 0) data.push(line.slice(5).trimStart());
    });
    return { type: eventName, data: data.join('\n') };
  }

  function problemMessage(body, fallback) {
    if (body && typeof body.message === 'string') return body.message;
    if (body && typeof body.detail === 'string') return body.detail;
    return fallback;
  }

  // POST + ReadableStream keeps the full document out of the URL, browser
  // history, Referer, nginx request line and ordinary access logs.
  function openLintStream(documentText, requestId, onEvent, onTransportError) {
    var controller = new AbortController();
    var closed = false;
    var terminal = false;
    var timer = setTimeout(function () {
      if (closed || terminal) return;
      controller.abort();
      onTransportError('分析超时，请缩短文档或稍后重试。');
    }, 240000);

    function close() {
      if (closed) return;
      closed = true;
      clearTimeout(timer);
      controller.abort();
    }

    (async function () {
      try {
        var response = await fetch('/api/struct-lint/stream', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream'
          },
          body: JSON.stringify({
            document: documentText,
            client_request_id: requestId
          }),
          signal: controller.signal
        });
        if (!response.ok) {
          var problem = null;
          try { problem = await response.json(); } catch (e) { problem = null; }
          throw new Error(problemMessage(problem, '请求失败（HTTP ' + response.status + '）'));
        }
        if (!response.body) throw new Error('当前浏览器不支持流式响应。');

        var reader = response.body.getReader();
        var decoder = new TextDecoder('utf-8');
        var buffer = '';
        while (!closed) {
          var part = await reader.read();
          buffer += decoder.decode(part.value || new Uint8Array(), { stream: !part.done });
          var boundary;
          while ((boundary = buffer.search(/\r?\n\r?\n/)) !== -1) {
            var separator = buffer.slice(boundary).match(/^\r?\n\r?\n/)[0];
            var block = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + separator.length);
            if (!block.trim()) continue;
            var event = decodeEventBlock(block);
            if (event.type === 'done' || event.type === 'error') terminal = true;
            onEvent(event);
          }
          if (part.done) break;
        }
        if (!closed && !terminal) throw new Error('连接提前结束，请重试。');
      } catch (error) {
        if (!closed && !(error && error.name === 'AbortError')) {
          onTransportError(error && error.message ? error.message : '网络错误，请检查连接后重试。');
        }
      } finally {
        clearTimeout(timer);
      }
    }());

    return { close: close };
  }

  // --- submit handler — consumes the POST SSE endpoint ---
  function runLint() {
    var doc = String(elTextarea.value || '').normalize('NFKC').trim();
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

    closeStream();
    var requestId = contracts.createRequestId('lint');
    _activeRequestId = requestId;
    showOnly(elLoading);
    setLoadingHint(_DEFAULT_HINT);
    startTimer();

    _stream = openLintStream(doc, requestId, function (event) {
      if (_activeRequestId !== requestId) return;
      if (event.type === 'meta') {
        var meta = null;
        try { meta = JSON.parse(event.data); } catch (err) { meta = null; }
        if (!meta || meta.request_id !== requestId ||
            meta.contract_version !== contracts.CONTRACT_VERSION) {
          closeStream();
          showError('响应未通过请求绑定校验，未展示任何模型内容。请重试。');
          return;
        }
        setLoadingHint('正在连接分析服务……');
        return;
      }
      if (event.type === 'progress') {
        var progress = null;
        try { progress = JSON.parse(event.data); } catch (err) { progress = null; }
        if (progress && progress.message) setLoadingHint(progress.message);
        return;
      }
      if (event.type === 'done') {
        var payload = null;
        try { payload = JSON.parse(event.data); } catch (err) { payload = null; }
        var validated = contracts.validateLintPayload(
          payload && payload.result, requestId, doc
        );
        closeStream();
        stopTimer();
        if (!validated) {
          showError('结果未通过完整性校验，未展示任何模型内容。请重试。');
          return;
        }
        renderResult(validated);
        return;
      }
      if (event.type === 'error') {
        var body = null;
        try { body = JSON.parse(event.data); } catch (err) { body = null; }
        closeStream();
        showError(problemMessage(body, '请稍后重试。'));
      }
    }, function (message) {
      if (_activeRequestId !== requestId) return;
      closeStream();
      showError(message || '网络错误，请检查连接后重试。');
    });
  }

  // --- reset to input view ---
  function backToInput() {
    closeStream();
    _activeRequestId = null;
    stopTimer();
    setLoadingHint(_DEFAULT_HINT);
    elInputError.hidden = true;
    showOnly(elInput);
  }

  // --- wire events ---
  if (elTextarea) {
    elTextarea.addEventListener('input', updateCharCount);
    updateCharCount();
  }
  if (elExamples && elTextarea) {
    elExamples.addEventListener('click', function (e) {
      var target = e.target;
      if (!target || typeof target.closest !== 'function') return;
      var chip = target.closest('.lint-chip[data-example]');
      if (!chip || !elExamples.contains(chip)) return;

      elTextarea.value = chip.getAttribute('data-example') || '';
      elTextarea.dispatchEvent(new Event('input', { bubbles: true }));
      elTextarea.focus();
    });
  }
  if (elSubmit && contracts) elSubmit.addEventListener('click', runLint);
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
  window.addEventListener('pagehide', function () {
    closeStream();
    _activeRequestId = null;
  });
})();
