"""F1 embedding-bridge sanity tests.

Goal:
 - Verify EmbeddingBridge constructs without the real V1/V2 model
   (TF-IDF fallback mode).
 - Verify suggest_neighbors returns top-k Neighbor objects ranked by
   descending similarity.
 - Verify expand_candidate_class on a real 24-class YAML returns
   non-empty, plausible suggestions.
 - Verify exclude_ids works.
 - Verify the bridge auto-loads V1 cache as an alternative version.

These tests are marked @pytest.mark.sanity (10s total budget per pytest.ini).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from embedding_bridge import (  # type: ignore  # noqa: E402
    EmbeddingBridge,
    Neighbor,
)


REPO = Path(__file__).resolve().parents[3]
CLASSES_DIR = REPO / "v4" / "taxonomy" / "classes"


@pytest.fixture(scope="module")
def bridge_v2() -> EmbeddingBridge:
    """V2 bridge in TF-IDF fallback mode (no real model on disk)."""
    return EmbeddingBridge(version="v2", fallback_mode="tfidf")


@pytest.fixture(scope="module")
def bridge_v1() -> EmbeddingBridge:
    """V1 bridge in TF-IDF fallback mode."""
    return EmbeddingBridge(version="v1", fallback_mode="tfidf")


# ----------------------------------------------------------------------
# construction + basic invariants
# ----------------------------------------------------------------------
@pytest.mark.sanity
def test_construction_loads_cache(bridge_v2: EmbeddingBridge) -> None:
    """Bridge must load V2 cache (4443 phenomena, 768-dim)."""
    assert bridge_v2.num_phenomena > 4000
    assert bridge_v2.mode in {"real_model", "tfidf"}
    # In CI / local dev the model is not present, so we expect tfidf.
    assert bridge_v2.mode == "tfidf"


@pytest.mark.sanity
def test_v1_cache_loads(bridge_v1: EmbeddingBridge) -> None:
    """V1 cache is 4475 phenomena, also 768-dim."""
    assert bridge_v1.num_phenomena == 4475


@pytest.mark.sanity
def test_invalid_version_raises() -> None:
    with pytest.raises(ValueError, match="version must be one of"):
        EmbeddingBridge(version="v9", fallback_mode="tfidf")


# ----------------------------------------------------------------------
# suggest_neighbors
# ----------------------------------------------------------------------
@pytest.mark.sanity
def test_suggest_neighbors_basic(bridge_v2: EmbeddingBridge) -> None:
    """Top-5 neighbours of a percolation-like description should be
    non-empty, well-formed, and sorted descending."""
    query = {
        "description": "网络节点占据率超过临界值时，最大连通子集贯穿整个系统，"
        "发生连续相变；类似 Granovetter 阈值模型。",
    }
    out = bridge_v2.suggest_neighbors(query, k=5)
    assert isinstance(out, list)
    assert len(out) == 5
    assert all(isinstance(n, Neighbor) for n in out)
    # similarities must be descending
    sims = [n.similarity for n in out]
    assert sims == sorted(sims, reverse=True)
    # each Neighbor must have an id and a description
    for n in out:
        assert n.id
        assert n.description
        assert -1.0 <= n.similarity <= 1.0 + 1e-6  # cosine bounds


@pytest.mark.sanity
def test_suggest_neighbors_string_input(bridge_v2: EmbeddingBridge) -> None:
    """Raw string input works too (not just dict)."""
    out = bridge_v2.suggest_neighbors("珊瑚白化的滞后恢复", k=3)
    assert len(out) == 3


@pytest.mark.sanity
def test_suggest_neighbors_empty_input(bridge_v2: EmbeddingBridge) -> None:
    """Empty description returns empty list, no exception."""
    assert bridge_v2.suggest_neighbors({"description": ""}, k=5) == []
    assert bridge_v2.suggest_neighbors("", k=5) == []


@pytest.mark.sanity
def test_exclude_ids_filters_out(bridge_v2: EmbeddingBridge) -> None:
    """Items whose id is in exclude_ids must not appear in results."""
    query = {"description": "渗流 percolation 相变 临界 节点占据"}
    baseline = bridge_v2.suggest_neighbors(query, k=5)
    assert baseline
    excluded = {baseline[0].id}
    out = bridge_v2.suggest_neighbors(query, k=5, exclude_ids=excluded)
    out_ids = {n.id for n in out}
    assert excluded.isdisjoint(out_ids)


@pytest.mark.sanity
def test_self_id_auto_excluded(bridge_v2: EmbeddingBridge) -> None:
    """If query dict has its own id, that id must be auto-excluded."""
    # Pick any real KB id
    sample_id = "5k-01-001"
    bridge_kb = bridge_v2._kb_by_id[sample_id]  # noqa: SLF001 (test peek)
    query = {"id": sample_id, "description": bridge_kb["description"]}
    out = bridge_v2.suggest_neighbors(query, k=5)
    out_ids = {n.id for n in out}
    assert sample_id not in out_ids


# ----------------------------------------------------------------------
# expand_candidate_class
# ----------------------------------------------------------------------
@pytest.mark.sanity
def test_expand_percolation_class(bridge_v2: EmbeddingBridge) -> None:
    """The percolation_connectivity class has 5 positive_examples.
    Expansion must return non-empty suggestions."""
    yaml_path = CLASSES_DIR / "percolation_connectivity.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        class_yaml = yaml.safe_load(f)
    out = bridge_v2.expand_candidate_class(class_yaml, k=10)
    assert len(out) > 0
    assert len(out) <= 10
    # All returned Neighbors must have ids
    assert all(n.id for n in out)


@pytest.mark.sanity
def test_expand_no_positives_returns_empty(bridge_v2: EmbeddingBridge) -> None:
    """If a class has no positive_examples, expansion returns empty (not error)."""
    out = bridge_v2.expand_candidate_class({"class_id": "fake", "positive_examples": []}, k=5)
    assert out == []


@pytest.mark.sanity
def test_expand_handles_missing_positive_examples_key(
    bridge_v2: EmbeddingBridge,
) -> None:
    """Class YAML without the positive_examples key entirely -> empty, no error."""
    out = bridge_v2.expand_candidate_class({"class_id": "fake"}, k=5)
    assert out == []


# ----------------------------------------------------------------------
# Neighbor.to_dict serialisation
# ----------------------------------------------------------------------
@pytest.mark.sanity
def test_neighbor_to_dict(bridge_v2: EmbeddingBridge) -> None:
    out = bridge_v2.suggest_neighbors("percolation transition", k=1)
    assert len(out) == 1
    d = out[0].to_dict()
    assert set(d.keys()) == {"id", "name", "domain", "description", "similarity"}
    assert isinstance(d["similarity"], float)


# ----------------------------------------------------------------------
# walkthrough on a second real class: helps catch tight-coupling bugs
# ----------------------------------------------------------------------
@pytest.mark.sanity
def test_expand_hysteresis_class(bridge_v2: EmbeddingBridge) -> None:
    yaml_path = CLASSES_DIR / "hysteresis_first_order_transition.yaml"
    if not yaml_path.exists():
        pytest.skip("hysteresis_first_order_transition.yaml not present")
    with open(yaml_path, encoding="utf-8") as f:
        class_yaml = yaml.safe_load(f)
    out = bridge_v2.expand_candidate_class(class_yaml, k=8)
    # We only assert non-error and well-formedness; quality of suggestions
    # depends on real V1/V2 model which isn't loaded here.
    assert isinstance(out, list)
    for n in out:
        assert isinstance(n, Neighbor)
        assert n.id
