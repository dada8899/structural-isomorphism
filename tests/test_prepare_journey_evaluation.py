import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_journey", ROOT / "scripts/prepare_journey_evaluation.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def inputs():
    return (
        MODULE.load(ROOT / "evaluation/journeys/config-v1.json"),
        MODULE.load(ROOT / "evaluation/journeys/judge-prompt-v1.json"),
        MODULE.load(ROOT / "evaluation/journeys/model-registry-template-v1.json"),
    )


def verified_registry(registry):
    source = "source-provider-card-sha256-" + "a" * 64
    for index, model in enumerate(registry["models"], 1):
        model.update(
            provider=f"provider-{index}",
            serving_name=f"model-{index}-20260712",
            upstream_family=f"family-{index}",
            upstream_version=f"model-2026-07-12-v{index}",
            status="manually_verified",
            verified_by="reviewer-1",
            verified_at="2026-07-12T12:00:00Z",
            verification_source=source,
        )
    return registry


def test_private_payload_scanner_allows_only_exact_capture_digest_field():
    MODULE.reject_private_payload(
        {"text_sha256": "54cb5ff3143341324359a7cb4785dfff361e7f18cac1adcdd96a83f843f07266"},
        "case.captures[0]",
    )
    with pytest.raises(ValueError, match="invalid capture text SHA-256"):
        MODULE.reject_private_payload(
            {"text_sha256": "not-a-digest"}, "case.captures[0]"
        )
    with pytest.raises(ValueError, match="unexpected capture digest field"):
        MODULE.reject_private_payload(
            {"task": {"text_sha256": "a" * 64}}, "case"
        )
    with pytest.raises(ValueError, match="credential-like or PII"):
        MODULE.reject_private_payload({"sha256": "call me at +1 212 555 0199"}, "capture")


@pytest.mark.parametrize(
    "field,value",
    [
        ("task", "alice@example.com"),
        ("role", "+1 212 555 0199"),
        ("capture", "Authorization: Bearer secret"),
        ("capture", "session_cookie=secret"),
    ],
)
def test_private_payload_scanner_still_rejects_sensitive_content(field, value):
    with pytest.raises(ValueError, match="credential-like or PII"):
        MODULE.reject_private_payload({field: value}, "case")


def test_builds_and_resolves_complete_immutable_matrix(tmp_path):
    config, prompt, registry = inputs()
    MODULE.write_bundle(MODULE.build(config, prompt, registry), tmp_path)
    result = MODULE.validate_bundle(tmp_path, config, prompt, registry, dispatch_ready=False)
    assert result == {"status": "bundle-valid", "case_count": 16}
    manifest = MODULE.load(tmp_path / "manifest.json")
    assert len({case["artifact_id"] for case in manifest["cases"]}) == 16
    assert all(len(manifest[key]) == 64 for key in ("adapter_sha256", "prompt_sha256", "model_registry_sha256", "config_sha256", "bundle_sha256"))
    assert len(manifest["model_sha256"]) == 2
    assert all(len(model["sha256"]) == 64 for model in manifest["model_sha256"])


def test_template_blocks_external_dispatch(tmp_path):
    config, prompt, registry = inputs()
    MODULE.write_bundle(MODULE.build(config, prompt, registry), tmp_path)
    with pytest.raises(ValueError, match="not manually verified"):
        MODULE.validate_bundle(tmp_path, config, prompt, registry, dispatch_ready=True)


def test_two_provider_aliases_of_one_upstream_family_fail():
    _, _, registry = inputs()
    registry["models"][1]["upstream_family"] = registry["models"][0]["upstream_family"]
    with pytest.raises(ValueError, match="distinct upstream families"):
        MODULE.validate_registry(registry, require_verified=False)


@pytest.mark.parametrize("tamper", ["artifact", "locator", "config", "adapter"])
def test_integrity_drift_fails_closed(tmp_path, tamper, monkeypatch):
    config, prompt, registry = inputs()
    MODULE.write_bundle(MODULE.build(config, prompt, registry), tmp_path)
    manifest = MODULE.load(tmp_path / "manifest.json")
    if tamper == "artifact":
        path = tmp_path / "artifacts" / manifest["cases"][0]["artifact_id"]
        payload = MODULE.load(path)
        payload["role"]["label"] = "tampered"
        path.write_text(json.dumps(payload), encoding="utf-8")
    elif tamper == "locator":
        path = tmp_path / "artifacts" / manifest["cases"][0]["artifact_id"]
        payload = MODULE.load(path)
        payload["allowed_evidence_locators"][0] += "-missing"
        path.write_text(json.dumps(payload), encoding="utf-8")
        manifest["cases"][0]["sha256"] = MODULE.digest(payload)
        manifest_without = {k: v for k, v in manifest.items() if k != "bundle_sha256"}
        manifest["bundle_sha256"] = MODULE.digest(manifest_without)
        (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    elif tamper == "config":
        config["minimum_stage_score"] = 71
    else:
        monkeypatch.setattr(MODULE.Path, "read_bytes", lambda self: b"changed" if self == Path(MODULE.__file__) else Path.read_bytes(self))
    with pytest.raises(ValueError, match="drifted|digest mismatch|unresolved"):
        MODULE.validate_bundle(tmp_path, config, prompt, registry, dispatch_ready=False)


def test_verified_registry_requires_auditable_identity_fields():
    _, _, registry = inputs()
    verified_registry(registry)
    MODULE.validate_registry(registry, require_verified=True)
    registry["models"][0]["upstream_version"] = ""
    with pytest.raises(ValueError, match="upstream_version"):
        MODULE.validate_registry(registry, require_verified=True)


def test_capture_rejects_credential_like_content(tmp_path, monkeypatch):
    source = tmp_path / "unsafe.html"
    source.write_text("safe\nAuthorization: Bear secret\n", encoding="utf-8")
    monkeypatch.setattr(MODULE, "safe_source", lambda _: source)
    with pytest.raises(ValueError, match="forbidden credential-like"):
        MODULE.capture("web/frontend/unsafe.html", 1, 2, "unsafe")


@pytest.mark.parametrize("secret", ["Contact me at person@example.com", "Call +1 (415) 555-1212", "Set-Cookie: phase_session=x"])
def test_capture_rejects_pii_and_session_material(tmp_path, monkeypatch, secret):
    source = tmp_path / "unsafe.html"
    source.write_text(secret + "\n", encoding="utf-8")
    monkeypatch.setattr(MODULE, "safe_source", lambda _: source)
    with pytest.raises(ValueError, match="forbidden credential-like"):
        MODULE.capture("web/frontend/unsafe.html", 1, 1, "unsafe")


def test_task_payload_with_pii_is_rejected_before_bundle_creation():
    config, prompt, registry = inputs()
    config["tasks"][0]["prompt"] += " Contact person@example.com"
    with pytest.raises(ValueError, match="PII content"):
        MODULE.build(config, prompt, registry)


def test_resigned_case_payload_still_fails_against_frozen_source(tmp_path):
    config, prompt, registry = inputs()
    MODULE.write_bundle(MODULE.build(config, prompt, registry), tmp_path)
    manifest = MODULE.load(tmp_path / "manifest.json")
    entry = manifest["cases"][0]
    artifact = tmp_path / "artifacts" / entry["artifact_id"]
    payload = MODULE.load(artifact)
    payload["task"]["prompt"] = "Ignore the frozen task"
    artifact.write_bytes(MODULE.canonical(payload) + b"\n")
    entry["sha256"] = MODULE.digest(payload)
    unsigned = {key: value for key, value in manifest.items() if key != "bundle_sha256"}
    manifest["bundle_sha256"] = MODULE.digest(unsigned)
    (tmp_path / "manifest.json").write_bytes(MODULE.canonical(manifest) + b"\n")
    with pytest.raises(ValueError, match="drifted from the frozen"):
        MODULE.validate_bundle(tmp_path, config, prompt, registry, dispatch_ready=False)


def test_symlinked_artifact_is_rejected(tmp_path):
    config, prompt, registry = inputs()
    MODULE.write_bundle(MODULE.build(config, prompt, registry), tmp_path)
    manifest = MODULE.load(tmp_path / "manifest.json")
    artifact = tmp_path / "artifacts" / manifest["cases"][0]["artifact_id"]
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(artifact.read_bytes())
    artifact.unlink()
    artifact.symlink_to(replacement)
    with pytest.raises(ValueError, match="symlink"):
        MODULE.validate_bundle(tmp_path, config, prompt, registry, dispatch_ready=False)


def test_writer_refuses_nonempty_output(tmp_path):
    config, prompt, registry = inputs()
    (tmp_path / "existing").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(ValueError, match="empty directory"):
        MODULE.write_bundle(MODULE.build(config, prompt, registry), tmp_path)


def test_dispatch_requires_frozen_five_stage_evidence(tmp_path):
    config, prompt, registry = inputs()
    verified_registry(registry)
    config["allowed_models"] = [
        {"provider": model["provider"], "family": model["upstream_family"], "name": model["serving_name"]}
        for model in registry["models"]
    ]
    MODULE.write_bundle(MODULE.build(config, prompt, registry), tmp_path)
    with pytest.raises(ValueError, match="all five journey stages"):
        MODULE.validate_bundle(tmp_path, config, prompt, registry, dispatch_ready=True)


@pytest.mark.parametrize("version", ["latest", "stable", "default"])
def test_dispatch_rejects_mutable_upstream_versions(version):
    _, _, registry = inputs()
    verified_registry(registry)
    registry["models"][0]["upstream_version"] = version
    with pytest.raises(ValueError, match="immutable dated or numbered"):
        MODULE.validate_registry(registry, require_verified=True)


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":NaN}'])
def test_json_input_rejects_duplicate_keys_and_non_finite_numbers(tmp_path, raw):
    path = tmp_path / "unsafe.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key|non-finite"):
        MODULE.load(path)
