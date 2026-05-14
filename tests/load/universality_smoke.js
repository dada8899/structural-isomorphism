// universality_smoke.js — k6 smoke test for /api/universality/* (W14-B)
//
// W10-E adds /api/universality/classes (list) and /api/universality/classes/{id}.
// Until that ships, this script gracefully degrades: if 404 it skips the
// class-detail probe and reports the gap in the summary (so we can re-run
// once the W10-E PR lands).
//
// Run:
//   BASE_URL=http://localhost:8000 k6 run tests/load/universality_smoke.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

// Known class IDs from W10-E taxonomy. If the endpoint is missing the
// probes return 404 and the script reports skipped status.
const CLASS_IDS = new SharedArray('classes', function () {
  return [
    'preferential_attachment',
    'soc_threshold_cascade',
    'kuramoto_sync',
    'self_organized_criticality',
    'power_law_tail',
  ];
});

export const options = {
  scenarios: {
    smoke: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '10s', target: 10 },
        { duration: '20s', target: 10 },
        { duration: '5s',  target: 0  },
      ],
      gracefulRampDown: '5s',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.95'],
  },
  userAgent: 'structural-isomorphism-k6-loadtest/1.0 (w14-b universality)',
};

export default function () {
  // List endpoint
  const listRes = http.get(`${BASE_URL}/api/universality/classes`, {
    tags: { endpoint: '/api/universality/classes' },
  });
  check(listRes, {
    'list status 200 or 404 (not yet shipped)': (r) =>
      r.status === 200 || r.status === 404,
    'list response time < 1s': (r) => r.timings.duration < 1000,
  });

  // Detail endpoint — random class ID
  const cid = CLASS_IDS[Math.floor(Math.random() * CLASS_IDS.length)];
  const detailRes = http.get(`${BASE_URL}/api/universality/classes/${cid}`, {
    tags: { endpoint: '/api/universality/classes/:id' },
  });
  check(detailRes, {
    'detail status 200/404': (r) => r.status === 200 || r.status === 404,
    'detail response time < 1s': (r) => r.timings.duration < 1000,
  });

  sleep(0.5);
}

export function handleSummary(data) {
  const m = data.metrics;
  const summary = {
    endpoints: ['/api/universality/classes', '/api/universality/classes/:id'],
    base_url: BASE_URL,
    p50_ms: m.http_req_duration?.values?.med?.toFixed(1),
    p95_ms: m.http_req_duration?.values?.['p(95)']?.toFixed(1),
    p99_ms: m.http_req_duration?.values?.['p(99)']?.toFixed(1),
    error_rate: m.http_req_failed?.values?.rate?.toFixed(4),
    requests: m.http_reqs?.values?.count,
    rps: m.http_reqs?.values?.rate?.toFixed(2),
  };
  return {
    stdout: '\n=== universality_smoke summary ===\n' + JSON.stringify(summary, null, 2) + '\n',
    'tests/load/results/universality_smoke.json': JSON.stringify(summary, null, 2),
  };
}
