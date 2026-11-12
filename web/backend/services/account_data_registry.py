"""Single registry for authenticated account export and erasure."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
if __package__ == "web.backend.services":
    from ..logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id

logger = get_logger("structural.account_data")


@dataclass(frozen=True)
class AccountAsset:
    name: str
    owner_key: str
    retention: str
    export: Callable[[str], object]
    delete: Callable[[str], object]
    restore: Callable[[str, object, object], None] | None = None
    # Public export and private compensation can have different schemas.
    # Forward-compatible stores use this hook to snapshot opaque raw values
    # without exposing them through the account-export API.
    snapshot: Callable[[str], object] | None = None

    def validate(self) -> None:
        if not self.name or not self.owner_key or not self.retention:
            raise ValueError("account asset metadata must be complete")
        if not callable(self.export) or not callable(self.delete):
            raise ValueError(f"account asset {self.name} must support export and delete")
        if self.snapshot is not None and not callable(self.snapshot):
            raise ValueError(f"account asset {self.name} snapshot must be callable")


class AccountDataRegistry:
    def __init__(self, assets: list[AccountAsset]):
        names = [asset.name for asset in assets]
        if len(names) != len(set(names)):
            raise ValueError("account asset names must be unique")
        for asset in assets:
            asset.validate()
        self.assets = tuple(assets)

    def manifest(self) -> list[dict]:
        return [
            {"name": a.name, "owner_key": a.owner_key, "retention": a.retention}
            for a in self.assets
        ]

    def export_all(self, owner: str) -> dict:
        return {asset.name: asset.export(owner) for asset in self.assets}

    def delete_all(self, owner: str) -> dict:
        """Delete in order; compensate reversible stores if a later step fails."""
        completed: list[tuple[AccountAsset, object, object]] = []
        removed: dict[str, object] = {}
        try:
            for asset in self.assets:
                snapshot = (
                    asset.snapshot(owner)
                    if asset.snapshot is not None
                    else asset.export(owner)
                )
                result = asset.delete(owner)
                removed[asset.name] = result
                completed.append((asset, snapshot, result))
        except Exception:
            for asset, snapshot, result in reversed(completed):
                if asset.restore is not None:
                    try:
                        asset.restore(owner, snapshot, result)
                    except Exception as exc:
                        logger.error(
                            "account_data.rollback_failed",
                            error_type=type(exc).__name__,
                            incident_id=new_incident_id(),
                        )
            raise
        return removed


def deletion_tombstone(owner: str, removed: dict, audit_key: str) -> dict:
    return {
        "event": "account_deleted",
        "owner_hash": _owner_hash(owner, audit_key),
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "removed": removed,
        "retention": "security audit retained for 365 days",
    }


def _owner_hash(owner: str, audit_key: str) -> str:
    """Pseudonymous audit correlation protected from email dictionaries."""
    derived = hmac.new(
        audit_key.encode("utf-8"),
        b"structural.account-deletion-audit.v1",
        hashlib.sha256,
    ).digest()
    return hmac.new(
        derived,
        owner.strip().lower().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:16]
