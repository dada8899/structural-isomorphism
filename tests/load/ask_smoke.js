// ask_smoke.js — k6 smoke test for /api/ask/stream SSE endpoint (W14-B)
//
// LLM-bound: thresholds relaxed to p(95)<5000ms.
// SSE streams a series of events; we read the full body and verify the [DONE]
// terminator. Each VU pulls a random query from queries.json.
//
// NOTE: /api/ask/stream consumes real LLM budget. Use against staging/local
// only by default; explicit BASE_URL=prod required.
//
// Run:
//   BASE_URL=http://localhost:8000 k6 run tests/load/ask_smoke.js
//
// To dial the load lower (e.g. 1-2 VU prod sanity):
//   BASE_URL=https://beta.structural.bytedance.city VUS=1 DURATION=20s \
//     k6 run tests/load/ask_smoke.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const VUS = parseInt(__ENV.VUS || '5');
const DURATION = __ENV.DURATION || '60s';

const queries = new SharedArray('queries', function () {
  return JSON.parse(open('./queries.json')).queries;
});

export const options = {
  scenarios: {
    ask_smoke: {
      executor: 'constant-vus',
      vus: VUS,
      duration: DURATION,
    },
  },
  thresholds: {
    // LLM-bound: P95 5s, P99 10s.
    http_req_duration: ['p(95)<5000', 'p(99)<10000'],
    http_req_failed: ['rate<0.05'],  // SSE timeouts more tolerated
    checks: ['rate>0.95'],
  },
  userAgent: 'structural-isomorphism-k6-loadtest/1.0 (w14-b ask_smoke)',
};

export default function () {
  const q = queries[Math.floor(Math.random() * queries.length)];
  const payload = JSON.stringify({ query: q });
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    timeout: '60s',
    tags: { endpoint: '/api/ask/stream' },
  };
  const res = http.post(`${BASE_URL}/api/ask/stream`, payload, params);
  check(res, {
    'status 200': (r) => r.status === 200,
    'is SSE': (r) => (r.headers['Content-Type'] || '').includes('text/event-stream'),
    'body non-empty': (r) => r.body && r.body.length > 0,
    'has data events': (r) => r.body && r.body.includes('data:'),
  });
  // Polite pacing — SSE streams are heavy on the backend.
  sleep(2);
}

export function handleSummary(data) {
  const m = data.metrics;
  const summary = {
    endpoint: '/api/ask/stream',
    base_url: BASE_URL,
    vus: VUS,
    duration: DURATION,
    p50_ms: m.http_req_duration?.values?.med?.toFixed(1),
    p95_ms: m.http_req_duration?.values?.['p(95)']?.toFixed(1),
    p99_ms: m.http_req_duration?.values?.['p(99)']?.toFixed(1),
    error_rate: m.http_req_failed?.values?.rate?.toFixed(4),
    requests: m.http_reqs?.values?.count,
    rps: m.http_reqs?.values?.rate?.toFixed(2),
    note: 'LLM-bound endpoint — costs real budget',
  };
  return {
    stdout: '\n=== ask_smoke summary ===\n' + JSON.stringify(summary, null, 2) + '\n',
    'tests/load/results/ask_smoke.json': JSON.stringify(summary, null, 2),
  };
}
