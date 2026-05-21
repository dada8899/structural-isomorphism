"""verified_isomorphisms — the "result-verified" isomorphism library.

B Data Flywheel (Session ***REMOVED***18).

A *verified isomorphism* is a persisted analyze report that at least one
real user came back and marked `outcome='worked'` in report_followup. It
is stronger evidence than the LLM-rated v2_pairs (services/v2_pairs.py):
v2_pairs is "a model thinks these two phenomena share structure";
a verified isomorphism is "a person borrowed the structure and it worked".

We deliberately keep the two separate — different provenance, different
trust level. This module only shapes the followup-derived data; the raw
JOIN lives in ReportStore.verified_isomorphisms().
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _short(text: str, limit: int = 120) -> str:
    """Trim a query/problem string for list display."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def shape_verified(report_row: dict) -> dict:
    """Project a ReportStore.verified_isomorphisms() row to the API shape.

    `report_row` carries: id, query, b_id, lang, payload (decoded dict),
    created_at, verifier_count, last_verified_at.

    From the payload we pull the source phenomenon / shared structure so
    the UI can render "你的问题 → 借自哪个现象" without a second lookup.
    Older reports may lack `_credibility` or `shared_structure` → we
    degrade gracefully to empty strings.
    """
    payload: dict[str, Any] = report_row.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    credibility = payload.get("_credibility") or {}
    if not isinstance(credibility, dict):
        credibility = {}

    shared = payload.get("shared_structure") or {}
    if not isinstance(shared, dict):
        shared = {}

    source_domain = (
        credibility.get("source_domain")
        or shared.get("source_phenomenon")
        or shared.get("name")
        or ""
    )
    structure_name = shared.get("name") or ""

    return {
        "report_id": report_row.get("id", ""),
        "problem": _short(report_row.get("query", "")),
        "b_id": report_row.get("b_id", ""),
        "lang": report_row.get("lang", ""),
        "source_phenomenon": str(source_domain),
        "structure_name": str(structure_name),
        "verifier_count": int(report_row.get("verifier_count", 0) or 0),
        "last_verified_at": report_row.get("last_verified_at", "") or "",
        "created_at": report_row.get("created_at", "") or "",
    }


def list_verified(store, *, limit: int = 50) -> list[dict]:
    """Return the verified-isomorphism library, shaped for the API.

    `store` is a ReportStore. Empty / no-followup DB → []. Never raises:
    a malformed payload on one row is logged and that row degrades, it
    does not sink the whole list.
    """
    try:
        rows = store.verified_isomorphisms(limit=limit)
    except Exception:  ***REMOVED*** pragma: no cover - defensive
        logger.exception("verified_isomorphisms query failed")
        return []
    out: list[dict] = []
    for row in rows:
        try:
            out.append(shape_verified(row))
        except Exception:  ***REMOVED*** pragma: no cover - defensive
            logger.warning(
                "skipping malformed verified row %s", row.get("id")
            )
    return out
