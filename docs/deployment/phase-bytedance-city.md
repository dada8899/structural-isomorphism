# Deployment: phase.bytedance.city (D1 Phase Detector)

Deployed 2026-05-13 (W4-D, v4 session #3).

## URLs

- Public site: <https://phase.bytedance.city/>
- API health:  <https://phase.bytedance.city/api/health>
- API stats:   <https://phase.bytedance.city/api/stats>
- API screener: <https://phase.bytedance.city/api/screener?limit=20>
- API company detail: <https://phase.bytedance.city/api/company/COIN>

## Architecture

```
Internet
   │ HTTPS (443)
   ▼
┌──────────────────────────────────────┐
│ Nginx (VPS 43.156.233.71)            │
│  server_name phase.bytedance.city    │
│  /etc/nginx/conf.d/phase.bytedance.city.conf
└─┬─────────────┬──────────────────────┘
  │ /api/*      │ /*
  ▼             ▼
127.0.0.1:8200  127.0.0.1:3210
FastAPI         Next.js 14.2.15 (App Router)
(uvicorn)       (next start prod)
  │
  ▼
SQLite
/root/Projects/structural-isomorphism-v4/v4/product/d1_phase_detector/d1.sqlite
(97 companies from structtuples_2026-05-13.jsonl)
```

## VPS paths

| Item | Path |
|---|---|
| Repo root | `/root/Projects/structural-isomorphism-v4/` |
| Python venv | `/root/Projects/structural-isomorphism-v4/.venv/` |
| API entry | `v4/product/d1_phase_detector/api/main.py` |
| Web entry | `web/phase-detector/` |
| SQLite DB | `v4/product/d1_phase_detector/d1.sqlite` |
| Source JSONL | `v4/product/d1_phase_detector/structtuples_2026-05-13.jsonl` |
| Nginx vhost | `/etc/nginx/conf.d/phase.bytedance.city.conf` |
| Cert (LE) | `/etc/letsencrypt/live/phase.bytedance.city/{fullchain,privkey}.pem` |

Note: this lives in `structural-isomorphism-v4/` rather than `structural-isomorphism/` because the latter contained a non-git legacy `phase/` directory from earlier work — kept it untouched, cloned fresh repo at the `-v4` suffix path to avoid destructive overwrite. CLAUDE.md path registry should be updated to point at the `-v4` suffix until the legacy dir is archived (separate cleanup).

## systemd units

`/etc/systemd/system/phase-detector-api.service`:

```ini
[Service]
User=root
WorkingDirectory=/root/Projects/structural-isomorphism-v4
Environment="DB_URL=sqlite:////root/Projects/structural-isomorphism-v4/v4/product/d1_phase_detector/d1.sqlite"
ExecStart=/root/Projects/structural-isomorphism-v4/.venv/bin/uvicorn v4.product.d1_phase_detector.api.main:app --host 127.0.0.1 --port 8200
Restart=on-failure
RestartSec=5
```

`/etc/systemd/system/phase-detector-web.service`:

```ini
[Service]
User=root
WorkingDirectory=/root/Projects/structural-isomorphism-v4/web/phase-detector
Environment="NODE_ENV=production"
Environment="PORT=3210"
Environment="NEXT_PUBLIC_API_BASE=https://phase.bytedance.city/api"
Environment="NEXT_PUBLIC_USE_MOCK=false"
Environment="PATH=/root/.nvm/versions/node/v22.22.0/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/root/.nvm/versions/node/v22.22.0/bin/node /root/Projects/structural-isomorphism-v4/web/phase-detector/node_modules/next/dist/bin/next start -p 3210
Restart=on-failure
RestartSec=5
```

Common ops:

```bash
systemctl status phase-detector-api phase-detector-web
systemctl restart phase-detector-api
journalctl -u phase-detector-api -f
```

## Port allocation

- 8200: FastAPI (uvicorn) — internal only, exposed via nginx /api/
- 3210: Next.js — internal only, exposed via nginx /
- Note: 3200 was already taken by `routify/apps/docs` (existing site), so phase-detector-web binds 3210 instead of 3200 as originally planned.

## Data refresh workflow

When `structtuples_*.jsonl` is regenerated (W3-A batch re-run):

```bash
# 1. push new JSONL to VPS
ssh root@43.156.233.71 'cd /root/Projects/structural-isomorphism-v4 && git pull origin main'

# 2. re-ingest into SQLite (idempotent UPSERT by ticker)
ssh root@43.156.233.71 'cd /root/Projects/structural-isomorphism-v4 && \
  .venv/bin/python v4/product/d1_phase_detector/scripts/ingest_to_postgres.py \
    v4/product/d1_phase_detector/structtuples_2026-05-13.jsonl \
    --db-url sqlite:////root/Projects/structural-isomorphism-v4/v4/product/d1_phase_detector/d1.sqlite'

# 3. restart API (picks up new DB rows since stateless reads)
ssh root@43.156.233.71 'systemctl restart phase-detector-api'

# 4. (optional) verify
curl -s https://phase.bytedance.city/api/stats | jq .total
```

For frontend code/asset changes:

```bash
ssh root@43.156.233.71 'cd /root/Projects/structural-isomorphism-v4 && git pull origin main && \
  cd web/phase-detector && export NVM_DIR=/root/.nvm && . $NVM_DIR/nvm.sh && \
  pnpm install && NEXT_PUBLIC_API_BASE=https://phase.bytedance.city/api NEXT_PUBLIC_USE_MOCK=false pnpm build && \
  systemctl restart phase-detector-web'
```

## SSL renewal

certbot auto-renew cron is installed by `certbot --nginx`. Cert valid until 2026-08-11. Renewal handled by certbot's `--nginx` integration; no manual action needed unless renewal fails.

Verify:

```bash
ssh root@43.156.233.71 'systemctl list-timers | grep certbot'
ssh root@43.156.233.71 'certbot certificates -d phase.bytedance.city'
```

## DNS

DNSPod A record:
- subdomain: `phase`
- domain: `bytedance.city`
- value: `43.156.233.71`
- type: A
- line: 默认
- RecordId: 2292899335 (created 2026-05-13 via tccli)

## Monitoring TODO

Per CLAUDE.md "项目 = 网站 + Monitor" rule, AI Monitor (`monitor.bytedance.city`) Projects card region must be updated to include phase.bytedance.city. This is a **cross-repo** change (in `~/Projects/ai-monitor/`) — out of scope for this PR. Open as follow-up:

- Add card to `ai-monitor/ai-monitor.py` Projects region:
  - name: D1 Phase Detector
  - url: <https://phase.bytedance.city/>
  - health check: GET /api/health → expect `{"status":"ok"}`

## Known gaps / follow-ups

1. **AI Monitor card not yet added** (cross-repo, see above)
2. **API is read-only** — no auth, no rate limiting. CORS is `*`. Fine for v4 demo, harden before public alpha.
3. **SQLite single-writer** — `re-ingest` while API serving works (UPSERT atomic per row), but parallel batch ingest from multiple processes will lock. For scale → move to Postgres (`jubendashi-postgres` container already exists, just point `DB_URL`).
4. **Legacy `/root/Projects/structural-isomorphism/`** untouched on VPS. Need user decision: archive vs delete. Path registry in CLAUDE.md still points there; update to `-v4` once decided.
5. **`tccli` 中文 RecordLine** — DNS record creation succeeded with `默认` after using SSH heredoc (avoids local-shell encoding issues).
