"""Single registry for authenticated account export and erasure."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger("structural.account_data")


@dataclass(frozen=True)
class AccountAsset:
    name: str
    owner_key: str
    retention: str
    export: Callable[[str], object]
    delete: Callable[[str], object]
    restore: Callable[[str, object, object], None] | None = None

    def validate(self) -> None:
        if not self.name or not self.owner_key or not self.retention:
            raise ValueError("account asset metadata must be complete")
        if not callable(self.export) or not callable(self.delete):
            raise ValueError(f"account asset {self.name} must support export and delete")


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
                snapshot = asset.export(owner)
                result = asset.delete(owner)
                removed[asset.name] = result
                completed.append((asset, snapshot, result))
        except Exception:
            for asset, snapshot, result in reversed(completed):
                if asset.restore is not None:
                    try:
                        asset.restore(owner, snapshot, result)
                    except Exception:
                        logger.exception(
                            "account_data.rollback_failed asset=%s owner_hash=%s",
                            asset.name, _owner_hash(owner),
                        )
            raise
        return removed


def deletion_tombstone(owner: str, removed: dict) -> dict:
    return {
        "event": "account_deleted",
        "owner_hash": _owner_hash(owner),
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "removed": removed,
        "retention": "security audit retained for 365 days",
    }


def _owner_hash(owner: str) -> str:
    return hashlib.sha256(owner.strip().lower().encode("utf-8")).hexdigest()[:16]
