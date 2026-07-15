"""Per-account Structural research library.

Endpoints:
  GET    /api/favorites              → canonical tickers + typed research bookmarks
                                       (anonymous receives an empty envelope)
  POST   /api/favorites/merge        → merge anonymous tickers and typed bookmarks
                                       into the authenticated account
  POST   /api/favorites/bookmarks    → save a typed Structural analysis bookmark
  DELETE /api/favorites/bookmarks/id → remove an account bookmark
  POST   /api/favorites/{ticker}     → add (201 created / 200 idempotent)
  DELETE /api/favorites/{ticker}     → remove (204 no content)

Auth model
----------
The current owner is resolved from the canonical direct/SSO account session
or a valid API key. Conflicting credentials fail closed. Anonymous reads return
an empty envelope and writes require authentication; local items can be merged
once after sign-in.

Storage
-------
Production storage is configured outside the Git checkout. Records preserve
legacy/unknown raw bookmark entries for lossless account export and rollback,
while public responses expose only canonical supported bookmark schemas.

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
"favorites_limit_exceeded") — the cap is an abuse-control quota, not a
purchase prompt. There is currently no paid upgrade flow; clients tell users
to remove an item before retrying.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import json
import hashlib
import os
import re
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

if __package__ == "web.backend.api":
    from ..logging_config import get_logger, new_incident_id
    from ..auth.api_key import APIKey, verify_api_key
    from .auth import (
        account_deletion_epoch,
        account_owner_transaction,
        api_key_retired_by_account_deletion,
        require_same_origin,
        resolve_account_user,
    )
    from ..errors import (
        Forbidden,
        InvalidInput,
        RateLimitExceeded,
        Unauthenticated,
        UpstreamUnavailable,
    )
    from ..services.input_limits import MAX_RESEARCH_QUERY_CHARS
else:
    from logging_config import get_logger, new_incident_id
    from auth.api_key import APIKey, verify_api_key
    from api.auth import (
        account_deletion_epoch,
        account_owner_transaction,
        api_key_retired_by_account_deletion,
        require_same_origin,
        resolve_account_user,
    )
    from errors import (
        Forbidden,
        InvalidInput,
        RateLimitExceeded,
        Unauthenticated,
        UpstreamUnavailable,
    )
    from services.input_limits import MAX_RESEARCH_QUERY_CHARS

router = APIRouter(tags=["favorites"])
logger = get_logger("structural.favorites")

# Ticker validation: 1-10 chars, uppercase letters/digits/dot/dash. The dash
# and dot accommodate exchange suffixes (BRK.A, 7203.T, 0700.HK).
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")
_ENTITY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_BOOKMARK_ID_RE = re.compile(r"^bm_[0-9a-f]{24}$")
_HTML_TAG_RE = re.compile(r"<\s*/?\s*(?:[A-Za-z]|!)[^>]*>")
FAVORITES_SCHEMA_VERSION = "favorites-v2"
BOOKMARK_SCHEMA_VERSION = "bookmark-v1"
STRUCTURAL_BOOKMARK_SCHEMA_VERSION = "bookmark-v2"
MAX_MERGE_BOOKMARKS = 100
_FingerprintItem = Annotated[StrictStr, Field(min_length=1, max_length=120)]

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


def _safe_text(
    value: str,
    field: str,
    maximum: int,
    *,
    allow_layout: bool = False,
) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{field} must contain 1-{maximum} characters")
    for char in normalized:
        if unicodedata.category(char) in {"Cc", "Cf"}:
            if allow_layout and char in {"\n", "\r", "\t"}:
                continue
            raise ValueError(f"{field} contains control characters")
    if _HTML_TAG_RE.search(normalized):
        raise ValueError(f"{field} must be plain text, not HTML")
    return normalized


def _entity_id(value: str, field: str) -> str:
    normalized = value.strip()
    if not _ENTITY_ID_RE.fullmatch(normalized):
        raise ValueError(f"{field} is not a canonical Structural identifier")
    return normalized


class StructuralBookmarkFingerprintInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_query: StrictStr = Field(
        min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS
    )
    summary: StrictStr = Field(min_length=8, max_length=1000)
    variables: list[_FingerprintItem] = Field(default_factory=list, max_length=12)
    constraints: list[_FingerprintItem] = Field(default_factory=list, max_length=12)
    unknowns: list[_FingerprintItem] = Field(default_factory=list, max_length=12)
    revision: StrictInt = Field(default=1, ge=1, le=1000)

    @field_validator("source_query")
    @classmethod
    def validate_source_query(cls, value: str) -> str:
        return _safe_text(
            value,
            "fingerprint.source_query",
            MAX_RESEARCH_QUERY_CHARS,
            allow_layout=True,
        )

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        return _safe_text(value, "fingerprint.summary", 1000, allow_layout=True)

    @field_validator("variables", "constraints", "unknowns")
    @classmethod
    def validate_items(cls, values: list[str], info) -> list[str]:
        return [
            _safe_text(item, f"fingerprint.{info.field_name}", 120)
            for item in values
        ]


class StructuralAnalysisBookmarkInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["structural_analysis"]
    title: StrictStr = Field(min_length=1, max_length=240)
    query: StrictStr = Field(
        min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS
    )
    source_id: Optional[StrictStr] = Field(default=None, min_length=1, max_length=120)
    target_id: StrictStr = Field(min_length=1, max_length=120)
    fingerprint: Optional[StructuralBookmarkFingerprintInput] = None
    origin_discovery_id: Optional[StrictStr] = Field(
        default=None,
        pattern=r"^discovery-[0-9a-f]{16}$",
    )
    origin_contract_version: Optional[Literal["discovery-candidate-v2"]] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _safe_text(value, "title", 240)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        return _safe_text(
            value, "query", MAX_RESEARCH_QUERY_CHARS, allow_layout=True
        )

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _entity_id(value, "source_id")

    @field_validator("target_id")
    @classmethod
    def validate_target_id(cls, value: str) -> str:
        return _entity_id(value, "target_id")

    @model_validator(mode="after")
    def validate_bound_context(self):
        if self.fingerprint is not None and self.fingerprint.source_query != self.query:
            raise ValueError("fingerprint does not match bookmark query")
        if (self.origin_discovery_id is None) != (
            self.origin_contract_version is None
        ):
            raise ValueError("discovery origin fields must be provided together")
        return self


class FavoritesMergeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # Legacy Phase clients intentionally receive per-entry drop semantics.
    tickers: list[object] = Field(default_factory=list, max_length=1000)
    bookmarks: list[StructuralAnalysisBookmarkInput] = Field(
        default_factory=list, max_length=MAX_MERGE_BOOKMARKS
    )


class PhaseCompanyBookmark(BaseModel):
    """Canonical public projection of one legacy Phase company ticker."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["bookmark-v1"]
    bookmark_id: str = Field(pattern=r"^bm_[0-9a-f]{24}$")
    kind: Literal["phase_company"]
    title: str = Field(min_length=1, max_length=10)
    href: str = Field(min_length=1)
    source: Literal["Phase"]
    created_at: None = None


class StructuralAnalysisBookmark(BaseModel):
    """Canonical public projection of one Structural analysis bookmark."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["bookmark-v2"]
    bookmark_id: str = Field(pattern=r"^bm_[0-9a-f]{24}$")
    kind: Literal["structural_analysis"]
    title: str = Field(min_length=1, max_length=240)
    query: str = Field(min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS)
    source_id: Optional[str] = None
    target_id: str = Field(min_length=1, max_length=120)
    fingerprint: Optional[StructuralBookmarkFingerprintInput] = None
    origin_discovery_id: Optional[str] = Field(
        default=None,
        pattern=r"^discovery-[0-9a-f]{16}$",
    )
    origin_contract_version: Optional[Literal["discovery-candidate-v2"]] = None
    href: str = Field(min_length=1)
    source: Literal["Structural"]
    created_at: Optional[str] = None


PublicBookmark = PhaseCompanyBookmark | StructuralAnalysisBookmark


class FavoritesResponse(BaseModel):
    """Public research-library envelope; opaque storage records never appear."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["favorites-v2"]
    tickers: list[str]
    bookmarks: list[PublicBookmark]
    authenticated: bool
    auth_method: Optional[Literal["session", "api_key"]] = None
    cap: Optional[int] = Field(default=None, ge=0)
    total: Optional[int] = Field(default=None, ge=0)


class FavoritesMergeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["favorites-v2"]
    tickers: list[str]
    bookmarks: list[PublicBookmark]
    merged: list[str]
    dropped: list[str]
    confirmed_bookmark_ids: list[str]
    dropped_bookmark_ids: list[str]
    cap: Optional[int] = Field(default=None, ge=0)
    total: int = Field(ge=0)


class BookmarkMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]
    created: bool
    bookmark: StructuralAnalysisBookmark


class TickerMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]
    added: bool
    ticker: str = Field(pattern=r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")


def _data_file() -> Path:
    """Persistent storage path; production must never default into Git."""
    env_override = os.getenv("STRUCTURAL_FAVORITES_PATH", "").strip()
    if env_override:
        target = Path(env_override)
    else:
        auth_data_dir = os.getenv("AUTH_DATA_DIR", "").strip()
        if auth_data_dir:
            target = Path(auth_data_dir) / "favorites.jsonl"
        elif os.getenv("STRUCTURAL_ENV", "dev").lower() == "prod":
            raise RuntimeError(
                "favorites persistence requires AUTH_DATA_DIR or "
                "STRUCTURAL_FAVORITES_PATH in production"
            )
        else:
            target = Path(__file__).resolve().parent.parent / "data" / "favorites.jsonl"
    if os.getenv("STRUCTURAL_ENV", "dev").lower() == "prod":
        repo_root = Path(__file__).resolve().parents[3]
        try:
            target.resolve().relative_to(repo_root)
        except ValueError:
            pass
        else:
            raise RuntimeError("favorites persistence path must be outside the Git checkout")
    _migrate_legacy_file(target)
    return target


def _legacy_data_file() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "favorites.jsonl"


def _migrate_legacy_file(target: Path) -> None:
    """Copy a pre-persistence-boundary JSONL once, without overwriting data."""
    legacy = _legacy_data_file()
    if target == legacy or target.exists() or not legacy.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = legacy.read_bytes()
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
        except Exception:
            target.unlink(missing_ok=True)
            raise
        logger.info("structural.favorites.storage_migrated")
    except FileExistsError:
        return


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


def _canonical_stored_ticker(value: object) -> Optional[str]:
    """Return a stored ticker only when its JSON value is already canonical.

    Legacy rows may contain arbitrary JSON values. They remain opaque storage
    payloads: normalization is for new request input, never an implicit
    migration of historical values.
    """
    if not isinstance(value, str):
        return None
    if value != value.strip().upper():
        return None
    return value if _TICKER_RE.fullmatch(value) else None


def _canonical_tickers(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: dict[str, bool] = {}
    for raw in values:
        ticker = _canonical_stored_ticker(raw)
        if ticker is not None and ticker not in seen:
            seen[ticker] = True
            result.append(ticker)
    return result


def _bookmark_id(kind: str, identity: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{identity}".encode("utf-8")).hexdigest()[:24]
    return f"bm_{digest}"


def _phase_bookmark(ticker: str) -> dict:
    norm = _validate_ticker(ticker)
    return {
        "schema_version": BOOKMARK_SCHEMA_VERSION,
        "bookmark_id": _bookmark_id("phase_company", norm),
        "kind": "phase_company",
        "title": norm,
        "href": f"https://phase.bytedance.city/company/{quote(norm, safe='')}",
        "source": "Phase",
        "created_at": None,
    }


def _analysis_bookmark(
    value: StructuralAnalysisBookmarkInput, *, created_at: Optional[str] = None
) -> dict:
    typed_target = {
        "query": value.query,
        "source_id": value.source_id,
        "target_id": value.target_id,
        **(
            {"fingerprint": value.fingerprint.model_dump(mode="json")}
            if value.fingerprint is not None else {}
        ),
        **(
            {
                "origin_discovery_id": value.origin_discovery_id,
                "origin_contract_version": value.origin_contract_version,
            }
            if value.origin_discovery_id is not None else {}
        ),
    }
    identity = json.dumps(
        typed_target,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema_version": STRUCTURAL_BOOKMARK_SCHEMA_VERSION,
        "bookmark_id": _bookmark_id("structural_analysis", identity),
        "kind": "structural_analysis",
        "title": value.title,
        **typed_target,
        # Navigation is intentionally incomplete without the typed payload.
        # The authenticated frontend creates a one-use sessionStorage handoff
        # at click time; question/fingerprint never enter this pathname.
        "href": f"/analyze?id={quote(value.target_id, safe='')}",
        "source": "Structural",
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }


def _raw_bookmarks(rec: dict) -> list[object]:
    """Copy the storage list without interpreting or normalizing its values."""
    raw_bookmarks = rec.get("bookmarks", [])
    if not isinstance(raw_bookmarks, list):
        raise ValueError("favorites record bookmarks must be a list")
    return list(raw_bookmarks)


def _canonical_bookmark_from_raw(raw: object) -> Optional[dict]:
    """Project one currently understood record; keep every other value opaque."""
    if not isinstance(raw, dict) or raw.get("kind") != "structural_analysis":
        return None
    # A future schema can reuse today's field names with different semantics.
    # Never reinterpret it as bookmark-v1 merely because it happens to parse.
    if raw.get("schema_version") not in (
        None,
        BOOKMARK_SCHEMA_VERSION,
        STRUCTURAL_BOOKMARK_SCHEMA_VERSION,
    ):
        return None
    allowed_fields = {
        "schema_version",
        "bookmark_id",
        "kind",
        "title",
        "query",
        "source_id",
        "target_id",
        "fingerprint",
        "origin_discovery_id",
        "origin_contract_version",
        "href",  # known legacy field; ignored and rebuilt safely
        "source",
        "created_at",
    }
    if set(raw) - allowed_fields:
        return None
    created_at = raw.get("created_at")
    if created_at is not None:
        if (
            not isinstance(created_at, str)
            or not created_at
            or len(created_at) > 64
            or created_at != created_at.strip()
            or any(
                unicodedata.category(char).startswith("C")
                for char in created_at
            )
        ):
            return None
        try:
            parsed_created_at = datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            )
        except ValueError:
            return None
        if parsed_created_at.tzinfo is None or parsed_created_at.utcoffset() is None:
            return None
    try:
        model = StructuralAnalysisBookmarkInput.model_validate({
            "kind": raw.get("kind"),
            "title": raw.get("title"),
            "query": raw.get("query"),
            "source_id": raw.get("source_id"),
            "target_id": raw.get("target_id"),
            "fingerprint": raw.get("fingerprint"),
            "origin_discovery_id": raw.get("origin_discovery_id"),
            "origin_contract_version": raw.get("origin_contract_version"),
        })
        bookmark = _analysis_bookmark(model, created_at=created_at)
        if created_at is None:
            bookmark["created_at"] = None
        return bookmark
    except (TypeError, ValueError):
        return None


def _stored_bookmarks(rec: dict) -> list[dict]:
    valid: list[dict] = []
    seen: set[str] = set()
    for raw in _raw_bookmarks(rec):
        bookmark = _canonical_bookmark_from_raw(raw)
        if bookmark is None:
            continue
        if bookmark["bookmark_id"] in seen:
            continue
        seen.add(bookmark["bookmark_id"])
        valid.append(bookmark)
    return valid


def _public_bookmarks(rec: dict) -> list[dict]:
    phase = [_phase_bookmark(ticker) for ticker in _canonical_tickers(rec.get("tickers"))]
    return phase + _stored_bookmarks(rec)


def _total_favorites(rec: dict) -> int:
    return len(_canonical_tickers(rec.get("tickers"))) + len(_stored_bookmarks(rec))


def _storage_unavailable(action: str, exc: BaseException) -> UpstreamUnavailable:
    """Build a secret-safe, asset-safe persistence failure response."""
    logger.error(
        "structural.favorites.storage_failed",
        error_type=type(exc).__name__,
        incident_id=new_incident_id(),
    )
    return UpstreamUnavailable(
        detail="Favorites storage is temporarily unavailable. Please try again.",
        type_slug="favorites_storage_unavailable",
    )


def _validated_storage_record(value: object, line_no: int) -> tuple[str, dict]:
    """Validate the JSONL envelope without normalizing opaque legacy values."""
    if not isinstance(value, dict):
        raise ValueError(f"line {line_no} must contain an object")
    email = value.get("email")
    if not isinstance(email, str) or not email.strip():
        raise ValueError(f"line {line_no} has no owner")
    tickers = value.get("tickers", [])
    bookmarks = value.get("bookmarks", [])
    if not isinstance(tickers, list):
        raise ValueError(f"line {line_no} tickers must be a list")
    if not isinstance(bookmarks, list):
        raise ValueError(f"line {line_no} bookmarks must be a list")
    # Missing containers are valid legacy records. Add them only to the
    # in-memory representation; reads never rewrite or migrate the source.
    value.setdefault("tickers", [])
    value.setdefault("bookmarks", [])
    return email.strip().lower(), value


def _load_all() -> dict[str, dict]:
    """Read all records; only a genuinely missing file means an empty store."""
    out: dict[str, dict] = {}
    try:
        path = _data_file()
    except Exception as exc:
        raise _storage_unavailable("resolve", exc) from exc
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh, 1):
                payload = raw.strip()
                if not payload:
                    continue
                email, rec = _validated_storage_record(json.loads(payload), line_no)
                if email in out:
                    raise ValueError(f"line {line_no} duplicates an owner")
                out[email] = rec
    except FileNotFoundError as exc:
        # A missing path is the sole empty-store case. If the path still
        # exists, opening it failed and treating that as empty could erase it
        # on the next mutation.
        try:
            still_exists = path.exists()
        except OSError as check_exc:
            raise _storage_unavailable("read", check_exc) from check_exc
        if still_exists:
            raise _storage_unavailable("read", exc) from exc
        return {}
    except Exception as exc:
        raise _storage_unavailable("read", exc) from exc
    return out


def _atomic_write_all(records: dict[str, dict]) -> None:
    """Rewrite full jsonl atomically (tmp file + rename)."""
    tmp_path: Optional[str] = None
    try:
        path = _data_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".favorites-", suffix=".jsonl.tmp", dir=str(path.parent)
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for rec in records.values():
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception as exc:
        # Clean up tmp file on failure so we don't leak dot-files.
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            except OSError as cleanup_exc:
                logger.error(
                    "structural.favorites.storage_cleanup_failed",
                    error_type=type(cleanup_exc).__name__,
                    incident_id=new_incident_id(),
                )
        raise _storage_unavailable("write", exc) from exc


def _get_user_record(email: str, all_records: Optional[dict] = None) -> dict:
    """Return existing record for email or a fresh blank one."""
    records = all_records if all_records is not None else _load_all()
    rec = records.get(email.lower())
    if rec is None:
        rec = {
            "schema_version": FAVORITES_SCHEMA_VERSION,
            "email": email.lower(),
            "tickers": [],
            "bookmarks": [],
            "updated_at": None,
        }
    # Storage validation guarantees a list container. Individual ticker values
    # intentionally remain opaque JSON until an explicit canonical match.
    if not isinstance(rec.get("tickers"), list):
        raise ValueError("favorites record tickers must be a list")
    if not isinstance(rec.get("bookmarks"), list):
        raise ValueError("favorites record bookmarks must be a list")
    _mark_legacy_storage_schema(rec)
    return rec


def _mark_legacy_storage_schema(rec: dict) -> None:
    """Version only an unversioned legacy envelope; preserve future markers."""
    if "schema_version" not in rec:
        rec["schema_version"] = FAVORITES_SCHEMA_VERSION


def _save_user_record(rec: dict) -> None:
    """Read-modify-write under lock."""
    email = (rec.get("email") or "").lower()
    if not email:
        raise InvalidInput(detail="record missing email")
    _mark_legacy_storage_schema(rec)
    rec["updated_at"] = datetime.now(timezone.utc).isoformat()
    with _WRITE_LOCK:
        all_recs = _load_all()
        all_recs[email] = rec
        _atomic_write_all(all_recs)


def export_account_favorites(email: str) -> dict:
    """Registry adapter: export one account's server-side favorites."""
    records = _load_all()
    rec = records.get(email.lower())
    return {
        "schema_version": FAVORITES_SCHEMA_VERSION,
        "exists": rec is not None,
        "tickers": _canonical_tickers((rec or {}).get("tickers")),
        "bookmarks": _stored_bookmarks(rec or {}),
        "updated_at": (rec or {}).get("updated_at"),
    }


def snapshot_account_favorites(email: str) -> dict:
    """Private, lossless compensation snapshot; never return through an API."""
    records = _load_all()
    rec = records.get(email.lower())
    return {
        "snapshot_version": "favorites-raw-snapshot-v1",
        "exists": rec is not None,
        "record": copy.deepcopy(rec) if rec is not None else None,
    }


def delete_account_favorites(email: str) -> dict:
    """Registry adapter: remove one account without touching other owners."""
    with _WRITE_LOCK:
        records = _load_all()
        removed = records.pop(email.lower(), None)
        if removed is not None:
            _atomic_write_all(records)
        return {
            "records": int(removed is not None),
            "tickers": len(_canonical_tickers((removed or {}).get("tickers"))),
            "bookmarks": len(_stored_bookmarks(removed or {})),
        }


def restore_account_favorites(email: str, snapshot: object, _removed: object = None) -> None:
    """Compensating write used if a later account deletion step fails."""
    if not isinstance(snapshot, dict) or not snapshot.get("exists"):
        return
    with _WRITE_LOCK:
        records = _load_all()
        if snapshot.get("snapshot_version") == "favorites-raw-snapshot-v1":
            raw_record = copy.deepcopy(snapshot.get("record"))
            owner, restored = _validated_storage_record(raw_record, 1)
            if owner != email.lower():
                raise ValueError("favorites snapshot owner mismatch")
            records[owner] = restored
        else:
            # Backward-compatible recovery for an in-flight pre-v2 snapshot.
            records[email.lower()] = {
                "schema_version": FAVORITES_SCHEMA_VERSION,
                "email": email.lower(),
                "tickers": list(snapshot["tickers"]),
                "bookmarks": list(snapshot.get("bookmarks", [])),
                "updated_at": snapshot.get("updated_at"),
            }
        _atomic_write_all(records)


@dataclass(frozen=True)
class _FavoriteUser:
    owner_email: str
    tier: str
    auth_method: str
    deletion_epoch: Optional[str] = None


def _resolve_user(request: Request, api_key: Optional[APIKey]) -> Optional[_FavoriteUser]:
    """Session is authoritative; API key remains a compatibility fallback."""
    session_user, status = resolve_account_user(request)
    if status == "valid" and session_user:
        return _FavoriteUser(session_user["email"], session_user["tier"], "session")
    if status != "absent":
        if status == "credential_conflict":
            logger.warning("structural.favorites.credential_conflict")
            raise Unauthenticated(
                detail="Conflicting authenticated credentials; sign in again",
                status=409, error="credential_conflict",
            )
        logger.warning("structural.favorites.session_invalid")
        raise Unauthenticated(detail="invalid or revoked authenticated session")
    if api_key is not None:
        deletion_epoch = account_deletion_epoch(api_key.owner_email)
        if api_key_retired_by_account_deletion(
            api_key.owner_email, api_key.created_at,
        ):
            logger.warning("structural.favorites.api_key_retired")
            raise Unauthenticated(detail="API key predates account deletion")
        return _FavoriteUser(
            api_key.owner_email, api_key.tier, "api_key", deletion_epoch,
        )
    return None


def _require_user(request: Request, api_key: Optional[APIKey]) -> _FavoriteUser:
    user = _resolve_user(request, api_key)
    if user is None:
        raise Unauthenticated(
            detail="favorites write requires an authenticated session"
        )
    if user.auth_method == "session":
        origin_error = require_same_origin(request)
        if origin_error is not None:
            raise Forbidden(detail="invalid origin for cookie-authenticated mutation")
    return user


@contextmanager
def _favorite_write_transaction(
    request: Request, api_key: Optional[APIKey],
):
    """Serialize and revalidate an owner-scoped mutation with account erase."""
    provisional = _require_user(request, api_key)
    with account_owner_transaction(provisional.owner_email):
        current = _require_user(request, api_key)
        if current.owner_email.lower() != provisional.owner_email.lower():
            raise Unauthenticated(
                detail="Authenticated owner changed; retry with one credential",
                status=409,
                error="credential_conflict",
            )
        if current.deletion_epoch != provisional.deletion_epoch:
            raise Unauthenticated(detail="Account deletion state changed; retry")
        with _WRITE_LOCK:
            yield current


def _limit_for_tier(tier: str) -> Optional[int]:
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])


# ---------------- endpoints ----------------


@router.get(
    "/favorites",
    response_model=FavoritesResponse,
    response_model_exclude_unset=True,
    summary="List the current account's research library",
    description=(
        "Returns canonical typed research bookmarks plus legacy company "
        "tickers. Anonymous callers receive an empty envelope (not 401) so "
        "the client can stage local items before sign-in."
    ),
)
async def list_favorites(
    request: Request,
    api_key: Optional[APIKey] = Depends(verify_api_key),
):
    user = _resolve_user(request, api_key)
    if user is None:
        return {
            "schema_version": FAVORITES_SCHEMA_VERSION,
            "tickers": [],
            "bookmarks": [],
            "authenticated": False,
            "auth_method": None,
        }
    rec = _get_user_record(user.owner_email)
    return {
        "schema_version": FAVORITES_SCHEMA_VERSION,
        "tickers": _canonical_tickers(rec.get("tickers")),
        "bookmarks": _public_bookmarks(rec),
        "authenticated": True,
        "auth_method": user.auth_method,
        "cap": _limit_for_tier(user.tier),
        "total": _total_favorites(rec),
    }


# IMPORTANT — route declaration order:
# `/favorites/merge` MUST be declared BEFORE `/favorites/{ticker}`,
# otherwise FastAPI matches the catch-all `{ticker}` first and "merge"
# never reaches the merge handler. Static paths under a catch-all
# always declare first.


# --------------- merge (anon localStorage → user account) ---------------


@router.post(
    "/favorites/merge",
    response_model=FavoritesMergeResponse,
    response_model_exclude_unset=True,
    summary="Merge anonymous research-library items into the account",
    description=(
        "Unions supported anonymous company tickers and typed Structural "
        "analysis bookmarks into the authenticated account. The response "
        "explicitly returns dropped ticker and bookmark identifiers when the "
        "account cap is reached; clients must keep or warn about those items."
    ),
)
async def merge_favorites(
    request: Request,
    body: FavoritesMergeInput,
    api_key: Optional[APIKey] = Depends(verify_api_key),
):
    normalized: list[str] = []
    for t in body.tickers:
        try:
            normalized.append(_validate_ticker(t))
        except InvalidInput:
            continue  # silently drop garbage entries
    submitted_bookmarks = [_analysis_bookmark(item) for item in body.bookmarks]

    with _favorite_write_transaction(request, api_key) as user:
        all_recs = _load_all()
        rec = _get_user_record(user.owner_email, all_recs)
        existing_raw: list[object] = list(rec.get("tickers") or [])
        existing_canonical = _canonical_tickers(existing_raw)
        raw_bookmarks = _raw_bookmarks(rec)
        stored_bookmarks = _stored_bookmarks(rec)
        stored_ids = {item["bookmark_id"] for item in stored_bookmarks}
        seen_tickers = {ticker: True for ticker in existing_canonical}
        cap = _limit_for_tier(user.tier)
        dropped: list[str] = []
        merged: list[str] = []
        total = len(existing_canonical) + len(stored_bookmarks)
        for t in normalized:
            if t in seen_tickers:
                continue
            if cap is not None and total >= cap:
                dropped.append(t)
                continue
            existing_raw.append(t)
            existing_canonical.append(t)
            seen_tickers[t] = True
            merged.append(t)
            total += 1
        confirmed_bookmark_ids: list[str] = []
        dropped_bookmark_ids: list[str] = []
        added_bookmarks: list[dict] = []
        for bookmark in submitted_bookmarks:
            bookmark_id = bookmark["bookmark_id"]
            if bookmark_id in stored_ids:
                if bookmark_id not in confirmed_bookmark_ids:
                    confirmed_bookmark_ids.append(bookmark_id)
                continue
            if cap is not None and total >= cap:
                if bookmark_id not in dropped_bookmark_ids:
                    dropped_bookmark_ids.append(bookmark_id)
                continue
            raw_bookmarks.append(bookmark)
            stored_bookmarks.append(bookmark)
            added_bookmarks.append(bookmark)
            stored_ids.add(bookmark_id)
            confirmed_bookmark_ids.append(bookmark_id)
            total += 1
        changed = bool(merged) or bool(added_bookmarks)
        if changed:
            rec["tickers"] = existing_raw
            rec["bookmarks"] = raw_bookmarks
            _mark_legacy_storage_schema(rec)
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            all_recs[user.owner_email.lower()] = rec
            _atomic_write_all(all_recs)

    logger.info(
        "structural.favorites.merged",
        count=total,
    )

    return {
        "schema_version": FAVORITES_SCHEMA_VERSION,
        "tickers": existing_canonical,
        "bookmarks": _public_bookmarks(rec),
        "merged": merged,
        "dropped": dropped,
        "confirmed_bookmark_ids": confirmed_bookmark_ids,
        "dropped_bookmark_ids": dropped_bookmark_ids,
        "cap": cap,
        "total": total,
    }


@router.post(
    "/favorites/bookmarks",
    response_model=BookmarkMutationResponse,
    status_code=201,
    responses={
        200: {
            "model": BookmarkMutationResponse,
            "description": "Bookmark already existed; no duplicate was created",
        },
    },
    summary="Save one typed Structural research bookmark",
)
async def add_bookmark(
    request: Request,
    bookmark: StructuralAnalysisBookmarkInput,
    api_key: Optional[APIKey] = Depends(verify_api_key),
):
    candidate = _analysis_bookmark(bookmark)
    bookmark_id = candidate["bookmark_id"]

    with _favorite_write_transaction(request, api_key) as user:
        all_recs = _load_all()
        rec = _get_user_record(user.owner_email, all_recs)
        raw_bookmarks = _raw_bookmarks(rec)
        stored = _stored_bookmarks(rec)
        existing = next(
            (item for item in stored if item["bookmark_id"] == bookmark_id), None
        )
        if existing is not None:
            return JSONResponse(status_code=200, content={
                "ok": True, "created": False, "bookmark": existing,
            })
        cap = _limit_for_tier(user.tier)
        total = len(_canonical_tickers(rec.get("tickers"))) + len(stored)
        if cap is not None and total >= cap:
            raise RateLimitExceeded(
                detail=(
                    f"favorites cap reached: tier={user.tier} allows {cap}. "
                    "Remove an item before adding another."
                ),
                type_slug="favorites_limit_exceeded",
                tier=user.tier,
                cap=cap,
                current=total,
            )
        raw_bookmarks.append(candidate)
        rec["bookmarks"] = raw_bookmarks
        _mark_legacy_storage_schema(rec)
        rec["updated_at"] = datetime.now(timezone.utc).isoformat()
        all_recs[user.owner_email.lower()] = rec
        _atomic_write_all(all_recs)

    logger.info(
        "structural.favorites.bookmark_added",
        count=total + 1,
    )
    return JSONResponse(status_code=201, content={
        "ok": True, "created": True, "bookmark": candidate,
    })


@router.delete(
    "/favorites/bookmarks/{bookmark_id}",
    status_code=204,
    response_class=Response,
    summary="Remove one typed account bookmark",
)
async def remove_bookmark(
    bookmark_id: str,
    request: Request,
    api_key: Optional[APIKey] = Depends(verify_api_key),
):
    if not _BOOKMARK_ID_RE.fullmatch(bookmark_id):
        raise InvalidInput(detail="invalid bookmark id")

    with _favorite_write_transaction(request, api_key) as user:
        all_recs = _load_all()
        rec = _get_user_record(user.owner_email, all_recs)
        tickers = list(rec.get("tickers", []))
        raw_bookmarks = _raw_bookmarks(rec)
        next_raw_bookmarks: list[object] = []
        removed_structural = False
        for raw in raw_bookmarks:
            canonical = _canonical_bookmark_from_raw(raw)
            if canonical is not None and canonical["bookmark_id"] == bookmark_id:
                removed_structural = True
                continue
            next_raw_bookmarks.append(raw)
        next_tickers = []
        for raw_ticker in tickers:
            canonical = _canonical_stored_ticker(raw_ticker)
            if canonical is None or _phase_bookmark(canonical)["bookmark_id"] != bookmark_id:
                next_tickers.append(raw_ticker)
        removed = removed_structural or len(next_tickers) != len(tickers)
        if removed:
            rec["bookmarks"] = next_raw_bookmarks
            rec["tickers"] = next_tickers
            _mark_legacy_storage_schema(rec)
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            all_recs[user.owner_email.lower()] = rec
            _atomic_write_all(all_recs)
        total = len(_stored_bookmarks(rec)) + len(_canonical_tickers(next_tickers))

    logger.info(
        "structural.favorites.bookmark_remove_completed",
        count=total,
    )
    return Response(status_code=204)


@router.post(
    "/favorites/{ticker}",
    response_model=TickerMutationResponse,
    status_code=201,
    responses={
        200: {
            "model": TickerMutationResponse,
            "description": "Ticker already existed; no duplicate was created",
        },
    },
    summary="Add a ticker to favorites (idempotent)",
    description=(
        "Add the given ticker to the current user's favorites. Idempotent: "
        "adding a duplicate returns 200 (no-op). Enforces the account's "
        "configured abuse-control cap; no paid upgrade is currently sold."
    ),
)
async def add_favorite(
    ticker: str,
    request: Request,
    api_key: Optional[APIKey] = Depends(verify_api_key),
):
    norm = _validate_ticker(ticker)

    with _favorite_write_transaction(request, api_key) as user:
        all_recs = _load_all()
        rec = _get_user_record(user.owner_email, all_recs)
        existing: list[object] = list(rec.get("tickers") or [])
        canonical = _canonical_tickers(existing)

        if norm in canonical:
            # Idempotent no-op. 200 + flag so client knows what happened.
            return JSONResponse(
                status_code=200,
                content={"ok": True, "added": False, "ticker": norm},
            )

        cap = _limit_for_tier(user.tier)
        total = len(canonical) + len(_stored_bookmarks(rec))
        if cap is not None and total >= cap:
            raise RateLimitExceeded(
                detail=(
                    f"favorites cap reached: tier={user.tier} allows {cap}. "
                    "Remove an item before adding another."
                ),
                type_slug="favorites_limit_exceeded",
                tier=user.tier,
                cap=cap,
                current=total,
            )

        existing.append(norm)
        rec["tickers"] = existing
        _mark_legacy_storage_schema(rec)
        rec["updated_at"] = datetime.now(timezone.utc).isoformat()
        all_recs[user.owner_email.lower()] = rec
        _atomic_write_all(all_recs)

    logger.info(
        "structural.favorites.bookmark_added",
        count=total + 1,
    )

    return JSONResponse(
        status_code=201,
        content={"ok": True, "added": True, "ticker": norm},
    )


@router.delete(
    "/favorites/{ticker}",
    status_code=204,
    response_class=Response,
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
    norm = _validate_ticker(ticker)

    with _favorite_write_transaction(request, api_key) as user:
        all_recs = _load_all()
        rec = _get_user_record(user.owner_email, all_recs)
        existing: list[object] = list(rec.get("tickers") or [])
        next_tickers = [
            raw for raw in existing if _canonical_stored_ticker(raw) != norm
        ]
        removed = len(next_tickers) != len(existing)
        if removed:
            rec["tickers"] = next_tickers
            _mark_legacy_storage_schema(rec)
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            all_recs[user.owner_email.lower()] = rec
            _atomic_write_all(all_recs)

    logger.info(
        "structural.favorites.bookmark_remove_completed",
        count=len(_canonical_tickers(next_tickers)) + len(_stored_bookmarks(rec)),
    )

    return Response(status_code=204)
