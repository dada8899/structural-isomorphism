"""Strict, dependency-light identity for a discovery-derived report."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any
from urllib.parse import urlencode


SCHEMA_VERSION = "discovery-candidate-v2"
PAIR_ID_VERSION = "discovery-pair-v1"
ORIGIN_CONTENT_VERSION = "discovery-origin-content-v1"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_DISCOVERY_ID = re.compile(r"^discovery-[0-9a-f]{16}$")
_FAMILY_ID = re.compile(r"^(?:anchor|pair)-[0-9a-f]{12}$")
_ORIGIN_CONTENT_ID = re.compile(r"^origin-[0-9a-f]{24}$")


def normalize_candidate_identifier(value: Any) -> str | None:
    """Return a canonical public KB identifier or ``None``.

    Discovery generation, response validation, and persisted-origin reads all
    call this helper so Unicode/control-character policy cannot drift between
    those three boundaries.
    """
    if not isinstance(value, str) or value != value.strip():
        return None
    if (
        unicodedata.normalize("NFKC", value) != value
        or any(unicodedata.category(char).startswith("C") for char in value)
        or not _IDENTIFIER.fullmatch(value)
    ):
        return None
    return value


def normalize_candidate_family_id(value: Any) -> str | None:
    """Return the canonical generated family id or ``None``."""
    if not isinstance(value, str) or value != value.strip():
        return None
    if unicodedata.normalize("NFKC", value) != value:
        return None
    return value if _FAMILY_ID.fullmatch(value) else None


def normalize_discovery_id(value: Any) -> str | None:
    """Return a canonical pair-derived id shape or ``None``."""
    if not isinstance(value, str) or value != value.strip():
        return None
    return value if _DISCOVERY_ID.fullmatch(value) else None


def discovery_id_for_pair(a_id: str, b_id: str) -> str:
    payload = "\x1f".join(
        (PAIR_ID_VERSION, *sorted((a_id, b_id))),
    ).encode("utf-8")
    return f"discovery-{hashlib.sha256(payload).hexdigest()[:16]}"


def analyze_url_for_candidate(
    *, a_id: str, b_id: str, discovery_id: str, contract_version: str,
) -> str:
    """Build the one canonical deep link for a public candidate."""
    return "/analyze?" + urlencode({
        "a_id": a_id,
        "id": b_id,
        "origin_discovery_id": discovery_id,
        "origin_contract_version": contract_version,
    })


def origin_content_id_for(
    *,
    discovery_id: str,
    contract_version: str,
    candidate_family_id: str,
    tier: str,
    a_id: str,
    b_id: str,
) -> str:
    """Bind all mutable-looking snapshot fields to one public content id.

    This is deliberately a non-secret content address, not an authentication
    signature.  Authenticity comes from ``api.analyze`` resolving the current
    server-side catalog before it creates the snapshot.  The content id makes
    partial database/serialization tampering fail closed on later reads.
    Pair order is excluded from identity because discovery ids are explicitly
    directionless; the analyze deep-link boundary separately enforces its
    exact source/target order.
    """
    canonical = json.dumps(
        {
            "candidate_family_id": candidate_family_id,
            "contract_version": contract_version,
            "discovery_id": discovery_id,
            "pair": sorted((a_id, b_id)),
            "tier": tier,
            "version": ORIGIN_CONTENT_VERSION,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return f"origin-{hashlib.sha256(canonical).hexdigest()[:24]}"


def build_origin_candidate(
    *,
    discovery_id: Any,
    contract_version: Any,
    candidate_family_id: Any,
    tier: Any,
    a_id: Any,
    b_id: Any,
) -> dict[str, Any] | None:
    """Create a server-resolved origin snapshot or fail closed."""
    a_normalized = normalize_candidate_identifier(a_id)
    b_normalized = normalize_candidate_identifier(b_id)
    family_normalized = normalize_candidate_family_id(candidate_family_id)
    if (
        not a_normalized
        or not b_normalized
        or a_normalized == b_normalized
        or normalize_discovery_id(discovery_id) is None
        or discovery_id != discovery_id_for_pair(a_normalized, b_normalized)
        or contract_version != SCHEMA_VERSION
        or not family_normalized
        or tier not in {"priority_review", "candidate_pool"}
    ):
        return None
    content_id = origin_content_id_for(
        discovery_id=discovery_id,
        contract_version=SCHEMA_VERSION,
        candidate_family_id=family_normalized,
        tier=tier,
        a_id=a_normalized,
        b_id=b_normalized,
    )
    return {
        "discovery_id": discovery_id,
        "contract_version": SCHEMA_VERSION,
        "candidate_family_id": family_normalized,
        "tier": tier,
        "pair": {"a_id": a_normalized, "b_id": b_normalized},
        "origin_content_id": content_id,
    }


def normalize_origin_candidate(value: Any) -> dict[str, Any] | None:
    """Return the exact public snapshot or fail closed for any drift."""
    if not isinstance(value, dict) or set(value) != {
        "discovery_id",
        "contract_version",
        "candidate_family_id",
        "tier",
        "pair",
        "origin_content_id",
    }:
        return None
    pair = value.get("pair")
    if not isinstance(pair, dict) or set(pair) != {"a_id", "b_id"}:
        return None
    candidate = build_origin_candidate(
        discovery_id=value.get("discovery_id"),
        contract_version=value.get("contract_version"),
        candidate_family_id=value.get("candidate_family_id"),
        tier=value.get("tier"),
        a_id=pair.get("a_id"),
        b_id=pair.get("b_id"),
    )
    if candidate is None:
        return None
    if (
        not isinstance(value.get("origin_content_id"), str)
        or not _ORIGIN_CONTENT_ID.fullmatch(value["origin_content_id"])
        or value["origin_content_id"] != candidate["origin_content_id"]
    ):
        return None
    return candidate


def migrate_legacy_origin_candidate(
    value: Any, *, authoritative_origin: Any,
) -> dict[str, Any] | None:
    """Upgrade the pre-content-id shape only against trusted catalog truth.

    Callers must first build ``authoritative_origin`` from the current public
    server catalog with :func:`build_origin_candidate`.  We intentionally do
    not auto-upgrade old payload bytes on read: without that authority, a
    syntactically valid old ``family`` or ``tier`` value cannot be authenticated.
    This explicit migration keeps correct records recoverable without claiming
    that legacy self-asserted metadata is safe.
    """
    authoritative = normalize_origin_candidate(authoritative_origin)
    if authoritative is None or not isinstance(value, dict):
        return None
    legacy = {key: item for key, item in authoritative.items() if key != "origin_content_id"}
    return authoritative if value == legacy else None


def origin_candidate_from_payload(payload: Any) -> dict[str, Any] | None:
    """Read only the reserved origin snapshot; never expose the payload."""
    if not isinstance(payload, dict):
        return None
    return normalize_origin_candidate(payload.get("_origin_candidate"))
