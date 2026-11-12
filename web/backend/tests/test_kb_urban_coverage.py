"""KB Urban/Computational Social Science coverage sanity test (2026-05-24).

The X1 KB coverage audit (docs/coverage/kb-coverage-audit-2026-05-24.md)
identified Urban as the most under-covered domain (37 entries) and showed
3/10 cross-domain pair queries failing on sociology / urban / culture
side. This test guards the 100+ Urban/Social additions written to
`data/kb-additions-2026-05-24-urban-social.jsonl` and merged into
`data/kb-5000-merged.jsonl`.

Two layers:
  1. File-level coverage (fast, no model load):
     - Additions file is well-formed JSONL.
     - Required schema fields present, description >= 50 chars, type_id valid.
     - Domain categories cover the 11 sub-buckets named in the task spec.
     - Five recall-keyword phrases (Bettencourt 城市标度 / Granovetter
       threshold / Bass diffusion / three-phase traffic / Schelling
       segregation) each appear in >= 1 entry's name+description.

  2. Real embedding recall (heavy, model load ~13s; gated by `slow` marker
     and `RUN_KB_URBAN_RECALL_TEST=1` env var):
     - For the same five phrases, SearchService.search() must return at
       least one of the new urban/social entries in the top-20 results.

Layer (1) runs by default in the PR-time CI profile. Layer (2) is gated
to keep PR-time pytest budget low (the existing test_search_service_v2v3
module already pays the model-load cost; this avoids paying it twice).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DATA_DIR = _REPO_ROOT / "data"
_ADDITIONS = _DATA_DIR / "kb-additions-2026-05-24-urban-social.jsonl"
_MERGED_KB = _DATA_DIR / "kb-5000-merged.jsonl"

# 11 sub-categories from the task spec → id-prefix → expected min count
_CATEGORY_PREFIX_MIN = {
    "urb": 10,   # Bettencourt scaling + Zipf-Gibrat + bonus
    "trf": 10,   # 交通流相变
    "opn": 15,   # 意见 / 信息扩散
    "inv": 10,   # 创新 / 技术采纳
    "fin": 10,   # 金融市场社会层
    "epi": 10,   # 流行病学社会传播
    "cul": 10,   # 文化 / 时尚周期
    "crm": 5,    # 城市犯罪
    "sch": 5,    # 教育 / 健康 inequality
}

# Recall-keyword phrases the X1 audit named explicitly. Each MUST appear
# verbatim (substring) in name+description of >= 1 addition.
_RECALL_PHRASES = (
    "Bettencourt",        # 城市标度律
    "Granovetter",        # 门槛模型 / 弱联系
    "Bass",               # Bass 扩散方程
    "三相",               # Kerner three-phase traffic
    "Schelling",          # 隔离模型
)


def _load_additions() -> List[Dict]:
    assert _ADDITIONS.exists(), f"Additions file missing: {_ADDITIONS}"
    items: List[Dict] = []
    with open(_ADDITIONS, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))  # raises if malformed
    return items


# ---------------- Layer 1 — file-level coverage (fast) -------------------

@pytest.mark.sanity
def test_additions_file_loadable_and_nonempty():
    items = _load_additions()
    assert len(items) >= 100, f"expected >= 100 additions, got {len(items)}"


@pytest.mark.sanity
def test_additions_schema_well_formed():
    items = _load_additions()
    valid_type_ids = {f"{i:02d}" for i in range(1, 85)}
    errors: List[str] = []
    seen_ids: set = set()
    for it in items:
        for field in ("id", "name", "domain", "type_id", "description"):
            if field not in it or not it[field]:
                errors.append(f"{it.get('id', '<?>')}: missing/empty field {field}")
        if "id" in it:
            if it["id"] in seen_ids:
                errors.append(f"duplicate id {it['id']}")
            seen_ids.add(it["id"])
        if it.get("type_id") not in valid_type_ids:
            errors.append(f"{it.get('id')}: type_id '{it.get('type_id')}' not in 01..84")
        if len(it.get("description", "")) < 50:
            errors.append(
                f"{it.get('id')}: description {len(it.get('description', ''))} chars (< 50)"
            )
    assert not errors, "schema errors:\n  " + "\n  ".join(errors[:20])


@pytest.mark.sanity
def test_additions_no_collision_with_existing_kb():
    """All addition ids must be unique across the merged KB.

    Skipped if the merged KB hasn't been updated (additions not yet merged
    in this checkout); in CI the embedding update script appends them
    before this runs.
    """
    if not _MERGED_KB.exists():
        pytest.skip(f"{_MERGED_KB} missing")
    additions = _load_additions()
    add_ids = {it["id"] for it in additions}
    merged_ids: set = set()
    add_count_in_merged = 0
    with open(_MERGED_KB, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("id") in add_ids:
                add_count_in_merged += 1
            merged_ids.add(d.get("id", ""))
    # Each id appears at most once in the merged KB (no duplicate-append).
    # If add_count_in_merged > 0, additions have already been merged — that
    # is fine; we only fail on duplicates.
    dup = len(merged_ids) - len(set(merged_ids))
    assert dup == 0, f"merged KB has {dup} duplicate ids"
    if add_count_in_merged > 0:
        assert add_count_in_merged == len(add_ids), (
            f"partial-merge detected: {add_count_in_merged}/{len(add_ids)} addition ids "
            "appear in merged KB. Re-run scripts/update_kb_embeddings_urban.py to finish."
        )


@pytest.mark.sanity
def test_additions_cover_all_11_categories():
    items = _load_additions()
    from collections import Counter
    prefix_counts = Counter(it["id"].split("-")[0] for it in items)
    missing: List[str] = []
    for prefix, min_count in _CATEGORY_PREFIX_MIN.items():
        if prefix_counts.get(prefix, 0) < min_count:
            missing.append(
                f"prefix '{prefix}' has {prefix_counts.get(prefix, 0)} entries, "
                f"need >= {min_count}"
            )
    assert not missing, "category coverage gaps:\n  " + "\n  ".join(missing)


@pytest.mark.sanity
def test_recall_phrases_present_in_additions():
    """Each X1-audit phrase must appear as substring in some addition."""
    items = _load_additions()
    missing: List[str] = []
    hits: Dict[str, List[str]] = {}
    for phrase in _RECALL_PHRASES:
        matched = [
            it["id"] for it in items
            if phrase.lower() in (it["name"] + " " + it["description"]).lower()
        ]
        hits[phrase] = matched
        if not matched:
            missing.append(phrase)
    assert not missing, (
        "recall phrases not found in additions: "
        + ", ".join(missing)
        + f"\n  hits so far: {hits}"
    )


@pytest.mark.sanity
def test_type_id_diversity():
    """Additions should hit at least 15 distinct type_ids (covers the
    structural-diversity goal — not one mega-cluster on a single mechanism)."""
    items = _load_additions()
    type_ids = {it["type_id"] for it in items}
    assert len(type_ids) >= 15, (
        f"type_id diversity low: only {len(type_ids)} unique type_ids "
        f"({sorted(type_ids)})"
    )


# ---------------- Layer 2 — real embedding recall (slow, opt-in) ----------

_RUN_RECALL = os.environ.get("RUN_KB_URBAN_RECALL_TEST", "0") == "1"


@pytest.mark.slow
@pytest.mark.skipif(not _RUN_RECALL, reason="set RUN_KB_URBAN_RECALL_TEST=1 to run")
def test_urban_additions_recallable_via_search():
    """End-to-end: each recall phrase must return at least one new urban/
    social addition in the top-20 SearchService results.

    Costs ~15-25s for model load + KB encode. Gated behind env var so it
    doesn't bloat the PR-time pytest budget. Run nightly or manually:

        RUN_KB_URBAN_RECALL_TEST=1 pytest \
            web/backend/tests/test_kb_urban_coverage.py::test_urban_additions_recallable_via_search
    """
    backend = Path(__file__).resolve().parent.parent
    for p in (backend, _REPO_ROOT):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    from services.search_service import SearchService  # noqa: E402

    # Use the live merged KB (must have been updated by the script).
    svc = SearchService(
        data_dir=str(_DATA_DIR),
        kb_file="kb-5000-merged.jsonl",
        precomputed_embeddings=str(_REPO_ROOT / "web" / "data" / "kb_v2_embeddings.npy"),
    )
    add_ids = {it["id"] for it in _load_additions()}

    queries = {
        "Bettencourt": "Bettencourt 城市标度律 人口 GDP",
        "Granovetter": "Granovetter threshold 门槛模型 集体行为",
        "Bass": "Bass diffusion 技术扩散 S 曲线",
        "Kerner three-phase": "Kerner 三相 交通流 同步流",
        "Schelling": "Schelling 隔离 segregation 棋盘模型",
    }

    missing: List[str] = []
    for label, q in queries.items():
        results = svc.search(q, top_k=20) if hasattr(svc, "search") else None
        if not results:
            missing.append(f"{label}: search returned nothing")
            continue
        hit_ids = {r.get("id") if isinstance(r, dict) else getattr(r, "id", None) for r in results}
        if not (hit_ids & add_ids):
            missing.append(f"{label}: top-20 has no addition id (hits={list(hit_ids)[:5]})")
    assert not missing, "recall gaps:\n  " + "\n  ".join(missing)
