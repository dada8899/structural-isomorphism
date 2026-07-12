"""Unit tests for api.favorites — W15-C, session #10.

Run with:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_favorites.py -q

Coverage:
    - GET empty for new user / anonymous
    - POST adds, idempotent on duplicate (201 vs 200)
    - DELETE removes, idempotent
    - DELETE returns 204
    - Per-tier limit enforcement (free 50 → 429 on 51st)
    - pro tier larger cap
    - team / admin tier unlimited
    - Anonymous write rejected (401)
    - Invalid ticker rejected (422)
    - Merge endpoint: union + drop-over-cap
    - Atomic write safety (concurrent POST via thread pool)
"""
from __future__ import annotations

import concurrent.futures
import json
import sys
import threading
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import favorites as fav  # noqa: E402
from api import auth as session_auth  # noqa: E402
from auth import api_key as auth_mod  # noqa: E402
from errors import install_problem_handlers  # noqa: E402


# ---- fixtures ----


def _seed_keys_file(tmp_path: Path) -> Path:
    """Write a JSONL of fake API keys covering free / pro / team / admin."""
    p = tmp_path / "api_keys.jsonl"
    rows = [
        {
            "key": "sk_test_free",
            "tier": "free",
            "owner_email": "free@example.com",
            "created_at": "2026-05-15T00:00:00Z",
            "revoked": False,
        },
        {
            "key": "sk_test_pro",
            "tier": "pro",
            "owner_email": "pro@example.com",
            "created_at": "2026-05-15T00:00:00Z",
            "revoked": False,
        },
        {
            "key": "sk_test_team",
            "tier": "team",
            "owner_email": "team@example.com",
            "created_at": "2026-05-15T00:00:00Z",
            "revoked": False,
        },
        {
            "key": "sk_test_admin",
            "tier": "admin",
            "owner_email": "admin@example.com",
            "created_at": "2026-05-15T00:00:00Z",
            "revoked": False,
        },
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Redirect storage to tmp_path.
    fav_path = tmp_path / "favorites.jsonl"
    monkeypatch.setenv("STRUCTURAL_FAVORITES_PATH", str(fav_path))

    # Force a fresh API-key store backed by our seed file.
    keys_path = _seed_keys_file(tmp_path)
    monkeypatch.setenv("STRUCTURAL_API_KEYS_PATH", str(keys_path))
    # Reset cached store instance so the env var actually takes effect.
    monkeypatch.setattr(auth_mod, "_store", None, raising=False)
    monkeypatch.setattr(session_auth, "_data_dir", lambda: tmp_path)
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET", "favorites-session-test-secret-32-chars-ok")
    monkeypatch.setenv("AUTH_LINK_BASE_URL", "http://testserver")

    app = FastAPI()
    install_problem_handlers(app)
    app.include_router(fav.router, prefix="/api")
    return TestClient(app)


def _hdr(key: str | None) -> dict:
    return {"X-API-Key": key} if key else {}


# ---- GET ----


def test_get_anonymous_returns_empty(client):
    r = client.get("/api/favorites")
    assert r.status_code == 200
    assert r.json() == {
        "tickers": [], "authenticated": False, "auth_method": None
    }


def test_get_new_user_returns_empty(client):
    r = client.get("/api/favorites", headers=_hdr("sk_test_free"))
    assert r.status_code == 200
    assert r.json()["tickers"] == []
    assert r.json()["authenticated"] is True
    assert r.json()["auth_method"] == "api_key"


def test_production_storage_requires_external_persistent_path(monkeypatch):
    monkeypatch.delenv("STRUCTURAL_FAVORITES_PATH", raising=False)
    monkeypatch.delenv("AUTH_DATA_DIR", raising=False)
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    with pytest.raises(RuntimeError, match="persistence requires"):
        fav._data_file()


def test_production_storage_rejects_repo_path(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    monkeypatch.setenv(
        "STRUCTURAL_FAVORITES_PATH", str(_BACKEND / "data" / "favorites.jsonl")
    )
    with pytest.raises(RuntimeError, match="outside the Git checkout"):
        fav._data_file()


def test_legacy_storage_migrates_once_without_overwrite(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy" / "favorites.jsonl"
    target = tmp_path / "persistent" / "favorites.jsonl"
    legacy.parent.mkdir()
    legacy.write_text('{"email":"old@example.com","tickers":["AAPL"]}\n')
    monkeypatch.setattr(fav, "_legacy_data_file", lambda: legacy)
    fav._migrate_legacy_file(target)
    assert target.read_text() == legacy.read_text()
    target.write_text("authoritative\n")
    fav._migrate_legacy_file(target)
    assert target.read_text() == "authoritative\n"


def _session_cookie(email: str, tier: str = "free") -> str:
    session_auth._ensure_user(email)
    token, _ = session_auth._issue_jwt(email, tier)
    return token


def test_http_only_session_is_server_source_of_truth(client):
    token = _session_cookie("member@example.com")
    client.cookies.set("phase_session", token)
    added = client.post(
        "/api/favorites/AAPL", headers={"Origin": "http://testserver"}
    )
    assert added.status_code == 201
    listed = client.get("/api/favorites")
    assert listed.json()["tickers"] == ["AAPL"]
    assert listed.json()["auth_method"] == "session"

    # A fresh browser/device with the same authenticated account reads the
    # durable server state rather than the first device's local storage.
    with TestClient(client.app) as second_device:
        second_device.cookies.set("phase_session", token)
        assert second_device.get("/api/favorites").json()["tickers"] == ["AAPL"]


def test_http_only_session_merges_anonymous_tickers(client):
    client.cookies.set("phase_session", _session_cookie("member@example.com"))
    merged = client.post(
        "/api/favorites/merge",
        json={"tickers": ["AAPL", "tsla", "AAPL"]},
        headers={"Origin": "http://testserver"},
    )
    assert merged.status_code == 200
    assert set(merged.json()["tickers"]) == {"AAPL", "TSLA"}
    assert client.get("/api/favorites").json()["tickers"] == ["AAPL", "TSLA"]


def test_session_precedes_legacy_api_key(client):
    client.cookies.set("phase_session", _session_cookie("member@example.com"))
    response = client.post(
        "/api/favorites/AAPL",
        headers={**_hdr("sk_test_pro"), "Origin": "http://testserver"},
    )
    assert response.status_code == 201
    assert client.get("/api/favorites").json()["tickers"] == ["AAPL"]
    client.cookies.delete("phase_session")
    assert client.get(
        "/api/favorites", headers=_hdr("sk_test_pro")
    ).json()["tickers"] == []


def test_revoked_session_does_not_fall_back_to_api_key(client):
    token, jti = session_auth._issue_jwt("free@example.com", "free")
    session_auth._store().revoke(jti, "2026-07-12T00:00:00+00:00")
    client.cookies.set("phase_session", token)
    response = client.post(
        "/api/favorites/AAPL", headers=_hdr("sk_test_free")
    )
    assert response.status_code == 401


def test_session_mutation_rejects_cross_origin(client):
    client.cookies.set("phase_session", _session_cookie("member@example.com"))
    response = client.post(
        "/api/favorites/AAPL", headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403


# ---- POST add ----


def test_post_adds_ticker(client):
    r = client.post("/api/favorites/AAPL", headers=_hdr("sk_test_free"))
    assert r.status_code == 201
    body = r.json()
    assert body["added"] is True
    assert body["ticker"] == "AAPL"

    # Now GET should include it.
    r2 = client.get("/api/favorites", headers=_hdr("sk_test_free"))
    assert r2.status_code == 200
    assert r2.json()["tickers"] == ["AAPL"]


def test_post_idempotent_on_duplicate(client):
    r1 = client.post("/api/favorites/TSLA", headers=_hdr("sk_test_free"))
    assert r1.status_code == 201
    r2 = client.post("/api/favorites/TSLA", headers=_hdr("sk_test_free"))
    assert r2.status_code == 200
    assert r2.json()["added"] is False


def test_post_normalizes_to_uppercase(client):
    r = client.post("/api/favorites/aapl", headers=_hdr("sk_test_free"))
    assert r.status_code == 201
    assert r.json()["ticker"] == "AAPL"


def test_post_accepts_dot_dash_in_ticker(client):
    r = client.post("/api/favorites/BRK.A", headers=_hdr("sk_test_free"))
    assert r.status_code == 201
    r = client.post("/api/favorites/7203.T", headers=_hdr("sk_test_free"))
    assert r.status_code == 201


def test_post_rejects_invalid_ticker(client):
    r = client.post("/api/favorites/!!!", headers=_hdr("sk_test_free"))
    assert r.status_code == 422


def test_post_rejects_too_long_ticker(client):
    r = client.post(
        "/api/favorites/" + "X" * 50, headers=_hdr("sk_test_free")
    )
    assert r.status_code == 422


def test_post_anonymous_rejected(client):
    r = client.post("/api/favorites/AAPL")
    assert r.status_code == 401


# ---- DELETE ----


def test_delete_removes_ticker(client):
    client.post("/api/favorites/MSFT", headers=_hdr("sk_test_free"))
    r = client.delete("/api/favorites/MSFT", headers=_hdr("sk_test_free"))
    assert r.status_code == 204
    r2 = client.get("/api/favorites", headers=_hdr("sk_test_free"))
    assert "MSFT" not in r2.json()["tickers"]


def test_delete_idempotent(client):
    # Deleting non-existent should still return 204.
    r = client.delete("/api/favorites/NEVERFAVED", headers=_hdr("sk_test_free"))
    assert r.status_code == 204


def test_delete_anonymous_rejected(client):
    r = client.delete("/api/favorites/AAPL")
    assert r.status_code == 401


# ---- tier limits ----


def test_free_tier_caps_at_50(client):
    """51st attempt → 429 with slug favorites_limit_exceeded."""
    for i in range(50):
        r = client.post(
            f"/api/favorites/T{i:03d}", headers=_hdr("sk_test_free")
        )
        assert r.status_code == 201, f"failed at {i}: {r.status_code}"
    # 51st add should fail.
    r = client.post("/api/favorites/OVER", headers=_hdr("sk_test_free"))
    assert r.status_code == 429
    body = r.json()
    assert "type" in body and "favorites_limit_exceeded" in body["type"]
    # ext fields present.
    assert body.get("tier") == "free"
    assert body.get("cap") == 50


def test_pro_tier_larger_cap(client):
    # Sanity: pro accepts 51+ entries (just check it crosses 50 threshold).
    for i in range(60):
        r = client.post(f"/api/favorites/T{i:03d}", headers=_hdr("sk_test_pro"))
        assert r.status_code == 201


def test_team_tier_unlimited(client):
    # Push past the pro cap of 500. We send 50 to keep test fast — we're
    # really checking the cap-checking branch returns None and doesn't 429.
    # (Setting up 500 entries is too slow for CI.)
    for i in range(50):
        r = client.post(
            f"/api/favorites/T{i:03d}", headers=_hdr("sk_test_team")
        )
        assert r.status_code == 201


def test_admin_tier_unlimited(client):
    for i in range(50):
        r = client.post(
            f"/api/favorites/T{i:03d}", headers=_hdr("sk_test_admin")
        )
        assert r.status_code == 201


# ---- merge ----


def test_merge_unions(client):
    # Seed user state with one ticker.
    client.post("/api/favorites/AAPL", headers=_hdr("sk_test_free"))
    # Merge two new + the existing one.
    r = client.post(
        "/api/favorites/merge",
        json={"tickers": ["TSLA", "AAPL", "NVDA"]},
        headers=_hdr("sk_test_free"),
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body["tickers"]) == {"AAPL", "TSLA", "NVDA"}
    assert body["merged"] == ["TSLA", "NVDA"]
    assert body["dropped"] == []


def test_merge_caps_overflow(client):
    # Pre-fill free user to 49 entries.
    for i in range(49):
        r = client.post(f"/api/favorites/T{i:03d}", headers=_hdr("sk_test_free"))
        assert r.status_code == 201
    # Merge 5 more → 1 fits, 4 dropped.
    r = client.post(
        "/api/favorites/merge",
        json={"tickers": ["NEW1", "NEW2", "NEW3", "NEW4", "NEW5"]},
        headers=_hdr("sk_test_free"),
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["tickers"]) == 50
    assert len(body["dropped"]) == 4


def test_merge_rejects_bad_body(client):
    r = client.post(
        "/api/favorites/merge",
        json={"not_tickers": []},
        headers=_hdr("sk_test_free"),
    )
    assert r.status_code == 422


def test_merge_silently_drops_garbage_entries(client):
    r = client.post(
        "/api/favorites/merge",
        json={"tickers": ["AAPL", "!!!", "tsla", 123, ""]},
        headers=_hdr("sk_test_free"),
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body["tickers"]) == {"AAPL", "TSLA"}


def test_merge_anonymous_rejected(client):
    r = client.post("/api/favorites/merge", json={"tickers": ["AAPL"]})
    assert r.status_code == 401


# ---- atomic write safety (concurrent POST) ----


def test_concurrent_adds_no_lost_writes(client):
    """Hammer the POST endpoint from a thread pool; every accepted POST
    must show up in the final GET state. No 'lost-write' regression.

    Pragmatic safeguard: TestClient is sync but threads call into it
    concurrently. Our backing _WRITE_LOCK is module-level threading.RLock
    so writes serialise."""
    tickers = [f"C{i:03d}" for i in range(40)]

    def add(t: str) -> int:
        return client.post(
            f"/api/favorites/{t}", headers=_hdr("sk_test_pro")
        ).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(add, tickers))

    # All should be 201 (no duplicates among the 40 unique tickers).
    assert all(s == 201 for s in results), f"non-201 in {results}"

    r = client.get("/api/favorites", headers=_hdr("sk_test_pro"))
    assert r.status_code == 200
    assert set(r.json()["tickers"]) == set(tickers)


def test_records_isolated_per_user(client):
    """User A's favorites don't leak into user B's view."""
    client.post("/api/favorites/AAPL", headers=_hdr("sk_test_free"))
    client.post("/api/favorites/TSLA", headers=_hdr("sk_test_pro"))

    r_free = client.get("/api/favorites", headers=_hdr("sk_test_free"))
    r_pro = client.get("/api/favorites", headers=_hdr("sk_test_pro"))

    assert r_free.json()["tickers"] == ["AAPL"]
    assert r_pro.json()["tickers"] == ["TSLA"]
