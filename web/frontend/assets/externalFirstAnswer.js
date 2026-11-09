/* Strict display/confirmation data for an optional user-triggered fallback.
 * This module performs no requests and never grants sending permission. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ExternalFirstAnswer = api;
})(typeof window === 'undefined' ? globalThis : window, function () {
  'use strict';
  const PURPOSE = 'external-first-answer-question-v1';
  const CONTRACT = 'external-first-answer-v1';
  const TARGET = 'https://api.deepseek.com/chat/completions';
  const KEY = /^[a-f0-9]{64}$/;
  const ID = /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
  const positive = value => Number.isSafeInteger(value) && value >= 1 && value <= 2147483647;
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value) &&
    (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
  const keys = (value, names) => object(value) && Object.keys(value).length === names.length &&
    names.every(name => Object.hasOwn(value, name));

  function preview(value, expected, nowSeconds) {
    if (!keys(value, ['contract_revision','purpose','metadata','exact_question','provider','model','target',
                      'currency','scale','upper_units','preview_digest','request_digest','valid_until','may_send']) ||
        !object(expected) || value.contract_revision !== CONTRACT || value.purpose !== PURPOSE ||
        value.provider !== 'deepseek' || value.model !== 'deepseek-flash' || value.target !== TARGET ||
        value.currency !== 'CNY' || value.scale !== 6 || !Number.isSafeInteger(value.upper_units) ||
        value.upper_units < 1 || value.upper_units > 300000000 || typeof value.may_send !== 'boolean' ||
        typeof value.preview_digest !== 'string' || !KEY.test(value.preview_digest) ||
        typeof value.request_digest !== 'string' || !KEY.test(value.request_digest) ||
        !Number.isSafeInteger(nowSeconds) || !Number.isSafeInteger(value.valid_until) ||
        value.valid_until <= nowSeconds || value.valid_until - nowSeconds > 60 ||
        typeof value.exact_question !== 'string' || Array.from(value.exact_question).length < 8 ||
        Array.from(value.exact_question).length > 1000 || value.exact_question !== expected.original_input) return null;
    const anchor = value.metadata;
    if (!keys(anchor,['research_id','input_revision','research_version','problem_digest']) ||
        typeof anchor.research_id !== 'string' || !ID.test(anchor.research_id) ||
        !positive(anchor.input_revision) || !positive(anchor.research_version) ||
        typeof anchor.problem_digest !== 'string' || !KEY.test(anchor.problem_digest) ||
        anchor.research_id !== expected.research_id || anchor.input_revision !== expected.input_revision ||
        anchor.research_version !== expected.research_version || anchor.problem_digest !== expected.problem_digest) return null;
    return Object.freeze({...value, metadata:Object.freeze({...anchor})});
  }

  function confirmation(value, expected, decision, nowSeconds) {
    const checked = preview(value, expected, nowSeconds);
    if (!checked || !checked.may_send ||
        !keys(decision,['confirm_exact_question','confirm_maximum_cost','declares_right_to_send']) ||
        Object.values(decision).some(item => item !== true)) return null;
    // No question text, provider URL, materials or cost override can be sent
    // from the confirmation panel; the server re-reads the approved snapshot.
    return Object.freeze({
      purpose:PURPOSE,
      preview_digest:checked.preview_digest,
      request_digest:checked.request_digest,
      upper_units:checked.upper_units,
      confirm_exact_question:true,
      confirm_maximum_cost:true,
      declares_right_to_send:true,
    });
  }

  function statusReceipt(value, expected) {
    if (!keys(value,['contract_revision','metadata','operation_key','status']) ||
        value.contract_revision !== CONTRACT || !object(expected) ||
        typeof value.operation_key !== 'string' || !ID.test(value.operation_key) ||
        value.operation_key !== expected.operation_key ||
        !['pending','accepted','unknown','completed','not_sent'].includes(value.status) ||
        !keys(value.metadata,['research_id','input_revision','research_version','problem_digest'])) return null;
    return ['research_id','input_revision','research_version','problem_digest']
      .every(key => value.metadata[key] === expected[key]) ? value.status : null;
  }

  function resultReceipt(value, expected) {
    if (!keys(value,['contract_revision','metadata','operation_key','result_digest','schema','review_required','candidate']) ||
        value.contract_revision !== CONTRACT || value.schema !== 'external-first-answer-unverified-candidate-v1' ||
        value.review_required !== true || typeof value.result_digest !== 'string' || !KEY.test(value.result_digest) ||
        !statusReceipt({contract_revision:value.contract_revision,metadata:value.metadata,
                        operation_key:value.operation_key,status:'completed'},expected)) return null;
    const item = value.candidate;
    const text = (input,max) => typeof input === 'string' && input.trim().length > 0 &&
      Array.from(input).length <= max && !/[<>]|https?:|www\./i.test(input);
    if (keys(item,['status','explanation','assumptions','next_check','evidence_status']) &&
        item.status === 'candidate' && item.evidence_status === 'not_checked' && text(item.explanation,900) &&
        Array.isArray(item.assumptions) && item.assumptions.length >= 1 && item.assumptions.length <= 4 &&
        item.assumptions.every(value=>text(value,240)) && text(item.next_check,400)) return item;
    if (keys(item,['status','question']) && item.status === 'clarification' && text(item.question,240)) return item;
    if (keys(item,['status','reason']) && item.status === 'insufficient' &&
        ['unsupported','not_enough_information'].includes(item.reason)) return item;
    return null;
  }

  function mount(panel, options) {
    const doc = panel.ownerDocument;
    let epoch = 0;
    function reset() { epoch++; panel.hidden = true; panel.replaceChildren(); }
    function add(tag, text, parent = panel) {
      const element = doc.createElement(tag);
      element.textContent = text;
      parent.append(element);
      return element;
    }
    function button(text, parent = panel) {
      const element = add('button', text, parent);
      element.type = 'button';
      return element;
    }
    function offer() {
      reset();
      const current = options.current();
      if (current?.external_first_answer === 'pending') {
        panel.hidden = false;
        const status = add('p','外部提交结果尚待核对。不要重复发送。');
        status.setAttribute('role','status');
        if (typeof options.inspect !== 'function' || typeof current.operation_key !== 'string' ||
            !ID.test(current.operation_key)) return;
        const anchor = Object.freeze({...current});
        const generation = epoch;
        const active = () => {
          const latest = options.current();
          return generation === epoch && latest?.external_first_answer === 'pending' &&
            ['research_id','input_revision','research_version','problem_digest','actor','operation_key']
              .every(key => latest[key] === anchor[key]);
        };
        const inspect = button('核对原提交');
        const readResult = button('查看待核查分析');
        readResult.hidden = true;
        const resultBody = add('div','');
        readResult.addEventListener('click', async () => {
          if (!active() || readResult.disabled || typeof options.loadResult !== 'function') return;
          readResult.disabled = true;
          let result;
          try { result = resultReceipt(await options.loadResult(anchor), anchor); } catch {}
          if (!active()) return;
          readResult.disabled = false;
          resultBody.replaceChildren();
          if (!result) { add('p','暂时无法核对原返回内容。',resultBody); return; }
          add('h3','外部返回 · 待核查',resultBody);
          if (result.status === 'candidate') {
            add('p','此解释尚未核验证据。',resultBody);
            add('p',result.explanation,resultBody);
            const conditions = add('ul','',resultBody);
            for (const item of result.assumptions) add('li',item,conditions);
            add('p',result.next_check,resultBody);
          } else if (result.status === 'clarification') add('p',result.question,resultBody);
          else add('p','原返回没有足够信息形成解释。',resultBody);
        });
        inspect.addEventListener('click', async () => {
          if (!active() || inspect.disabled) return;
          inspect.disabled = true;
          status.textContent = '正在只读核对原提交…';
          let observed;
          try { observed = statusReceipt(await options.inspect(anchor),anchor); } catch {}
          if (!active()) return;
          const labels = {
            pending:'原请求仍在等待核对。不要重复发送。',
            accepted:'原请求已接收。请继续查看这一条记录。',
            unknown:'服务端尚不能确认原请求结果。不要重复发送。',
            completed:'原请求已返回。请查看该修订的待核查分析。',
            not_sent:'服务端确认原请求未发送。此处不会重新提交。',
          };
          status.textContent = labels[observed] || '暂时无法核对原请求。不要重复发送。';
          readResult.hidden = observed !== 'completed' || typeof options.loadResult !== 'function';
          inspect.disabled = false;
        });
        return;
      }
      if (!current || current.external_first_answer !== 'ready') return;
      const anchor = Object.freeze({...current});
      const generation = epoch;
      const active = () => {
        const current = options.current();
        return generation === epoch && current && ['ready','pending'].includes(current.external_first_answer) &&
          ['research_id','input_revision','research_version','problem_digest','original_input','actor']
            .every(key => current[key] === anchor[key]);
      };
      panel.hidden = false;
      const open = button('查看外部分析选项');
      const status = add('p', '');
      status.setAttribute('role','status');
      open.addEventListener('click', async () => {
        if (!active() || open.disabled) return;
        open.disabled = true;
        status.textContent = '正在读取外发预览…';
        let offer;
        try { offer = preview(await options.load(anchor), anchor, options.now()); } catch {}
        if (!active()) return;
        if (!offer) {
          status.textContent = '外部分析预览暂不可用。原问题仍已保存。';
          open.disabled = false;
          return;
        }
        status.textContent = offer.may_send ? '请核对本次发送内容和费用。' : '外部分析当前未开放。';
        const detail = add('div', '');
        add('p', '接收方：DeepSeek', detail);
        add('p', '费用上限：人民币 ¥' + (offer.upper_units / 1000000).toFixed(6), detail);
        add('pre', offer.exact_question, detail);
        button('关闭预览', detail).addEventListener('click', () => { if (active()) offerPanel(); });
        if (!offer.may_send) return;
        const checks = {};
        for (const [key,text] of [
          ['confirm_exact_question','同意发送上方这条问题'],
          ['confirm_maximum_cost','接受本次费用上限'],
          ['declares_right_to_send','我有权发送这段内容'],
        ]) {
          const label = add('label', '', detail);
          const input = doc.createElement('input');
          input.type = 'checkbox';
          label.append(input, doc.createTextNode(text));
          checks[key] = input;
        }
        const send = button('确认发送', detail);
        let submitted = false;
        send.disabled = true;
        const decisions = () => Object.fromEntries(Object.entries(checks).map(([key,input])=>[key,input.checked]));
        for (const input of Object.values(checks)) input.addEventListener('change', () => {
          send.disabled = submitted || !active() || !confirmation(offer,anchor,decisions(),options.now());
        });
        send.addEventListener('click', async () => {
          if (!active() || submitted) return;
          const body = confirmation(offer, anchor, decisions(), options.now());
          if (!body) { send.disabled = true; status.textContent = '报价已失效，请重新查看。'; return; }
          submitted = true;
          send.disabled = true;
          for (const control of detail.querySelectorAll('button,input')) control.disabled = true;
          status.textContent = '正在核对提交结果…';
          try {
            const receipt = await options.submit(anchor, body);
            if (!active()) return;
            const observed = statusReceipt(receipt,options.current());
            status.textContent = observed === 'completed'
              ? '原请求已返回。请重开研究记录查看待核查分析。'
              : ['accepted','pending'].includes(observed)
                ? '请求已接收。请从研究记录查看进度。'
                : '提交结果尚未确认。请从研究记录核对，不要重复发送。';
          } catch {
            if (active()) status.textContent = '提交结果尚未确认。请从研究记录核对，不要重复发送。';
          }
        });
      });
    }
    const offerPanel = offer;
    return Object.freeze({offer, reset});
  }

  return Object.freeze({preview, confirmation, statusReceipt, resultReceipt, mount});
});
