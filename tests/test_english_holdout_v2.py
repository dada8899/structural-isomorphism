import copy

import pytest

from scripts.build_english_holdout_v2 import OLD_DATASET, build, read_jsonl, tokens, validate


def rows():
    old = read_jsonl(OLD_DATASET)
    return build(old), [row["query"] for row in old if row["language"] == "en"]


def test_holdout_is_deterministic_sealed_and_clustered():
    first, old = rows()
    second, _ = rows()
    assert first == second
    assert len(first) == 200
    assert sum(row["expected_scope"] == "in_scope" for row in first) == 100
    assert sum(row["expected_scope"] == "out_of_scope" for row in first) == 100
    assert sum(row["dangerous"] for row in first) == 40
    assert len({" ".join(sorted(tokens(row["query"]))) for row in first}) == 200
    assert len({row["query"] for row in first if row["expected_scope"] == "out_of_scope"}) == 100
    assert len({row["query"] for row in first if row["dangerous"]}) == 40
    mechanisms = {}
    for row in first[:100]:
        mechanisms.setdefault(row["cluster"]["mechanism"], set()).add(row["cluster"]["user"])
    assert all(len(users) >= 5 for users in mechanisms.values())
    assert all(row["labels"] is None for row in first)
    validate(first, old)


def test_labels_or_missing_clusters_fail_closed():
    values, old = rows()
    labelled = copy.deepcopy(values); labelled[0]["labels"] = {"relevance": 3}
    with pytest.raises(ValueError, match="label seal"):
        validate(labelled, old)
    broken = copy.deepcopy(values); broken[0]["cluster"].pop("user")
    with pytest.raises(ValueError, match="cluster"):
        validate(broken, old)


def test_development_near_duplicate_fails():
    values, old = rows()
    values[0]["query"] = old[0]
    with pytest.raises(ValueError, match="near duplicate"):
        validate(values, old)


def test_internal_near_duplicate_fails():
    values, old = rows()
    values[1]["query"] = values[0]["query"]
    with pytest.raises(ValueError, match="duplicate"):
        validate(values, old)
