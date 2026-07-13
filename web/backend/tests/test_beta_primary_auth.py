"""Beta-primary account migration contracts.

Legacy Phase→beta SSO stays valid, while a beta magic-link session resolves
to the same stable account subject for every beta-owned asset.
"""
from __future__ import annotations

import concurrent.futures
import sqlite3
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import auth, favorites, report_account, sso
from errors import install_problem_handlers
from services.report_store import ReportStore


ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture()
def beta_stack(tmp_path, monkeypatch):
    auth_dir = tmp_path / "auth"
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
    monkeypatch.setenv("AUTH_DATA_DIR", str(auth_dir))
    monkeypatch.setenv("JWT_SECRET", "beta-primary-auth-secret-32-characters")
    monkeypatch.setenv("AUTH_LINK_BASE_URL", "http://beta.test")
    monkeypatch.setenv("ADMIN_NOTIFICATION_EMAIL", "owner@example.test")
    monkeypatch.setenv("STRUCTURAL_FAVORITES_PATH", str(tmp_path / "favorites.jsonl"))
    monkeypatch.setenv("STRUCTURAL_SSO_SECRET", "beta-primary-sso-secret-32-characters")
    monkeypatch.setenv("STRUCTURAL_SSO_DATA_DIR", str(tmp_path / "sso"))
    monkeypatch.setenv("STRUCTURAL_SSO_PHASE_ORIGIN", "http://phase.test")
    monkeypatch.setenv("STRUCTURAL_SSO_BETA_ORIGIN", "http://beta.test")
    monkeypatch.setattr(auth, "_data_dir", lambda: auth_dir)
    report_account._store = ReportStore(tmp_path / "history.db")
    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(favorites.router, prefix="/api")
    app.include_router(report_account.router, prefix="/api")
    app.include_router(sso.router, prefix="/api")
    install_problem_handlers(app)
    yield TestClient(app, base_url="http://beta.test"), report_account._store
    report_account._store = None


def _direct_login(client: TestClient, email: str = "alice@example.com") -> tuple[str, str]:
    requested = client.post(
        "/api/auth/request-link",
        headers={"Origin": "http://beta.test"},
        json={"email": email, "return_to": "/reports?view=owned"},
    )
    assert requested.status_code == 200, requested.text
    link = requested.json()["dev_link"]
    query = parse_qs(urlsplit(link).query)
    assert link.startswith("http://beta.test/auth/verify?")
    assert query["next"] == ["/reports?view=owned"]
    verified = client.post(
        "/api/auth/verify", headers={"Origin": "http://beta.test"},
        json={"token": requested.json()["dev_token"]},
    )
    assert verified.status_code == 200, verified.text
    cookie = verified.headers["set-cookie"]
    assert "phase_session=" in cookie
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    return email, client.cookies.get("phase_session")


def _trusted_sso_session(email: str, *, jti: str) -> str:
    subject = sso._subject_id(email)
    now = int(time.time())
    sso.SsoReplayStore(sso._data_dir() / "sso_replay.sqlite3").issue(
        f"binding-{jti}", subject, "free", now + 120, email=email,
    )
    return jwt.encode({
        "iss": "http://beta.test", "aud": "structural-beta-session",
        "sub": subject, "tier": "free", "jti": jti,
        "iat": now, "issued_ns": time.time_ns(), "exp": now + 3600,
    }, sso._secret(), algorithm="HS256")


def test_direct_session_maps_to_legacy_sso_subject(beta_stack):
    client, _ = beta_stack
    email, _ = _direct_login(client)
    from starlette.requests import Request
    raw = client.cookies.get("phase_session")
    request = Request({
        "type": "http",
        "headers": [(b"cookie", f"phase_session={raw}".encode())],
    })
    user, status = sso.resolve_beta_user(request)
    assert status == "valid"
    assert user == {
        "id": sso._subject_id(email), "email": email,
        "tier": "free", "auth_method": "direct",
    }


def test_dual_valid_cross_account_credentials_reject_every_account_surface_without_writes(beta_stack):
    alice, store = beta_stack
    alice_email, _ = _direct_login(alice, "alice@example.com")
    assert alice.post(
        "/api/favorites/AAPL", headers={"Origin": "http://beta.test"},
    ).status_code == 201
    alice_report = store.create(
        query="alice", b_id="a", lang="zh", payload={}, model="m",
        creator_anon_id="alice-anon",
    )
    store.claim_by_anon("alice-anon", sso._subject_id(alice_email))

    bob = TestClient(alice.app, base_url="http://beta.test")
    bob_email, _ = _direct_login(bob, "bob@example.com")
    assert bob.post(
        "/api/favorites/TSLA", headers={"Origin": "http://beta.test"},
    ).status_code == 201
    bob_report = store.create(
        query="bob", b_id="b", lang="zh", payload={}, model="m",
        creator_anon_id="bob-anon",
    )
    store.claim_by_anon("bob-anon", sso._subject_id(bob_email))

    bob_sso = _trusted_sso_session(bob_email, jti="bob-on-alice-browser")
    alice.cookies.set(
        "structural_beta_session", bob_sso, domain="beta.test", path="/",
    )
    ledger = sso.SsoReplayStore(sso._data_dir() / "sso_replay.sqlite3")
    before = {
        "alice_favorites": favorites.export_account_favorites(alice_email),
        "bob_favorites": favorites.export_account_favorites(bob_email),
        "alice_reports": store.export_by_owner(sso._subject_id(alice_email)),
        "bob_reports": store.export_by_owner(sso._subject_id(bob_email)),
        "alice_revoked": ledger.subject_revoked_at(sso._subject_id(alice_email)),
        "bob_revoked": ledger.subject_revoked_at(sso._subject_id(bob_email)),
    }

    requests = [
        alice.get("/api/auth/me"),
        alice.get("/api/favorites"),
        alice.get("/api/me/reports"),
        alice.post("/api/me/reports/claim", headers={"Origin": "http://beta.test"}),
        alice.get("/api/me/export"),
        alice.post(
            "/api/me/delete", headers={"Origin": "http://beta.test"},
            json={"confirmation": "DELETE"},
        ),
    ]
    for response in requests:
        assert response.status_code in {401, 409}, response.text
        assert response.json().get("error") == "credential_conflict", response.text
        assert alice_email not in response.text and bob_email not in response.text
    after = {
        "alice_favorites": favorites.export_account_favorites(alice_email),
        "bob_favorites": favorites.export_account_favorites(bob_email),
        "alice_reports": store.export_by_owner(sso._subject_id(alice_email)),
        "bob_reports": store.export_by_owner(sso._subject_id(bob_email)),
        "alice_revoked": ledger.subject_revoked_at(sso._subject_id(alice_email)),
        "bob_revoked": ledger.subject_revoked_at(sso._subject_id(bob_email)),
    }
    assert after == before
    assert [row["id"] for row in after["alice_reports"]["reports"]] == [alice_report["id"]]
    assert [row["id"] for row in after["bob_reports"]["reports"]] == [bob_report["id"]]


def test_dual_valid_same_identity_uses_all_assets_and_delete_revokes_both(beta_stack):
    client, store = beta_stack
    email, direct_token = _direct_login(client)
    subject = sso._subject_id(email)
    assert client.post(
        "/api/favorites/AAPL", headers={"Origin": "http://beta.test"},
    ).status_code == 201
    owned = store.create(
        query="same", b_id="same", lang="zh", payload={}, model="m",
        creator_anon_id="same-identity",
    )
    store.claim_by_anon("same-identity", subject)
    sso_token = _trusted_sso_session(email, jti="same-identity-sso")
    client.cookies.set(
        "structural_beta_session", sso_token, domain="beta.test", path="/",
    )

    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/favorites").json()["tickers"] == ["AAPL"]
    assert client.get("/api/me/reports").json()["items"][0]["id"] == owned["id"]
    assert client.get("/api/me/export").status_code == 200
    deleted = client.post(
        "/api/me/delete", headers={"Origin": "http://beta.test"},
        json={"confirmation": "DELETE"},
    )
    assert deleted.status_code == 200, deleted.text
    ledger = sso.SsoReplayStore(sso._data_dir() / "sso_replay.sqlite3")
    assert ledger.subject_revoked_at(subject) is not None
    assert favorites.export_account_favorites(email)["tickers"] == []
    assert store.list_by_owner(subject) == []
    direct_replay = TestClient(client.app, base_url="http://beta.test")
    direct_replay.cookies.set("phase_session", direct_token, domain="beta.test", path="/")
    assert direct_replay.get("/api/me/export").status_code == 401
    sso_replay = TestClient(client.app, base_url="http://beta.test")
    sso_replay.cookies.set(
        "structural_beta_session", sso_token, domain="beta.test", path="/",
    )
    assert sso_replay.get("/api/me/reports").status_code == 401


def test_successful_phase_exchange_clears_direct_cookie(beta_stack):
    seed, _ = beta_stack
    email = "exchange@example.com"
    auth._ensure_user(email)
    direct_token, _ = auth._issue_jwt(email, "free")
    beta = TestClient(seed.app, base_url="http://beta.test")
    beta.cookies.set("phase_session", direct_token, domain="beta.test", path="/")
    phase = TestClient(seed.app, base_url="http://phase.test")
    phase.cookies.set("phase_session", direct_token, domain="phase.test", path="/")

    started = beta.get(
        "/api/sso/start", headers={"Origin": "http://beta.test"},
        follow_redirects=False,
    )
    query = parse_qs(urlsplit(started.headers["location"]).query)
    issued = phase.post(
        "/api/sso/issue", headers={"Origin": "http://beta.test"},
        json={
            "audience": "structural-beta", "state": query["state"][0],
            "nonce": query["nonce"][0],
        },
    )
    assert issued.status_code == 200, issued.text
    exchanged = beta.post(
        "/api/sso/exchange", headers={"Origin": "http://beta.test"},
        json={"code": issued.json()["code"], "state": query["state"][0]},
    )
    assert exchanged.status_code == 200, exchanged.text
    assert beta.cookies.get("phase_session") is None
    assert beta.cookies.get("structural_beta_session")


def test_invalid_sso_cookie_never_downgrades_to_direct_session(beta_stack):
    client, _ = beta_stack
    _direct_login(client)
    client.cookies.set("structural_beta_session", "invalid-sso-cookie")
    from starlette.requests import Request
    cookies = (
        f"phase_session={client.cookies.get('phase_session')}; "
        "structural_beta_session=invalid-sso-cookie"
    )
    request = Request({"type": "http", "headers": [(b"cookie", cookies.encode())]})
    assert sso.resolve_beta_user(request) == (None, "invalid")


def test_invalid_or_revoked_direct_cookie_never_falls_through_to_valid_sso(beta_stack):
    client, _ = beta_stack
    email = "alice@example.com"
    auth._ensure_user(email)
    valid_sso = _trusted_sso_session(email, jti="valid-sso-with-bad-direct")
    client.cookies.set(
        "structural_beta_session", valid_sso, domain="beta.test", path="/",
    )
    client.cookies.set("phase_session", "invalid-direct", domain="beta.test", path="/")
    assert client.get("/api/auth/me").status_code == 401

    valid_direct, jti = auth._issue_jwt(email, "free")
    auth._store().revoke(jti, "2026-07-13T00:00:00+00:00", email)
    client.cookies.set("phase_session", valid_direct, domain="beta.test", path="/")
    revoked = client.get("/api/auth/me")
    assert revoked.status_code == 401
    assert revoked.json()["error"] == "session revoked"


@pytest.mark.parametrize("stale_cookie", ["invalid-sso-cookie", "expired-sso-cookie"])
def test_direct_verify_clears_stale_sso_and_assets_are_reachable(beta_stack, stale_cookie):
    client, _ = beta_stack
    client.cookies.set("structural_beta_session", stale_cookie, domain="beta.test", path="/")
    _direct_login(client)
    assert client.cookies.get("structural_beta_session") is None
    assert client.post(
        "/api/favorites/AAPL", headers={"Origin": "http://beta.test"},
    ).status_code == 201
    assert client.get("/api/me/export").status_code == 200

    client.cookies.set("structural_beta_session", stale_cookie, domain="beta.test", path="/")
    logged_out = client.post("/api/auth/logout", headers={"Origin": "http://beta.test"})
    assert logged_out.status_code == 200
    assert client.cookies.get("structural_beta_session") is None


def test_direct_beta_login_unifies_favorites_reports_export_and_delete(beta_stack):
    client, store = beta_stack
    email, session_token = _direct_login(client)
    report = store.create(
        query="owned", b_id="b1", lang="zh", payload={}, model="m",
        creator_anon_id="same-browser",
    )
    assert client.post(
        "/api/favorites/AAPL", headers={"Origin": "http://beta.test"}
    ).status_code == 201
    assert client.post(
        "/api/reports/anon-proof",
        headers={"Origin": "http://beta.test", "X-Anon-Id": "same-browser"},
    ).status_code == 200
    claimed = client.post(
        "/api/me/reports/claim", headers={"Origin": "http://beta.test"}
    )
    assert claimed.status_code == 200 and claimed.json()["claimed"] == 1
    listed = client.get("/api/me/reports")
    assert [item["id"] for item in listed.json()["items"]] == [report["id"]]
    exported = client.get("/api/me/export").json()["data"]
    assert exported["favorites"]["tickers"] == ["AAPL"]
    assert exported["claimed_reports"]["reports"][0]["id"] == report["id"]

    deleted = client.post(
        "/api/me/delete", headers={"Origin": "http://beta.test"},
        json={"confirmation": "DELETE"},
    )
    assert deleted.status_code == 200, deleted.text
    assert client.get("/api/auth/me").status_code == 401
    replay = TestClient(client.app, base_url="http://beta.test")
    replay.cookies.set("phase_session", session_token)
    assert replay.get("/api/me/export").status_code == 401
    assert store.list_by_owner(sso._subject_id(email)) == []

    # Re-registration is a new credential generation on the same stable
    # subject; only sessions issued before deletion remain revoked.
    auth._ensure_user(email)
    new_session, _ = auth._issue_jwt(email, "free")
    from starlette.requests import Request
    new_request = Request({
        "type": "http",
        "headers": [(b"cookie", f"phase_session={new_session}".encode())],
    })
    assert sso.resolve_beta_user(new_request)[1] == "valid"


def test_legacy_subject_session_requires_trusted_email_binding_then_shares_assets(beta_stack):
    client, store = beta_stack
    email, direct_token = _direct_login(client)
    subject = sso._subject_id(email)
    assert client.post(
        "/api/favorites/AAPL", headers={"Origin": "http://beta.test"},
    ).status_code == 201
    owned = store.create(
        query="legacy", b_id="b1", lang="zh", payload={}, model="m",
        creator_anon_id="legacy-browser",
    )
    store.claim_by_anon("legacy-browser", subject)

    now = int(time.time())
    old_sso = jwt.encode({
        "iss": "http://beta.test", "aud": "structural-beta-session",
        "sub": subject, "tier": "free", "jti": "legacy-session",
        "iat": now, "issued_ns": time.time_ns(), "exp": now + 3600,
    }, sso._secret(), algorithm="HS256")
    client.cookies.delete("phase_session")
    client.cookies.set("structural_beta_session", old_sso)

    # A pre-migration subject-only cookie cannot guess an email or expose
    # email-owned assets until a trusted Phase exchange establishes binding.
    from starlette.requests import Request
    unlinked_request = Request({
        "type": "http",
        "headers": [(b"cookie", f"structural_beta_session={old_sso}".encode())],
    })
    assert auth.resolve_account_user(unlinked_request)[1] == "unlinked"
    ledger = sso.SsoReplayStore(sso._data_dir() / "sso_replay.sqlite3")
    ledger.issue("trusted-migration", subject, "free", now + 120, email=email)

    assert client.get("/api/favorites").json()["tickers"] == ["AAPL"]
    exported = client.get("/api/me/export")
    assert exported.status_code == 200
    assert exported.json()["data"]["favorites"]["tickers"] == ["AAPL"]
    assert exported.json()["data"]["claimed_reports"]["reports"][0]["id"] == owned["id"]

    deleted = client.post(
        "/api/me/delete", headers={"Origin": "http://beta.test"},
        json={"confirmation": "DELETE"},
    )
    assert deleted.status_code == 200, deleted.text
    direct_replay = TestClient(client.app, base_url="http://beta.test")
    direct_replay.cookies.set("phase_session", direct_token)
    assert direct_replay.get("/api/me/export").status_code == 401
    sso_replay = TestClient(client.app, base_url="http://beta.test")
    sso_replay.cookies.set("structural_beta_session", old_sso)
    assert sso_replay.get("/api/me/export").status_code == 401
    assert store.list_by_owner(subject) == []
    assert ledger.email_for_subject(subject) is None


def test_existing_subject_only_sso_database_migrates_without_losing_codes(tmp_path):
    database = tmp_path / "legacy-sso.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE issued_sso_codes("
            "jti TEXT PRIMARY KEY,subject_id TEXT NOT NULL,tier TEXT NOT NULL,"
            "expires_at INTEGER NOT NULL,consumed_at INTEGER)"
        )
        connection.execute(
            "INSERT INTO issued_sso_codes VALUES(?,?,?,?,NULL)",
            ("old-code", "old-subject", "free", int(time.time()) + 120),
        )
    ledger = sso.SsoReplayStore(database)
    with sqlite3.connect(database) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(issued_sso_codes)")
        }
        assert "email" in columns
        assert connection.execute(
            "SELECT subject_id FROM issued_sso_codes WHERE jti='old-code'"
        ).fetchone() == ("old-subject",)
    ledger.issue(
        "new-code", "new-subject", "free", int(time.time()) + 120,
        email="owner@example.com",
    )
    assert ledger.email_for_subject("new-subject") == "owner@example.com"


def test_magic_token_is_one_time_under_strictmode_like_concurrency(beta_stack):
    client, _ = beta_stack
    requested = client.post(
        "/api/auth/request-link", headers={"Origin": "http://beta.test"},
        json={"email": "race@example.com"},
    )
    token = requested.json()["dev_token"]

    def verify(_index: int) -> int:
        isolated = TestClient(client.app, base_url="http://beta.test")
        return isolated.post(
            "/api/auth/verify", headers={"Origin": "http://beta.test"},
            json={"token": token},
        ).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(verify, range(4)))
    assert statuses.count(200) == 1
    assert statuses.count(400) == 3


@pytest.mark.parametrize(
    "value,expected",
    [
        ("/reports?view=owned", "/reports?view=owned"),
        ("https://evil.example/x", None),
        ("//evil.example/x", None),
        ("/\\evil.example", None),
        ("/auth/verify", None),
    ],
)
def test_return_target_is_local_and_non_recursive(value, expected):
    assert auth._safe_return_to(value) == expected


def test_beta_native_pages_and_strictmode_client_contract():
    main = (ROOT / "web/backend/main.py").read_text(encoding="utf-8")
    login = (ROOT / "web/frontend/auth-login.html").read_text(encoding="utf-8")
    verify = (ROOT / "web/frontend/auth-verify.html").read_text(encoding="utf-8")
    script = (ROOT / "web/frontend/assets/js/auth-pages.js").read_text(encoding="utf-8")
    assert 'FileResponse(FRONTEND_DIR / "auth-login.html")' in main
    assert 'FRONTEND_DIR / "auth-verify.html"' in main
    assert "phase.bytedance.city/auth/login" not in main
    assert 'data-auth-page="login"' in login and 'autocomplete="email"' in login
    assert 'data-auth-page="verify"' in verify
    assert "fetch(path" in script and "credentials: 'same-origin'" in script
    assert "'/api/auth/request-link'" in script
    assert "'/api/auth/verify'" in script and "'/api/auth/me'" in script
    assert "__structuralAuthVerifyFlight" in script
    assert "window.history.replaceState(null, '', '/auth/verify')" in script
    assert "target.origin !== window.location.origin" in script
    assert verify.index("<script>") < verify.index('<meta charset="UTF-8">')
    assert 'name="referrer" content="no-referrer"' in verify
    assert "structural_auth_verify_token" in verify and "sessionStorage" in verify
    assert "window.location.hash" in script and "VERIFY_TOKEN_KEY" in script
    assert '"Referrer-Policy": "no-referrer"' in main
    assert '"Cache-Control": "no-store"' in main


def test_verify_document_response_blocks_referrer_and_caching():
    import main as beta_main
    response = TestClient(beta_main.app).get(
        "/auth/verify?token=never-log-or-forward-this-token"
    )
    assert response.status_code == 200
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_beta_deploy_loads_private_canonical_auth_environment():
    deploy = (ROOT / "scripts/deploy-vps.sh").read_text(encoding="utf-8")
    unit = (ROOT / "web/scripts/structural-web.service").read_text(encoding="utf-8")
    assert "/root/.config/structural-isomorphism/beta-auth.env" in deploy
    assert "stat -Lc '%a' \"$BETA_AUTH_ENV_FILE\"" in deploy
    assert "AUTH_LINK_BASE_URL https://beta.structural.bytedance.city" in deploy
    assert "AUTH_SITE_ROLE beta" in deploy
    assert "AUTH_DATA_DIR must be absolute and outside Git" in deploy
    assert "AUTH_TRUSTED_PROXY_IPS" in deploy
    assert "EnvironmentFile=/root/.config/structural-isomorphism/beta-auth.env" in unit
    assert unit.index("web/backend/.env") < unit.index("beta-auth.env")


def test_beta_runtime_rejects_noncanonical_production_link(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_SITE_ROLE", "beta")
    monkeypatch.setenv("JWT_SECRET", "A7f9K2m4P8q1R6t3V5x0Y2z8C4d7H9j1L6n3")
    monkeypatch.setenv("AUTH_LINK_BASE_URL", "https://phase.bytedance.city")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "login@example.test")
    monkeypatch.setenv("ADMIN_NOTIFICATION_EMAIL", "owner@example.test")
    monkeypatch.setenv("AUTH_DATA_DIR", "/tmp/structural-auth-test")
    monkeypatch.setenv("AUTH_TRUSTED_PROXY_IPS", "127.0.0.1/32")
    with pytest.raises(RuntimeError, match="canonical beta"):
        auth._validate_production_config()


def _set_valid_prod_auth(monkeypatch, data_dir: Path) -> None:
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_SITE_ROLE", "beta")
    monkeypatch.setenv("JWT_SECRET", "A7f9K2m4P8q1R6t3V5x0Y2z8C4d7H9j1L6n3")
    monkeypatch.setenv("AUTH_LINK_BASE_URL", "https://beta.structural.bytedance.city")
    monkeypatch.setenv("AUTH_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AUTH_TRUSTED_PROXY_IPS", "127.0.0.1/32,::1/128")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "login@example.test")
    monkeypatch.setenv("ADMIN_NOTIFICATION_EMAIL", "owner@example.test")


def test_runtime_requires_beta_role_and_absolute_external_data_dir(tmp_path, monkeypatch):
    _set_valid_prod_auth(monkeypatch, tmp_path / "auth")
    auth._validate_production_config()
    monkeypatch.setenv("AUTH_SITE_ROLE", "phase")
    with pytest.raises(RuntimeError, match="AUTH_SITE_ROLE=beta"):
        auth._validate_production_config()
    monkeypatch.setenv("AUTH_SITE_ROLE", "beta")
    monkeypatch.setenv("AUTH_DATA_DIR", "relative/auth")
    with pytest.raises(RuntimeError, match="must be absolute"):
        auth._validate_production_config()
    monkeypatch.setenv("AUTH_DATA_DIR", str(ROOT / "private-auth"))
    with pytest.raises(RuntimeError, match="outside the Git worktree"):
        auth._validate_production_config()


def test_proxy_ip_ignores_untrusted_headers_and_walks_trusted_chain(monkeypatch):
    from starlette.requests import Request
    monkeypatch.setenv("AUTH_TRUSTED_PROXY_IPS", "127.0.0.1/32,10.0.0.0/8")
    spoofed = Request({
        "type": "http", "client": ("198.51.100.9", 1234),
        "headers": [(b"x-forwarded-for", b"203.0.113.7")],
    })
    assert auth._client_ip(spoofed) == "198.51.100.9"
    proxied = Request({
        "type": "http", "client": ("127.0.0.1", 1234),
        "headers": [(b"x-forwarded-for", b"192.0.2.44, 10.0.0.8")],
    })
    assert auth._client_ip(proxied) == "192.0.2.44"


def test_global_email_circuit_breaker_is_atomic(beta_stack, monkeypatch):
    client, _ = beta_stack
    monkeypatch.setenv("AUTH_GLOBAL_EMAIL_LIMIT_PER_HOUR", "2")
    monkeypatch.setenv("AUTH_IP_EMAIL_LIMIT_PER_HOUR", "20")
    statuses = [client.post(
        "/api/auth/request-link", headers={"Origin": "http://beta.test"},
        json={"email": f"global-{index}@example.com"},
    ).status_code for index in range(3)]
    assert statuses == [200, 200, 429]
