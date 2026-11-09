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
        const status = add('p','外部提交结果尚待核对。请从研究记录查看，不要重复发送。');
        status.setAttribute('role','status');
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
            status.textContent = keys(receipt,['status','operation_ref','request_digest']) &&
              receipt.status === 'accepted' && typeof receipt.operation_ref === 'string' && ID.test(receipt.operation_ref) &&
              receipt.request_digest === offer.request_digest
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

  return Object.freeze({preview, confirmation, mount});
});
