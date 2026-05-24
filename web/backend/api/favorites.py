"""
User favorites / bookmarks for companies (W15-C, session #10).

Endpoints:
  GET    /api/favorites              → {"tickers": [...]} for current user
                                       (empty array for anonymous — does NOT 401
                                        so client-side store can hydrate from
                                        localStorage seamlessly)
  POST   /api/favorites/{ticker}     → add (201 created / 200 idempotent)
  DELETE /api/favorites/{ticker}     → remove (204 no content)

Auth model
----------
W15-B "current user" is the email tied to the supplied X-API-Key. If no
key is supplied → anonymous → server returns empty list and rejects writes
with 401. Client persists into localStorage until sign-in, then calls the
one-time merge route documented in /api/favorites/merge (POST).

Storage
-------
`web/backend/data/favorites.jsonl` — one JSON record per user (keyed by
email):
    {"email": "alice@example.com", "tickers": ["AAPL","TSLA"], "updated_at": "..."}

We rewrite the whole file on every mutation (atomic rename). It's a flat
file; scale ceiling is ~tens of thousands of users which is well within
beta target. The mutation lock + atomic rename pair makes concurrent POST
safe (no partial writes, last-writer-wins for the *same* user).

Tier limits
-----------
free  → 50 favorites per user
pro   → 500
team  → unlimited
admin → unlimited

Exceeding the cap returns 429 (RFC 7807 RateLimitExceeded, slug
"favorites_limit_exceeded") — the cap is a quota not a rate, but the
client UX is the same ("upgrade for more").
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from auth.api_key import APIKey, verify_api_key
from errors import (
    Forbidden,
    InvalidInput,
    RateLimitExceeded,
    Unauthenticated,
)

router = APIRouter(tags=["favorites"])
logger = logging.getLogger("structural.favorites")

# Ticker validation: 1-10 chars, uppercase letters/digits/dot/dash. The dash
# and dot accommodate exchange suffixes (BRK.A, 7203.T, 0700.HK).
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")

# Tier → max favorites. None == unlimited.
TIER_LIMITS = {
    "free": 50,
    "pro": 500,
    "team": None,
    "admin": None,
}

# Mutation lock — serialises read-modify-write of the jsonl. We intentionally
# use a single global RLock because the file is small (<1MB even at 10k
# users) and beta-stage write QPS is negligible.
_WRITE_LOCK = threading.RLock()


def _data_file() -> Path:
    """Storage path. Override via STRUCTURAL_FAVORITES_PATH in tests."""
    env_override = os.getenv("STRUCTURAL_FAVORITES_PATH")
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parent.parent / "data" / "favorites.jsonl"


def _normalize_ticker(t: str) -> str:
    """Trim + uppercase. Returns "" on garbage."""
    if not isinstance(t, str):
        return ""
    return t.strip().upper()


def _validate_ticker(t: str) -> str:
    """Normalize + raise InvalidInput on bad shape."""
    norm = _normalize_ticker(t)
    if not norm or not _TICKER_RE.match(norm):
        raise InvalidInput(detail=f"invalid ticker: {t!r}")
    return norm


def _load_all() -> dict[str, dict]:
    """Read entire jsonl into {email: record}. Missing file → {}."""
    path = _data_file()
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh, 1):
                raw = raw.strip()
                if not raw or raw.startswith("#"):
                    continue
                try:
                    rec = json.loads(raw)
                    email = (rec.get("email") or "").lower()
                    if email:
                        out[email] = rec
                except Exception as e:
                    logger.warning(
                        "favorites.jsonl line %d malformed: %s", line_no, e
                    )
    except Exception as e:
        logger.error("favorites.jsonl read failed: %s", e)
    return out


def _atomic_write_all(records: dict[str, dict]) -> None:
    """Rewrite full jsonl atomically (tmp file + rename)."""
    path = _data_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".favorites-", suffix=".jsonl.tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for rec in records.values():
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        # Clean up tmp file on failure so we don't leak dot-files.
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def _get_user_record(email: str, all_records: Optional[dict] = None) -> dict:
    """Return existing record for email or a fresh blank one."""
    records = all_records if all_records is not None else _load_all()
    rec = records.get(email.lower())
    if rec is None:
        rec = {"email": email.lower(), "tickers": [], "updated_at": None}
    # Defensive: tickers must be list[str].
    if not isinstance(rec.get("tickers"), list):
        rec["tickers"] = []
    return rec


def _save_user_record(rec: dict) -> None:
    """Read-modify-write under lock."""
    email = (rec.get("email") or "").lower()
    if not email:
        raise InvalidInput(detail="record missing email")
    rec["updated_at"] = datetime.now(timezone.utc).isoformat()
    with _WRITE_LOCK:
        all_recs = _load_all()
        all_recs[email] = rec
        _atomic_write_all(all_recs)


def _require_user(api_key: Optional[APIKey]) -> APIKey:
    """Promote 'optional auth' to 'required auth' for write endpoints."""
    if api_key is None:
        raise Unauthenticated(
            detail="favorites write requires an authenticated session"
        )
    return api_key


def _limit_for_tier(tier: str) -> Optional[int]:
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])


# ---------------- endpoints ----------------


@router.get(
    "/favorites",
    summary="List current user's favorited company tickers",
    description=(
        "Returns the current user's favorite tickers. Anonymous callers "
        "receive an empty list (NOT 401) so client-side stores can hydrate "
        "from localStorage without a login wall."
    ),
)
async def list_favorites(
    request: Request,
    api_key: Optional[APIKey] = Depends(verify_api_key),
):
    if api_key is None:
        return {"tickers": []}
    rec = _get_user_record(api_key.owner_email)
    return {"tickers": rec.get("tickers", [])}


# IMPORTANT — route declaration order:
# `/favorites/merge` MUST be declared BEFORE `/favorites/{ticker}`,
# otherwise FastAPI matches the catch-all `{ticker}` first and "merge"
# never reaches the merge handler. Static paths under a catch-all
# always declare first.


# --------------- merge (anon localStorage → user account) ---------------


@router.post(
    "/favorites/merge",
    summary="One-time merge: anon localStorage tickers → server account",
    description=(
        "Posts a list of tickers gathered while anonymous; server unions "
        "them into the user's account. Tier cap still applies: tickers "
        "beyond the cap are dropped silently (client should warn the user)."
        " Returns final {tickers, dropped}."
    ),
)
async def merge_favorites(
    request: Request,
    api_key: Optional[APIKey] = Depends(verify_api_key),
):
    user = _require_user(api_key)
    try:
        body = await request.json()
    except Exception:
        raise InvalidInput(detail="body must be JSON")
    raw_list = body.get("tickers") if isinstance(body, dict) else None
    if not isinstance(raw_list, list):
        raise InvalidInput(detail="body.tickers must be an array")

    normalized: list[str] = []
    for t in raw_list[:1000]:  # hard cap on payload size to avoid abuse
        try:
            normalized.append(_validate_ticker(t))
        except InvalidInput:
            continue  # silently drop garbage entries

    with _WRITE_LOCK:
        all_recs = _load_all()
        rec = _get_user_record(user.owner_email, all_recs)
        existing: list[str] = list(rec.get("tickers") or [])
        seen = set(existing)
        cap = _limit_for_tier(user.tier)
        dropped: list[str] = []
        for t in normalized:
            if t in seen:
                continue
            if cap is not None and len(existing) >= cap:
                dropped.append(t)
                continue
            existing.append(t)
            seen.add(t)
        rec["tickers"] = existing
        rec["updated_at"] = datetime.now(timezone.utc).isoformat()
        all_recs[user.owner_email.lower()] = rec
        _atomic_write_all(all_recs)

    return {"tickers": existing, "dropped": dropped, "cap": cap}


@router.post(
    "/favorites/{ticker}",
    summary="Add a ticker to favorites (idempotent)",
    description=(
        "Add the given ticker to the current user's favorites. Idempotent: "
        "adding a duplicate returns 200 (no-op). Enforces a per-tier cap "
        "(free=50, pro=500, team/admin=unlimited)."
    ),
)
async def add_favorite(
    ticker: str,
    request: Request,
    api_key: Optional[APIKey] = Depends(verify_api_key),
):
    user = _require_user(api_key)
    norm = _validate_ticker(ticker)

    with _WRITE_LOCK:
        all_recs = _load_all()
        rec = _get_user_record(user.owner_email, all_recs)
        existing: list[str] = list(rec.get("tickers") or [])

        if norm in existing:
            # Idempotent no-op. 200 + flag so client knows what happened.
            return JSONResponse(
                status_code=200,
                content={"ok": True, "added": False, "ticker": norm},
            )

        cap = _limit_for_tier(user.tier)
        if cap is not None and len(existing) >= cap:
            raise RateLimitExceeded(
                detail=(
                    f"favorites cap reached: tier={user.tier} allows {cap}. "
                    f"Upgrade for more."
                ),
                type_slug="favorites_limit_exceeded",
                tier=user.tier,
                cap=cap,
                current=len(existing),
            )

        existing.append(norm)
        rec["tickers"] = existing
        rec["updated_at"] = datetime.now(timezone.utc).isoformat()
        all_recs[user.owner_email.lower()] = rec
        _atomic_write_all(all_recs)

    return JSONResponse(
        status_code=201,
        content={"ok": True, "added": True, "ticker": norm},
    )


@router.delete(
    "/favorites/{ticker}",
    summary="Remove a ticker from favorites",
    description=(
        "Remove the given ticker from the current user's favorites. "
        "Returns 204 whether or not the ticker was present (idempotent)."
    ),
)
async def remove_favorite(
    ticker: str,
    request: Request,
    api_key: Optional[APIKey] = Depends(verify_api_key),
):
    user = _require_user(api_key)
    norm = _validate_ticker(ticker)

    with _WRITE_LOCK:
        all_recs = _load_all()
        rec = _get_user_record(user.owner_email, all_recs)
        existing: list[str] = list(rec.get("tickers") or [])
        if norm in existing:
            existing.remove(norm)
            rec["tickers"] = existing
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            all_recs[user.owner_email.lower()] = rec
            _atomic_write_all(all_recs)

    return Response(status_code=204)
