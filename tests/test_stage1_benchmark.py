from __future__ import annotations

import copy
import importlib.util
import json
import hashlib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_stage1_benchmark.py"
STAGE1 = ROOT / "evaluation" / "stage1"

spec = importlib.util.spec_from_file_location("stage1_validator", SCRIPT)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def manifest() -> dict:
    return validator.load_json(STAGE1 / "manifest-v1.json")


def problems() -> list[dict]:
    return validator.load_jsonl(STAGE1 / "fixtures" / "synthetic-problems-v1.jsonl")


def test_synthetic_implementation_package_is_valid_but_not_evidence() -> None:
    summary = validator.validate_manifest(
        STAGE1,
        manifest(),
        formal=False,
        results_path=STAGE1 / "fixtures" / "synthetic-results-v1.jsonl",
    )
    assert summary == {
        "benchmark_id": "stc-stage1-synthetic-implementation-v1",
        "status": "IMPLEMENTATION_ONLY_NOT_STARTED",
        "tasks": 2,
        "arms": 13,
        "results": 2,
        "scientific_evidence": False,
    }


def test_formal_mode_rejects_synthetic_fixture() -> None:
    with pytest.raises(validator.ValidationError, match="rejects implementation"):
        validator.validate_manifest(STAGE1, manifest(), formal=True, results_path=None)


def test_formal_mode_fails_closed_when_results_are_omitted() -> None:
    changed = manifest()
    changed.update(status="FORMAL_FROZEN", evidence_class="historical", scientific_claim_allowed=True)
    changed["immutable_digest"] = validator.manifest_digest(changed)
    with pytest.raises(validator.ValidationError, match="requires a sealed, complete results file"):
        validator.validate_manifest(STAGE1, changed, formal=True, results_path=None)


def test_manifest_digest_is_immutable() -> None:
    changed = manifest()
    changed["budgets"][0]["wall_seconds_max"] += 1
    with pytest.raises(validator.ValidationError, match="immutable_digest mismatch"):
        validator.validate_manifest(STAGE1, changed, formal=False, results_path=None)


def test_artifact_digest_is_fail_closed() -> None:
    changed = manifest()
    changed["artifacts"][0]["sha256"] = "0" * 64
    changed["immutable_digest"] = validator.manifest_digest(changed)
    with pytest.raises(validator.ValidationError, match="artifact digest mismatch"):
        validator.validate_manifest(STAGE1, changed, formal=False, results_path=None)


def test_unsafe_artifact_path_is_rejected() -> None:
    with pytest.raises(validator.ValidationError, match="unsafe artifact path"):
        validator.safe_artifact_path(STAGE1, "../secret")


def test_symlinked_artifact_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    real.write_text("{}\n", encoding="utf-8")
    link = tmp_path / "linked.json"
    link.symlink_to(real)
    with pytest.raises(validator.ValidationError, match="symlink"):
        validator.safe_artifact_path(tmp_path, "linked.json")


def test_symlinked_parent_directory_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "artifact.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "alias").symlink_to(real, target_is_directory=True)
    with pytest.raises(validator.ValidationError, match="symlink"):
        validator.sha256_artifact(tmp_path, "alias/artifact.json")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda row: row["information_boundary"].update(latest_allowed_publication_at=row["t0"]), "cutoff must precede"),
        (lambda row: row["outcome_release"].update(available_after_t0=row["t0"]), "after t0"),
        (lambda row: row["contamination"].update(near_duplicate_check="not_run"), "contamination checks"),
        (lambda row: row["controls"].update(matched_non_isomorph=False), "matched non-isomorph"),
        (lambda row: row.update(unexpected=True), "extra"),
    ],
)
def test_problem_schema_and_chronology_fail_closed(mutate, message: str) -> None:
    row = copy.deepcopy(problems()[0])
    mutate(row)
    with pytest.raises(validator.ValidationError, match=message):
        validator.validate_problem(row)


def test_duplicate_json_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.jsonl"
    path.write_text('{"task_id":"one","task_id":"two"}\n', encoding="utf-8")
    with pytest.raises(validator.ValidationError, match="duplicate JSON key"):
        validator.load_jsonl(path)


def test_nonfinite_number_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "nan.json"
    path.write_text('{"value": NaN}\n', encoding="utf-8")
    with pytest.raises(validator.ValidationError, match="non-finite"):
        validator.load_json(path)


def test_vfu_cannot_be_true_when_any_gate_fails() -> None:
    row = validator.load_jsonl(STAGE1 / "fixtures" / "synthetic-results-v1.jsonl")[0]
    row["vfu"]["verified_useful_discovery"] = True
    budgets = {item["budget_id"]: item for item in manifest()["budgets"]}
    arms = {item["arm_id"] for item in manifest()["arms"]}
    with pytest.raises(validator.ValidationError, match="VFU conjunction"):
        validator.validate_result(row, arms, budgets, "budget_synthetic_ci")


def test_fatal_event_forces_vfu_false_and_consistent_flag() -> None:
    row = validator.load_jsonl(STAGE1 / "fixtures" / "synthetic-results-v1.jsonl")[0]
    row["fatal_events"] = ["fabricated_citation"]
    budgets = {item["budget_id"]: item for item in manifest()["budgets"]}
    arms = {item["arm_id"] for item in manifest()["arms"]}
    with pytest.raises(validator.ValidationError, match="no_fatal_error conflicts"):
        validator.validate_result(row, arms, budgets, "budget_synthetic_ci")


def test_budget_overrun_requires_terminal_status() -> None:
    row = validator.load_jsonl(STAGE1 / "fixtures" / "synthetic-results-v1.jsonl")[0]
    row["budget_usage"]["wall_seconds"] = 61
    budgets = {item["budget_id"]: item for item in manifest()["budgets"]}
    arms = {item["arm_id"] for item in manifest()["arms"]}
    with pytest.raises(validator.ValidationError, match="exceeds budget"):
        validator.validate_result(row, arms, budgets, "budget_synthetic_ci")


def test_exactly_eight_numbered_ablations_required() -> None:
    changed = manifest()
    changed["arms"] = [arm for arm in changed["arms"] if arm.get("ablation_index") != 8]
    changed["immutable_digest"] = validator.manifest_digest(changed)
    with pytest.raises(validator.ValidationError, match="exactly eight ablations"):
        validator.validate_manifest(STAGE1, changed, formal=False, results_path=None)


def test_duplicate_ablation_index_cannot_hide_a_ninth_ablation() -> None:
    changed = manifest()
    changed["arms"].append({"arm_id": "extra_ablation", "kind": "ablation", "ablation_index": 8})
    changed["immutable_digest"] = validator.manifest_digest(changed)
    with pytest.raises(validator.ValidationError, match="exactly eight ablations"):
        validator.validate_manifest(STAGE1, changed, formal=False, results_path=None)


def test_results_outside_benchmark_root_are_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "results.jsonl"
    outside.write_text((STAGE1 / "fixtures" / "synthetic-results-v1.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(validator.ValidationError, match="inside benchmark root"):
        validator.validate_manifest(STAGE1, manifest(), formal=False, results_path=outside)


def test_duplicate_run_id_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "stage1"
    (root / "schemas").mkdir(parents=True)
    (root / "fixtures").mkdir()
    for relative in ["schemas/problem-package-v1.schema.json", "schemas/run-result-v1.schema.json", "fixtures/synthetic-problems-v1.jsonl"]:
        target = root / relative
        target.write_bytes((STAGE1 / relative).read_bytes())
    rows = validator.load_jsonl(STAGE1 / "fixtures" / "synthetic-results-v1.jsonl")
    rows[1]["run_id"] = rows[0]["run_id"]
    results = root / "fixtures" / "synthetic-results-v1.jsonl"
    results.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    changed = manifest()
    for artifact in changed["artifacts"]:
        artifact["sha256"] = hashlib.sha256((root / artifact["path"]).read_bytes()).hexdigest()
    changed["immutable_digest"] = validator.manifest_digest(changed)
    with pytest.raises(validator.ValidationError, match="duplicate run_id"):
        validator.validate_manifest(root, changed, formal=False, results_path=results)


def test_schemas_are_valid_json_and_strict() -> None:
    for name in ["problem-package-v1.schema.json", "run-result-v1.schema.json"]:
        schema = json.loads((STAGE1 / "schemas" / name).read_text(encoding="utf-8"))
        assert schema["additionalProperties"] is False
        assert schema["$schema"].endswith("2020-12/schema")
