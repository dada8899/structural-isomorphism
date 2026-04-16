/**
 * Structural — API client (vanilla JS, no dependencies)
 */

const API_BASE = '/api';

// Pull current language (set by i18n.js). Defaults to 'zh' so existing
// behavior is preserved when i18n.js hasn't loaded.
function __apiLang() {
  try { return (window.i18n && window.i18n.getLang && window.i18n.getLang()) || 'zh'; } catch (e) { return 'zh'; }
}

async function apiFetch(path, options = {}) {
  const lang = __apiLang();
  let url = `${API_BASE}${path}`;
  // If caller provided a body, inject lang into it (body-field pattern).
  if (options.body && typeof options.body === 'string') {
    try {
      const parsed = JSON.parse(options.body);
      if (typeof parsed === 'object' && parsed !== null && parsed.lang === undefined) {
        parsed.lang = lang;
        options.body = JSON.stringify(parsed);
      }
    } catch (e) { /* body not JSON, skip */ }
  } else if (!options.body) {
    // GET/HEAD requests: append as query param (unless already set).
    const sep = url.includes('?') ? '&' : '?';
    if (!/[?&]lang=/.test(url)) url = `${url}${sep}lang=${encodeURIComponent(lang)}`;
  }
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`API ${resp.status}: ${text || resp.statusText}`);
  }
  return resp.json();
}

window.StructuralAPI = {
  async health() {
    return apiFetch('/health');
  },

  async search(query, topK = 12) {
    // Fast path: skip the LLM rewrite/assessment. The caller fires
    // assessQuery() in parallel for the worthiness gate.
    return apiFetch('/search', {
      method: 'POST',
      body: JSON.stringify({ query, top_k: topK, rewrite: false }),
    });
  },

  async assessQuery(query) {
    return apiFetch('/search/assess', {
      method: 'POST',
      body: JSON.stringify({ query }),
    });
  },

  async getPhenomenon(id) {
    return apiFetch(`/phenomenon/${encodeURIComponent(id)}`);
  },

  async generateMapping(aId, bId) {
    return apiFetch('/mapping', {
      method: 'POST',
      body: JSON.stringify({ a_id: aId, b_id: bId }),
    });
  },

  async getDaily() {
    return apiFetch('/daily');
  },

  async getExamples() {
    return apiFetch('/examples');
  },

  async getSuggestions() {
    return apiFetch('/suggest');
  },

  async synthesize(query, rewrittenQuery, results) {
    return apiFetch('/synthesize', {
      method: 'POST',
      body: JSON.stringify({
        query,
        rewritten_query: rewrittenQuery,
        results,
      }),
    });
  },
};
