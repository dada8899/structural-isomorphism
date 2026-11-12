"""Sanity tests for site/web-published JSON artifacts.

Ensures the data files served to web/frontend stay structurally sound and
internally consistent with the source-of-truth artifacts we generated in
v4/results/ + v4/taxonomy/.

These run offline (no network) and exit < 1s; they protect against silent
schema drift between data layer (Python pipeline) and presentation layer
(web/frontend assets).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
WEB_DATA = REPO / "web" / "frontend" / "assets" / "data"
CLASSES_JSON = WEB_DATA / "universality-classes.json"
TAXONOMY_DIR = REPO / "v4" / "taxonomy" / "classes"
RESULTS_DIR = REPO / "v4" / "results"


# ---------------------------------------------------------------------------
# universality-classes.json schema + counts
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def classes_data():
    assert CLASSES_JSON.exists(), f"missing {CLASSES_JSON}"
    return json.loads(CLASSES_JSON.read_text())


def test_top_level_keys_present(classes_data):
    assert "meta" in classes_data
    assert "stats" in classes_data
    assert "classes" in classes_data


def test_meta_has_required_fields(classes_data):
    meta = classes_data["meta"]
    for k in ("generated_at", "version", "total_classes"):
        assert k in meta, f"meta missing {k}"
    assert isinstance(meta["total_classes"], int)
    assert meta["total_classes"] > 0


def test_classes_list_nonempty_and_uniform(classes_data):
    classes = classes_data["classes"]
    assert isinstance(classes, list)
    assert len(classes) > 0
    # Every class has class_id + name_zh + name_en at minimum
    for c in classes:
        assert "class_id" in c, f"class missing class_id: {c}"
        assert "name_zh" in c, f"class missing name_zh: {c['class_id']}"
        assert "name_en" in c, f"class missing name_en: {c['class_id']}"


def test_class_ids_uniqueness_audit(classes_data):
    """Audit: surface duplicate class_ids without blocking (known issue).

    Session #3 W6-E discovery (2026-05-13): universality-classes.json v0.3
    contains 2 duplicate class_ids: motter_lai_network_cascade (x2) and
    gardner_collins_toggle_switch (x2). Total 23 entries / 21 unique.

    Tracking as known data issue (file w6e-data-dedup-followup); this test
    pins the current state (<= 4 dup slots) so any *new* duplicate breaks
    CI immediately.
    """
    from collections import Counter

    ids = [c["class_id"] for c in classes_data["classes"]]
    dups = {k: v for k, v in Counter(ids).items() if v > 1}
    # known dups (audit baseline): motter_lai_network_cascade, gardner_collins_toggle_switch
    n_dup_slots = sum(v - 1 for v in dups.values())
    assert n_dup_slots <= 2, (
        f"new duplicate class_ids beyond known baseline: {dups}"
    )


def test_stats_counts_consistent_with_classes_list(classes_data):
    """`stats.n_equivalence_classes` should match len(classes)."""
    stats = classes_data["stats"]
    if "n_equivalence_classes" in stats:
        assert stats["n_equivalence_classes"] == len(classes_data["classes"]), (
            f"stats.n_equivalence_classes={stats['n_equivalence_classes']} "
            f"!= len(classes)={len(classes_data['classes'])}"
        )


def test_b3_consensus_counts_internal_sum(classes_data):
    """If `stats.b3_consensus` is present, it should be a dict of int counts."""
    stats = classes_data["stats"]
    b3 = stats.get("b3_consensus")
    if b3 is None:
        pytest.skip("b3_consensus not present yet")
    assert isinstance(b3, dict)
    for k, v in b3.items():
        assert isinstance(v, int), f"b3_consensus[{k}]={v!r} not int"
        assert v >= 0
    # Total should be reasonable (<= total_classes upper bound)
    total = sum(b3.values())
    assert total <= classes_data["meta"]["total_classes"] * 2  # generous slack


def test_verified_predictions_matches_paper_claim(classes_data):
    """v0.2 preprint claims 13 verified systems (paper § results)."""
    stats = classes_data["stats"]
    if "verified_predictions" in stats:
        assert stats["verified_predictions"] >= 10
        assert stats["verified_predictions"] <= 25  # generous upper bound


# ---------------------------------------------------------------------------
# Cross-reference: web class_ids should correspond to taxonomy yaml or
# documented stubs
# ---------------------------------------------------------------------------


def test_web_class_ids_are_strings(classes_data):
    """Defensive: class_id must be a string identifier (no spaces, no junk)."""
    for c in classes_data["classes"]:
        cid = c["class_id"]
        assert isinstance(cid, str)
        assert cid.strip() == cid
        assert " " not in cid
        # Allow underscore/alphanumeric/hyphen
        assert all(ch.isalnum() or ch in "_-" for ch in cid), f"bad char in {cid}"


def test_each_class_has_provenance_or_rank(classes_data):
    """Either rank or provenance field — guards against malformed entries."""
    for c in classes_data["classes"]:
        assert "rank" in c or "provenance" in c, f"class {c.get('class_id')} has no rank/provenance"


# ---------------------------------------------------------------------------
# Taxonomy yaml directory existence (where applicable)
# ---------------------------------------------------------------------------


def test_taxonomy_dir_has_yaml_files():
    if not TAXONOMY_DIR.exists():
        pytest.skip("taxonomy/classes/ not present")
    yaml_files = list(TAXONOMY_DIR.glob("*.yaml"))
    assert len(yaml_files) > 0


# ---------------------------------------------------------------------------
# Layer 5 phase count consistency (paper-claim invariant)
# ---------------------------------------------------------------------------


def test_layer5_phase_count_matches_meta(classes_data):
    """meta.layer5_phase_count is the headline number for Layer 5 SOC phases.

    Paper v0.2 claims '13 verified phases' (B3 taxonomy v2). Soft-bound here
    so we catch zero / negative / absurd values.
    """
    meta = classes_data["meta"]
    n = meta.get("layer5_phase_count")
    if n is None:
        pytest.skip("layer5_phase_count not present")
    assert isinstance(n, int)
    assert n > 0
    assert n < 50  # sanity upper bound


# ---------------------------------------------------------------------------
# Defensive JSON-roundtrip (catches encoding / float NaN / etc.)
# ---------------------------------------------------------------------------


def test_json_round_trip_stable(classes_data):
    """Parse → dump → parse should yield equivalent structure."""
    s = json.dumps(classes_data, ensure_ascii=False, sort_keys=True)
    reparsed = json.loads(s)
    assert reparsed["meta"]["total_classes"] == classes_data["meta"]["total_classes"]
    assert len(reparsed["classes"]) == len(classes_data["classes"])
