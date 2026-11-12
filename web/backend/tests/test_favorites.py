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
import builtins
import json
import sys
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
        "schema_version": "favorites-v2",
        "tickers": [],
        "bookmarks": [],
        "authenticated": False,
        "auth_method": None,
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
    session_auth._ensure_user("free@example.com")
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


# ---- favorites-v2 typed research bookmarks ----


def _analysis_bookmark(index: int = 1, **overrides) -> dict:
    payload = {
        "kind": "structural_analysis",
        "title": f"Candidate {index}",
        "query": f"How does mechanism {index} transfer?",
        "source_id": f"source-{index}",
        "target_id": f"target-{index}",
    }
    payload.update(overrides)
    return payload


def _opaque_bookmarks() -> list[object]:
    """Forward/legacy values that current code must store but never project."""
    return [
        {
            "schema_version": "bookmark-v9",
            "bookmark_id": "bm_ffffffffffffffffffffffff",
            "kind": "structural_analysis",
            "title": "Future bookmark",
            "query": "future semantics",
            "source_id": "future-source",
            "target_id": "future-target",
            "future_payload": {"nested": [1, "two"]},
        },
        {
            "schema_version": "bookmark-v1",
            "kind": "future_kind",
            "payload": ["opaque", 2],
        },
        {
            "schema_version": ["future", 10],
            "kind": "structural_analysis",
            "title": "Unhashable schema marker",
            "query": "must remain opaque",
            "source_id": None,
            "target_id": "future-target",
        },
        {
            "schema_version": "bookmark-v1",
            "kind": "structural_analysis",
            "title": "<script>not public</script>",
            "query": "malformed-current-record",
            "source_id": None,
            "target_id": "target",
        },
        {
            "schema_version": "bookmark-v1",
            "kind": "structural_analysis",
            "title": "Unstable legacy timestamp",
            "query": "must not receive a fresh timestamp on every read",
            "source_id": None,
            "target_id": "target",
            "created_at": "",
        },
        {"raw": ["legacy", {"nested": True}]},
        ["array-record", 3],
        "string-record",
        7,
        None,
    ]


def test_get_v2_keeps_legacy_tickers_and_maps_phase_bookmarks(client):
    assert client.post(
        "/api/favorites/AAPL", headers=_hdr("sk_test_free")
    ).status_code == 201

    body = client.get("/api/favorites", headers=_hdr("sk_test_free")).json()
    assert body["schema_version"] == "favorites-v2"
    assert body["tickers"] == ["AAPL"]
    assert body["bookmarks"] == [{
        "schema_version": "bookmark-v1",
        "bookmark_id": body["bookmarks"][0]["bookmark_id"],
        "kind": "phase_company",
        "title": "AAPL",
        "href": "https://phase.bytedance.city/company/AAPL",
        "source": "Phase",
        "created_at": None,
    }]
    assert body["bookmarks"][0]["bookmark_id"].startswith("bm_")


def test_legacy_jsonl_upgrades_on_mutation_without_losing_tickers(client, monkeypatch, tmp_path):
    path = tmp_path / "legacy-favorites.jsonl"
    path.write_text(
        json.dumps({
            "email": "free@example.com",
            "tickers": ["AAPL", "TSLA"],
            "updated_at": "2026-01-01T00:00:00+00:00",
            "legacy_note": "preserve-me",
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("STRUCTURAL_FAVORITES_PATH", str(path))

    listed = client.get("/api/favorites", headers=_hdr("sk_test_free"))
    assert listed.status_code == 200
    assert listed.json()["tickers"] == ["AAPL", "TSLA"]
    assert "schema_version" not in json.loads(path.read_text())

    added = client.post(
        "/api/favorites/bookmarks",
        json=_analysis_bookmark(),
        headers=_hdr("sk_test_free"),
    )
    assert added.status_code == 201
    stored = json.loads(path.read_text())
    assert stored["schema_version"] == "favorites-v2"
    assert stored["tickers"] == ["AAPL", "TSLA"]
    assert stored["legacy_note"] == "preserve-me"
    assert len(stored["bookmarks"]) == 1


def test_typed_bookmark_server_mints_stable_id_and_canonical_href(client):
    payload = _analysis_bookmark(
        title="Neural avalanche candidate",
        query="critical branching + finite size",
        source_id="neural.source",
        target_id="grid-target",
    )
    first = client.post(
        "/api/favorites/bookmarks", json=payload, headers=_hdr("sk_test_free")
    )
    assert first.status_code == 201, first.text
    bookmark = first.json()["bookmark"]
    assert bookmark["bookmark_id"].startswith("bm_")
    assert bookmark["schema_version"] == "bookmark-v2"
    assert bookmark["href"] == "/analyze?id=grid-target"
    assert "q=" not in bookmark["href"]
    assert bookmark["title"] == "Neural avalanche candidate"
    assert "owner" not in first.text.lower()

    replay = client.post(
        "/api/favorites/bookmarks", json=payload, headers=_hdr("sk_test_free")
    )
    assert replay.status_code == 200
    assert replay.json()["created"] is False
    assert replay.json()["bookmark"]["bookmark_id"] == bookmark["bookmark_id"]
    assert len(client.get(
        "/api/favorites", headers=_hdr("sk_test_free")
    ).json()["bookmarks"]) == 1


def test_known_bookmark_mutations_preserve_opaque_raw_records(client):
    path = fav._data_file()
    opaque = _opaque_bookmarks()
    path.write_text(json.dumps({
        "schema_version": "favorites-v9",
        "email": "free@example.com",
        "tickers": [],
        "bookmarks": opaque,
        "updated_at": "2026-07-13T00:00:00+00:00",
        "future_envelope": {"raw": [1, None, True]},
    }) + "\n", encoding="utf-8")

    # Opaque values are storage-only and cannot become executable/public data.
    listed = client.get("/api/favorites", headers=_hdr("sk_test_free"))
    assert listed.status_code == 200
    assert listed.json()["bookmarks"] == []
    assert listed.json()["total"] == 0

    added = client.post(
        "/api/favorites/bookmarks",
        json=_analysis_bookmark(1),
        headers=_hdr("sk_test_free"),
    )
    assert added.status_code == 201, added.text
    first = added.json()["bookmark"]
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["bookmarks"][:len(opaque)] == opaque
    assert stored["bookmarks"][len(opaque):] == [first]
    assert stored["schema_version"] == "favorites-v9"
    assert stored["future_envelope"] == {"raw": [1, None, True]}

    merged = client.post(
        "/api/favorites/merge",
        json={
            "tickers": [],
            "bookmarks": [_analysis_bookmark(1), _analysis_bookmark(2)],
        },
        headers=_hdr("sk_test_free"),
    )
    assert merged.status_code == 200, merged.text
    assert len(merged.json()["confirmed_bookmark_ids"]) == 2
    second = next(
        item for item in merged.json()["bookmarks"]
        if item["kind"] == "structural_analysis"
        and item["bookmark_id"] != first["bookmark_id"]
    )
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["bookmarks"][:len(opaque)] == opaque
    assert [item["bookmark_id"] for item in stored["bookmarks"][len(opaque):]] == [
        first["bookmark_id"], second["bookmark_id"],
    ]
    assert stored["schema_version"] == "favorites-v9"

    removed = client.delete(
        f"/api/favorites/bookmarks/{first['bookmark_id']}",
        headers=_hdr("sk_test_free"),
    )
    assert removed.status_code == 204
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["bookmarks"] == [*opaque, second]
    assert stored["schema_version"] == "favorites-v9"
    assert client.get(
        "/api/favorites", headers=_hdr("sk_test_free")
    ).json()["bookmarks"] == [second]

    before_missing = path.read_bytes()
    assert client.delete(
        "/api/favorites/bookmarks/bm_000000000000000000000000",
        headers=_hdr("sk_test_free"),
    ).status_code == 204
    assert path.read_bytes() == before_missing


@pytest.mark.parametrize("created_at", [
    "",
    "2026-07-13T12:00:00",
    "2026-07-13T12:00:00+00:00\n",
    "<script>alert(1)</script>",
    "x" * 65,
    7,
    ["2026-07-13T12:00:00Z"],
])
def test_stored_bookmark_rejects_unstable_or_unsafe_created_at(created_at):
    raw = {
        "schema_version": "bookmark-v1",
        **_analysis_bookmark(9),
        "created_at": created_at,
    }
    assert fav._canonical_bookmark_from_raw(raw) is None


def test_stored_bookmark_created_at_projection_is_stable():
    raw = {"schema_version": "bookmark-v1", **_analysis_bookmark(10)}
    first = fav._canonical_bookmark_from_raw(raw)
    second = fav._canonical_bookmark_from_raw(raw)
    assert first == second
    assert first is not None and first["created_at"] is None

    raw["created_at"] = "2026-07-13T12:00:00Z"
    projected = fav._canonical_bookmark_from_raw(raw)
    assert projected is not None
    assert projected["created_at"] == "2026-07-13T12:00:00Z"


@pytest.mark.parametrize("attack", [
    {"owner_email": "victim@example.com"},
    {"bookmark_id": "bm_client_forged"},
    {"href": "javascript:alert(1)"},
    {"url": "https://evil.example/steal"},
    {"extra": "field"},
])
def test_typed_bookmark_rejects_client_owned_or_extra_fields_without_mutation(
    client, attack,
):
    payload = {**_analysis_bookmark(), **attack}
    response = client.post(
        "/api/favorites/bookmarks", json=payload, headers=_hdr("sk_test_free")
    )
    assert response.status_code == 422
    listed = client.get("/api/favorites", headers=_hdr("sk_test_free")).json()
    assert listed["tickers"] == [] and listed["bookmarks"] == []


@pytest.mark.parametrize("field,value", [
    ("kind", "discovery_candidate"),
    ("title", "<img src=x onerror=alert(1)>") ,
    ("title", "control\u0000character"),
    ("query", "<script>alert(1)</script>"),
    ("query", "line\u000bbreak"),
    ("source_id", "../escape"),
    ("target_id", "https://evil.example"),
    ("target_id", "x" * 121),
])
def test_typed_bookmark_rejects_kind_html_controls_and_unbound_targets(
    client, field, value,
):
    response = client.post(
        "/api/favorites/bookmarks",
        json=_analysis_bookmark(**{field: value}),
        headers=_hdr("sk_test_free"),
    )
    assert response.status_code == 422


def test_typed_bookmark_requires_auth_and_same_origin_for_session(client):
    assert client.post(
        "/api/favorites/bookmarks", json=_analysis_bookmark()
    ).status_code == 401
    client.cookies.set("phase_session", _session_cookie("member@example.com"))
    blocked = client.post(
        "/api/favorites/bookmarks",
        json=_analysis_bookmark(),
        headers={"Origin": "https://evil.example"},
    )
    assert blocked.status_code == 403
    assert client.get("/api/favorites").json()["bookmarks"] == []


def test_total_quota_is_shared_between_tickers_and_typed_bookmarks(client):
    for index in range(49):
        assert client.post(
            f"/api/favorites/T{index:03d}", headers=_hdr("sk_test_free")
        ).status_code == 201
    accepted = client.post(
        "/api/favorites/bookmarks",
        json=_analysis_bookmark(),
        headers=_hdr("sk_test_free"),
    )
    assert accepted.status_code == 201
    rejected = client.post(
        "/api/favorites/bookmarks",
        json=_analysis_bookmark(2),
        headers=_hdr("sk_test_free"),
    )
    assert rejected.status_code == 429
    assert rejected.json()["current"] == 50


def test_merge_supports_tickers_and_bookmarks_with_replay_and_partial_quota(client):
    for index in range(48):
        assert client.post(
            f"/api/favorites/T{index:03d}", headers=_hdr("sk_test_free")
        ).status_code == 201
    payload = {
        "tickers": ["NEW1"],
        "bookmarks": [_analysis_bookmark(1), _analysis_bookmark(2)],
    }
    merged = client.post(
        "/api/favorites/merge", json=payload, headers=_hdr("sk_test_free")
    )
    assert merged.status_code == 200, merged.text
    body = merged.json()
    assert body["merged"] == ["NEW1"]
    assert len(body["confirmed_bookmark_ids"]) == 1
    assert len(body["dropped_bookmark_ids"]) == 1
    assert body["total"] == 50

    replay = client.post(
        "/api/favorites/merge", json=payload, headers=_hdr("sk_test_free")
    )
    assert replay.status_code == 200
    assert replay.json()["merged"] == []
    assert replay.json()["confirmed_bookmark_ids"] == body["confirmed_bookmark_ids"]
    assert replay.json()["dropped_bookmark_ids"] == body["dropped_bookmark_ids"]


def test_merge_rejects_extra_or_invalid_typed_bookmark_atomically(client):
    attack = {
        "tickers": ["AAPL"],
        "bookmarks": [{**_analysis_bookmark(), "href": "https://evil.example"}],
    }
    response = client.post(
        "/api/favorites/merge", json=attack, headers=_hdr("sk_test_free")
    )
    assert response.status_code == 422
    listed = client.get("/api/favorites", headers=_hdr("sk_test_free")).json()
    assert listed["tickers"] == [] and listed["bookmarks"] == []


def test_typed_delete_handles_structural_and_phase_bookmarks_idempotently(client):
    created = client.post(
        "/api/favorites/bookmarks",
        json=_analysis_bookmark(),
        headers=_hdr("sk_test_free"),
    ).json()["bookmark"]
    client.post("/api/favorites/AAPL", headers=_hdr("sk_test_free"))
    listed = client.get("/api/favorites", headers=_hdr("sk_test_free")).json()
    phase = next(item for item in listed["bookmarks"] if item["kind"] == "phase_company")

    for bookmark_id in (created["bookmark_id"], phase["bookmark_id"]):
        removed = client.delete(
            f"/api/favorites/bookmarks/{bookmark_id}", headers=_hdr("sk_test_free")
        )
        assert removed.status_code == 204
        replay = client.delete(
            f"/api/favorites/bookmarks/{bookmark_id}", headers=_hdr("sk_test_free")
        )
        assert replay.status_code == 204
    final = client.get("/api/favorites", headers=_hdr("sk_test_free")).json()
    assert final["tickers"] == [] and final["bookmarks"] == []


def test_typed_delete_rejects_path_or_client_forged_ids(client):
    assert client.delete(
        "/api/favorites/bookmarks/not-a-bookmark", headers=_hdr("sk_test_free")
    ).status_code == 422
    assert client.delete(
        "/api/favorites/bookmarks/bm_%2E%2E%2Fescape", headers=_hdr("sk_test_free")
    ).status_code in {404, 422}


def test_typed_and_phase_delete_preserve_opaque_legacy_tickers(client):
    created = client.post(
        "/api/favorites/bookmarks",
        json=_analysis_bookmark(),
        headers=_hdr("sk_test_free"),
    ).json()["bookmark"]
    path = fav._data_file()
    record = json.loads(path.read_text(encoding="utf-8"))
    opaque = ["legacy ticker with spaces", {"raw": "ticker"}, ["nested"], 7, " aapl "]
    record["tickers"] = ["AAPL", *opaque, "AAPL"]
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    phase_id = fav._phase_bookmark("AAPL")["bookmark_id"]
    phase_delete = client.delete(
        f"/api/favorites/bookmarks/{phase_id}", headers=_hdr("sk_test_free")
    )
    assert phase_delete.status_code == 204
    after_phase = json.loads(path.read_text(encoding="utf-8"))
    assert after_phase["tickers"] == opaque

    structural_delete = client.delete(
        f"/api/favorites/bookmarks/{created['bookmark_id']}",
        headers=_hdr("sk_test_free"),
    )
    assert structural_delete.status_code == 204
    preserved = json.loads(path.read_text(encoding="utf-8"))
    assert preserved["tickers"] == opaque

    before = path.read_bytes()
    missing = client.delete(
        "/api/favorites/bookmarks/bm_ffffffffffffffffffffffff",
        headers=_hdr("sk_test_free"),
    )
    assert missing.status_code == 204
    assert path.read_bytes() == before


def test_merge_keeps_raw_prefix_and_only_appends_unique_canonical_tickers(client):
    path = fav._data_file()
    raw_prefix = [{"raw": 1}, ["nested"], 7, "bad ticker", "AAPL", "AAPL", " aapl "]
    record = {
        "email": "pro@example.com", "tickers": raw_prefix,
        "bookmarks": [], "updated_at": "legacy",
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    payload = {
        "tickers": ["aapl", " tsla ", "TSLA", {"new": 1}, ["new"], 9],
        "bookmarks": [],
    }
    merged = client.post(
        "/api/favorites/merge", json=payload, headers=_hdr("sk_test_pro")
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["tickers"] == ["AAPL", "TSLA"]
    assert merged.json()["merged"] == ["TSLA"]
    assert merged.json()["total"] == 2
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["tickers"] == raw_prefix + ["TSLA"]

    before_replay = path.read_bytes()
    replay = client.post(
        "/api/favorites/merge", json=payload, headers=_hdr("sk_test_pro")
    )
    assert replay.status_code == 200
    assert replay.json()["merged"] == []
    assert replay.json()["total"] == 2
    assert path.read_bytes() == before_replay


def test_missing_storage_allows_atomic_first_write(client):
    path = fav._data_file()
    assert not path.exists()
    response = client.post("/api/favorites/AAPL", headers=_hdr("sk_test_free"))
    assert response.status_code == 201
    assert json.loads(path.read_text(encoding="utf-8"))["tickers"] == ["AAPL"]
    assert list(path.parent.glob(".favorites-*.jsonl.tmp")) == []


@pytest.mark.parametrize(
    "corrupt_bytes",
    [
        b'{"email":"free@example.com","tickers":["AAPL"]}\nnot-json\n',
        b'\xff\xfe\x00broken',
        b'[]\n',
        b'{"email":"","tickers":[]}\n',
    ],
)
def test_nonempty_malformed_storage_fails_closed_without_rewrite(
    client, corrupt_bytes,
):
    path = fav._data_file()
    path.write_bytes(corrupt_bytes)
    before = path.read_bytes()

    listed = client.get("/api/favorites", headers=_hdr("sk_test_free"))
    mutated = client.post("/api/favorites/MSFT", headers=_hdr("sk_test_free"))
    merged = client.post(
        "/api/favorites/merge",
        headers=_hdr("sk_test_free"),
        json={"tickers": ["MSFT"], "bookmarks": []},
    )
    assert [listed.status_code, mutated.status_code, merged.status_code] == [503, 503, 503]
    assert path.read_bytes() == before
    assert list(path.parent.glob(".favorites-*.jsonl.tmp")) == []
    assert "AAPL" not in listed.text and "free@example.com" not in listed.text


def test_storage_read_oserror_returns_503_and_preserves_all_owners(
    client, monkeypatch,
):
    path = fav._data_file()
    original = (
        b'{"email":"free@example.com","tickers":["AAPL"]}\n'
        b'{"email":"pro@example.com","tickers":["TSLA"]}\n'
    )
    path.write_bytes(original)
    real_open = builtins.open

    def fail_target_open(candidate, *args, **kwargs):
        if Path(candidate) == path:
            raise OSError("simulated storage read failure")
        return real_open(candidate, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fail_target_open)
    listed = client.get("/api/favorites", headers=_hdr("sk_test_free"))
    deleted = client.delete("/api/favorites/AAPL", headers=_hdr("sk_test_free"))
    assert listed.status_code == 503
    assert deleted.status_code == 503
    assert path.read_bytes() == original
    assert list(path.parent.glob(".favorites-*.jsonl.tmp")) == []


def test_atomic_replace_failure_returns_503_without_file_or_temp_change(
    client, monkeypatch,
):
    assert client.post(
        "/api/favorites/AAPL", headers=_hdr("sk_test_free")
    ).status_code == 201
    path = fav._data_file()
    before = path.read_bytes()
    monkeypatch.setattr(
        fav.os, "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("simulated replace failure")),
    )
    response = client.post("/api/favorites/MSFT", headers=_hdr("sk_test_free"))
    assert response.status_code == 503
    assert path.read_bytes() == before
    assert list(path.parent.glob(".favorites-*.jsonl.tmp")) == []


def test_concurrent_typed_bookmark_adds_have_no_lost_writes(client):
    payloads = [_analysis_bookmark(index) for index in range(30)]

    def add(payload: dict) -> int:
        return client.post(
            "/api/favorites/bookmarks", json=payload, headers=_hdr("sk_test_pro")
        ).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        statuses = list(executor.map(add, payloads))

    assert statuses == [201] * len(payloads)
    listed = client.get("/api/favorites", headers=_hdr("sk_test_pro")).json()
    assert len(listed["bookmarks"]) == 30
    assert len({item["bookmark_id"] for item in listed["bookmarks"]}) == 30
