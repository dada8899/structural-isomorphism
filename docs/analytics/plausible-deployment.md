# Plausible Community Edition — VPS self-hosted deployment

> **Status (2026-05-13, W4-B G3)**: scaffold only. Plausible JS snippet is already
> wired into the site (`web/frontend/*.html` + `web/phase-detector/app/layout.tsx`)
> pointing at `plausible.bytedance.city`, which currently does **not** resolve.
> The browser will silently drop the `<script defer src="...">` load — zero user-
> visible impact — until DNS + container are stood up per this doc.
>
> Owner for actual deploy: W4-D (deploy session) or later ops sweep. **Do not run
> these steps as part of W4-B**; this file is the runbook.

---

## 1. Why self-host

- Plausible Cloud is $9/month for 10k pageviews. Cheap, but we already have a
  VPS with spare capacity.
- Self-hosted = full data ownership, no third-party tracking concerns, easier
  GDPR posture for European/EU traffic from outreach.
- Plausible CE is open-source (AGPL), feature-parity for our use case
  (pageviews, referrers, top pages, sources). What CE lacks vs Cloud: funnels,
  saved segments, multi-user team plans — none of which we need yet.

## 2. Prerequisites

| Item | Status / how |
|---|---|
| VPS reachable, root SSH | yes: `ssh root@43.156.233.71` |
| Docker + docker-compose | already installed (other projects use it) |
| Domain available | `plausible.bytedance.city` (need DNS A record, see §5) |
| Port 8000 free | check `ss -tlnp \| grep 8000` before deploy |
| Disk space | ~2 GB initial, grows ~1 MB / 100k pageviews |
| Memory | 2 GB headroom recommended (Postgres + ClickHouse + Plausible) |

## 3. docker-compose.yml

Save to `/root/plausible/docker-compose.yml`:

```yaml
version: "3.3"

services:
  plausible_db:
    image: postgres:16-alpine
    restart: always
    volumes:
      - db-data:/var/lib/postgresql/data
    environment:
      - POSTGRES_PASSWORD=__REPLACE_STRONG_RANDOM__

  plausible_events_db:
    image: clickhouse/clickhouse-server:24.3-alpine
    restart: always
    volumes:
      - event-data:/var/lib/clickhouse
      - event-logs:/var/log/clickhouse-server
      - ./clickhouse-config.xml:/etc/clickhouse-server/config.d/logging.xml:ro
      - ./clickhouse-user-config.xml:/etc/clickhouse-server/users.d/logging.xml:ro
    ulimits:
      nofile:
        soft: 262144
        hard: 262144

  plausible:
    image: ghcr.io/plausible/community-edition:v2.1.4
    restart: always
    command: sh -c "/entrypoint.sh db migrate && /entrypoint.sh run"
    depends_on:
      - plausible_db
      - plausible_events_db
    ports:
      - 127.0.0.1:8000:8000
    environment:
      - BASE_URL=https://plausible.bytedance.city
      - SECRET_KEY_BASE=__REPLACE_64_RANDOM_BYTES__
      - DATABASE_URL=postgres://postgres:__REPLACE_STRONG_RANDOM__@plausible_db:5432/plausible_db
      - CLICKHOUSE_DATABASE_URL=http://plausible_events_db:8123/plausible_events_db
      - DISABLE_REGISTRATION=invite_only

volumes:
  db-data:
  event-data:
  event-logs:
```

Generate secrets:

```bash
openssl rand -base64 48      # SECRET_KEY_BASE
openssl rand -base64 24      # POSTGRES_PASSWORD (substitute in BOTH places)
```

Plus the two ClickHouse logging configs (minimal, suppress noise):

`/root/plausible/clickhouse-config.xml`:
```xml
<clickhouse>
  <logger><level>warning</level><console>true</console></logger>
  <query_thread_log remove="remove"/>
  <query_log remove="remove"/>
  <text_log remove="remove"/>
  <trace_log remove="remove"/>
  <metric_log remove="remove"/>
  <asynchronous_metric_log remove="remove"/>
  <session_log remove="remove"/>
  <part_log remove="remove"/>
</clickhouse>
```

`/root/plausible/clickhouse-user-config.xml`:
```xml
<clickhouse>
  <profiles><default><log_queries>0</log_queries><log_query_threads>0</log_query_threads></default></profiles>
</clickhouse>
```

## 4. Bring up

```bash
cd /root/plausible
docker compose up -d
docker compose logs -f plausible       # watch for "Running PlausibleWeb.Endpoint"
curl -I http://127.0.0.1:8000          # should 200 / 302
```

## 5. DNS

DNSPod (manual or via tccli):

```bash
tccli dnspod CreateRecord --cli-unfold-argument \
  --Domain bytedance.city \
  --SubDomain plausible \
  --RecordType A \
  --RecordLine 默认 \
  --Value 43.156.233.71
```

Wait ~1 min, verify: `dig plausible.bytedance.city +short` → `43.156.233.71`.

## 6. nginx reverse proxy

Create `/etc/nginx/conf.d/plausible.conf`:

```nginx
server {
    listen 80;
    server_name plausible.bytedance.city;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name plausible.bytedance.city;

    ssl_certificate     /etc/letsencrypt/live/plausible.bytedance.city/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/plausible.bytedance.city/privkey.pem;

    # Plausible needs websocket support for the live dashboard
    proxy_http_version 1.1;
    proxy_set_header   Upgrade           $http_upgrade;
    proxy_set_header   Connection        "upgrade";
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

Test + reload:

```bash
nginx -t && systemctl reload nginx
```

## 7. SSL via certbot

```bash
certbot --nginx -d plausible.bytedance.city \
  --non-interactive --agree-tos -m riazward110@gmail.com
```

certbot auto-rewrites the conf to add the cert paths and `ssl_session_cache`,
`ssl_protocols TLSv1.2 TLSv1.3`, etc.

## 8. First-time setup

1. Browse to `https://plausible.bytedance.city/register`. Because we set
   `DISABLE_REGISTRATION=invite_only`, only the first user can register before
   it locks down.
2. Create the admin account (use a real email — needed for password reset).
3. Add site: `Sites → + Add a site` →
   - Domain: `structural.bytedance.city`
   - Timezone: `Asia/Shanghai`
   - Save.
4. Plausible shows the snippet. **Compare** with what we already shipped:
   ```html
   <script defer data-domain="structural.bytedance.city"
           src="https://plausible.bytedance.city/js/script.js"></script>
   ```
   Should match. If Plausible shows a different `data-domain` casing, update
   the site config in Plausible, not the HTML.
5. Add second site for `phase.bytedance.city` (when that subdomain ships).

## 9. Verify

```bash
curl -I https://plausible.bytedance.city/js/script.js   # expect 200
curl -A 'Mozilla/5.0' https://structural.bytedance.city/   # warm a page
# wait ~10 s, check dashboard → "Realtime"
```

Send 1-2 page views from a different network / phone to confirm capture.

## 10. Backups

```bash
# nightly cron, /etc/cron.d/plausible-backup
0 3 * * * root cd /root/plausible && docker compose exec -T plausible_db \
  pg_dump -U postgres plausible_db | gzip > /root/backups/plausible-pg-$(date +\%F).sql.gz
```

ClickHouse events DB is replayable from Postgres in a pinch; don't bother
backing it up unless we grow past ~1M events.

## 11. Upgrades

```bash
cd /root/plausible
docker compose pull
docker compose up -d
```

Plausible CE follows semver; minor versions are non-breaking. Check the release
notes for major bumps (rare).

## 12. Cost

- VPS: already paid for.
- Domain: already paid for.
- Disk: negligible until ~1M events.
- **Marginal cost: $0/month.**

## 13. Failure modes / rollback

- If Plausible container OOMs: bump VPS or `docker compose down plausible` and
  go back to nginx access log analytics (`scripts/analytics/parse_nginx_logs.py`).
- If we want to migrate to Plausible Cloud later: export Postgres data via
  Plausible's CSV export, sign up on plausible.io, import. Zero data loss.
- The site snippet is harmless if Plausible is down — `defer` + non-blocking +
  silent DNS fail.

## 14. Privacy disclosure

We've already committed `docs/privacy-policy.md`. Plausible CE is cookieless
and doesn't store IPs, so no additional disclosure is needed once deployed.
GDPR posture: lawful basis = legitimate interest (low-risk pseudonymous
analytics), no consent banner required per EDPB guidance for cookieless
analytics.
