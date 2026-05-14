// mixed_realistic.js — weighted-mix realistic traffic profile (W14-B)
//
// Approximates the prod traffic shape observed on beta.structural after
// W10-E ships:
//   60 %  /api/daily        (cheap GET, homepage refresh)
//   20 %  /phase/api/companies  (companies list)
//   15 %  /api/universality/classes (universality explorer)
//    5 %  /api/ask/stream  (LLM-bound, expensive)
//
// 50 VUs × 5 min total. Designed to be the canonical "is the backend
// healthy under realistic load" check.
//
// Run:
//   BASE_URL=http://localhost:8000 k6 run tests/load/mixed_realistic.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const VUS = parseInt(__ENV.VUS || '50');
const DURATION = __ENV.DURATION || '5m';

const queries = new SharedArray('queries', function () {
  return JSON.parse(open('./queries.json')).queries;
});

const CLASS_IDS = [
  'preferential_attachment',
  'soc_threshold_cascade',
  'kuramoto_sync',
  'self_organized_criticality',
  'power_law_tail',
];

export const options = {
  scenarios: {
    mixed: {
      executor: 'constant-vus',
      vus: VUS,
      duration: DURATION,
    },
  },
  thresholds: {
    // Aggregate: weighted by mix → P95 should still be sub-second-ish
    // because cheap endpoints dominate. The /api/ask/stream subset has its
    // own threshold below.
    http_req_duration: ['p(95)<3000', 'p(99)<8000'],
    http_req_failed: ['rate<0.02'],
    'http_req_duration{endpoint:/api/daily}': ['p(95)<500'],
    'http_req_duration{endpoint:/phase/api/companies}': ['p(95)<800'],
    'http_req_duration{endpoint:/api/universality/classes}': ['p(95)<800'],
    'http_req_duration{endpoint:/api/ask/stream}': ['p(95)<8000'],
    checks: ['rate>0.97'],
  },
  userAgent: 'structural-isomorphism-k6-loadtest/1.0 (w14-b mixed)',
};

function rollWeighted() {
  const r = Math.random();
  if (r < 0.60) return 'daily';
  if (r < 0.80) return 'companies';
  if (r < 0.95) return 'universality';
  return 'ask';
}

export default function () {
  const choice = rollWeighted();
  if (choice === 'daily') {
    const res = http.get(`${BASE_URL}/api/daily`, {
      tags: { endpoint: '/api/daily' },
    });
    check(res, { 'daily 200': (r) => r.status === 200 });
  } else if (choice === 'companies') {
    const res = http.get(`${BASE_URL}/phase/api/companies`, {
      tags: { endpoint: '/phase/api/companies' },
    });
    check(res, { 'companies 200': (r) => r.status === 200 });
  } else if (choice === 'universality') {
    const cid = CLASS_IDS[Math.floor(Math.random() * CLASS_IDS.length)];
    const res = http.get(`${BASE_URL}/api/universality/classes`, {
      tags: { endpoint: '/api/universality/classes' },
    });
    check(res, { 'universality list 200/404': (r) => r.status === 200 || r.status === 404 });
    const res2 = http.get(`${BASE_URL}/api/universality/classes/${cid}`, {
      tags: { endpoint: '/api/universality/classes/:id' },
    });
    check(res2, { 'universality detail 200/404': (r) => r.status === 200 || r.status === 404 });
  } else {
    // ask: expensive, only 5 %
    const q = queries[Math.floor(Math.random() * queries.length)];
    const res = http.post(
      `${BASE_URL}/api/ask/stream`,
      JSON.stringify({ query: q }),
      {
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        timeout: '60s',
        tags: { endpoint: '/api/ask/stream' },
      }
    );
    check(res, { 'ask 200': (r) => r.status === 200 });
  }
  sleep(Math.random() * 1.5 + 0.3);  // 0.3–1.8 s think time
}

export function handleSummary(data) {
  const m = data.metrics;
  const summary = {
    scenario: 'mixed_realistic',
    base_url: BASE_URL,
    vus: VUS,
    duration: DURATION,
    aggregate: {
      p50_ms: m.http_req_duration?.values?.med?.toFixed(1),
      p95_ms: m.http_req_duration?.values?.['p(95)']?.toFixed(1),
      p99_ms: m.http_req_duration?.values?.['p(99)']?.toFixed(1),
      error_rate: m.http_req_failed?.values?.rate?.toFixed(4),
      rps: m.http_reqs?.values?.rate?.toFixed(2),
    },
  };
  return {
    stdout: '\n=== mixed_realistic summary ===\n' + JSON.stringify(summary, null, 2) + '\n',
    'tests/load/results/mixed_realistic.json': JSON.stringify(summary, null, 2),
  };
}
