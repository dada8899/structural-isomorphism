// phases_smoke.js — k6 smoke test for cheap GET endpoint (W14-B, session #10)
//
// Install k6:
//   macOS:  brew install k6
//   Linux:  sudo gpg -k && sudo gpg --no-default-keyring \
//             --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
//             --keyserver hkp://keyserver.ubuntu.com:80 \
//             --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69 && \
//           echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] \
//             https://dl.k6.io/deb stable main" | \
//             sudo tee /etc/apt/sources.list.d/k6.list && \
//           sudo apt-get update && sudo apt-get install k6
//   Docker: docker run -i --rm grafana/k6 run - <phases_smoke.js
//
// Run:
//   BASE_URL=http://localhost:8000 k6 run tests/load/phases_smoke.js
//   BASE_URL=https://beta.structural.bytedance.city k6 run tests/load/phases_smoke.js
//
// NOTE on endpoint choice: The W14 task spec referenced "/api/phases" but the
// canonical cheap GET on the live backend is /api/daily (returns the daily
// rotating cross-domain analogy — pre-computed, no LLM, < 100 ms median).
// This file targets /api/daily; if /api/phases is added later, swap the path.

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const ENDPOINT = __ENV.PHASES_PATH || '/api/daily';

export const options = {
  scenarios: {
    smoke: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '10s', target: 10 },  // ramp up
        { duration: '20s', target: 10 },  // hold
        { duration: '5s',  target: 0  },  // ramp down
      ],
      gracefulRampDown: '5s',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
  },
  // Be a polite user-agent on shared infrastructure.
  userAgent: 'structural-isomorphism-k6-loadtest/1.0 (w14-b)',
};

export default function () {
  const res = http.get(`${BASE_URL}${ENDPOINT}`, {
    tags: { endpoint: ENDPOINT },
  });
  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 1s': (r) => r.timings.duration < 1000,
    'has json body': (r) => r.body && r.body.length > 0,
  });
  sleep(0.5);
}

export function handleSummary(data) {
  const m = data.metrics;
  const summary = {
    endpoint: ENDPOINT,
    base_url: BASE_URL,
    p50_ms: m.http_req_duration?.values?.med?.toFixed(1),
    p95_ms: m.http_req_duration?.values?.['p(95)']?.toFixed(1),
    p99_ms: m.http_req_duration?.values?.['p(99)']?.toFixed(1),
    error_rate: m.http_req_failed?.values?.rate?.toFixed(4),
    requests: m.http_reqs?.values?.count,
    rps: m.http_reqs?.values?.rate?.toFixed(2),
  };
  return {
    stdout: '\n=== phases_smoke summary ===\n' + JSON.stringify(summary, null, 2) + '\n',
    'tests/load/results/phases_smoke.json': JSON.stringify(summary, null, 2),
  };
}
