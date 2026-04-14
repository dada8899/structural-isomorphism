/**
 * Structural — API client (vanilla JS, no dependencies)
 */

const API_BASE = '/api';

async function apiFetch(path, options = {}) {
  const url = `${API_BASE}${path}`;
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
