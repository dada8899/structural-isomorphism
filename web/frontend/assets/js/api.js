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

  /**
   * Streaming synthesize. Returns { abort } so callers can cancel mid-flight.
   * callbacks: { onText({content,total_length}), onDone({result}), onError(err) }
   *
   * EventSource doesn't support POST so we hand-parse SSE off fetch's
   * ReadableStream. The wire format matches the backend exactly:
   *   event: text\ndata: {...}\n\n
   *   event: done\ndata: {...}\n\n
   *   event: error\ndata: {...}\n\n
   */
  synthesizeStream(query, rewrittenQuery, results, callbacks) {
    const lang = __apiLang();
    const ctrl = new AbortController();
    const cb = callbacks || {};

    (async () => {
      try {
        const resp = await fetch(`${API_BASE}/synthesize/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
          },
          body: JSON.stringify({
            query,
            rewritten_query: rewrittenQuery,
            results,
            lang,
          }),
          signal: ctrl.signal,
        });
        if (!resp.ok) {
          const text = await resp.text().catch(() => '');
          throw new Error(`API ${resp.status}: ${text || resp.statusText}`);
        }
        if (!resp.body) {
          throw new Error('No response body (streaming unsupported)');
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        // SSE messages are separated by a blank line (\n\n)
        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let idx;
          while ((idx = buffer.indexOf('\n\n')) !== -1) {
            const message = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            let event = 'message';
            let data = '';
            for (const line of message.split('\n')) {
              if (line.startsWith('event: ')) event = line.slice(7).trim();
              else if (line.startsWith('data: ')) data += line.slice(6);
            }
            if (!data) continue;
            let parsed;
            try { parsed = JSON.parse(data); }
            catch (e) {
              console.warn('[synthesize] SSE parse failed:', e, data);
              continue;
            }
            if (event === 'text') cb.onText && cb.onText(parsed);
            else if (event === 'done') { cb.onDone && cb.onDone(parsed); return; }
            else if (event === 'error') {
              const err = new Error(parsed.message || 'stream error');
              err.payload = parsed;
              throw err;
            }
          }
        }
      } catch (err) {
        if (err && err.name === 'AbortError') return;
        if (cb.onError) cb.onError(err);
        else console.error('[synthesize] stream error:', err);
      }
    })();

    return { abort: () => ctrl.abort() };
  },
};
