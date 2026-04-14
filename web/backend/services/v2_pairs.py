"""
v2_pairs: shared loader for the V2 cross-domain pair reverse index.

Used by both /api/search (Phase 2) and /api/phenomenon (Phase 3) to enrich
responses with "V2 模型识别的跨域对" — the LLM-rated cross-domain pairs the
v2 pipeline pre-computed.

Source data: web/data/v2_pairs_index.json
Built by:    scripts/build_v2_pairs_index.py
"""
import json
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("structural.v2pairs")

_INDEX_PATH = Path(__file__).parent.parent.parent / "data" / "v2_pairs_index.json"

_by_id: dict = {}
_stats: dict = {}
_loaded = False


def _ensure_loaded():
    global _by_id, _stats, _loaded
    if _loaded:
        return
    if not _INDEX_PATH.exists():
        logger.warning("v2_pairs_index.json not found at %s", _INDEX_PATH)
        _loaded = True
        return
    try:
        with open(_INDEX_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _by_id = data.get("by_id", {})
        _stats = data.get("stats", {})
        logger.info(
            "v2_pairs loaded: %d phenomena indexed, %d total pairs",
            len(_by_id),
            _stats.get("indexed_pairs", 0),
        )
    except Exception as e:
        logger.exception("Failed to load v2_pairs_index: %s", e)
    _loaded = True


def get_pairs_for(phenomenon_id: str, limit: Optional[int] = None) -> List[dict]:
    """
    Return the v2 cross-domain neighborhood for a phenomenon, sorted by
    similarity desc. Each entry is a dict:
    {
        "other_id":     str,
        "other_name":   str,
        "other_domain": str,
        "self_role":    "a" | "b",
        "score":        int (4 or 5),
        "similarity":   float (0-1),
        "reason":       str,
        "value_type":   str,
        "potential":    str,
    }
    Returns [] if no pairs (most phenomena don't have v2-rated cross-domain neighbors).
    """
    _ensure_loaded()
    if not phenomenon_id:
        return []
    pairs = _by_id.get(phenomenon_id, [])
    if limit is not None:
        return pairs[:limit]
    return pairs


def has_pairs(phenomenon_id: str) -> bool:
    _ensure_loaded()
    return phenomenon_id in _by_id and len(_by_id[phenomenon_id]) > 0


def stats() -> dict:
    _ensure_loaded()
    return dict(_stats)
