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

  return Object.freeze({preview, confirmation});
});
