"""Shared, fail-closed normalization for discovery evidence fields."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from datetime import date
from typing import Any
from urllib.parse import urlsplit


def _clean_text(value: Any, *, limit: int, required: bool = False) -> str:
    if not isinstance(value, str):
        if required:
            raise ValueError("required discovery evidence text is missing")
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    cleaned = "".join(
        char for char in normalized if not unicodedata.category(char).startswith("C")
    ).strip()
    if required and not cleaned:
        raise ValueError("required discovery evidence text is blank")
    return cleaned[:limit]


def normalize_candidate_equations(raw: Mapping[str, Any], *, limit: int = 8) -> list[str]:
    """Return the public Chinese equation list without dropping localized rows."""
    shared = raw.get("shared_equations")
    if shared is not None:
        if not isinstance(shared, list):
            raise ValueError("shared discovery equations must be a list")
        value: Any = shared
    elif isinstance(raw.get("shared_equation"), str):
        value = [raw["shared_equation"]]
    else:
        value = raw.get("equations", [])
        if value is None:
            value = []
        if not isinstance(value, list):
            raise ValueError("discovery equations must be a list")

    equations: list[str] = []
    for entry in value:
        if isinstance(entry, str):
            item = _clean_text(entry, limit=500)
        elif isinstance(entry, Mapping):
            if set(entry) - {"zh", "en"} or "zh" not in entry:
                raise ValueError("localized discovery equation has an invalid shape")
            item = _clean_text(entry.get("zh"), limit=500, required=True)
            if entry.get("en") not in {None, ""}:
                _clean_text(entry.get("en"), limit=500, required=True)
        else:
            raise ValueError("discovery equation must be text or localized text")
        if item:
            equations.append(item)
    return equations[:limit]


def valid_reviewed_literature_source(entry: Any, *, today: date | None = None) -> bool:
    """Validate an auditable source record; independence is a separate claim."""
    if not isinstance(entry, Mapping):
        return False
    source = _clean_text(entry.get("source"), limit=2048)
    license_name = _clean_text(entry.get("license"), limit=120)
    provenance = _clean_text(entry.get("provenance_class"), limit=120)
    review = entry.get("source_review")
    if not source or not license_name or not provenance or not isinstance(review, Mapping):
        return False
    if license_name.lower() == "unknown" or provenance.lower() == "unknown":
        return False
    parsed = urlsplit(source)
    if not (
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    ):
        return False
    reviewer = _clean_text(review.get("reviewer"), limit=200)
    reviewed_at = _clean_text(review.get("reviewed_at"), limit=100)
    if not reviewer or not reviewed_at:
        return False
    try:
        reviewed_on = date.fromisoformat(reviewed_at)
    except ValueError:
        return False
    return reviewed_on <= (today or date.today())


__all__ = ["normalize_candidate_equations", "valid_reviewed_literature_source"]
