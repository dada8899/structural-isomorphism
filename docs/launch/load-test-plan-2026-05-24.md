# Load test plan + procedure — 2026-05-24

**Unblocks**: HN readiness § 1 "(blocker) Load test passed — site stays up at
50 RPS for 10 min".

**Scripts**:
- `tools/load-test/locustfile.py` — Python / Locust (preferred for CI)
- `tools/load-test/k6-spike.js` — Go / k6 (preferred for ad-hoc spike testing)

**Run against**: prod (`beta.structural.bytedance.city` + `phase.bytedance.city`).
Staging is not representative — VPS capacity is the variable we are measuring.

---

## SLOs

Pass = ALL of:

| Metric | Target | Why |
|---|---|---|
| Sustained 50 RPS × 10 min | p95 < 800 ms; 5xx < 0.5% | HN front-page sustained traffic floor |
| Spike 100 RPS × 5 min | p95 < 1500 ms; 5xx < 0.5% | HN front-page peak (rank 1–5) |
| Spike 200 RPS × 60 s | no full crash; recovery within 60 s | "we just got front-paged" surge |
| Phase detector parallel load | p95 < 2000 ms; 5xx < 1% | Cross-product spillover |

Soft targets (informational, not blockers):

| Metric | Target |
|---|---|
| CPU peak | < 80% of available cores |
| Memory peak | < 75% of 32 GB |
| Nginx connection count | < 8192 |
| Postgres active connections | < 80% of pool size (40 default) |

---

## Pre-test checklist

```bash
# 1. Notify in #ops Slack: "Load test starting at HH:MM, lasts ~30 min"
#    (Don't surprise anyone watching the AI Monitor dashboard.)

# 2. SSH into VPS, start tail of structured logs in a second pane
ssh vps
journalctl -u structural-backend -f -o cat | tee /tmp/load-test-backend.log

# 3. In a third pane, watch resources
ssh vps "watch -n 2 'top -bn1 | head -20; echo ---; ss -s; echo ---; \
  free -h; echo ---; nproc'"

# 4. Confirm baseline (no real users in trouble right now)
curl -w "\nstatus=%{http_code} ttfb=%{time_starttransfer}\n" \
  -s -o /dev/null https://beta.structural.bytedance.city/

# 5. Warm CDN
for path in / /api/search?q=test /api/discoveries /methodology; do
  curl -s -o /dev/null https://beta.structural.bytedance.city$path
done
```

---

## Test sequence (≈ 30 min total)

### Stage 1 — Sustained 50 RPS × 10 min (the blocker run)

```bash
pip install locust==2.32.4
mkdir -p tools/load-test/results

locust -f tools/load-test/locustfile.py \
  --host=https://beta.structural.bytedance.city \
  --users 50 --spawn-rate 5 --run-time 10m \
  --headless \
  --csv=tools/load-test/results/stage1-$(date +%Y%m%d-%H%M%S) \
  --html=tools/load-test/results/stage1-report.html
```

Pass criteria:
- Final summary line: `[LOAD-TEST VERDICT] PASS`
- `stage1-*_stats.csv`: median < 400 ms, p95 < 800 ms
- VPS top: load average < 4.0 (16 cores → 25% load)
- Postgres: `pg_stat_activity` rows < 30

If FAIL → fix and re-run. Common causes:

| Symptom | Likely cause | Fix |
|---|---|---|
| 5xx > 0.5% on `/api/search` | uvicorn worker count too low | `WEB_CONCURRENCY=8` in systemd unit, restart |
| p95 spikes at 4 min mark | embedding cache cold | preload `np.load` on startup |
| 502 from nginx | backend timeout | bump `proxy_read_timeout` to 30s |
| db connection exhaustion | no connection pooling | `pgbouncer` or sqlalchemy pool_size=20 |

### Stage 2 — Spike 100 RPS × 5 min

```bash
locust -f tools/load-test/locustfile.py \
  --host=https://beta.structural.bytedance.city \
  --users 100 --spawn-rate 20 --run-time 5m \
  --headless \
  --csv=tools/load-test/results/stage2-$(date +%Y%m%d-%H%M%S)
```

Pass criteria:
- 5xx < 0.5%
- p95 < 1500 ms (relaxed vs stage 1)
- VPS load average < 8.0

### Stage 3 — Burst 200 RPS × 60 s

This is the "we just hit HN front page top 3" scenario.

```bash
# Use k6 here — better burst control than locust
brew install k6
k6 run -e HOST=https://beta.structural.bytedance.city \
  tools/load-test/k6-spike.js
```

Pass criteria:
- No 5+ second continuous unavailability
- Recovery: after burst ends, p95 returns to < 800 ms within 60 s
- nginx error log: no "worker_connections are not enough" lines

If FAIL on Stage 3 only: launch IS still go, but pre-stage a manual `tccli`
to upgrade VPS specs *during* the launch if `/admin/health` p95 > 2 s for
more than 90 s.

### Stage 4 — Phase detector cross-product

In a second terminal, while Stage 1 is running, also run:

```bash
PHASE_DETECTOR_HOST=https://phase.bytedance.city \
locust -f tools/load-test/locustfile.py \
  --host=https://phase.bytedance.city \
  --users 20 --spawn-rate 5 --run-time 10m \
  --headless \
  --csv=tools/load-test/results/stage4-phase-$(date +%Y%m%d-%H%M%S)
```

This tests that the marketing site and the phase detector — which share the same
VPS — don't starve each other.

---

## Post-test analysis

```bash
# 1. Aggregate the CSVs
python3 - <<'PY'
import csv, glob
for f in sorted(glob.glob('tools/load-test/results/stage*_stats.csv')):
    rows = list(csv.DictReader(open(f)))
    agg = next((r for r in rows if r['Name'] == 'Aggregated'), None)
    if not agg:
        continue
    print(f"{f}")
    print(f"  requests={agg['Request Count']} failures={agg['Failure Count']} "
          f"median={agg['Median Response Time']}ms p95={agg['95%']}ms")
PY

# 2. Check backend log for surprises
ssh vps "grep -E 'ERROR|CRITICAL|Traceback' /tmp/load-test-backend.log | head -50"

# 3. Plausible recheck — did event firing keep up?
# Open https://plausible.io/beta.structural.bytedance.city
# Verify Page Views graph shows the load test as a visible spike, not flatlined
# (flatlined → Plausible script rate-limited; need to debounce client-side)

# 4. Snapshot the VPS metrics graphs
# (manual: take screenshot of monitor.bytedance.city for the test window)
```

---

## Repeat schedule

- T-7 days before launch: full 4-stage run (catch capacity drift)
- T-1 day before launch: Stage 1 + 2 only (smoke)
- T+24 h after launch: Stage 1 only (verify real traffic + load test sum
  did not silently degrade the prod baseline)

If we add any non-trivial new endpoint between launch attempts, re-run the
full sequence.

---

## Known capacity headroom (current VPS, 2026-05-24)

Best-effort estimate before running:

| Capacity item | Current | Headroom @ 100 RPS |
|---|---|---|
| nginx worker_connections | 8192 | 80× expected concurrent connections |
| uvicorn workers | 4 (default) | tight — bump to 8 before launch |
| Postgres max_connections | 100 | OK if pool_size ≤ 30 |
| VPS CPU | 16 cores | 50 RPS ≈ 30% util (verified informally) |
| VPS RAM | 32 GB | embedding cache ≈ 1.2 GB; abundant |
| Outbound bandwidth | 1 Gbps shared | demo.gif × 100 RPS = 500 Mbps spike risk → CDN required |

Action items derived from this table (already filed in HN readiness § 1):

- [ ] Bump uvicorn `WEB_CONCURRENCY=8` before launch
- [ ] Verify CDN cache `Cache-Control: public, max-age=300` on HTML
- [ ] Verify `demo.gif` is served from CDN, not origin
- [ ] Confirm Postgres pool_size = 20 (not default 5)
- [ ] Stop all non-essential cron during launch window (per HN readiness § 4)

---

## Verdict log

A green stage-1 line in `tools/load-test/results/` is the artifact that
unblocks HN readiness § 1. Drop the verdict text into the readiness doc when
the test passes:

```
[2026-MM-DD HH:MM] Stage 1 PASS. Median=312ms p95=687ms 5xx=0.04%. → unblock § 1 LOAD-TEST.
```
