from __future__ import annotations

import json

import pytest

from scripts.wto_reproducibility import (
    SCHEMA,
    cluster_bootstrap,
    cluster_id,
    coding_bundle,
    coding_disagreements,
    leave_one_cluster_out,
    load_rows,
    validate_codings,
)


@pytest.fixture(scope="module")
def rows():
    return load_rows()


@pytest.fixture(scope="module")
def bundle(rows):
    return coding_bundle(rows)


def coding(task, bundle, coder="coder-a"):
    return {
        "schema_version": SCHEMA, "task_id": task["task_id"],
        "bundle_fingerprint": bundle["bundle_fingerprint"], "coder_id": coder,
        "ds_no": task["ds_no"], "sunk_cost_stage": "independent-stage",
        "sunk_cost_s": 0.5, "defendant_complied_24mo": 1,
        "source_citations": ["WTO official summary, identified section"],
        "confidence": "medium", "note": "",
    }


def test_policy_clusters_cover_known_linked_cases(rows):
    assert cluster_id("103") == cluster_id("113")
    assert cluster_id("217") == cluster_id("234")
    assert cluster_id("257") == cluster_id("264") == cluster_id("277")
    assert len({cluster_id(row["ds_no"]) for row in rows}) < len(rows)


def test_cluster_bootstrap_and_loo_are_deterministic(rows):
    first = cluster_bootstrap(rows, samples=100)
    second = cluster_bootstrap(rows, samples=100)
    assert first == second
    assert first["n_rows"] == 23
    assert first["n_policy_clusters"] == 17
    loo = leave_one_cluster_out(rows)
    assert len(loo["fits"]) == 17
    assert loo["all_converged"] is True


def test_bundle_is_blinded_deterministic_and_complete(rows, bundle):
    assert bundle == coding_bundle(rows)
    assert bundle["task_count"] == 23
    assert len({task["task_id"] for task in bundle["tasks"]}) == 23
    serialized = json.dumps(bundle)
    for forbidden in ("outcome_basis", "defendant_complied_24mo", "sunk_cost_s"):
        assert forbidden not in serialized


def test_coding_validation_requires_sources_and_one_coder(bundle):
    values = [coding(task, bundle) for task in bundle["tasks"]]
    assert len(validate_codings(values, bundle)) == 23
    missing_source = {**values[0], "source_citations": []}
    with pytest.raises(ValueError, match="requires source citations"):
        validate_codings([missing_source], bundle, require_complete=False)
    mixed = [{**values[0], "coder_id": "a"}, {**values[1], "coder_id": "b"}]
    with pytest.raises(ValueError, match="one coding file"):
        validate_codings(mixed, bundle, require_complete=False)


def test_comparison_reports_only_disputed_fields(bundle):
    first = [coding(task, bundle, "a") for task in bundle["tasks"]]
    second = [coding(task, bundle, "b") for task in bundle["tasks"]]
    second[0]["defendant_complied_24mo"] = 0
    disputes = coding_disagreements(first, second)
    assert disputes == [{
        "task_id": first[0]["task_id"], "ds_no": first[0]["ds_no"],
        "disputed_fields": ["defendant_complied_24mo"],
    }]
