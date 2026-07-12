from scripts.validate_evidence_assets import (
    DISCOVERIES,
    KB,
    KB_SCHEMA,
    LADDER,
    migrate_legacy_kb_row,
    normalize_discovery,
    normalize_variable_mapping,
    read_json,
    validate_kb_vnext_row,
    validate_ladder,
    validate_repository,
)


def test_repository_evidence_asset_contracts_pass() -> None:
    assert validate_repository() == []


def test_evidence_ladder_is_ordered_and_has_no_generic_verified_state() -> None:
    ladder = read_json(LADDER)
    assert validate_ladder(ladder) == []
    assert [item["id"] for item in ladder["levels"]][-2:] == ["externally_reviewed", "replicated"]
    assert "verified" not in {item["id"] for item in ladder["levels"]}


def test_legacy_kb_migration_preserves_unknowns() -> None:
    schema = read_json(KB_SCHEMA)
    legacy = {"id": "x", "name": "n", "domain": "d", "type_id": "01", "description": "text"}
    migrated = migrate_legacy_kb_row(legacy, schema)
    assert migrated["language"] == "zh"
    assert migrated["provenance_class"] == "unknown"
    assert migrated["source"] is None
    assert migrated["source_review"] is None
    assert migrated["license"] == "unknown"
    assert migrated["evidence_level"] == "candidate"
    assert validate_kb_vnext_row(migrated, schema) == []


def test_kb_promotion_requires_real_source_license_and_provenance() -> None:
    schema = read_json(KB_SCHEMA)
    legacy = {"id": "x", "name": "n", "domain": "d", "type_id": "01", "description": "text"}
    promoted = {**migrate_legacy_kb_row(legacy, schema), "evidence_level": "source_backed"}
    errors = validate_kb_vnext_row(promoted, schema)
    assert any("source locator" in error for error in errors)
    assert any("unknown license/provenance" in error for error in errors)
    assert any("source review" in error for error in errors)


def test_discovery_normalization_unifies_equations_and_downgrades_unreviewed() -> None:
    old = {"rank": 1, "equations": ["x=y"], "isomorphism_confidence": 90, "literature_status": "unexplored"}
    new = {"rank": 2, "shared_equation": "a=b", "variable_mapping": {"a": "b"}, "isomorphism_confidence": 0.8}
    first, second = normalize_discovery(old), normalize_discovery(new)
    assert first["shared_equations"] == ["x=y"]
    assert second["shared_equations"] == ["a=b"]
    assert first["model_score_unvalidated"] == 90.0
    assert first["literature_status"] == "not_systematically_reviewed"
    assert first["evidence_level"] == "candidate"


def test_discovery_does_not_promote_on_unreviewed_literature_list() -> None:
    row = {"shared_equation": "x=y", "literature_evidence": [{"source": "doi:example"}]}
    assert normalize_discovery(row)["evidence_level"] == "candidate"


def test_legacy_string_variable_mapping_is_preserved_deterministically() -> None:
    assert normalize_variable_mapping("价格↔负载; 阈值↔容量") == {
        "价格": "负载",
        "阈值": "容量",
    }


def test_mapping_preserves_unstructured_notes_without_inventing_a_pair() -> None:
    assert normalize_variable_mapping("malformed") is None
    assert normalize_variable_mapping("质量↔增益; ζ目标值共享") == {
        "质量": "增益",
        "__unmapped_notes__": "ζ目标值共享",
    }


def test_promoted_row_requires_review_identity_and_date() -> None:
    schema = read_json(KB_SCHEMA)
    legacy = {"id": "x", "name": "n", "domain": "d", "type_id": "01", "description": "text"}
    row = {
        **migrate_legacy_kb_row(legacy, schema),
        "evidence_level": "source_backed",
        "source": {"locator": "https://example.test/data"},
        "license": "CC-BY-4.0",
        "provenance_class": "real",
        "source_review": {},
    }
    assert any("source review" in error for error in validate_kb_vnext_row(row, schema))


def test_all_4443_legacy_rows_migrate_without_invented_evidence() -> None:
    import json

    schema = read_json(KB_SCHEMA)
    rows = [json.loads(line) for line in KB.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 4443
    migrated = [migrate_legacy_kb_row(row, schema) for row in rows]
    assert all(row["source"] is None and row["source_review"] is None for row in migrated)
    assert all(row["license"] == "unknown" and row["provenance_class"] == "unknown" for row in migrated)


def test_legacy_migration_is_deterministic() -> None:
    schema = read_json(KB_SCHEMA)
    row = {"id": "x", "name": "n", "domain": "d", "type_id": "01", "description": "text"}
    assert migrate_legacy_kb_row(row, schema) == migrate_legacy_kb_row(row, schema)


def test_audited_source_backed_row_passes() -> None:
    schema = read_json(KB_SCHEMA)
    row = {
        "id": "x", "name": "n", "domain": "d", "type_id": "01", "description": "text",
        "language": "zh", "provenance_class": "real",
        "source": {"locator": "https://example.test/data"},
        "source_review": {"reviewer": "independent-reviewer", "reviewed_at": "2026-07-12"},
        "license": "CC-BY-4.0", "data_layer": "raw", "evidence_level": "source_backed",
    }
    assert validate_kb_vnext_row(row, schema) == []


def test_discovery_promotes_only_with_complete_reviewed_evidence() -> None:
    row = {
        "shared_equation": "x=y",
        "literature_status": "bounded",
        "literature_evidence": [{
            "source": "https://doi.org/example", "license": "CC-BY-4.0",
            "provenance_class": "literature-derived", "source_review": {"reviewer": "r"},
        }],
    }
    normalized = normalize_discovery(row)
    assert normalized["evidence_level"] == "source_backed"
    assert normalized["literature_status"] == "bounded"


def test_all_39_discovery_equations_and_mappings_normalize() -> None:
    rows = read_json(DISCOVERIES)["discoveries"]
    normalized = [normalize_discovery(row) for row in rows]
    assert len(normalized) == 39
    assert all(row["shared_equations"] for row in normalized)
    assert all(
        normalized[index]["variable_mapping"] is not None
        for index, raw in enumerate(rows) if raw.get("variable_mapping") is not None
    )


def test_ladder_rejects_source_backed_without_review_requirement() -> None:
    ladder = read_json(LADDER)
    source_level = next(item for item in ladder["levels"] if item["id"] == "source_backed")
    source_level["requires"].remove("source_review")
    assert any("source review" in error for error in validate_ladder(ladder))


def test_ladder_prohibits_generic_claims_in_both_languages() -> None:
    prohibited = set(read_json(LADDER)["prohibited_generic_labels"])
    assert {"verified", "confirmed", "已验证", "已确认"} <= prohibited
