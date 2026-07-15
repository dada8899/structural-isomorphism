"""Keyed, domain-separated identifiers for privacy-sensitive state.

Production identifiers must not be offline-testable hashes of emails or IP
addresses.  Every caller supplies a purpose string, which is included in the
key derivation so a value cannot be correlated across independent stores.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import re


_ENV_NAME = "STRUCTURAL_PRIVACY_HMAC_KEY"
_CANONICAL_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
_PURPOSE_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_DEV_FALLBACK = hashlib.sha256(
    b"structural-local-only-privacy-identifiers-v2"
).digest()


def _is_production() -> bool:
    return os.getenv("STRUCTURAL_ENV", "dev").strip().lower() == "prod"


def _validated_root_key() -> bytes:
    raw = os.getenv(_ENV_NAME, "")
    if not raw:
        if _is_production():
            raise RuntimeError(f"{_ENV_NAME} is required in production")
        return _DEV_FALLBACK

    if not _CANONICAL_KEY_RE.fullmatch(raw) or len(set(raw)) < 12:
        raise RuntimeError(
            f"{_ENV_NAME} must be unquoted lowercase 64-hex with 12+ distinct characters"
        )
    return raw.encode("ascii")


def validate_privacy_hmac_config() -> None:
    """Validate the root without returning or logging secret material."""
    _validated_root_key()


def normalize_identifier(kind: str, value: str) -> str:
    raw = str(value or "").strip()
    if kind == "email":
        return raw.lower()
    if kind == "ip":
        try:
            return ipaddress.ip_address(raw).compressed
        except ValueError:
            return "unknown"
    if kind == "opaque":
        return raw
    raise ValueError("unsupported privacy identifier kind")


def opaque_identifier(
    purpose: str,
    value: str,
    *,
    kind: str,
) -> str:
    """Return ``<purpose>:v2:<hmac>`` for a normalized identifier."""
    if not _PURPOSE_RE.fullmatch(purpose):
        raise ValueError("privacy identifier purpose is outside the allowlist")
    normalized = normalize_identifier(kind, value)
    root = _validated_root_key()
    derived = hmac.new(
        root,
        b"structural.privacy.identifier-key.v2\0" + purpose.encode("ascii"),
        hashlib.sha256,
    ).digest()
    digest = hmac.new(
        derived,
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{purpose}:v2:{digest}"
