"""Fail-closed privacy contract for optional beta analytics."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "web" / "frontend"

AUTH_OR_NONPUBLIC = {
    "auth-callback.html",
    "auth-login.html",
    "auth-verify.html",
    "redesign-mockups/variant-a-perplexity-white.html",
    "redesign-mockups/variant-b-perplexity-ink.html",
}

ANALYTICS_PRIVATE_OR_RETIRED_PAGES = {
    "404",
    "analyze",
    "connections",
    "paper",  # Served through the validated /paper/{public-slug} route.
    "report",
    "reports",
}

PRIVATE_ANALYTICS_BUNDLES = (
    "analyze.js",
    "my-reports.js",
    "report.js",
)


def _relative_html() -> dict[str, str]:
    return {
        str(path.relative_to(FRONTEND)): path.read_text(encoding="utf-8")
        for path in FRONTEND.rglob("*.html")
    }


def test_every_public_beta_page_uses_consent_loader() -> None:
    pages = _relative_html()
    public = {
        name: text for name, text in pages.items() if name not in AUTH_OR_NONPUBLIC
    }

    assert len(public) == 27
    assert all(
        text.count('/assets/js/analytics-consent.js') == 1
        for text in public.values()
    )
    assert all(
        '<script src="https://plausible.bytedance.city/' not in text
        for text in pages.values()
    )
    assert all("plausible.bytedance.city" not in text for text in pages.values())
    assert "data-analytics-settings" in pages["thank-you.html"]


def test_consent_loader_is_explicit_dnt_first_and_fail_closed() -> None:
    source = (FRONTEND / "assets/js/analytics-consent.js").read_text(
        encoding="utf-8"
    )

    assert "navigator.doNotTrack" in source
    assert "analyticsRouteIsSafe()" in source
    for route in ("analyze", "reports", "report"):
        assert f"/^\\/{route}(?:\\.html)?(?:\\/|$)/" in source
    assert "dntEnabled()" in source
    assert "saveChoice(false, 'dnt')" in source
    assert "if (!analyticsRouteIsSafe() || dntEnabled() || installedPlausible) return" in source
    assert "if (!saveChoice(analytics, 'explicit'))" in source
    assert "unloadPlausible();" in source
    assert "data-analytics-choice" in source
    assert "data-analytics-settings" in source
    assert "window.location.assign('/privacy#analytics')" in source
    assert "structural.lang" in source
    assert "You decide whether to share anonymous usage data" in source
    assert "beta.structural.bytedance.city" in source
    assert "https://plausible.bytedance.city/api/event" in source
    assert "current.origin + current.pathname" in source
    assert "referrerPolicy: 'no-referrer'" in source
    assert "credentials: 'omit'" in source
    assert "EVENT_POLICIES" in source
    assert "Object.prototype.hasOwnProperty.call(EVENT_POLICIES, name)" in source
    assert "document.createElement('script')" not in source


def test_analytics_public_allowlist_matches_published_consent_pages() -> None:
    pages = {
        path.stem
        for path in FRONTEND.glob("*.html")
        if "/assets/js/analytics-consent.js" in path.read_text(encoding="utf-8")
    }
    public_pages = pages - ANALYTICS_PRIVATE_OR_RETIRED_PAGES
    expected_routes = {
        "/" if stem == "index" else f"/{stem}" for stem in public_pages
    }
    # Both forms are served for the homepage; every other exact route maps
    # mechanically to one published HTML surface above.
    expected_routes.add("/index")

    source = (FRONTEND / "assets/js/analytics-consent.js").read_text(
        encoding="utf-8"
    )
    route_block = source.split("var ANALYTICS_PUBLIC_ROUTES = [", 1)[1].split(
        "];", 1
    )[0]
    actual_routes = set(re.findall(r"'(/[^']*)'", route_block))

    assert actual_routes == expected_routes
    assert "/pricing" in actual_routes
    assert "/connections" not in actual_routes

    controls = (ROOT / "scripts/check_public_controls.py").read_text(
        encoding="utf-8"
    )
    assert '"/pricing"' in controls.split("DYNAMIC_BETA_PREFIXES", 1)[0]
    retired = controls.split("RETIRED_PUBLIC_PREFIXES = ", 1)[1].split("\n", 1)[0]
    assert '"/pricing"' not in retired
    scan_exclusions = controls.split("def scan_beta()", 1)[1].split(
        "parser = ControlParser", 1
    )[0]
    assert '"pricing.html"' not in scan_exclusions


def test_literal_analytics_callers_exactly_match_event_policies() -> None:
    consent_source = (FRONTEND / "assets/js/analytics-consent.js").read_text(
        encoding="utf-8"
    )
    policy_block = consent_source.split("var EVENT_POLICIES = {", 1)[1].split(
        "\n  };", 1
    )[0]
    policies = set(
        re.findall(r"^    ([a-z][a-z0-9_]*):", policy_block, flags=re.MULTILINE)
    )

    literal_call = re.compile(
        r"(?:window\.)?(?:plausible|trackEvent|trackPlausible|track)"
        r"\s*\(\s*['\"]([a-z][a-z0-9_]*)['\"]"
    )
    literal_events: set[str] = set()
    for path in (*FRONTEND.glob("*.html"), *(FRONTEND / "assets/js").glob("*.js")):
        literal_events.update(literal_call.findall(path.read_text(encoding="utf-8")))

    registry_source = (FRONTEND / "assets/js/analytics.js").read_text(
        encoding="utf-8"
    )
    registry_block = registry_source.split("var EVENTS = {", 1)[1].split(
        "\n  };", 1
    )[0]
    registry_events = set(
        re.findall(r':\s*["\']([a-z][a-z0-9_]*)["\']', registry_block)
    )

    assert literal_events <= policies
    assert registry_events <= policies
    assert policies == literal_events | registry_events | {"pageview"}

    for filename in PRIVATE_ANALYTICS_BUNDLES:
        private_source = (FRONTEND / "assets/js" / filename).read_text(
            encoding="utf-8"
        )
        assert "window.plausible" not in private_source
        assert "trackPlausible" not in private_source
        assert "window.analytics.track" not in private_source
        assert "trackEvent" not in private_source

    catalog = (ROOT / "docs/analytics/plausible-events.md").read_text(
        encoding="utf-8"
    ).split("## Beta event catalog (exhaustive)", 1)[1].split(
        "## How to verify in production", 1
    )[0]
    documented_events = set(
        re.findall(r"^\| `([a-z][a-z0-9_]*)` \|", catalog, flags=re.MULTILINE)
    )
    assert documented_events == policies


def test_legacy_plausible_tracker_urls_are_absent_from_product_and_docs() -> None:
    legacy_urls = (
        "plausible.bytedance.city/js/" + "script.js",
        "plausible.io/js/" + "script.js",
    )
    excluded_parts = {".git", ".next", ".venv", "node_modules"}
    scanned_suffixes = {
        ".conf", ".html", ".js", ".json", ".jsx", ".md", ".mjs",
        ".py", ".sh", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
    }
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if excluded_parts.intersection(relative.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in scanned_suffixes:
            continue
        text = path.read_text(encoding="utf-8")
        if any(legacy in text for legacy in legacy_urls):
            offenders.append(str(relative))
    assert offenders == []


def test_plausible_deployment_runbook_is_pinned_private_and_recoverable() -> None:
    runbook = (ROOT / "docs/analytics/plausible-deployment.md").read_text(
        encoding="utf-8"
    )

    required_baseline = (
        "NOT PUBLICLY DEPLOYED — awaiting application PR merge",
        "v3.2.1",
        "ec6c4da776547516d8f48159ce1a704df4f475ad",
        "e4f5a87a5570bd61605217e7ceb376636db8eddb",
        "sha256:33e60bfb40f2df5da00f8753b76fad04f67dba3abe6d73eb516e440e3fb62985",
        "sha256:7450d9df4bfce160541d65bdba6bd4bcdd9a6db07f13dde91060705fa242c650",
        "/root/plausible-ce",
        "127.0.0.1:8800:8000",
        "chmod 0700 /root/plausible-ce",
        "chmod 0600 .env",
        "chmod 0600 compose.override.yml",
    )
    for contract in required_baseline:
        assert contract in runbook

    for site in ("beta.structural.bytedance.city", "phase.bytedance.city"):
        site_creation = f"Create site `{site}` with timezone `Asia/Shanghai`"
        assert site_creation in runbook

    sections_in_order = (
        "## 3. Preflight: application and DNS must be safe",
        "## 4. Install the pinned CE tree",
        "## 5. Loopback bootstrap and two-site initialization",
        "## 6. Stage HTTP ACME before DNS",
        "## 7. Final Nginx privacy boundary",
        "## 8. Real two-product ingestion acceptance",
    )
    positions = [runbook.index(section) for section in sections_in_order]
    assert positions == sorted(positions)

    event_location = runbook.split("location = /api/event {", 1)[1].split(
        "\n    }", 1
    )[0]
    assert "POST|OPTIONS" in event_location
    assert "access_log off;" in event_location
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in event_location
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" not in runbook
    assert "location = /js/script.js" in runbook
    assert "location /js/" not in runbook
    assert "location ^~ /js/" not in runbook

    for volume in ("db-data", "event-data", "event-logs", "plausible-data"):
        assert volume in runbook
    assert "ClickHouse event data is not replayable from PostgreSQL" in runbook
    assert "NEVER run `docker compose down -v`" in runbook

    backup_contracts = (
        "plausible-ce-complete-v2",
        "plausible-ce-authority-v1",
        "tar -czf \"$backup_dir/config-root-only.tgz\"",
        "config_paths=(.env compose.yml compose.override.yml clickhouse)",
        "config_paths+=(compose.restore-images.yml)",
        "git bundle create \"$backup_dir/source.bundle\" HEAD",
        "cp -- \"$authority_file\" \"$backup_dir/authority.env\"",
        "production_compose_file=\"$production_dir/compose.yml:$production_dir/compose.override.yml\"",
        "COMPOSE_FILE=\"$production_compose_file\" docker compose",
        "postgres.dump",
        "RESOLVED_IMAGES.txt",
        "docker compose ps --quiet \"$service\"",
        "{{range .RepoDigests}}{{println .}}{{end}}",
        "plausible_db) expected_repo=postgres",
        "plausible_events_db) expected_repo=clickhouse/clickhouse-server",
        "plausible) expected_repo=ghcr.io/plausible/community-edition",
        "docker run --rm \"$archive_helper\" tar --help",
        "--volume \"$backup_dir:/backup\" \"$archive_helper\"",
        "MANIFEST.txt",
        "SHA256SUMS",
        "sha256sum --check SHA256SUMS",
        "install -d -o root -g root -m 0700 \"$backup_dir\"",
        "chmod 0600 \"$backup_dir\"/*",
        "pg_restore --list < \"$backup_dir/postgres.dump\" > /dev/null",
        "trap resume_production EXIT",
        "printf 'source_commit=%s\\n' \"$(git rev-parse HEAD)\"",
    )
    for contract in backup_contracts:
        assert contract in runbook

    backup = runbook.split("### 9.1 Consistent root-only backup", 1)[1].split(
        "### 9.2 Isolated restore drill", 1
    )[0]
    backup_order = (
        "docker compose stop plausible",
        "pg_dump --username postgres",
        "docker compose stop plausible_db plausible_events_db",
        "tar -czf \"$backup_dir/config-root-only.tgz\"",
        "sha256sum --check SHA256SUMS",
        "resume_production\ncurl --fail",
    )
    backup_positions = [backup.index(token) for token in backup_order]
    assert backup_positions == sorted(backup_positions)

    restore_contracts = (
        "restore_project=\"plausible-ce-restore-$restore_stamp\"",
        "restore_port=\"${RESTORE_PORT:-18800}\"",
        "tar -xzf \"$SOURCE_BACKUP_DIR/config-root-only.tgz\"",
        "git clone \"$SOURCE_BACKUP_DIR/source.bundle\" \"$restore_dir\"",
        "backup_source_commit=\"$(sed -n 's/^source_commit=//p'",
        "test \"$backup_source_commit\" = \"$authority_source_commit\"",
        "checkout --detach \"$backup_source_commit\"",
        "chown -R root:root \"$restore_dir\"",
        "chmod 0700 \"$restore_dir\"",
        "chmod 0600 \"$restore_dir/.env\" \"$restore_dir/compose.override.yml\"",
        "resolved_image_for()",
        "resolved_image_for plausible_db postgres",
        "plausible_events_db clickhouse/clickhouse-server",
        "plausible ghcr.io/plausible/community-edition",
        "resolved_image_for archive_helper postgres",
        "docker pull \"$resolved_image\" > /dev/null",
        "COMPOSE_FILE=compose.yml:compose.override.yml:compose.restore-images.yml",
        "printf '  plausible_db:\\n    image: \"%s\"\\n' \"$postgres_image\"",
        "printf '  plausible_events_db:\\n    image: \"%s\"\\n' \"$clickhouse_image\"",
        "printf '  plausible:\\n    image: \"%s\"\\n' \"$plausible_image\"",
        "--volume \"$SOURCE_BACKUP_DIR:/backup:ro\" \"$archive_helper\"",
        "\"$postgres_image\" > /dev/null",
        "COMPOSE_FILE=\"$restore_compose_file\" docker compose config --quiet",
        "docker volume create",
        "tar -C /target -xzf \"/backup/$logical.tgz\"",
        "docker compose config --quiet",
        "http://127.0.0.1:$restore_port/api/system/health/ready",
        "logical_pg_container=\"${restore_project}-logical-pg\"",
        "pg_restore --username postgres --dbname plausible_db",
        "Do not change Nginx or DNS during a drill",
        "### 9.3 Disaster promotion and failed-restore rollback",
    )
    for contract in restore_contracts:
        assert contract in runbook

    restore = runbook.split("### 9.2 Isolated restore drill", 1)[1].split(
        "### 9.3 Disaster promotion and failed-restore rollback", 1
    )[0]
    assert restore.index("sha256sum --check SHA256SUMS") < restore.index(
        "tar -xzf \"$SOURCE_BACKUP_DIR/config-root-only.tgz\""
    )
    assert restore.index("docker compose up -d") < restore.index(
        "api/system/health/ready"
    )
    assert "cat .env" not in runbook
    assert "cat /root/plausible-ce/.env" not in runbook
    assert "docker compose config >" not in runbook
    assert "docker compose down --volumes" not in runbook
    assert "docker tag" not in runbook
    assert "docker pull alpine:3.21" not in runbook
    assert "ce_version=" not in runbook
    assert "oci_index_digest=" not in runbook

    authority_contracts = (
        "/root/plausible-ce-authority.env",
        "PLAUSIBLE_AUTHORITY_PROTOCOL=plausible-ce-authority-v1",
        "production_dir=\"$PLAUSIBLE_ACTIVE_DIR\"",
        "production_project=\"$PLAUSIBLE_ACTIVE_PROJECT\"",
        "backup_dir=\"$backup_root/$production_project/$stamp\"",
        "rollback_promotion()",
        "mv -f \"$authority_candidate\" \"$authority_file\"",
        "compose_project \"$old_dir\" \"$old_project\" stop",
        "restored_source_commit=\"$(git -C \"$RESTORED_DIR\" rev-parse HEAD)\"",
        "PLAUSIBLE_ACTIVE_SOURCE_COMMIT=%s\\n' \"$restored_source_commit\"",
        "Then run Section 9.1 from the new authority",
        "cd \"$PLAUSIBLE_ACTIVE_DIR\"",
        "export COMPOSE_PROJECT_NAME=\"$PLAUSIBLE_ACTIVE_PROJECT\"",
    )
    for contract in authority_contracts:
        assert contract in runbook
    promotion = runbook.split(
        "### 9.3 Disaster promotion and failed-restore rollback", 1
    )[1].split("### 9.4 Upgrades", 1)[0]
    assert promotion.index("authority_swapped=1") < promotion.index(
        'mv -f "$authority_candidate" "$authority_file"'
    )
    assert "rollback_failed=0" in promotion
    assert "CRITICAL: Plausible promotion rollback" in promotion
    assert "COMPOSE_FILE=\"$compose_file\" COMPOSE_PROJECT_NAME=\"$project_name\"" in promotion
    assert "compose_project \"$old_dir\" \"$old_project\" stop" in promotion
    assert "Then run Section 9.1 from the new authority" in promotion

    assert "direct expanded Events API request" in runbook
    assert "@plausible-analytics/tracker" in runbook
    assert runbook.count("no `x-plausible-dropped` header") == 2
    assert "fresh row for each hostname" in runbook
    assert "dashboard confirmations" in runbook
    assert "## 10. Deployment receipt (fill only after real execution)" in runbook

    forbidden_legacy_claims = (
        "v2.1.4",
        "ClickHouse events DB is replayable from Postgres",
        "don't bother backing it up",
        "127.0.0.1:8000:8000",
        "Domain: `structural.bytedance.city`",
        "no consent banner required",
        "The site snippet is harmless",
        "minor versions are non-breaking",
        "Zero data loss",
    )
    for claim in forbidden_legacy_claims:
        assert claim not in runbook

    assert "43.156.233.71" not in runbook
    assert re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", runbook) is None
    assert "- [x]" not in runbook.lower()


def test_plausible_runbook_closes_operational_receipt_and_backup_gates() -> None:
    runbook = (ROOT / "docs/analytics/plausible-deployment.md").read_text(
        encoding="utf-8"
    )
    events = (ROOT / "docs/analytics/plausible-events.md").read_text(
        encoding="utf-8"
    )

    assert "**Runbook version:** 1.3.0" in runbook
    nginx_contracts = (
        "/root/plausible-nginx-source/plausible-acme-http.conf",
        "/root/plausible-nginx-source/plausible-final-tls.conf",
        "/etc/nginx/conf.d/plausible.bytedance.city.conf",
        "/root/scripts/install-nginx-privacy-vhost.sh",
        "/var/lib/structural-isomorphism/nginx-privacy/",
        'bash "$nginx_installer" "$nginx_source" "$nginx_target"',
        "plausible.bytedance.city plausible_acme_privacy",
        "rollback_final_nginx()",
        "nginx_lock_dir=/run/lock/plausible-nginx-vhost.lock.d",
        'mkdir -m 0700 "$nginx_lock_dir"',
        "trap cleanup_final_transaction EXIT",
        'mv -f "$final_candidate" "$nginx_target"',
        "CRITICAL: final Nginx rollback failed; backup retained.",
    )
    for contract in nginx_contracts:
        assert contract in runbook

    nginx_blocks = re.findall(
        r"^```nginx\n(.*?)^```$", runbook, flags=re.MULTILINE | re.DOTALL
    )
    acme_sources = [
        block for block in nginx_blocks if "plausible_acme_privacy" in block
    ]
    assert len(acme_sources) == 1
    acme_source = acme_sources[0]
    acme_log_format = acme_source.split("log_format plausible_acme_privacy", 1)[
        1
    ].split(";", 1)[0]
    assert set(re.findall(r"\$[A-Za-z_][A-Za-z0-9_]*", acme_log_format)) == {
        "$request_method",
        "$status",
        "$body_bytes_sent",
        "$request_time",
        "$upstream_response_time",
        "$request_id",
    }
    assert acme_source.count("server {") == 1
    assert acme_source.count(
        "access_log /var/log/nginx/access.log plausible_acme_privacy;"
    ) == 1
    assert acme_source.count("error_log /dev/null crit;") == 1
    assert acme_source.count("add_header Referrer-Policy no-referrer always;") == 1
    assert acme_source.count("proxy_hide_header Referrer-Policy;") == 1

    acme = runbook.split("## 6. Stage HTTP ACME before DNS", 1)[1].split(
        "## 7. Final Nginx privacy boundary", 1
    )[0]
    dns_contracts = (
        "dig +short @1.1.1.1 bytedance.city NS",
        "for resolver in $authoritative_ns 1.1.1.1 8.8.8.8",
        'test "$ipv4_answers" = "$VPS_PUBLIC_IP"',
        "wc -l | tr -d ' '",
        'dig +short "@$resolver" plausible.bytedance.city AAAA',
    )
    for contract in dns_contracts:
        assert contract in acme
    assert acme.index("bash \"$nginx_installer\"") < acme.index(
        "tccli dnspod CreateRecord"
    )
    assert acme.index("tccli dnspod CreateRecord") < acme.index(
        "for resolver in $authoritative_ns 1.1.1.1 8.8.8.8"
    )
    assert acme.index("for resolver in $authoritative_ns 1.1.1.1 8.8.8.8") < (
        acme.index("certbot certonly")
    )

    encryption_blocks = [
        block for block in _plausible_runbook_bash_blocks() if "age --encrypt" in block
    ]
    assert len(encryption_blocks) == 1
    encryption = encryption_blocks[0]
    encryption_contracts = (
        '"${PLAUSIBLE_BACKUP_RECIPIENTS_FILE:',
        '"${PLAUSIBLE_OFFHOST_TARGET:',
        "AGE-SECRET-KEY-",
        'age_version="$(age --version 2>/dev/null)"',
        "^v?1\\.[0-9]+",
        "END { if (!seen) exit 1 }",
        'recipient_snapshot="$(mktemp',
        'cmp -s "$PLAUSIBLE_BACKUP_RECIPIENTS_FILE" "$recipient_snapshot"',
        'sha256sum --check SHA256SUMS',
        'tar --format=posix -cf - -- "${archive_files[@]}"',
        "age --encrypt",
        '--recipients-file "$recipient_snapshot"',
        'rclone copyto --immutable "$encrypted_artifact"',
        'rclone copyto "$PLAUSIBLE_OFFHOST_TARGET" "$verification_copy"',
        'cmp -s "$encrypted_artifact" "$verification_copy"',
        'cmp -s "$checksum_file" "$checksum_verification_copy"',
        'test "$retrieved_sha256" = "$ciphertext_sha256"',
    )
    for contract in encryption_contracts:
        assert contract in encryption
    assert "PLAUSIBLE_BACKUP_RECIPIENTS_FILE=" not in encryption
    assert "PLAUSIBLE_OFFHOST_TARGET=" not in encryption
    assert "s3://" not in encryption
    assert "scp " not in encryption

    initial_receipt = runbook.split(
        "### 10.1 Initial production deployment receipt — every row required", 1
    )[1].split(
        "### 10.2 Disaster recovery and promotion receipt — conditional", 1
    )[0]
    recovery_receipt = runbook.split(
        "### 10.2 Disaster recovery and promotion receipt — conditional", 1
    )[1].split("### 10.3 Upgrade receipt — conditional", 1)[0]
    upgrade_receipt = runbook.split(
        "### 10.3 Upgrade receipt — conditional", 1
    )[1]
    assert "`N/A` is forbidden in Section 10.1" in initial_receipt
    assert "Previous project stopped" not in initial_receipt
    assert "Upgrade rollback-compatibility" not in initial_receipt
    assert "Previous project stopped" in recovery_receipt
    assert "Status (write exactly `EXECUTED` or `N/A`)" in recovery_receipt
    assert "after any incident-driven restore or Section 9.3 promotion" in (
        recovery_receipt
    )
    assert "initial Section 9.2 restore drill belongs only to Section 10.1" in (
        recovery_receipt
    )
    assert "Status (write exactly `EXECUTED` or `N/A`)" in upgrade_receipt
    assert "after any upgrade command was attempted" in upgrade_receipt
    assert "Upgrade rollback-compatibility" in upgrade_receipt

    goal_rows = re.findall(
        r"^\| `(beta\.structural\.bytedance\.city|phase\.bytedance\.city)` "
        r"\| `([a-z_]+)` \| \[ \] \| `__________` \|$",
        runbook,
        flags=re.MULTILINE,
    )
    configured_goals: dict[str, set[str]] = {}
    for site, event in goal_rows:
        configured_goals.setdefault(site, set()).add(event)
    assert configured_goals == {
        "beta.structural.bytedance.city": {
            "waitlist_signup",
            "waitlist_error",
            "thank_you_view",
            "thank_you_share",
        },
        "phase.bytedance.city": {
            "screener_filter_applied",
            "company_viewed",
            "waitlist_signup",
            "waitlist_error",
            "methodology_opened",
            "thank_you_share",
        },
    }
    goal_highlights = events.split("## Phase Detector goal highlights", 1)[1].split(
        "## Beta event catalog (exhaustive)", 1
    )[0]
    yes_goals = set(
        re.findall(
            r"^\| `([a-z_]+)` \|.*\| (?:\*\*)?yes\b",
            goal_highlights,
            flags=re.MULTILINE | re.IGNORECASE,
        )
    )
    assert yes_goals == set().union(*configured_goals.values())


def _plausible_runbook_bash_blocks() -> list[str]:
    runbook = (ROOT / "docs/analytics/plausible-deployment.md").read_text(
        encoding="utf-8"
    )
    return re.findall(r"^```bash\n(.*?)^```$", runbook, flags=re.MULTILINE | re.DOTALL)


def test_plausible_bash_blocks_parse_separately_and_secret_bootstrap_is_inert(
    tmp_path: Path,
) -> None:
    blocks = _plausible_runbook_bash_blocks()
    assert blocks
    for index, block in enumerate(blocks):
        syntax = subprocess.run(
            ["bash", "-n"],
            input=block,
            text=True,
            capture_output=True,
            check=False,
        )
        assert syntax.returncode == 0, f"bash block {index}: {syntax.stderr}"

    secret_blocks = [block for block in blocks if "secret_key_base=" in block]
    assert len(secret_blocks) == 1
    secret_block = secret_blocks[0]
    assert "resume_production" not in secret_block
    assert "trap " not in secret_block

    secret_dir = tmp_path / "secret-bootstrap"
    secret_dir.mkdir(mode=0o700)
    executable = secret_block.replace(
        "cd /root/plausible-ce", 'cd "$TEST_SECRET_DIR"'
    )
    executable = (
        "set -euo pipefail\n"
        + executable
        + "\nif declare -F resume_production > /dev/null; then exit 91; fi\n"
        + 'test -z "$(trap -p EXIT)"\n'
    )
    result = subprocess.run(
        ["bash"],
        input=executable,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "TEST_SECRET_DIR": str(secret_dir)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert (secret_dir / ".env").stat().st_mode & 0o777 == 0o600


def test_final_nginx_transaction_swaps_or_restores_atomically(tmp_path: Path) -> None:
    blocks = _plausible_runbook_bash_blocks()
    final_blocks = [block for block in blocks if "rollback_final_nginx()" in block]
    assert len(final_blocks) == 1
    transaction = final_blocks[0]

    real_install = shutil.which("install")
    real_stat = shutil.which("stat")
    assert real_install is not None
    assert real_stat is not None

    mock_bin = tmp_path / "final-nginx-mocks"
    mock_bin.mkdir()
    mocks = {
        "install": r'''#!/usr/bin/env bash
set -euo pipefail
arguments=()
while (( "$#" )); do
  case "$1" in
    -o|-g) shift 2 ;;
    *) arguments+=("$1"); shift ;;
  esac
done
exec "$REAL_INSTALL" "${arguments[@]}"
''',
        "stat": r'''#!/usr/bin/env bash
set -euo pipefail
test "$1" = -c
format="$2"
path="$3"
if "$REAL_STAT" -c '%a' "$path" >/dev/null 2>&1; then
  mode="$("$REAL_STAT" -c '%a' "$path")"
else
  mode="$("$REAL_STAT" -f '%Lp' "$path")"
fi
case "$format" in
  '%a') printf '%s\n' "$mode" ;;
  '%U:%G %a') printf 'root:root %s\n' "$mode" ;;
  *) exit 2 ;;
esac
''',
        "sync": r'''#!/usr/bin/env bash
set -euo pipefail
count=0
test ! -f "$MOCK_STATE/sync-count" || \
  count="$(<"$MOCK_STATE/sync-count")"
count=$((count + 1))
printf '%s\n' "$count" > "$MOCK_STATE/sync-count"
case "${MOCK_FAIL_STAGE:-}" in
  sync-before-traps) test "$count" -ne 1 ;;
  sync-after-mv) test "$count" -ne 3 ;;
esac
''',
        "nginx": r'''#!/usr/bin/env bash
set -euo pipefail
test "$1" = -t
count=0
test ! -f "$MOCK_STATE/nginx-count" || \
  count="$(<"$MOCK_STATE/nginx-count")"
count=$((count + 1))
printf '%s\n' "$count" > "$MOCK_STATE/nginx-count"
case "${MOCK_FAIL_STAGE:-}" in
  nginx-first) test "$count" -ne 1 ;;
  nginx-after-reload) test "$count" -ne 2 ;;
esac
''',
        "systemctl": r'''#!/usr/bin/env bash
set -euo pipefail
test "$1" = reload && test "$2" = nginx
count=0
test ! -f "$MOCK_STATE/reload-count" || \
  count="$(<"$MOCK_STATE/reload-count")"
count=$((count + 1))
printf '%s\n' "$count" > "$MOCK_STATE/reload-count"
if [[ "${MOCK_FAIL_STAGE:-}" == reload && "$count" == 1 ]]; then
  exit 1
fi
''',
        "curl": r'''#!/usr/bin/env bash
set -euo pipefail
url="${*: -1}"
case "$url" in
  */api/system/health/*)
    test "${MOCK_FAIL_STAGE:-}" != health
    ;;
  */js/script.js)
    if [[ "${MOCK_FAIL_STAGE:-}" == tracker ]]; then
      printf '%s' 200
    else
      printf '%s' 410
    fi
    ;;
  *) exit 2 ;;
esac
''',
    }
    for name, source in mocks.items():
        path = mock_bin / name
        path.write_text(source, encoding="utf-8")
        path.chmod(0o700)

    cases = {
        "success": 0,
        "sync-before-traps": 1,
        "sync-after-mv": 1,
        "nginx-first": 1,
        "nginx-after-reload": 1,
        "reload": 1,
        "health": 1,
        "tracker": 1,
    }
    for stage, expected_failure in cases.items():
        case_dir = tmp_path / stage
        source_dir = case_dir / "source"
        target_dir = case_dir / "conf.d"
        backup_dir = source_dir / "backups"
        lock_dir = case_dir / "run/lock/plausible-nginx-vhost.lock.d"
        source_dir.mkdir(parents=True, mode=0o700)
        target_dir.mkdir(parents=True)
        lock_dir.parent.mkdir(parents=True)
        source = source_dir / "plausible-final-tls.conf"
        target = target_dir / "plausible.bytedance.city.conf"
        source.write_text("new-final-vhost\n", encoding="utf-8")
        source.chmod(0o600)
        target.write_text("old-http-stage\n", encoding="utf-8")
        target.chmod(0o640)

        replacements = {
            "nginx_source=/root/plausible-nginx-source/plausible-final-tls.conf": (
                f"nginx_source={shlex.quote(str(source))}"
            ),
            "nginx_target=/etc/nginx/conf.d/plausible.bytedance.city.conf": (
                f"nginx_target={shlex.quote(str(target))}"
            ),
            "nginx_target_dir=/etc/nginx/conf.d": (
                f"nginx_target_dir={shlex.quote(str(target_dir))}"
            ),
            "nginx_source_dir=/root/plausible-nginx-source": (
                f"nginx_source_dir={shlex.quote(str(source_dir))}"
            ),
            "nginx_backup_dir=/root/plausible-nginx-source/backups": (
                f"nginx_backup_dir={shlex.quote(str(backup_dir))}"
            ),
            "nginx_lock_dir=/run/lock/plausible-nginx-vhost.lock.d": (
                f"nginx_lock_dir={shlex.quote(str(lock_dir))}"
            ),
            'test "$(id -u)" = 0': ": # test executes without root ownership",
        }
        executable = transaction
        for original, replacement in replacements.items():
            assert original in executable
            executable = executable.replace(original, replacement, 1)

        state = case_dir / "state"
        state.mkdir()
        result = subprocess.run(
            ["bash"],
            input=executable,
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "PATH": f"{mock_bin}:{os.environ['PATH']}",
                "MOCK_FAIL_STAGE": "" if stage == "success" else stage,
                "MOCK_STATE": str(state),
                "REAL_INSTALL": real_install,
                "REAL_STAT": real_stat,
            },
        )

        backups = list(backup_dir.glob("pre-final-*.conf"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == "old-http-stage\n"
        assert not lock_dir.exists()
        assert list(target_dir.glob(".plausible-final.*")) == []
        if expected_failure:
            assert result.returncode != 0
            assert target.read_text(encoding="utf-8") == "old-http-stage\n"
            assert target.stat().st_mode & 0o777 == 0o640
        else:
            assert result.returncode == 0, result.stderr
            assert target.read_text(encoding="utf-8") == "new-final-vhost\n"
            assert target.stat().st_mode & 0o777 == 0o644


def test_initial_authority_is_published_only_after_readiness(tmp_path: Path) -> None:
    blocks = _plausible_runbook_bash_blocks()
    authority_blocks = [
        block for block in blocks if "PLAUSIBLE_INITIAL_ACTIVE_DIR" in block
    ]
    assert len(authority_blocks) == 1
    authority_block = authority_blocks[0]
    assert authority_block.startswith("set -euo pipefail\n")
    assert authority_block.index("api/system/health/ready") < authority_block.index(
        'mv -f "$authority_candidate" "$authority_file"'
    )

    mock_bin = tmp_path / "authority-mocks"
    mock_bin.mkdir()
    scripts = {
        "docker": "#!/usr/bin/env bash\n"
        "printf '%s\\n' up >> \"$MOCK_LOG\"\n"
        "if [[ \"${MOCK_FAIL_STAGE:-}\" == docker ]]; then exit 31; fi\n",
        "curl": "#!/usr/bin/env bash\n"
        "printf '%s\\n' ready >> \"$MOCK_LOG\"\n"
        "if [[ \"${MOCK_FAIL_STAGE:-}\" == curl ]]; then exit 32; fi\n",
        "chown": "#!/usr/bin/env bash\nexit 0\n",
    }
    for name, source in scripts.items():
        path = mock_bin / name
        path.write_text(source, encoding="utf-8")
        path.chmod(0o700)

    for stage in ("success", "docker", "curl"):
        case_dir = tmp_path / f"authority-{stage}"
        active_dir = case_dir / "active"
        state_dir = case_dir / "state"
        active_dir.mkdir(parents=True)
        state_dir.mkdir()
        env_file = active_dir / ".env"
        env_file.write_text("test-only\n", encoding="utf-8")
        env_file.chmod(0o600)
        authority_file = state_dir / "authority.env"
        log = case_dir / "calls.log"
        log.touch()
        result = subprocess.run(
            ["bash"],
            input=authority_block,
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "PATH": f"{mock_bin}:{os.environ['PATH']}",
                "MOCK_FAIL_STAGE": "" if stage == "success" else stage,
                "MOCK_LOG": str(log),
                "PLAUSIBLE_AUTHORITY_FILE": str(authority_file),
                "PLAUSIBLE_AUTHORITY_STATE_DIR": str(state_dir),
                "PLAUSIBLE_INITIAL_ACTIVE_DIR": str(active_dir),
                "PLAUSIBLE_INITIAL_ACTIVE_PORT": "18800",
            },
        )
        calls = log.read_text(encoding="utf-8").splitlines()
        if stage == "success":
            assert result.returncode == 0, result.stderr
            assert calls == ["up", "ready"]
            assert authority_file.is_file()
            assert authority_file.stat().st_mode & 0o777 == 0o600
            authority = authority_file.read_text(encoding="utf-8")
            assert f"PLAUSIBLE_ACTIVE_DIR={active_dir}" in authority
            assert "PLAUSIBLE_ACTIVE_PORT=18800" in authority
        else:
            assert result.returncode != 0
            assert not authority_file.exists()


def test_plausible_backup_block_resumes_once_on_success_and_failures(
    tmp_path: Path,
) -> None:
    blocks = _plausible_runbook_bash_blocks()
    backup_blocks = [
        block for block in blocks if "backup_protocol=%s" in block
    ]
    assert len(backup_blocks) == 1
    backup_block = backup_blocks[0]
    assert backup_block.startswith("set -euo pipefail\n")
    assert "trap resume_production EXIT" in backup_block
    assert "resume_production\ncurl --fail" in backup_block
    assert backup_block.rindex("api/system/health/ready") < backup_block.rindex(
        "trap - EXIT"
    )

    mock_bin = tmp_path / "mock-bin"
    mock_bin.mkdir()
    mocks = {
        "docker": r'''#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == compose ]]; then
  expected="$TEST_PRODUCTION_DIR/compose.yml:$TEST_PRODUCTION_DIR/compose.override.yml"
  [[ "${COMPOSE_FILE:-}" == "$expected" || \
    "${COMPOSE_FILE:-}" == "$expected:"* ]] || exit 45
fi
if [[ "${1:-}" == compose && "${2:-}" == stop && "${3:-}" == plausible && "$#" == 3 ]]; then
  printf '%s\n' stop-writer >> "$MOCK_LOG"
  exit 0
fi
if [[ "${1:-}" == compose && "${2:-}" == up ]]; then
  printf '%s\n' resume >> "$MOCK_LOG"
  exit 0
fi
if [[ "${1:-}" == compose && "${2:-}" == ps ]]; then
  printf 'mock-%s\n' "${@: -1}"
  exit 0
fi
if [[ "${1:-}" == inspect ]]; then
  printf 'image-%s\n' "${@: -1}"
  exit 0
fi
if [[ "${1:-}" == image && "${2:-}" == inspect ]]; then
  case "${@: -1}" in
    image-mock-plausible_db) repo=postgres ;;
    image-mock-plausible_events_db) repo=clickhouse/clickhouse-server ;;
    image-mock-plausible) repo=ghcr.io/plausible/community-edition ;;
    alpine:3.21) repo=alpine ;;
    *) exit 44 ;;
  esac
  printf '%s@sha256:%s\n' "$repo" \
    aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  exit 0
fi
if [[ "${1:-}" == pull ]]; then
  exit 0
fi
if [[ " $* " == *" pg_dump "* ]]; then
  if [[ "${MOCK_FAIL_STAGE:-}" == docker ]]; then exit 40; fi
  printf '%s\n' mock-postgres-dump
  exit 0
fi
if [[ " $* " == *" pg_restore "* ]]; then
  command cat > /dev/null
  exit 0
fi
if [[ "${1:-}" == compose && "${2:-}" == stop ]]; then
  printf '%s\n' stop-databases >> "$MOCK_LOG"
  exit 0
fi
if [[ "${1:-}" == volume && "${2:-}" == ls ]]; then
  printf '%s\n' mock-volume
  exit 0
fi
if [[ "${1:-}" == run ]]; then
  if [[ " $* " == *" tar --help "* ]]; then exit 0; fi
  archive=''
  for argument in "$@"; do
    case "$argument" in /backup/*.tgz) archive="${argument##*/}" ;; esac
  done
  backup_dir=''
  backup_dir="$(find "$MOCK_BACKUP_ROOT" -mindepth 2 -maxdepth 2 -type d | head -1)"
  test -n "$archive"
  test -n "$backup_dir"
  : > "$backup_dir/$archive"
  exit 0
fi
exit 0
''',
        "tar": r'''#!/usr/bin/env bash
set -euo pipefail
if [[ "${MOCK_FAIL_STAGE:-}" == tar && " $* " == *" -czf "* ]]; then exit 41; fi
while (( "$#" )); do
  case "$1" in
    -czf) : > "$2"; exit 0 ;;
    -tzf) test -f "$2"; exit ;;
  esac
  shift
done
exit 0
''',
        "sha256sum": r'''#!/usr/bin/env bash
set -euo pipefail
if [[ "${MOCK_FAIL_STAGE:-}" == sha256 && "${1:-}" == --check ]]; then exit 42; fi
exec "$REAL_SHA256SUM" "$@"
''',
        "install": r'''#!/usr/bin/env bash
set -euo pipefail
target=''
for argument in "$@"; do target="$argument"; done
mkdir -p "$target"
chmod 0700 "$target"
''',
        "stat": r'''#!/usr/bin/env bash
set -euo pipefail
last=''
for argument in "$@"; do last="$argument"; done
case "$last" in */backups/*) printf '%s\n' 'root:root 700' ;; *) printf '%s\n' 'root:root 600' ;; esac
''',
        "git": r'''#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == bundle && "${2:-}" == create ]]; then
  : > "$3"
  exit 0
fi
printf '%s\n' ec6c4da776547516d8f48159ce1a704df4f475ad
''',
        "chown": "#!/usr/bin/env bash\nexit 0\n",
        "curl": "#!/usr/bin/env bash\n"
        "if [[ \"${MOCK_FAIL_STAGE:-}\" == curl ]]; then exit 43; fi\n"
        "exit 0\n",
    }
    for name, source in mocks.items():
        path = mock_bin / name
        path.write_text(source, encoding="utf-8")
        path.chmod(0o700)

    real_sha256sum = shutil.which("sha256sum")
    assert real_sha256sum is not None
    for stage in ("success", "docker", "tar", "sha256", "curl"):
        case_dir = tmp_path / stage
        production_dir = case_dir / "production"
        backup_root = case_dir / "backups"
        production_dir.mkdir(parents=True)
        backup_root.mkdir(parents=True)
        (production_dir / "clickhouse").mkdir()
        for filename in (".env", "compose.yml", "compose.override.yml"):
            path = production_dir / filename
            path.write_text("test-only\n", encoding="utf-8")
            path.chmod(0o600)
        (production_dir / "clickhouse/config.xml").write_text(
            "<clickhouse/>\n", encoding="utf-8"
        )
        log = case_dir / "calls.log"
        log.touch()
        authority_file = case_dir / "authority.env"
        authority_file.write_text(
            "PLAUSIBLE_AUTHORITY_PROTOCOL=plausible-ce-authority-v1\n"
            f"PLAUSIBLE_ACTIVE_DIR={production_dir}\n"
            "PLAUSIBLE_ACTIVE_PROJECT=plausible-ce\n"
            "PLAUSIBLE_ACTIVE_PORT=8800\n"
            "PLAUSIBLE_ACTIVE_SOURCE_COMMIT="
            "ec6c4da776547516d8f48159ce1a704df4f475ad\n",
            encoding="utf-8",
        )
        authority_file.chmod(0o600)

        executable = backup_block
        if stage == "success":
            executable += '\ntest -z "$(trap -p EXIT)"\n'
        env = {
            **os.environ,
            "PATH": f"{mock_bin}:{os.environ['PATH']}",
            "REAL_SHA256SUM": real_sha256sum,
            "MOCK_BACKUP_ROOT": str(backup_root),
            "MOCK_FAIL_STAGE": "" if stage == "success" else stage,
            "MOCK_LOG": str(log),
            "PLAUSIBLE_AUTHORITY_FILE": str(authority_file),
            "PLAUSIBLE_AUTHORITY_ROOT": str(case_dir),
            "PLAUSIBLE_BACKUP_ROOT": str(backup_root),
            "TEST_BACKUP_ROOT": str(backup_root),
            "TEST_PRODUCTION_DIR": str(production_dir),
        }
        result = subprocess.run(
            ["bash"],
            input=executable,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        calls = log.read_text(encoding="utf-8").splitlines()
        assert "stop-writer" in calls
        assert calls.count("resume") == 1
        assert calls.index("stop-writer") < calls.index("resume")
        if stage == "success":
            assert result.returncode == 0, result.stderr
            assert "stop-databases" in calls
        else:
            assert result.returncode != 0


def test_promotion_switches_one_authority_and_rolls_back_failures(
    tmp_path: Path,
) -> None:
    blocks = _plausible_runbook_bash_blocks()
    promotion_blocks = [block for block in blocks if "rollback_promotion()" in block]
    assert len(promotion_blocks) == 1
    promotion_block = promotion_blocks[0]

    mock_bin = tmp_path / "promotion-mocks"
    mock_bin.mkdir()
    scripts = {
        "stat": "#!/usr/bin/env bash\nprintf '%s\\n' 'root:root 600'\n",
        "git": "#!/usr/bin/env bash\nprintf '%s\\n' "
        "ec6c4da776547516d8f48159ce1a704df4f475ad\n",
        "chown": "#!/usr/bin/env bash\nexit 0\n",
        "curl": "#!/usr/bin/env bash\n"
        "printf '%s\\n' health >> \"$MOCK_LOG\"\nexit 0\n",
        "docker": r'''#!/usr/bin/env bash
set -euo pipefail
project="${COMPOSE_PROJECT_NAME:-unset}"
if [[ "$project" == restored ]]; then
  case "${COMPOSE_FILE:-}" in
    *:*/compose.restore-images.yml) ;;
    *) exit 68 ;;
  esac
fi
if [[ "${1:-}" == compose && "${2:-}" == stop && "${3:-}" == plausible ]]; then
  printf 'stop:%s:plausible\n' "$project" >> "$MOCK_LOG"
  if [[ "${MOCK_PROMOTION_FAIL:-}" == candidate-stop && "$project" == restored ]]; then
    exit 66
  fi
  exit 0
fi
if [[ "${1:-}" == compose && "${2:-}" == up ]]; then
  printf 'up:%s\n' "$project" >> "$MOCK_LOG"
  if [[ "${MOCK_PROMOTION_FAIL:-}" == candidate-start && "$project" == restored ]]; then
    exit 61
  fi
  if [[ "${MOCK_PROMOTION_FAIL:-}" == old-start && "$project" == old ]]; then
    exit 62
  fi
  exit 0
fi
if [[ "${1:-}" == compose && "${2:-}" == stop ]]; then
  printf 'stop:%s:all\n' "$project" >> "$MOCK_LOG"
  if [[ "$project" == old && ( "${MOCK_PROMOTION_FAIL:-}" == after-swap || "${MOCK_PROMOTION_FAIL:-}" == restore-mv ) ]]; then
    exit 63
  fi
  exit 0
fi
if [[ "${1:-}" == compose && "${2:-}" == exec ]]; then
  printf 'clickhouse:%s\n' "$project" >> "$MOCK_LOG"
  exit 0
fi
exit 0
''',
        "cp": r'''#!/usr/bin/env bash
set -euo pipefail
args=()
for argument in "$@"; do
  case "$argument" in --preserve=*) ;; *) args+=("$argument") ;; esac
done
exec /bin/cp "${args[@]}"
''',
        "sed": r'''#!/usr/bin/env bash
set -euo pipefail
test "${1:-}" = -i
test "${2:-}" = -E
expression="$3"
file="$4"
/usr/bin/sed -E "$expression" "$file" > "$file.tmp"
/bin/mv "$file.tmp" "$file"
''',
        "mv": r'''#!/usr/bin/env bash
set -euo pipefail
count=0
if [[ -f "$MOCK_MV_COUNT" ]]; then count="$(cat "$MOCK_MV_COUNT")"; fi
count=$((count + 1))
printf '%s\n' "$count" > "$MOCK_MV_COUNT"
if [[ "${MOCK_PROMOTION_FAIL:-}" == candidate-mv && "$count" == 1 ]]; then exit 64; fi
if [[ "${MOCK_PROMOTION_FAIL:-}" == restore-mv && "$count" -ge 2 ]]; then exit 65; fi
exec /bin/mv "$@"
''',
    }
    for name, source in scripts.items():
        path = mock_bin / name
        path.write_text(source, encoding="utf-8")
        path.chmod(0o700)

    scenarios = {
        "success": ("PROMOTE\n", 0, "restored"),
        "reject": ("REJECT\n", None, "old"),
        "candidate-start": ("PROMOTE\n", None, "old"),
        "candidate-stop": ("PROMOTE\n", 97, "old"),
        "candidate-mv": ("PROMOTE\n", None, "old"),
        "after-swap": ("PROMOTE\n", None, "old"),
        "restore-mv": ("PROMOTE\n", 97, "restored"),
        "old-start": ("REJECT\n", 97, "old"),
    }
    for stage, (stdin, exact_status, expected_authority) in scenarios.items():
        case_dir = tmp_path / f"promotion-{stage}"
        old_dir = case_dir / "old"
        restored_dir = case_dir / "restored"
        state_dir = case_dir / "state"
        for directory in (old_dir, restored_dir, state_dir):
            directory.mkdir(parents=True)
        (restored_dir / ".env").write_text(
            "BASE_URL=http://127.0.0.1:18800\n", encoding="utf-8"
        )
        (restored_dir / "compose.override.yml").write_text(
            'ports:\n  - "127.0.0.1:18800:8000"\n', encoding="utf-8"
        )
        (restored_dir / "compose.restore-images.yml").write_text(
            "services:\n  plausible:\n    image: test@sha256:test\n",
            encoding="utf-8",
        )
        authority_file = state_dir / "authority.env"
        authority_file.write_text(
            "PLAUSIBLE_AUTHORITY_PROTOCOL=plausible-ce-authority-v1\n"
            f"PLAUSIBLE_ACTIVE_DIR={old_dir}\n"
            "PLAUSIBLE_ACTIVE_PROJECT=old\n"
            "PLAUSIBLE_ACTIVE_PORT=8800\n"
            "PLAUSIBLE_ACTIVE_SOURCE_COMMIT="
            "ec6c4da776547516d8f48159ce1a704df4f475ad\n",
            encoding="utf-8",
        )
        authority_file.chmod(0o600)
        log = case_dir / "calls.log"
        log.touch()
        env = {
            **os.environ,
            "PATH": f"{mock_bin}:{os.environ['PATH']}",
            "MOCK_LOG": str(log),
            "MOCK_MV_COUNT": str(case_dir / "mv.count"),
            "MOCK_PROMOTION_FAIL": "" if stage == "success" else stage,
            "PLAUSIBLE_AUTHORITY_FILE": str(authority_file),
            "PLAUSIBLE_AUTHORITY_ROOT": str(case_dir),
            "PLAUSIBLE_AUTHORITY_STATE_DIR": str(state_dir),
            "RESTORED_DIR": str(restored_dir),
            "RESTORED_PROJECT": "restored",
            "RESTORED_PROOF_PORT": "18800",
        }
        result = subprocess.run(
            ["bash", "-c", promotion_block],
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        if exact_status is not None:
            assert result.returncode == exact_status, result.stderr
        else:
            assert result.returncode != 0
        authority = authority_file.read_text(encoding="utf-8")
        expected_dir = restored_dir if expected_authority == "restored" else old_dir
        assert f"PLAUSIBLE_ACTIVE_DIR={expected_dir}" in authority
        calls = log.read_text(encoding="utf-8").splitlines()
        if stage == "success":
            assert "stop:old:all" in calls
            assert "up:restored" in calls
            assert "up:old" not in calls
        elif stage not in {"restore-mv", "old-start"}:
            assert "up:old" in calls
        if exact_status == 97:
            assert "CRITICAL: Plausible promotion rollback" in result.stderr

        if stage == "success":
            backup_block = next(
                block for block in blocks if "backup_protocol=%s" in block
            )
            backup_preamble = backup_block.split("production_resumed=0", 1)[0]
            backup_preamble += (
                '\ntest "$production_dir" = "$EXPECTED_ACTIVE_DIR"\n'
                'test "$production_project" = restored\n'
            )
            preamble = subprocess.run(
                ["bash"], input=backup_preamble, text=True, capture_output=True,
                check=False,
                env={**env, "EXPECTED_ACTIVE_DIR": str(restored_dir)},
            )
            assert preamble.returncode == 0, preamble.stderr

            upgrade_block = next(
                block for block in blocks
                if 'cd "$PLAUSIBLE_ACTIVE_DIR"' in block
                and 'docker compose config --quiet' in block
            )
            upgrade_block += (
                '\ntest "$PWD" = "$EXPECTED_ACTIVE_DIR"\n'
                'test "$COMPOSE_PROJECT_NAME" = restored\n'
            )
            upgrade = subprocess.run(
                ["bash"], input=upgrade_block, text=True, capture_output=True,
                check=False,
                env={**env, "EXPECTED_ACTIVE_DIR": str(restored_dir)},
            )
            assert upgrade.returncode == 0, upgrade.stderr


def test_upgrade_switches_source_images_and_authority_as_one_transaction(
    tmp_path: Path,
) -> None:
    blocks = _plausible_runbook_bash_blocks()
    upgrade_blocks = [block for block in blocks if "rollback_upgrade()" in block]
    assert len(upgrade_blocks) == 1
    upgrade_block = upgrade_blocks[0]
    assert upgrade_block.startswith("set -euo pipefail\n")
    config_images_position = upgrade_block.index("docker compose config --images")
    assert config_images_position < upgrade_block.index(
        'mv -f "$candidate_override" "$runtime_override"'
    )
    assert config_images_position < upgrade_block.rindex(
        "docker compose up -d --force-recreate"
    )
    authority_position = upgrade_block.index(
        'mv -f "$authority_candidate" "$authority_file"'
    )
    assert upgrade_block.index(
        'assert_running_image plausible_db postgres "$TARGET_POSTGRES_IMAGE"',
        config_images_position,
    ) < authority_position
    assert upgrade_block.index(
        'assert_running_image plausible_events_db clickhouse/clickhouse-server',
        config_images_position,
    ) < authority_position
    assert upgrade_block.index(
        'assert_running_image plausible ghcr.io/plausible/community-edition',
        config_images_position,
    ) < authority_position
    assert upgrade_block.index(
        'test "$upgrade_confirmation" = UPGRADE'
    ) < authority_position
    assert 'chown root:root "$output"' in upgrade_block
    assert 'chmod 0600 "$output"' in upgrade_block
    assert 'old_source_commit=$old_source_commit' in upgrade_block
    assert 'target_plausible_image=$TARGET_PLAUSIBLE_IMAGE' in upgrade_block
    assert "migration_round_trip_test=pass" in upgrade_block
    assert "postgres_rollback_test=pass" in upgrade_block
    assert "clickhouse_rollback_test=pass" in upgrade_block
    assert "exit 98" in upgrade_block

    old_commit = "1" * 40
    target_commit = "2" * 40
    old_images = {
        "plausible_db": f"postgres@sha256:{'1' * 64}",
        "plausible_events_db": (
            f"clickhouse/clickhouse-server@sha256:{'2' * 64}"
        ),
        "plausible": (
            f"ghcr.io/plausible/community-edition@sha256:{'3' * 64}"
        ),
    }
    target_images = {
        "plausible_db": f"postgres@sha256:{'4' * 64}",
        "plausible_events_db": (
            f"clickhouse/clickhouse-server@sha256:{'5' * 64}"
        ),
        "plausible": (
            f"ghcr.io/plausible/community-edition@sha256:{'6' * 64}"
        ),
    }

    mock_bin = tmp_path / "upgrade-mocks"
    mock_bin.mkdir()
    scripts = {
        "stat": "#!/usr/bin/env bash\nprintf '%s\\n' 'root:root 600'\n",
        "chown": "#!/usr/bin/env bash\nexit 0\n",
        "cp": r'''#!/usr/bin/env bash
set -euo pipefail
args=()
for argument in "$@"; do
  case "$argument" in --preserve=*) ;; *) args+=("$argument") ;; esac
done
exec /bin/cp "${args[@]}"
''',
        "git": r'''#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == -C ]]; then shift 2; fi
case "${1:-}" in
  rev-parse) cat "$MOCK_GIT_STATE" ;;
  diff) exit 0 ;;
  cat-file) exit 0 ;;
  checkout)
    test "${2:-}" = --detach
    printf '%s\n' "${3:?}" > "$MOCK_GIT_STATE"
    ;;
  *) exit 70 ;;
esac
''',
        "curl": r'''#!/usr/bin/env bash
set -euo pipefail
if [[ "${MOCK_UPGRADE_FAIL:-}" == readiness ]] &&
   [[ "$(cat "$MOCK_GIT_STATE")" == "$MOCK_TARGET_COMMIT" ]]; then
  exit 71
fi
exit 0
''',
        "mv": r'''#!/usr/bin/env bash
set -euo pipefail
destination="${@: -1}"
if [[ "${MOCK_UPGRADE_FAIL:-}" == authority-mv &&
      "$destination" == "$PLAUSIBLE_AUTHORITY_FILE" ]]; then
  count=0
  if [[ -f "$MOCK_AUTHORITY_MV_COUNT" ]]; then
    count="$(cat "$MOCK_AUTHORITY_MV_COUNT")"
  fi
  count=$((count + 1))
  printf '%s\n' "$count" > "$MOCK_AUTHORITY_MV_COUNT"
  if [[ "$count" == 1 ]]; then exit 74; fi
fi
exec /bin/mv "$@"
''',
        "docker": r'''#!/usr/bin/env bash
set -euo pipefail
image_for_service() {
  local service="$1" file
  if [[ -n "${COMPOSE_FILE:-}" ]]; then
    file="${COMPOSE_FILE##*:}"
  else
    file="$MOCK_ACTIVE_DIR/compose.restore-images.yml"
  fi
  awk -v service="$service" '
    $0 == "  " service ":" { found=1; next }
    found && $1 == "image:" {
      value=$2
      gsub(/^"|"$/, "", value)
      print value
      exit
    }
  ' "$file"
}
image_id_for_ref() {
  local ref="$1"
  printf 'sha256:%s\n' "${ref##*@sha256:}"
}
ref_for_image_id() {
  local wanted="$1" ref
  for ref in "$MOCK_OLD_POSTGRES" "$MOCK_OLD_CLICKHOUSE" \
    "$MOCK_OLD_PLAUSIBLE" "$TARGET_POSTGRES_IMAGE" \
    "$TARGET_CLICKHOUSE_IMAGE" "$TARGET_PLAUSIBLE_IMAGE"; do
    if [[ "$(image_id_for_ref "$ref")" == "$wanted" ]]; then
      printf '%s\n' "$ref"
      return 0
    fi
  done
  return 1
}

if [[ "${1:-}" == pull ]]; then exit 0; fi
if [[ "${1:-}" == inspect ]]; then
  service="${@: -1}"
  service="${service#container-}"
  ref="$(image_for_service "$service")"
  if [[ "${MOCK_UPGRADE_FAIL:-}" == runtime-mismatch &&
        "$service" == plausible &&
        "$(cat "$MOCK_GIT_STATE")" == "$MOCK_TARGET_COMMIT" ]]; then
    ref="$MOCK_OLD_PLAUSIBLE"
  fi
  image_id_for_ref "$ref"
  exit 0
fi
if [[ "${1:-}" == image && "${2:-}" == inspect ]]; then
  format=''
  ref_or_id="${@: -1}"
  for ((index=1; index <= $#; index++)); do
    if [[ "${!index}" == --format ]]; then
      next=$((index + 1))
      format="${!next}"
    fi
  done
  if [[ "$format" == *'.Id'* ]]; then
    image_id_for_ref "$ref_or_id"
  else
    ref_for_image_id "$ref_or_id"
  fi
  exit 0
fi
if [[ "${1:-}" == compose ]]; then
  command="${2:-}"
  case "$command" in
    config)
      if [[ "${3:-}" == --images ]]; then
        image_for_service plausible_db
        image_for_service plausible_events_db
        if [[ "${MOCK_UPGRADE_FAIL:-}" == configured-images &&
              "$(cat "$MOCK_GIT_STATE")" == "$MOCK_TARGET_COMMIT" ]]; then
          printf '%s\n' "$MOCK_OLD_PLAUSIBLE"
        else
          image_for_service plausible
        fi
      fi
      exit 0
      ;;
    ps)
      printf 'container-%s\n' "${@: -1}"
      exit 0
      ;;
    up)
      source_commit="$(cat "$MOCK_GIT_STATE")"
      printf 'up:%s\n' "$source_commit" >> "$MOCK_LOG"
      if [[ "${MOCK_UPGRADE_FAIL:-}" == rollback-up ]]; then exit 72; fi
      exit 0
      ;;
    stop)
      printf 'stop:%s\n' "$(cat "$MOCK_GIT_STATE")" >> "$MOCK_LOG"
      exit 0
      ;;
    exec) exit 0 ;;
  esac
fi
exit 73
''',
    }
    for name, source in scripts.items():
        path = mock_bin / name
        path.write_text(source, encoding="utf-8")
        path.chmod(0o700)

    scenarios = {
        "success": ("UPGRADE\n", 0, target_commit),
        "configured-images": ("UPGRADE\n", None, old_commit),
        "runtime-mismatch": ("UPGRADE\n", None, old_commit),
        "readiness": ("UPGRADE\n", None, old_commit),
        "reject": ("REJECT\n", None, old_commit),
        "bad-evidence": ("UPGRADE\n", None, old_commit),
        "authority-mv": ("UPGRADE\n", None, old_commit),
        "rollback-up": ("UPGRADE\n", 98, old_commit),
    }
    for stage, (stdin, exact_status, expected_commit) in scenarios.items():
        case_dir = tmp_path / f"upgrade-{stage}"
        active_dir = case_dir / "active"
        state_dir = case_dir / "state"
        active_dir.mkdir(parents=True)
        state_dir.mkdir()
        for filename in ("compose.yml", "compose.override.yml"):
            (active_dir / filename).write_text("services: {}\n", encoding="utf-8")
        (active_dir / ".env").write_text(
            "BASE_URL=https://plausible.bytedance.city\n", encoding="utf-8"
        )
        (active_dir / ".env").chmod(0o600)

        def write_override(path: Path, images: dict[str, str]) -> None:
            path.write_text(
                "services:\n"
                f'  plausible_db:\n    image: "{images["plausible_db"]}"\n'
                "  plausible_events_db:\n"
                f'    image: "{images["plausible_events_db"]}"\n'
                f'  plausible:\n    image: "{images["plausible"]}"\n',
                encoding="utf-8",
            )
            path.chmod(0o600)

        runtime_override = active_dir / "compose.restore-images.yml"
        write_override(runtime_override, old_images)
        git_state = case_dir / "git-state"
        git_state.write_text(f"{old_commit}\n", encoding="utf-8")
        authority_file = state_dir / "authority.env"
        authority_file.write_text(
            "PLAUSIBLE_AUTHORITY_PROTOCOL=plausible-ce-authority-v1\n"
            f"PLAUSIBLE_ACTIVE_DIR={active_dir}\n"
            "PLAUSIBLE_ACTIVE_PROJECT=plausible-ce\n"
            "PLAUSIBLE_ACTIVE_PORT=8800\n"
            f"PLAUSIBLE_ACTIVE_SOURCE_COMMIT={old_commit}\n",
            encoding="utf-8",
        )
        authority_file.chmod(0o600)
        evidence = state_dir / "rollback-evidence.env"
        evidence.write_text(
            "rollback_protocol=plausible-ce-in-place-rollback-v1\n"
            f"pre_upgrade_backup_sha256={'a' * 64}\n"
            f"old_source_commit={old_commit}\n"
            f"target_source_commit={target_commit}\n"
            f"old_postgres_image={old_images['plausible_db']}\n"
            f"old_clickhouse_image={old_images['plausible_events_db']}\n"
            f"old_plausible_image={old_images['plausible']}\n"
            f"target_postgres_image={target_images['plausible_db']}\n"
                f"target_clickhouse_image={target_images['plausible_events_db']}\n"
                f"target_plausible_image={target_images['plausible']}\n"
                "migration_round_trip_test=pass\n"
                "postgres_rollback_test=pass\n"
            f"clickhouse_rollback_test={'fail' if stage == 'bad-evidence' else 'pass'}\n",
            encoding="utf-8",
        )
        evidence.chmod(0o600)
        log = case_dir / "calls.log"
        log.touch()
        env = {
            **os.environ,
            "PATH": f"{mock_bin}:{os.environ['PATH']}",
            "MOCK_GIT_STATE": str(git_state),
            "MOCK_ACTIVE_DIR": str(active_dir),
            "MOCK_AUTHORITY_MV_COUNT": str(case_dir / "authority-mv.count"),
            "MOCK_LOG": str(log),
            "MOCK_TARGET_COMMIT": target_commit,
            "MOCK_UPGRADE_FAIL": "" if stage == "success" else stage,
            "MOCK_OLD_POSTGRES": old_images["plausible_db"],
            "MOCK_OLD_CLICKHOUSE": old_images["plausible_events_db"],
            "MOCK_OLD_PLAUSIBLE": old_images["plausible"],
            "PLAUSIBLE_AUTHORITY_FILE": str(authority_file),
            "PLAUSIBLE_AUTHORITY_ROOT": str(case_dir),
            "PLAUSIBLE_AUTHORITY_STATE_DIR": str(state_dir),
            "ROLLBACK_COMPATIBILITY_EVIDENCE": str(evidence),
            "PRE_UPGRADE_BACKUP_SHA256": "a" * 64,
            "TARGET_SOURCE_COMMIT": target_commit,
            "TARGET_POSTGRES_IMAGE": target_images["plausible_db"],
            "TARGET_CLICKHOUSE_IMAGE": target_images["plausible_events_db"],
            "TARGET_PLAUSIBLE_IMAGE": target_images["plausible"],
        }
        result = subprocess.run(
            ["bash", "-c", upgrade_block],
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        if exact_status is None:
            assert result.returncode != 0
        else:
            assert result.returncode == exact_status, result.stderr
        authority = authority_file.read_text(encoding="utf-8")
        assert f"PLAUSIBLE_ACTIVE_SOURCE_COMMIT={expected_commit}" in authority
        assert git_state.read_text(encoding="utf-8").strip() == expected_commit
        runtime = runtime_override.read_text(encoding="utf-8")
        expected_images = target_images if stage == "success" else old_images
        for image in expected_images.values():
            assert image in runtime
        assert runtime_override.stat().st_mode & 0o777 == 0o600
        env_text = (active_dir / ".env").read_text(encoding="utf-8")
        if stage == "bad-evidence":
            assert "COMPOSE_FILE=" not in env_text
        else:
            assert (
                "COMPOSE_FILE=compose.yml:compose.override.yml:compose.restore-images.yml"
                in env_text
            )
        if stage == "bad-evidence":
            assert log.read_text(encoding="utf-8") == ""
        if stage == "rollback-up":
            assert "CRITICAL: Plausible upgrade rollback" in result.stderr
        else:
            assert "CRITICAL: Plausible upgrade rollback" not in result.stderr


def test_consent_controls_are_bilingual_and_touch_sized() -> None:
    strings = json.loads(
        (FRONTEND / "assets/data/i18n/ui.json").read_text(encoding="utf-8")
    )
    for key in (
        "analytics.title",
        "analytics.body",
        "analytics.privacy",
        "analytics.essential",
        "analytics.allow",
        "analytics.settings",
    ):
        assert strings[key]["zh"].strip()
        assert strings[key]["en"].strip()

    css = (FRONTEND / "assets/css/common.css").read_text(encoding="utf-8")
    responsive = (FRONTEND / "assets/css/responsive.css").read_text(
        encoding="utf-8"
    )
    chrome = (FRONTEND / "assets/js/site-chrome.js").read_text(encoding="utf-8")
    assert ".analytics-consent" in css
    assert "min-height: 44px" in css
    privacy_link_rule = css.split(".analytics-consent__copy a {", 1)[1].split("}", 1)[0]
    assert "display: inline-flex" in privacy_link_rule
    assert "align-items: center" in privacy_link_rule
    assert "min-height: 44px" in privacy_link_rule
    assert "@media (max-width: 640px)" in css
    assert "@media (max-width: 360px)" in responsive
    assert 'data-analytics-settings data-i18n="analytics.settings"' in chrome


def test_privacy_copy_does_not_promise_unimplemented_calendar_retention() -> None:
    policy = (ROOT / "docs/privacy-policy.md").read_text(encoding="utf-8")
    normalized_policy = " ".join(policy.split())
    phase = (ROOT / "web/phase-detector/app/privacy/page.tsx").read_text(
        encoding="utf-8"
    )

    assert "Frontend error logs are retained for up to 90 days" not in policy
    assert "Nginx access logs are retained for 14 days" not in policy
    assert "does not promise a fixed calendar retention period" in normalized_policy
    assert "no fixed public calendar period is promised" in normalized_policy
    assert "错误日志：<strong>90 天</strong>" not in phase
    assert "Nginx 访问日志：<strong>14 天</strong>" not in phase
    assert phase.count("不承诺固定天数") == 2


def test_analytics_never_derives_identifiers_from_user_query_text() -> None:
    ask = (FRONTEND / "assets/js/ask.js").read_text(encoding="utf-8")

    for forbidden in (
        "query_hash",
        "computeQueryHash",
        "fallbackHash",
        "crypto.subtle",
    ):
        assert forbidden not in ask

    assert "phenomenon_id" in ask
    assert "position: position" in ask
    assert "surface: surface" in ask


def test_report_capability_page_defends_referrer_in_html() -> None:
    report = (FRONTEND / "report.html").read_text(encoding="utf-8")

    assert '<meta name="referrer" content="no-referrer">' in report
    assert 'content="strict-origin-when-cross-origin"' not in report
    assert '/assets/js/report.js?v=20260714n2' in report
    assert '/assets/js/analytics-consent.js?v=20260714n2' in report
