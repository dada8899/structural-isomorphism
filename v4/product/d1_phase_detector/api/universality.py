"""Universality class taxonomy loader + endpoint helpers.

Session #10 W10-E — exposes the YAML taxonomy under `dataset/v1/taxonomy/`
as three REST endpoints (registered by main.py):

    GET /api/universality/classes
    GET /api/universality/classes/{class_id}
    GET /api/universality/companies/{class_id}

Design notes:

* Source of truth = per-class YAML in `dataset/v1/taxonomy/classes/*.yaml`
  + umbrella file `dataset/v1/taxonomy/universality_classes.yaml`.
* Per-class files (~35 today) take precedence; umbrella entries are
  merged in for any class without its own file, so we always surface
  every advertised class even if its per-class YAML is missing.
* One per-class file (`soc_threshold_cascade.yaml`) has a known YAML
  indentation bug (line 55). We catch parse errors per file so a single
  malformed YAML can't take down the whole endpoint — that file still
  loads via its umbrella entry, and a CI-visible warning is logged.
* Class detail endpoint joins the YAML metadata with the live company
  list from `d1_companies` (matching on `universality_class` column).
* All taxonomy I/O happens at import time + cached. The file set is tiny
  (~36 files, all <30KB) so we just walk it once on startup.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, HTTPException

from .db import get_cursor, placeholder, row_to_dict

logger = logging.getLogger("structural.universality")

router = APIRouter(prefix="/api/universality", tags=["universality"])


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

# This file lives at:
#   <repo>/v4/product/d1_phase_detector/api/universality.py
# Taxonomy lives at:
#   <repo>/dataset/v1/taxonomy/...
# We walk up 4 levels (api -> d1_phase_detector -> product -> v4 -> repo).
def _default_taxonomy_dir() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "dataset"
        / "v1"
        / "taxonomy"
    )


def _taxonomy_dir() -> Path:
    override = os.getenv("STRUCTURAL_TAXONOMY_DIR")
    if override:
        return Path(override)
    return _default_taxonomy_dir()


# ---------------------------------------------------------------------------
# YAML loading helpers
# ---------------------------------------------------------------------------

def _safe_load_yaml(path: Path) -> Optional[Dict[str, Any]]:
    """Load one YAML file, returning None + warning on parse failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
        return None
    except yaml.YAMLError as e:
        logger.warning("taxonomy YAML parse failed for %s: %s", path.name, e)
        return None
    except OSError as e:  # pragma: no cover -- IO errors caught explicitly
        logger.warning("taxonomy YAML read failed for %s: %s", path.name, e)
        return None


def _normalize_class_record(raw: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Project a YAML record onto our public-facing schema.

    Per-class YAML and umbrella YAML use slightly different field names
    (e.g. `class_id` vs `id`, `display_name` vs `name`). We project
    everything onto one shape that the frontend can consume directly.
    """
    class_id = raw.get("class_id") or raw.get("id")
    if not class_id:
        return {}

    # Display names
    display_name = (
        raw.get("display_name")
        or raw.get("name_en")
        or raw.get("name")
        or class_id.replace("_", " ").title()
    )
    display_name_zh = raw.get("display_name_zh") or raw.get("name")

    # One-line definition for cards
    definition = (
        raw.get("hub_phenomenon")
        or raw.get("definition")
        or ""
    )
    if isinstance(definition, str):
        definition = definition.strip()

    # Exponent band — pulled from key_invariants in per-class file, or
    # invariants in umbrella file. We surface as a list of strings; the FE
    # picks the first or shows all.
    invariants_raw = raw.get("key_invariants") or raw.get("invariants") or []
    if isinstance(invariants_raw, list):
        invariants = [str(x) for x in invariants_raw if x]
    else:
        invariants = [str(invariants_raw)]

    # Empirical / evidence systems
    positive_examples = raw.get("positive_examples") or []
    if isinstance(positive_examples, list):
        evidence_systems = []
        for ex in positive_examples:
            if isinstance(ex, dict):
                phen = ex.get("phenomenon")
                if phen:
                    evidence_systems.append(
                        {
                            "phenomenon": str(phen),
                            "evidence": str(ex.get("evidence", "")),
                            "verified_at": str(ex.get("verified_at", "")),
                            "paper": ex.get("paper"),
                        }
                    )
    else:
        evidence_systems = []

    # Known members (from umbrella) — merged into evidence_systems if no
    # positive_examples present, so the card always has something to show.
    known_members = raw.get("known_members") or []
    if not evidence_systems and isinstance(known_members, list):
        evidence_systems = [
            {
                "phenomenon": str(m),
                "evidence": "",
                "verified_at": "",
                "paper": None,
            }
            for m in known_members
        ]

    # Negative examples + edge cases preserved verbatim in detail view.
    negative_examples = raw.get("negative_examples") or []
    if not isinstance(negative_examples, list):
        negative_examples = []

    edge_cases = raw.get("edge_cases") or []
    if not isinstance(edge_cases, list):
        edge_cases = []

    # Shared equation / master equation
    equation = raw.get("shared_equation") or raw.get("master_equation") or ""
    if isinstance(equation, str):
        equation = equation.strip()

    # References / prototypes
    references = raw.get("references") or []
    if not isinstance(references, list):
        references = [str(references)]
    else:
        references = [str(r) for r in references if r]

    prototypes = raw.get("prototypes") or []
    if not isinstance(prototypes, list):
        prototypes = [str(prototypes)]
    else:
        prototypes = [str(p) for p in prototypes if p]

    # Status (well-established / emerging / speculative)
    status = str(raw.get("status", "unknown"))

    return {
        "class_id": class_id,
        "display_name": display_name,
        "display_name_zh": display_name_zh,
        "definition": definition,
        "status": status,
        "key_invariants": invariants,
        "shared_equation": equation,
        "evidence_systems": evidence_systems,
        "negative_examples": negative_examples,
        "edge_cases": edge_cases,
        "references": references,
        "prototypes": prototypes,
        "source": source,
    }


@lru_cache(maxsize=1)
def _load_all_classes() -> Dict[str, Dict[str, Any]]:
    """Load every universality class once and cache the result.

    Strategy:
      1. Walk per-class YAML files in taxonomy/classes/ — these are the
         canonical per-class records.
      2. Load umbrella file (universality_classes.yaml) and merge in any
         class not already covered by per-class files. This ensures we
         always advertise every advertised class.
    """
    out: Dict[str, Dict[str, Any]] = {}
    base = _taxonomy_dir()
    classes_dir = base / "classes"

    if classes_dir.exists():
        for yaml_file in sorted(classes_dir.glob("*.yaml")):
            raw = _safe_load_yaml(yaml_file)
            if not raw:
                continue
            norm = _normalize_class_record(raw, source=f"classes/{yaml_file.name}")
            if not norm:
                continue
            out[norm["class_id"]] = norm
    else:
        logger.warning("taxonomy classes dir missing: %s", classes_dir)

    umbrella_file = base / "universality_classes.yaml"
    if umbrella_file.exists():
        raw = _safe_load_yaml(umbrella_file)
        if raw and isinstance(raw, dict):
            for entry in raw.get("classes", []) or []:
                if not isinstance(entry, dict):
                    continue
                norm = _normalize_class_record(entry, source="universality_classes.yaml")
                if not norm:
                    continue
                # Per-class file takes precedence; umbrella fills gaps.
                if norm["class_id"] not in out:
                    out[norm["class_id"]] = norm

    if not out:
        logger.warning("no universality classes loaded from %s", base)

    return out


def _summary_card(cls: Dict[str, Any]) -> Dict[str, Any]:
    """Strip a full class record down to the card-sized payload."""
    return {
        "class_id": cls["class_id"],
        "display_name": cls["display_name"],
        "display_name_zh": cls.get("display_name_zh"),
        "definition": cls["definition"],
        "status": cls["status"],
        "exponent_band": cls["key_invariants"][:3],  # short list for card
        "evidence_count": len(cls.get("evidence_systems") or []),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/classes")
def list_classes() -> Dict[str, Any]:
    """List every known universality class as a summary card.

    Response:
        {
          "count": <int>,
          "classes": [ { class_id, display_name, definition, ... }, ... ]
        }
    """
    classes = _load_all_classes()
    cards = [_summary_card(c) for c in classes.values()]
    # Sort: well-established first, then alphabetical
    status_order = {"well-established": 0, "emerging": 1, "speculative": 2, "unknown": 3}
    cards.sort(key=lambda c: (status_order.get(c["status"], 9), c["class_id"]))
    return {"count": len(cards), "classes": cards}


@router.get("/classes/{class_id}")
def get_class_detail(class_id: str) -> Dict[str, Any]:
    """Return the full taxonomy record for one class."""
    classes = _load_all_classes()
    cls = classes.get(class_id)
    if cls is None:
        raise HTTPException(status_code=404, detail=f"class_id={class_id} not found")
    return cls


@router.get("/companies/{class_id}")
def companies_for_class(class_id: str) -> Dict[str, Any]:
    """List tickers currently tagged with this universality class.

    Joins YAML taxonomy (for class existence check) with the live
    `d1_companies` table on `universality_class`. Empty list is a valid
    response (taxonomy class exists but no companies yet match).
    """
    classes = _load_all_classes()
    if class_id not in classes:
        raise HTTPException(status_code=404, detail=f"class_id={class_id} not found")

    companies: List[Dict[str, Any]] = []
    try:
        with get_cursor() as (cur, driver):
            ph = placeholder(driver)
            cur.execute(
                f"SELECT ticker, name, sector, industry, dynamics_family, "
                f"critical_point_state, extraction_confidence, tldr "
                f"FROM d1_companies WHERE universality_class = {ph} "
                f"ORDER BY extraction_confidence DESC, ticker ASC LIMIT 100",
                (class_id,),
            )
            rows = cur.fetchall()
            for r in rows:
                companies.append(row_to_dict(r, driver))
    except Exception as e:  # pragma: no cover -- DB access guarded
        logger.warning("companies_for_class DB query failed: %s", e)

    return {
        "class_id": class_id,
        "display_name": classes[class_id]["display_name"],
        "count": len(companies),
        "companies": companies,
    }
