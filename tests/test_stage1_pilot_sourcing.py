from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prepare_stage1_pilot.py"
spec = importlib.util.spec_from_file_location("pilot_sourcing", SCRIPT)
assert spec and spec.loader
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def queue() -> dict:
    return pilot.load_json(pilot.QUEUE)


def checklist() -> dict:
    return pilot.load_json(pilot.CHECKLIST)


def test_checked_in_queue_is_valid_sourcing_only() -> None:
    assert pilot.validate_queue(queue(), checklist()) == {
        "slots": 12, "domains": 4, "formal_evidence": False, "dispatch_ready": False,
    }


def test_every_slot_has_complete_design_fields_but_no_answer() -> None:
    for slot in queue()["slots"]:
        assert set(slot["baselines"]) == pilot.EXPECTED_BASELINES
        assert all(value > 0 for value in slot["budget"].values())
        assert slot["answer_source"] == {
            "state": "NOT_IMPORTED", "locator": None, "digest": None, "imported_into_repository": False,
        }
        assert slot["formal_evidence_allowed"] is False


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda slot: slot["answer_source"].update(state="IMPORTED"), "outcome answer"),
        (lambda slot: slot["answer_source"].update(locator="secret"), "outcome answer"),
        (lambda slot: slot["time_split"].update(t0="2025-01-01"), "must not fabricate"),
        (lambda slot: slot["baselines"].pop(), "strong baselines"),
        (lambda slot: slot["budget"].update(compute_usd_max=0), "positive complete budget"),
        (lambda slot: slot["budget"].update(compute_usd_max=float("nan")), "positive complete budget"),
        (lambda slot: slot["contamination_scan"].update(state="PASS"), "must remain NOT_RUN"),
        (lambda slot: slot.update(formal_evidence_allowed=True), "cannot become formal evidence"),
        (lambda slot: slot.update(task_family="publication_writing"), "unsupported task family"),
        (lambda slot: slot["negative_control"].update(kind="positive_example"), "unsupported negative control"),
    ],
)
def test_placeholder_boundaries_fail_closed(mutate, message: str) -> None:
    slot = copy.deepcopy(queue()["slots"][0])
    mutate(slot)
    with pytest.raises(pilot.PilotValidationError, match=message):
        pilot.validate_slot(slot)


def test_expert_packet_is_answer_blind_and_digest_stable() -> None:
    packet = pilot.expert_packet(queue()["slots"][0], checklist())
    assert "answer_source" not in packet
    assert packet["answer_source_state"] == "NOT_IMPORTED"
    digest = packet.pop("packet_sha256")
    assert digest == pilot.canonical_sha256(packet)
    assert all(item["result"] == "NOT_RUN" for item in packet["contamination_questions"])


def test_packet_writer_is_private_and_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "packets"
    pilot.write_packets(queue(), checklist(), output)
    paths = sorted(output.glob("*.json"))
    assert len(paths) == 12
    assert paths[0].stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        pilot.write_packets(queue(), checklist(), output)


def test_contamination_checklist_missing_answer_absence_fails() -> None:
    changed = checklist()
    changed["checks"] = [item for item in changed["checks"] if item["id"] != "answer_absence"]
    with pytest.raises(pilot.PilotValidationError, match="incomplete|exact nine leakage checks"):
        pilot.validate_checklist(changed)


def test_queue_requires_exact_four_by_three_matrix() -> None:
    changed = queue()
    changed["slots"][11]["domain"] = "earth_systems"
    changed["slots"][11]["expert_role"]["domain_expertise"] = pilot.EXPECTED_EXPERTISE["earth_systems"]
    with pytest.raises(pilot.PilotValidationError, match="4-domain x 3-family"):
        pilot.validate_queue(changed, checklist())


def test_queue_requires_one_equal_budget() -> None:
    changed = queue()
    changed["slots"][0]["budget"]["compute_usd_max"] += 1
    with pytest.raises(pilot.PilotValidationError, match="equal frozen budget"):
        pilot.validate_queue(changed, checklist())


def test_all_nine_contamination_questions_are_frozen() -> None:
    changed = checklist()
    changed["checks"][0]["question"] = "Reveal the answer to the packet recipient."
    with pytest.raises(pilot.PilotValidationError, match="questions drifted"):
        pilot.validate_checklist(changed)


def test_contamination_result_states_and_dispatch_rule_are_frozen() -> None:
    changed = checklist()
    changed["result_states"].append("SKIPPED")
    with pytest.raises(pilot.PilotValidationError, match="result states mismatch"):
        pilot.validate_checklist(changed)


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"value":NaN}'])
def test_json_loader_rejects_duplicate_keys_and_nonfinite(tmp_path: Path, raw: str) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(pilot.PilotValidationError, match="duplicate JSON key|non-finite"):
        pilot.load_json(path)


def test_json_loader_rejects_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(pilot.PilotValidationError, match="non-symlink"):
        pilot.load_json(link)


def test_packet_digest_is_deterministic() -> None:
    first = pilot.expert_packet(queue()["slots"][0], checklist())
    second = pilot.expert_packet(queue()["slots"][0], checklist())
    assert first == second


def test_packet_writer_rejects_symlink_output(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "packets"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(pilot.PilotValidationError, match="symlink"):
        pilot.write_packets(queue(), checklist(), link)


def test_duplicate_slot_ids_fail() -> None:
    changed = queue()
    changed["slots"][1]["slot_id"] = changed["slots"][0]["slot_id"]
    with pytest.raises(pilot.PilotValidationError, match="IDs must be unique"):
        pilot.validate_queue(changed, checklist())


def test_slot_ids_are_the_exact_frozen_sequence() -> None:
    changed = queue()
    changed["slots"][0]["slot_id"] = "pilot-99"
    with pytest.raises(pilot.PilotValidationError, match="pilot-01 through pilot-12"):
        pilot.validate_queue(changed, checklist())


def test_schema_is_strict_and_queue_remains_formal_no_go() -> None:
    schema = json.loads((ROOT / "evaluation/stage1/schemas/pilot-sourcing-slot-v1.schema.json").read_text())
    assert schema["additionalProperties"] is False
    assert schema["properties"]["formal_evidence_allowed"]["const"] is False
    assert queue()["status"] == "PILOT_SOURCING_ONLY_FORMAL_NO_GO"
