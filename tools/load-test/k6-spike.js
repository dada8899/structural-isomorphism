// HN-launch load test (k6 variant) — for users who prefer k6 over locust.
// Same target SLOs as locustfile.py.
//
// Install: brew install k6
// Run:
//     k6 run -e HOST=https://beta.structural.bytedance.city tools/load-test/k6-spike.js
//
// CI mode (writes JSON for downstream parsing):
//     k6 run --out json=tools/load-test/results/k6-$(date +%s).json tools/load-test/k6-spike.js
//
// The 3 stages model:
//   stage 1: 50 VUs × 10 min   — sustained, expect p95 < 800 ms
//   stage 2: 100 VUs × 5 min   — sustained, expect p95 < 1500 ms
//   stage 3: 200 VUs × 60 s    — spike, expect no 5xx storm + recovery
//
// k6 thresholds will EXIT NON-ZERO if SLOs blown.

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const HOST = __ENV.HOST || 'https://beta.structural.bytedance.city';
const PHASE_HOST = __ENV.PHASE_HOST || 'https://phase.bytedance.city';

const errorRate = new Rate('hn_5xx_rate');
const searchLatency = new Trend('search_latency');
const detailLatency = new Trend('detail_latency');

const SEARCH_QUERIES = [
  'bank runs',
  'neural avalanches',
  'wildfires',
  'DeFi liquidations',
  'GitHub stars',
  'earthquake aftershocks',
  'epidemic spread',
  'social cascades',
  'power grid failure',
  'citation networks',
  'asdf123',
  'phase transition',
  'self-organized criticality',
  'Ising model',
  'Sornette dragon king',
  'Plenz avalanche',
];

const TICKERS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'JPM'];

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

export const options = {
  stages: [
    { duration: '30s', target: 50 },     // warmup
    { duration: '10m', target: 50 },     // SLO check #1
    { duration: '1m',  target: 100 },    // ramp
    { duration: '5m',  target: 100 },    // SLO check #2
    { duration: '20s', target: 200 },    // spike
    { duration: '60s', target: 200 },    // spike sustained
    { duration: '20s', target: 0 },      // drain
  ],
  thresholds: {
    'http_req_failed':         ['rate<0.005'],         // < 0.5% total
    'http_req_duration{type:search}':  ['p(95)<1500'], // search p95 < 1.5s
    'http_req_duration{type:detail}':  ['p(95)<2000'], // detail p95 < 2.0s
    'http_req_duration{type:static}':  ['p(95)<500'],  // static p95 < 0.5s
    'hn_5xx_rate':             ['rate<0.005'],
  },
};

export default function () {
  group('landing', () => {
    const r = http.get(`${HOST}/`, { tags: { type: 'static' } });
    check(r, { '200': (resp) => resp.status === 200 });
    errorRate.add(r.status >= 500);
  });

  sleep(Math.random() * 3 + 2);

  group('search', () => {
    const q = encodeURIComponent(pick(SEARCH_QUERIES));
    const r = http.get(`${HOST}/api/search?q=${q}`, { tags: { type: 'search' } });
    check(r, { 'search 2xx or 4xx (not 5xx)': (resp) => resp.status < 500 });
    errorRate.add(r.status >= 500);
    searchLatency.add(r.timings.duration);
  });

  sleep(Math.random() * 4 + 2);

  if (Math.random() < 0.3) {
    group('phenomenon_detail', () => {
      const pid = pick(['bank-runs', 'neural-avalanches', 'wildfires', 'github-stars']);
      const r = http.get(`${HOST}/api/phenomenon/${pid}`, { tags: { type: 'detail' } });
      check(r, { '< 500': (resp) => resp.status < 500 });
      errorRate.add(r.status >= 500);
      detailLatency.add(r.timings.duration);
    });
    sleep(Math.random() * 3 + 2);
  }

  if (Math.random() < 0.15) {
    group('phase_detector', () => {
      const t = pick(TICKERS);
      const r = http.get(`${PHASE_HOST}/api/phase/${t}`, { tags: { type: 'detail' } });
      check(r, { '< 500': (resp) => resp.status < 500 });
      errorRate.add(r.status >= 500);
    });
  }

  sleep(Math.random() * 4 + 1);
}

export function handleSummary(data) {
  const p95Search = data.metrics['http_req_duration{type:search}']?.values?.['p(95)'] ?? 0;
  const p95Detail = data.metrics['http_req_duration{type:detail}']?.values?.['p(95)'] ?? 0;
  const errPct = (data.metrics['http_req_failed']?.values?.rate ?? 0) * 100;

  const verdict = (errPct < 0.5 && p95Search < 1500 && p95Detail < 2000) ? 'PASS' : 'FAIL';
  const line = `\n[K6 VERDICT] ${verdict} | err%=${errPct.toFixed(3)} | ` +
               `p95_search=${p95Search.toFixed(0)}ms | p95_detail=${p95Detail.toFixed(0)}ms\n`;

  return {
    stdout: line,
    'tools/load-test/results/k6-summary.json': JSON.stringify(data, null, 2),
  };
}
