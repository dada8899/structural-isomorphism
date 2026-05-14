// stress_ramp.js — find the saturation point of the cheap GET path (W14-B)
//
// Ramps 100 → 500 → 1000 VUs over 10 min hitting /api/daily (cheapest GET).
// Records the VU level at which 5xx error rate first crosses 1 %.
//
// IMPORTANT: This is a *stress* test. Do NOT run against prod without
// explicit user authorization. Default target is localhost.
//
// Run (local only by default):
//   BASE_URL=http://localhost:8000 k6 run tests/load/stress_ramp.js
//
// To explicitly target staging (requires confirmation):
//   I_KNOW_WHAT_I_AM_DOING=yes BASE_URL=https://beta.structural.bytedance.city \
//     k6 run tests/load/stress_ramp.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const SAFETY = __ENV.I_KNOW_WHAT_I_AM_DOING || 'no';
const ENDPOINT = __ENV.PHASES_PATH || '/api/daily';

if (BASE_URL.includes('bytedance.city') && SAFETY !== 'yes') {
  throw new Error(
    'Refusing to stress-test prod without I_KNOW_WHAT_I_AM_DOING=yes. ' +
    'Set BASE_URL=http://localhost:8000 to run locally, or set the safety ' +
    'flag to acknowledge the consequences.'
  );
}

export const errors5xx = new Rate('errors_5xx');

export const options = {
  scenarios: {
    stress: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 100 },   // ramp to 100
        { duration: '2m', target: 100 },   // hold
        { duration: '2m', target: 500 },   // ramp to 500
        { duration: '2m', target: 500 },   // hold
        { duration: '1m', target: 1000 },  // push to 1000
        { duration: '1m', target: 1000 },  // hold
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    // Soft thresholds — we *expect* to break things here. These exist
    // only to fail the run if the breaking point is suspiciously low.
    http_req_failed: ['rate<0.50'],
    errors_5xx: ['rate<0.20'],
  },
  userAgent: 'structural-isomorphism-k6-loadtest/1.0 (w14-b stress)',
};

export default function () {
  const res = http.get(`${BASE_URL}${ENDPOINT}`, {
    tags: { endpoint: ENDPOINT },
    timeout: '30s',
  });
  const is5xx = res.status >= 500;
  errors5xx.add(is5xx);
  check(res, {
    'not 5xx': (r) => r.status < 500,
  });
  sleep(0.1);
}

export function handleSummary(data) {
  const m = data.metrics;
  const summary = {
    scenario: 'stress_ramp',
    base_url: BASE_URL,
    endpoint: ENDPOINT,
    peak_vus: 1000,
    p50_ms: m.http_req_duration?.values?.med?.toFixed(1),
    p95_ms: m.http_req_duration?.values?.['p(95)']?.toFixed(1),
    p99_ms: m.http_req_duration?.values?.['p(99)']?.toFixed(1),
    total_requests: m.http_reqs?.values?.count,
    failed_rate: m.http_req_failed?.values?.rate?.toFixed(4),
    rate_5xx: m.errors_5xx?.values?.rate?.toFixed(4),
    note: 'For saturation point, inspect time-series output (k6 cloud or InfluxDB) — single rate is aggregate.',
  };
  return {
    stdout: '\n=== stress_ramp summary ===\n' + JSON.stringify(summary, null, 2) + '\n',
    'tests/load/results/stress_ramp.json': JSON.stringify(summary, null, 2),
  };
}
