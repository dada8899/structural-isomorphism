/* Structural — A1 方法反查页 (Session #18)
 *
 * 用户输入一个方法 → POST /api/method/apply → 展示结构签名 +
 * "这个方法还能用在这些地方" 的现象卡片。每张卡片可跳到 /analyze 预填。
 */
(function () {
  'use strict';

  var form = document.getElementById('apply-form');
  var input = document.getElementById('apply-input');
  var countEl = document.getElementById('apply-count');
  var submitBtn = document.getElementById('apply-submit');
  var statusEl = document.getElementById('apply-status');
  var resultEl = document.getElementById('apply-result');
  var signatureEl = document.getElementById('apply-signature');
  var matchesEl = document.getElementById('apply-matches');
  var matchesCountEl = document.getElementById('apply-matches-count');
  var examplesEl = document.getElementById('apply-examples');

  var MAX_LEN = 1000;
  var busy = false;

  // --- helpers ---------------------------------------------------------

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function showStatus(kind, html) {
    statusEl.hidden = false;
    statusEl.className = 'apply-status apply-status--' + kind;
    statusEl.innerHTML = html;
  }

  function hideStatus() {
    statusEl.hidden = true;
    statusEl.innerHTML = '';
  }

  function setBusy(on) {
    busy = on;
    submitBtn.disabled = on;
    submitBtn.textContent = on ? '正在分析…' : '查找可套用的领域';
  }

  function updateCount() {
    var n = input.value.length;
    countEl.textContent = n + ' / ' + MAX_LEN;
  }

  // --- render ----------------------------------------------------------

  function renderSignature(data) {
    var kws = (data.keywords || []).map(function (k) {
      return '<span class="apply-kw">' + esc(k) + '</span>';
    }).join('');
    var degraded = data.llm_used
      ? ''
      : '<p class="apply-signature__note">当前未启用结构提炼模型，'
        + '签名直接采用原始描述，结果仍按结构相似度排序。</p>';
    signatureEl.innerHTML =
      '<div class="apply-signature__label">结构签名</div>'
      + '<p class="apply-signature__text">' + esc(data.signature) + '</p>'
      + (kws ? '<div class="apply-signature__kws">' + kws + '</div>' : '')
      + degraded;
  }

  function relevancePct(r) {
    var v = Math.max(0, Math.min(1, Number(r) || 0));
    return Math.round(v * 100);
  }

  function buildAnalyzeUrl(method, m) {
    // q  = 方法 + 现象（让 analyze 知道要把方法套到这个现象上）;
    // id = 现象 id，作为 analyze 的目标现象。
    // URL contract lives in utils/buildAnalyzeUrl.js — single source of truth.
    var textA = '能不能把「' + method + '」这个方法套用到「'
      + m.name + '」（' + m.domain + '）上？';
    return window.buildAnalyzeUrl({ id: m.id, q: textA });
  }

  function renderMatches(method, matches) {
    if (!matches.length) {
      matchesCountEl.textContent = '';
      matchesEl.innerHTML =
        '<div class="apply-empty">'
        + '没有找到结构上能套用的现象。试试把方法描述写得更具体——'
        + '说明它假设了什么结构、靠什么机制起作用。'
        + '</div>';
      return;
    }
    matchesCountEl.textContent = matches.length + ' 个候选';
    matchesEl.innerHTML = matches.map(function (m) {
      var note = m.apply_note
        ? '<p class="apply-card__note">' + esc(m.apply_note) + '</p>'
        : '<p class="apply-card__note apply-card__note--muted">'
          + esc((m.description || '').slice(0, 90)) + '</p>';
      var url = buildAnalyzeUrl(method, m);
      return ''
        + '<article class="apply-card">'
        + '  <div class="apply-card__top">'
        + '    <span class="apply-card__domain">' + esc(m.domain) + '</span>'
        + '    <span class="apply-card__rel" title="结构相似度">'
        +        relevancePct(m.relevance) + '%</span>'
        + '  </div>'
        + '  <h3 class="apply-card__name">' + esc(m.name) + '</h3>'
        + note
        + '  <a class="apply-card__link" href="' + esc(url) + '">'
        +     '深入分析 →</a>'
        + '</article>';
    }).join('');
  }

  // --- submit ----------------------------------------------------------

  async function run(method) {
    if (busy) return;
    method = (method || '').trim();
    if (method.length < 4) {
      showStatus('error', '请至少输入 4 个字描述这个方法。');
      resultEl.hidden = true;
      return;
    }
    if (method.length > MAX_LEN) {
      showStatus('error', '方法描述过长，请精简到 ' + MAX_LEN + ' 字以内。');
      return;
    }

    setBusy(true);
    showStatus('loading', '<span class="apply-spinner"></span>'
      + '正在提炼结构签名并检索可套用的领域…');
    resultEl.hidden = true;

    try {
      var resp = await fetch('/api/method/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ method: method, top_n: 8 })
      });

      if (!resp.ok) {
        var msg = '分析失败，请稍后重试。';
        if (resp.status === 422) msg = '输入不符合要求，请检查方法描述。';
        else if (resp.status === 503) msg = '检索服务正在启动，请稍后再试。';
        showStatus('error', msg);
        return;
      }

      var data = await resp.json();
      hideStatus();
      renderSignature(data);
      renderMatches(method, data.matches || []);
      resultEl.hidden = false;
      resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (e) {
      showStatus('error', '网络异常，请检查连接后重试。');
    } finally {
      setBusy(false);
    }
  }

  // --- events ----------------------------------------------------------

  input.addEventListener('input', updateCount);

  // Cmd/Ctrl+Enter 提交
  input.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      run(input.value);
    }
  });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    run(input.value);
  });

  examplesEl.addEventListener('click', function (e) {
    var chip = e.target.closest('.apply-chip');
    if (!chip) return;
    input.value = chip.getAttribute('data-method') || '';
    updateCount();
    run(input.value);
  });

  // URL 预填：?method=
  (function prefill() {
    try {
      var m = new URLSearchParams(window.location.search).get('method');
      if (m) {
        input.value = m.slice(0, MAX_LEN);
        updateCount();
        run(input.value);
      }
    } catch (e) { /* ignore */ }
  })();

  updateCount();
})();
