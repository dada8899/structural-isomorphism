/**
 * Structural — Shared /analyze URL builder.
 *
 * Single source of truth for the /analyze page URL contract. The /analyze
 * User text and its confirmed fingerprint are written to a one-use,
 * short-lived sessionStorage handoff. The URL carries only public KB ids and
 * a random local handoff key, so browser history/referrers never receive the
 * question text.
 *
 * This shim closes the gap that SESSION-21 §1 patched at four entry points
 * (ask.js / whitespace.js / apply.js / classes.js). Before this builder, each
 * caller hand-rolled URLSearchParams and could (and did) drift to the backend
 * API param names, breaking the deep-link silently.
 *
 * Usage:
 *   var url = window.buildAnalyzeUrl({ id: 'kb-123', q: 'why does X happen' });
 *   // -> "/analyze?id=kb-123&handoff=9f..." (question stays local)
 *
 * Params (all optional but at least one of id/q recommended):
 *   - id   : B-side phenomenon id (KB phenomenon). Without this analyze.js
 *            bails to empty state, so callers should hide CTAs when missing.
 *   - q    : prefilled research question text. Stored locally, never in URL.
 *   - a_id : optional A-side phenomenon id when both sides are known up front.
 *   - fingerprint : optional user-confirmed structure, stored with q.
 *   - origin_discovery_id / origin_contract_version : optional validated
 *            candidate provenance, stored locally with q rather than in URL.
 *
 * Returns a relative URL string starting with "/analyze". Caller is
 * responsible for the host prefix when an absolute URL is needed.
 */
(function () {
  'use strict';

  var PREFIX = 'structural_analyze_handoff:';
  var MAX_AGE_MS = 15 * 60 * 1000;
  var MAX_PENDING = 32;
  var MAX_STORAGE_ENTRIES = 4096;
  var MAX_RESEARCH_QUERY_CHARS = 8000;
  var ENTITY_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/;
  var DISCOVERY_ID_RE = /^discovery-[0-9a-f]{16}$/;
  var CONTROL_RE = /[\p{Cc}\p{Cf}\p{Cs}]/u;
  var HTML_TAG_RE = /<\s*\/?\s*(?:[A-Za-z]|!)[^>]*>/;
  var DEFAULT_IGNORABLE_RANGES = [
    [0x00AD, 0x00AD], [0x034F, 0x034F], [0x061C, 0x061C],
    [0x115F, 0x1160], [0x17B4, 0x17B5], [0x180B, 0x180F],
    [0x200B, 0x200F], [0x202A, 0x202E], [0x2060, 0x206F],
    [0x3164, 0x3164], [0xFE00, 0xFE0F], [0xFEFF, 0xFEFF],
    [0xFFA0, 0xFFA0], [0x1BCA0, 0x1BCA3], [0x1D173, 0x1D17A],
    [0xE0000, 0xE0FFF]
  ];

  function hasForbiddenUnicode(value, allowLayout) {
    for (var char of value) {
      if (allowLayout && (char === '\n' || char === '\r' || char === '\t')) continue;
      if (CONTROL_RE.test(char)) return true;
      var codepoint = char.codePointAt(0);
      if (DEFAULT_IGNORABLE_RANGES.some(function (range) {
        return range[0] <= codepoint && codepoint <= range[1];
      })) return true;
    }
    return false;
  }

  function safeText(value, maximum, allowLayout) {
    if (typeof value !== 'string') return '';
    var normalized = value.normalize('NFKC').trim();
    if (!normalized || Array.from(normalized).length > maximum || HTML_TAG_RE.test(normalized)) return '';
    if (hasForbiddenUnicode(value, allowLayout) ||
        hasForbiddenUnicode(normalized, allowLayout)) return '';
    return normalized;
  }

  function safeId(value) {
    if (value == null || value === '') return '';
    var normalized = String(value).trim();
    return ENTITY_ID_RE.test(normalized) ? normalized : '';
  }

  function normalizeFingerprint(raw, query) {
    if (raw == null) return null;
    if (typeof raw !== 'object' || Array.isArray(raw)) return null;
    var allowed = {
      source_query: true, summary: true, variables: true,
      constraints: true, unknowns: true, revision: true
    };
    if (Object.keys(raw).some(function (key) { return !allowed[key]; })) return null;
    var sourceQuery = safeText(raw.source_query, MAX_RESEARCH_QUERY_CHARS, true);
    var summary = safeText(raw.summary, 1000, true);
    if (!sourceQuery || sourceQuery !== query || !summary || summary.length < 8) return null;
    var result = { source_query: sourceQuery, summary: summary };
    for (var field of ['variables', 'constraints', 'unknowns']) {
      var values = raw[field] == null ? [] : raw[field];
      if (!Array.isArray(values) || values.length > 12) return null;
      var cleaned = values.map(function (item) { return safeText(item, 120, false); });
      if (cleaned.some(function (item) { return !item; })) return null;
      result[field] = cleaned;
    }
    var revision = raw.revision == null ? 1 : raw.revision;
    if (!Number.isInteger(revision) || revision < 1 || revision > 1000) return null;
    result.revision = revision;
    return result;
  }

  function normalizeOrigin(opts) {
    var discoveryId = opts.origin_discovery_id;
    var contract = opts.origin_contract_version;
    if (discoveryId == null && contract == null) return null;
    if (typeof discoveryId !== 'string' || !DISCOVERY_ID_RE.test(discoveryId) ||
        contract !== 'discovery-candidate-v2') return null;
    return {
      origin_discovery_id: discoveryId,
      origin_contract_version: contract
    };
  }

  function randomKey() {
    try {
      if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
        var bytes = new Uint8Array(16);
        crypto.getRandomValues(bytes);
        return Array.from(bytes).map(function (b) {
          return ('0' + b.toString(16)).slice(-2);
        }).join('');
      }
    } catch (e) { return ''; }
    return '';
  }

  function pendingRecords() {
    var rows = [];
    try {
      var scanLimit = sessionStorage.length;
      if (!Number.isSafeInteger(scanLimit) || scanLimit < 0 || scanLimit > MAX_STORAGE_ENTRIES) {
        return null;
      }
      var index = 0;
      for (var scanned = 0; scanned < scanLimit && index < sessionStorage.length; scanned += 1) {
        var currentLength = sessionStorage.length;
        if (!Number.isSafeInteger(currentLength) || currentLength < 0 ||
            currentLength > MAX_STORAGE_ENTRIES) return null;
        if (index >= currentLength) break;
        var key = sessionStorage.key(index);
        if (typeof key !== 'string' || !key) return null;
        if (key.indexOf(PREFIX) !== 0) {
          index += 1;
          continue;
        }
        var created = 0;
        try { created = Number(JSON.parse(sessionStorage.getItem(key) || '{}').created_at) || 0; } catch (_) {}
        if (!created || Date.now() - created > MAX_AGE_MS) {
          sessionStorage.removeItem(key);
          if (sessionStorage.getItem(key) !== null) return null;
          var reducedLength = sessionStorage.length;
          if (!Number.isSafeInteger(reducedLength) || reducedLength !== currentLength - 1) {
            return null;
          }
        } else {
          rows.push({ key: key, created_at: created });
          index += 1;
        }
      }
      var finalLength = sessionStorage.length;
      if (!Number.isSafeInteger(finalLength) || finalLength < 0 ||
          finalLength > MAX_STORAGE_ENTRIES || index < finalLength) return null;
    } catch (_) { return null; }
    return rows.sort(function (a, b) { return a.created_at - b.created_at; });
  }

  function createHandoff(opts) {
    var query = safeText(opts.q, MAX_RESEARCH_QUERY_CHARS, true);
    if (!query) return '';
    var fingerprint = normalizeFingerprint(opts.fingerprint, query);
    if (opts.fingerprint != null && !fingerprint) return '';
    var origin = normalizeOrigin(opts);
    if ((opts.origin_discovery_id != null || opts.origin_contract_version != null) && !origin) return '';
    try {
      var records = pendingRecords();
      if (!records) return '';
      while (records.length >= MAX_PENDING) {
        var oldest = records.shift().key;
        sessionStorage.removeItem(oldest);
        if (sessionStorage.getItem(oldest) !== null) return '';
      }
      var serialized = JSON.stringify({
        version: 2,
        created_at: Date.now(),
        query: query,
        id: opts.id == null ? '' : String(opts.id),
        a_id: opts.a_id == null ? null : String(opts.a_id),
        fingerprint: fingerprint,
        origin_discovery_id: origin ? origin.origin_discovery_id : null,
        origin_contract_version: origin ? origin.origin_contract_version : null
      });
      for (var attempt = 0; attempt < 8; attempt += 1) {
        var key = randomKey();
        if (!key) return '';
        var storageKey = PREFIX + key;
        if (sessionStorage.getItem(storageKey) !== null) continue;
        sessionStorage.setItem(storageKey, serialized);
        if (sessionStorage.getItem(storageKey) !== serialized) {
          try { sessionStorage.removeItem(storageKey); } catch (_) {}
          return '';
        }
        return key;
      }
      return '';
    } catch (_) {
      // Privacy fails closed when sessionStorage is unavailable: never fall
      // back to putting the question into the URL.
      return '';
    }
  }

  function consumeAnalyzeHandoff(key, expected) {
    if (!/^[0-9a-f]{16,64}$/.test(String(key || ''))) return null;
    var raw = null;
    try {
      raw = sessionStorage.getItem(PREFIX + key);
      sessionStorage.removeItem(PREFIX + key); // consume before parsing
      if (sessionStorage.getItem(PREFIX + key) !== null) return null;
    } catch (_) { return null; }
    if (!raw) return null;
    try {
      var value = JSON.parse(raw);
      if (!value || (value.version !== 1 && value.version !== 2) ||
          !Number.isFinite(value.created_at) ||
          value.created_at > Date.now() + 30000 ||
          Date.now() - value.created_at > MAX_AGE_MS) return null;
      var query = safeText(value.query, MAX_RESEARCH_QUERY_CHARS, true);
      var id = safeId(value.id);
      var aId = value.a_id == null ? null : safeId(value.a_id);
      if (!query || (value.id && !id) || (value.a_id != null && !aId)) return null;
      expected = expected || {};
      if (id !== safeId(expected.id)) return null;
      if ((aId || '') !== (safeId(expected.a_id) || '')) return null;
      var fingerprint = normalizeFingerprint(value.fingerprint, query);
      if (value.fingerprint != null && !fingerprint) return null;
      var origin = normalizeOrigin(value);
      if ((value.origin_discovery_id != null || value.origin_contract_version != null) && !origin) return null;
      return {
        version: 2,
        created_at: value.created_at,
        query: query,
        id: id,
        a_id: aId,
        fingerprint: fingerprint,
        origin_discovery_id: origin ? origin.origin_discovery_id : null,
        origin_contract_version: origin ? origin.origin_contract_version : null
      };
    } catch (_) { return null; }
  }

  function buildAnalyzeUrl(opts) {
    opts = opts || {};
    var p = new URLSearchParams();
    var id = safeId(opts.id);
    var aId = safeId(opts.a_id);
    if (opts.id != null && opts.id !== '' && !id) return '/analyze';
    if (opts.a_id != null && opts.a_id !== '' && !aId) return id ? '/analyze?id=' + encodeURIComponent(id) : '/analyze';
    if (id) p.set('id', id);
    if (aId) p.set('a_id', aId);
    var privateRequested = opts.q != null && String(opts.q).trim() !== '';
    var handoff = createHandoff(opts);
    if (handoff) p.set('handoff', handoff);
    if (privateRequested && !handoff) p.delete('a_id');
    var qs = p.toString();
    return qs ? '/analyze?' + qs : '/analyze';
  }

  // Expose on window for classic-script callers; also export as CommonJS
  // for the node-based unit test runner under tests/.
  if (typeof window !== 'undefined') {
    window.StructuralInputLimits = Object.freeze({
      researchQueryChars: MAX_RESEARCH_QUERY_CHARS
    });
    window.buildAnalyzeUrl = buildAnalyzeUrl;
    window.consumeAnalyzeHandoff = consumeAnalyzeHandoff;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      buildAnalyzeUrl: buildAnalyzeUrl,
      consumeAnalyzeHandoff: consumeAnalyzeHandoff,
      MAX_RESEARCH_QUERY_CHARS: MAX_RESEARCH_QUERY_CHARS
    };
  }
}());
