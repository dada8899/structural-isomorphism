import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("journey_eval", ROOT / "scripts/evaluate_user_journeys.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def inputs():
    config = MODULE.load_json(ROOT / "evaluation/journeys/config-v1.json")
    rows = MODULE.load_jsonl(ROOT / "evaluation/journeys/offline-fixture-v1.jsonl")
    return config, rows


def test_offline_fixture_is_valid_and_reports_disagreement():
    config, rows = inputs()
    MODULE.validate_config(config)
    report = MODULE.aggregate(rows, config, require_complete=False)
    group = report["groups"][0]
    assert group["weighted_score"] == 78.4
    assert group["verdict_agreement"] == 0.5
    assert group["stage_scores"]["recovery"]["variance"] == 4
    assert group["status"] == "fail"
    assert report["run_id"] == "offline-001"
    assert len(report["config_sha256"]) == 64


@pytest.mark.parametrize("mutation", ["missing_stage", "float_score", "empty_evidence", "bad_locator", "extra_field"])
def test_judgments_fail_closed(mutation):
    config, rows = inputs()
    row = copy.deepcopy(rows[0])
    if mutation == "missing_stage":
        del row["stages"]["recovery"]
    elif mutation == "float_score":
        row["stages"]["input"]["score"] = 88.5
    elif mutation == "empty_evidence":
        row["stages"]["result"]["evidence"] = []
    elif mutation == "bad_locator":
        row["stages"]["action"]["evidence"] = ["looks convincing"]
    else:
        row["confidence"] = 0.9
    with pytest.raises(ValueError):
        MODULE.validate_row(row, config)


def test_same_family_is_not_heterogeneous():
    config, rows = inputs()
    rows[1]["model"]["family"] = rows[0]["model"]["family"]
    config["allowed_models"][1]["family"] = rows[0]["model"]["family"]
    with pytest.raises(ValueError, match="not heterogeneous"):
        MODULE.aggregate(rows, config, require_complete=False)


def test_missing_second_model_fails():
    config, rows = inputs()
    with pytest.raises(ValueError, match="insufficient models"):
        MODULE.aggregate(rows[:1], config, require_complete=False)


def test_partial_matrix_fails_release_gate():
    config, rows = inputs()
    with pytest.raises(ValueError, match="incomplete role/task matrix"):
        MODULE.aggregate(rows, config)


def test_multiple_run_ids_fail():
    config, rows = inputs()
    rows[1]["run_id"] = "different-run"
    with pytest.raises(ValueError, match="exactly one run_id"):
        MODULE.aggregate(rows, config, require_complete=False)


def test_unregistered_model_identity_fails():
    config, rows = inputs()
    rows[1]["model"]["family"] = "alias-family"
    with pytest.raises(ValueError, match="frozen allowed_models"):
        MODULE.aggregate(rows, config, require_complete=False)


def test_non_finite_config_number_fails(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"weight": NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite JSON number"):
        MODULE.load_json(path)


def test_abstention_is_never_a_pass():
    config, rows = inputs()
    rows[1]["verdict"] = "abstain"
    for stage in rows[1]["stages"].values():
        stage["score"] = 90
    report = MODULE.aggregate(rows, config, require_complete=False)
    assert report["groups"][0]["status"] == "fail"


def test_pass_below_floor_is_rejected():
    config, rows = inputs()
    rows[0]["stages"]["recovery"]["score"] = 69
    with pytest.raises(ValueError, match="verdict conflicts"):
        MODULE.validate_row(rows[0], config)


@pytest.mark.parametrize("locator", [
    "https://example.com/result#claim",
    "artifact://../secret#token",
    "artifact://sample/result#",
])
def test_unsafe_or_external_evidence_locator_fails(locator):
    config, rows = inputs()
    rows[0]["stages"]["result"]["evidence"] = [locator]
    with pytest.raises(ValueError, match="safe artifact locator"):
        MODULE.validate_row(rows[0], config)


def test_frozen_role_registry_covers_required_perspectives():
    config, _ = inputs()
    assert {role["id"] for role in config["roles"]} == {
        "research_pm", "growth_lead", "doctoral_researcher", "first_time_user",
        "non_technical_user", "mobile_user", "screen_reader_user", "skeptical_reviewer",
    }
