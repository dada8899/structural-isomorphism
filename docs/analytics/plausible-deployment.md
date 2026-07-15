# Plausible Community Edition deployment runbook

**Runbook version:** 1.3.0

**Runbook date:** 2026-07-15

**Current state (2026-07-15): NOT PUBLICLY DEPLOYED — awaiting application PR merge.**

This is the production authority for `plausible.bytedance.city`. It describes
the intended deployment; it is not a deployment receipt. Keep DNS absent until
the application release that removes every legacy remote tracker reference is
live on both products.

## 1. Locked upstream baseline

| Artifact | Required value |
|---|---|
| Community Edition repository | `https://github.com/plausible/community-edition` |
| CE branch/tag | `v3.2.1` |
| CE repository commit | `ec6c4da776547516d8f48159ce1a704df4f475ad` |
| Official compose | `https://raw.githubusercontent.com/plausible/community-edition/v3.2.1/compose.yml` |
| Analytics release commit | `e4f5a87a5570bd61605217e7ceb376636db8eddb` |
| Application image | `ghcr.io/plausible/community-edition:v3.2.1` |
| OCI index digest | `sha256:33e60bfb40f2df5da00f8753b76fad04f67dba3abe6d73eb516e440e3fb62985` |
| linux/amd64 manifest digest | `sha256:7450d9df4bfce160541d65bdba6bd4bcdd9a6db07f13dde91060705fa242c650` |
| Server directory | `/root/plausible-ce` |
| Only host binding | `127.0.0.1:8800:8000` |

Do not copy a compose file from an older deployment and do not use a floating
tag. The official `v3.2.1` compose also owns the compatible Postgres,
ClickHouse, four named-volume, health-check, and low-resource configuration.
Local changes belong only in `.env` and `compose.override.yml`.

## 2. Hard gates and zero-public-window order

Execute these gates in order. A failed gate stops the deployment.

1. Merge and deploy the application PR to Beta and Phase.
2. Prove that product code contains zero legacy remote tracker references and
   that `plausible.bytedance.city` still returns DNS `NXDOMAIN`.
3. Install CE at `/root/plausible-ce`, bind it only to loopback, and create the
   first administrator plus both sites over an SSH tunnel.
4. Replace bootstrap settings with the final public `BASE_URL`, close public
   registration, restart, and prove loopback readiness.
5. Install and locally validate the HTTP-only ACME challenge server while DNS
   is still absent. All other HTTP paths return `503` at this stage.
6. Create the DNS record, wait for authoritative and public resolvers, then
   issue the certificate with the already-working HTTP challenge path.
7. Install the final TLS proxy, including the exact legacy tracker deny and
   event privacy controls, and only then make the dashboard/event endpoint
   publicly reachable.
8. Run real Beta and Phase ingestion acceptance and fill in the deployment
   receipt. HTTP `202` alone is not acceptance.

The application-first order prevents an accidental DNS change from activating
old browser tracker code. The HTTP-only ACME staging server prevents a gap in
which DNS exists but a half-configured dashboard is exposed.

## 3. Preflight: application and DNS must be safe

Run in the exact application merge SHA that is deployed to both products:

```bash
git rev-parse HEAD
rg -n 'plausible\.bytedance\.city/js/script\.js|plausible\.io/js/script\.js' \
  web/frontend web/phase-detector
```

The `rg` command must exit `1` with no matches. Then verify the public hostname
does not resolve:

```bash
dig +short plausible.bytedance.city A
dig +short plausible.bytedance.city AAAA
```

Both commands must print nothing. Record the deployed application SHA and the
two DNS observations before continuing.

## 4. Install the pinned CE tree

Run as root on the deployment server. Do not print secret values to the
terminal, logs, shell tracing, or the deployment receipt.

```bash
umask 077
git clone --branch v3.2.1 --single-branch \
  https://github.com/plausible/community-edition /root/plausible-ce
cd /root/plausible-ce
test "$(git rev-parse HEAD)" = ec6c4da776547516d8f48159ce1a704df4f475ad
git diff --exit-code
test -z "$(git status --porcelain)"
chmod 0700 /root/plausible-ce
```

Generate secrets directly into the root-only environment file. The generated
values below are examples of generation procedures, not fixed credentials:

```bash
cd /root/plausible-ce
umask 077
secret_key_base="$(openssl rand -base64 64 | tr -d '\n')"
totp_vault_key="$(openssl rand -base64 32 | tr -d '\n')"
postgres_password="$(openssl rand -hex 32)"
{
  printf '%s\n' 'COMPOSE_PROJECT_NAME=plausible-ce'
  printf '%s\n' 'BASE_URL=http://127.0.0.1:8800'
  printf 'SECRET_KEY_BASE=%s\n' "$secret_key_base"
  printf 'TOTP_VAULT_KEY=%s\n' "$totp_vault_key"
  printf 'POSTGRES_PASSWORD=%s\n' "$postgres_password"
  printf '%s\n' 'DISABLE_REGISTRATION=false'
  printf '%s\n' 'ENABLE_EMAIL_VERIFICATION=false'
  printf '%s\n' 'HTTP_PORT=8000'
} > .env
unset secret_key_base totp_vault_key postgres_password
chmod 0600 .env
```

Create root-only `compose.override.yml`. The digest pins the OCI index; the
linux/amd64 manifest is independently verified below.

```yaml
services:
  plausible_db:
    environment:
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

  plausible:
    image: "ghcr.io/plausible/community-edition:v3.2.1@sha256:33e60bfb40f2df5da00f8753b76fad04f67dba3abe6d73eb516e440e3fb62985"
    ports:
      - "127.0.0.1:8800:8000"
    environment:
      BASE_URL: "${BASE_URL:?BASE_URL is required}"
      SECRET_KEY_BASE: "${SECRET_KEY_BASE:?SECRET_KEY_BASE is required}"
      TOTP_VAULT_KEY: "${TOTP_VAULT_KEY:?TOTP_VAULT_KEY is required}"
      DISABLE_REGISTRATION: "${DISABLE_REGISTRATION:?DISABLE_REGISTRATION is required}"
      ENABLE_EMAIL_VERIFICATION: "${ENABLE_EMAIL_VERIFICATION:?ENABLE_EMAIL_VERIFICATION is required}"
      HTTP_PORT: "${HTTP_PORT:?HTTP_PORT is required}"
      DATABASE_URL: "postgres://postgres:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@plausible_db:5432/plausible_db"
```

```bash
chmod 0600 compose.override.yml
docker compose config --quiet
docker compose pull
docker image inspect \
  ghcr.io/plausible/community-edition:v3.2.1@sha256:33e60bfb40f2df5da00f8753b76fad04f67dba3abe6d73eb516e440e3fb62985 \
  --format '{{json .RepoDigests}}'
docker buildx imagetools inspect \
  ghcr.io/plausible/community-edition:v3.2.1@sha256:33e60bfb40f2df5da00f8753b76fad04f67dba3abe6d73eb516e440e3fb62985
```

The output must bind the index digest above and show the linux/amd64 manifest
digest `sha256:7450d9df4bfce160541d65bdba6bd4bcdd9a6db07f13dde91060705fa242c650`.
Do not continue on an architecture or digest mismatch.

## 5. Loopback bootstrap and two-site initialization

```bash
cd /root/plausible-ce
docker compose up -d
docker compose ps
curl --fail --silent --show-error \
  http://127.0.0.1:8800/api/system/health/ready
ss -ltnp | rg '127\.0\.0\.1:8800'
```

There must be no `0.0.0.0:8800`, `[::]:8800`, Postgres, or ClickHouse host
listener. From an operator machine, open an SSH tunnel without changing DNS:

```bash
: "${DEPLOYMENT_HOST_ALIAS:?set the deployment host alias from the project registry}"
ssh -N -L 8800:127.0.0.1:8800 "$DEPLOYMENT_HOST_ALIAS"
```

Browse to `http://127.0.0.1:8800` and, while the service is loopback-only:

1. Create the first administrator using an operator-selected email and a
   password stored in the approved password manager. Do not record either in
   this repository or the deployment receipt.
2. Create site `beta.structural.bytedance.city` with timezone `Asia/Shanghai`.
3. Create site `phase.bytedance.city` with timezone `Asia/Shanghai`.
4. Confirm both sites are visible to the first administrator.

Now close registration and switch to the final URL by editing only `.env`:

```dotenv
BASE_URL=https://plausible.bytedance.city
DISABLE_REGISTRATION=true
```

```bash
set -euo pipefail
active_dir="${PLAUSIBLE_INITIAL_ACTIVE_DIR:-/root/plausible-ce}"
active_port="${PLAUSIBLE_INITIAL_ACTIVE_PORT:-8800}"
chmod 0600 "$active_dir/.env"
cd "$active_dir"
docker compose up -d --force-recreate plausible
curl --fail --silent --show-error \
  "http://127.0.0.1:$active_port/api/system/health/ready"

authority_file="${PLAUSIBLE_AUTHORITY_FILE:-/root/plausible-ce-authority.env}"
authority_state_dir="${PLAUSIBLE_AUTHORITY_STATE_DIR:-/root}"
authority_candidate="$(mktemp "$authority_state_dir/.plausible-ce-authority.XXXXXX")"
{
  printf '%s\n' 'PLAUSIBLE_AUTHORITY_PROTOCOL=plausible-ce-authority-v1'
  printf 'PLAUSIBLE_ACTIVE_DIR=%s\n' "$active_dir"
  printf '%s\n' 'PLAUSIBLE_ACTIVE_PROJECT=plausible-ce'
  printf 'PLAUSIBLE_ACTIVE_PORT=%s\n' "$active_port"
  printf '%s\n' \
    'PLAUSIBLE_ACTIVE_SOURCE_COMMIT=ec6c4da776547516d8f48159ce1a704df4f475ad'
} > "$authority_candidate"
chown root:root "$authority_candidate"
chmod 0600 "$authority_candidate"
mv -f "$authority_candidate" "$authority_file"
```

Keep the service loopback-only. DNS must still be `NXDOMAIN`. The root-owned
authority file above is the single source for every future backup, promotion,
rollback, and upgrade; filesystem directory names alone do not confer active
status.

## 6. Stage HTTP ACME before DNS

Create the ACME webroot and install an HTTP-only Nginx server. It intentionally
serves no dashboard and no event API. The canonical source, live target, and
reviewed transaction installer are fixed as follows:

- source: `/root/plausible-nginx-source/plausible-acme-http.conf`;
- target: `/etc/nginx/conf.d/plausible.bytedance.city.conf`;
- installer: `/root/scripts/install-nginx-privacy-vhost.sh`;
- transaction state and root-only rollback snapshot:
  `/var/lib/structural-isomorphism/nginx-privacy/`.

Create the source directory as `root:root 0700`, save the exact configuration
below as the named source file, and make that regular, non-symlink file
`root:root 0600`. The privacy-safe access format deliberately omits client IP,
host, URI, query, referrer, user agent, and request body while satisfying the
installer's reviewed vhost contract.

```bash
install -d -o root -g root -m 0755 /var/www/acme/.well-known/acme-challenge
```

```nginx
log_format plausible_acme_privacy
    '$request_method $status $body_bytes_sent $request_time '
    '$upstream_response_time $request_id';

server {
    listen 80;
    listen [::]:80;
    server_name plausible.bytedance.city;

    access_log /var/log/nginx/access.log plausible_acme_privacy;
    error_log /dev/null crit;
    add_header Referrer-Policy no-referrer always;
    proxy_hide_header Referrer-Policy;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/acme;
        default_type text/plain;
        try_files $uri =404;
    }

    location / {
        return 503;
    }
}
```

```bash
set -euo pipefail
umask 077
nginx_source_dir=/root/plausible-nginx-source
nginx_source="$nginx_source_dir/plausible-acme-http.conf"
nginx_target=/etc/nginx/conf.d/plausible.bytedance.city.conf
nginx_installer=/root/scripts/install-nginx-privacy-vhost.sh
nginx_backup_dir="$nginx_source_dir/backups"
install -d -o root -g root -m 0700 "$nginx_source_dir" "$nginx_backup_dir"
test -d "$nginx_source_dir" && test ! -L "$nginx_source_dir"
test -d "$nginx_backup_dir" && test ! -L "$nginx_backup_dir"
test "$(stat -c '%U:%G %a' "$nginx_source_dir")" = 'root:root 700'
test "$(stat -c '%U:%G %a' "$nginx_backup_dir")" = 'root:root 700'
test -f "$nginx_source" && test ! -L "$nginx_source"
chown root:root "$nginx_source"
chmod 0600 "$nginx_source"
test "$(stat -c '%U:%G %a' "$nginx_source")" = 'root:root 600'
test -x "$nginx_installer" && test ! -L "$nginx_installer"

stage_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "$nginx_backup_dir/pre-acme-$stage_stamp.conf"
test ! -L "$nginx_backup_dir/pre-acme-$stage_stamp.conf"
test ! -e "$nginx_backup_dir/pre-acme-$stage_stamp.absent"
test ! -L "$nginx_backup_dir/pre-acme-$stage_stamp.absent"
if test -e "$nginx_target" || test -L "$nginx_target"; then
  test -f "$nginx_target" && test ! -L "$nginx_target"
  install -o root -g root -m 0600 "$nginx_target" \
    "$nginx_backup_dir/pre-acme-$stage_stamp.conf"
  sha256sum "$nginx_backup_dir/pre-acme-$stage_stamp.conf"
else
  printf '%s\n' 'target_absent_before_acme=true' \
    > "$nginx_backup_dir/pre-acme-$stage_stamp.absent"
  chmod 0600 "$nginx_backup_dir/pre-acme-$stage_stamp.absent"
fi

bash "$nginx_installer" "$nginx_source" "$nginx_target" \
  plausible.bytedance.city plausible_acme_privacy
nginx -t
stage_http_status="$(curl -sS -o /dev/null -w '%{http_code}' \
  -H 'Host: plausible.bytedance.city' http://127.0.0.1/)"
test "$stage_http_status" = 503
printf 'stage_http_status=%s\n' "$stage_http_status"
```

The installer snapshots the source, keeps its journal and live rollback copy
root-only, atomically installs the target, runs `nginx -t`, reloads, validates
the effective vhost, and restores the old target on any failure. The separately
retained pre-stage backup records the before-state after the installer commits.
The local probe must return `503`. Only after that proof, create the DNS `A`
record using the deployment registry's current public address; do not copy an
address from this document:

```bash
: "${VPS_PUBLIC_IP:?set the current value from the project registry}"
tccli dnspod CreateRecord --cli-unfold-argument \
  --Domain bytedance.city --SubDomain plausible --RecordType A \
  --RecordLine '默认' --Value "$VPS_PUBLIC_IP"
unset VPS_PUBLIC_IP
```

Resolve the zone's authoritative nameservers through `1.1.1.1`, then require
every authoritative server plus both `1.1.1.1` and `8.8.8.8` to return exactly
the approved `A` value and no `AAAA` value. Any empty, duplicate, stale, or
unexpected answer stops the deployment:

```bash
set -euo pipefail
: "${VPS_PUBLIC_IP:?set the current value from the project registry}"
[[ "$VPS_PUBLIC_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]
IFS=. read -r ipv4_a ipv4_b ipv4_c ipv4_d <<EOF
$VPS_PUBLIC_IP
EOF
for octet in "$ipv4_a" "$ipv4_b" "$ipv4_c" "$ipv4_d"; do
  (( 10#$octet <= 255 ))
done
authoritative_ns="$(dig +short @1.1.1.1 bytedance.city NS \
  | sed 's/\.$//' | LC_ALL=C sort -u)"
test -n "$authoritative_ns"
while IFS= read -r resolver; do
  [[ "$resolver" =~ ^[A-Za-z0-9.-]+$ ]]
done <<EOF
$authoritative_ns
EOF

for resolver in $authoritative_ns 1.1.1.1 8.8.8.8; do
  ipv4_answers="$(dig +short "@$resolver" plausible.bytedance.city A)"
  test "$(printf '%s\n' "$ipv4_answers" | sed '/^$/d' \
    | wc -l | tr -d ' ')" = 1
  test "$ipv4_answers" = "$VPS_PUBLIC_IP"
  test -z "$(dig +short "@$resolver" plausible.bytedance.city AAAA)"
done
unset VPS_PUBLIC_IP authoritative_ns resolver ipv4_answers
unset ipv4_a ipv4_b ipv4_c ipv4_d octet
```

Then request the certificate using the already-tested webroot; select the ACME
contact at execution time rather than hardcoding it:

```bash
read -r -p 'ACME contact email: ' ACME_CONTACT
certbot certonly --webroot --webroot-path /var/www/acme \
  --domain plausible.bytedance.city --non-interactive --agree-tos \
  --email "$ACME_CONTACT"
unset ACME_CONTACT
```

Until the final TLS configuration passes `nginx -t`, the public HTTP root must
continue returning `503`.

## 7. Final Nginx privacy boundary

Install the final configuration only after the certificate exists. The exact
`/js/script.js` deny is a migration tripwire for the retired remote tracker.
Do not block the whole `/js/` tree: Plausible's dashboard may need its own
static JavaScript assets.

The canonical final source is
`/root/plausible-nginx-source/plausible-final-tls.conf`; the live target remains
`/etc/nginx/conf.d/plausible.bytedance.city.conf`. Save the exact configuration
below as a `root:root 0600` regular, non-symlink source file. The reviewed
installer from Section 6 is used wherever its stricter single-access-log
contract is compatible. This final vhost intentionally adds `access_log off`
inside the event and health locations, so that installer must reject it rather
than silently weaken its contract. The explicit fail-closed transaction after
the configuration therefore performs the final swap, validation, reload, and
rollback while retaining a root-only before-state.

```nginx
map $http_upgrade $plausible_connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    listen [::]:80;
    server_name plausible.bytedance.city;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/acme;
        default_type text/plain;
        try_files $uri =404;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name plausible.bytedance.city;

    ssl_certificate /etc/letsencrypt/live/plausible.bytedance.city/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/plausible.bytedance.city/privkey.pem;
    client_max_body_size 10m;

    location = /js/script.js {
        access_log off;
        return 410;
    }

    location = /api/event {
        if ($request_method !~ ^(POST|OPTIONS)$) { return 405; }
        add_header Allow 'POST, OPTIONS' always;
        access_log off;
        client_max_body_size 64k;
        proxy_pass http://127.0.0.1:8800;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }

    location = /api/system/health/live {
        access_log off;
        proxy_pass http://127.0.0.1:8800;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }

    location = /api/system/health/ready {
        access_log off;
        proxy_pass http://127.0.0.1:8800;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }

    location / {
        proxy_pass http://127.0.0.1:8800;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $plausible_connection_upgrade;
    }
}
```

`X-Forwarded-For` deliberately overwrites an untrusted client-supplied value;
it must not use `$proxy_add_x_forwarded_for`. The event endpoint accepts only
`POST` and CORS preflight `OPTIONS`, and its Nginx access log is disabled so
analytics payloads cannot be duplicated into request logs. The root proxy
retains WebSocket upgrade support for the live dashboard.

```bash
set -Eeuo pipefail
umask 077
nginx_source=/root/plausible-nginx-source/plausible-final-tls.conf
nginx_target=/etc/nginx/conf.d/plausible.bytedance.city.conf
nginx_target_dir=/etc/nginx/conf.d
nginx_source_dir=/root/plausible-nginx-source
nginx_backup_dir=/root/plausible-nginx-source/backups
nginx_lock_dir=/run/lock/plausible-nginx-vhost.lock.d
test "$(id -u)" = 0
test -d "$nginx_target_dir" && test ! -L "$nginx_target_dir"
test "$(cd -P "$nginx_target_dir" && pwd)" = "$nginx_target_dir"
test -d "$nginx_source_dir" && test ! -L "$nginx_source_dir"
test -f "$nginx_source" && test ! -L "$nginx_source"
test "$(stat -c '%U:%G %a' "$nginx_source")" = 'root:root 600'
test "$(dirname "$nginx_target")" = "$nginx_target_dir"
install -d -o root -g root -m 0700 "$nginx_backup_dir"
test -d "$nginx_backup_dir" && test ! -L "$nginx_backup_dir"
test "$(stat -c '%U:%G %a' "$nginx_backup_dir")" = 'root:root 700'

release_final_lock() {
  rm -f "$nginx_lock_dir/pid"
  rmdir "$nginx_lock_dir"
}
cleanup_final_transaction() {
  if test -n "${final_candidate:-}"; then
    rm -f "$final_candidate"
  fi
  release_final_lock
}
mkdir -m 0700 "$nginx_lock_dir"
trap cleanup_final_transaction EXIT
printf '%s\n' "$$" > "$nginx_lock_dir/pid"
chmod 0600 "$nginx_lock_dir/pid"

final_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
final_backup="$nginx_backup_dir/pre-final-$final_stamp.conf"
test ! -e "$final_backup" && test ! -L "$final_backup"
test ! -e "$final_backup.absent" && test ! -L "$final_backup.absent"
final_candidate="$(mktemp "$nginx_target_dir/.plausible-final.XXXXXX")"
test -f "$final_candidate" && test ! -L "$final_candidate"
had_target=0
target_mode=0644
installed=0
if test -e "$nginx_target" || test -L "$nginx_target"; then
  test -f "$nginx_target" && test ! -L "$nginx_target"
  had_target=1
  target_mode="$(stat -c '%a' "$nginx_target")"
  [[ "$target_mode" =~ ^[0-7]{3,4}$ ]]
  install -o root -g root -m 0600 "$nginx_target" "$final_backup"
  cmp -s "$nginx_target" "$final_backup"
  sync -f "$final_backup"
else
  printf '%s\n' 'target_absent_before_final=true' \
    > "$final_backup.absent"
  chmod 0600 "$final_backup.absent"
  sync -f "$final_backup.absent"
fi

rollback_final_nginx() {
  local failure_code="$1" rollback_ok=1
  trap - ERR INT TERM HUP
  set +e
  rm -f "$final_candidate"
  if (( installed == 1 )); then
    if (( had_target == 1 )); then
      install -o root -g root -m "$target_mode" "$final_backup" \
        "$final_candidate" || rollback_ok=0
      mv -f "$final_candidate" "$nginx_target" || rollback_ok=0
      sync -f "$nginx_target_dir" || rollback_ok=0
    else
      rm -f "$nginx_target" || rollback_ok=0
      sync -f "$nginx_target_dir" || rollback_ok=0
    fi
    nginx -t >/dev/null 2>&1 || rollback_ok=0
    systemctl reload nginx >/dev/null 2>&1 || rollback_ok=0
  fi
  if (( rollback_ok == 0 )); then
    printf '%s\n' \
      'CRITICAL: final Nginx rollback failed; backup retained.' >&2
    exit 125
  fi
  exit "$failure_code"
}
trap 'rollback_final_nginx "$?"' ERR
trap 'rollback_final_nginx 130' INT
trap 'rollback_final_nginx 143' TERM
trap 'rollback_final_nginx 129' HUP

install -o root -g root -m 0644 "$nginx_source" "$final_candidate"
cmp -s "$nginx_source" "$final_candidate"
sync -f "$final_candidate"
mv -f "$final_candidate" "$nginx_target"
installed=1
sync -f "$nginx_target_dir"
cmp -s "$nginx_source" "$nginx_target"
nginx -t
systemctl reload nginx
nginx -t
sha256sum "$nginx_target"
if (( had_target == 1 )); then
  sha256sum "$final_backup"
fi

curl --fail --silent --show-error \
  https://plausible.bytedance.city/api/system/health/live
curl --fail --silent --show-error \
  https://plausible.bytedance.city/api/system/health/ready
PLAUSIBLE_ORIGIN=https://plausible.bytedance.city
retired_tracker_status="$(curl -sS -o /dev/null -w '%{http_code}' \
  "$PLAUSIBLE_ORIGIN/js/script.js")"
test "$retired_tracker_status" = 410
printf 'retired_tracker_status=%s\n' "$retired_tracker_status"
unset PLAUSIBLE_ORIGIN
trap - ERR INT TERM HUP
release_final_lock
trap - EXIT
```

The health probes must succeed and the retired tracker probe must return
`410`. Confirm a normal dashboard asset under `/js/`, if the rendered
dashboard uses one, is not caught by that exact deny.

## 8. Real two-product ingestion acceptance

Use clean browser profiles against the deployed Beta and Phase releases. For
each product, opt in explicitly and generate one unique pageview or custom
event. Do not use a synthetic server-side `curl` as the acceptance event:
Plausible's bot filtering depends on the real browser user agent and client IP.

For Beta, inspect the direct expanded Events API request and require:

- `POST https://plausible.bytedance.city/api/event` returns `202`;
- the JSON body uses `name`, `url`, `domain`, and optional `props`;
- `domain` is exactly `beta.structural.bytedance.city`;
- `url` is canonical origin plus pathname, with no query, fragment, or
  referrer data;
- the response has no `x-plausible-dropped` header.

For Phase, inspect the request produced by the pinned
`@plausible-analytics/tracker` integration and require:

- the event endpoint returns `202`;
- its site domain is exactly `phase.bytedance.city`;
- only the application allowlist survives the privacy transform;
- the response has no `x-plausible-dropped` header.

A `202` carrying `x-plausible-dropped` is a failed acceptance. After both real
requests, confirm raw ingress in ClickHouse:

```bash
cd /root/plausible-ce
docker compose exec -T plausible_events_db clickhouse-client \
  --database plausible_events_db \
  --query "SELECT hostname, name, pathname, timestamp FROM events_v2 WHERE hostname IN ('beta.structural.bytedance.city', 'phase.bytedance.city') ORDER BY timestamp DESC LIMIT 20 FORMAT PrettyCompact"
```

There must be at least one fresh row for each hostname. Finally, sign in to the
dashboard and independently open each site. Confirm the same Beta and Phase
events in Realtime. ClickHouse rows without both dashboard confirmations are
not a complete acceptance.

### 8.1 Configure and accept every `Goal? = yes` event

The executable event authorities remain the code allowlists; the human goal
authority is `docs/analytics/plausible-events.md`. For each row marked `yes`,
configure a Plausible **Custom event** goal only on a site whose documented
caller emits that event. The resulting per-site sets are exact: optional rows
are excluded, and a shared event is configured independently on both sites.

Using the dashboard over HTTPS, open each site's settings and its Goals page.
For every row below, create the exact case-sensitive event goal or prove that
exactly one matching goal already exists. After saving, reopen the Goals page,
confirm the one-to-one entry, and record UTC time plus a non-secret evidence
reference. Do not batch-check rows from memory. A duplicate, missing goal,
wrong site, renamed event, or unchecked row fails this gate.

| Site | Exact custom-event goal | Created or uniquely existing | Reopened-settings acceptance (UTC + evidence reference) |
|---|---|---|---|
| `beta.structural.bytedance.city` | `waitlist_signup` | [ ] | `__________` |
| `beta.structural.bytedance.city` | `waitlist_error` | [ ] | `__________` |
| `beta.structural.bytedance.city` | `thank_you_view` | [ ] | `__________` |
| `beta.structural.bytedance.city` | `thank_you_share` | [ ] | `__________` |
| `phase.bytedance.city` | `screener_filter_applied` | [ ] | `__________` |
| `phase.bytedance.city` | `company_viewed` | [ ] | `__________` |
| `phase.bytedance.city` | `waitlist_signup` | [ ] | `__________` |
| `phase.bytedance.city` | `waitlist_error` | [ ] | `__________` |
| `phase.bytedance.city` | `methodology_opened` | [ ] | `__________` |
| `phase.bytedance.city` | `thank_you_share` | [ ] | `__________` |

The two fresh ingestion events required earlier prove the transport and site
binding. Goal configuration acceptance proves the dashboard mapping; it does
not justify deliberately causing a production error merely to populate an
error-rate goal. Record the ten completed row references again in the initial
deployment receipt as one indexed evidence artifact.

## 9. Backup, restore, and upgrades

Plausible stores account/site metadata in Postgres and analytics events in
ClickHouse. **ClickHouse event data is not replayable from PostgreSQL.** The
runtime identity also depends on the original `SECRET_KEY_BASE`,
`TOTP_VAULT_KEY`, database configuration, official compose, and local override.
A Postgres dump or a set of data volumes without those root-only files is not a
recoverable backup.

### 9.1 Consistent root-only backup

The complete backup set is:

- a logical `postgres.dump` for independent Postgres validation and recovery;
- cold snapshots of all four official volumes: `db-data`, `event-data`,
  `event-logs`, and `plausible-data`;
- `config-root-only.tgz`, containing `.env`, `compose.yml`,
  `compose.override.yml`, the optional generated `compose.restore-images.yml`,
  and the official `clickhouse/` configuration tree;
- `source.bundle`, which makes the exact source commit and `.git` history
  available without network access;
- `authority.env`, the non-secret snapshot of the active directory, Compose
  project, port, and source commit;
- `RESOLVED_IMAGES.txt`, containing the pullable repo digests actually used by
  Postgres, ClickHouse, and Plausible; its archive-helper entry deliberately
  reuses the resolved Postgres Alpine image after a real `tar` capability probe;
- `MANIFEST.txt` with non-secret backup and authority metadata; and
- `SHA256SUMS` covering every artifact above.

For `plausible-ce-complete-v2`, the recoverable runtime identity is the 40-hex
`source_commit` in `MANIFEST.txt` plus the three exact service repo digests in
`RESOLVED_IMAGES.txt`. Fixed release-name or historical OCI fields are
deliberately not copied forward after an upgrade.

Stop the only event writer before taking either database snapshot. The commands
never print `.env`, expand its values into logs, or render resolved Compose
configuration:

```bash
set -euo pipefail
authority_file="${PLAUSIBLE_AUTHORITY_FILE:-/root/plausible-ce-authority.env}"
test "$(stat -c '%U:%G %a' "$authority_file")" = 'root:root 600'
. "$authority_file"
test "$PLAUSIBLE_AUTHORITY_PROTOCOL" = 'plausible-ce-authority-v1'
production_dir="$PLAUSIBLE_ACTIVE_DIR"
production_project="$PLAUSIBLE_ACTIVE_PROJECT"
production_port="$PLAUSIBLE_ACTIVE_PORT"
authority_root="${PLAUSIBLE_AUTHORITY_ROOT:-/root}"
case "$production_dir" in "$authority_root"/*) ;; *) exit 1 ;; esac
[[ "$production_project" =~ ^[a-z0-9][a-z0-9_-]+$ ]]
[[ "$production_port" =~ ^[0-9]+$ ]]
export COMPOSE_PROJECT_NAME="$production_project"
backup_root="${PLAUSIBLE_BACKUP_ROOT:-/root/backups/plausible-ce}"
production_compose_file="$production_dir/compose.yml:$production_dir/compose.override.yml"
if test -f "$production_dir/compose.restore-images.yml"; then
  production_compose_file="$production_compose_file:$production_dir/compose.restore-images.yml"
fi
production_resumed=0
resume_production() {
  if (( production_resumed == 0 )); then
    cd "$production_dir"
    COMPOSE_FILE="$production_compose_file" docker compose up -d
    production_resumed=1
  fi
}
trap resume_production EXIT

cd "$production_dir"
test "$(git rev-parse HEAD)" = "$PLAUSIBLE_ACTIVE_SOURCE_COMMIT"
umask 077
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$backup_root/$production_project/$stamp"
install -d -o root -g root -m 0700 "$backup_dir"
test "$(stat -c '%U:%G %a' "$backup_dir")" = 'root:root 700'
test "$(stat -c '%U:%G %a' .env)" = 'root:root 600'
test "$(stat -c '%U:%G %a' compose.override.yml)" = 'root:root 600'

resolve_repo_digest() {
  local image_id="$1" expected_repo="$2" candidate resolved=''
  while IFS= read -r candidate; do
    [[ "$candidate" =~ ^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$ ]] \
      || continue
    case "$candidate" in
      "$expected_repo"@sha256:*)
        test -z "$resolved" || return 1
        resolved="$candidate"
        ;;
    esac
  done < <(docker image inspect \
    --format '{{range .RepoDigests}}{{println .}}{{end}}' "$image_id")
  test -n "$resolved" || return 1
  printf '%s\n' "$resolved"
}
{
  archive_helper=''
  for service in plausible_db plausible_events_db plausible; do
    case "$service" in
      plausible_db) expected_repo=postgres ;;
      plausible_events_db) expected_repo=clickhouse/clickhouse-server ;;
      plausible) expected_repo=ghcr.io/plausible/community-edition ;;
      *) exit 1 ;;
    esac
    container_id="$(COMPOSE_FILE="$production_compose_file" \
      docker compose ps --quiet "$service")"
    test -n "$container_id"
    image_id="$(docker inspect --format '{{.Image}}' "$container_id")"
    resolved_image="$(resolve_repo_digest "$image_id" "$expected_repo")"
    printf '%s=%s\n' "$service" "$resolved_image"
    if test "$service" = plausible_db; then
      archive_helper="$resolved_image"
    fi
  done
  test -n "$archive_helper"
  docker run --rm "$archive_helper" tar --help > /dev/null
  printf 'archive_helper=%s\n' "$archive_helper"
} > "$backup_dir/RESOLVED_IMAGES.txt"

COMPOSE_FILE="$production_compose_file" docker compose stop plausible
COMPOSE_FILE="$production_compose_file" docker compose exec -T plausible_db \
  pg_dump --username postgres --format=custom plausible_db \
  > "$backup_dir/postgres.dump"
COMPOSE_FILE="$production_compose_file" docker compose exec -T plausible_db \
  pg_restore --list < "$backup_dir/postgres.dump" > /dev/null
COMPOSE_FILE="$production_compose_file" \
  docker compose stop plausible_db plausible_events_db

cp -- "$authority_file" "$backup_dir/authority.env"
git bundle create "$backup_dir/source.bundle" HEAD
config_paths=(.env compose.yml compose.override.yml clickhouse)
if test -f compose.restore-images.yml; then
  config_paths+=(compose.restore-images.yml)
fi
tar -czf "$backup_dir/config-root-only.tgz" \
  "${config_paths[@]}"

for logical in db-data event-data event-logs plausible-data; do
  volume="$(docker volume ls \
    --filter label=com.docker.compose.project="$production_project" \
    --filter label=com.docker.compose.volume="$logical" \
    --format '{{.Name}}')"
  test -n "$volume"
  test "$(printf '%s\n' "$volume" | wc -l | tr -d ' ')" = 1
  docker run --rm --volume "$volume:/source:ro" \
    --volume "$backup_dir:/backup" "$archive_helper" \
    tar -C /source -czf "/backup/$logical.tgz" .
done

{
  printf 'backup_protocol=%s\n' 'plausible-ce-complete-v2'
  printf 'created_utc=%s\n' "$stamp"
  printf 'source_commit=%s\n' "$(git rev-parse HEAD)"
  printf 'active_dir=%s\n' "$production_dir"
  printf 'compose_project=%s\n' "$production_project"
  printf 'active_port=%s\n' "$production_port"
} > "$backup_dir/MANIFEST.txt"

chmod 0600 "$backup_dir"/*
chown root:root "$backup_dir"/*
(
  cd "$backup_dir"
  sha256sum MANIFEST.txt RESOLVED_IMAGES.txt authority.env source.bundle \
    config-root-only.tgz postgres.dump \
    db-data.tgz event-data.tgz event-logs.tgz plausible-data.tgz \
    > SHA256SUMS
  chmod 0600 SHA256SUMS
  chown root:root SHA256SUMS
  sha256sum --check SHA256SUMS
  tar -tzf config-root-only.tgz > /dev/null
  for archive in db-data.tgz event-data.tgz event-logs.tgz plausible-data.tgz; do
    tar -tzf "$archive" > /dev/null
  done
)
test "$(find "$backup_dir" -maxdepth 1 -type f ! -perm 0600 -print -quit)" = ''

resume_production
curl --fail --silent --show-error \
  "http://127.0.0.1:$production_port/api/system/health/ready"
trap - EXIT
```

If any dump, archive, checksum, ownership, or readiness check fails, keep the
backup directory for diagnosis, mark that snapshot invalid, and immediately
return the unchanged production project to service with `docker compose up -d`.
Do not copy an invalid set off-host.

`config-root-only.tgz` contains live secrets. It and every derivative must stay
root-owned (`0700` directory, `0600` files). Never copy the plaintext config
archive into the repository, chat, CI artifacts, or general object storage.

#### 9.1.1 Encrypt and verify the complete set off-host

Use age v1 with X25519 recipients and ChaCha20-Poly1305 payload encryption. The
approved public recipients file is referenced only by
`PLAUSIBLE_BACKUP_RECIPIENTS_FILE`; never put a recipient, private identity,
passphrase, or key path into this runbook or a receipt. The approved off-host
rclone object is referenced only by `PLAUSIBLE_OFFHOST_TARGET`; the variable
must name a configured remote object rather than a local path. A recovery
operator supplies the private identity separately through the approved secret
reference `PLAUSIBLE_BACKUP_IDENTITY_FILE` on the isolated restore host.

The command below streams one tar containing the complete enumerated backup
set directly into age, so it creates no second plaintext aggregate. It refuses
a private key in the recipients file, refuses an implicit/local destination,
uploads the ciphertext plus checksum, downloads the ciphertext again, and
requires byte-for-byte and SHA-256 equality. A command failure or missing
round-trip proof leaves this backup **not accepted**; do not fill its receipt
row.

```bash
set -euo pipefail
umask 077
: "${SOURCE_BACKUP_DIR:?set the verified backup from Section 9.1}"
: "${PLAUSIBLE_BACKUP_RECIPIENTS_FILE:?set the approved age recipients file}"
: "${PLAUSIBLE_OFFHOST_TARGET:?set the approved rclone remote object}"
command -v age >/dev/null
command -v rclone >/dev/null
age_version="$(age --version 2>/dev/null)"
[[ "$age_version" =~ ^v?1\.[0-9]+(\.[0-9]+)?([+-][0-9A-Za-z.-]+)?$ ]]
test "$(id -u)" = 0
[[ "$SOURCE_BACKUP_DIR" == /* ]]
test "$(realpath -e "$SOURCE_BACKUP_DIR")" = "$SOURCE_BACKUP_DIR"
test "$(stat -c '%U:%G %a' "$SOURCE_BACKUP_DIR")" = 'root:root 700'
[[ "$PLAUSIBLE_BACKUP_RECIPIENTS_FILE" == /* ]]
test -f "$PLAUSIBLE_BACKUP_RECIPIENTS_FILE"
test ! -L "$PLAUSIBLE_BACKUP_RECIPIENTS_FILE"
test "$(stat -c '%U:%G %a' "$PLAUSIBLE_BACKUP_RECIPIENTS_FILE")" = \
  'root:root 600'
test "$(realpath -e "$PLAUSIBLE_BACKUP_RECIPIENTS_FILE")" = \
  "$PLAUSIBLE_BACKUP_RECIPIENTS_FILE"
recipients_parent="$(dirname "$PLAUSIBLE_BACKUP_RECIPIENTS_FILE")"
test -d "$recipients_parent" && test ! -L "$recipients_parent"
test "$(realpath -e "$recipients_parent")" = "$recipients_parent"
test "$(stat -c '%U:%G %a' "$recipients_parent")" = 'root:root 700'
if grep -Eq 'AGE-SECRET-KEY-|BEGIN [A-Z ]*PRIVATE KEY' \
  "$PLAUSIBLE_BACKUP_RECIPIENTS_FILE"; then
  exit 1
fi
if ! awk '
  /^[[:space:]]*($|#)/ { next }
  /^age1[0-9a-z]+$/ { seen = 1; next }
  { exit 1 }
  END { if (!seen) exit 1 }
' "$PLAUSIBLE_BACKUP_RECIPIENTS_FILE"; then
  exit 1
fi
case "$PLAUSIBLE_OFFHOST_TARGET" in
  *$'\n'*|*$'\r'*|/*|'') exit 1 ;;
  [A-Za-z0-9]*:*) ;;
  *) exit 1 ;;
esac

archive_files=(
  MANIFEST.txt RESOLVED_IMAGES.txt authority.env source.bundle
  config-root-only.tgz postgres.dump db-data.tgz event-data.tgz
  event-logs.tgz plausible-data.tgz SHA256SUMS
)
for artifact in "${archive_files[@]}"; do
  test -f "$SOURCE_BACKUP_DIR/$artifact"
  test ! -L "$SOURCE_BACKUP_DIR/$artifact"
  test "$(stat -c '%U:%G %a' "$SOURCE_BACKUP_DIR/$artifact")" = \
    'root:root 600'
done
(
  cd "$SOURCE_BACKUP_DIR"
  sha256sum --check SHA256SUMS
)

backup_project="$(sed -n 's/^compose_project=//p' \
  "$SOURCE_BACKUP_DIR/MANIFEST.txt")"
backup_stamp="$(sed -n 's/^created_utc=//p' \
  "$SOURCE_BACKUP_DIR/MANIFEST.txt")"
[[ "$backup_project" =~ ^[a-z0-9][a-z0-9_-]+$ ]]
[[ "$backup_stamp" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]
export_dir="${PLAUSIBLE_BACKUP_EXPORT_DIR:-/root/backups/plausible-ce-encrypted}"
install -d -o root -g root -m 0700 "$export_dir"
test -d "$export_dir" && test ! -L "$export_dir"
test "$(realpath -e "$export_dir")" = "$export_dir"
test "$(stat -c '%U:%G %a' "$export_dir")" = 'root:root 700'
encrypted_artifact="$export_dir/$backup_project-$backup_stamp.tar.age"
encrypted_candidate="$export_dir/.$backup_project-$backup_stamp.tar.age.$$"
checksum_file="$encrypted_artifact.sha256"
checksum_candidate="$checksum_file.$$"
verification_copy="$export_dir/.offhost-roundtrip.$$"
checksum_verification_copy="$export_dir/.offhost-checksum-roundtrip.$$"
recipient_snapshot=''
test ! -e "$encrypted_artifact" && test ! -e "$checksum_file"
cleanup_backup_export() {
  rm -f "$encrypted_candidate" "$checksum_candidate" "$verification_copy" \
    "$checksum_verification_copy"
  if test -n "${recipient_snapshot:-}"; then
    rm -f "$recipient_snapshot"
  fi
}
trap cleanup_backup_export EXIT

recipient_snapshot="$(mktemp "$export_dir/.age-recipients.XXXXXX")"
install -o root -g root -m 0600 "$PLAUSIBLE_BACKUP_RECIPIENTS_FILE" \
  "$recipient_snapshot"
cmp -s "$PLAUSIBLE_BACKUP_RECIPIENTS_FILE" "$recipient_snapshot"
test "$(stat -c '%U:%G %a' "$recipient_snapshot")" = 'root:root 600'
if grep -Eq 'AGE-SECRET-KEY-|BEGIN [A-Z ]*PRIVATE KEY' \
  "$recipient_snapshot"; then
  exit 1
fi
if ! awk '
  /^[[:space:]]*($|#)/ { next }
  /^age1[0-9a-z]+$/ { seen = 1; next }
  { exit 1 }
  END { if (!seen) exit 1 }
' "$recipient_snapshot"; then
  exit 1
fi

(
  cd "$SOURCE_BACKUP_DIR"
  tar --format=posix -cf - -- "${archive_files[@]}"
) | age --encrypt \
  --recipients-file "$recipient_snapshot" \
  --output "$encrypted_candidate"
test -s "$encrypted_candidate"
chown root:root "$encrypted_candidate"
chmod 0600 "$encrypted_candidate"
mv "$encrypted_candidate" "$encrypted_artifact"
ciphertext_sha256="$(sha256sum "$encrypted_artifact" | awk '{print $1}')"
[[ "$ciphertext_sha256" =~ ^[0-9a-f]{64}$ ]]
printf '%s  %s\n' "$ciphertext_sha256" "$(basename "$encrypted_artifact")" \
  > "$checksum_candidate"
chown root:root "$checksum_candidate"
chmod 0600 "$checksum_candidate"
mv "$checksum_candidate" "$checksum_file"

rclone copyto --immutable "$encrypted_artifact" "$PLAUSIBLE_OFFHOST_TARGET"
rclone copyto --immutable "$checksum_file" \
  "$PLAUSIBLE_OFFHOST_TARGET.sha256"
rclone copyto "$PLAUSIBLE_OFFHOST_TARGET" "$verification_copy"
rclone copyto "$PLAUSIBLE_OFFHOST_TARGET.sha256" \
  "$checksum_verification_copy"
chmod 0600 "$verification_copy"
chmod 0600 "$checksum_verification_copy"
cmp -s "$encrypted_artifact" "$verification_copy"
cmp -s "$checksum_file" "$checksum_verification_copy"
retrieved_sha256="$(sha256sum "$verification_copy" | awk '{print $1}')"
test "$retrieved_sha256" = "$ciphertext_sha256"
cleanup_backup_export
trap - EXIT
printf 'encrypted_backup_sha256=%s\n' "$ciphertext_sha256"
printf 'age_version=%s\n' "$age_version"
```

Record only the approved remote object reference, ciphertext SHA-256, age
version, recipients-file approval identifier (not its contents), execution UTC,
and round-trip result in the initial deployment receipt. Decryption uses
`age --decrypt --identity "$PLAUSIBLE_BACKUP_IDENTITY_FILE"` only on an
isolated root-only restore host; it is not part of routine deployment.

### 9.2 Isolated restore drill

Restore into a new directory, a new Compose project, new volumes, and a
different loopback port. The production directory and volumes remain untouched.
Set `SOURCE_BACKUP_DIR` to one verified backup directory without printing its
contents:

```bash
set -euo pipefail
: "${SOURCE_BACKUP_DIR:?set a verified root-only backup directory}"
test "$(stat -c '%U:%G %a' "$SOURCE_BACKUP_DIR")" = 'root:root 700'
test "$(stat -c '%U:%G %a' "$SOURCE_BACKUP_DIR/config-root-only.tgz")" = \
  'root:root 600'
test "$(stat -c '%U:%G %a' "$SOURCE_BACKUP_DIR/SHA256SUMS")" = \
  'root:root 600'
(
  cd "$SOURCE_BACKUP_DIR"
  sha256sum --check SHA256SUMS
  rg -q '^backup_protocol=plausible-ce-complete-v2$' MANIFEST.txt
  rg -q '^PLAUSIBLE_AUTHORITY_PROTOCOL=plausible-ce-authority-v1$' \
    authority.env
)
test "$(grep -c '^source_commit=' "$SOURCE_BACKUP_DIR/MANIFEST.txt")" = 1
test "$(grep -c '^PLAUSIBLE_ACTIVE_SOURCE_COMMIT=' \
  "$SOURCE_BACKUP_DIR/authority.env")" = 1
backup_source_commit="$(sed -n 's/^source_commit=//p' \
  "$SOURCE_BACKUP_DIR/MANIFEST.txt")"
authority_source_commit="$(sed -n 's/^PLAUSIBLE_ACTIVE_SOURCE_COMMIT=//p' \
  "$SOURCE_BACKUP_DIR/authority.env")"
[[ "$backup_source_commit" =~ ^[0-9a-f]{40}$ ]]
test "$backup_source_commit" = "$authority_source_commit"

resolved_image_for() {
  local key="$1" expected_repo="$2" value
  test "$(grep -c "^${key}=" \
    "$SOURCE_BACKUP_DIR/RESOLVED_IMAGES.txt")" = 1 || return 1
  value="$(sed -n "s/^${key}=//p" \
    "$SOURCE_BACKUP_DIR/RESOLVED_IMAGES.txt")"
  [[ "$value" =~ ^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$ ]] \
    || return 1
  case "$value" in "$expected_repo"@sha256:*) ;; *) return 1 ;; esac
  printf '%s\n' "$value"
}
postgres_image="$(resolved_image_for plausible_db postgres)"
clickhouse_image="$(resolved_image_for \
  plausible_events_db clickhouse/clickhouse-server)"
plausible_image="$(resolved_image_for \
  plausible ghcr.io/plausible/community-edition)"
archive_helper="$(resolved_image_for archive_helper postgres)"
for resolved_image in "$postgres_image" "$clickhouse_image" \
  "$plausible_image" "$archive_helper"; do
  docker pull "$resolved_image" > /dev/null
done

restore_stamp="$(date -u +%Y%m%d%H%M%S)"
restore_project="plausible-ce-restore-$restore_stamp"
restore_dir="/root/$restore_project"
restore_port="${RESTORE_PORT:-18800}"
test ! -e "$restore_dir"
git clone "$SOURCE_BACKUP_DIR/source.bundle" "$restore_dir"
git -C "$restore_dir" checkout --detach "$backup_source_commit"
tar -xzf "$SOURCE_BACKUP_DIR/config-root-only.tgz" -C "$restore_dir"
chown -R root:root "$restore_dir"
chmod 0700 "$restore_dir"
chmod 0600 "$restore_dir/.env" "$restore_dir/compose.override.yml"
test "$(git -C "$restore_dir" rev-parse HEAD)" = "$backup_source_commit"
git -C "$restore_dir" diff --exit-code

sed -i -E \
  "s/^COMPOSE_PROJECT_NAME=.*/COMPOSE_PROJECT_NAME=$restore_project/" \
  "$restore_dir/.env"
sed -i -E \
  "s#^BASE_URL=.*#BASE_URL=http://127.0.0.1:$restore_port#" \
  "$restore_dir/.env"
sed -i -E \
  "s#127\\.0\\.0\\.1:8800:8000#127.0.0.1:$restore_port:8000#" \
  "$restore_dir/compose.override.yml"
sed -i '/^COMPOSE_FILE=/d' "$restore_dir/.env"
printf '%s\n' \
  'COMPOSE_FILE=compose.yml:compose.override.yml:compose.restore-images.yml' \
  >> "$restore_dir/.env"
{
  printf '%s\n' 'services:'
  printf '  plausible_db:\n    image: "%s"\n' "$postgres_image"
  printf '  plausible_events_db:\n    image: "%s"\n' "$clickhouse_image"
  printf '  plausible:\n    image: "%s"\n' "$plausible_image"
} > "$restore_dir/compose.restore-images.yml"
chmod 0600 "$restore_dir/.env" "$restore_dir/compose.override.yml" \
  "$restore_dir/compose.restore-images.yml"

for logical in db-data event-data event-logs plausible-data; do
  restored_volume="${restore_project}_${logical}"
  docker volume create \
    --label com.docker.compose.project="$restore_project" \
    --label com.docker.compose.volume="$logical" \
    "$restored_volume" > /dev/null
  docker run --rm --volume "$restored_volume:/target" \
    --volume "$SOURCE_BACKUP_DIR:/backup:ro" "$archive_helper" \
    tar -C /target -xzf "/backup/$logical.tgz"
done

cd "$restore_dir"
restore_compose_file="$restore_dir/compose.yml:$restore_dir/compose.override.yml:$restore_dir/compose.restore-images.yml"
COMPOSE_FILE="$restore_compose_file" docker compose config --quiet
COMPOSE_FILE="$restore_compose_file" docker compose up -d
for attempt in $(seq 1 60); do
  if curl --fail --silent --show-error \
    "http://127.0.0.1:$restore_port/api/system/health/ready" > /dev/null; then
    break
  fi
  sleep 2
done
curl --fail --silent --show-error \
  "http://127.0.0.1:$restore_port/api/system/health/ready"
ss -ltn | rg "127\\.0\\.0\\.1:$restore_port"
if ss -ltn | rg -q "(?:0\\.0\\.0\\.0|\\[::\\]):$restore_port"; then
  exit 1
fi
COMPOSE_FILE="$restore_compose_file" \
  docker compose exec -T plausible_events_db clickhouse-client \
  --database plausible_events_db \
  --query "SELECT hostname, count() FROM events_v2 WHERE hostname IN ('beta.structural.bytedance.city', 'phase.bytedance.city') GROUP BY hostname ORDER BY hostname FORMAT PrettyCompact"

set -a
. "$restore_dir/.env"
set +a
export PGPASSWORD="$POSTGRES_PASSWORD"
logical_pg_container="${restore_project}-logical-pg"
logical_pg_volume="${restore_project}_logical-pg"
docker volume create "$logical_pg_volume" > /dev/null
docker run -d --name "$logical_pg_container" \
  --env POSTGRES_PASSWORD \
  --volume "$logical_pg_volume:/var/lib/postgresql/data" \
  "$postgres_image" > /dev/null
for attempt in $(seq 1 60); do
  if docker exec "$logical_pg_container" pg_isready --username postgres \
    > /dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker exec --env PGPASSWORD "$logical_pg_container" \
  createdb --username postgres plausible_db
docker exec -i --env PGPASSWORD "$logical_pg_container" \
  pg_restore --username postgres --dbname plausible_db \
  --no-owner --no-privileges \
  < "$SOURCE_BACKUP_DIR/postgres.dump"
test "$(docker exec --env PGPASSWORD "$logical_pg_container" \
  psql --username postgres --dbname plausible_db --tuples-only --no-align \
  --command "SELECT count(*) FROM sites WHERE domain IN ('beta.structural.bytedance.city', 'phase.bytedance.city');")" = 2
docker rm --force "$logical_pg_container" > /dev/null
docker volume rm "$logical_pg_volume" > /dev/null
unset PGPASSWORD POSTGRES_PASSWORD SECRET_KEY_BASE TOTP_VAULT_KEY
unset COMPOSE_PROJECT_NAME BASE_URL DISABLE_REGISTRATION
unset ENABLE_EMAIL_VERIFICATION HTTP_PORT
```

Use an SSH tunnel to the restore port. Confirm that the original administrator
can sign in, both sites still use `Asia/Shanghai`, and both sites show the
expected historical events. The cold `db-data` snapshot is used for the exact
paired restore above, while the temporary Postgres container proves that
`postgres.dump` is an independent logical recovery path. Never import it into
production merely to test it.

Only these combined checks constitute a restore proof:

1. every checksum passes before extraction;
2. restored configuration is root-owned and secret files are `0600`;
3. readiness passes on the alternate loopback port with no wildcard listener;
4. the first administrator, both site/timezone records, and their ClickHouse
   plus dashboard history survive the cold-volume restore; and
5. `postgres.dump` independently restores both site rows into a clean Postgres
   volume.

Do not change Nginx or DNS during a drill. After evidence is recorded, run this
in the restore directory without a volume flag:

```bash
COMPOSE_FILE=compose.yml:compose.override.yml:compose.restore-images.yml \
  docker compose down
```

Remove only the four explicitly named restore volumes after a second operator
verifies `restore_project`; never use a wildcard or production project name.

### 9.3 Disaster promotion and failed-restore rollback

Promotion changes the single authority; it does not leave the restored stack as
an unnamed second production. Complete Section 9.2 first, keep its directory,
project, volumes, and source history intact, and set the three `RESTORED_*`
variables below. The old authority is copied before either writer changes.

This same-host promotion is atomic at the authority-file boundary. Its EXIT
trap stops the candidate, restores the previous authority, and restarts the old
stack on any failure or rejected dashboard check:

```bash
set -euo pipefail
authority_file="${PLAUSIBLE_AUTHORITY_FILE:-/root/plausible-ce-authority.env}"
test "$(stat -c '%U:%G %a' "$authority_file")" = 'root:root 600'
. "$authority_file"
test "$PLAUSIBLE_AUTHORITY_PROTOCOL" = 'plausible-ce-authority-v1'
old_dir="$PLAUSIBLE_ACTIVE_DIR"
old_project="$PLAUSIBLE_ACTIVE_PROJECT"
old_port="$PLAUSIBLE_ACTIVE_PORT"
old_source_commit="$PLAUSIBLE_ACTIVE_SOURCE_COMMIT"

: "${RESTORED_DIR:?set the proven restore directory from Section 9.2}"
: "${RESTORED_PROJECT:?set the proven restore Compose project}"
: "${RESTORED_PROOF_PORT:?set the proven alternate loopback port}"
authority_root="${PLAUSIBLE_AUTHORITY_ROOT:-/root}"
case "$old_dir" in "$authority_root"/*) ;; *) exit 1 ;; esac
case "$RESTORED_DIR" in "$authority_root"/*) ;; *) exit 1 ;; esac
[[ "$old_project" =~ ^[a-z0-9][a-z0-9_-]+$ ]]
[[ "$RESTORED_PROJECT" =~ ^[a-z0-9][a-z0-9_-]+$ ]]
[[ "$old_port" =~ ^[0-9]+$ ]]
[[ "$old_source_commit" =~ ^[0-9a-f]{40}$ ]]
[[ "$RESTORED_PROOF_PORT" =~ ^[0-9]+$ ]]
test "$RESTORED_PROOF_PORT" != 8800
test "$RESTORED_DIR" != "$old_dir"
test "$RESTORED_PROJECT" != "$old_project"
restored_source_commit="$(git -C "$RESTORED_DIR" rev-parse HEAD)"
[[ "$restored_source_commit" =~ ^[0-9a-f]{40}$ ]]

compose_project() {
  local project_dir="$1" project_name="$2" compose_file
  shift 2
  compose_file="$project_dir/compose.yml:$project_dir/compose.override.yml"
  if test -f "$project_dir/compose.restore-images.yml"; then
    compose_file="$compose_file:$project_dir/compose.restore-images.yml"
  fi
  (
    cd "$project_dir"
    COMPOSE_FILE="$compose_file" COMPOSE_PROJECT_NAME="$project_name" \
      docker compose "$@"
  )
}

promotion_stamp="$(date -u +%Y%m%d%H%M%S)"
authority_state_dir="${PLAUSIBLE_AUTHORITY_STATE_DIR:-/root}"
old_authority_backup="$authority_state_dir/plausible-ce-authority.rollback-$promotion_stamp.env"
cp --preserve=mode,ownership "$authority_file" "$old_authority_backup"
chmod 0600 "$old_authority_backup"
authority_swapped=0

rollback_promotion() {
  status=$?
  trap - EXIT
  set +e
  rollback_failed=0
  compose_project "$RESTORED_DIR" "$RESTORED_PROJECT" stop plausible \
    || rollback_failed=1
  (
    cd "$RESTORED_DIR"
    sed -i -E \
      "s#127\\.0\\.0\\.1:8800:8000#127.0.0.1:$RESTORED_PROOF_PORT:8000#" \
      compose.override.yml
    sed -i -E \
      "s#^BASE_URL=.*#BASE_URL=http://127.0.0.1:$RESTORED_PROOF_PORT#" .env
  ) || rollback_failed=1
  if (( authority_swapped == 1 )); then
    authority_rollback="$(mktemp "$authority_state_dir/.plausible-ce-authority.XXXXXX")"
    if [[ -n "$authority_rollback" ]]; then
      cp "$old_authority_backup" "$authority_rollback" || rollback_failed=1
      chown root:root "$authority_rollback" || rollback_failed=1
      chmod 0600 "$authority_rollback" || rollback_failed=1
      mv -f "$authority_rollback" "$authority_file" || rollback_failed=1
    else
      rollback_failed=1
    fi
  fi
  compose_project "$old_dir" "$old_project" up -d || rollback_failed=1
  grep -Fqx "PLAUSIBLE_ACTIVE_DIR=$old_dir" "$authority_file" || rollback_failed=1
  grep -Fqx "PLAUSIBLE_ACTIVE_PROJECT=$old_project" "$authority_file" || rollback_failed=1
  grep -Fqx "PLAUSIBLE_ACTIVE_PORT=$old_port" "$authority_file" || rollback_failed=1
  grep -Fqx "PLAUSIBLE_ACTIVE_SOURCE_COMMIT=$old_source_commit" \
    "$authority_file" || rollback_failed=1
  curl --fail --silent --show-error \
    "http://127.0.0.1:$old_port/api/system/health/ready" \
    > /dev/null || rollback_failed=1
  if (( rollback_failed != 0 )); then
    printf '%s\n' \
      'CRITICAL: Plausible promotion rollback could not restore authority/runtime agreement.' \
      >&2
    exit 97
  fi
  set -e
  exit "$status"
}
trap rollback_promotion EXIT

compose_project "$RESTORED_DIR" "$RESTORED_PROJECT" up -d
curl --fail --silent --show-error \
  "http://127.0.0.1:$RESTORED_PROOF_PORT/api/system/health/ready"

compose_project "$old_dir" "$old_project" stop plausible
compose_project "$RESTORED_DIR" "$RESTORED_PROJECT" stop plausible
(
  cd "$RESTORED_DIR"
  sed -i -E \
    "s#127\\.0\\.0\\.1:$RESTORED_PROOF_PORT:8000#127.0.0.1:8800:8000#" \
    compose.override.yml
  sed -i -E \
    's#^BASE_URL=.*#BASE_URL=https://plausible.bytedance.city#' .env
  chmod 0600 .env compose.override.yml
)
compose_project "$RESTORED_DIR" "$RESTORED_PROJECT" up -d
curl --fail --silent --show-error \
  http://127.0.0.1:8800/api/system/health/ready
curl --fail --silent --show-error \
  http://127.0.0.1:8800/api/system/health/live
compose_project "$RESTORED_DIR" "$RESTORED_PROJECT" \
  exec -T plausible_events_db clickhouse-client \
  --database plausible_events_db \
  --query "SELECT hostname, count() FROM events_v2 WHERE hostname IN ('beta.structural.bytedance.city', 'phase.bytedance.city') GROUP BY hostname ORDER BY hostname FORMAT PrettyCompact"

printf '%s\n' \
  'Verify both sites and historical events through the live dashboard.' \
  'Type PROMOTE only if the restored stack is the intended authority.'
read -r promotion_confirmation
test "$promotion_confirmation" = PROMOTE

authority_candidate="$(mktemp "$authority_state_dir/.plausible-ce-authority.XXXXXX")"
{
  printf '%s\n' 'PLAUSIBLE_AUTHORITY_PROTOCOL=plausible-ce-authority-v1'
  printf 'PLAUSIBLE_ACTIVE_DIR=%s\n' "$RESTORED_DIR"
  printf 'PLAUSIBLE_ACTIVE_PROJECT=%s\n' "$RESTORED_PROJECT"
  printf '%s\n' 'PLAUSIBLE_ACTIVE_PORT=8800'
  printf 'PLAUSIBLE_ACTIVE_SOURCE_COMMIT=%s\n' "$restored_source_commit"
} > "$authority_candidate"
chown root:root "$authority_candidate"
chmod 0600 "$authority_candidate"
authority_swapped=1
mv -f "$authority_candidate" "$authority_file"

compose_project "$old_dir" "$old_project" stop
. "$authority_file"
test "$PLAUSIBLE_ACTIVE_DIR" = "$RESTORED_DIR"
test "$PLAUSIBLE_ACTIVE_PROJECT" = "$RESTORED_PROJECT"
test "$PLAUSIBLE_ACTIVE_PORT" = 8800
test "$PLAUSIBLE_ACTIVE_SOURCE_COMMIT" = "$restored_source_commit"
curl --fail --silent --show-error \
  http://127.0.0.1:8800/api/system/health/ready
trap - EXIT
```

After the script succeeds, the restored project is the only running authority
and the previous project is fully stopped. Keep the old directory, its
root-only authority snapshot, and all old volumes for the rollback retention
window; do not destroy them during promotion. Update the project registry and
deployment receipt with the new active directory/project and the old rollback
snapshot. Then run Section 9.1 from the new authority and require a new complete
backup plus the Beta/Phase ClickHouse and dashboard proofs. That post-promotion
backup proves the next backup no longer resolves to stale data.

For a later rollback within the retention window, stop the active project,
atomically restore the saved authority file, start the project named by that
file, and pass loopback, ClickHouse, and dashboard checks before retiring the
failed candidate. Never infer the old source from a directory name.

On a replacement host, complete the same loopback proof and authority switch
before any public change, then repeat the HTTP ACME, DNS, certificate, and final
TLS sequence in Sections 6 and 7. DNS is always last.

NEVER run `docker compose down -v`; `docker compose down` without `-v`
preserves named volumes, but it is still not a substitute for a verified
backup.

### 9.4 Upgrades

Resolve the active source from the authority file. Do not `cd` to a remembered
directory or assume that `/root/plausible-ce` is still active after a recovery:

```bash
set -euo pipefail
authority_file="${PLAUSIBLE_AUTHORITY_FILE:-/root/plausible-ce-authority.env}"
test "$(stat -c '%U:%G %a' "$authority_file")" = 'root:root 600'
. "$authority_file"
test "$PLAUSIBLE_AUTHORITY_PROTOCOL" = 'plausible-ce-authority-v1'
cd "$PLAUSIBLE_ACTIVE_DIR"
export COMPOSE_PROJECT_NAME="$PLAUSIBLE_ACTIVE_PROJECT"
test "$(git rev-parse HEAD)" = "$PLAUSIBLE_ACTIVE_SOURCE_COMMIT"
active_compose_file="$PLAUSIBLE_ACTIVE_DIR/compose.yml:$PLAUSIBLE_ACTIVE_DIR/compose.override.yml"
if test -f "$PLAUSIBLE_ACTIVE_DIR/compose.restore-images.yml"; then
  active_compose_file="$active_compose_file:$PLAUSIBLE_ACTIVE_DIR/compose.restore-images.yml"
fi
COMPOSE_FILE="$active_compose_file" docker compose config --quiet
```

An exact runtime pin is part of the active identity. Never update only the Git
checkout or image tag: `compose.restore-images.yml` has final precedence and
would otherwise keep the old runtime while a new source commit is recorded.

Before an in-place upgrade:

1. Read the release-specific migration and rollback notes.
2. Take, verify, encrypt, and transfer the complete backup in Section 9.1.
3. Upgrade a Section 9.2 copy, then actually downgrade that copy to the old
   source and exact old image digests. Record successful Postgres and
   ClickHouse rollback checks in a root-owned `0600` evidence file.
4. Fetch the new CE source and independently verify the target commit plus the
   three target repo digests.

The evidence file must contain exactly applicable facts, including these four
lines, with the real target commit substituted:

```text
rollback_protocol=plausible-ce-in-place-rollback-v1
pre_upgrade_backup_sha256=<64 lowercase hex SHA256SUMS file checksum>
old_source_commit=<40 lowercase hex current authority commit>
target_source_commit=<40 lowercase hex target commit>
old_postgres_image=<postgres@sha256:... observed before upgrade>
old_clickhouse_image=<clickhouse/clickhouse-server@sha256:... observed before upgrade>
old_plausible_image=<ghcr.io/plausible/community-edition@sha256:... observed before upgrade>
target_postgres_image=<postgres@sha256:...>
target_clickhouse_image=<clickhouse/clickhouse-server@sha256:...>
target_plausible_image=<ghcr.io/plausible/community-edition@sha256:...>
migration_round_trip_test=pass
postgres_rollback_test=pass
clickhouse_rollback_test=pass
```

If either migration is irreversible, the downgrade test fails, or compatibility
is unknown, **do not run the transaction below**. A failed upgrade must instead
recover from the pre-upgrade complete backup through Section 9.2 and promote it
through Section 9.3. Restoring old source and images alone is not a database or
ClickHouse schema rollback.

For a release that passed that real rollback test, export the exact target
commit and digests plus the evidence path, then run this transaction. It creates
a root-only candidate image override, verifies the rendered image set, verifies
the running container image IDs and repo digests, and updates authority last:

```bash
set -euo pipefail
: "${TARGET_SOURCE_COMMIT:?set verified 40-hex target commit}"
: "${TARGET_POSTGRES_IMAGE:?set exact postgres repo digest}"
: "${TARGET_CLICKHOUSE_IMAGE:?set exact clickhouse repo digest}"
: "${TARGET_PLAUSIBLE_IMAGE:?set exact plausible repo digest}"
: "${PRE_UPGRADE_BACKUP_SHA256:?set SHA-256 of tested backup SHA256SUMS}"
: "${ROLLBACK_COMPATIBILITY_EVIDENCE:?set root-only rollback evidence path}"
[[ "$TARGET_SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]]
[[ "$TARGET_POSTGRES_IMAGE" =~ ^postgres@sha256:[0-9a-f]{64}$ ]]
[[ "$TARGET_CLICKHOUSE_IMAGE" =~ ^clickhouse/clickhouse-server@sha256:[0-9a-f]{64}$ ]]
[[ "$TARGET_PLAUSIBLE_IMAGE" =~ ^ghcr.io/plausible/community-edition@sha256:[0-9a-f]{64}$ ]]
[[ "$PRE_UPGRADE_BACKUP_SHA256" =~ ^[0-9a-f]{64}$ ]]
test "$(stat -c '%U:%G %a' "$ROLLBACK_COMPATIBILITY_EVIDENCE")" = \
  'root:root 600'
require_evidence_fact() {
  test "$(grep -Fxc -- "$1" "$ROLLBACK_COMPATIBILITY_EVIDENCE")" = 1
}
require_evidence_fact 'rollback_protocol=plausible-ce-in-place-rollback-v1'
require_evidence_fact \
  "pre_upgrade_backup_sha256=$PRE_UPGRADE_BACKUP_SHA256"
require_evidence_fact "target_source_commit=$TARGET_SOURCE_COMMIT"

authority_file="${PLAUSIBLE_AUTHORITY_FILE:-/root/plausible-ce-authority.env}"
test "$(stat -c '%U:%G %a' "$authority_file")" = 'root:root 600'
. "$authority_file"
test "$PLAUSIBLE_AUTHORITY_PROTOCOL" = 'plausible-ce-authority-v1'
active_dir="$PLAUSIBLE_ACTIVE_DIR"
active_project="$PLAUSIBLE_ACTIVE_PROJECT"
active_port="$PLAUSIBLE_ACTIVE_PORT"
old_source_commit="$PLAUSIBLE_ACTIVE_SOURCE_COMMIT"
authority_root="${PLAUSIBLE_AUTHORITY_ROOT:-/root}"
authority_state_dir="${PLAUSIBLE_AUTHORITY_STATE_DIR:-/root}"
case "$active_dir" in "$authority_root"/*) ;; *) exit 1 ;; esac
[[ "$active_project" =~ ^[a-z0-9][a-z0-9_-]+$ ]]
[[ "$active_port" =~ ^[0-9]+$ ]]
test "$TARGET_SOURCE_COMMIT" != "$old_source_commit"
cd "$active_dir"
test "$(stat -c '%U:%G %a' .env)" = 'root:root 600'
test "$(stat -c '%U:%G %a' compose.override.yml)" = 'root:root 600'
test "$(git rev-parse HEAD)" = "$old_source_commit"
git diff --exit-code
git diff --cached --exit-code
git cat-file -e "$TARGET_SOURCE_COMMIT^{commit}"

current_compose_file="$active_dir/compose.yml:$active_dir/compose.override.yml"
if test -f "$active_dir/compose.restore-images.yml"; then
  current_compose_file="$current_compose_file:$active_dir/compose.restore-images.yml"
fi
COMPOSE_FILE="$current_compose_file" COMPOSE_PROJECT_NAME="$active_project" \
  docker compose config --quiet

repo_digest_for_image_id() {
  local image_id="$1" expected_repo="$2" candidate resolved=''
  while IFS= read -r candidate; do
    [[ "$candidate" =~ ^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$ ]] \
      || continue
    case "$candidate" in
      "$expected_repo"@sha256:*)
        test -z "$resolved" || return 1
        resolved="$candidate"
        ;;
    esac
  done < <(docker image inspect \
    --format '{{range .RepoDigests}}{{println .}}{{end}}' "$image_id")
  test -n "$resolved" || return 1
  printf '%s\n' "$resolved"
}

running_image_identity() {
  local service="$1" expected_repo="$2" compose_file="$3"
  local container_id image_id repo_digest
  container_id="$(COMPOSE_FILE="$compose_file" \
    COMPOSE_PROJECT_NAME="$active_project" \
    docker compose ps --quiet "$service")"
  test -n "$container_id" || return 1
  image_id="$(docker inspect --format '{{.Image}}' "$container_id")"
  test -n "$image_id" || return 1
  repo_digest="$(repo_digest_for_image_id "$image_id" "$expected_repo")"
  test -n "$repo_digest" || return 1
  printf '%s|%s\n' "$image_id" "$repo_digest"
}

assert_running_image() {
  local service="$1" expected_repo="$2" expected_image="$3" compose_file="$4"
  local identity actual_id actual_digest expected_id
  identity="$(running_image_identity "$service" "$expected_repo" "$compose_file")"
  IFS='|' read -r actual_id actual_digest <<< "$identity"
  expected_id="$(docker image inspect --format '{{.Id}}' "$expected_image")"
  test "$actual_id" = "$expected_id" || return 1
  test "$actual_digest" = "$expected_image" || return 1
}

old_postgres_identity="$(running_image_identity \
  plausible_db postgres "$current_compose_file")"
old_clickhouse_identity="$(running_image_identity \
  plausible_events_db clickhouse/clickhouse-server "$current_compose_file")"
old_plausible_identity="$(running_image_identity \
  plausible ghcr.io/plausible/community-edition "$current_compose_file")"
IFS='|' read -r old_postgres_id old_postgres_image <<< "$old_postgres_identity"
IFS='|' read -r old_clickhouse_id old_clickhouse_image <<< "$old_clickhouse_identity"
IFS='|' read -r old_plausible_id old_plausible_image <<< "$old_plausible_identity"

for evidence_fact in \
  "old_source_commit=$old_source_commit" \
  "old_postgres_image=$old_postgres_image" \
  "old_clickhouse_image=$old_clickhouse_image" \
  "old_plausible_image=$old_plausible_image" \
  "target_postgres_image=$TARGET_POSTGRES_IMAGE" \
  "target_clickhouse_image=$TARGET_CLICKHOUSE_IMAGE" \
  "target_plausible_image=$TARGET_PLAUSIBLE_IMAGE" \
  'migration_round_trip_test=pass' \
  'postgres_rollback_test=pass' \
  'clickhouse_rollback_test=pass'; do
  require_evidence_fact "$evidence_fact"
done

for target_image in "$TARGET_POSTGRES_IMAGE" "$TARGET_CLICKHOUSE_IMAGE" \
  "$TARGET_PLAUSIBLE_IMAGE"; do
  docker pull "$target_image" > /dev/null
done

umask 077
upgrade_stamp="$(date -u +%Y%m%d%H%M%S)"
runtime_override="$active_dir/compose.restore-images.yml"
candidate_override="$(mktemp "$active_dir/.compose.upgrade-images.XXXXXX.yml")"
rollback_override="$authority_state_dir/plausible-ce-images.rollback-$upgrade_stamp.yml"
old_authority_backup="$authority_state_dir/plausible-ce-authority.rollback-$upgrade_stamp.env"
write_image_override() {
  local output="$1" postgres_image="$2" clickhouse_image="$3" plausible_image="$4"
  {
    printf '%s\n' 'services:'
    printf '  plausible_db:\n    image: "%s"\n' "$postgres_image"
    printf '  plausible_events_db:\n    image: "%s"\n' "$clickhouse_image"
    printf '  plausible:\n    image: "%s"\n' "$plausible_image"
  } > "$output"
  chown root:root "$output"
  chmod 0600 "$output"
}
publish_runtime_compose_file() {
  local env_candidate
  env_candidate="$(mktemp "$active_dir/.env.upgrade.XXXXXX")" || return 1
  sed '/^COMPOSE_FILE=/d' "$active_dir/.env" > "$env_candidate" || return 1
  printf '%s\n' \
    'COMPOSE_FILE=compose.yml:compose.override.yml:compose.restore-images.yml' \
    >> "$env_candidate" || return 1
  chown root:root "$env_candidate" || return 1
  chmod 0600 "$env_candidate" || return 1
  mv -f "$env_candidate" "$active_dir/.env" || return 1
}
write_image_override "$candidate_override" \
  "$TARGET_POSTGRES_IMAGE" "$TARGET_CLICKHOUSE_IMAGE" \
  "$TARGET_PLAUSIBLE_IMAGE"
write_image_override "$rollback_override" \
  "$old_postgres_image" "$old_clickhouse_image" "$old_plausible_image"
cp --preserve=mode,ownership "$authority_file" "$old_authority_backup"
chmod 0600 "$old_authority_backup"
authority_swapped=0

rollback_upgrade() {
  status=$?
  trap - EXIT
  set +e
  rollback_failed=0
  failure_compose_file="$active_dir/compose.yml:$active_dir/compose.override.yml"
  if test -f "$runtime_override"; then
    failure_compose_file="$failure_compose_file:$runtime_override"
  elif test -n "${candidate_override:-}" && test -f "$candidate_override"; then
    failure_compose_file="$failure_compose_file:$candidate_override"
  fi
  COMPOSE_FILE="$failure_compose_file" COMPOSE_PROJECT_NAME="$active_project" \
    docker compose stop || rollback_failed=1
  git -C "$active_dir" checkout --detach "$old_source_commit" \
    || rollback_failed=1
  rollback_candidate="$(mktemp "$active_dir/.compose.rollback-images.XXXXXX.yml")"
  if [[ -n "$rollback_candidate" ]]; then
    cp "$rollback_override" "$rollback_candidate" || rollback_failed=1
    chown root:root "$rollback_candidate" || rollback_failed=1
    chmod 0600 "$rollback_candidate" || rollback_failed=1
    mv -f "$rollback_candidate" "$runtime_override" || rollback_failed=1
  else
    rollback_failed=1
  fi
  publish_runtime_compose_file || rollback_failed=1
  if (( authority_swapped == 1 )); then
    authority_rollback="$(mktemp "$authority_state_dir/.plausible-ce-authority.XXXXXX")"
    if [[ -n "$authority_rollback" ]]; then
      cp "$old_authority_backup" "$authority_rollback" || rollback_failed=1
      chown root:root "$authority_rollback" || rollback_failed=1
      chmod 0600 "$authority_rollback" || rollback_failed=1
      mv -f "$authority_rollback" "$authority_file" || rollback_failed=1
    else
      rollback_failed=1
    fi
  fi
  old_compose_file="$active_dir/compose.yml:$active_dir/compose.override.yml:$runtime_override"
  COMPOSE_FILE="$old_compose_file" COMPOSE_PROJECT_NAME="$active_project" \
    docker compose up -d --force-recreate || rollback_failed=1
  assert_running_image plausible_db postgres "$old_postgres_image" \
    "$old_compose_file" || rollback_failed=1
  assert_running_image plausible_events_db clickhouse/clickhouse-server \
    "$old_clickhouse_image" "$old_compose_file" || rollback_failed=1
  assert_running_image plausible ghcr.io/plausible/community-edition \
    "$old_plausible_image" "$old_compose_file" || rollback_failed=1
  curl --fail --silent --show-error \
    "http://127.0.0.1:$active_port/api/system/health/ready" \
    > /dev/null || rollback_failed=1
  grep -Fqx "PLAUSIBLE_ACTIVE_SOURCE_COMMIT=$old_source_commit" \
    "$authority_file" || rollback_failed=1
  if test -n "${candidate_override:-}" && test -f "$candidate_override"; then
    rm -f -- "$candidate_override" || rollback_failed=1
  fi
  if (( rollback_failed != 0 )); then
    printf '%s\n' \
      'CRITICAL: Plausible upgrade rollback could not restore source/config/authority/runtime agreement. Recover the complete pre-upgrade backup through Sections 9.2 and 9.3.' \
      >&2
    exit 98
  fi
  exit "$status"
}
trap rollback_upgrade EXIT

git checkout --detach "$TARGET_SOURCE_COMMIT"
target_candidate_compose_file="$active_dir/compose.yml:$active_dir/compose.override.yml:$candidate_override"
COMPOSE_FILE="$target_candidate_compose_file" \
  COMPOSE_PROJECT_NAME="$active_project" docker compose config --quiet
configured_images="$(COMPOSE_FILE="$target_candidate_compose_file" \
  COMPOSE_PROJECT_NAME="$active_project" docker compose config --images)"
test "$(printf '%s\n' "$configured_images" | sed '/^$/d' | wc -l | tr -d ' ')" = 3
expected_images="$(printf '%s\n' "$TARGET_POSTGRES_IMAGE" \
  "$TARGET_CLICKHOUSE_IMAGE" "$TARGET_PLAUSIBLE_IMAGE" | sort)"
test "$(printf '%s\n' "$configured_images" | sort)" = "$expected_images"

mv -f "$candidate_override" "$runtime_override"
candidate_override=''
publish_runtime_compose_file
target_compose_file="$active_dir/compose.yml:$active_dir/compose.override.yml:$runtime_override"
COMPOSE_FILE="$target_compose_file" COMPOSE_PROJECT_NAME="$active_project" \
  docker compose up -d --force-recreate
curl --fail --silent --show-error \
  "http://127.0.0.1:$active_port/api/system/health/ready"
curl --fail --silent --show-error \
  "http://127.0.0.1:$active_port/api/system/health/live"
assert_running_image plausible_db postgres "$TARGET_POSTGRES_IMAGE" \
  "$target_compose_file"
assert_running_image plausible_events_db clickhouse/clickhouse-server \
  "$TARGET_CLICKHOUSE_IMAGE" "$target_compose_file"
assert_running_image plausible ghcr.io/plausible/community-edition \
  "$TARGET_PLAUSIBLE_IMAGE" "$target_compose_file"
COMPOSE_FILE="$target_compose_file" COMPOSE_PROJECT_NAME="$active_project" \
  docker compose exec -T plausible_events_db clickhouse-client \
  --database plausible_events_db \
  --query "SELECT hostname, count() FROM events_v2 WHERE hostname IN ('beta.structural.bytedance.city', 'phase.bytedance.city') GROUP BY hostname ORDER BY hostname FORMAT PrettyCompact"

printf '%s\n' \
  'Send one fresh Beta event and one fresh Phase event. Require 202, no x-plausible-dropped, fresh ClickHouse rows, and both dashboard confirmations.' \
  'Type UPGRADE only after every check passes.'
read -r upgrade_confirmation
test "$upgrade_confirmation" = UPGRADE

authority_candidate="$(mktemp "$authority_state_dir/.plausible-ce-authority.XXXXXX")"
{
  printf '%s\n' 'PLAUSIBLE_AUTHORITY_PROTOCOL=plausible-ce-authority-v1'
  printf 'PLAUSIBLE_ACTIVE_DIR=%s\n' "$active_dir"
  printf 'PLAUSIBLE_ACTIVE_PROJECT=%s\n' "$active_project"
  printf 'PLAUSIBLE_ACTIVE_PORT=%s\n' "$active_port"
  printf 'PLAUSIBLE_ACTIVE_SOURCE_COMMIT=%s\n' "$TARGET_SOURCE_COMMIT"
} > "$authority_candidate"
chown root:root "$authority_candidate"
chmod 0600 "$authority_candidate"
authority_swapped=1
mv -f "$authority_candidate" "$authority_file"
. "$authority_file"
test "$PLAUSIBLE_ACTIVE_SOURCE_COMMIT" = "$TARGET_SOURCE_COMMIT"
test "$(git rev-parse HEAD)" = "$TARGET_SOURCE_COMMIT"
assert_running_image plausible_db postgres "$TARGET_POSTGRES_IMAGE" \
  "$target_compose_file"
assert_running_image plausible_events_db clickhouse/clickhouse-server \
  "$TARGET_CLICKHOUSE_IMAGE" "$target_compose_file"
assert_running_image plausible ghcr.io/plausible/community-edition \
  "$TARGET_PLAUSIBLE_IMAGE" "$target_compose_file"
trap - EXIT
```

Retain the root-only old authority and exact old image override for the rollback
window. Then run Section 9.1 from the new authority; the new backup must record
the target source commit and all three target repo digests. A missing evidence
file, failed rendered-image comparison, failed running-image comparison, failed
readiness check, or rejected manual acceptance leaves authority on the old
commit and invokes the verified rollback path.

## 10. Deployment receipt (fill only after real execution)

### 10.1 Initial production deployment receipt — every row required

- [ ] Application PR number and merge SHA: `__________`
- [ ] Beta deployed SHA: `__________`
- [ ] Phase deployed SHA: `__________`
- [ ] Legacy product reference scan: zero matches at `__________` UTC
- [ ] Pre-deploy DNS A/AAAA: `NXDOMAIN` at `__________` UTC
- [ ] CE source commit: `__________`
- [ ] OCI index digest and linux/amd64 manifest verified: `__________`
- [ ] `/root/plausible-ce` mode `0700`; `.env` and override mode `0600`
- [ ] Only host binding is `127.0.0.1:8800:8000`
- [ ] First administrator created over loopback; registration closed afterward
- [ ] `beta.structural.bytedance.city`, timezone `Asia/Shanghai`, created
- [ ] `phase.bytedance.city`, timezone `Asia/Shanghai`, created
- [ ] HTTP source/target checksum, root-only before-state, installer result, and
      pre-DNS `503`: `__________`
- [ ] DNS change identifier: `__________`
- [ ] Exact `A` convergence at every authoritative server, `1.1.1.1`, and
      `8.8.8.8`, with empty `AAAA`: `__________`
- [ ] Certificate identifier/expiry (no private material): `__________`
- [ ] Final Nginx source/target and before-state checksums, atomic transaction,
      rollback owner, and `nginx -t`: `__________`
- [ ] Exact `/js/script.js` deny returns `410`; dashboard JavaScript still loads
- [ ] Public live and ready health checks pass
- [ ] Beta direct expanded request: `202`, no `x-plausible-dropped`
- [ ] Phase NPM request: `202`, no `x-plausible-dropped`
- [ ] Fresh ClickHouse row confirmed for Beta and Phase
- [ ] Fresh dashboard event confirmed for Beta and Phase
- [ ] All ten Section 8.1 goal rows uniquely configured and individually
      evidenced: `__________`
- [ ] Complete backup path and `SHA256SUMS` verification: `__________`
- [ ] Resolved Postgres, ClickHouse, Plausible, and helper digests verified
- [ ] Root-only config archive (`.env`, compose, runtime override) mode/checksum:
      `__________`
- [ ] age version, X25519 recipients-file approval identifier, execution UTC,
      and ciphertext SHA-256: `__________`
- [ ] Approved off-host object reference and byte-for-byte download verification:
      `__________`
- [ ] Isolated restore drill project, loopback port, and result: `__________`
- [ ] Active authority file checksum and dir/project/port: `__________`

`N/A` is forbidden in Section 10.1. An unchecked or placeholder-only row means
the initial deployment is incomplete.

### 10.2 Disaster recovery and promotion receipt — conditional

Status (write exactly `EXECUTED` or `N/A`): `__________`

If status is `N/A`, leave every checkbox below unchecked and record:

- reason no disaster recovery or promotion was required: `__________`;
- receipt window and unchanged active-authority checksum: `__________`.

`N/A` is invalid after any incident-driven restore or Section 9.3 promotion
command was attempted, after a failure, or merely because evidence is missing.
The mandatory initial Section 9.2 restore drill belongs only to Section 10.1
and does not turn this conditional disaster receipt into `EXECUTED`. If status
is `EXECUTED`, every row below is required:

- [ ] Incident/change identifier, operator, start/end UTC: `__________`
- [ ] Encrypted source object, ciphertext checksum, approved identity reference,
      and successful root-only decryption verification: `__________`
- [ ] Backup `SHA256SUMS`, source commit, authority, and resolved image proofs:
      `__________`
- [ ] Isolated restore project/port and full Section 9.2 proof: `__________`
- [ ] Previous project stopped; rollback authority/volumes retained: `__________`
- [ ] Post-promotion backup resolved from new authority and verified: `__________`
- [ ] Rollback owner and exact previous image/source baseline: `__________`

### 10.3 Upgrade receipt — conditional

Status (write exactly `EXECUTED` or `N/A`): `__________`

If status is `N/A`, leave every checkbox below unchecked and record:

- reason no upgrade was performed: `__________`;
- receipt window and unchanged source/image/authority checksums: `__________`.

`N/A` is invalid after any upgrade command was attempted, after a failed or
rolled-back upgrade, or when evidence is missing. If status is `EXECUTED`,
every row below is required:

- [ ] Change identifier, operator, start/end UTC, source and image baselines:
      `__________`
- [ ] Complete encrypted pre-upgrade backup and isolated restore proof:
      `__________`
- [ ] Upgrade rollback-compatibility evidence path/checksum: `__________`
- [ ] Upgrade rendered target images and running IDs/digests verified: `__________`
- [ ] Upgrade authority switched only after ingestion/dashboard acceptance: `__________`
- [ ] Post-upgrade complete backup and rollback-window owner/expiry: `__________`

Never mark a checkbox for a condition that did not occur; use the conditional
status plus both required `N/A` fields instead. Never backfill any receipt from
assumptions, HTTP status alone, or service/container `active` state.
