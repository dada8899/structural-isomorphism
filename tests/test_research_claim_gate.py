import hashlib
import json
from pathlib import Path

from scripts.research_claim_gate import DEFAULT_LEDGER, ROOT, validate


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    (root / "evidence").mkdir(parents=True)
    (root / "paper").mkdir()
    evidence = root / "evidence/result.json"
    evidence.write_text('{"result":"bounded"}', encoding="utf-8")
    manuscript_line = "The bounded fixture is PASS-CONFIRMED."
    (root / "paper/draft.md").write_text(
        f"# Draft\n\n## Abstract\n{manuscript_line}\n", encoding="utf-8"
    )
    claim = {
        "claim_id": "C-1", "headline": True,
        "exact_wording": "A bounded result was observed.",
        "scope": "This fixture only.",
        "status": "reviewer-readable-do-not-submit",
        "evidence": [{"path": "evidence/result.json", "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}],
        "command": "python3 analysis.py", "environment": "test", "seed": None,
        "result_figure_table": "result.json", "provenance": "fixture",
        "independence": "internal only", "caveats": ["Not externally reviewed."],
    }
    ledger = {
        "schema_version": "1.0.0", "manuscript": "paper/draft.md",
        "manuscript_status": "reviewer-readable-do-not-submit",
        "review_status": "internal-review-only", "external_review_completed": False,
        "manuscript_claim_inventory": [{
            "line_sha256": hashlib.sha256(manuscript_line.encode()).hexdigest(),
            "claim_ids": ["C-1"], "disposition": "bounded",
        }],
        "conflict_register": [{
            "conflict_id": "X-1", "claim_ids": ["C-1"],
            "evidence": [{"path": "evidence/result.json", "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}],
            "resolution": "Exclude the conflicted claim from submission.",
            "submission_blocking": True,
        }],
        "claims": [claim],
    }
    path = root / "ledger.json"
    path.write_text(json.dumps(ledger), encoding="utf-8")
    return root, path


def _mutate(path: Path, callback) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    callback(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_repository_ledger_passes() -> None:
    assert validate(DEFAULT_LEDGER, ROOT) == []


def test_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    root, ledger = _fixture(tmp_path)
    (root / "evidence/result.json").write_text("changed", encoding="utf-8")
    assert any("hash mismatch" in error for error in validate(ledger, root))


def test_missing_headline_evidence_fails_closed(tmp_path: Path) -> None:
    root, ledger = _fixture(tmp_path)
    _mutate(ledger, lambda data: data["claims"][0].update(evidence=[]))
    assert any("no evidence" in error for error in validate(ledger, root))


def test_placeholder_identifier_fails_closed(tmp_path: Path) -> None:
    root, ledger = _fixture(tmp_path)
    (root / "paper/draft.md").write_text("DOI: TBD", encoding="utf-8")
    assert any("placeholder DOI/arXiv" in error for error in validate(ledger, root))


def test_absolute_universality_and_fake_external_review_fail(tmp_path: Path) -> None:
    root, ledger = _fixture(tmp_path)
    def mutate(data):
        data["external_review_completed"] = True
        data["claims"][0]["exact_wording"] = "This proves a universal law of all systems."
    _mutate(ledger, mutate)
    errors = validate(ledger, root)
    assert any("external_review_completed" in error for error in errors)
    assert any("absolute universality" in error for error in errors)


def test_malformed_paths_fail_without_crashing(tmp_path: Path) -> None:
    root, ledger = _fixture(tmp_path)
    def mutate(data):
        data["manuscript"] = None
        data["claims"][0]["evidence"][0]["path"] = None
    _mutate(ledger, mutate)
    errors = validate(ledger, root)
    assert any("manuscript path" in error for error in errors)
    assert any("evidence path" in error for error in errors)


def test_unregistered_strong_manuscript_claim_fails_closed(tmp_path: Path) -> None:
    root, ledger = _fixture(tmp_path)
    (root / "paper/draft.md").write_text(
        "# Draft\n\n## Abstract\nThe experiment is PASS-CONFIRMED.\n",
        encoding="utf-8",
    )
    _mutate(ledger, lambda data: data.update(manuscript_claim_inventory=[]))
    assert any("unregistered strong manuscript claim" in error for error in validate(ledger, root))


def test_inventory_is_bidirectional_and_claim_linked(tmp_path: Path) -> None:
    root, ledger = _fixture(tmp_path)
    line = "The experiment is PASS-CONFIRMED."
    (root / "paper/draft.md").write_text(f"# Draft\n\n## Abstract\n{line}\n", encoding="utf-8")
    digest = hashlib.sha256(line.encode()).hexdigest()
    _mutate(ledger, lambda data: data.update(manuscript_claim_inventory=[{
        "line_sha256": digest, "claim_ids": ["C-1"], "disposition": "bounded",
    }]))
    assert validate(ledger, root) == []
    (root / "paper/draft.md").write_text("# Draft\n\n## Abstract\nNo strong claim.\n", encoding="utf-8")
    assert any("stale manuscript claim inventory" in error for error in validate(ledger, root))


def test_unresolved_conflict_must_block_and_exclude(tmp_path: Path) -> None:
    root, ledger = _fixture(tmp_path)
    def mutate(data):
        data["conflict_register"][0]["submission_blocking"] = False
        data["conflict_register"][0]["resolution"] = "Discuss later."
    _mutate(ledger, mutate)
    errors = validate(ledger, root)
    assert any("must block submission" in error for error in errors)
    assert any("must explicitly exclude" in error for error in errors)
