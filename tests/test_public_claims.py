import json
from pathlib import Path

from scripts.check_public_claims import DEFAULT_INVENTORY, ROOT, validate


def test_repository_current_public_copy_passes() -> None:
    assert validate(DEFAULT_INVENTORY, ROOT) == []


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "page.html").write_text("Plain decision summary. Next: inspect evidence.", encoding="utf-8")
    inventory = {
        "schema_version": "current-public-copy-v1",
        "scope": {"runtime_pages": ["page.html"], "current_documents": [], "excluded_contexts": []},
        "forbidden_patterns": ["verified universal law"],
        "required_context": [{"path": "page.html", "patterns": ["Next: inspect evidence."]}],
        "context_rules": [{"term": "verified", "allowed": "checksum", "forbidden": "mechanism proof"}],
        "readability_contract": {
            "first_use": "Explain terms.", "two_layers": "Summary then detail.",
            "actionable_states": "Give a next step.", "buttons": "Use user actions.",
            "restatement_test": "State known, uncertain, next."
        },
    }
    path = root / "inventory.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")
    return root, path


def test_forbidden_claim_fails_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    (root / "page.html").write_text("This is a verified universal law. Next: inspect evidence.")
    errors = validate(inventory, root)
    assert any("forbidden public claim" in error for error in errors)


def test_missing_context_and_readability_contract_fail(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    data = json.loads(inventory.read_text())
    data["readability_contract"].pop("restatement_test")
    inventory.write_text(json.dumps(data))
    (root / "page.html").write_text("Plain summary.")
    errors = validate(inventory, root)
    assert any("missing required context" in error for error in errors)
    assert any("readability_contract" in error for error in errors)
