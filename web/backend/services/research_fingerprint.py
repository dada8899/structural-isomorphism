"""Validated user-confirmed structure for bounded research retrieval."""
from __future__ import annotations

import math
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
)

from .input_limits import MAX_RESEARCH_QUERY_CHARS, normalize_research_text


FINGERPRINT_HINT_MAX_CHARS = 1600
FINGERPRINT_RERANK_BONUS_MAX = 0.02
_FingerprintItem = StrictStr


class ConfirmedResearchFingerprint(BaseModel):
    """A user-edited structure draft bound to one canonical source query."""

    model_config = ConfigDict(extra="forbid", strict=True)

    source_query: StrictStr = Field(min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS)
    summary: StrictStr = Field(min_length=8, max_length=1000)
    variables: list[_FingerprintItem] = Field(default_factory=list, max_length=12)
    constraints: list[_FingerprintItem] = Field(default_factory=list, max_length=12)
    unknowns: list[_FingerprintItem] = Field(default_factory=list, max_length=12)
    revision: StrictInt = Field(default=1, ge=1, le=1000)

    @field_validator("source_query")
    @classmethod
    def _normalize_source_query(cls, value: str) -> str:
        return normalize_research_text(
            value,
            max_chars=MAX_RESEARCH_QUERY_CHARS,
            field_name="fingerprint.source_query",
        )

    @field_validator("summary")
    @classmethod
    def _normalize_summary(cls, value: str) -> str:
        normalized = normalize_research_text(
            value,
            max_chars=1000,
            field_name="fingerprint.summary",
        )
        if len(normalized) < 8:
            raise ValueError("fingerprint.summary must be at least 8 characters")
        return normalized

    @field_validator("variables", "constraints", "unknowns")
    @classmethod
    def _normalize_items(cls, values: list[str], info) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = normalize_research_text(
                value,
                max_chars=120,
                allow_layout=False,
                field_name=f"fingerprint.{info.field_name}",
            )
            if item in seen:
                raise ValueError(f"fingerprint.{info.field_name} contains duplicates")
            seen.add(item)
            normalized.append(item)
        return normalized


def build_fingerprint_retrieval_hint(fingerprint: ConfirmedResearchFingerprint) -> str:
    """Build a bounded local-only hint without repeating the raw source query."""

    parts = [fingerprint.summary]
    for label, values in (
        ("variables", fingerprint.variables),
        ("constraints", fingerprint.constraints),
    ):
        if values:
            parts.append(f"{label}: " + "; ".join(values))
    return " | ".join(parts)[:FINGERPRINT_HINT_MAX_CHARS]


def _finite_score(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return score if math.isfinite(score) and 0.0 <= score <= 1.0 else 0.0


def bounded_fingerprint_rerank(
    original_cards: list[dict[str, Any]],
    fingerprint_cards: list[dict[str, Any]],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    """Rerank only the raw-query pool with a small fingerprint rank bonus.

    The confirmed fingerprint may reorder close raw-query candidates, but it
    cannot introduce a new candidate, alter the displayed score, or overcome
    more than ``FINGERPRINT_RERANK_BONUS_MAX`` of raw score separation.
    """

    if top_k < 1:
        return []
    allowed_ids = {
        card.get("id")
        for card in original_cards
        if isinstance(card, dict) and isinstance(card.get("id"), str) and card.get("id")
    }
    fp_rank: dict[str, int] = {}
    for card in fingerprint_cards:
        card_id = card.get("id") if isinstance(card, dict) else None
        if card_id in allowed_ids and card_id not in fp_rank:
            fp_rank[card_id] = len(fp_rank)

    ranked: list[tuple[float, int, dict[str, Any]]] = []
    seen: set[str] = set()
    for index, card in enumerate(original_cards):
        if not isinstance(card, dict):
            continue
        card_id = card.get("id")
        if not isinstance(card_id, str) or not card_id or card_id in seen:
            continue
        seen.add(card_id)
        bonus = 0.0
        if card_id in fp_rank:
            bonus = FINGERPRINT_RERANK_BONUS_MAX / (fp_rank[card_id] + 1)
        ranked.append((-(_finite_score(card.get("score")) + bonus), index, card))

    ranked.sort(key=lambda row: (row[0], row[1]))
    return [dict(row[2]) for row in ranked[:top_k]]
