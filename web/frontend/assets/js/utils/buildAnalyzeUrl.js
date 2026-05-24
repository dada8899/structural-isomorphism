/**
 * Structural — Shared /analyze URL builder.
 *
 * Single source of truth for the /analyze page URL contract. The /analyze
 * page (analyze.js) reads `id`, `q`, and (optionally) `a_id` from URL params,
 * then translates them to the backend API's `text_a`/`b_id`/`a_id` itself.
 *
 * This shim closes the gap that SESSION-21 §1 patched at four entry points
 * (ask.js / whitespace.js / apply.js / classes.js). Before this builder, each
 * caller hand-rolled URLSearchParams and could (and did) drift to the backend
 * API param names, breaking the deep-link silently.
 *
 * Usage:
 *   var url = window.buildAnalyzeUrl({ id: 'kb-123', q: 'why does X happen' });
 *   // -> "/analyze?id=kb-123&q=why%20does%20X%20happen"
 *
 * Params (all optional but at least one of id/q recommended):
 *   - id   : B-side phenomenon id (KB phenomenon). Without this analyze.js
 *            bails to empty state, so callers should hide CTAs when missing.
 *   - q    : prefilled research question text. Encoded as a single string.
 *   - a_id : optional A-side phenomenon id when both sides are known up front.
 *
 * Returns a relative URL string starting with "/analyze". Caller is
 * responsible for the host prefix when an absolute URL is needed.
 */
(function () {
  'use strict';

  function buildAnalyzeUrl(opts) {
    opts = opts || {};
    var p = new URLSearchParams();
    if (opts.id != null && opts.id !== '') p.set('id', String(opts.id));
    if (opts.q != null && opts.q !== '') p.set('q', String(opts.q));
    if (opts.a_id != null && opts.a_id !== '') p.set('a_id', String(opts.a_id));
    var qs = p.toString();
    return qs ? '/analyze?' + qs : '/analyze';
  }

  // Expose on window for classic-script callers; also export as CommonJS
  // for the node-based unit test runner under tests/.
  if (typeof window !== 'undefined') {
    window.buildAnalyzeUrl = buildAnalyzeUrl;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { buildAnalyzeUrl: buildAnalyzeUrl };
  }
}());
